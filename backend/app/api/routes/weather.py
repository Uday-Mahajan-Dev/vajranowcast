"""Weather observation and atmospheric instability indices API endpoints with grid snapping and rate limiting."""

import logging
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Request, status
from app.config import settings
from app.core.limiter import limiter
from app.models.schemas import DEFAULT_DISCLAIMER, DataSourceStatus
from app.services.data_ingestion import OpenMeteoService
from app.services.feature_engineering import FeatureEngineer

logger = logging.getLogger("vajranowcast.api.weather")

router = APIRouter()


def snap_to_grid(value: float, step: float = 0.25) -> float:
    """Snap geographic coordinate to the nearest 0.25 degree grid node."""
    return round(round(value / step) * step, 4)


@router.get("/current")
@limiter.limit(settings.RATE_LIMIT_NOWCAST)
async def get_current_weather(
    request: Request,
    lat: float = Query(28.61, ge=settings.INDIA_LAT_MIN, le=settings.INDIA_LAT_MAX, description="Latitude"),
    lon: float = Query(77.21, ge=settings.INDIA_LON_MIN, le=settings.INDIA_LON_MAX, description="Longitude"),
):
    """Fetch raw current weather observations and hourly fields from Open-Meteo API with coordinate snapping."""
    try:
        snapped_lat = snap_to_grid(lat)
        snapped_lon = snap_to_grid(lon)

        data_service = OpenMeteoService()
        weather_data, is_stale, cached_at, stale_reason = await data_service.fetch_current_weather(snapped_lat, snapped_lon)
        return {
            "latitude": snapped_lat,
            "longitude": snapped_lon,
            "request_time": datetime.now(timezone.utc).isoformat(),
            "weather": weather_data,
            "stale": is_stale,
            "cached_at": cached_at,
            "stale_reason": stale_reason,
            "disclaimer": DEFAULT_DISCLAIMER,
        }
    except Exception as e:
        logger.error(f"Error fetching current weather for ({lat}, {lon}): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal weather observation service error.")


@router.get("/indices")
@limiter.limit(settings.RATE_LIMIT_NOWCAST)
async def get_atmospheric_indices(
    request: Request,
    lat: float = Query(28.61, ge=settings.INDIA_LAT_MIN, le=settings.INDIA_LAT_MAX, description="Latitude"),
    lon: float = Query(77.21, ge=settings.INDIA_LON_MIN, le=settings.INDIA_LON_MAX, description="Longitude"),
):
    """
    Fetch atmospheric observations and compute thermodynamic instability indices:
    CAPE categories, CIN, Dew Point Depression, Precipitable Water, and Convective Potential.
    """
    try:
        snapped_lat = snap_to_grid(lat)
        snapped_lon = snap_to_grid(lon)

        data_service = OpenMeteoService()
        raw_data, is_stale, cached_at, stale_reason = await data_service.fetch_current_weather(snapped_lat, snapped_lon)

        feature_eng = FeatureEngineer()
        features, row_dt_ist = feature_eng.build_feature_vector(
            weather_data=raw_data,
            lat=snapped_lat,
            lon=snapped_lon,
            timestamp=datetime.now(timezone.utc),
            target_hour_index=0,
        )
        now_idx, _ = feature_eng.find_current_hour_index(raw_data, datetime.now(timezone.utc))

        cape = features.get("cape", 0.0)
        cin = features.get("cin", 0.0)
        humidity = features.get("relative_humidity", 0.0)
        dpd = features.get("dew_point_depression", 0.0)
        pw = features.get("precipitable_water", 0.0)
        cape_cin = features.get("cape_cin_ratio", 0.0)

        # Extract NWP model values if available for the current hour
        hourly = raw_data.get("hourly", {})
        cape_arr = hourly.get("cape", [])
        cin_arr = hourly.get("convective_inhibition", [])
        nwp_cape = float(cape_arr[now_idx]) if cape_arr and 0 <= now_idx < len(cape_arr) and cape_arr[now_idx] is not None else None
        nwp_cin = float(cin_arr[now_idx]) if cin_arr and 0 <= now_idx < len(cin_arr) and cin_arr[now_idx] is not None else None

        return {
            "latitude": snapped_lat,
            "longitude": snapped_lon,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_time_ist": row_dt_ist.isoformat(),
            "derived_indices": {
                "description": "Empirical thermodynamic approximations derived from surface T, Td, and Psfc (Bolton 1980); used as model inputs",
                "cape_index_derived": round(cape, 1),
                "cin_index_derived": round(cin, 1),
                "pw_index_derived": round(pw, 1),
                "cape_cin_ratio": round(cape_cin, 2),
                "dew_point_depression_c": round(dpd, 1),
                "relative_humidity_pct": round(humidity, 1),
                "surface_pressure_hpa": round(features.get("surface_pressure", 1013.0), 1),
                "note": "Severity bands are calibrated strictly against model P(TS) and optimal threshold (0.1860); derived CAPE is not used for severity classification.",
            },
            "nwp_values": {
                "description": "Raw numerical weather prediction values from Open-Meteo NWP sounding (not a model input)",
                "nwp_cape_j_kg (not a model input)": round(nwp_cape, 1) if nwp_cape is not None else None,
                "nwp_cin_j_kg (not a model input)": round(nwp_cin, 1) if nwp_cin is not None else None,
                "nwp_cape_j_kg": round(nwp_cape, 1) if nwp_cape is not None else None,
                "nwp_cin_j_kg": round(nwp_cin, 1) if nwp_cin is not None else None,
            },
            "disclaimer": DEFAULT_DISCLAIMER,
        }
    except Exception as e:
        logger.error(f"Error computing atmospheric indices for ({lat}, {lon}): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal atmospheric index calculation error.")


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

    # 2. GFS 0.25 (Planned)
    sources.append(
        DataSourceStatus(
            source_name="NOAA GFS 0.25° Global Forecast",
            status="planned",
            last_updated=now_iso,
            variables=["HGT_clb", "CAPE_sfc", "CIN_sfc", "PWAT_ea", "UGRD_10m", "VGRD_10m"],
        )
    )

    # 3. MOSDAC Satellite / Radar (Planned)
    sources.append(
        DataSourceStatus(
            source_name="ISRO MOSDAC INSAT-3D/3DR",
            status="planned",
            last_updated=now_iso,
            variables=["Cloud Top Brightness Temp (TIR1)", "Water Vapor (WV)", "Rainfall Rate (HEM)"],
        )
    )

    # 4. Blitzortung Lightning Network (Planned)
    sources.append(
        DataSourceStatus(
            source_name="Blitzortung TOA Lightning Network",
            status="planned",
            last_updated=now_iso,
            variables=["stroke_timestamp", "stroke_lat", "stroke_lon", "current_ka"],
        )
    )

    return sources
