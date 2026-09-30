"""Zero-network parity tests verifying exact mathematical alignment between training notebook and backend pipeline."""

from datetime import datetime
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest

from app.services.training_features import (
    CLEAN_FEATURE_COLS,
    build_features_from_raw_slice,
    engineer_training_features_df,
)

REFERENCES_DIR = Path(__file__).resolve().parent.parent / "app" / "ml" / "ml_references"
MODELS_DIR = Path(__file__).resolve().parent.parent / "app" / "ml" / "saved_models"


def test_model_parity_against_colab_golden_rows():
    """
    Model Parity Test (Task 4a):
    Feed golden_rows.csv features to the loaded unscaled HistGradientBoosting model
    and assert |prob - colab_prob| < 1e-6.
    """
    golden_rows_path = REFERENCES_DIR / "golden_rows.csv"
    model_path = MODELS_DIR / "thunderstorm_model.pkl"
    cols_path = MODELS_DIR / "feature_columns.pkl"

    assert golden_rows_path.exists(), f"{golden_rows_path} must exist"
    assert model_path.exists(), f"{model_path} must exist"

    golden_rows = pd.read_csv(golden_rows_path)
    model = joblib.load(model_path)
    feature_columns = joblib.load(cols_path)

    assert feature_columns == CLEAN_FEATURE_COLS

    X = golden_rows[feature_columns].values
    model_probs = model.predict_proba(X)[:, 1]
    colab_probs = golden_rows["colab_prob"].values

    diffs = np.abs(model_probs - colab_probs)
    max_diff = np.max(diffs)

    assert max_diff < 1e-6, f"Model probability mismatch exceeds 1e-6: max diff = {max_diff}"


def test_pipeline_parity_against_colab_golden_raw():
    """
    Pipeline Parity Test (Task 4b):
    For each golden row, build features from golden_raw.csv with training_features.py
    and assert every feature matches golden_rows.csv within tolerance 1e-6.
    """
    golden_raw_path = REFERENCES_DIR / "golden_raw.csv"
    golden_rows_path = REFERENCES_DIR / "golden_rows.csv"

    assert golden_raw_path.exists(), f"{golden_raw_path} must exist"
    assert golden_rows_path.exists(), f"{golden_rows_path} must exist"

    golden_raw = pd.read_csv(golden_raw_path)
    golden_rows = pd.read_csv(golden_rows_path)

    for gid, group in golden_raw.groupby("golden_row"):
        raw_hourly = {c: group[c].tolist() for c in group.columns}
        target_idx = len(group) - 1
        t_str = group["time"].iloc[-1]
        target_time = datetime.fromisoformat(t_str)
        lat = float(group["latitude"].iloc[-1])
        lon = float(group["longitude"].iloc[-1])

        computed_features = build_features_from_raw_slice(
            raw_hourly=raw_hourly,
            target_idx=target_idx,
            original_lat=lat,
            original_lon=lon,
            target_time=target_time,
        )

        expected_row = golden_rows.iloc[int(gid)]

        for col in CLEAN_FEATURE_COLS:
            val_computed = computed_features[col]
            val_expected = float(expected_row[col])
            diff = abs(val_computed - val_expected)
            assert diff < 1e-6, (
                f"Feature '{col}' mismatch in golden row {gid}: "
                f"computed={val_computed}, expected={val_expected}, diff={diff}"
            )


def test_spec_parity_backend_and_frontend():
    """
    Spec Parity Test:
    Assert that the backend OPEN_METEO_PARAMS_SPEC and frontend constants match identically.
    """
    from app.config import settings
    frontend_constants_path = (
        Path(__file__).resolve().parent.parent.parent
        / "frontend"
        / "lib"
        / "constants.ts"
    )
    assert frontend_constants_path.exists(), "frontend/lib/constants.ts must exist"

    content = frontend_constants_path.read_text(encoding="utf-8")
    backend_spec = settings.OPEN_METEO_PARAMS_SPEC

    # Verify hourly variables string matches exactly
    assert f'hourly: "{backend_spec["hourly"]}"' in content
    assert f'forecast_days: {backend_spec["forecast_days"]}' in content
    assert f'past_days: {backend_spec["past_days"]}' in content
    assert f'timezone: "{backend_spec["timezone"]}"' in content


