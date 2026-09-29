"""Authentication and role-based authorization dependencies using Supabase Auth with algorithm pinning and JWKS prefetching."""

import asyncio
import logging
import secrets
from typing import Any, Callable, Dict, List, Optional
import jwt
from jwt import PyJWKClient, PyJWKClientError
from fastapi import Depends, Header, HTTPException, status
from app.config import settings

logger = logging.getLogger("vajranowcast.auth")

# Global PyJWKClient instance
_jwks_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json" if settings.SUPABASE_URL else ""
_jwk_client: Optional[PyJWKClient] = None

if _jwks_url:
    try:
        _jwk_client = PyJWKClient(_jwks_url, cache_keys=True, lifespan=3600)
    except Exception as e:
        logger.warning(f"Could not initialize PyJWKClient for {_jwks_url}: {e}")


async def init_jwks():
    """Prefetch JWKS public keys at application startup without blocking the event loop."""
    if _jwk_client is not None:
        try:
            logger.info("Prefetching Supabase JWKS signing keys...")
            await asyncio.to_thread(_jwk_client.get_jwk_set)
            logger.info("Supabase JWKS signing keys prefetched and cached successfully.")
        except Exception as e:
            logger.warning(f"Could not prefetch JWKS keys during startup: {e}")


def _verify_jwt_token_sync(token: str) -> Dict[str, Any]:
    """
    Synchronous helper to verify Supabase JWT tokens with strict algorithm and key pinning.
    Prevents algorithm confusion attacks and rejects alg=none.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed or invalid authorization token header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = unverified_header.get("alg")
    kid = unverified_header.get("kid")

    # 1. Explicitly reject alg=none or missing algorithm
    if not alg or alg.lower() == "none":
        logger.warning("Rejected token with 'none' algorithm.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token algorithm 'none' is explicitly rejected.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Asymmetric JWKS path: Required whenever kid is present
    if kid and _jwk_client is not None:
        # Enforce that kid-based tokens MUST use asymmetric algorithms (ES256, RS256)
        if alg not in ["ES256", "RS256"]:
            logger.warning(f"Rejected token: kid '{kid}' cannot be used with symmetric algorithm '{alg}'.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Algorithm '{alg}' is not permitted for JWKS key verification.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            signing_key = _jwk_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
                options={"verify_aud": True, "verify_exp": True},
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (jwt.InvalidTokenError, PyJWKClientError) as e:
            logger.warning(f"Asymmetric JWT validation failed: {type(e).__name__}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or untrusted authorization token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 3. Symmetric HS256 path: Allowed ONLY when SUPABASE_JWT_SECRET is set AND token has NO kid
    if alg == "HS256":
        if kid:
            # Prevent key-confusion where an attacker crafts HS256 with a JWKS kid
            logger.warning("Rejected HS256 token presenting a JWKS kid (potential key confusion attack).")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Symmetric HS256 algorithm cannot be used with a JWKS key ID.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        secret = settings.SUPABASE_JWT_SECRET
        if not secret:
            logger.error("Received HS256 token but SUPABASE_JWT_SECRET is not configured in backend.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token validation configuration error.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_aud": True, "verify_exp": True},
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"HS256 JWT signature verification failed: {type(e).__name__}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization token signature.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Unsupported or unauthorized token algorithm: {alg}",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> Dict[str, Any]:
    """
    FastAPI dependency to authenticate requests without blocking the event loop.
    Accepts Supabase Bearer JWT tokens or valid X-Admin-Token machine secret.
    Extracts role strictly from app_metadata.role.
    """
    # Check for machine service token first using constant-time comparison
    if x_admin_token and settings.ADMIN_TOKEN:
        if secrets.compare_digest(x_admin_token, settings.ADMIN_TOKEN):
            return {
                "sub": "service-machine",
                "email": "system@vajranowcast.internal",
                "role": "admin",
                "app_metadata": {"role": "admin"},
                "is_machine": True,
            }
        else:
            logger.warning("Invalid X-Admin-Token attempted.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid service credentials.",
            )

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    claims = await asyncio.to_thread(_verify_jwt_token_sync, token)

    # Read role ONLY from app_metadata (cannot be edited by user)
    app_meta = claims.get("app_metadata", {})
    role = app_meta.get("role", "authenticated") if isinstance(app_meta, dict) else "authenticated"

    return {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "role": role,
        "app_metadata": app_meta,
        "user_metadata": claims.get("user_metadata", {}),
        "is_machine": False,
    }


def require_role(allowed_roles: List[str]) -> Callable:
    """
    Factory creating a dependency that enforces required user roles (e.g. 'meteorologist', 'admin').
    """
    async def _role_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = user.get("role", "")
        # Admin supersedes all roles
        if user_role == "admin" or user_role in allowed_roles:
            return user

        logger.warning(f"Access forbidden: User {user.get('sub')} with role '{user_role}' requires {allowed_roles}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access forbidden. Required role: {', '.join(allowed_roles)}.",
        )

    return _role_checker
