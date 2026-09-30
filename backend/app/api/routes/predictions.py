"""Prediction and nowcasting API routes with grid snapping, strict input bounds, rate limiting, and spatial grid."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional, Set
from fastapi import APIRouter, HTTPException, Query, Request, status
from app.config import settings
from app.core.cache import meteo_cache
from app.core.limiter import limiter
from app.models.schemas import (
    DEFAULT_DISCLAIMER,
    GridPointPrediction,
    GridResponse,
    HistoricalReplayEvent,
    HistoricalResponse,
    NowcastResponse,
    SeverityLevel,
    ThunderstormPrediction,
)
from app.services.data_ingestion import OpenMeteoService
from app.services.feature_engineering import FeatureEngineer
from app.services.training_features import build_features_from_raw_slice
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
    {"name": "Nagpur", "lat": 21.15, "lon": 79.09},
]

ALLOWED_LEAD_HOURS: Set[float] = {0.0, 1.0, 2.0, 3.0, 6.0}
CONVECTIVE_CODES = {80, 81, 82, 85, 91, 92, 93, 95, 96, 99}

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
GRID_FILE = DATA_DIR / "latest_grid.json"
REPLAYS_DIR = DATA_DIR / "historical_replays"


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
    Automatically snaps coordinates to 0.25° grid, applies 15-minute TTL caching, and supports graceful stale fallback.
    """
    try:
        snapped_lat = snap_to_grid(lat)
        snapped_lon = snap_to_grid(lon)

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
        predictions = await nowcaster.predict_for_location(lat, lon, raw_hours)

        now = datetime.now(timezone.utc)
        is_any_stale = any(p.stale for p in predictions)
        cached_at = predictions[0].cached_at if predictions else None

        metadata = {
            "model_version": f"{settings.APP_VERSION}-calibrated-hgbc",
            "model_type": "HistGradientBoostingClassifier + CalibratedClassifierCV",
            "data_sources": ["Open-Meteo Forecast API"],
            "optimal_threshold": settings.OPTIMAL_THRESHOLD,
            "decision_rule": f"P(TS) >= {settings.OPTIMAL_THRESHOLD} signifies high storm threat",
            "target_description": "probability of heavy warm convective rainfall (>2 mm/h with warm, humid conditions) in the next hour, used as a thunderstorm proxy",
            "thermodynamic_indices_description": "Empirical thermodynamic approximations derived from surface temperature, dewpoint, and surface pressure using Bolton (1980) formulas; not NWP sounding integrations",
            "features_count": 24,
            "target_lead_time": "t+1 hour",
            "confidence_formula": "base_confidence * max(0.60, 1.0 - (lead_hours / 6.0) * 0.40)",
            "snapped_coordinates": {"latitude": snapped_lat, "longitude": snapped_lon},
        }

        return NowcastResponse(
            request_time=now,
            predictions=predictions,
            metadata=metadata,
            stale=is_any_stale,
            cached_at=cached_at,
            disclaimer=DEFAULT_DISCLAIMER,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating nowcast for ({lat}, {lon}): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal nowcasting engine error.")


@router.get("/model/info")
async def get_model_info():
    """
    Get machine learning model metadata, architecture details, feature list, and confidence calibration formulas.
    """
    return {
        "model_name": "Calibrated HistGradientBoostingClassifier",
        "model_type": "HistGradientBoostingClassifier + CalibratedClassifierCV (Isotonic)",
        "lead_time": "1_hour (t+1 nowcast)",
        "target_description": "probability of heavy warm convective rainfall (>2 mm/h with warm, humid conditions) in the next hour, used as a thunderstorm proxy",
        "thermodynamic_indices_description": "Empirical thermodynamic approximations derived from surface temperature, dewpoint, and surface pressure using Bolton (1980) formulas; not NWP sounding integrations",
        "optimal_threshold": settings.OPTIMAL_THRESHOLD,
        "decision_rule": f"P(TS) >= {settings.OPTIMAL_THRESHOLD} signifies thunderstorm occurrence in the next hour",
        "confidence_calibration": {
            "description": "Dynamic confidence score reflecting distance from decision boundary scaled by lead-time decay factor.",
            "base_confidence_formula": "np.clip(0.50 + 0.45 * min(|P(TS) - 0.1860| / 0.50, 1.0), 0.50, 0.95)",
            "lead_time_factor_formula": "max(0.60, 1.0 - (lead_hours / 6.0) * 0.40)",
            "final_confidence_formula": "round(base_confidence * lead_time_factor, 4)",
            "lead_factor_values": {
                "lead_0h": 1.0,
                "lead_1h": 0.9333,
                "lead_2h": 0.8667,
                "lead_3h": 0.8000,
                "lead_6h": 0.6000,
            },
        },
        "lightning_model": {
            "method": "rule-based heuristic",
            "formula": "round(min(ts_prob * 0.90, 0.99), 4)",
            "description": "Monotonic function of thunderstorm probability ensuring lightning never exceeds storm probability.",
        },
        "alert_tiers": {
            "watch": settings.ALERT_TIER_WATCH,
            "advisory": settings.ALERT_TIER_ADVISORY,
            "warning": settings.ALERT_TIER_WARNING,
        },
        "severity_bands": {
            "method": "purely P(TS)-dependent threshold calibration",
            "very_severe": f"P(TS) >= {settings.SEVERE_PROB_THRESHOLD} (0.75)",
            "severe": f"P(TS) >= {settings.ALERT_PROB_THRESHOLD} (0.60)",
            "moderate": "P(TS) >= 0.40",
            "weak": f"P(TS) >= {settings.OPTIMAL_THRESHOLD} (0.1860)",
            "none": f"P(TS) < {settings.OPTIMAL_THRESHOLD} (0.1860)",
        },
        "features": [
            "cape", "cin", "temperature_2m", "dewpoint_2m", "relative_humidity",
            "surface_pressure", "wind_speed_10m", "wind_direction_10m", "cloud_cover",
            "precipitable_water", "dew_point_depression", "cape_cin_ratio", "hour_sin",
            "hour_cos", "month_sin", "month_cos", "latitude", "longitude",
            "precip_1hr_ago", "precip_last_3hr", "storm_2hr_ago", "cloud_trend",
            "temp_trend", "pressure_trend"
        ],
        "num_features": 24,
        "roc_auc": 0.9467,
        "disclaimer": DEFAULT_DISCLAIMER,
    }


@router.get("/nowcast/cities")
@limiter.limit(settings.RATE_LIMIT_CITIES)
async def get_cities_nowcast(request: Request):
    """
    Get nowcasts for 10 major Indian metropolitan hubs using a single batched HTTP call and 15-minute TTL caching.
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


@router.get("/grid", response_model=GridResponse)
@limiter.limit("60/minute")
async def get_precomputed_grid(request: Request):
    """
    Retrieve the latest precomputed regional thunderstorm and lightning nowcast grid across India.
    Served from 10-minute in-memory cache with fallback to GitHub Pages CDN or last known good memory state (up to 3h max).
    """
    # 1. Check in-memory cache first
    cached = meteo_cache.get_grid()
    if cached is not None:
        data, is_stale, cached_at = cached
        points = [
            GridPointPrediction(
                latitude=p["latitude"],
                longitude=p["longitude"],
                thunderstorm_probability=p.get("thunderstorm_probability", 0.0),
                severity=SeverityLevel(p.get("severity", "none")),
                lightning_probability=p.get("lightning_probability", 0.0),
                confidence=p.get("confidence", 0.0),
                cape=p.get("cape", 0.0),
                cin=p.get("cin", 0.0),
                precipitable_water=p.get("precipitable_water", 0.0),
            )
            for p in data.get("points", [])
        ]
        return GridResponse(
            generated_at=datetime.fromisoformat(data["generated_at"]) if isinstance(data["generated_at"], str) else data["generated_at"],
            valid_until=datetime.fromisoformat(data["valid_until"]) if isinstance(data["valid_until"], str) else data["valid_until"],
            lead_time_hours=data.get("lead_time_hours", 1.0),
            total_points=len(points),
            resolution_deg=data.get("resolution_deg", 1.6),
            grid_resolution_km=data.get("grid_resolution_km", 175.0),
            stale=is_stale,
            stale_reason="Served from 3-hour memory cache" if is_stale else None,
            points=points,
            disclaimer=data.get("disclaimer", DEFAULT_DISCLAIMER),
        )

    # 2. Try fetching from GitHub Pages CDN if configured
    if settings.GITHUB_PAGES_BASE_URL:
        cdn_url = f"{settings.GITHUB_PAGES_BASE_URL.rstrip('/')}/grid_latest.json"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(cdn_url)
                if res.status_code == 200:
                    payload = res.json()
                    meteo_cache.set_grid(payload)
                    points = [
                        GridPointPrediction(
                            latitude=p["latitude"],
                            longitude=p["longitude"],
                            thunderstorm_probability=p.get("thunderstorm_probability", 0.0),
                            severity=SeverityLevel(p.get("severity", "none")),
                            lightning_probability=p.get("lightning_probability", 0.0),
                            confidence=p.get("confidence", 0.0),
                            cape=p.get("cape", 0.0),
                            cin=p.get("cin", 0.0),
                            precipitable_water=p.get("precipitable_water", 0.0),
                        )
                        for p in payload.get("points", [])
                    ]
                    return GridResponse(
                        generated_at=datetime.fromisoformat(payload["generated_at"]),
                        valid_until=datetime.fromisoformat(payload["valid_until"]),
                        lead_time_hours=payload.get("lead_time_hours", 1.0),
                        total_points=len(points),
                        resolution_deg=payload.get("resolution_deg", 1.6),
                        grid_resolution_km=payload.get("grid_resolution_km", 175.0),
                        stale=False,
                        stale_reason=None,
                        points=points,
                        disclaimer=payload.get("disclaimer", DEFAULT_DISCLAIMER),
                    )
        except Exception as e:
            logger.warning(f"Could not fetch grid from Pages CDN ({cdn_url}): {e}")

    # 3. Fallback: Clean empty grid response if no data has been cached yet
    now = datetime.now(timezone.utc)
    return GridResponse(
        generated_at=now,
        valid_until=now + timedelta(hours=1),
        total_points=0,
        resolution_deg=1.6,
        grid_resolution_km=175.0,
        stale=True,
        stale_reason="Grid precomputation dataset initializing on Pages CDN",
        points=[],
        disclaimer=DEFAULT_DISCLAIMER,
    )


@router.get("/historical/replays", response_model=List[HistoricalReplayEvent])
async def list_historical_replays():
    """
    List curated real historical Indian thunderstorm and lightning events available for instant replay.
    """
    events = []
    if REPLAYS_DIR.exists():
        for file_path in sorted(REPLAYS_DIR.glob("*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    events.append(
                        HistoricalReplayEvent(
                            event_id=d.get("event_id", file_path.stem),
                            event_name=d.get("event_name", "Historical Event"),
                            city=d.get("city", "India"),
                            state=d.get("state", "India"),
                            latitude=d.get("latitude", 0.0),
                            longitude=d.get("longitude", 0.0),
                            date=d.get("date", ""),
                            hour_ist=d.get("hour_ist", ""),
                            hour_utc=d.get("hour_utc", ""),
                            synoptic_summary=d.get("synoptic_summary", ""),
                            source=d.get("source", "Open-Meteo Historical Archive"),
                            source_url=d.get("source_url", ""),
                            computed_verdict=d.get("computed_verdict"),
                            verified_by_human=d.get("verified_by_human", False),
                            optimal_threshold=d.get("optimal_threshold", 0.186),
                            features_vector=d.get("features_vector"),
                            prediction=d.get("prediction"),
                            actual_outcome=d.get("actual_outcome"),
                            timeline=d.get("timeline"),
                        )
                    )
            except Exception as e:
                logger.warning(f"Error parsing replay file {file_path}: {e}")

    return events


@router.get("/historical", response_model=HistoricalResponse)
@limiter.limit(settings.RATE_LIMIT_NOWCAST)
async def get_historical_verification(
    request: Request,
    lat: float = Query(..., ge=settings.INDIA_LAT_MIN, le=settings.INDIA_LAT_MAX, description="Latitude"),
    lon: float = Query(..., ge=settings.INDIA_LON_MIN, le=settings.INDIA_LON_MAX, description="Longitude"),
    date: str = Query(..., description="Target date in YYYY-MM-DD format (2015-01-01 to today - 5 days)"),
    hour: int = Query(..., ge=0, le=23, description="Target UTC/local hour (0-23)"),
    event_id: Optional[str] = Query(None, description="Optional curated event ID for instant certified replay"),
):
    """
    Run historical retrospective inference and verify against actual recorded weather code.
    Enforces date range bounds (2015-01-01 to 5 days prior to current date) or loads curated certified events.
    """
    try:
        # Check if matching curated event replay exists
        if event_id and REPLAYS_DIR.exists():
            matched_file = None
            for p in REPLAYS_DIR.glob("*.json"):
                if p.stem == event_id or p.stem == event_id.replace("-", "_"):
                    matched_file = p
                    break
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        d = json.load(f)
                        if d.get("event_id") == event_id:
                            matched_file = p
                            break
                except Exception:
                    pass

            if matched_file and matched_file.exists():
                with open(matched_file, "r", encoding="utf-8") as f:
                    ev_data = json.load(f)
                pred_data = ev_data["prediction"]
                outcome_data = ev_data["actual_outcome"]
                h_idx = ev_data.get("hour_idx", hour)
                target_time = datetime.fromisoformat(f"{ev_data['date']}T{h_idx:02d}:00:00+05:30")
                prediction = ThunderstormPrediction(
                    latitude=ev_data["latitude"],
                    longitude=ev_data["longitude"],
                    timestamp=datetime.now(timezone.utc),
                    prediction_time=target_time,
                    lead_time_hours=pred_data.get("lead_time_hours", 1.0),
                    thunderstorm_probability=pred_data["thunderstorm_probability"],
                    severity=SeverityLevel(pred_data["severity"]),
                    lightning_probability=pred_data["lightning_probability"],
                    confidence=pred_data["confidence"],
                    contributing_factors=pred_data.get("contributing_factors"),
                    disclaimer=DEFAULT_DISCLAIMER,
                )
                return HistoricalResponse(
                    request_time=datetime.now(timezone.utc),
                    date=ev_data["date"],
                    hour=int(ev_data.get("hour_idx", hour)),
                    prediction=prediction,
                    actual_weather_code=outcome_data.get("weather_code"),
                    actual_was_thunderstorm=outcome_data.get("was_thunderstorm"),
                    disclaimer=DEFAULT_DISCLAIMER,
                )

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
        features = build_features_from_raw_slice(
            raw_hourly=weather_data.get("hourly", {}),
            target_idx=hour,
            original_lat=snapped_lat,
            original_lon=snapped_lon,
            target_time=target_time,
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

        hourly = weather_data.get("hourly", {})
        weather_codes = hourly.get("weather_code", [])

        actual_weather_code: Optional[int] = None
        actual_was_thunderstorm: Optional[bool] = None

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
