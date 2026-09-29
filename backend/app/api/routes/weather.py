"""Weather observation and atmospheric instability indices API endpoints."""

import logging
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from app.config import settings
from app.models.schemas import DataSourceStatus
from app.services.data_ingestion import OpenMeteoService
from app.services.feature_engineering import FeatureEngineer

logger = logging.getLogger("vajranowcast.api.weather")

router = APIRouter()


@router.get("/current")
async def get_current_weather(
    lat: float = Query(28.61, ge=settings.INDIA_LAT_MIN, le=settings.INDIA_LAT_MAX, description="Latitude"),
    lon: float = Query(77.21, ge=settings.INDIA_LON_MIN, le=settings.INDIA_LON_MAX, description="Longitude"),
):
    """Fetch raw current weather observations and hourly fields from Open-Meteo API."""
    try:
        data_service = OpenMeteoService()
        data = await data_service.fetch_current_weather(lat, lon)
        return {
            "latitude": lat,
            "longitude": lon,
            "request_time": datetime.now(timezone.utc).isoformat(),
            "weather": data,
        }
    except Exception as e:
        logger.error(f"Error fetching current weather for ({lat}, {lon}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indices")
async def get_atmospheric_indices(
    lat: float = Query(28.61, ge=settings.INDIA_LAT_MIN, le=settings.INDIA_LAT_MAX, description="Latitude"),
    lon: float = Query(77.21, ge=settings.INDIA_LON_MIN, le=settings.INDIA_LON_MAX, description="Longitude"),
):
    """
    Fetch atmospheric observations and compute thermodynamic instability indices:
    CAPE categories, CIN, Dew Point Depression, Precipitable Water, and Convective Potential.
    """
    try:
        data_service = OpenMeteoService()
        raw_data = await data_service.fetch_current_weather(lat, lon)

        feature_eng = FeatureEngineer()
        features = feature_eng.build_feature_vector(
            weather_data=raw_data,
            lat=lat,
            lon=lon,
            timestamp=datetime.now(timezone.utc),
            target_hour_index=1,
        )

        cape = features.get("cape", 0.0)
        cin = features.get("cin", 0.0)
        humidity = features.get("relative_humidity", 0.0)
        dpd = features.get("dew_point_depression", 0.0)
        pw = features.get("precipitable_water", 0.0)
        cape_cin = features.get("cape_cin_ratio", 0.0)

        # Categorize CAPE
        if cape > 3000:
            cape_category = "Extreme"
        elif cape > 2000:
            cape_category = "Strong"
        elif cape > 1000:
            cape_category = "Moderate"
        elif cape > 500:
            cape_category = "Weak"
        else:
            cape_category = "None"

        # Convective Potential composite assessment
        if cape > 2000 and humidity > 70 and cin < 50:
            convective_potential = "High / Violent Convection Likely"
        elif cape > 1000 and humidity > 55:
            convective_potential = "Moderate / Thunderstorm Possible"
        elif cape > 500:
            convective_potential = "Low / Isolated Convection"
        else:
            convective_potential = "Stable / Nil Severe Activity"

        return {
            "latitude": lat,
            "longitude": lon,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "indices": {
                "cape_j_kg": round(cape, 1),
                "cape_category": cape_category,
                "cin_j_kg": round(cin, 1),
                "cape_cin_ratio": round(cape_cin, 2),
                "dew_point_depression_c": round(dpd, 1),
                "precipitable_water_mm": round(pw, 1),
                "relative_humidity_pct": round(humidity, 1),
                "surface_pressure_hpa": round(features.get("surface_pressure", 1013.0), 1),
                "convective_potential": convective_potential,
            },
        }
    except Exception as e:
        logger.error(f"Error computing atmospheric indices for ({lat}, {lon}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources/status", response_model=list[DataSourceStatus])
async def get_data_sources_status():
    """
    Check operational status and variable coverage of configured meteorological data feeds.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    sources = []

    # 1. Open-Meteo live status test
    try:
        service = OpenMeteoService()
        # Test probe Delhi
        await service.fetch_current_weather(28.61, 77.21)
        open_meteo_status = "active"
    except Exception as e:
        logger.warning(f"Open-Meteo health probe warning: {e}")
        open_meteo_status = "degraded"

    sources.append(
        DataSourceStatus(
            source_name="Open-Meteo High-Resolution NWP",
            status=open_meteo_status,
            last_updated=now_iso,
            variables=[
                "temperature_2m",
                "dew_point_2m",
                "relative_humidity_2m",
                "surface_pressure",
                "wind_speed_10m",
                "wind_direction_10m",
                "cloud_cover",
                "precipitation",
                "cape",
                "convective_inhibition",
                "precipitable_water",
            ],
        )
    )

    # 2. GFS 0.25 (Configured)
    sources.append(
        DataSourceStatus(
            source_name="NOAA GFS 0.25° Global Forecast",
            status="configured",
            last_updated=now_iso,
            variables=["HGT_clb", "CAPE_sfc", "CIN_sfc", "PWAT_ea", "UGRD_10m", "VGRD_10m"],
        )
    )

    # 3. MOSDAC Satellite / Radar (Configured)
    sources.append(
        DataSourceStatus(
            source_name="ISRO MOSDAC INSAT-3D/3DR",
            status="configured",
            last_updated=now_iso,
            variables=["Cloud Top Brightness Temp (TIR1)", "Water Vapor (WV)", "Rainfall Rate (HEM)"],
        )
    )

    # 4. Blitzortung Lightning Network (Configured)
    sources.append(
        DataSourceStatus(
            source_name="Blitzortung TOA Lightning Network",
            status="configured",
            last_updated=now_iso,
            variables=["stroke_timestamp", "stroke_lat", "stroke_lon", "current_ka"],
        )
    )

    return sources
