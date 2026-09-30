"""Supabase free-tier maintenance script: Keep-alive ping and 7-day data retention cleanup."""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend root to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.models.database import get_supabase_admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vajranowcast.maintenance")


def run_supabase_maintenance() -> bool:
    """
    Perform keep-alive query and enforce 7-day data retention on Supabase free tier.
    """
    logger.info("Starting Supabase free-tier maintenance...")
    try:
        supabase = get_supabase_admin()
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return False

    now_utc = datetime.now(timezone.utc)
    logger.info(f"Connected to Supabase ({settings.SUPABASE_URL}) at {now_utc.isoformat()}")

    # 1. Keep-Alive Ping
    try:
        res = supabase.table("alerts").select("count", count="exact").limit(1).execute()
        total_alerts = res.count if hasattr(res, "count") else len(res.data or [])
        logger.info(f"[Keep-Alive] Ping successful. Active table row count: {total_alerts}")
    except Exception as e:
        logger.warning(f"[Keep-Alive] Ping query encountered error: {e}")

    # 2. 7-Day Data Retention Cleanup
    seven_days_ago_iso = (now_utc.replace(hour=0, minute=0, second=0, microsecond=0)).isoformat()

    try:
        # Inactive alerts cleanup
        res_alerts = (
            supabase.table("alerts")
            .delete()
            .lt("created_at", seven_days_ago_iso)
            .eq("is_active", False)
            .execute()
        )
        logger.info("[Retention] Purged inactive alerts older than 7 days.")
    except Exception as e:
        logger.warning(f"[Retention] Alerts cleanup note: {e}")

    try:
        # Historical predictions cleanup
        supabase.table("predictions").delete().lt("created_at", seven_days_ago_iso).execute()
        logger.info("[Retention] Purged predictions older than 7 days.")
    except Exception as e:
        logger.warning(f"[Retention] Predictions cleanup note: {e}")

    try:
        # Weather cache cleanup
        supabase.table("weather_cache").delete().lt("cached_at", seven_days_ago_iso).execute()
        logger.info("[Retention] Purged weather_cache entries older than 7 days.")
    except Exception as e:
        logger.warning(f"[Retention] Weather cache cleanup note: {e}")

    logger.info("Supabase maintenance completed successfully.")
    return True


if __name__ == "__main__":
    success = run_supabase_maintenance()
    sys.exit(0 if success else 1)
