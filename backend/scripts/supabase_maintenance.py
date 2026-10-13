"""Supabase free-tier maintenance script: Keep-alive ping and 7-day data retention cleanup."""

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend root to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.models.database import get_supabase_admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vajranowcast.maintenance")

RETENTION_DAYS = 7


def run_supabase_maintenance() -> bool:
    """Keep the free-tier project awake and enforce 7-day data retention."""
    logger.info("Starting Supabase free-tier maintenance...")
    try:
        supabase = get_supabase_admin()
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return False

    now_utc = datetime.now(timezone.utc)
    logger.info(f"Connected to Supabase at {now_utc.isoformat()}")

    # 1. Keep-alive ping — this is the part that must succeed
    try:
        res = supabase.table("alerts").select("*", count="exact").limit(1).execute()
        logger.info(f"[Keep-Alive] Ping successful. alerts row count: {res.count}")
    except Exception as e:
        logger.error(f"[Keep-Alive] Ping failed: {e}")
        return False

    # 2. Retention cleanup — failures here are logged but don't fail the run
    cutoff_iso = (now_utc - timedelta(days=RETENTION_DAYS)).isoformat()
    logger.info(f"[Retention] Deleting rows older than {cutoff_iso}")

    try:
        supabase.table("alerts").delete().lt("created_at", cutoff_iso).eq("is_active", False).execute()
        logger.info("[Retention] Purged inactive alerts older than 7 days.")
    except Exception as e:
        logger.warning(f"[Retention] Alerts cleanup note: {e}")

    try:
        supabase.table("predictions").delete().lt("created_at", cutoff_iso).execute()
        logger.info("[Retention] Purged predictions older than 7 days.")
    except Exception as e:
        logger.warning(f"[Retention] Predictions cleanup note: {e}")

    try:
        supabase.table("weather_cache").delete().lt("cached_at", cutoff_iso).execute()
        logger.info("[Retention] Purged weather_cache entries older than 7 days.")
    except Exception as e:
        logger.warning(f"[Retention] Weather cache cleanup note: {e}")

    logger.info("Supabase maintenance completed successfully.")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_supabase_maintenance() else 1)
