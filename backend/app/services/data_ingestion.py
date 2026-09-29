"""Data ingestion service for fetching real-time and historical atmospheric data from Open-Meteo."""

import asyncio
import logging
from typing import Any
import httpx
from app.config import settings

logger = logging.getLogger("vajranowcast.ingestion")


class OpenMeteoService:
    """Service to interface with Open-Meteo Forecast and Historical Archive APIs."""

    def __init__(self):
        self.forecast_url = settings.OPEN_METEO_URL
        self.archive_url = settings.OPEN_METEO_ARCHIVE_URL
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    async def fetch_current_weather(self, lat: float, lon: float) -> dict[str, Any]:
        """
        Fetch real-time atmospheric conditions and 1-day past/forecast hourly fields.
        past_days=1 is critical for calculating persistence and trend features.
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,"
                "wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code"
            ),
            "hourly": (
                "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,"
                "wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,"
                "precipitation_probability,cape,convective_inhibition,"
                "total_column_integrated_water_vapour,weather_code"
            ),
            "forecast_days": 1,
            "past_days": 1,
            "timezone": "Asia/Kolkata",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.forecast_url, params=params)
            response.raise_for_status()
            data = response.json()
            # Standardize total_column_integrated_water_vapour -> precipitable_water in hourly
            if "hourly" in data and "total_column_integrated_water_vapour" in data["hourly"]:
                data["hourly"]["precipitable_water"] = data["hourly"]["total_column_integrated_water_vapour"]
            return data

    async def fetch_historical_weather(self, lat: float, lon: float, date_str: str) -> dict[str, Any]:
        """
        Fetch historical atmospheric conditions for model validation and retrospective analysis.
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": date_str,
            "end_date": date_str,
            "hourly": (
                "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,"
                "wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code"
            ),
            "timezone": "Asia/Kolkata",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.archive_url, params=params)
            response.raise_for_status()
            return response.json()

    async def fetch_multiple_cities(self, cities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Fetch weather data concurrently for multiple cities using asyncio.gather.
        """
        async def _fetch_single_city(city_info: dict[str, Any]) -> dict[str, Any]:
            name = city_info.get("name", "Unknown")
            lat = city_info["lat"]
            lon = city_info["lon"]
            try:
                data = await self.fetch_current_weather(lat, lon)
                return {"city": name, "lat": lat, "lon": lon, "data": data}
            except Exception as e:
                logger.error(f"Failed fetching weather for {name} ({lat}, {lon}): {e}")
                return {"city": name, "lat": lat, "lon": lon, "data": None, "error": str(e)}

        tasks = [_fetch_single_city(city) for city in cities]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final_results = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                final_results.append({
                    "city": cities[i].get("name", "Unknown"),
                    "lat": cities[i]["lat"],
                    "lon": cities[i]["lon"],
                    "data": None,
                    "error": str(res),
                })
            else:
                final_results.append(res)

        return final_results
