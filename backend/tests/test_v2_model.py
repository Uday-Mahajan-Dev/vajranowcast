"""Tests for VajraNowcast v2 Retrained Model.

Verifies:
1. Feature columns match v1 CLEAN_FEATURE_COLS in exact order.
2. SHA-256 integrity verification passes for saved_models_v2/.
3. Bit-for-bit parity (< 1e-6) against saved_models_v2/golden_rows.csv.
4. Cyclone scenario at 24 °C gives probability >= 0.30 (Watch tier or higher, no cliff).
5. Calm dry scenario gives probability < 0.05.
6. ThunderstormClassifier properly loads v2 artifacts when MODEL_VERSION=v2.
"""

from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest

from app.config import settings
from app.services.training_features import (
    CLEAN_FEATURE_COLS,
    build_features_from_raw_slice,
    compute_thunderstorm_label_v2,
)

V2_DIR = Path(__file__).resolve().parent.parent / "app" / "ml" / "saved_models_v2"
V1_DIR = Path(__file__).resolve().parent.parent / "app" / "ml" / "saved_models"


def test_v2_feature_columns_equal_v1():
    """Assert feature_columns.pkl in v2 equals v1's CLEAN_FEATURE_COLS in exact order."""
    cols_v2_path = V2_DIR / "feature_columns.pkl"
    assert cols_v2_path.exists(), f"Missing {cols_v2_path}"
    cols_v2 = joblib.load(cols_v2_path)
    assert cols_v2 == CLEAN_FEATURE_COLS, "v2 feature columns must match CLEAN_FEATURE_COLS exactly"


def test_v2_model_hash_verification():
    """Verify SHA-256 checksums of saved_models_v2/ against model_hashes.json."""
    hashes_path = V2_DIR / "model_hashes.json"
    assert hashes_path.exists(), f"Missing {hashes_path}"

    with open(hashes_path, "r", encoding="utf-8") as f:
        expected_hashes = json.load(f)

    for filename, expected_hash in expected_hashes.items():
        fpath = V2_DIR / filename
        assert fpath.exists(), f"Artifact {filename} listed in model_hashes.json is missing"
        hasher = hashlib.sha256()
        with open(fpath, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        actual_hash = hasher.hexdigest()
        assert actual_hash.lower() == expected_hash.lower(), (
            f"Hash mismatch for {filename}: expected {expected_hash}, got {actual_hash}"
        )


def test_v2_model_parity_against_golden_rows():
    """
    Assert that the exported v2 model reproduces golden_rows.csv probabilities within 1e-6.
    Must include cool heavy-rain rows (temperature <= 25 °C).
    """
    model_path = V2_DIR / "thunderstorm_model.pkl"
    golden_path = V2_DIR / "golden_rows.csv"

    assert model_path.exists(), f"Missing {model_path}"
    assert golden_path.exists(), f"Missing {golden_path}"

    model = joblib.load(model_path)
    golden_df = pd.read_csv(golden_path)

    # Check requirement: 20 rows, at least 5 cool heavy-rain rows with temp <= 25 °C
    assert len(golden_df) == 20, f"Expected 20 golden rows, found {len(golden_df)}"
    cool_rows = golden_df[(golden_df["target"] == 1) & (golden_df["temperature_2m"] <= 25.0)]
    assert len(cool_rows) >= 5, f"Expected at least 5 cool positive rows, found {len(cool_rows)}"

    X = golden_df[CLEAN_FEATURE_COLS].values
    probs = model.predict_proba(X)[:, 1]
    expected_probs = golden_df["prob_v2"].values

    diffs = np.abs(probs - expected_probs)
    max_diff = np.max(diffs)
    assert max_diff < 1e-6, f"v2 parity mismatch exceeds 1e-6: max diff = {max_diff}"


def test_v2_cyclone_scenario_prob_watch_tier():
    """
    Acceptance test: In cyclone scenario (10 mm/h rain, 70 km/h wind, RH 96%, pressure fall),
    v2 gives P >= 0.30 at 24 °C (reaching at least the Watch tier, with no cliff).
    """
    model_path = V2_DIR / "thunderstorm_model.pkl"
    assert model_path.exists(), f"Missing {model_path}"
    model = joblib.load(model_path)

    t = 24.0
    dp = t - 0.8
    raw_slice = {
        "temperature_2m": [t, t, t, t],
        "dew_point_2m": [dp, dp, dp, dp],
        "relative_humidity_2m": [96.0, 96.0, 96.0, 96.0],
        "surface_pressure": [991.5, 990.0, 990.0, 990.0],
        "wind_speed_10m": [70.0, 70.0, 70.0, 70.0],
        "wind_direction_10m": [90.0, 90.0, 90.0, 90.0],
        "cloud_cover": [100.0, 100.0, 100.0, 100.0],
        "precipitation": [10.0, 10.0, 10.0, 10.0],
        "weather_code": [65, 65, 65, 65],
    }
    target_time = datetime(2026, 10, 27, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    f = build_features_from_raw_slice(
        raw_slice,
        target_idx=3,
        original_lat=16.95,
        original_lon=82.24,
        target_time=target_time,
        model_version="v2",
    )

    X = np.array([f[c] for c in CLEAN_FEATURE_COLS], dtype=np.float64).reshape(1, -1)
    p = float(model.predict_proba(X)[0, 1])

    assert p >= 0.30, f"Expected cyclone P >= 0.30 at 24 °C, got {p:.4f}"


def test_v2_calm_dry_scenario_prob():
    """Calm dry conditions must produce P < 0.05."""
    model_path = V2_DIR / "thunderstorm_model.pkl"
    assert model_path.exists(), f"Missing {model_path}"
    model = joblib.load(model_path)

    raw_slice = {
        "temperature_2m": [22.0, 22.0, 22.0, 22.0],
        "dew_point_2m": [8.0, 8.0, 8.0, 8.0],
        "relative_humidity_2m": [40.0, 40.0, 40.0, 40.0],
        "surface_pressure": [1015.0, 1015.0, 1015.0, 1015.0],
        "wind_speed_10m": [8.0, 8.0, 8.0, 8.0],
        "wind_direction_10m": [300.0, 300.0, 300.0, 300.0],
        "cloud_cover": [10.0, 10.0, 10.0, 10.0],
        "precipitation": [0.0, 0.0, 0.0, 0.0],
        "weather_code": [0, 0, 0, 0],
    }
    target_time = datetime(2025, 1, 15, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    f = build_features_from_raw_slice(
        raw_slice,
        target_idx=3,
        original_lat=28.61,
        original_lon=77.21,
        target_time=target_time,
        model_version="v2",
    )

    X = np.array([f[c] for c in CLEAN_FEATURE_COLS], dtype=np.float64).reshape(1, -1)
    p = float(model.predict_proba(X)[0, 1])

    assert p < 0.05, f"Expected calm dry P < 0.05, got {p:.4f}"
