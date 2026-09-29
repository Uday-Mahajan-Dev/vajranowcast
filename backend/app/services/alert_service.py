"""Alert generation and active alerts management service interfacing with Supabase."""

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from app.config import settings
from app.models.database import get_supabase_admin
from app.models.schemas import ThunderstormPrediction

logger = logging.getLogger("vajranowcast.alerts")


class AlertService:
    """Service to generate, persist, query, and expire convective weather alerts."""

    def __init__(self):
        try:
            self.supabase = get_supabase_admin()
        except Exception as e:
            logger.error(f"Failed to initialize Supabase admin client: {e}")
            self.supabase = None

    async def generate_alerts(self, predictions_by_city: dict[str, list[Any]]) -> list[dict[str, Any]]:
        """
        Evaluate city predictions against ALERT_PROB_THRESHOLD (0.6) and publish new alerts.
        """
        results: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for city, preds in predictions_by_city.items():
            if not isinstance(preds, list):
                continue

            for p in preds:
                # Support both dict and ThunderstormPrediction Pydantic model
                if isinstance(p, ThunderstormPrediction):
                    ts_prob = p.thunderstorm_probability
                    lt_prob = p.lightning_probability
                    lat = p.latitude
                    lon = p.longitude
                    severity_val = p.severity.value if hasattr(p.severity, "value") else str(p.severity)
                    lead_hours = p.lead_time_hours
                elif isinstance(p, dict):
                    if "error" in p or "thunderstorm_probability" not in p:
                        continue
                    ts_prob = float(p.get("thunderstorm_probability", 0.0))
                    lt_prob = float(p.get("lightning_probability", 0.0))
                    lat = float(p.get("latitude", 0.0))
                    lon = float(p.get("longitude", 0.0))
                    severity_val = str(p.get("severity", "none"))
                    lead_hours = float(p.get("lead_time_hours", 1.0))
                else:
                    continue

                if ts_prob >= settings.ALERT_PROB_THRESHOLD:
                    alert_id = str(uuid.uuid4())
                    valid_from = now.isoformat()
                    valid_until = (now + timedelta(hours=lead_hours + 1.0)).isoformat()
                    msg = (
                        f"⚠️ {severity_val.upper()} thunderstorm expected in {city} "
                        f"within {int(lead_hours)}h. Probability: {ts_prob * 100:.0f}%"
                    )

                    alert_dict = {
                        "alert_id": alert_id,
                        "city": city,
                        "latitude": lat,
                        "longitude": lon,
                        "alert_type": "thunderstorm",
                        "severity": severity_val,
                        "thunderstorm_probability": ts_prob,
                        "lightning_probability": lt_prob,
                        "valid_from": valid_from,
                        "valid_until": valid_until,
                        "lead_time_hours": lead_hours,
                        "message": msg,
                        "is_active": True,
                    }

                    if self.supabase is not None:
                        try:
                            # Note: Supabase python client methods are synchronous
                            self.supabase.table("alerts").insert(alert_dict).execute()
                        except Exception as e:
                            logger.error(f"Error persisting alert to Supabase: {e}")

                    results.append(alert_dict)

        return results

    async def get_active_alerts(self) -> list[dict[str, Any]]:
        """Fetch all active alerts from the Supabase database ordered by latest creation."""
        if self.supabase is None:
            return []

        try:
            # Sync Supabase call
            response = (
                self.supabase.table("alerts")
                .select("*")
                .eq("is_active", True)
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Error fetching active alerts: {e}")
            return []

    async def expire_old_alerts(self):
        """Mark alerts whose valid_until timestamp has passed as inactive."""
        if self.supabase is None:
            return

        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            (
                self.supabase.table("alerts")
                .update({"is_active": False})
                .lt("valid_until", now_iso)
                .eq("is_active", True)
                .execute()
            )
        except Exception as e:
            logger.error(f"Error expiring old alerts: {e}")
