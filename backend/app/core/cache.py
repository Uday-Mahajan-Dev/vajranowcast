"""In-memory TTL cache and 3-hour max stale fallback store for meteorological responses and predictions."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from cachetools import TTLCache

logger = logging.getLogger("vajranowcast.cache")

MAX_STALE_AGE_SECONDS = 10800  # 3 hours maximum for stale data fallback


def snap_to_grid(value: float, step: float = 0.25) -> float:
    """
    Snap geographic coordinate to the nearest 0.25 degree grid node (~27 km).
    Matches Phase 1 input normalization.
    """
    return round(round(float(value) / step) * step, 4)


def snap_coordinates(lat: float, lon: float, step: float = 0.25) -> Tuple[float, float]:
    """Snap pair of coordinates to 0.25 degree grid node."""
    return snap_to_grid(lat, step), snap_to_grid(lon, step)


class MeteorologicalCache:
    """
    Two-tier caching layer:
    1. Fresh TTL Cache (15 minutes for spot weather, 60 minutes for city batch)
    2. Stale Fallback Cache (up to 3 hours maximum)
    """

    def __init__(
        self,
        weather_ttl: int = 900,         # 15 minutes
        cities_ttl: int = 3600,         # 60 minutes (reduced quota consumption)
        maxsize: int = 2000,
    ):
        self.weather_ttl = weather_ttl
        self.cities_ttl = cities_ttl

        # Tier 1: Fresh TTL caches
        self._fresh_weather: TTLCache = TTLCache(maxsize=maxsize, ttl=weather_ttl)
        self._fresh_cities_weather: TTLCache = TTLCache(maxsize=10, ttl=cities_ttl)
        self._fresh_cities_nowcast: TTLCache = TTLCache(maxsize=10, ttl=cities_ttl)
        self._fresh_grid: TTLCache = TTLCache(maxsize=5, ttl=600)  # 10 min for grid

        # Tier 2: Stale Fallback store (capped at 3 hours / 10,800s)
        self._stale_weather: TTLCache = TTLCache(maxsize=maxsize, ttl=MAX_STALE_AGE_SECONDS)
        self._stale_cities_weather: TTLCache = TTLCache(maxsize=10, ttl=MAX_STALE_AGE_SECONDS)
        self._stale_cities_nowcast: TTLCache = TTLCache(maxsize=10, ttl=MAX_STALE_AGE_SECONDS)
        self._stale_grid: TTLCache = TTLCache(maxsize=5, ttl=MAX_STALE_AGE_SECONDS)

    def get_weather(self, lat: float, lon: float) -> Optional[Tuple[dict[str, Any], bool, datetime]]:
        """
        Look up cached weather for snapped 0.25 degree coordinates.
        Returns (data, is_stale, cached_at) if valid and under 3h old, else None.
        """
        snapped_lat = snap_to_grid(lat, 0.25)
        snapped_lon = snap_to_grid(lon, 0.25)
        key = f"weather:{snapped_lat}:{snapped_lon}"

        # 1. Fresh cache hit
        if key in self._fresh_weather:
            entry = self._fresh_weather[key]
            return entry["data"], False, entry["cached_at"]

        # 2. Stale cache fallback (valid up to 3 hours)
        if key in self._stale_weather:
            entry = self._stale_weather[key]
            age = (datetime.now(timezone.utc) - entry["cached_at"]).total_seconds()
            if age <= MAX_STALE_AGE_SECONDS:
                return entry["data"], True, entry["cached_at"]
            else:
                del self._stale_weather[key]

        return None

    def set_weather(self, lat: float, lon: float, data: dict[str, Any]) -> None:
        """Cache fresh weather response in fresh TTL and stale fallback tiers."""
        snapped_lat = snap_to_grid(lat, 0.25)
        snapped_lon = snap_to_grid(lon, 0.25)
        key = f"weather:{snapped_lat}:{snapped_lon}"
        now_dt = datetime.now(timezone.utc)
        entry = {
            "data": data,
            "cached_at": now_dt,
            "stored_timestamp": time.time(),
        }
        self._fresh_weather[key] = entry
        self._stale_weather[key] = entry

    def get_cities_weather(self) -> Optional[Tuple[list[dict[str, Any]], bool, datetime]]:
        """Look up cached batch weather response for metropolitan cities (60 min TTL)."""
        key = "cities_weather_batch"
        if key in self._fresh_cities_weather:
            entry = self._fresh_cities_weather[key]
            return entry["data"], False, entry["cached_at"]

        if key in self._stale_cities_weather:
            entry = self._stale_cities_weather[key]
            age = (datetime.now(timezone.utc) - entry["cached_at"]).total_seconds()
            if age <= MAX_STALE_AGE_SECONDS:
                return entry["data"], True, entry["cached_at"]

        return None

    def set_cities_weather(self, data: list[dict[str, Any]]) -> None:
        """Cache batched cities weather response."""
        key = "cities_weather_batch"
        now_dt = datetime.now(timezone.utc)
        entry = {
            "data": data,
            "cached_at": now_dt,
            "stored_timestamp": time.time(),
        }
        self._fresh_cities_weather[key] = entry
        self._stale_cities_weather[key] = entry

    def get_cities_nowcast(self) -> Optional[Tuple[dict[str, Any], bool, datetime]]:
        """Look up cached nowcast predictions for metropolitan cities (60 min TTL)."""
        key = "cities_nowcast_batch"
        if key in self._fresh_cities_nowcast:
            entry = self._fresh_cities_nowcast[key]
            return entry["data"], False, entry["cached_at"]

        if key in self._stale_cities_nowcast:
            entry = self._stale_cities_nowcast[key]
            age = (datetime.now(timezone.utc) - entry["cached_at"]).total_seconds()
            if age <= MAX_STALE_AGE_SECONDS:
                return entry["data"], True, entry["cached_at"]

        return None

    def set_cities_nowcast(self, data: dict[str, Any]) -> None:
        """Cache batched nowcast predictions for cities."""
        key = "cities_nowcast_batch"
        now_dt = datetime.now(timezone.utc)
        entry = {
            "data": data,
            "cached_at": now_dt,
            "stored_timestamp": time.time(),
        }
        self._fresh_cities_nowcast[key] = entry
        self._stale_cities_nowcast[key] = entry

    def get_grid(self) -> Optional[Tuple[dict[str, Any], bool, datetime]]:
        """Look up in-memory cached precomputed grid (10 min fresh, 3h stale fallback)."""
        key = "grid_latest"
        if key in self._fresh_grid:
            entry = self._fresh_grid[key]
            return entry["data"], False, entry["cached_at"]

        if key in self._stale_grid:
            entry = self._stale_grid[key]
            age = (datetime.now(timezone.utc) - entry["cached_at"]).total_seconds()
            if age <= MAX_STALE_AGE_SECONDS:
                return entry["data"], True, entry["cached_at"]

        return None

    def set_grid(self, data: dict[str, Any]) -> None:
        """Cache precomputed grid in memory."""
        key = "grid_latest"
        now_dt = datetime.now(timezone.utc)
        entry = {
            "data": data,
            "cached_at": now_dt,
            "stored_timestamp": time.time(),
        }
        self._fresh_grid[key] = entry
        self._stale_grid[key] = entry

    def clear(self) -> None:
        """Clear all caches."""
        self._fresh_weather.clear()
        self._fresh_cities_weather.clear()
        self._fresh_cities_nowcast.clear()
        self._fresh_grid.clear()
        self._stale_weather.clear()
        self._stale_cities_weather.clear()
        self._stale_cities_nowcast.clear()
        self._stale_grid.clear()


# Global singleton instance
meteo_cache = MeteorologicalCache(weather_ttl=900, cities_ttl=3600)
