"""Alert routes with role-based authentication, rate limiting, and alert de-duplication."""

import logging
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
import httpx
from app.api.auth import require_role
from app.config import settings
from app.core.cache import meteo_cache
from app.core.limiter import limiter
from app.models.schemas import DEFAULT_DISCLAIMER, GenerateAlertsRequest, TestAlertRequest
from app.services.alert_service import AlertService

logger = logging.getLogger("vajranowcast.api.alerts")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

router = APIRouter()


@router.get("/active")
async def get_active_alerts(request: Request):
    """
    Retrieve all currently active severe weather and thunderstorm alerts.
    Public endpoint with automatic stale alert expiration.
    """
    try:
        service = AlertService()
        alerts = await service.get_active_alerts()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(alerts),
            "alerts": alerts,
            "disclaimer": DEFAULT_DISCLAIMER,
        }
    except Exception as e:
        logger.error(f"Error retrieving active alerts: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal alert retrieval error.")


@router.post("/generate")
@limiter.limit(settings.RATE_LIMIT_ALERTS)
async def generate_alerts(
    request: Request,
    payload: Optional[GenerateAlertsRequest] = None,
    current_user: Dict[str, Any] = Depends(require_role(["meteorologist", "admin"])),
):
    """
    Trigger alert generation from precomputed city predictions (optional body) or Pages CDN.
    Never calls Open-Meteo directly on Render.
    Protected endpoint: Requires 'meteorologist' or 'admin' role in Supabase Auth app_metadata or valid X-Admin-Token.
    """
    try:
        user_info = f"user {current_user.get('sub')} (role: {current_user.get('role')})"
        logger.info(f"Alert generation triggered by {user_info}")

        predictions_by_city: Dict[str, Any] = {}

        if payload and payload.cities:
            logger.info("Using precomputed city predictions provided in request body.")
            predictions_by_city = {
                city: [item.model_dump() for item in items]
                for city, items in payload.cities.items()
            }
        else:
            logger.info("No payload provided in generate request; loading precomputed cities from cache/Pages CDN.")
            # 1. Check in-memory cache
            cached = meteo_cache.get_cities_nowcast()
            if cached is not None:
                data, _, _ = cached
                predictions_by_city = data

            # 2. Try fetching from Pages CDN
            if not predictions_by_city and settings.GITHUB_PAGES_BASE_URL:
                cdn_url = f"{settings.GITHUB_PAGES_BASE_URL.rstrip('/')}/cities_latest.json"
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        res = await client.get(cdn_url)
                        if res.status_code == 200:
                            cdn_payload = res.json()
                            predictions_by_city = cdn_payload.get("cities", {})
                            meteo_cache.set_cities_nowcast(predictions_by_city)
                except Exception as e:
                    logger.warning(f"Could not fetch cities from Pages CDN ({cdn_url}): {e}")

            # 3. Fallback to local files
            if not predictions_by_city:
                local_file = DATA_DIR / "cities_latest.json"
                if not local_file.exists():
                    local_file = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "public" / "data" / "cities_latest.json"
                if local_file.exists():
                    try:
                        with open(local_file, "r", encoding="utf-8") as f:
                            local_payload = json.load(f)
                            predictions_by_city = local_payload.get("cities", {})
                            meteo_cache.set_cities_nowcast(predictions_by_city)
                    except Exception as e:
                        logger.warning(f"Could not load local cities file {local_file}: {e}")

        alert_svc = AlertService()
        generated = await alert_svc.generate_alerts(predictions_by_city)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "triggered_by": current_user.get("role"),
            "alerts_generated": len(generated),
            "alerts": generated,
            "disclaimer": DEFAULT_DISCLAIMER,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating alerts batch: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal alert generation error.")


@router.post("/test")
@limiter.limit(settings.RATE_LIMIT_ALERTS)
async def create_test_alert(
    request: Request,
    payload: TestAlertRequest,
    current_user: Dict[str, Any] = Depends(require_role(["meteorologist", "admin"])),
):
    """
    Staff-only drill endpoint: create a simulated test alert with is_test=true, expiring in 15 minutes.
    Protected endpoint: Requires 'meteorologist' or 'admin' role in Supabase Auth app_metadata or valid X-Admin-Token.
    """
    try:
        user_info = f"user {current_user.get('sub')} (role: {current_user.get('role')})"
        logger.info(f"Test alert triggered by {user_info} for city {payload.city} (tier: {payload.tier})")

        alert_svc = AlertService()
        alert = await alert_svc.create_test_alert(
            city=payload.city,
            tier=payload.tier,
            lead_time_hours=payload.lead_time_hours,
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "triggered_by": current_user.get("role"),
            "alert": alert,
            "disclaimer": DEFAULT_DISCLAIMER,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating test alert: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal test alert creation error.")
