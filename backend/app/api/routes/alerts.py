"""Alert routes with role-based authentication, rate limiting, and alert de-duplication."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.api.auth import require_role
from app.api.routes.predictions import INDIAN_CITIES
from app.config import settings
from app.core.limiter import limiter
from app.models.schemas import DEFAULT_DISCLAIMER
from app.services.alert_service import AlertService
from app.services.ml_inference import NowcastingService

logger = logging.getLogger("vajranowcast.api.alerts")

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
    current_user: Dict[str, Any] = Depends(require_role(["meteorologist", "admin"])),
):
    """
    Trigger real-time scan across major Indian cities and generate/update alerts for high-probability threats.
    Protected endpoint: Requires 'meteorologist' or 'admin' role in Supabase Auth app_metadata or valid X-Admin-Token.
    """
    try:
        user_info = f"user {current_user.get('sub')} (role: {current_user.get('role')})"
        logger.info(f"Alert generation triggered by {user_info}")

        nowcaster = NowcastingService()
        predictions_by_city = await nowcaster.predict_for_cities(INDIAN_CITIES)

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
