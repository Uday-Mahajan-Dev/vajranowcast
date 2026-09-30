"""Alert generation, de-duplication, and active alerts management interfacing with Supabase asynchronously."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from app.config import settings
from app.models.database import get_supabase_admin
from app.models.schemas import ThunderstormPrediction

logger = logging.getLogger("vajranowcast.alerts")


class AlertService:
    """Service to generate, de-duplicate, persist, query, and expire convective weather alerts."""

    def __init__(self):
        try:
            self.supabase = get_supabase_admin()
        except Exception as e:
            logger.error(f"Failed to initialize Supabase admin client: {e}")
            self.supabase = None

    def _sync_expire_old_alerts(self) -> None:
        """Synchronous helper to expire outdated alerts in Supabase."""
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
            logger.warning(f"Failed to expire old alerts: {e}")

    def _sync_get_active_alerts_for_city(self, city: str) -> List[Dict[str, Any]]:
        """Synchronous query for currently active alerts in a specific city."""
        if self.supabase is None:
            return []
        try:
            res = (
                self.supabase.table("alerts")
                .select("*")
                .eq("city", city)
                .eq("is_active", True)
                .eq("alert_type", "thunderstorm")
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Error querying active alerts for city {city}: {e}")
            return []

    def _sync_insert_alert(self, alert_dict: Dict[str, Any]) -> None:
        """Synchronous insert into Supabase alerts table with conflict fallback."""
        if self.supabase is None:
            return
        try:
            self.supabase.table("alerts").insert(alert_dict).execute()
        except Exception as e:
            logger.warning(f"Insert encountered conflict or error: {e}. Falling back to update on active record.")
            city = alert_dict.get("city")
            if city:
                existing = self._sync_get_active_alerts_for_city(city)
                if existing:
                    target_id = existing[0]["alert_id"]
                    self._sync_update_alert(target_id, {
                        "severity": alert_dict.get("severity"),
                        "thunderstorm_probability": alert_dict.get("thunderstorm_probability"),
                        "lightning_probability": alert_dict.get("lightning_probability"),
                        "valid_until": alert_dict.get("valid_until"),
                        "lead_time_hours": alert_dict.get("lead_time_hours"),
                        "message": alert_dict.get("message"),
                        "is_active": True,
                    })

    def _sync_update_alert(self, alert_id: str, updates: Dict[str, Any]) -> None:
        """Synchronous update on Supabase alerts table by alert_id."""
        if self.supabase is None:
            return
        self.supabase.table("alerts").update(updates).eq("alert_id", alert_id).execute()

    def _sync_get_all_active_alerts(self) -> List[Dict[str, Any]]:
        """Synchronous query for all active alerts."""
        if self.supabase is None:
            return []
        res = (
            self.supabase.table("alerts")
            .select("*")
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        return res.data or []

    async def expire_old_alerts(self) -> None:
        """Asynchronously mark alerts whose valid_until timestamp has passed as inactive."""
        await asyncio.to_thread(self._sync_expire_old_alerts)

    @staticmethod
    def get_tier_for_probability(ts_prob: float) -> Optional[str]:
        """Classify probability into alert tier: warning, advisory, watch, or None."""
        if ts_prob >= settings.ALERT_TIER_WARNING:
            return "warning"
        if ts_prob >= settings.ALERT_TIER_ADVISORY:
            return "advisory"
        if ts_prob >= settings.ALERT_TIER_WATCH:
            return "watch"
        return None

    @staticmethod
    def build_tier_message(city: str, tier: str, ts_prob: float, lead_hours: float) -> str:
        """Format honest and actionable alert message according to tier."""
        pct = int(round(ts_prob * 100))
        lead_int = max(1, int(round(lead_hours)))
        if tier == "warning":
            return f"Warning: severe convective thunderstorm and heavy rain expected in {city} within {lead_int}h ({pct}%)"
        if tier == "advisory":
            return f"Advisory: heavy rain possible in the next hour in {city} ({pct}%)"
        return f"Watch: convective storm conditions developing in {city} within {lead_int}h ({pct}%)"

    async def generate_alerts(self, predictions_by_city: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        """
        Evaluate city predictions against 3-tier thresholds (WATCH >= 0.30, ADVISORY >= 0.40, WARNING >= 0.60),
        de-duplicate against existing active alerts, and persist or update in Supabase asynchronously.
        """
        # Step 1: Clean up any expired alerts first
        await self.expire_old_alerts()

        results: List[Dict[str, Any]] = []
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

                tier = self.get_tier_for_probability(ts_prob)
                if tier is not None:
                    valid_from = now.isoformat()
                    valid_until = (now + timedelta(hours=lead_hours + 1.0)).isoformat()
                    msg = self.build_tier_message(city, tier, ts_prob, lead_hours)

                    # Step 2: De-duplication check against existing active alerts for this city
                    existing_active = await asyncio.to_thread(self._sync_get_active_alerts_for_city, city)

                    if existing_active:
                        # Existing active alert found: Update it with latest threat state & tier
                        target_alert = existing_active[0]
                        alert_id = target_alert["alert_id"]
                        updates = {
                            "severity": severity_val,
                            "tier": tier,
                            "is_test": False,
                            "thunderstorm_probability": ts_prob,
                            "lightning_probability": lt_prob,
                            "valid_until": valid_until,
                            "lead_time_hours": lead_hours,
                            "message": msg,
                            "is_active": True,
                        }
                        try:
                            await asyncio.to_thread(self._sync_update_alert, alert_id, updates)
                            target_alert.update(updates)
                            results.append(target_alert)
                            logger.info(f"De-duplicated and updated existing {tier.upper()} alert for {city} (ID: {alert_id})")
                        except Exception as e:
                            logger.error(f"Error updating existing alert in Supabase: {e}")
                    else:
                        # No existing active alert: Create and insert new tier record
                        alert_id = str(uuid.uuid4())
                        alert_dict = {
                            "alert_id": alert_id,
                            "city": city,
                            "latitude": lat,
                            "longitude": lon,
                            "alert_type": "thunderstorm",
                            "severity": severity_val,
                            "tier": tier,
                            "is_test": False,
                            "thunderstorm_probability": ts_prob,
                            "lightning_probability": lt_prob,
                            "valid_from": valid_from,
                            "valid_until": valid_until,
                            "lead_time_hours": lead_hours,
                            "message": msg,
                            "is_active": True,
                        }
                        try:
                            await asyncio.to_thread(self._sync_insert_alert, alert_dict)
                            results.append(alert_dict)
                            logger.info(f"Inserted new {tier.upper()} alert for {city} (ID: {alert_id})")
                        except Exception as e:
                            logger.error(f"Error persisting new alert to Supabase: {e}")
                            results.append(alert_dict)

        return results

    async def create_test_alert(
        self,
        city: str,
        tier: str = "warning",
        lead_time_hours: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Create a staff simulation/drill alert with is_test=True, expiring strictly in 15 minutes.
        Real alerts can NEVER be created through this method.
        """
        from app.api.routes.predictions import INDIAN_CITIES

        # Step 1: Resolve city metadata
        matched_city = next((c for c in INDIAN_CITIES if c["name"].lower() == city.lower()), None)
        city_name = matched_city["name"] if matched_city else city
        lat = matched_city["lat"] if matched_city else 28.61
        lon = matched_city["lon"] if matched_city else 77.21

        # Step 2: Normalize tier and test parameters
        normalized_tier = tier.lower().strip()
        if normalized_tier not in ("watch", "advisory", "warning"):
            normalized_tier = "warning"

        if normalized_tier == "warning":
            prob = 0.65
            sev = "severe"
        elif normalized_tier == "advisory":
            prob = 0.45
            sev = "moderate"
        else:
            prob = 0.35
            sev = "weak"

        now = datetime.now(timezone.utc)
        valid_from = now.isoformat()
        # 15 minutes drill lifetime
        valid_until = (now + timedelta(minutes=15)).isoformat()
        msg = f"TEST — DRILL: {normalized_tier.capitalize()}: simulated convective event for {city_name} ({int(round(prob*100))}%)"

        alert_id = str(uuid.uuid4())
        alert_dict = {
            "alert_id": alert_id,
            "city": city_name,
            "latitude": lat,
            "longitude": lon,
            "alert_type": "thunderstorm",
            "severity": sev,
            "tier": normalized_tier,
            "is_test": True,
            "thunderstorm_probability": prob,
            "lightning_probability": prob * 0.9,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "lead_time_hours": lead_time_hours,
            "message": msg,
            "is_active": True,
        }

        # De-duplicate existing active alert for this city
        existing_active = await asyncio.to_thread(self._sync_get_active_alerts_for_city, city_name)
        if existing_active:
            target_id = existing_active[0]["alert_id"]
            await asyncio.to_thread(self._sync_update_alert, target_id, alert_dict)
            alert_dict["alert_id"] = target_id
        else:
            await asyncio.to_thread(self._sync_insert_alert, alert_dict)

        logger.info(f"Created TEST drill alert for {city_name} ({normalized_tier.upper()}) ID: {alert_dict['alert_id']}")
        return alert_dict

    async def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Fetch all active alerts asynchronously from Supabase, expiring stale ones first."""
        await self.expire_old_alerts()
        return await asyncio.to_thread(self._sync_get_all_active_alerts)
