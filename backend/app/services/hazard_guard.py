"""Rule-based severe weather hazard guard protecting against out-of-distribution extremes."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.config import settings


@dataclass
class HazardResult:
    """Result of rule-based hazard guard evaluation."""
    hazard_flags: List[str] = field(default_factory=list)
    hazard_tier: Optional[str] = None  # None | "watch" | "advisory" | "warning"
    reasons: List[str] = field(default_factory=list)
    out_of_training_range: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hazard_flags": self.hazard_flags,
            "hazard_tier": self.hazard_tier,
            "reasons": self.reasons,
            "out_of_training_range": self.out_of_training_range,
        }


def _get_val(arr: Optional[List[Any]], idx: int) -> Optional[float]:
    """Helper to safely extract a float value from an array at a given index."""
    if arr is None or not (0 <= idx < len(arr)):
        return None
    val = arr[idx]
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def evaluate_hazards(
    raw_hourly: Dict[str, Any],
    target_idx: int = 0,
    model_version: Optional[str] = None,
) -> HazardResult:
    """
    Pure function evaluating severe weather hazards on hour t and t+1.
    Uses ONLY variables already fetched from Open-Meteo in standard default units (km/h, mm, hPa).

    Rules:
      - WMO weather_code 95 -> "thunderstorm_forecast" (Advisory); 96 or 99 -> "thunderstorm_hail" (Warning)
      - precipitation >= 10 mm/h -> "heavy_rain" (Advisory); >= 20 mm/h -> "very_heavy_rain" (Warning)
      - wind_speed_10m >= 50 km/h -> "strong_wind" (Watch); >= 62 km/h -> "cyclonic_gale" (Warning, IMD cyclonic-storm threshold)
      - surface_pressure fall >= 3 hPa over last 3 h AND precipitation >= 2 mm/h -> "rapid_pressure_fall" (Watch)
      - If wind_gusts_10m is present, gusts >= 90 km/h -> "damaging_gusts" (Warning)
      - out_of_training_range:
          * v1: (rain >= 2 mm/h and temperature <= 25 °C) or (wind >= 62 km/h) or (pressure < 995 hPa)
          * v2: only (wind >= 62 km/h) or (pressure < 995 hPa) -- cool rain was part of v2 training domain.
    """
    if not raw_hourly or not isinstance(raw_hourly, dict):
        return HazardResult()

    # Determine array length from available keys
    lengths = [len(v) for v in raw_hourly.values() if isinstance(v, list)]
    if not lengths:
        return HazardResult()
    max_len = max(lengths)

    if target_idx < 0 or target_idx >= max_len:
        target_idx = max(0, min(target_idx, max_len - 1))

    # Evaluate window: hour t and t+1 (if available)
    eval_indices = [target_idx]
    if target_idx + 1 < max_len:
        eval_indices.append(target_idx + 1)

    temp_arr = raw_hourly.get("temperature_2m")
    rain_arr = raw_hourly.get("precipitation")
    wind_arr = raw_hourly.get("wind_speed_10m")
    press_arr = raw_hourly.get("surface_pressure")
    code_arr = raw_hourly.get("weather_code")
    gust_arr = raw_hourly.get("wind_gusts_10m")

    # Track flags with their tier and reason
    # Tier ranking: warning (3), advisory (2), watch (1)
    detected_warnings: List[tuple[str, str]] = []  # (flag, reason)
    detected_advisories: List[tuple[str, str]] = []
    detected_watches: List[tuple[str, str]] = []

    # 1. WMO weather_code: 96, 99 (Warning); 95 (Advisory)
    codes = [_get_val(code_arr, idx) for idx in eval_indices]
    int_codes = [int(c) for c in codes if c is not None]
    if any(c in (96, 99) for c in int_codes):
        detected_warnings.append(("thunderstorm_hail", "severe thunderstorm with hail forecast"))
    elif any(c == 95 for c in int_codes):
        detected_advisories.append(("thunderstorm_forecast", "thunderstorm forecast"))

    # 2. Wind speed (10m): >= 62 km/h (Warning), >= 50 km/h (Watch)
    winds = [_get_val(wind_arr, idx) for idx in eval_indices]
    valid_winds = [w for w in winds if w is not None]
    max_wind = max(valid_winds) if valid_winds else 0.0

    if max_wind >= settings.HAZARD_WIND_WARNING:
        detected_warnings.append(("cyclonic_gale", f"forecast winds {max_wind:.0f} km/h (cyclonic gale)"))
    elif max_wind >= settings.HAZARD_WIND_WATCH:
        detected_watches.append(("strong_wind", f"forecast strong winds {max_wind:.0f} km/h"))

    # 3. Precipitation: >= 20 mm/h (Warning), >= 10 mm/h (Advisory)
    rains = [_get_val(rain_arr, idx) for idx in eval_indices]
    valid_rains = [r for r in rains if r is not None]
    max_rain = max(valid_rains) if valid_rains else 0.0

    if max_rain >= settings.HAZARD_RAIN_WARNING:
        detected_warnings.append(("very_heavy_rain", f"forecast very heavy rain {max_rain:.0f} mm/h"))
    elif max_rain >= settings.HAZARD_RAIN_ADVISORY:
        detected_advisories.append(("heavy_rain", f"forecast heavy rain {max_rain:.0f} mm/h"))

    # 4. Optional Wind Gusts (10m): >= 90 km/h (Warning)
    if gust_arr is not None:
        gusts = [_get_val(gust_arr, idx) for idx in eval_indices]
        valid_gusts = [g for g in gusts if g is not None]
        max_gust = max(valid_gusts) if valid_gusts else 0.0
        if max_gust >= settings.HAZARD_GUST_WARNING:
            detected_warnings.append(("damaging_gusts", f"forecast damaging gusts {max_gust:.0f} km/h"))

    # 5. Rapid surface pressure fall: >= 3 hPa over last 3 h AND precipitation >= 2 mm/h (Watch)
    rapid_fall_detected = False
    max_fall_val = 0.0
    for idx in eval_indices:
        p_curr = _get_val(press_arr, idx)
        if p_curr is not None:
            # Check 3 hours ago; if unavailable, fallback to index 0 if index > 0
            prior_idx = idx - 3 if idx >= 3 else 0 if idx > 0 else None
            if prior_idx is not None and prior_idx != idx:
                p_prior = _get_val(press_arr, prior_idx)
                if p_prior is not None:
                    fall = p_prior - p_curr
                    r_curr = _get_val(rain_arr, idx) or 0.0
                    if fall >= settings.HAZARD_PRESSURE_FALL_3H and (r_curr >= settings.HAZARD_PRESSURE_FALL_RAIN or max_rain >= settings.HAZARD_PRESSURE_FALL_RAIN):
                        rapid_fall_detected = True
                        if fall > max_fall_val:
                            max_fall_val = fall

    if rapid_fall_detected:
        detected_watches.append(("rapid_pressure_fall", f"rapid pressure fall ({max_fall_val:.1f} hPa/3h) with rain"))

    # 6. Out of training range check:
    # Model-version aware:
    #   - v1: rain >= 2 mm/h with temperature <= 25 °C, OR wind >= 62 km/h, OR pressure < 995 hPa
    #   - v2: temperature condition dropped (v2 was trained on cool rain). Only wind >= 62 km/h OR pressure < 995 hPa
    active_version = (model_version or getattr(settings, "MODEL_VERSION", "v1")).lower()
    check_temp = (active_version != "v2") if model_version is not None else getattr(settings, "HAZARD_OUT_OF_RANGE_CHECK_TEMP", True)

    out_of_training_range = False
    for idx in eval_indices:
        t = _get_val(temp_arr, idx)
        r = _get_val(rain_arr, idx)
        w = _get_val(wind_arr, idx)
        p = _get_val(press_arr, idx)

        # v1 only: rain >= 2 mm/h with temperature <= 25 °C was outside v1 training label
        if check_temp and r is not None and t is not None:
            if r >= settings.HAZARD_OUT_OF_RANGE_RAIN and t <= settings.HAZARD_OUT_OF_RANGE_TEMP:
                out_of_training_range = True
                break

        # Both v1 and v2: extreme cyclonic winds (>= 62 km/h) or deep pressure drops (< 995 hPa)
        if w is not None and w >= settings.HAZARD_OUT_OF_RANGE_WIND:
            out_of_training_range = True
            break
        if p is not None and p < settings.HAZARD_OUT_OF_RANGE_PRESSURE:
            out_of_training_range = True
            break

    # Compile hazard tier and list of flags / reasons in severity order
    all_flags: List[str] = []
    all_reasons: List[str] = []

    for flag, reason in detected_warnings:
        all_flags.append(flag)
        all_reasons.append(reason)
    for flag, reason in detected_advisories:
        all_flags.append(flag)
        all_reasons.append(reason)
    for flag, reason in detected_watches:
        all_flags.append(flag)
        all_reasons.append(reason)

    if detected_warnings:
        hazard_tier = "warning"
    elif detected_advisories:
        hazard_tier = "advisory"
    elif detected_watches:
        hazard_tier = "watch"
    else:
        hazard_tier = None

    return HazardResult(
        hazard_flags=all_flags,
        hazard_tier=hazard_tier,
        reasons=all_reasons,
        out_of_training_range=out_of_training_range,
    )


def resolve_display_tier(
    ts_prob: float,
    hazard_tier: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """
    Determine the more severe of ML tier and hazard_tier.
    Returns: (display_tier, tier_source) where tier_source is 'ml', 'hazard_guard', or None.
    """
    ml_tier = (
        "warning" if ts_prob >= settings.ALERT_TIER_WARNING
        else "advisory" if ts_prob >= settings.ALERT_TIER_ADVISORY
        else "watch" if ts_prob >= settings.ALERT_TIER_WATCH
        else None
    )

    tier_ranks = {None: 0, "watch": 1, "advisory": 2, "warning": 3}
    ml_rank = tier_ranks.get(ml_tier, 0)
    guard_rank = tier_ranks.get(hazard_tier, 0)

    if guard_rank > ml_rank:
        return hazard_tier, "hazard_guard"
    elif ml_rank > 0:
        return ml_tier, "ml"
    else:
        return None, None

