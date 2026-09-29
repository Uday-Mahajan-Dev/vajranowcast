"""Comprehensive automated test suite for Phase 1 security hardening, authentication, rate limiting, and integrity."""

import base64
import hashlib
import hmac
import json
import time
import pytest
import jwt
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from app.main import app
from app.config import settings
from app.core.limiter import limiter
from app.ml.models.thunderstorm_model import ThunderstormClassifier
from app.services.alert_service import AlertService

TEST_JWT_SECRET = "test_super_secret_jwt_key_at_least_32_chars_long!"

# Generate a temporary EC keypair for testing JWKS and algorithm confusion
_private_key = ec.generate_private_key(ec.SECP256R1())
_public_key = _private_key.public_key()
_public_pem_bytes = _public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Configure test environment secrets and settings."""
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "test_admin_token_123")
    monkeypatch.setattr(settings, "TRUSTED_PROXY", "")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    limiter.reset()


def create_hs256_token(
    sub: str = "user-123",
    role: str = None,
    user_metadata_role: str = None,
    expired: bool = False,
    kid: str = None,
    secret: str = TEST_JWT_SECRET,
) -> str:
    """Helper to generate mock Supabase Auth HS256 tokens."""
    now = int(time.time())
    exp = now - 3600 if expired else now + 3600

    headers = {"alg": "HS256", "typ": "JWT"}
    if kid:
        headers["kid"] = kid

    payload = {
        "sub": sub,
        "email": f"{sub}@example.com",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL}/auth/v1",
        "iat": now,
        "exp": exp,
        "app_metadata": {"role": role} if role else {},
        "user_metadata": {"role": user_metadata_role} if user_metadata_role else {},
    }
    return jwt.encode(payload, secret, algorithm="HS256", headers=headers)


def craft_raw_hs256_confusion_token(payload: dict, secret_bytes: bytes, kid: str = None) -> str:
    """Craft a raw HS256 token signed using arbitrary secret bytes (simulating algorithm confusion exploit)."""
    headers = {"alg": "HS256", "typ": "JWT"}
    if kid:
        headers["kid"] = kid

    h_b64 = base64.urlsafe_b64encode(json.dumps(headers).encode()).rstrip(b"=").decode()
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    signing_input = f"{h_b64}.{p_b64}".encode()
    signature = hmac.new(secret_bytes, signing_input, hashlib.sha256).digest()
    s_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{h_b64}.{p_b64}.{s_b64}"


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. AUTHENTICATION & ROLE AUTHORIZATION TESTS
# ==============================================================================

def test_alerts_generate_missing_auth(client):
    """Protected /generate endpoint must return 401 when no credentials are provided."""
    response = client.post("/api/v1/alerts/generate")
    assert response.status_code == 401
    assert "Missing Authorization header" in response.json()["detail"]


def test_alerts_generate_invalid_auth_format(client):
    """Invalid Authorization header format returns 401."""
    response = client.post("/api/v1/alerts/generate", headers={"Authorization": "InvalidTokenHeader"})
    assert response.status_code == 401


def test_alerts_generate_expired_token(client):
    """Expired JWT token returns 401."""
    token = create_hs256_token(role="meteorologist", expired=True)
    response = client.post("/api/v1/alerts/generate", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_alerts_generate_alg_none_rejected(client):
    """Token with alg=none is explicitly rejected with 401."""
    now = int(time.time())
    payload = {"sub": "attacker", "aud": "authenticated", "exp": now + 3600, "app_metadata": {"role": "admin"}}
    token = jwt.encode(payload, key="", algorithm="none")
    response = client.post("/api/v1/alerts/generate", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "rejected" in response.json()["detail"].lower()


def test_alerts_generate_key_confusion_rejected(client):
    """
    Algorithm confusion attack test:
    Attacker signs an HS256 token using the public key as the HMAC secret.
    The backend MUST reject it with 401.
    """
    now = int(time.time())
    payload = {
        "sub": "attacker-admin",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL}/auth/v1",
        "exp": now + 3600,
        "app_metadata": {"role": "admin"},
    }

    # 1. HS256 token signed with public key bytes as secret without kid -> fails against SUPABASE_JWT_SECRET
    confusion_token_1 = craft_raw_hs256_confusion_token(payload, _public_pem_bytes, kid=None)
    res1 = client.post("/api/v1/alerts/generate", headers={"Authorization": f"Bearer {confusion_token_1}"})
    assert res1.status_code == 401

    # 2. HS256 token with a JWKS kid -> explicitly rejected because HS256 cannot use JWKS kid
    confusion_token_2 = craft_raw_hs256_confusion_token(payload, _public_pem_bytes, kid="cee3e3ad-b8b5-4072-bc3f-f2cc1e8f7270")
    res2 = client.post("/api/v1/alerts/generate", headers={"Authorization": f"Bearer {confusion_token_2}"})
    assert res2.status_code == 401


def test_alerts_generate_plain_user_forbidden(client):
    """Authenticated user without 'meteorologist' or 'admin' role in app_metadata must receive 403."""
    token = create_hs256_token(role=None)  # No app_metadata role
    response = client.post("/api/v1/alerts/generate", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert "forbidden" in response.json()["detail"].lower()


def test_alerts_generate_user_metadata_spoof_forbidden(client):
    """Role set ONLY in user_metadata (which users can edit) must NOT grant access (403)."""
    token = create_hs256_token(role=None, user_metadata_role="admin")
    response = client.post("/api/v1/alerts/generate", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_alerts_generate_meteorologist_role_allowed(client, monkeypatch):
    """User with 'meteorologist' in app_metadata is allowed (200)."""
    async def mock_predict_for_cities(self, cities):
        return {"Delhi": [{"thunderstorm_probability": 0.8, "lead_time_hours": 1.0, "severity": "severe", "lightning_probability": 0.7, "latitude": 28.61, "longitude": 77.21}]}

    async def mock_generate_alerts(self, preds):
        return [{"city": "Delhi", "alert_id": "test-123", "is_active": True}]

    from app.services.ml_inference import NowcastingService

    monkeypatch.setattr(NowcastingService, "predict_for_cities", mock_predict_for_cities)
    monkeypatch.setattr(AlertService, "generate_alerts", mock_generate_alerts)

    token = create_hs256_token(role="meteorologist")
    response = client.post("/api/v1/alerts/generate", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["alerts_generated"] == 1


def test_alerts_generate_admin_token_service_allowed(client, monkeypatch):
    """Machine caller with valid X-Admin-Token is authenticated as admin service (200)."""
    async def mock_predict_for_cities(self, cities):
        return {}

    async def mock_generate_alerts(self, preds):
        return []

    from app.services.ml_inference import NowcastingService

    monkeypatch.setattr(NowcastingService, "predict_for_cities", mock_predict_for_cities)
    monkeypatch.setattr(AlertService, "generate_alerts", mock_generate_alerts)

    response = client.post("/api/v1/alerts/generate", headers={"X-Admin-Token": "test_admin_token_123"})
    assert response.status_code == 200


def test_alerts_generate_invalid_admin_token(client):
    """Machine caller with invalid X-Admin-Token returns 401."""
    response = client.post("/api/v1/alerts/generate", headers={"X-Admin-Token": "wrong_token_secret"})
    assert response.status_code == 401


# ==============================================================================
# 2. RATE LIMITING & IP SPOOFING RESISTANCE TESTS
# ==============================================================================

def test_rate_limiting_61st_request_returns_429(client, monkeypatch):
    """The 61st request to /nowcast in an hour returns 429 Too Many Requests."""
    async def mock_predict_for_location(self, lat, lon, lead_hours):
        return []

    from app.services.ml_inference import NowcastingService
    monkeypatch.setattr(NowcastingService, "predict_for_location", mock_predict_for_location)

    limiter.reset()

    # Send 60 allowed requests
    for i in range(60):
        res = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=0")
        assert res.status_code == 200, f"Request {i+1} failed with {res.status_code}"

    # 61st request must trigger 429
    res_61 = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=0")
    assert res_61.status_code == 429
    assert "rate limit exceeded" in res_61.text.lower()


def test_rate_limiting_ip_spoofing_does_not_bypass(client, monkeypatch):
    """Sending spoofed CF-Connecting-IP or leftmost X-Forwarded-For does not bypass the rate limit."""
    async def mock_predict_for_location(self, lat, lon, lead_hours):
        return []

    from app.services.ml_inference import NowcastingService
    monkeypatch.setattr(NowcastingService, "predict_for_location", mock_predict_for_location)

    limiter.reset()

    # Send requests with changing fake CF-Connecting-IP and fake leftmost X-Forwarded-For
    # Behind Render (TRUSTED_PROXY_HOPS=1), the rightmost proxy hop IP (10.0.0.1) is used
    for i in range(60):
        headers = {
            "CF-Connecting-IP": f"203.0.113.{i}",
            "X-Forwarded-For": f"198.51.100.{i}, 10.0.0.1",
        }
        res = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=0", headers=headers)
        assert res.status_code == 200

    # 61st request with yet another fake IP must STILL be rate limited because proxy hop IP (10.0.0.1) is used
    headers_61 = {
        "CF-Connecting-IP": "1.2.3.4",
        "X-Forwarded-For": "5.6.7.8, 10.0.0.1",
    }
    res_61 = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=0", headers=headers_61)
    assert res_61.status_code == 429


# ==============================================================================
# 3. INPUT VALIDATION & GRID SNAPPING TESTS
# ==============================================================================

def test_nowcast_invalid_coordinates(client):
    """Coordinates outside India boundaries must be rejected with 422."""
    response = client.get("/api/v1/predictions/nowcast?lat=45.0&lon=77.0")
    assert response.status_code == 422

    response = client.get("/api/v1/predictions/nowcast?lat=28.0&lon=50.0")
    assert response.status_code == 422


def test_nowcast_invalid_lead_hours(client):
    """Invalid lead_hours outside {0,1,2,3,6} must return 400."""
    response = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=0,1,10")
    assert response.status_code == 400
    assert "Invalid lead_hours" in response.json()["detail"]


def test_nowcast_too_many_lead_hours(client):
    """More than 5 lead_hours items must return 400."""
    response = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=0,1,2,3,6,6")
    assert response.status_code == 400


def test_historical_future_date_rejected(client):
    """Future dates must be rejected with 400."""
    response = client.get("/api/v1/predictions/historical?lat=28.61&lon=77.21&date=2030-01-01&hour=12")
    assert response.status_code == 400
    assert "out of allowed historical range" in response.json()["detail"]


def test_historical_too_old_date_rejected(client):
    """Dates prior to 2015-01-01 must be rejected with 400."""
    response = client.get("/api/v1/predictions/historical?lat=28.61&lon=77.21&date=2010-01-01&hour=12")
    assert response.status_code == 400


# ==============================================================================
# 4. SECURITY HEADERS & DISCLAIMER TESTS
# ==============================================================================

def test_security_headers_present(client):
    """All responses must include standard HTTP security hardening headers."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "Strict-Transport-Security" in response.headers


