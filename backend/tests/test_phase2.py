"""Comprehensive automated test suite for Phase 2: Caching, Batching, Precomputed Grid, and Free-Tier Optimization."""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.core.cache import meteo_cache, snap_to_grid, MAX_STALE_AGE_SECONDS
from app.core.limiter import limiter
from app.core.quota import quota_guard
from app.main import app
from scripts.supabase_maintenance import run_supabase_maintenance
from app.services.data_ingestion import OpenMeteoService
from app.services.feature_engineering import FeatureEngineer

# Generate 72 rolling hourly timestamps centered around current time
_base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
MOCK_HOURLY_TIMES = [
    (_base_time + timedelta(hours=h - 24)).strftime("%Y-%m-%dT%H:00")
    for h in range(72)
]

MOCK_OPEN_METEO_PAYLOAD = {
    "latitude": 28.5,
    "longitude": 77.25,
    "utc_offset_seconds": 19800,
    "timezone": "Asia/Kolkata",
    "current": {
        "temperature_2m": 32.5,
        "relative_humidity_2m": 65.0,
        "dew_point_2m": 24.5,
        "surface_pressure": 1002.1,
        "wind_speed_10m": 5.2,
        "wind_direction_10m": 120,
        "cloud_cover": 75,
        "precipitation": 0.0,
        "weather_code": 2,
    },
    "hourly": {
        "time": MOCK_HOURLY_TIMES,
        "temperature_2m": [30.0 + (h % 5) for h in range(72)],
        "relative_humidity_2m": [60.0 + (h % 20) for h in range(72)],
        "dew_point_2m": [22.0 + (h % 3) for h in range(72)],
        "surface_pressure": [1000.0 + (h % 5) for h in range(72)],
        "wind_speed_10m": [4.0 + (h % 6) for h in range(72)],
        "wind_direction_10m": [90 + (h * 5) % 360 for h in range(72)],
        "cloud_cover": [50 + (h % 40) for h in range(72)],
        "precipitation": [0.0] * 72,
        "precipitation_probability": [10] * 72,
        "cape": [2200.0] * 72,
        "convective_inhibition": [-25.0] * 72,
        "total_column_integrated_water_vapour": [52.0] * 72,
        "weather_code": [1] * 72,
    },
}


@pytest.fixture(autouse=True)
def reset_caches():
    """Reset in-memory cache and quota guard before each test."""
    meteo_cache.clear()
    quota_guard.reset()
    limiter.reset()


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. TTL CACHING & 0.25° SNAPPING TESTS
# ==============================================================================

def test_coordinate_snapping_025_degrees():
    """Verify coordinate snapping rounds to the nearest 0.25 degree step."""
    assert snap_to_grid(28.61, 0.25) == 28.5
    assert snap_to_grid(28.66, 0.25) == 28.75
    assert snap_to_grid(77.21, 0.25) == 77.25


@pytest.mark.asyncio
async def test_weather_ttl_cache_prevents_duplicate_http_calls(monkeypatch):
    """Subsequent calls within 15-minute TTL must hit cache without issuing HTTP requests."""
    service = OpenMeteoService()
    call_count = 0

    async def mock_get(self, url, params=None):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=MOCK_OPEN_METEO_PAYLOAD, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    # First fetch (cache miss -> 1 HTTP call)
    data1, is_stale1, cached_at1, _ = await service.fetch_current_weather(28.5, 77.25)
    assert call_count == 1
    assert is_stale1 is False

    # Second fetch for exact same coordinates (cache hit -> 0 HTTP calls)
    data2, is_stale2, cached_at2, _ = await service.fetch_current_weather(28.5, 77.25)
    assert call_count == 1
    assert is_stale2 is False
    assert data1["current"]["temperature_2m"] == data2["current"]["temperature_2m"]

    # Third fetch for nearby coordinates snapped to same 0.25 node (28.52, 77.24 -> 28.5, 77.25)
    data3, is_stale3, _, _ = await service.fetch_current_weather(28.52, 77.24)
    assert call_count == 1
    assert is_stale3 is False


# ==============================================================================
# 2. SINGLE BATCHED CITIES REQUEST TEST
# ==============================================================================

