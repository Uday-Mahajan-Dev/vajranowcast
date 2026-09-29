"""Prediction and nowcasting API routes with grid snapping, strict input bounds, and rate limiting."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Set
from fastapi import APIRouter, HTTPException, Query, Request, status
from app.config import settings
from app.core.limiter import limiter
from app.models.schemas import (
    DEFAULT_DISCLAIMER,
    HistoricalResponse,
    NowcastResponse,
    SeverityLevel,
    ThunderstormPrediction,
)
from app.services.data_ingestion import OpenMeteoService
from app.services.feature_engineering import FeatureEngineer
from app.services.ml_inference import NowcastingService
from app.ml.models.thunderstorm_model import (
    LightningPredictor,
    SeverityClassifier,
    ThunderstormClassifier,
)

logger = logging.getLogger("vajranowcast.api.predictions")

router = APIRouter()

INDIAN_CITIES = [
    {"name": "Delhi", "lat": 28.61, "lon": 77.21},
    {"name": "Mumbai", "lat": 19.08, "lon": 72.88},
    {"name": "Kolkata", "lat": 22.57, "lon": 88.36},
    {"name": "Chennai", "lat": 13.08, "lon": 80.27},
    {"name": "Bengaluru", "lat": 12.97, "lon": 77.59},
    {"name": "Hyderabad", "lat": 17.39, "lon": 78.49},
    {"name": "Jaipur", "lat": 26.91, "lon": 75.79},
    {"name": "Lucknow", "lat": 26.85, "lon": 80.95},
    {"name": "Guwahati", "lat": 26.14, "lon": 91.74},
    {"name": "Pune", "lat": 18.52, "lon": 73.86},
]

ALLOWED_LEAD_HOURS: Set[float] = {0.0, 1.0, 2.0, 3.0, 6.0}
CONVECTIVE_CODES = {80, 81, 82, 85, 91, 92, 93, 95, 96, 99}


def snap_to_grid(value: float, step: float = 0.25) -> float:
    """Snap geographic coordinate to the nearest 0.25 degree grid node."""
    return round(round(value / step) * step, 4)


@router.get("/nowcast", response_model=NowcastResponse)
@limiter.limit(settings.RATE_LIMIT_NOWCAST)
async def get_nowcast(
    request: Request,
    lat: float = Query(..., ge=settings.INDIA_LAT_MIN, le=settings.INDIA_LAT_MAX, description="Latitude (India: 6.0 to 38.0)"),
    lon: float = Query(..., ge=settings.INDIA_LON_MIN, le=settings.INDIA_LON_MAX, description="Longitude (India: 68.0 to 98.0)"),
    lead_hours: str = Query("0,1,2,3,6", description="Comma-separated lead times in hours (allowed: 0,1,2,3,6)"),
):
    """
    Get 1-hour ahead nowcast predictions across validated lead times for any location in India.
    Automatically snaps coordinates to 0.25° grid and validates lead time parameters.
    """
    try:
        # Snap coordinates to 0.25° grid
        snapped_lat = snap_to_grid(lat)
        snapped_lon = snap_to_grid(lon)

        # Parse and validate lead_hours strictly
        try:
            raw_hours = [float(h.strip()) for h in lead_hours.split(",") if h.strip()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid lead_hours format. Must be comma-separated numbers.",
            )

        if not raw_hours:
            raw_hours = [0.0, 1.0, 2.0, 3.0, 6.0]

        if len(raw_hours) > 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At most 5 lead_hours values are allowed per request.",
            )

        invalid_leads = [h for h in raw_hours if h not in ALLOWED_LEAD_HOURS]
        if invalid_leads:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid lead_hours {invalid_leads}. Allowed values are: {sorted(list(ALLOWED_LEAD_HOURS))}.",
            )

        nowcaster = NowcastingService()
        predictions = await nowcaster.predict_for_location(snapped_lat, snapped_lon, raw_hours)

        now = datetime.now(timezone.utc)
        metadata = {
            "model_version": f"{settings.APP_VERSION}-calibrated-hgbc",
            "model_type": "HistGradientBoostingClassifier + CalibratedClassifierCV",
            "data_sources": ["Open-Meteo Forecast API"],
            "optimal_threshold": settings.OPTIMAL_THRESHOLD,
            "decision_rule": f"P(TS) >= {settings.OPTIMAL_THRESHOLD} signifies high storm threat",
            "features_count": 24,
            "target_lead_time": "t+1 hour",
            "snapped_coordinates": {"latitude": snapped_lat, "longitude": snapped_lon},
        }

        return NowcastResponse(
            request_time=now,
            predictions=predictions,
            metadata=metadata,
            disclaimer=DEFAULT_DISCLAIMER,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating nowcast for ({lat}, {lon}): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal nowcasting engine error.")


@router.get("/nowcast/cities")
@limiter.limit(settings.RATE_LIMIT_CITIES)
async def get_cities_nowcast(request: Request):
    """
    Get parallel nowcasts for 10 major Indian metropolitan and regional hubs.
    """
    try:
        nowcaster = NowcastingService()
        results = await nowcaster.predict_for_cities(INDIAN_CITIES)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cities_count": len(INDIAN_CITIES),
            "cities": results,
            "disclaimer": DEFAULT_DISCLAIMER,
        }
    except Exception as e:
        logger.error(f"Error fetching city nowcasts: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal city nowcast processing error.")


@router.get("/historical", response_model=HistoricalResponse)
@limiter.limit(settings.RATE_LIMIT_NOWCAST)
async def get_historical_verification(
    request: Request,
    lat: float = Query(..., ge=settings.INDIA_LAT_MIN, le=settings.INDIA_LAT_MAX, description="Latitude"),
    lon: float = Query(..., ge=settings.INDIA_LON_MIN, le=settings.INDIA_LON_MAX, description="Longitude"),
    date: str = Query(..., description="Target date in YYYY-MM-DD format (2015-01-01 to today - 5 days)"),
    hour: int = Query(..., ge=0, le=23, description="Target UTC/local hour (0-23)"),
):
    """
    Run historical retrospective inference and verify against actual recorded weather code.
    Enforces date range bounds (2015-01-01 to 5 days prior to current date).
    """
    try:
        # Validate date format and bounds
        try:
            parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Expected YYYY-MM-DD.",
            )

        min_date = datetime(2015, 1, 1).date()
        max_date = datetime.now(timezone.utc).date() - timedelta(days=5)

        if parsed_date < min_date or parsed_date > max_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Date '{date}' out of allowed historical range ({min_date.isoformat()} to {max_date.isoformat()}).",
            )

        snapped_lat = snap_to_grid(lat)
        snapped_lon = snap_to_grid(lon)

        data_service = OpenMeteoService()
        weather_data = await data_service.fetch_historical_weather(snapped_lat, snapped_lon, date)

        feature_eng = FeatureEngineer()
        target_time = datetime.fromisoformat(f"{date}T{hour:02d}:00:00")
        features = feature_eng.build_feature_vector_simple(
            weather_data=weather_data,
            lat=snapped_lat,
            lon=snapped_lon,
            timestamp=target_time,
            hour_index=hour,
        )

        ts_model = ThunderstormClassifier()
        lt_model = LightningPredictor()
        severity_classifier = SeverityClassifier()

        ts_prob, ts_conf, severity_str = ts_model.predict(features)
        lt_prob, _ = lt_model.predict(features, ts_prob)

        try:
            sev_enum = SeverityLevel(severity_str)
        except ValueError:
            sev_enum = SeverityLevel.none

        # Extract actual observed weather code at the specified hour
        hourly = weather_data.get("hourly", {})
        weather_codes = hourly.get("weather_code", [])

        actual_weather_code: int | None = None
        actual_was_thunderstorm: bool | None = None

        if weather_codes and 0 <= hour < len(weather_codes) and weather_codes[hour] is not None:
            actual_weather_code = int(weather_codes[hour])
            actual_was_thunderstorm = actual_weather_code in CONVECTIVE_CODES

        prediction = ThunderstormPrediction(
            latitude=snapped_lat,
            longitude=snapped_lon,
            timestamp=datetime.now(timezone.utc),
            prediction_time=target_time,
            lead_time_hours=1.0,
            thunderstorm_probability=round(ts_prob, 4),
            severity=sev_enum,
            lightning_probability=round(lt_prob, 4),
            confidence=round(ts_conf, 4),
            contributing_factors={
                "cape": round(float(features.get("cape", 0.0)), 1),
                "cin": round(float(features.get("cin", 0.0)), 1),
                "relative_humidity": round(float(features.get("relative_humidity", 0.0)), 1),
                "dew_point_depression": round(float(features.get("dew_point_depression", 0.0)), 1),
                "precipitable_water": round(float(features.get("precipitable_water", 0.0)), 1),
                "precip_last_3hr": 0.0,
                "pressure_trend": 0.0,
            },
            disclaimer=DEFAULT_DISCLAIMER,
        )

        return HistoricalResponse(
            request_time=datetime.now(timezone.utc),
            date=date,
            hour=hour,
            prediction=prediction,
            actual_weather_code=actual_weather_code,
            actual_was_thunderstorm=actual_was_thunderstorm,
            disclaimer=DEFAULT_DISCLAIMER,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying historical prediction for ({lat}, {lon}) on {date} hour {hour}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal historical verification error.")
