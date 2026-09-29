"""API Quota tracker and rate guard enforcing per-location and variable-weighted Open-Meteo free-tier compliance."""

import logging
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger("vajranowcast.quota")


class OpenMeteoQuotaGuard:
    """
    In-memory rolling quota tracker conforming strictly to Open-Meteo API credit accounting:
    1. Multi-location requests count as N calls (1 per coordinate).
    2. Variable weighting: Requests requesting >10 hourly variables count as ceil(vars / 10) call credits per location.
    3. Daily free-tier threshold: 10,000 credits/day, hourly threshold: 5,000 credits/hr.
    """

    def __init__(
        self,
        max_daily_calls: int = 9000,
        max_hourly_calls: int = 4500,
        max_minute_calls: int = 500,
    ):
        self.max_daily_calls = max_daily_calls
        self.max_hourly_calls = max_hourly_calls
        self.max_minute_calls = max_minute_calls

        self._call_timestamps: list[float] = []
        self._daily_count: int = 0
        self._last_day_reset: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _cleanup_old_timestamps(self, now: float) -> None:
        """Remove timestamps older than 1 hour and reset daily counters at UTC midnight."""
        current_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if current_day != self._last_day_reset:
            self._daily_count = 0
            self._last_day_reset = current_day

        one_hour_ago = now - 3600.0
        self._call_timestamps = [t for t in self._call_timestamps if t > one_hour_ago]

    def can_make_request(
        self,
        num_locations: int = 1,
        num_variables: int = 12,
        batch_weight: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Check if an outgoing request is within quota limits using location and variable multipliers.
        Weight = batch_weight if provided else num_locations * ceil(num_variables / 10).
        """
        if batch_weight is not None:
            weight = batch_weight
        else:
            weight = num_locations * (2 if num_variables > 10 else 1)
        now = time.time()
        self._cleanup_old_timestamps(now)

        if self._daily_count + weight > self.max_daily_calls:
            return False, f"Daily quota limit reached ({self._daily_count}/{self.max_daily_calls} credits)"

        one_minute_ago = now - 60.0
        minute_calls = sum(1 for t in self._call_timestamps if t > one_minute_ago)
        if minute_calls + weight > self.max_minute_calls:
            return False, f"Per-minute rate limit reached ({minute_calls}/{self.max_minute_calls} credits)"

        if len(self._call_timestamps) + weight > self.max_hourly_calls:
            return False, f"Hourly quota limit reached ({len(self._call_timestamps)}/{self.max_hourly_calls} credits)"

        return True, "OK"

    def record_request(
        self,
        num_locations: int = 1,
        num_variables: int = 12,
        batch_weight: Optional[int] = None,
    ) -> None:
        """Record consumption of credits calculated per location and variable weight."""
        if batch_weight is not None:
            weight = batch_weight
        else:
            weight = num_locations * (2 if num_variables > 10 else 1)
        now = time.time()
        self._cleanup_old_timestamps(now)
        for _ in range(weight):
            self._call_timestamps.append(now)
        self._daily_count += weight

    def get_status(self) -> dict:
        """Return current quota utilization statistics."""
        now = time.time()
        self._cleanup_old_timestamps(now)
        one_minute_ago = now - 60.0
        minute_calls = sum(1 for t in self._call_timestamps if t > one_minute_ago)
        return {
            "daily_credits_used": self._daily_count,
            "daily_credits_limit": self.max_daily_calls,
            "hourly_credits_used": len(self._call_timestamps),
            "hourly_credits_limit": self.max_hourly_calls,
            "minute_credits_used": minute_calls,
            "minute_credits_limit": self.max_minute_calls,
        }

    def reset(self) -> None:
        """Reset all counters."""
        self._call_timestamps.clear()
        self._daily_count = 0


# Global singleton instance
quota_guard = OpenMeteoQuotaGuard()