def test_nowcast_and_nowcast_from_data_parity():
    """
    Parity Test:
    Verify that the exact same Open-Meteo payload processed through /nowcast (mocked server fetch)
    and /nowcast-from-data (client direct payload) produces identical predictions.
    """
    from datetime import timedelta, timezone
    from unittest.mock import AsyncMock, patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.cache import meteo_cache

    meteo_cache.clear()
    client = TestClient(app)

    base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hourly_times = [
        (base_time + timedelta(hours=h - 24)).strftime("%Y-%m-%dT%H:00")
        for h in range(72)
    ]

    mock_om_payload = {
        "latitude": 28.61,
        "longitude": 77.21,
        "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "hourly": {
            "time": hourly_times,
            "temperature_2m": [32.0 + (h % 4) for h in range(72)],
            "relative_humidity_2m": [65.0 + (h % 15) for h in range(72)],
            "dew_point_2m": [24.0 + (h % 2) for h in range(72)],
            "surface_pressure": [1002.0 + (h % 3) for h in range(72)],
            "wind_speed_10m": [6.0 + (h % 5) for h in range(72)],
            "wind_direction_10m": [(120 + h * 5) % 360 for h in range(72)],
            "cloud_cover": [70.0 + (h % 25) for h in range(72)],
            "precipitation": [0.5 if h == 25 else 0.0 for h in range(72)],
            "weather_code": [80.0 if h == 25 else 1.0 for h in range(72)],
        },
    }

    # 1. Fetch via GET /nowcast (mocking OpenMeteoService.fetch_current_weather)
    with patch(
        "app.services.data_ingestion.OpenMeteoService.fetch_current_weather",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = (mock_om_payload, False, datetime.now(timezone.utc), None)
        res_server = client.get(
            "/api/v1/predictions/nowcast",
            params={"lat": 28.61, "lon": 77.21, "lead_hours": "0,1,2,3,6"},
        )

    assert res_server.status_code == 200, f"GET /nowcast failed: {res_server.text}"
    server_data = res_server.json()
    assert server_data["metadata"]["data_fetched_by"] == "server"

    # 2. Fetch via POST /nowcast-from-data (direct client payload)
    res_client = client.post(
        "/api/v1/predictions/nowcast-from-data",
        params={"lead_hours": "0,1,2,3,6"},
        json=mock_om_payload,
    )

    assert res_client.status_code == 200, f"POST /nowcast-from-data failed: {res_client.text}"
    client_data = res_client.json()
    assert client_data["metadata"]["data_fetched_by"] == "client"

    # 3. Assert exact prediction parity across all lead times
    assert len(server_data["predictions"]) == len(client_data["predictions"]) == 5

    for s_pred, c_pred in zip(server_data["predictions"], client_data["predictions"]):
        assert s_pred["lead_time_hours"] == c_pred["lead_time_hours"]
        assert abs(s_pred["thunderstorm_probability"] - c_pred["thunderstorm_probability"]) < 1e-6
        assert abs(s_pred["lightning_probability"] - c_pred["lightning_probability"]) < 1e-6
        assert s_pred["severity"] == c_pred["severity"]
        assert abs(s_pred["confidence"] - c_pred["confidence"]) < 1e-6
        assert s_pred["valid_from"] == c_pred["valid_from"]
        assert s_pred["valid_until"] == c_pred["valid_until"]


def test_nowcast_from_data_strict_validation():
    """
    Validation Test:
    Assert strict validation rules on POST /nowcast-from-data.
    """
    from datetime import timedelta, timezone
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hourly_times = [
        (base_time + timedelta(hours=h - 24)).strftime("%Y-%m-%dT%H:00")
        for h in range(72)
    ]

    valid_payload = {
        "latitude": 28.61,
        "longitude": 77.21,
        "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "hourly": {
            "time": hourly_times,
            "temperature_2m": [30.0] * 72,
            "relative_humidity_2m": [60.0] * 72,
            "dew_point_2m": [22.0] * 72,
            "surface_pressure": [1000.0] * 72,
            "wind_speed_10m": [5.0] * 72,
            "wind_direction_10m": [90.0] * 72,
            "cloud_cover": [50.0] * 72,
            "precipitation": [0.0] * 72,
            "weather_code": [1.0] * 72,
        },
    }

    # Invalid timezone
    invalid_tz = dict(valid_payload, timezone="UTC")
    res = client.post("/api/v1/predictions/nowcast-from-data", json=invalid_tz)
    assert res.status_code == 422

    # Invalid UTC offset
    invalid_offset = dict(valid_payload, utc_offset_seconds=0)
    res = client.post("/api/v1/predictions/nowcast-from-data", json=invalid_offset)
    assert res.status_code == 422

    # Coordinates outside coverage box
    invalid_coords = dict(valid_payload, latitude=55.0)
    res = client.post("/api/v1/predictions/nowcast-from-data", json=invalid_coords)
    assert res.status_code == 422

    # Array length mismatch
    invalid_hourly = dict(valid_payload)
    invalid_hourly["hourly"] = dict(valid_payload["hourly"], temperature_2m=[30.0] * 50)
    res = client.post("/api/v1/predictions/nowcast-from-data", json=invalid_hourly)
    assert res.status_code == 422

    # Out of range relative humidity
    invalid_rh = dict(valid_payload)
    invalid_rh["hourly"] = dict(valid_payload["hourly"], relative_humidity_2m=[150.0] * 72)
    res = client.post("/api/v1/predictions/nowcast-from-data", json=invalid_rh)
    assert res.status_code == 422