@pytest.mark.asyncio
async def test_cities_nowcast_single_batched_http_call(monkeypatch):
    """Querying 10 metro cities must issue exactly ONE batched HTTP request to Open-Meteo."""
    service = OpenMeteoService()
    http_calls = []

    mock_batch_response = [
        {**MOCK_OPEN_METEO_PAYLOAD, "latitude": 28.5, "longitude": 77.25},
        {**MOCK_OPEN_METEO_PAYLOAD, "latitude": 19.0, "longitude": 73.0},
    ]

    async def mock_get(self, url, params=None):
        http_calls.append(params)
        return httpx.Response(200, json=mock_batch_response, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    test_cities = [
        {"name": "Delhi", "lat": 28.61, "lon": 77.21},
        {"name": "Mumbai", "lat": 19.08, "lon": 72.88},
    ]

    results, is_stale, _, _ = await service.fetch_multiple_cities(test_cities)

    # Verify only 1 network call was made
    assert len(http_calls) == 1
    assert len(results) == 2
    assert results[0]["city"] == "Delhi"
    assert results[1]["city"] == "Mumbai"


# ==============================================================================
# 3. QUOTA GUARD, PER-LOCATION WEIGHTING & 3-HOUR MAX STALE CUTOFF
# ==============================================================================

def test_quota_guard_location_and_variable_weighting():
    """Quota guard must apply ceil(vars / 10) multiplier per location."""
    # 1 location with 12 variables = 2 credits
    allowed, _ = quota_guard.can_make_request(num_locations=1, num_variables=12)
    assert allowed is True
    quota_guard.record_request(num_locations=1, num_variables=12)
    assert quota_guard._daily_count == 2

    # Batch of 10 locations with 12 variables = 20 credits
    quota_guard.record_request(num_locations=10, num_variables=12)
    assert quota_guard._daily_count == 22


@pytest.mark.asyncio
async def test_quota_guard_fallback_to_stale_data(monkeypatch):
    """When quota is reached or upstream returns 429, return cached data marked stale: true."""
    service = OpenMeteoService()

    # Pre-populate cache
    meteo_cache.set_weather(28.5, 77.25, MOCK_OPEN_METEO_PAYLOAD)

    # Exhaust quota artificially
    quota_guard._daily_count = 9500

    data, is_stale, cached_at, stale_reason = await service.fetch_current_weather(28.5, 77.25, force_refresh=True)
    assert is_stale is True
    assert "Quota guard active" in stale_reason
    assert data["current"]["temperature_2m"] == 32.5


@pytest.mark.asyncio
async def test_upstream_429_returns_stale_cache(monkeypatch):
    """When upstream returns HTTP 429, fall back to stale cache with descriptive reason."""
    service = OpenMeteoService()
    meteo_cache.set_weather(28.5, 77.25, MOCK_OPEN_METEO_PAYLOAD)

    async def mock_get_429(self, url, params=None):
        return httpx.Response(429, text="Rate limit exceeded", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_429)

    data, is_stale, cached_at, stale_reason = await service.fetch_current_weather(28.5, 77.25, force_refresh=True)
    assert is_stale is True
    assert "429" in stale_reason


def test_stale_data_expired_after_3_hours():
    """Stale cache must NOT return data older than 3 hours (10,800 seconds)."""
    # Put an expired entry in stale cache (>3 hours old)
    meteo_cache._stale_weather["weather:28.5:77.25"] = {
        "data": MOCK_OPEN_METEO_PAYLOAD,
        "cached_at": datetime.fromtimestamp(time.time() - 11000, tz=timezone.utc),
        "stored_timestamp": time.time() - 11000,
    }

    # Should return None because age > 10800 seconds
    res = meteo_cache.get_weather(28.5, 77.25)
    assert res is None


# ==============================================================================
# 4. PRECOMPUTED GRID & STATIC LAND MASK TESTS
# ==============================================================================

def test_static_india_land_mask_file_exists():
    """Verify static India land mask is committed and contains 70 representative points."""
    mask_file = Path("app/data/india_land_mask.json")
    assert mask_file.exists(), "india_land_mask.json must exist in app/data/"

    with open(mask_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "points" in data
    assert len(data["points"]) == 70
    assert data["resolution_degrees"] > 0
    assert data.get("grid_resolution_km") == 175.0


def test_grid_endpoint_structure_and_metadata(client):
    """GET /api/v1/predictions/grid must return valid GridResponse structure with grid_resolution_km."""
    # Pre-populate in-memory grid cache
    meteo_cache.set_grid({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "valid_until": datetime.now(timezone.utc).isoformat(),
        "lead_time_hours": 1.0,
        "total_points": 2,
        "resolution_deg": 1.6,
        "grid_resolution_km": 175.0,
        "stale": False,
        "points": [
            {
                "latitude": 28.6,
                "longitude": 77.2,
                "thunderstorm_probability": 0.45,
                "severity": "moderate",
                "lightning_probability": 0.40,
                "confidence": 0.85,
                "cape": 1800.0,
                "cin": 20.0,
                "precipitable_water": 45.0,
            }
        ],
    })

    response = client.get("/api/v1/predictions/grid")
    assert response.status_code == 200
    data = response.json()
    assert "generated_at" in data
    assert "valid_until" in data
    assert "grid_resolution_km" in data
    assert data["grid_resolution_km"] == 175.0
    assert data["resolution_deg"] == 1.6
    assert data["total_points"] == 1


# ==============================================================================
# 5. CURATED HISTORICAL REPLAY TESTS
# ==============================================================================

def test_historical_replays_list_endpoint(client):
    """GET /api/v1/predictions/historical/replays must list 4 verified Indian convective events with external URLs."""
    response = client.get("/api/v1/predictions/historical/replays")
    assert response.status_code == 200
    events = response.json()
    assert len(events) >= 4

    for ev in events:
        assert "source_url" in ev
        assert ev["source_url"].startswith("http")
        assert ev["verified_by_human"] is False
        assert ev["computed_verdict"] in ["Hit", "Miss", "False Alarm", "Correct Rejection"]

    event_ids = {e["event_id"] for e in events}
    assert "delhi-record-downpour-20240628" in event_ids
    assert "kolkata-cyclone-remal-20240527" in event_ids
    assert "mumbai-monsoon-squall-20240620" in event_ids
    assert "bengaluru-thunderstorm-20230521" in event_ids


def test_historical_replay_instant_load(client):
    """GET /api/v1/predictions/historical with event_id returns certified event replay."""
    response = client.get(
        "/api/v1/predictions/historical?lat=22.57&lon=88.36&date=2024-05-27&hour=11&event_id=kolkata-cyclone-remal-20240527"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2024-05-27"
    assert data["hour"] == 11
    assert data["actual_was_thunderstorm"] is True


# ==============================================================================
# 6. SUPABASE MAINTENANCE TEST
# ==============================================================================

def test_supabase_maintenance_mocked(monkeypatch):
    """Verify Supabase maintenance executes ping and 7-day retention deletes."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.lt.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])

    from scripts import supabase_maintenance
    monkeypatch.setattr(supabase_maintenance, "get_supabase_admin", lambda: mock_supabase)

    success = supabase_maintenance.run_supabase_maintenance()
    assert success is True
    assert mock_supabase.table.call_count >= 4


# ==============================================================================
# 7. LIVE TESTING FIXES & MODEL SEMANTICS TESTS
# ==============================================================================

def test_lightning_probability_monotonic_scaling():
    """
    Lightning probability must be a monotonic function of P(TS) only (P(LT) = 0.90 * P(TS)).
    Assert: P(TS) = 0.0001 -> lightning < 0.01, regardless of high CAPE.
    """
    from app.ml.models.thunderstorm_model import LightningPredictor

    lt = LightningPredictor()
    assert lt.method == "rule-based heuristic"

    # Low storm probability with extreme CAPE must not inflate lightning probability
    features_extreme_cape = {"cape": 5000.0, "precipitable_water": 70.0}
    lt_prob_low, conf_low = lt.predict(features_extreme_cape, ts_prob=0.0001)
    assert lt_prob_low < 0.01, f"Expected lightning < 0.01 for P(TS)=0.0001, got {lt_prob_low}"
    assert lt_prob_low <= 0.0001

    # Monotonic scaling across probability spectrum
    test_probs = [0.0001, 0.05, 0.186, 0.40, 0.60, 0.85]
    prev_lt = -1.0
    for p in test_probs:
        lt_p, _ = lt.predict({}, ts_prob=p)
        assert lt_p <= p, f"Lightning prob {lt_p} should never exceed TS prob {p}"
        assert lt_p >= prev_lt, "Lightning probability must be monotonically non-decreasing"
        prev_lt = lt_p


def test_severity_classification_depends_only_on_probability():
    """
    Severity bands must be governed strictly by P(TS) thresholds and independent of derived CAPE.
    Thresholds: weak >= 0.1860, moderate >= 0.40, severe >= 0.60, very_severe >= 0.75.
    """
    from app.ml.models.thunderstorm_model import SeverityClassifier

    # High CAPE with low probability must be 'none'
    assert SeverityClassifier.classify(0.10, cape=5000.0) == "none"
    assert SeverityClassifier.classify(0.1859, cape=5000.0) == "none"

    # Threshold crossings
    assert SeverityClassifier.classify(0.1860, cape=0.0) == "weak"
    assert SeverityClassifier.classify(0.35, cape=0.0) == "weak"
    assert SeverityClassifier.classify(0.40, cape=0.0) == "moderate"
    assert SeverityClassifier.classify(0.55, cape=0.0) == "moderate"
    assert SeverityClassifier.classify(0.60, cape=0.0) == "severe"
    assert SeverityClassifier.classify(0.70, cape=0.0) == "severe"
    assert SeverityClassifier.classify(0.75, cape=0.0) == "very_severe"
    assert SeverityClassifier.classify(0.95, cape=0.0) == "very_severe"


def test_nowcast_response_coordinates_and_model_input(client, monkeypatch):
    """
    Response latitude/longitude must match user requested coordinates.
    Snapped coordinates stay strictly in metadata.snapped_coordinates.
    Model feature engineering receives original requested coordinates.
    """
    async def mock_get(self, url, params=None):
        return httpx.Response(200, json=MOCK_OPEN_METEO_PAYLOAD, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    req_lat = 28.61
    req_lon = 77.21
    response = client.get(f"/api/v1/predictions/nowcast?lat={req_lat}&lon={req_lon}&lead_hours=0,1")
    assert response.status_code == 200
    data = response.json()

    # Predictions must contain user's requested coordinates
    for pred in data["predictions"]:
        assert pred["latitude"] == req_lat
        assert pred["longitude"] == req_lon

    # Snapped coordinates reside only in metadata
    assert data["metadata"]["snapped_coordinates"]["latitude"] == 28.5
    assert data["metadata"]["snapped_coordinates"]["longitude"] == 77.25


def test_lead_time_validity_windows_extrapolation_and_confidence_decay(client, monkeypatch):
    """
    Test lead-time semantics:
    - Lead 0: valid now -> now+1h, extrapolated_lead_time: false
    - Lead N (>=1): valid now+Nh -> now+(N+1)h, extrapolated_lead_time: true
    - Confidence decreases monotonically across lead times.
    """
    async def mock_get(self, url, params=None):
        return httpx.Response(200, json=MOCK_OPEN_METEO_PAYLOAD, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    response = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=0,1,2,3,6")
    assert response.status_code == 200
    preds = response.json()["predictions"]
    assert len(preds) == 5

    # Lead 0
    p0 = preds[0]
    assert p0["lead_time_hours"] == 0.0
    assert p0["extrapolated_lead_time"] is False
    assert "valid_from" in p0 and "valid_until" in p0
    dt_from_0 = datetime.fromisoformat(p0["valid_from"])
    dt_until_0 = datetime.fromisoformat(p0["valid_until"])
    assert (dt_until_0 - dt_from_0).total_seconds() == 3600

    # Leads 1, 2, 3, 6 must be marked extrapolated_lead_time: true
    for p in preds[1:]:
        assert p["extrapolated_lead_time"] is True
        dt_from = datetime.fromisoformat(p["valid_from"])
        dt_until = datetime.fromisoformat(p["valid_until"])
        assert (dt_until - dt_from).total_seconds() == 3600
        assert "extrapolated lead time" in p["lead_time_note"]

    # Confidence must decrease across lead times (lead 0 factor 1.0 down to lead 6 factor ~0.60)
    confidences = [p["confidence"] for p in preds]
    assert confidences[0] > confidences[-1], f"Expected confidence at lead 0 ({confidences[0]}) > lead 6 ({confidences[-1]})"


def test_public_input_conditions_and_weather_indices(client, monkeypatch):
    """
    Public input_conditions must have renamed derived keys and real surface variables.
    /weather/indices must show NWP CAPE separately labelled as not a model input.
    """
    async def mock_get(self, url, params=None):
        return httpx.Response(200, json=MOCK_OPEN_METEO_PAYLOAD, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    # 1. Test /nowcast input_conditions
    res_nowcast = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=0")
    assert res_nowcast.status_code == 200
    pred0 = res_nowcast.json()["predictions"][0]
    inp = pred0["input_conditions"]

    assert "cape_index_derived" in inp
    assert "cin_index_derived" in inp
    assert "pw_index_derived" in inp
    assert "temperature_2m" in inp
    assert "relative_humidity" in inp
    assert "cloud_cover" in inp
    assert "wind_speed_10m" in inp
    assert "precip_1hr_ago" in inp

    # 2. Test /weather/indices
    res_indices = client.get("/api/v1/weather/indices?lat=28.61&lon=77.21")
    assert res_indices.status_code == 200
    indices_data = res_indices.json()

    derived = indices_data["derived_indices"]
    assert "cape_index_derived" in derived
    assert "cin_index_derived" in derived
    assert "pw_index_derived" in derived
    assert "cape_category" not in derived  # CAPE-based severity categorization removed

    nwp = indices_data["nwp_values"]
    assert "nwp_cape_j_kg (not a model input)" in nwp
    assert nwp["nwp_cape_j_kg (not a model input)"] == 2200.0


def test_model_info_documentation_endpoint(client):
    """GET /api/v1/predictions/model/info must return model architecture and confidence formulas."""
    response = client.get("/api/v1/predictions/model/info")
    assert response.status_code == 200
    data = response.json()

    assert data["optimal_threshold"] == 0.186
    assert "confidence_calibration" in data
    assert "base_confidence_formula" in data["confidence_calibration"]
    assert "lead_time_factor_formula" in data["confidence_calibration"]
    assert "lightning_model" in data
    assert data["lightning_model"]["method"] == "rule-based heuristic"
    assert "severity_bands" in data
    assert len(data["features"]) == 24


# ==============================================================================
# 8. TIMEZONE-AWARE ROW SELECTION & TEMPORAL FEATURE ALIGNMENT TESTS (08:43 UTC -> 14:00 IST)
# ==============================================================================

def test_asia_kolkata_hourly_row_matching_and_lags(client, monkeypatch):
    """
    Test 6a & 6b:
    Fake Open-Meteo response in Asia/Kolkata with distinct temperatures per hour.
    Freeze 'now' at 08:43 UTC (14:13 IST).
    Assert:
    - Lead 0 uses 14:00 IST row (distinct temp), Lead 6 uses 20:00 IST row.
    - hour_sin / hour_cos correspond to 14:00 IST (sin=-0.5, cos=-0.866025).
    - valid_from / valid_until are aligned to 14:00->15:00 IST as UTC (08:30Z -> 09:30Z).
    - input_time_ist is present and equals '2026-09-29T14:00:00+05:30'.
    """
    from datetime import timezone as dt_tz, timedelta as dt_td
    import app.services.ml_inference as ml_inf_mod

    # 48 hours starting yesterday (past_days=1, forecast_days=1)
    # Day 1 (yesterday 2026-09-28): hours 0..23 (temps 100.0..123.0)
    # Day 2 (today 2026-09-29): hours 0..23 (temps 200.0..223.0)
    time_arr = (
        [f"2026-09-28T{h:02d}:00" for h in range(24)] +
        [f"2026-09-29T{h:02d}:00" for h in range(24)]
    )
    temp_arr = [100.0 + h for h in range(24)] + [200.0 + h for h in range(24)]
    rh_arr = [50.0 + (h % 20) for h in range(48)]

    fake_payload = {
        "latitude": 28.61,
        "longitude": 77.21,
        "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "current": {
            "temperature_2m": 214.0,
            "relative_humidity_2m": 60.0,
            "dew_point_2m": 20.0,
            "surface_pressure": 1005.0,
            "wind_speed_10m": 5.0,
            "wind_direction_10m": 120,
            "cloud_cover": 20,
            "precipitation": 0.0,
            "weather_code": 1,
        },
        "hourly": {
            "time": time_arr,
            "temperature_2m": temp_arr,
            "relative_humidity_2m": rh_arr,
            "dew_point_2m": [18.0] * 48,
            "surface_pressure": [1005.0] * 48,
            "wind_speed_10m": [6.0] * 48,
            "wind_direction_10m": [100] * 48,
            "cloud_cover": [25] * 48,
            "precipitation": [0.0] * 48,
            "precipitation_probability": [5] * 48,
            "cape": [1500.0] * 48,
            "convective_inhibition": [-10.0] * 48,
            "total_column_integrated_water_vapour": [40.0] * 48,
            "weather_code": [1] * 48,
        },
    }

    async def mock_get(self, url, params=None):
        return httpx.Response(200, json=fake_payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    # Freeze now at 2026-09-29 08:43:00 UTC (= 14:13:00 IST)
    frozen_utc = datetime(2026, 9, 29, 8, 43, 0, tzinfo=dt_tz.utc)

    # Monkeypatch datetime.now in NowcastingService
    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return frozen_utc.astimezone(tz)
            return frozen_utc

    monkeypatch.setattr(ml_inf_mod, "datetime", MockDatetime)

    response = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=0,1,6")
    assert response.status_code == 200
    data = response.json()
    preds = data["predictions"]

    # 1. Lead 0 checks: must pick 14:00 IST row
    p0 = preds[0]
    assert p0["lead_time_hours"] == 0.0
    assert p0["input_time_ist"] == "2026-09-29T14:00:00+05:30"
    assert p0["input_conditions"]["temperature_2m"] == 214.0  # 200 + 14
    assert p0["extrapolated_lead_time"] is False

    # Check valid_from / valid_until aligned to 14:00 -> 15:00 IST as UTC
    dt_from_0 = datetime.fromisoformat(p0["valid_from"])
    dt_until_0 = datetime.fromisoformat(p0["valid_until"])
    assert dt_from_0.hour == 8 and dt_from_0.minute == 30  # 14:00 IST in UTC is 08:30
    assert dt_until_0.hour == 9 and dt_until_0.minute == 30  # 15:00 IST in UTC is 09:30

    # 2. Lead 6 checks: must pick 20:00 IST row
    p6 = preds[2]
    assert p6["lead_time_hours"] == 6.0
    assert p6["input_time_ist"] == "2026-09-29T20:00:00+05:30"
    assert p6["input_conditions"]["temperature_2m"] == 220.0  # 200 + 20
    assert p6["extrapolated_lead_time"] is True
    dt_from_6 = datetime.fromisoformat(p6["valid_from"])
    assert dt_from_6.hour == 14 and dt_from_6.minute == 30  # 20:00 IST in UTC is 14:30

    # 3. Verify temporal features (hour_sin, hour_cos) for 14:00 IST
    fe = ml_inf_mod.FeatureEngineer()
    feats, dt_ist = fe.build_feature_vector(fake_payload, 28.61, 77.21, frozen_utc, target_hour_index=0)
    expected_hour_sin = np.sin(2.0 * np.pi * 14.0 / 24.0)
    expected_hour_cos = np.cos(2.0 * np.pi * 14.0 / 24.0)
    assert abs(feats["hour_sin"] - expected_hour_sin) < 1e-5
    assert abs(feats["hour_cos"] - expected_hour_cos) < 1e-5
    assert abs(feats["hour_sin"] - (-0.5)) < 1e-5
    assert abs(feats["hour_cos"] - (-0.8660254)) < 1e-5


def test_cities_multi_location_response_timezone_matching(client, monkeypatch):
    """
    Test 6c:
    Multi-location cities response must match the 14:00 IST row when called at 08:43 UTC.
    """
    from datetime import timezone as dt_tz
    import app.services.ml_inference as ml_inf_mod

    time_arr = (
        [f"2026-09-28T{h:02d}:00" for h in range(24)] +
        [f"2026-09-29T{h:02d}:00" for h in range(24)]
    )
    temp_arr = [100.0 + h for h in range(24)] + [200.0 + h for h in range(24)]

    fake_city_weather = {
        "latitude": 28.5,
        "longitude": 77.25,
        "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "current": {"temperature_2m": 214.0, "weather_code": 1},
        "hourly": {
            "time": time_arr,
            "temperature_2m": temp_arr,
            "relative_humidity_2m": [60.0] * 48,
            "dew_point_2m": [18.0] * 48,
            "surface_pressure": [1005.0] * 48,
            "wind_speed_10m": [6.0] * 48,
            "wind_direction_10m": [100] * 48,
            "cloud_cover": [25] * 48,
            "precipitation": [0.0] * 48,
            "precipitation_probability": [5] * 48,
            "cape": [1500.0] * 48,
            "convective_inhibition": [-10.0] * 48,
            "total_column_integrated_water_vapour": [40.0] * 48,
            "weather_code": [1] * 48,
        },
    }

    mock_batch = [fake_city_weather] * 10

    async def mock_get(self, url, params=None):
        return httpx.Response(200, json=mock_batch, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    frozen_utc = datetime(2026, 9, 29, 8, 43, 0, tzinfo=dt_tz.utc)

    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return frozen_utc.astimezone(tz)
            return frozen_utc

    monkeypatch.setattr(ml_inf_mod, "datetime", MockDatetime)

    response = client.get("/api/v1/predictions/nowcast/cities")
    assert response.status_code == 200
    data = response.json()
    assert "cities" in data

    for city_name, city_preds in data["cities"].items():
        assert len(city_preds) == 5
        lead0 = city_preds[0]
        assert lead0["input_time_ist"] == "2026-09-29T14:00:00+05:30"
        assert lead0["input_conditions"]["temperature_2m"] == 214.0
        lead6 = city_preds[4]
        assert lead6["input_time_ist"] == "2026-09-29T20:00:00+05:30"
        assert lead6["input_conditions"]["temperature_2m"] == 220.0


def test_alert_tiers_classification_and_messages():
    """
    Test 3 alert tiers:
    - WATCH: >= 0.30 (msg: Watch: convective storm conditions developing...)
    - ADVISORY: >= 0.40 (msg: Advisory: heavy rain possible in the next hour...)
    - WARNING: >= 0.60 (msg: Warning: severe convective thunderstorm and heavy rain expected...)
    - Below 0.30: None
    """
    from app.services.alert_service import AlertService
    from app.config import settings

    assert settings.ALERT_TIER_WATCH == 0.30
    assert settings.ALERT_TIER_ADVISORY == 0.40
    assert settings.ALERT_TIER_WARNING == 0.60

    assert AlertService.get_tier_for_probability(0.65) == "warning"
    assert AlertService.get_tier_for_probability(0.60) == "warning"
    assert AlertService.get_tier_for_probability(0.45) == "advisory"
    assert AlertService.get_tier_for_probability(0.40) == "advisory"
    assert AlertService.get_tier_for_probability(0.35) == "watch"
    assert AlertService.get_tier_for_probability(0.30) == "watch"
    assert AlertService.get_tier_for_probability(0.29) is None

    msg_warn = AlertService.build_tier_message("Delhi", "warning", 0.65, 1.0)
    assert "Warning: severe convective thunderstorm" in msg_warn
    assert "(65%)" in msg_warn

    msg_adv = AlertService.build_tier_message("Delhi", "advisory", 0.43, 1.0)
    assert "Advisory: heavy rain possible" in msg_adv
    assert "(43%)" in msg_adv

    msg_watch = AlertService.build_tier_message("Delhi", "watch", 0.34, 1.0)
    assert "Watch: convective storm conditions developing" in msg_watch
    assert "(34%)" in msg_watch


def test_create_test_alert_endpoint_auth(client, monkeypatch):
    """Staff test alert endpoint requires meteorologist or admin role."""
    from app.config import settings

    # 1. Missing auth -> 401
    res = client.post("/api/v1/alerts/test", json={"city": "Delhi", "tier": "warning"})
    assert res.status_code == 401

    # 2. Valid admin token -> 200
    res_admin = client.post(
        "/api/v1/alerts/test",
        json={"city": "Delhi", "tier": "warning", "lead_time_hours": 1.0},
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
    )
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert "alert" in data
    assert data["alert"]["is_test"] is True
    assert data["alert"]["tier"] == "warning"
    assert data["alert"]["city"] == "Delhi"
    assert "TEST — DRILL" in data["alert"]["message"]


# ==============================================================================
# 9. HORIZON BOUNDARY, INDICES 200 & DELETION OF SIMPLE VECTOR BUILDER TESTS
# ==============================================================================

def test_horizon_boundary_returns_clean_error_on_missing_data(client, monkeypatch):
    """
    Test 3a:
    When current hour is at start/end of the time array and future hours for lead 6
    are missing, the service must return a clean 503 error ('Insufficient data to compute nowcast for this hour')
    without crashing (500) or silently falling back to an unverified feature pipeline.
    """
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    now_str = now.strftime("%Y-%m-%dT%H:00")

    # 1. Payload with current hour at start and no future hours for lead 6 (only 1 hour)
    payload_start_only = {
        "latitude": 28.61,
        "longitude": 77.21,
        "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "current": {"temperature_2m": 30.0, "weather_code": 1},
        "hourly": {
            "time": [now_str],
            "temperature_2m": [30.0],
            "relative_humidity_2m": [60.0],
            "dew_point_2m": [20.0],
            "surface_pressure": [1005.0],
            "wind_speed_10m": [5.0],
            "wind_direction_10m": [100],
            "cloud_cover": [25],
            "precipitation": [0.0],
            "precipitation_probability": [0],
            "cape": [1000.0],
            "convective_inhibition": [-10.0],
            "total_column_integrated_water_vapour": [40.0],
            "weather_code": [1],
        },
    }

    async def mock_get_start(self, url, params=None):
        return httpx.Response(200, json=payload_start_only, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_start)

    # Lead 6 exceeds available horizon -> clean 503
    res_lead6 = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=6")
    assert res_lead6.status_code == 503
    assert res_lead6.json()["detail"] == "Insufficient data to compute nowcast for this hour"

    # Lead 0 with no previous hours uses safe zero/default lags without crashing or fallback
    res_lead0 = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=0")
    assert res_lead0.status_code == 200
    assert len(res_lead0.json()["predictions"]) == 1

    # 2. Payload with current hour at end of array (24 past hours, 0 future hours)
    past_times = [(now - timedelta(hours=23 - h)).strftime("%Y-%m-%dT%H:00") for h in range(24)]
    payload_end_only = {
        "latitude": 28.61,
        "longitude": 77.21,
        "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "current": {"temperature_2m": 30.0, "weather_code": 1},
        "hourly": {
            "time": past_times,
            "temperature_2m": [30.0] * 24,
            "relative_humidity_2m": [60.0] * 24,
            "dew_point_2m": [20.0] * 24,
            "surface_pressure": [1005.0] * 24,
            "wind_speed_10m": [5.0] * 24,
            "wind_direction_10m": [100] * 24,
            "cloud_cover": [25] * 24,
            "precipitation": [0.0] * 24,
            "precipitation_probability": [0] * 24,
            "cape": [1000.0] * 24,
            "convective_inhibition": [-10.0] * 24,
            "total_column_integrated_water_vapour": [40.0] * 24,
            "weather_code": [1] * 24,
        },
    }

    async def mock_get_end(self, url, params=None):
        return httpx.Response(200, json=payload_end_only, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_end)

    # Lead 6 exceeds available horizon -> clean 503
    res_lead6_end = client.get("/api/v1/predictions/nowcast?lat=28.61&lon=77.21&lead_hours=6")
    assert res_lead6_end.status_code == 503
    assert res_lead6_end.json()["detail"] == "Insufficient data to compute nowcast for this hour"


def test_weather_indices_never_returns_500_for_valid_payload(client, monkeypatch):
    """
    Test 3b:
    GET /weather/indices must return 200 with valid derived thermodynamic indices
    and never return 500 when provided with a valid Open-Meteo payload.
    """
    async def mock_get(self, url, params=None):
        return httpx.Response(200, json=MOCK_OPEN_METEO_PAYLOAD, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    response = client.get("/api/v1/weather/indices?lat=28.61&lon=77.21")
    assert response.status_code == 200
    data = response.json()
    assert "derived_indices" in data
    assert "cape_index_derived" in data["derived_indices"]
    assert "cin_index_derived" in data["derived_indices"]
    assert "pw_index_derived" in data["derived_indices"]
    assert isinstance(data["derived_indices"]["cape_index_derived"], (int, float))


def test_simple_vector_builder_completely_deleted():
    """
    Test 3c:
    Assert that the unverified simple-vector fallback builder is completely deleted
    from FeatureEngineer and cannot be invoked by any prediction code path.
    """
    assert not hasattr(FeatureEngineer, "build_feature_vector_simple"), (
        "FeatureEngineer.build_feature_vector_simple must be completely deleted."
    )
    assert not hasattr(FeatureEngineer, "build_feature_vector_fast"), (
        "FeatureEngineer.build_feature_vector_fast must be deleted."
    )



