"""Data ingestion service for fetching real-time and historical atmospheric data from Open-Meteo
with TTL caching, batch requests, quota guard, and stale fallback support."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
import httpx
from app.config import settings
from app.core.cache import meteo_cache, snap_coordinates
from app.core.quota import quota_guard

logger = logging.getLogger("vajranowcast.ingestion")

# 9 canonical model variables (quota-optimized, no current= block)
OPEN_METEO_MODEL_HOURLY_VARS = (
    "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,"
    "wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code"
)

# Extended variables requested ONLY for /weather/indices
OPEN_METEO_INDICES_HOURLY_VARS = (
    "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,"
    "wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code,"
    "precipitation_probability,cape,convective_inhibition,total_column_integrated_water_vapour"
)


class OpenMeteoService:
    """Service to interface with Open-Meteo Forecast and Historical Archive APIs."""

    def __init__(self):
        self.forecast_url = settings.OPEN_METEO_URL
        self.archive_url = settings.OPEN_METEO_ARCHIVE_URL
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    async def fetch_current_weather(
        self,
        lat: float,
        lon: float,
        force_refresh: bool = False,
        include_nwp_indices: bool = False,
    ) -> Tuple[Dict[str, Any], bool, Optional[datetime], Optional[str]]:
        """
        Fetch atmospheric conditions for a snapped location.
        Quota-optimized: requests only the 9 model variables without current= block by default.
        Returns: (weather_data, is_stale, cached_at, stale_reason)
        """
        snapped_lat, snapped_lon = snap_coordinates(lat, lon)

        # 1. Check TTL cache unless forced
        if not force_refresh:
            cached = meteo_cache.get_weather(snapped_lat, snapped_lon)
            if cached is not None:
                data, is_stale, cached_at = cached
                if not is_stale:
                    return data, False, cached_at, None

        # 2. Check Quota Guard
        allowed, reason = quota_guard.can_make_request(batch_weight=1)
        if not allowed:
            logger.warning(f"Open-Meteo quota guard blocked request for ({snapped_lat}, {snapped_lon}): {reason}")
            cached = meteo_cache.get_weather(snapped_lat, snapped_lon)
            if cached is not None:
                data, _, cached_at = cached
                return data, True, cached_at, f"Quota guard active: {reason}"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "detail": "Weather data provider is busy for this server — try again shortly.",
                    "code": "upstream_rate_limited",
                },
            )

        hourly_vars = OPEN_METEO_INDICES_HOURLY_VARS if include_nwp_indices else OPEN_METEO_MODEL_HOURLY_VARS

        params = {
            "latitude": snapped_lat,
            "longitude": snapped_lon,
            "hourly": hourly_vars,
            "forecast_days": 2,
            "past_days": 1,
            "timezone": "Asia/Kolkata",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.forecast_url, params=params)
                
                # Check for 429 or 5xx upstream errors
                if response.status_code == 429 or response.status_code >= 500:
                    snippet = response.text[:300] if hasattr(response, "text") else ""
                    logger.warning(
                        f"Open-Meteo returned HTTP {response.status_code} for ({snapped_lat}, {snapped_lon}): {snippet}"
                    )
                    cached = meteo_cache.get_weather(snapped_lat, snapped_lon)
                    if cached is not None:
                        data, _, cached_at = cached
                        return data, True, cached_at, f"Upstream Open-Meteo returned {response.status_code}"
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail={
                            "detail": "Weather data provider is busy for this server — try again shortly.",
                            "code": "upstream_rate_limited",
                        },
                    )

                response.raise_for_status()
                quota_guard.record_request(batch_weight=1)
                data = response.json()

                if "hourly" in data and "total_column_integrated_water_vapour" in data["hourly"]:
                    data["hourly"]["precipitable_water"] = data["hourly"]["total_column_integrated_water_vapour"]

                # Store in cache
                meteo_cache.set_weather(snapped_lat, snapped_lon, data)
                return data, False, datetime.now(timezone.utc), None

        except HTTPException:
            raise
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error(f"Error communicating with Open-Meteo for ({snapped_lat}, {snapped_lon}): {e}")
            cached = meteo_cache.get_weather(snapped_lat, snapped_lon)
            if cached is not None:
                data, _, cached_at = cached
                return data, True, cached_at, f"Network error ({type(e).__name__}); served from fallback cache"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "detail": "Weather data provider is busy for this server — try again shortly.",
                    "code": "upstream_rate_limited",
                },
            )

    async def fetch_batch_locations(
        self,
        locations: List[Dict[str, float]],
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[datetime], Optional[str]]:
        """
        Fetch atmospheric conditions for multiple locations in a single batched HTTP request.
        """
        if not locations:
            return [], False, datetime.now(timezone.utc), None

        lats_str = ",".join(str(snap_coordinates(loc["latitude"], loc["longitude"])[0]) for loc in locations)
        lons_str = ",".join(str(snap_coordinates(loc["latitude"], loc["longitude"])[1]) for loc in locations)

        allowed, reason = quota_guard.can_make_request(batch_weight=1)
        if not allowed:
            logger.warning(f"Quota guard blocked batch request: {reason}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "detail": "Weather data provider is busy for this server — try again shortly.",
                    "code": "upstream_rate_limited",
                },
            )

        params = {
            "latitude": lats_str,
            "longitude": lons_str,
            "hourly": OPEN_METEO_MODEL_HOURLY_VARS,
            "forecast_days": 2,
            "past_days": 1,
            "timezone": "Asia/Kolkata",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.forecast_url, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    snippet = response.text[:300] if hasattr(response, "text") else ""
                    logger.warning(f"Open-Meteo batch returned HTTP {response.status_code}: {snippet}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail={
                            "detail": "Weather data provider is busy for this server — try again shortly.",
                            "code": "upstream_rate_limited",
                        },
                    )

                response.raise_for_status()
                quota_guard.record_request(batch_weight=1)
                raw_json = response.json()

                if isinstance(raw_json, list):
                    results = raw_json
                else:
                    results = [raw_json]

                now_dt = datetime.now(timezone.utc)
                for idx, item in enumerate(results):
                    if "hourly" in item and "total_column_integrated_water_vapour" in item["hourly"]:
                        item["hourly"]["precipitable_water"] = item["hourly"]["total_column_integrated_water_vapour"]
                    if idx < len(locations):
                        lat = locations[idx]["latitude"]
                        lon = locations[idx]["longitude"]
                        meteo_cache.set_weather(lat, lon, item)

                return results, False, now_dt, None
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in batch location fetch: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "detail": "Weather data provider is busy for this server — try again shortly.",
                    "code": "upstream_rate_limited",
                },
            )

    async def fetch_multiple_cities(
        self,
        cities: List[Dict[str, Any]],
        force_refresh: bool = False,
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[datetime], Optional[str]]:
        """
        Fetch weather data for multiple cities using a SINGLE batched HTTP call to Open-Meteo.
        Utilizes 15-minute TTL caching.
        """
        if not force_refresh:
            cached = meteo_cache.get_cities_weather()
            if cached is not None:
                data, is_stale, cached_at = cached
                if not is_stale:
                    return data, False, cached_at, None

        locs = [{"latitude": c["lat"], "longitude": c["lon"]} for c in cities]
        try:
            results, is_stale, cached_at, stale_reason = await self.fetch_batch_locations(locs)
            formatted = []
            for i, c in enumerate(cities):
                city_data = results[i] if i < len(results) else None
                formatted.append({
                    "city": c.get("name", "Unknown"),
                    "lat": c["lat"],
                    "lon": c["lon"],
                    "data": city_data,
                })
            meteo_cache.set_cities_weather(formatted)
            return formatted, False, datetime.now(timezone.utc), None

        except Exception as e:
            logger.warning(f"Batch fetch failed: {e}. Checking for stale cached cities.")
            cached = meteo_cache.get_cities_weather()
            if cached is not None:
                data, _, cached_at = cached
                return data, True, cached_at, f"Failed updating city batch ({str(e)}); served stale"
            raise

    async def fetch_historical_weather(self, lat: float, lon: float, date_str: str) -> dict[str, Any]:
        """
        Fetch historical atmospheric conditions for model validation and retrospective analysis.
        """
        snapped_lat, snapped_lon = snap_coordinates(lat, lon)
        params = {
            "latitude": snapped_lat,
            "longitude": snapped_lon,
            "start_date": date_str,
            "end_date": date_str,
            "hourly": OPEN_METEO_MODEL_HOURLY_VARS,
            "timezone": "Asia/Kolkata",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.archive_url, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                snippet = response.text[:300] if hasattr(response, "text") else ""
                logger.warning(f"Historical fetch returned HTTP {response.status_code}: {snippet}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "detail": "Weather data provider is busy for this server — try again shortly.",
                        "code": "upstream_rate_limited",
                    },
                )
            response.raise_for_status()
            quota_guard.record_request(batch_weight=1)
            return response.json()