def test_upstream_429_returns_503():
    """
    Upstream Error Test:
    Assert that Open-Meteo 429/5xx with no cache returns HTTP 503 with upstream_rate_limited code.
    """
    from unittest.mock import AsyncMock, patch
    from fastapi.testclient import TestClient
    import httpx
    from app.main import app
    from app.core.cache import meteo_cache

    meteo_cache.clear()
    client = TestClient(app)

    # Mock httpx client in OpenMeteoService to return 429
    mock_resp = httpx.Response(
        status_code=429,
        content=b'{"error": true, "reason": "Daily API request limit exceeded on shared IP."}',
        request=httpx.Request("GET", "https://api.open-meteo.com/v1/forecast"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = client.get("/api/v1/predictions/nowcast", params={"lat": 19.08, "lon": 72.88})

    assert res.status_code == 503
    data = res.json()
    assert data["code"] == "upstream_rate_limited"
    assert "Weather data provider is busy" in data["detail"]


def test_health_stored_state_instant():
    """
    Health Check Test:
    Verify that /health only reports stored state without re-verifying hashes or reloading model.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["model_loaded"] is True
    assert data["optimal_threshold"] == 0.186
    assert "version" in data


def test_alerts_generate_accepts_precomputed_body():
    """
    Alert Generation Test:
    Verify POST /api/v1/alerts/generate accepts precomputed city predictions without calling Open-Meteo.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import settings

    client = TestClient(app)

    body = {
        "cities": {
            "Delhi": [
                {
                    "latitude": 28.61,
                    "longitude": 77.21,
                    "lead_time_hours": 1.0,
                    "thunderstorm_probability": 0.65,
                    "severity": "severe",
                    "lightning_probability": 0.58,
                    "confidence": 0.85,
                }
            ]
        }
    }

    res = client.post(
        "/api/v1/alerts/generate",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json=body,
    )
    assert res.status_code == 200
    data = res.json()
    assert "alerts_generated" in data
    assert "alerts" in data