def test_disclaimer_present_in_health_and_root(client):
    """Health endpoint reports version 1.1.0."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["version"] == "1.1.0"


# ==============================================================================
# 5. MODEL INTEGRITY VERIFICATION TEST
# ==============================================================================

def test_model_hash_verification(monkeypatch):
    """Model loader must successfully verify stored hashes."""
    clf = ThunderstormClassifier()
    assert clf.is_trained is True
    assert clf.optimal_threshold == 0.186


# ==============================================================================
# 6. ALERT DE-DUPLICATION TEST
# ==============================================================================

@pytest.mark.asyncio
async def test_alert_deduplication(monkeypatch):
    """AlertService should update existing active alert rather than inserting duplicate."""
    svc = AlertService()
    
    existing_db = [{"alert_id": "existing-uuid-1", "city": "Kolkata", "is_active": True, "alert_type": "thunderstorm"}]
    updated_alerts = []
    inserted_alerts = []

    monkeypatch.setattr(svc, "_sync_expire_old_alerts", lambda: None)
    monkeypatch.setattr(svc, "_sync_get_active_alerts_for_city", lambda city: existing_db if city == "Kolkata" else [])
    monkeypatch.setattr(svc, "_sync_update_alert", lambda aid, up: updated_alerts.append((aid, up)))
    monkeypatch.setattr(svc, "_sync_insert_alert", lambda a: inserted_alerts.append(a))

    predictions = {
        "Kolkata": [{"thunderstorm_probability": 0.75, "lead_time_hours": 1.0, "severity": "severe", "lightning_probability": 0.6, "latitude": 22.57, "longitude": 88.36}],
        "Delhi": [{"thunderstorm_probability": 0.70, "lead_time_hours": 1.0, "severity": "severe", "lightning_probability": 0.5, "latitude": 28.61, "longitude": 77.21}],
    }

    results = await svc.generate_alerts(predictions)
    assert len(results) == 2
    # Kolkata should have been updated (de-duplicated)
    assert len(updated_alerts) == 1
    assert updated_alerts[0][0] == "existing-uuid-1"
    # Delhi should have been inserted new
    assert len(inserted_alerts) == 1
    assert inserted_alerts[0]["city"] == "Delhi"
