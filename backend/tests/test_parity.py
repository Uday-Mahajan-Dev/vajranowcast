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
