"""Feature engineering pipeline ported line-by-line from the training notebook (VajraMLModel.ipynb).

Computes the exact 24 CLEAN_FEATURE_COLS expected by the unscaled HistGradientBoostingClassifier.
Derived variables (cape, cin, precipitable_water) are computed using the notebook's Bolton-style
empirical formulas and clipping ranges.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

CLEAN_FEATURE_COLS = [
    "cape",
    "cin",
    "temperature_2m",
    "dewpoint_2m",
    "relative_humidity",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "cloud_cover",
    "precipitable_water",
    "dew_point_depression",
    "cape_cin_ratio",
    "hour_sin",
    "hour_cos",
    "month_sin",
    "month_cos",
    "latitude",
    "longitude",
    "precip_1hr_ago",
    "precip_last_3hr",
    "storm_2hr_ago",
    "cloud_trend",
    "temp_trend",
    "pressure_trend",
]

CONVECTIVE_CODES = {80, 81, 82, 85, 91, 92, 93, 95, 96, 99}


def compute_thunderstorm_label(
    weather_code: Union[float, int, pd.Series],
    precipitation: Union[float, pd.Series],
    temperature_2m: Union[float, pd.Series],
    relative_humidity_2m: Union[float, pd.Series],
    dew_point_2m: Union[float, pd.Series],
) -> Union[int, pd.Series]:
    """
    Notebook Method 1 + Method 2 combined thunderstorm label:
    1. weather_code in {80, 81, 82, 85, 91, 92, 93, 95, 96, 99}
    2. OR (precipitation > 2.0 AND temperature_2m > 25 AND relative_humidity_2m > 65 AND (temperature_2m - dew_point_2m) < 8)
    """
    if isinstance(weather_code, pd.Series):
        is_convective = weather_code.isin(CONVECTIVE_CODES).astype(int)
        dp_dep = temperature_2m.fillna(25.0) - dew_point_2m.fillna(20.0)
        is_heavy_convective = (
            (precipitation.fillna(0.0) > 2.0)
            & (temperature_2m.fillna(25.0) > 25.0)
            & (relative_humidity_2m.fillna(50.0) > 65.0)
            & (dp_dep < 8.0)
        ).astype(int)
        return ((is_convective == 1) | (is_heavy_convective == 1)).astype(int)
    else:
        wc = int(weather_code) if weather_code is not None and not np.isnan(weather_code) else 0
        p = float(precipitation) if precipitation is not None and not np.isnan(precipitation) else 0.0
        t = float(temperature_2m) if temperature_2m is not None and not np.isnan(temperature_2m) else 25.0
        rh = float(relative_humidity_2m) if relative_humidity_2m is not None and not np.isnan(relative_humidity_2m) else 50.0
        dp = float(dew_point_2m) if dew_point_2m is not None and not np.isnan(dew_point_2m) else 20.0

        is_conv = 1 if wc in CONVECTIVE_CODES else 0
        is_heavy = 1 if (p > 2.0 and t > 25.0 and rh > 65.0 and (t - dp) < 8.0) else 0
        return 1 if (is_conv == 1 or is_heavy == 1) else 0


def engineer_training_features_df(df_in: pd.DataFrame) -> pd.DataFrame:
    """
    Ported line-by-line from Cell 4 and Cell 5 of VajraMLModel.ipynb.
    Converts raw hourly columns into the 24 CLEAN_FEATURE_COLS.
    """
    df = df_in.copy()
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])

    # Map column names if needed
    if "dew_point_2m" not in df.columns and "dewpoint_2m" in df.columns:
        df["dew_point_2m"] = df["dewpoint_2m"]
    if "relative_humidity_2m" not in df.columns and "relative_humidity" in df.columns:
        df["relative_humidity_2m"] = df["relative_humidity"]

    # Compute thunderstorm label for storm lags
    if "thunderstorm" not in df.columns:
        df["thunderstorm"] = compute_thunderstorm_label(
            df["weather_code"],
            df["precipitation"],
            df["temperature_2m"],
            df["relative_humidity_2m"],
            df["dew_point_2m"],
        )

    # --- Raw features with notebook fillna defaults ---
    df["temperature_2m"] = df["temperature_2m"].fillna(25.0)
    df["dewpoint_2m"] = df["dew_point_2m"].fillna(20.0)
    df["relative_humidity"] = df["relative_humidity_2m"].fillna(60.0)
    df["surface_pressure"] = df["surface_pressure"].fillna(1013.0)
    df["wind_speed_10m"] = df["wind_speed_10m"].fillna(5.0)
    df["wind_direction_10m"] = df["wind_direction_10m"].fillna(180.0)
    df["cloud_cover"] = df["cloud_cover"].fillna(50.0)
    df["precipitation"] = df["precipitation"].fillna(0.0)

    # --- Derived thermodynamic stability formulas (Bolton 1980) ---
    e_s = 6.112 * np.exp(17.67 * df["temperature_2m"] / (df["temperature_2m"] + 243.5))
    e_d = 6.112 * np.exp(17.67 * df["dewpoint_2m"] / (df["dewpoint_2m"] + 243.5))

    r_s = 621.97 * e_s / (df["surface_pressure"] - e_s)
    r_d = 621.97 * e_d / (df["surface_pressure"] - e_d)

    theta_e = (
        (df["temperature_2m"] + 273.15)
        * (1000.0 / df["surface_pressure"]) ** 0.286
        * np.exp(2.675e6 * r_d / (1004.0 * (df["temperature_2m"] + 273.15)))
    )

    df["cape"] = ((theta_e - 300.0) * 80.0).clip(lower=0.0, upper=5000.0)
    df["dew_point_depression"] = (df["temperature_2m"] - df["dewpoint_2m"]).clip(lower=0.0)
    df["cin"] = (df["dew_point_depression"] ** 1.5 * 8.0).clip(lower=0.0, upper=400.0)
    df["cape_cin_ratio"] = df["cape"] / df["cin"].clip(lower=1.0)
    df["precipitable_water"] = (r_d * 0.3).clip(lower=5.0, upper=75.0)

    # --- Lag & persistence features ---
    grp = df.groupby("city") if "city" in df.columns else df

    if "city" in df.columns:
        df["precip_1hr_ago"] = df.groupby("city")["precipitation"].shift(1).fillna(0.0)
        df["precip_2hr_ago"] = df.groupby("city")["precipitation"].shift(2).fillna(0.0)
        df["precip_3hr_ago"] = df.groupby("city")["precipitation"].shift(3).fillna(0.0)
        df["storm_1hr_ago"] = df.groupby("city")["thunderstorm"].shift(1).fillna(0.0).astype(int)
        df["storm_2hr_ago"] = df.groupby("city")["thunderstorm"].shift(2).fillna(0.0).astype(int)
        df["cloud_1hr_ago"] = df.groupby("city")["cloud_cover"].shift(1).fillna(50.0)
        df["temp_1hr_ago"] = df.groupby("city")["temperature_2m"].shift(1).fillna(25.0)
        df["pressure_1hr_ago"] = df.groupby("city")["surface_pressure"].shift(1).fillna(1013.0)
    else:
        df["precip_1hr_ago"] = df["precipitation"].shift(1).fillna(0.0)
        df["precip_2hr_ago"] = df["precipitation"].shift(2).fillna(0.0)
        df["precip_3hr_ago"] = df["precipitation"].shift(3).fillna(0.0)
        df["storm_1hr_ago"] = df["thunderstorm"].shift(1).fillna(0.0).astype(int)
        df["storm_2hr_ago"] = df["thunderstorm"].shift(2).fillna(0.0).astype(int)
        df["cloud_1hr_ago"] = df["cloud_cover"].shift(1).fillna(50.0)
        df["temp_1hr_ago"] = df["temperature_2m"].shift(1).fillna(25.0)
        df["pressure_1hr_ago"] = df["surface_pressure"].shift(1).fillna(1013.0)

    df["precip_last_3hr"] = df["precip_1hr_ago"] + df["precip_2hr_ago"] + df["precip_3hr_ago"]
    df["cloud_trend"] = df["cloud_cover"] - df["cloud_1hr_ago"]
    df["temp_trend"] = df["temperature_2m"] - df["temp_1hr_ago"]
    df["pressure_trend"] = df["surface_pressure"] - df["pressure_1hr_ago"]

    # --- Temporal features (from local IST timestamp) ---
    if "time" in df.columns:
        df["hour"] = df["time"].dt.hour
        df["month"] = df["time"].dt.month
        df["hour_sin"] = np.sin(2.0 * np.pi * df["hour"] / 24.0)
        df["hour_cos"] = np.cos(2.0 * np.pi * df["hour"] / 24.0)
        df["month_sin"] = np.sin(2.0 * np.pi * df["month"] / 12.0)
        df["month_cos"] = np.cos(2.0 * np.pi * df["month"] / 12.0)

    df[CLEAN_FEATURE_COLS] = df[CLEAN_FEATURE_COLS].fillna(0.0)
    return df


def build_features_from_raw_slice(
    raw_hourly: Dict[str, List[Any]],
    target_idx: int,
    original_lat: float,
    original_lon: float,
    target_time: datetime,
) -> Dict[str, float]:
    """
    Build 24 CLEAN_FEATURE_COLS vector for a specific hour index from raw Open-Meteo hourly arrays.
    Uses target_idx as hour t, looking back to target_idx-1, target_idx-2, target_idx-3 for lags.
    """
    def _val(col: str, idx: int, default: float) -> float:
        arr = raw_hourly.get(col, [])
        if arr is not None and 0 <= idx < len(arr) and arr[idx] is not None:
            try:
                v = float(arr[idx])
                return v if not np.isnan(v) else default
            except (ValueError, TypeError):
                return default
        return default

    # Current hour t raw values
    t2m = _val("temperature_2m", target_idx, 25.0)
    dp = _val("dew_point_2m", target_idx, 20.0)
    rh = _val("relative_humidity_2m", target_idx, 60.0)
    p_sfc = _val("surface_pressure", target_idx, 1013.0)
    w_spd = _val("wind_speed_10m", target_idx, 5.0)
    w_dir = _val("wind_direction_10m", target_idx, 180.0)
    c_cov = _val("cloud_cover", target_idx, 50.0)
    precip = _val("precipitation", target_idx, 0.0)

    # Derived thermodynamic variables
    e_s = 6.112 * np.exp(17.67 * t2m / (t2m + 243.5))
    e_d = 6.112 * np.exp(17.67 * dp / (dp + 243.5))

    r_s = 621.97 * e_s / max(p_sfc - e_s, 1.0)
    r_d = 621.97 * e_d / max(p_sfc - e_d, 1.0)

    theta_e = (
        (t2m + 273.15)
        * (1000.0 / p_sfc) ** 0.286
        * np.exp(2.675e6 * r_d / (1004.0 * (t2m + 273.15)))
    )

    cape = float(np.clip((theta_e - 300.0) * 80.0, 0.0, 5000.0))
    dpd = float(np.clip(t2m - dp, 0.0, None))
    cin = float(np.clip(dpd ** 1.5 * 8.0, 0.0, 400.0))
    cape_cin_ratio = float(cape / max(cin, 1.0))
    precipitable_water = float(np.clip(r_d * 0.3, 5.0, 75.0))

    # Lags (t-1, t-2, t-3)
    p_1 = _val("precipitation", target_idx - 1, 0.0) if target_idx >= 1 else 0.0
    p_2 = _val("precipitation", target_idx - 2, 0.0) if target_idx >= 2 else 0.0
    p_3 = _val("precipitation", target_idx - 3, 0.0) if target_idx >= 3 else 0.0
    precip_last_3hr = float(p_1 + p_2 + p_3)

    # Storm 2 hours ago (evaluated at t-2)
    if target_idx >= 2:
        wc_2 = _val("weather_code", target_idx - 2, 0.0)
        t_2 = _val("temperature_2m", target_idx - 2, 25.0)
        rh_2 = _val("relative_humidity_2m", target_idx - 2, 50.0)
        dp_2 = _val("dew_point_2m", target_idx - 2, 20.0)
        storm_2hr_ago = float(compute_thunderstorm_label(wc_2, p_2, t_2, rh_2, dp_2))
    else:
        storm_2hr_ago = 0.0

    cloud_1 = _val("cloud_cover", target_idx - 1, 50.0) if target_idx >= 1 else 50.0
    cloud_trend = float(c_cov - cloud_1)

    temp_1 = _val("temperature_2m", target_idx - 1, 25.0) if target_idx >= 1 else 25.0
    temp_trend = float(t2m - temp_1)

    press_1 = _val("surface_pressure", target_idx - 1, 1013.0) if target_idx >= 1 else 1013.0
    pressure_trend = float(p_sfc - press_1)

    # Temporal (derived from local IST timestamp)
    if target_time.tzinfo is not None:
        target_ist = target_time.astimezone(timezone(timedelta(hours=5, minutes=30)))
    else:
        target_ist = target_time

    hour = float(target_ist.hour)
    month = float(target_ist.month)
    hour_sin = float(np.sin(2.0 * np.pi * hour / 24.0))
    hour_cos = float(np.cos(2.0 * np.pi * hour / 24.0))
    month_sin = float(np.sin(2.0 * np.pi * month / 12.0))
    month_cos = float(np.cos(2.0 * np.pi * month / 12.0))

    feature_dict = {
        "cape": cape,
        "cin": cin,
        "temperature_2m": float(t2m),
        "dewpoint_2m": float(dp),
        "relative_humidity": float(rh),
        "surface_pressure": float(p_sfc),
        "wind_speed_10m": float(w_spd),
        "wind_direction_10m": float(w_dir),
        "cloud_cover": float(c_cov),
        "precipitable_water": precipitable_water,
        "dew_point_depression": dpd,
        "cape_cin_ratio": cape_cin_ratio,
        "hour_sin": hour_sin,
        "hour_cos": hour_cos,
        "month_sin": month_sin,
        "month_cos": month_cos,
        "latitude": float(original_lat),
        "longitude": float(original_lon),
        "precip_1hr_ago": float(p_1),
        "precip_last_3hr": float(precip_last_3hr),
        "storm_2hr_ago": float(storm_2hr_ago),
        "cloud_trend": float(cloud_trend),
        "temp_trend": float(temp_trend),
        "pressure_trend": float(pressure_trend),
    }

    return feature_dict
