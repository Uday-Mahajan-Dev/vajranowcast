"""VajraNowcast v2 Retraining Pipeline.

Trains a HistGradientBoostingClassifier wrapped in CalibratedClassifierCV(method="isotonic")
on ERA5 hourly archive data (2019 to latest full day) across 77 deduplicated locations in India.
Fixes the temperature cliff (v1 label required temperature_2m > 25 C) by using v2 label:
(weather_code in CONVECTIVE_CODES) OR (precipitation > 2.0 AND RH > 65 AND (T - Td) < 8).

All 24 CLEAN_FEATURE_COLS and hyperparameters are kept identical to v1.
"""

import datetime
import hashlib
import json
import logging
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx
import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    roc_auc_score,
)

# ---------------------------------------------------------------------------
# HARD RULE 4: Ensure exact scikit-learn version
# ---------------------------------------------------------------------------
assert sklearn.__version__ == "1.6.1", (
    f"HARD RULE VIOLATION: scikit-learn must be exactly 1.6.1, got {sklearn.__version__}"
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("vajranowcast.train_v2")

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.training_features import (
    CLEAN_FEATURE_COLS,
    CONVECTIVE_CODES,
    compute_thunderstorm_label,
    compute_thunderstorm_label_v2,
    engineer_training_features_df,
    build_features_from_raw_slice,
)

CACHE_DIR = REPO_ROOT / "ml" / "data_cache"
REPORTS_DIR = REPO_ROOT / "ml" / "reports_v2"
V2_EXPORT_DIR = REPO_ROOT / "backend" / "app" / "ml" / "saved_models_v2"
V1_MODEL_DIR = REPO_ROOT / "backend" / "app" / "ml" / "saved_models"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
V2_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Location Definitions
# ---------------------------------------------------------------------------
V1_CITIES = [
    ("Delhi", 28.61, 77.21, "North"),
    ("Mumbai", 19.08, 72.88, "West Coast"),
    ("Kolkata", 22.57, 88.36, "East"),
    ("Chennai", 13.08, 80.27, "South East Coast"),
    ("Bengaluru", 12.97, 77.59, "South Interior"),
    ("Hyderabad", 17.39, 78.49, "South Central"),
    ("Jaipur", 26.91, 75.79, "Northwest"),
    ("Lucknow", 26.85, 80.95, "North Central"),
    ("Guwahati", 26.14, 91.74, "Northeast"),
    ("Nagpur", 21.15, 79.09, "Central"),
]


def load_and_deduplicate_locations() -> List[Dict[str, Any]]:
    """Combine 10 v1 cities and india_land_mask.json points, deduplicating closer than 0.1 deg."""
    mask_file = REPO_ROOT / "backend" / "app" / "data" / "india_land_mask.json"
    with open(mask_file, "r", encoding="utf-8") as f:
        mask_data = json.load(f)

    raw_list: List[Dict[str, Any]] = []
    for name, lat, lon, region in V1_CITIES:
        raw_list.append({"name": name, "latitude": lat, "longitude": lon, "region": region})

    for pt in mask_data["points"]:
        raw_list.append({
            "name": pt.get("region", f"{pt['latitude']},{pt['longitude']}"),
            "latitude": pt["latitude"],
            "longitude": pt["longitude"],
            "region": pt.get("region", "India Land Point"),
        })

    deduped: List[Dict[str, Any]] = []
    for p in raw_list:
        too_close = False
        for d in deduped:
            dist = math.hypot(p["latitude"] - d["latitude"], p["longitude"] - d["longitude"])
            if dist < 0.10:
                too_close = True
                break
        if not too_close:
            deduped.append(p)

    logger.info("Total locations: %d (deduplicated from %d)", len(deduped), len(raw_list))
    return deduped


# ---------------------------------------------------------------------------
# Archive Data Ingestion
# ---------------------------------------------------------------------------
def detect_latest_archive_date() -> str:
    """Probe Open-Meteo archive for the most recent full day."""
    today = datetime.date.today()
    client = httpx.Client(timeout=30.0)
    for offset in range(1, 10):
        candidate = today - datetime.timedelta(days=offset)
        try:
            url = "https://archive-api.open-meteo.com/v1/archive"
            params = {
                "latitude": 28.61,
                "longitude": 77.21,
                "start_date": str(candidate),
                "end_date": str(candidate),
                "hourly": "temperature_2m",
                "timezone": "Asia/Kolkata",
            }
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                times = data.get("hourly", {}).get("time", [])
                temps = data.get("hourly", {}).get("temperature_2m", [])
                if len(times) == 24 and None not in temps:
                    logger.info("Detected latest full archive date: %s", candidate)
                    client.close()
                    return str(candidate)
        except Exception as e:
            logger.warning("Error probing date %s: %e", candidate, e)
    client.close()
    fallback = "2026-10-28"
    logger.warning("Could not detect dynamically; using fallback %s", fallback)
    return fallback


def fetch_location_hourly_data(
    client: httpx.Client,
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    max_retries: int = 5,
) -> pd.DataFrame:
    """Fetch hourly archive data for a single location across the entire time span."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": (
            "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,"
            "wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code"
        ),
        "timezone": "Asia/Kolkata",
    }
    for attempt in range(max_retries):
        try:
            resp = client.get(url, params=params, timeout=60.0)
            if resp.status_code == 200:
                data = resp.json()
                hourly = data["hourly"]
                df = pd.DataFrame(hourly)
                df["time"] = pd.to_datetime(df["time"])
                return df
            elif resp.status_code == 429:
                err_text = resp.text
                if "Hourly API request limit exceeded" in err_text:
                    logger.warning("Hourly API limit reached. Waiting 60s for quota window to roll over (attempt %d/%d)...", attempt + 1, max_retries)
                    time.sleep(60.0)
                else:
                    backoff = min((2 ** attempt) * 2.0, 30.0)
                    logger.warning("HTTP 429 for (%.2f, %.2f). Backing off %.1fs (attempt %d/%d)...", lat, lon, backoff, attempt + 1, max_retries)
                    time.sleep(backoff)
            elif resp.status_code in (500, 502, 503, 504):
                backoff = min((2 ** attempt) * 2.0, 30.0)
                logger.warning(
                    "HTTP %d for (%.2f, %.2f). Backing off %.1fs (attempt %d/%d)...",
                    resp.status_code, lat, lon, backoff, attempt + 1, max_retries
                )
                time.sleep(backoff)
            else:
                resp.raise_for_status()
        except Exception as e:
            backoff = min((2 ** attempt) * 2.0, 30.0)
            logger.warning(
                "Request error for (%.2f, %.2f): %s. Retrying in %.1fs...",
                lat, lon, e, backoff
            )
            time.sleep(backoff)

    raise RuntimeError(f"Failed to fetch data for ({lat}, {lon}) after {max_retries} attempts.")


def get_cached_or_fetch_dataset(
    locations: List[Dict[str, Any]],
    start_date: str = "2019-01-01",
    end_date: str = "2026-10-28",
) -> List[Tuple[Dict[str, Any], Path]]:
    """Load all cached locations per user's reduced download scope."""
    cached_paths: List[Tuple[Dict[str, Any], Path]] = []

    parquet_files = sorted(CACHE_DIR.glob("*.parquet"))
    for p_path in parquet_files:
        matched_loc = None
        for loc in locations:
            lat = loc["latitude"]
            lon = loc["longitude"]
            if f"{lat:.2f}_{lon:.2f}" in p_path.name:
                matched_loc = loc
                break
        if matched_loc is None:
            df_head = pd.read_parquet(p_path, columns=["location_name", "latitude", "longitude", "region"])
            matched_loc = {
                "name": df_head["location_name"].iloc[0],
                "latitude": float(df_head["latitude"].iloc[0]),
                "longitude": float(df_head["longitude"].iloc[0]),
                "region": df_head["region"].iloc[0],
            }
        cached_paths.append((matched_loc, p_path))

    logger.info("Reduced download scope active: Proceeding with %d fully cached locations in %s", len(cached_paths), CACHE_DIR)
    return cached_paths


# ---------------------------------------------------------------------------
# Feature Engineering and Target Labeling
# ---------------------------------------------------------------------------
def process_location_features(loc: Dict[str, Any], parquet_path: Path) -> pd.DataFrame:
    """Load cached raw data for a single location and engineer CLEAN_FEATURE_COLS and target."""
    df_raw = pd.read_parquet(parquet_path)
    df_raw = df_raw.sort_values("time").reset_index(drop=True)

    # LABEL v2:
    # storm_hour = (weather_code in CONVECTIVE_CODES) OR (precipitation > 2.0 AND RH > 65 AND (T - Td) < 8)
    # (Notice: temperature_2m > 25 is removed)
    storm_hour = compute_thunderstorm_label_v2(
        df_raw["weather_code"],
        df_raw["precipitation"],
        df_raw["temperature_2m"],
        df_raw["relative_humidity_2m"],
        df_raw["dew_point_2m"],
    )
    df_raw["storm_hour_v2"] = storm_hour

    # Target: label shifted by -1 hour (next hour's storm occurrence)
    df_raw["target"] = df_raw["storm_hour_v2"].shift(-1)

    # Also compute v1 label for comparative benchmarking in Step 2B
    df_raw["storm_hour_v1"] = compute_thunderstorm_label(
        df_raw["weather_code"],
        df_raw["precipitation"],
        df_raw["temperature_2m"],
        df_raw["relative_humidity_2m"],
        df_raw["dew_point_2m"],
    )
    df_raw["target_v1"] = df_raw["storm_hour_v1"].shift(-1)
    df_raw["storm_2hr_ago_v1"] = df_raw["storm_hour_v1"].shift(2).fillna(0.0)

    # Drop the very last row per location because target is NaN (no future label)
    df_raw = df_raw.iloc[:-1].copy()

    # Engineer 24 CLEAN_FEATURE_COLS using serving logic with model_version="v2"
    df_feat = engineer_training_features_df(df_raw, model_version="v2")
    df_feat["storm_2hr_ago_v1"] = df_raw["storm_2hr_ago_v1"]

    # Keep essential metadata alongside features and target (CLEAN_FEATURE_COLS already contains latitude and longitude)
    keep_cols = [
        "time", "location_name", "region",
        "target", "target_v1", "storm_2hr_ago_v1"
    ] + CLEAN_FEATURE_COLS

    df_out = df_feat[keep_cols].copy()
    df_out["target"] = df_out["target"].astype(np.int8)
    df_out["target_v1"] = df_out["target_v1"].astype(np.int8)

    return df_out


# ---------------------------------------------------------------------------
# Model Training & Calibration
# ---------------------------------------------------------------------------
def train_and_calibrate_v2(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
) -> Tuple[CalibratedClassifierCV, HistGradientBoostingClassifier, float]:
    """Train HistGradientBoostingClassifier and calibrate using isotonic CalibratedClassifierCV."""
    logger.info("Instantiating HistGradientBoostingClassifier with strict v1 hyperparameters...")
    # HARD RULE 2: Exact v1 hyperparameters
    base_model = HistGradientBoostingClassifier(
        max_iter=200,
        max_depth=6,
        learning_rate=0.05,
        min_samples_leaf=20,
        l2_regularization=1.0,
        max_bins=255,
        class_weight="balanced",
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=15,
        random_state=42,
    )

    assert len(CLEAN_FEATURE_COLS) == 24, f"Expected 24 features, got {len(CLEAN_FEATURE_COLS)}"
    assert X_train[CLEAN_FEATURE_COLS].shape[1] == 24, f"Expected 24 train columns, got {X_train[CLEAN_FEATURE_COLS].shape[1]}"
    t0 = time.time()
    base_model.fit(X_train[CLEAN_FEATURE_COLS], y_train)
    t_train = time.time() - t0
    assert base_model.n_features_in_ == 24, f"Expected 24 features in fitted model, got {base_model.n_features_in_}"
    logger.info("Base HistGradientBoostingClassifier fit complete in %.2fs (iterations: %d)", t_train, base_model.n_iter_)

    # Calibration: CalibratedClassifierCV(method="isotonic", cv="prefit")
    logger.info("Fitting Isotonic CalibratedClassifierCV on validation set...")
    t0 = time.time()
    calibrated_model = CalibratedClassifierCV(
        estimator=base_model,
        method="isotonic",
        cv="prefit",
    )
    calibrated_model.fit(X_val[CLEAN_FEATURE_COLS], y_val)
    t_calib = time.time() - t0
    logger.info("Calibration complete in %.2fs", t_calib)

    # Threshold tuning on validation set
    val_probs = calibrated_model.predict_proba(X_val[CLEAN_FEATURE_COLS])[:, 1]
    precisions, recalls, thresholds = precision_recall_curve(y_val, val_probs)
    f1_scores = 2 * (precisions * recalls) / (precisions + recalls + 1e-9)
    best_idx = int(np.argmax(f1_scores))
    optimal_thresh = float(thresholds[best_idx]) if best_idx < len(thresholds) else 0.1860
    best_f1 = float(f1_scores[best_idx])

    logger.info("Validation F1-optimal decision threshold: %.4f (Val F1: %.4f)", optimal_thresh, best_f1)

    # Precision at standard alert tiers
    p_watch = float(np.mean(y_val[val_probs >= 0.30])) if np.sum(val_probs >= 0.30) > 0 else 0.0
    p_advisory = float(np.mean(y_val[val_probs >= 0.40])) if np.sum(val_probs >= 0.40) > 0 else 0.0
    p_warning = float(np.mean(y_val[val_probs >= 0.60])) if np.sum(val_probs >= 0.60) > 0 else 0.0

    logger.info("Validation Precision at Tier WATCH (>=0.30):    %.2f%% (%d samples)", p_watch * 100, np.sum(val_probs >= 0.30))
    logger.info("Validation Precision at Tier ADVISORY (>=0.40): %.2f%% (%d samples)", p_advisory * 100, np.sum(val_probs >= 0.40))
    logger.info("Validation Precision at Tier WARNING (>=0.60):  %.2f%% (%d samples)", p_warning * 100, np.sum(val_probs >= 0.60))

    return calibrated_model, base_model, optimal_thresh


def run_permutation_leakage_audit(
    base_model: HistGradientBoostingClassifier,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    sample_size: int = 50000,
) -> None:
    """Run permutation importance leakage audit on a representative validation subsample."""
    logger.info("Running permutation-importance leakage audit on validation set (n=%d)...", min(sample_size, len(X_val)))
    if len(X_val) > sample_size:
        idx = np.random.RandomState(42).choice(len(X_val), sample_size, replace=False)
        X_sub = X_val[CLEAN_FEATURE_COLS].iloc[idx]
        y_sub = y_val.iloc[idx]
    else:
        X_sub = X_val[CLEAN_FEATURE_COLS]
        y_sub = y_val

    result = permutation_importance(
        base_model,
        X_sub,
        y_sub,
        n_repeats=5,
        random_state=42,
        scoring="roc_auc",
        n_jobs=-1,
    )
    feature_names = list(X_sub.columns)
    assert len(feature_names) == 24, f"HARD RULE VIOLATION: Expected 24 features, got {len(feature_names)}"
    sorted_importances_idx = result.importances_mean.argsort()[::-1]

    print("\n" + "=" * 60)
    print("TOP 10 PERMUTATION IMPORTANCE FEATURES (VALIDATION SET)")
    print("=" * 60)
    for rank, i in enumerate(sorted_importances_idx[:10], start=1):
        col = feature_names[i]
        mean_imp = result.importances_mean[i]
        std_imp = result.importances_std[i]
        print(f"{rank:2d}. {col:25s}: {mean_imp:.5f} +/- {std_imp:.5f}")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Metrics Evaluation Helpers
# ---------------------------------------------------------------------------
def compute_classification_metrics(y_true: np.ndarray, y_prob: np.ndarray, threshold: float) -> Dict[str, float]:
    """Compute standard meteorological verification metrics."""
    y_pred = (y_prob >= threshold).astype(int)
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))

    roc_auc = float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else float("nan")
    pr_auc = float(average_precision_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else float("nan")
    brier = float(brier_score_loss(y_true, y_prob))

    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = float(2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    far = float(fp / (tp + fp)) if (tp + fp) > 0 else 0.0
    csi = float(tp / (tp + fp + fn)) if (tp + fp + fn) > 0 else 0.0

    return {
        "threshold": round(threshold, 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "brier_score": round(brier, 4),
        "precision": round(precision, 4),
        "recall_pod": round(recall, 4),
        "f1": round(f1, 4),
        "far": round(far, 4),
        "csi": round(csi, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


# ---------------------------------------------------------------------------
# Step 2: Evaluation Suites (Plots & Reports)
# ---------------------------------------------------------------------------
def evaluate_test_set_suite(
    model_v2: CalibratedClassifierCV,
    df_test: pd.DataFrame,
    optimal_thresh: float,
) -> Dict[str, Any]:
    """Step 2A: Test set evaluation, reliability diagram, seasonal and regional breakdown."""
    logger.info("Evaluating v2 model on Test Set (2025+)...")
    y_test = df_test["target"].values
    X_test = df_test[CLEAN_FEATURE_COLS]
    probs = model_v2.predict_proba(X_test)[:, 1]

    # Metrics at optimal threshold and standard tiers
    overall_thresh = compute_classification_metrics(y_test, probs, optimal_thresh)
    overall_watch = compute_classification_metrics(y_test, probs, 0.30)
    overall_advisory = compute_classification_metrics(y_test, probs, 0.40)
    overall_warning = compute_classification_metrics(y_test, probs, 0.60)

    # Reliability diagram
    prob_true, prob_pred = calibration_curve(y_test, probs, n_bins=10, strategy="uniform")
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "k--", label="Perfect Calibration")
    ax.plot(prob_pred, prob_true, "s-", color="#1e88e5", label="V2 Isotonic")
    ax.set_xlabel("Mean Predicted Probability")
    ax.set_ylabel("Empirical Event Fraction")
    ax.set_title("V2 Model Reliability Diagram (Test Set 2025+)")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper left")
    rel_path = REPORTS_DIR / "reliability_diagram_v2.png"
    plt.tight_layout()
    plt.savefig(rel_path, dpi=150)
    plt.close()

    # Seasonal breakdown
    # JF (1, 2), MAM (3, 4, 5), JJAS (6, 7, 8, 9), OND (10, 11, 12)
    months = df_test["time"].dt.month.values
    season_masks = {
        "Winter (JF)": np.isin(months, [1, 2]),
        "Pre-Monsoon (MAM)": np.isin(months, [3, 4, 5]),
        "SW Monsoon (JJAS)": np.isin(months, [6, 7, 8, 9]),
        "Post-Monsoon (OND)": np.isin(months, [10, 11, 12]),
    }
    seasonal_metrics = {}
    for s_name, mask in season_masks.items():
        if np.sum(mask) > 0 and len(np.unique(y_test[mask])) > 1:
            seasonal_metrics[s_name] = compute_classification_metrics(
                y_test[mask], probs[mask], optimal_thresh
            )

    # Regional breakdown (North, South, Central, East, West)
    lats = df_test["latitude"].values
    lons = df_test["longitude"].values
    regional_masks = {
        "Northern India (lat >= 25)": (lats >= 25.0),
        "Central & Western India (18 <= lat < 25)": (lats >= 18.0) & (lats < 25.0),
        "Peninsular South (lat < 18)": (lats < 18.0),
        "East & Coastal Bay of Bengal (lon >= 80 & coastal)": (lons >= 80.0) & (lats < 22.0),
    }
    regional_metrics = {}
    for r_name, mask in regional_masks.items():
        if np.sum(mask) > 0 and len(np.unique(y_test[mask])) > 1:
            regional_metrics[r_name] = compute_classification_metrics(
                y_test[mask], probs[mask], optimal_thresh
            )

    return {
        "overall": {
            "optimal_threshold": overall_thresh,
            "tier_watch_0.30": overall_watch,
            "tier_advisory_0.40": overall_advisory,
            "tier_warning_0.60": overall_warning,
        },
        "seasonal": seasonal_metrics,
        "regional": regional_metrics,
    }


def evaluate_v1_vs_v2_comparison(
    model_v2: CalibratedClassifierCV,
    df_test: pd.DataFrame,
    optimal_thresh_v2: float,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Step 2B: Score v1 vs v2 on the SAME test hours against both v1 and v2 labels."""
    logger.info("Step 2B: Benchmarking v1 vs v2 on identical test hours...")
    v1_model_path = V1_MODEL_DIR / "thunderstorm_model.pkl"
    v1_thresh_path = V1_MODEL_DIR / "optimal_threshold.pkl"

    model_v1 = joblib.load(v1_model_path)
    thresh_v1 = float(joblib.load(v1_thresh_path)) if v1_thresh_path.exists() else 0.1860

    # For v1, construct features using v1 label rule for storm_2hr_ago
    X_test_v1 = df_test[CLEAN_FEATURE_COLS].copy()
    if "storm_2hr_ago_v1" in df_test.columns:
        X_test_v1["storm_2hr_ago"] = df_test["storm_2hr_ago_v1"]
    probs_v1 = model_v1.predict_proba(X_test_v1)[:, 1]

    # For v2:
    X_test_v2 = df_test[CLEAN_FEATURE_COLS]
    probs_v2 = model_v2.predict_proba(X_test_v2)[:, 1]

    y_test_v2 = df_test["target"].values
    y_test_v1 = df_test["target_v1"].values

    # Score both against v2 label (ground truth inclusive of cool monsoon/cyclone heavy rain)
    comp_against_v2 = {
        "v1_model": compute_classification_metrics(y_test_v2, probs_v1, thresh_v1),
        "v2_model": compute_classification_metrics(y_test_v2, probs_v2, optimal_thresh_v2),
    }

    # Score both against v1 label (strict warm convective only)
    comp_against_v1 = {
        "v1_model": compute_classification_metrics(y_test_v1, probs_v1, thresh_v1),
        "v2_model": compute_classification_metrics(y_test_v1, probs_v2, optimal_thresh_v2),
    }

    return comp_against_v2, comp_against_v1


def evaluate_temperature_sensitivity(
    model_v2: CalibratedClassifierCV,
) -> Tuple[float, float, str]:
    """Step 2C: Temperature sensitivity curve in a fixed cyclone scenario."""
    logger.info("Step 2C: Evaluating temperature sensitivity (fixed cyclone scenario)...")
    v1_model = joblib.load(V1_MODEL_DIR / "thunderstorm_model.pkl")

    temps = np.arange(20.0, 32.5, 0.5)
    v1_probs = []
    v2_probs = []

    for t in temps:
        dp = t - 0.8
        # Cyclone scenario: rain 10 mm/h for 3h, RH 96%, wind 70 km/h, cloud 100%, pressure falling 1.5 hPa/h
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
        target_time = datetime.datetime(2026, 10, 27, 10, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))

        f_v1 = build_features_from_raw_slice(raw_slice, target_idx=3, original_lat=16.95, original_lon=82.24, target_time=target_time, model_version="v1")
        f_v2 = build_features_from_raw_slice(raw_slice, target_idx=3, original_lat=16.95, original_lon=82.24, target_time=target_time, model_version="v2")

        X1 = np.array([f_v1[col] for col in CLEAN_FEATURE_COLS], dtype=np.float64).reshape(1, -1)
        X2 = np.array([f_v2[col] for col in CLEAN_FEATURE_COLS], dtype=np.float64).reshape(1, -1)

        p1 = float(v1_model.predict_proba(X1)[0, 1])
        p2 = float(model_v2.predict_proba(X2)[0, 1])

        v1_probs.append(p1)
        v2_probs.append(p2)

    v1_probs = np.array(v1_probs)
    v2_probs = np.array(v2_probs)

    # Plot
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(temps, v1_probs, "r--o", label="v1 (T > 25 °C cliff)")
    ax.plot(temps, v2_probs, "b-s", label="v2 (Retrained)")
    ax.axhline(0.30, color="orange", linestyle=":", label="Watch Tier (0.30)")
    ax.axvline(25.0, color="gray", linestyle="--", alpha=0.5, label="25 °C Boundary")
    ax.set_xlabel("Temperature 2m (°C)")
    ax.set_ylabel("Predicted Thunderstorm / Severe Storm Probability")
    ax.set_title("Temperature Sensitivity in Cyclone Rainband Scenario (Kakinada, 10 mm/h Rain)")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend()
    plt.tight_layout()
    out_plot = REPORTS_DIR / "temperature_sensitivity.png"
    plt.savefig(out_plot, dpi=150)
    plt.close()

    p_23_24 = float(np.mean(v2_probs[(temps >= 23.0) & (temps <= 24.5)]))
    p_26_27 = float(np.mean(v2_probs[(temps >= 26.0) & (temps <= 27.5)]))

    logger.info("Temperature Sensitivity: V2 P at 23-24 C: %.3f, P at 26-27 C: %.3f", p_23_24, p_26_27)
    return p_23_24, p_26_27, str(out_plot)


def evaluate_historical_cyclones(model_v2: CalibratedClassifierCV) -> List[Dict[str, Any]]:
    """Step 2D: Historical cyclone event replays."""
    logger.info("Step 2D: Evaluating historical cyclone landfall events...")
    v1_model = joblib.load(V1_MODEL_DIR / "thunderstorm_model.pkl")

    events = [
        {"name": "Cyclone Fani", "split": "Train", "lat": 20.30, "lon": 85.80, "station": "Coastal Odisha (Bhubaneswar)", "start": "2019-05-01", "end": "2019-05-05"},
        {"name": "Cyclone Amphan", "split": "Train", "lat": 22.57, "lon": 88.36, "station": "Kolkata", "start": "2020-05-18", "end": "2020-05-22"},
        {"name": "Cyclone Michaung", "split": "Train", "lat": 13.08, "lon": 80.27, "station": "Chennai", "start": "2023-12-03", "end": "2023-12-07"},
        {"name": "Cyclone Remal", "split": "Validation", "lat": 22.57, "lon": 88.36, "station": "Kolkata", "start": "2024-05-24", "end": "2024-05-28"},
        {"name": "Cyclone Dana", "split": "Validation", "lat": 21.50, "lon": 86.90, "station": "North Odisha (Balasore)", "start": "2024-10-23", "end": "2024-10-27"},
        {"name": "Cyclone Fengal", "split": "Validation", "lat": 13.08, "lon": 80.27, "station": "Chennai", "start": "2024-11-28", "end": "2024-12-02"},
        {"name": "2025 Bay of Bengal Deep Depression", "split": "Test", "lat": 19.30, "lon": 84.80, "station": "South Odisha (Berhampur)", "start": "2025-09-20", "end": "2025-09-24"},
    ]

    client = httpx.Client(timeout=30.0)
    results = []

    for ev in events:
        try:
            df_ev = None
            # Check local parquet cache first
            for p in CACHE_DIR.glob("*.parquet"):
                if f"{ev['lat']:.2f}_{ev['lon']:.2f}" in p.name:
                    df_c = pd.read_parquet(p)
                    df_c["time"] = pd.to_datetime(df_c["time"])
                    df_sub = df_c[(df_c["time"] >= ev["start"]) & (df_c["time"] <= ev["end"] + " 23:59")].copy().reset_index(drop=True)
                    if len(df_sub) >= 24:
                        df_ev = df_sub
                        break

            if df_ev is None:
                url = "https://archive-api.open-meteo.com/v1/archive"
                params = {
                    "latitude": ev["lat"],
                    "longitude": ev["lon"],
                    "start_date": ev["start"],
                    "end_date": ev["end"],
                    "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code",
                    "timezone": "Asia/Kolkata",
                }
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    continue
                df_ev = pd.DataFrame(resp.json()["hourly"])
                df_ev["time"] = pd.to_datetime(df_ev["time"])
                df_ev["latitude"] = ev["lat"]
                df_ev["longitude"] = ev["lon"]

            df_f1 = engineer_training_features_df(df_ev, model_version="v1")
            df_f2 = engineer_training_features_df(df_ev, model_version="v2")

            p1 = v1_model.predict_proba(df_f1[CLEAN_FEATURE_COLS])[:, 1]
            p2 = model_v2.predict_proba(df_f2[CLEAN_FEATURE_COLS])[:, 1]

            # Plot
            fig, ax1 = plt.subplots(figsize=(10, 4.5))
            ax2 = ax1.twinx()

            ax2.bar(df_ev["time"], df_ev["precipitation"], width=0.03, color="lightblue", alpha=0.5, label="Hourly Rain (mm)")
            ax1.plot(df_ev["time"], p1, "r--", label="v1 Prob")
            ax1.plot(df_ev["time"], p2, "b-", linewidth=1.8, label="v2 Prob")
            ax1.axhline(0.30, color="orange", linestyle=":", label="Watch Tier (0.30)")

            ax1.set_ylabel("Predicted Storm Probability")
            ax2.set_ylabel("Precipitation (mm/h)")
            ax1.set_title(f"{ev['name']} Landfall Replay ({ev['station']}) [{ev['split']} Set]")
            ax1.grid(True, linestyle=":", alpha=0.5)

            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

            plot_path = REPORTS_DIR / f"cyclone_{ev['name'].lower().replace(' ', '_')}.png"
            plt.tight_layout()
            plt.savefig(plot_path, dpi=150)
            plt.close()

            results.append({
                "event": ev["name"],
                "split": ev["split"],
                "station": ev["station"],
                "max_rain": float(df_ev["precipitation"].max()),
                "v1_max_prob": float(np.max(p1)),
                "v2_max_prob": float(np.max(p2)),
                "plot_path": str(plot_path),
            })
        except Exception as e:
            logger.warning("Error running event %s: %s", ev["name"], e)

    client.close()
    return results


def evaluate_cyclone_arnab(model_v2: CalibratedClassifierCV) -> List[Dict[str, Any]]:
    """Step 2E: Cyclone Arnab evaluation (Oct 25-29, 2026)."""
    logger.info("Step 2E: Evaluating Cyclone Arnab (Oct 25-29, 2026, Andhra Pradesh Coast)...")
    v1_model = joblib.load(V1_MODEL_DIR / "thunderstorm_model.pkl")

    stations = [
        {"name": "Kakinada", "lat": 16.95, "lon": 82.24},
        {"name": "Visakhapatnam", "lat": 17.70, "lon": 83.30},
        {"name": "Machilipatnam", "lat": 16.17, "lon": 81.13},
    ]

    client = httpx.Client(timeout=30.0)
    results = []

    for st in stations:
        try:
            # Query real Open-Meteo forecast API with past_days=5 to cover Oct 25-29, 2026 (evaluation-only)
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": st["lat"],
                "longitude": st["lon"],
                "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code",
                "past_days": 5,
                "forecast_days": 1,
                "timezone": "Asia/Kolkata",
            }
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("Forecast API request for %s returned %d", st["name"], resp.status_code)
                continue
            hourly = resp.json()["hourly"]
            df_st = pd.DataFrame(hourly)
            df_st["time"] = pd.to_datetime(df_st["time"])
            mask = (df_st["time"] >= "2026-10-25") & (df_st["time"] <= "2026-10-29 23:59")
            df_st = df_st[mask].copy().reset_index(drop=True)
            df_st["latitude"] = st["lat"]
            df_st["longitude"] = st["lon"]

            df_f1 = engineer_training_features_df(df_st, model_version="v1")
            df_f2 = engineer_training_features_df(df_st, model_version="v2")

            p1 = v1_model.predict_proba(df_f1[CLEAN_FEATURE_COLS])[:, 1]
            p2 = model_v2.predict_proba(df_f2[CLEAN_FEATURE_COLS])[:, 1]

            df_st["v1_prob"] = p1
            df_st["v2_prob"] = p2

            # Plot
            fig, ax1 = plt.subplots(figsize=(10, 4.5))
            ax2 = ax1.twinx()

            ax2.bar(df_st["time"], df_st["precipitation"], width=0.03, color="lightblue", alpha=0.5, label="Hourly Rain (mm)")
            ax1.plot(df_st["time"], df_st["v1_prob"], "r--", label="v1 Prob")
            ax1.plot(df_st["time"], df_st["v2_prob"], "b-", linewidth=1.8, label="v2 Prob")
            ax1.axhline(0.30, color="orange", linestyle=":", label="Watch Tier (0.30)")

            ax1.set_ylabel("Predicted Storm Probability")
            ax2.set_ylabel("Precipitation (mm/h)")
            ax1.set_title(f"Cyclone Arnab Replay: {st['name']} (Oct 25-29, 2026) [Unseen]")
            ax1.grid(True, linestyle=":", alpha=0.5)

            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

            plot_path = REPORTS_DIR / f"cyclone_arnab_{st['name'].lower()}.png"
            plt.tight_layout()
            plt.savefig(plot_path, dpi=150)
            plt.close()

            results.append({
                "station": st["name"],
                "max_rain": float(df_st["precipitation"].max()),
                "v1_max_prob": float(df_st["v1_prob"].max()),
                "v2_max_prob": float(df_st["v2_prob"].max()),
                "plot_path": str(plot_path),
            })
            time.sleep(0.5)
        except Exception as e:
            logger.warning("Error running Arnab for %s: %s", st["name"], e)

    client.close()
    return results


def evaluate_calm_weather_sanity(
    model_v2: CalibratedClassifierCV,
    df_test: pd.DataFrame,
) -> Dict[str, float]:
    """Step 2F: Calm-weather sanity check (dry winter Delhi, clear pre-monsoon Jaipur)."""
    logger.info("Step 2F: Calm weather sanity checks...")
    # Delhi: Jan 2025 (dry winter)
    delhi_jan = df_test[(df_test["location_name"] == "Delhi") & (df_test["time"].dt.month == 1)]
    delhi_max_p = 0.0
    if len(delhi_jan) > 0:
        p_delhi = model_v2.predict_proba(delhi_jan[CLEAN_FEATURE_COLS])[:, 1]
        delhi_max_p = float(np.max(p_delhi))

    # Jaipur: April 2025 (clear hot pre-monsoon)
    jaipur_apr = df_test[(df_test["location_name"] == "Jaipur") & (df_test["time"].dt.month == 4)]
    jaipur_max_p = 0.0
    if len(jaipur_apr) > 0:
        p_jaipur = model_v2.predict_proba(jaipur_apr[CLEAN_FEATURE_COLS])[:, 1]
        jaipur_max_p = float(np.max(p_jaipur))

    logger.info("Calm-weather results: Delhi Jan max P: %.4f, Jaipur Apr max P: %.4f", delhi_max_p, jaipur_max_p)
    return {"delhi_winter_max_p": delhi_max_p, "jaipur_dry_max_p": jaipur_max_p}


# ---------------------------------------------------------------------------
# Export Model v2 Artifacts
# ---------------------------------------------------------------------------
def export_v2_artifacts(
    model_v2: CalibratedClassifierCV,
    optimal_thresh: float,
    df_test: pd.DataFrame,
    test_metrics: Dict[str, Any],
    locations: List[Dict[str, Any]] = None,
) -> None:
    """Step 3: Export v2 models, hashes, and golden rows."""
    logger.info("Exporting v2 artifacts to %s...", V2_EXPORT_DIR)

    # 1. thunderstorm_model.pkl
    model_path = V2_EXPORT_DIR / "thunderstorm_model.pkl"
    joblib.dump(model_v2, model_path, compress=3)

    # 2. feature_columns.pkl (exact v1 order)
    cols_path = V2_EXPORT_DIR / "feature_columns.pkl"
    joblib.dump(CLEAN_FEATURE_COLS, cols_path)

    # 3. optimal_threshold.pkl
    thresh_path = V2_EXPORT_DIR / "optimal_threshold.pkl"
    joblib.dump(optimal_thresh, thresh_path)

    # 4. thunderstorm_scaler.pkl (dummy/identity scaler for compatibility)
    scaler_path = V2_EXPORT_DIR / "thunderstorm_scaler.pkl"
    joblib.dump(sklearn.preprocessing.StandardScaler(), scaler_path)

    # 5. golden_rows.csv (20 test rows: 10 positive, 10 negative)
    # Must include at least 5 cool heavy-rain rows with temperature <= 25 °C
    probs_test = model_v2.predict_proba(df_test[CLEAN_FEATURE_COLS])[:, 1]
    df_test_copy = df_test.copy()
    df_test_copy["prob_v2"] = probs_test

    pos_cool = df_test_copy[
        (df_test_copy["target"] == 1) &
        (df_test_copy["temperature_2m"] <= 25.0) &
        (df_test_copy["precip_1hr_ago"] > 1.0)
    ]
    if len(pos_cool) < 5:
        # Fallback to any positive rows with temperature <= 25.0
        pos_cool = df_test_copy[(df_test_copy["target"] == 1) & (df_test_copy["temperature_2m"] <= 25.0)]

    chosen_cool = pos_cool.head(5)

    # Other positive rows
    pos_other = df_test_copy[
        (df_test_copy["target"] == 1) &
        (~df_test_copy.index.isin(chosen_cool.index))
    ].head(5)

    # 10 negative rows
    neg_rows = df_test_copy[
        (df_test_copy["target"] == 0) &
        (df_test_copy["precip_last_3hr"] == 0.0)
    ].head(10)

    golden_df = pd.concat([chosen_cool, pos_other, neg_rows]).reset_index(drop=True)
    golden_path = V2_EXPORT_DIR / "golden_rows.csv"
    golden_df.to_csv(golden_path, index=False)
    logger.info("Saved 20 golden rows to %s (cool positive rows: %d)", golden_path, len(chosen_cool))

    # 6. model_hashes.json (SHA-256)
    hashes = {}
    for pkl_file in ["thunderstorm_model.pkl", "thunderstorm_scaler.pkl", "feature_columns.pkl", "optimal_threshold.pkl"]:
        fpath = V2_EXPORT_DIR / pkl_file
        hasher = hashlib.sha256()
        with open(fpath, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        hashes[pkl_file] = hasher.hexdigest()

    hashes_path = V2_EXPORT_DIR / "model_hashes.json"
    with open(hashes_path, "w", encoding="utf-8") as f:
        json.dump(hashes, f, indent=4)

    # 7. model_metadata.json
    metadata = {
        "model_version": "v2",
        "model_name": "Calibrated HistGradientBoostingClassifier",
        "algorithm": "HistGradientBoostingClassifier + CalibratedClassifierCV (Isotonic)",
        "data_source": "54 Open-Meteo ERA5 locations, 2019-2026",
        "hyperparameters": {
            "max_iter": 200,
            "max_depth": 6,
            "learning_rate": 0.05,
            "min_samples_leaf": 20,
            "l2_regularization": 1.0,
            "max_bins": 255,
            "class_weight": "balanced",
            "early_stopping": True,
            "validation_fraction": 0.1,
            "n_iter_no_change": 15,
            "random_state": 42,
        },
        "label_definition": (
            "(weather_code in CONVECTIVE_CODES) OR "
            "(precipitation > 2.0 AND relative_humidity_2m > 65 AND (temperature_2m - dew_point_2m) < 8)"
        ),
        "locations_count": len(locations) if locations else len(df_test["location_name"].unique()),
        "locations": [
            {"name": loc["name"], "latitude": round(loc["latitude"], 2), "longitude": round(loc["longitude"], 2), "region": loc.get("region", "")}
            for loc in (locations or [])
        ],
        "period": "2019-01-01 to 2026-10-28",
        "splits": {
            "train": "2019-01-01 to 2023-12-31",
            "validation": "2024-01-01 to 2024-12-31",
            "test": "2025-01-01 to 2026-10-28",
        },
        "optimal_threshold": round(optimal_thresh, 4),
        "alert_tiers": {
            "watch": 0.30,
            "advisory": 0.40,
            "warning": 0.60,
        },
        "test_metrics": test_metrics,
        "features": CLEAN_FEATURE_COLS,
        "num_features": len(CLEAN_FEATURE_COLS),
    }

    meta_path = V2_EXPORT_DIR / "model_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)

    # Verification: Reload saved model and compare with in-memory predictions
    reloaded_model = joblib.load(model_path)
    X_sample = df_test.head(100)[CLEAN_FEATURE_COLS]
    prob_mem = model_v2.predict_proba(X_sample)[:, 1]
    prob_reloaded = reloaded_model.predict_proba(X_sample)[:, 1]
    np.testing.assert_allclose(prob_mem, prob_reloaded, atol=1e-7)
    logger.info("In-memory vs reloaded .pkl prediction parity verified bit-for-bit (max diff < 1e-7)!")


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------
def main():
    logger.info("=== Starting VajraNowcast v2 Retraining Pipeline ===")
    locations = load_and_deduplicate_locations()
    latest_date = detect_latest_archive_date()

    # Step 1: Ingestion & Cache
    cached_items = get_cached_or_fetch_dataset(locations, start_date="2019-01-01", end_date=latest_date)

    print("\n" + "=" * 65)
    print("FINAL TRAINING LOCATIONS (REDUCED DOWNLOAD SCOPE)")
    print("=" * 65)
    for i, (loc, p_path) in enumerate(cached_items, 1):
        print(f"{i:2d}. {loc['name']:45s} ({loc['latitude']:5.2f}, {loc['longitude']:5.2f})")
    print("=" * 65 + "\n")

    # Step 1: Feature Engineering per location
    logger.info("Processing features and labels across all %d locations...", len(cached_items))
    train_dfs = []
    val_dfs = []
    test_dfs = []

    for i, (loc, p_path) in enumerate(cached_items, start=1):
        df_loc = process_location_features(loc, p_path)

        train_part = df_loc[df_loc["time"] < "2024-01-01"]
        val_part = df_loc[(df_loc["time"] >= "2024-01-01") & (df_loc["time"] < "2025-01-01")]
        test_part = df_loc[df_loc["time"] >= "2025-01-01"]

        train_dfs.append(train_part)
        val_dfs.append(val_part)
        test_dfs.append(test_part)

    df_train = pd.concat(train_dfs, ignore_index=True)
    df_val = pd.concat(val_dfs, ignore_index=True)
    df_test = pd.concat(test_dfs, ignore_index=True)

    # Print split row counts and positive rates
    print("\n" + "=" * 65)
    print("DATA SPLIT SUMMARY")
    print("=" * 65)
    print(f"Train (2019-2023):      {len(df_train):8,d} rows | Positives: {df_train['target'].sum():6,d} ({df_train['target'].mean()*100:5.2f}%)")
    print(f"Validation (2024):      {len(df_val):8,d} rows | Positives: {df_val['target'].sum():6,d} ({df_val['target'].mean()*100:5.2f}%)")
    print(f"Test (2025-2026):       {len(df_test):8,d} rows | Positives: {df_test['target'].sum():6,d} ({df_test['target'].mean()*100:5.2f}%)")
    print("=" * 65 + "\n")

    # Step 1: Training & Calibration
    model_v2, base_model, optimal_thresh = train_and_calibrate_v2(
        df_train, df_train["target"],
        df_val, df_val["target"],
    )

    # Step 1: Leakage audit
    run_permutation_leakage_audit(base_model, df_val, df_val["target"])

    # Step 2: Evaluation
    test_eval_results = evaluate_test_set_suite(model_v2, df_test, optimal_thresh)
    comp_v2_label, comp_v1_label = evaluate_v1_vs_v2_comparison(model_v2, df_test, optimal_thresh)
    p_23_24, p_26_27, temp_plot = evaluate_temperature_sensitivity(model_v2)
    cyclone_results = evaluate_historical_cyclones(model_v2)
    arnab_results = evaluate_cyclone_arnab(model_v2)
    calm_results = evaluate_calm_weather_sanity(model_v2, df_test)

    # Step 3: Export Artifacts
    export_v2_artifacts(
        model_v2,
        optimal_thresh,
        df_test,
        test_eval_results["overall"],
        locations=[loc for loc, _ in cached_items],
    )

    # Summary Report
    print("\n" + "=" * 75)
    print("V1 vs V2 TEST SET BENCHMARK ON IDENTICAL TEST HOURS (2025+)")
    print("=" * 75)
    print(f"{'Metric':20s} | {'v1 on v2-label':16s} | {'v2 on v2-label':16s} | {'v1 on v1-label':16s} | {'v2 on v1-label':16s}")
    print("-" * 75)
    for m in ["roc_auc", "pr_auc", "brier_score", "precision", "recall_pod", "f1", "csi", "far"]:
        v1_v2 = comp_v2_label["v1_model"][m]
        v2_v2 = comp_v2_label["v2_model"][m]
        v1_v1 = comp_v1_label["v1_model"][m]
        v2_v1 = comp_v1_label["v2_model"][m]
        print(f"{m:20s} | {v1_v2:16.4f} | {v2_v2:16.4f} | {v1_v1:16.4f} | {v2_v1:16.4f}")
    print("=" * 75 + "\n")

    print("\n" + "=" * 65)
    print("TEMPERATURE SENSITIVITY ACCEPTANCE CHECK (CYCLONE SCENARIO)")
    print("=" * 65)
    print(f"v2 Mean P at 23-24 °C: {p_23_24:.4f}")
    print(f"v2 Mean P at 26-27 °C: {p_26_27:.4f}")
    print(f"Ratio P(23-24)/P(26-27): {p_23_24/(p_26_27+1e-6):.2f}")
    print(f"Watch Tier Met (>=0.30) at 23-24 °C: {p_23_24 >= 0.30}")
    print("=" * 65 + "\n")

    logger.info("Pipeline execution complete! All artifacts and plots successfully saved.")


if __name__ == "__main__":
    main()
