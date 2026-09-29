"""Feature engineering module to extract, calculate, and order 24 atmospheric features for ML inference.
Delegates to the canonical notebook feature extraction pipeline in training_features.py.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from app.services.training_features import (
    CLEAN_FEATURE_COLS,
    build_features_from_raw_slice,
    compute_thunderstorm_label,
)

IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


class FeatureEngineer:
    """Extracts meteorological and temporal features from Open-Meteo payloads matching training data."""

    FEATURE_COLUMNS = CLEAN_FEATURE_COLS

    @staticmethod
    def get_timezone_offset(weather_data: Dict[str, Any]) -> timezone:
        """Get timezone object from weather_data utc_offset_seconds (defaults to Asia/Kolkata +05:30)."""
        offset_sec = weather_data.get("utc_offset_seconds", 19800)
        if offset_sec is None:
            offset_sec = 19800
        return timezone(timedelta(seconds=offset_sec))

    @staticmethod
    def parse_time_array_to_ist(times: List[str], tz: timezone = IST_TIMEZONE) -> List[datetime]:
        """Parse Open-Meteo hourly string timestamps into timezone-aware IST datetimes."""
        parsed: List[datetime] = []
        for t_str in times:
            try:
                dt = datetime.fromisoformat(t_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=tz)
                else:
                    dt = dt.astimezone(tz)
                parsed.append(dt)
            except Exception:
                parsed.append(datetime.min.replace(tzinfo=tz))
        return parsed

    @classmethod
    def find_current_hour_index(
        cls,
        weather_data: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> Tuple[int, datetime]:
        """
        Choose the latest hourly row index where row_time <= timestamp (in Asia/Kolkata IST).
        Returns: (now_idx, row_ist_datetime)
        """
        hourly = weather_data.get("hourly", {})
        times = hourly.get("time", [])
        tz = cls.get_timezone_offset(weather_data)

        if timestamp is None:
            now_dt = datetime.now(timezone.utc)
        else:
            now_dt = timestamp

        now_ist = now_dt.astimezone(tz) if now_dt.tzinfo else now_dt.replace(tzinfo=timezone.utc).astimezone(tz)

        if not times:
            return 0, now_ist

        parsed_times = cls.parse_time_array_to_ist(times, tz)

        best_idx = 0
        best_dt = None

        for idx, dt in enumerate(parsed_times):
            if dt <= now_ist:
                best_idx = idx
                best_dt = dt
            else:
                break

        if best_dt is None:
            best_idx = 0
            best_dt = parsed_times[0] if parsed_times else now_ist

        return best_idx, best_dt

    def build_feature_vector(
        self,
        weather_data: Dict[str, Any],
        lat: float,
        lon: float,
        timestamp: datetime,
        target_hour_index: int = 0,
    ) -> Tuple[Dict[str, float], datetime]:
        """
        Build complete 24-feature vector using the exact training formulas and lags.
        target_hour_index is lead_hours offset (0 for lead 0, 1 for lead 1, etc.).
        Returns: (features_dict, input_time_ist_dt)
        """
        hourly = weather_data.get("hourly", {})
        times = hourly.get("time", [])
        tz = self.get_timezone_offset(weather_data)

        now_idx, base_dt = self.find_current_hour_index(weather_data, timestamp)
        target_idx = now_idx + target_hour_index
        if times and target_idx >= len(times):
            target_idx = len(times) - 1

        parsed_times = self.parse_time_array_to_ist(times, tz)
        if parsed_times and 0 <= target_idx < len(parsed_times):
            row_dt_ist = parsed_times[target_idx]
        else:
            row_dt_ist = base_dt + timedelta(hours=target_hour_index)

        features = build_features_from_raw_slice(
            raw_hourly=hourly,
            target_idx=target_idx,
            original_lat=lat,
            original_lon=lon,
            target_time=row_dt_ist,
        )
        return features, row_dt_ist

    def build_feature_vector_simple(
        self,
        weather_data: Dict[str, Any],
        lat: float,
        lon: float,
        timestamp: datetime,
        hour_index: int = 0,
    ) -> Tuple[Dict[str, float], datetime]:
        """
        Build feature vector for a specific hour index from hourly weather data.
        Returns: (features_dict, input_time_ist_dt)
        """
        hourly = weather_data.get("hourly", {})
        times = hourly.get("time", [])
        tz = self.get_timezone_offset(weather_data)
        idx = hour_index if times and 0 <= hour_index < len(times) else 0

        parsed_times = self.parse_time_array_to_ist(times, tz)
        if parsed_times and 0 <= idx < len(parsed_times):
            row_dt_ist = parsed_times[idx]
        else:
            row_dt_ist = timestamp.astimezone(tz) if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc).astimezone(tz)

        features = build_features_from_raw_slice(
            raw_hourly=hourly,
            target_idx=idx,
            original_lat=lat,
            original_lon=lon,
            target_time=row_dt_ist,
        )
        return features, row_dt_ist
