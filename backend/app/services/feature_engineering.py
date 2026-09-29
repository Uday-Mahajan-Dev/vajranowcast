"""Feature engineering module to extract, calculate, and order 24 atmospheric features for ML inference."""

from datetime import datetime
from typing import Any
import numpy as np


class FeatureEngineer:
    """Extracts meteorological and temporal features from Open-Meteo payloads."""

    FEATURE_COLUMNS = [
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

    CONVECTIVE_WEATHER_CODES = {80, 81, 82, 85, 91, 92, 93, 95, 96, 99}

    @staticmethod
    def compute_dew_point_depression(temp: float, dewpoint: float) -> float:
        """Compute dew point depression (T - Td) bounded below by 0."""
        return float(max(temp - dewpoint, 0.0))

    @staticmethod
    def compute_cape_cin_ratio(cape: float, cin: float) -> float:
        """Compute CAPE / |CIN| ratio avoiding division by zero."""
        return float(cape / max(abs(cin), 1.0))

    @staticmethod
    def temporal_features(timestamp: datetime) -> dict[str, float]:
        """Compute cyclic trigonometric features for hour of day and month of year."""
        hour = float(timestamp.hour) + float(timestamp.minute) / 60.0
        month = float(timestamp.month)

        return {
            "hour_sin": float(np.sin(2.0 * np.pi * hour / 24.0)),
            "hour_cos": float(np.cos(2.0 * np.pi * hour / 24.0)),
            "month_sin": float(np.sin(2.0 * np.pi * month / 12.0)),
            "month_cos": float(np.cos(2.0 * np.pi * month / 12.0)),
        }

    @staticmethod
    def geographic_features(lat: float, lon: float) -> dict[str, float]:
        """Return geographic coordinates formatted for model features."""
        return {
            "latitude": float(lat),
            "longitude": float(lon),
        }

    @staticmethod
    def _safe_get(arr: list[Any] | None, idx: int, default: Any = 0.0) -> Any:
        """Safely retrieve element by index with bounds checking and None fallback."""
        if arr is None or not isinstance(arr, list):
            return default
        if 0 <= idx < len(arr):
            val = arr[idx]
            return val if val is not None else default
        return default

    @staticmethod
    def _find_closest_time_index(times: list[str], target_time: datetime) -> int:
        """Find the index of the hourly time list closest to the target datetime."""
        if not times:
            return 0

        target_str = target_time.strftime("%Y-%m-%dT%H:00")
        if target_str in times:
            return times.index(target_str)

        best_idx = 0
        min_diff = float("inf")
        target_ts = target_time.timestamp()

        for idx, t_str in enumerate(times):
            try:
                dt = datetime.fromisoformat(t_str)
                diff = abs(dt.timestamp() - target_ts)
                if diff < min_diff:
                    min_diff = diff
                    best_idx = idx
            except Exception:
                continue

        return best_idx

    def build_feature_vector(
        self,
        weather_data: dict[str, Any],
        lat: float,
        lon: float,
        timestamp: datetime,
        target_hour_index: int = 1,
    ) -> dict[str, float]:
        """
        Build complete 24-feature vector including persistence and trend indicators.
        target_hour_index represents lead time offset from current hour (default 1 for t+1).
        """
        hourly = weather_data.get("hourly", {})
        times = hourly.get("time", [])

        if not times:
            return self.build_feature_vector_simple(weather_data, lat, lon, timestamp, hour_index=0)

        now_idx = self._find_closest_time_index(times, timestamp)

        pw_arr = hourly.get("precipitable_water") or hourly.get("total_column_integrated_water_vapour")

        # Extract current hour raw atmospheric features
        cape = float(self._safe_get(hourly.get("cape"), now_idx, 0.0))
        cin = float(abs(self._safe_get(hourly.get("convective_inhibition"), now_idx, 0.0)))
        temperature_2m = float(self._safe_get(hourly.get("temperature_2m"), now_idx, 25.0))
        dewpoint_2m = float(self._safe_get(hourly.get("dew_point_2m"), now_idx, 20.0))
        relative_humidity = float(self._safe_get(hourly.get("relative_humidity_2m"), now_idx, 60.0))
        surface_pressure = float(self._safe_get(hourly.get("surface_pressure"), now_idx, 1013.0))
        wind_speed_10m = float(self._safe_get(hourly.get("wind_speed_10m"), now_idx, 5.0))
        wind_direction_10m = float(self._safe_get(hourly.get("wind_direction_10m"), now_idx, 180.0))
        cloud_cover = float(self._safe_get(hourly.get("cloud_cover"), now_idx, 50.0))
        precipitable_water = float(self._safe_get(pw_arr, now_idx, 30.0))

        # Derived thermodynamic stability features
        dew_point_depression = self.compute_dew_point_depression(temperature_2m, dewpoint_2m)
        cape_cin_ratio = self.compute_cape_cin_ratio(cape, cin)

        # Persistence features from past 1-3 hours
        precip_1hr_ago = float(self._safe_get(hourly.get("precipitation"), now_idx - 1, 0.0))
        precip_2hr_ago = float(self._safe_get(hourly.get("precipitation"), now_idx - 2, 0.0))
        precip_3hr_ago = float(self._safe_get(hourly.get("precipitation"), now_idx - 3, 0.0))
        precip_last_3hr = float(precip_1hr_ago + precip_2hr_ago + precip_3hr_ago)

        weather_code_2hr_ago = int(self._safe_get(hourly.get("weather_code"), now_idx - 2, 0))
        storm_2hr_ago = 1.0 if weather_code_2hr_ago in self.CONVECTIVE_WEATHER_CODES else 0.0

        past_cloud = float(self._safe_get(hourly.get("cloud_cover"), now_idx - 1, cloud_cover))
        cloud_trend = float(cloud_cover - past_cloud)

        past_temp = float(self._safe_get(hourly.get("temperature_2m"), now_idx - 1, temperature_2m))
        temp_trend = float(temperature_2m - past_temp)

        past_pressure = float(self._safe_get(hourly.get("surface_pressure"), now_idx - 1, surface_pressure))
        pressure_trend = float(surface_pressure - past_pressure)

        # Temporal and geographic features
        temporal = self.temporal_features(timestamp)
        geo = self.geographic_features(lat, lon)

        # Order must exactly match self.FEATURE_COLUMNS
        feature_dict = {
            "cape": cape,
            "cin": cin,
            "temperature_2m": temperature_2m,
            "dewpoint_2m": dewpoint_2m,
            "relative_humidity": relative_humidity,
            "surface_pressure": surface_pressure,
            "wind_speed_10m": wind_speed_10m,
            "wind_direction_10m": wind_direction_10m,
            "cloud_cover": cloud_cover,
            "precipitable_water": precipitable_water,
            "dew_point_depression": dew_point_depression,
            "cape_cin_ratio": cape_cin_ratio,
            "hour_sin": temporal["hour_sin"],
            "hour_cos": temporal["hour_cos"],
            "month_sin": temporal["month_sin"],
            "month_cos": temporal["month_cos"],
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
            "precip_1hr_ago": precip_1hr_ago,
            "precip_last_3hr": precip_last_3hr,
            "storm_2hr_ago": storm_2hr_ago,
            "cloud_trend": cloud_trend,
            "temp_trend": temp_trend,
            "pressure_trend": pressure_trend,
        }

        return feature_dict

    def build_feature_vector_simple(
        self,
        weather_data: dict[str, Any],
        lat: float,
        lon: float,
        timestamp: datetime,
        hour_index: int = 0,
    ) -> dict[str, float]:
        """
        Simplified feature extractor for cases where past-hour data is unavailable or for historical verification.
        Persistence and trend features are defaulted to 0.
        """
        hourly = weather_data.get("hourly", {})
        times = hourly.get("time", [])
        idx = hour_index if times and 0 <= hour_index < len(times) else 0

        current = weather_data.get("current", {})
        pw_arr = hourly.get("precipitable_water") or hourly.get("total_column_integrated_water_vapour")

        cape = float(self._safe_get(hourly.get("cape"), idx, 0.0))
        cin = float(abs(self._safe_get(hourly.get("convective_inhibition"), idx, 0.0)))
        temperature_2m = float(self._safe_get(hourly.get("temperature_2m"), idx, current.get("temperature_2m", 25.0)))
        dewpoint_2m = float(self._safe_get(hourly.get("dew_point_2m"), idx, current.get("dew_point_2m", 20.0)))
        relative_humidity = float(self._safe_get(hourly.get("relative_humidity_2m"), idx, current.get("relative_humidity_2m", 60.0)))
        surface_pressure = float(self._safe_get(hourly.get("surface_pressure"), idx, current.get("surface_pressure", 1013.0)))
        wind_speed_10m = float(self._safe_get(hourly.get("wind_speed_10m"), idx, current.get("wind_speed_10m", 5.0)))
        wind_direction_10m = float(self._safe_get(hourly.get("wind_direction_10m"), idx, current.get("wind_direction_10m", 180.0)))
        cloud_cover = float(self._safe_get(hourly.get("cloud_cover"), idx, current.get("cloud_cover", 50.0)))
        precipitable_water = float(self._safe_get(pw_arr, idx, 30.0))

        dew_point_depression = self.compute_dew_point_depression(temperature_2m, dewpoint_2m)
        cape_cin_ratio = self.compute_cape_cin_ratio(cape, cin)

        temporal = self.temporal_features(timestamp)
        geo = self.geographic_features(lat, lon)

        feature_dict = {
            "cape": cape,
            "cin": cin,
            "temperature_2m": temperature_2m,
            "dewpoint_2m": dewpoint_2m,
            "relative_humidity": relative_humidity,
            "surface_pressure": surface_pressure,
            "wind_speed_10m": wind_speed_10m,
            "wind_direction_10m": wind_direction_10m,
            "cloud_cover": cloud_cover,
            "precipitable_water": precipitable_water,
            "dew_point_depression": dew_point_depression,
            "cape_cin_ratio": cape_cin_ratio,
            "hour_sin": temporal["hour_sin"],
            "hour_cos": temporal["hour_cos"],
            "month_sin": temporal["month_sin"],
            "month_cos": temporal["month_cos"],
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
            "precip_1hr_ago": 0.0,
            "precip_last_3hr": 0.0,
            "storm_2hr_ago": 0.0,
            "cloud_trend": 0.0,
            "temp_trend": 0.0,
            "pressure_trend": 0.0,
        }

        return feature_dict
