"""Alert routes for querying active convective alerts and triggering batch alert generation."""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.api.routes.predictions import INDIAN_CITIES
from app.services.alert_service import AlertService
from app.services.ml_inference import NowcastingService

logger = logging.getLogger("vajranowcast.api.alerts")

router = APIRouter()


@router.get("/active")
async def get_active_alerts():
    """Retrieve all active severe weather and thunderstorm alerts."""
    try:
        service = AlertService()
        alerts = await service.get_active_alerts()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(alerts),
            "alerts": alerts,
        }
    except Exception as e:
        logger.error(f"Error retrieving active alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_alerts():
    """
    Trigger real-time scan across major Indian cities and generate alerts for high-probability threats.
    """
    try:
        nowcaster = NowcastingService()
        predictions_by_city = await nowcaster.predict_for_cities(INDIAN_CITIES)

        alert_svc = AlertService()
        generated = await alert_svc.generate_alerts(predictions_by_city)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alerts_generated": len(generated),
            "alerts": generated,
        }
    except Exception as e:
        logger.error(f"Error generating alerts batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))
