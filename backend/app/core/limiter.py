"""Rate limiter configuration and secure trusted proxy client IP extraction."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import settings


def get_real_client_ip(request: Request) -> str:
    """
    Extract client IP address securely without trusting client-spoofable headers.
    - CF-Connecting-IP is ONLY trusted if TRUSTED_PROXY == 'cloudflare'.
    - X-Forwarded-For is parsed from the RIGHT according to TRUSTED_PROXY_HOPS (never leftmost client-controlled IP).
    - Falls back to request.client.host.
    """
    # 1. Cloudflare header only when explicitly configured
    if getattr(settings, "TRUSTED_PROXY", "").lower() == "cloudflare":
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()

    # 2. X-Forwarded-For: extract the IP appended by our trusted proxy
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        ips = [ip.strip() for ip in x_forwarded_for.split(",") if ip.strip()]
        hops = getattr(settings, "TRUSTED_PROXY_HOPS", 1)
        if len(ips) >= hops and hops > 0:
            return ips[-hops]

    # 3. Direct socket peer fallback
    if request.client and request.client.host:
        return request.client.host

    return get_remote_address(request) or "127.0.0.1"


limiter = Limiter(key_func=get_real_client_ip, default_limits=[])
