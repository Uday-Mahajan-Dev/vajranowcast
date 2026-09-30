"""Machine learning inference models and rule-based fallbacks for thunderstorm and lightning prediction."""

import hashlib
import json
import logging
import os
from typing import Any
import joblib
import numpy as np
from app.config import settings

logger = logging.getLogger("vajranowcast.ml")


class SeverityClassifier:
    """Classify storm severity based strictly on predicted thunderstorm probability P(TS)."""

    @staticmethod
    def classify(ts_prob: float, cape: float = 0.0, wind_shear: float = 0.0) -> str:
        """
        Classify severity into none, weak, moderate, severe, or very_severe.
        Bands depend strictly on thunderstorm probability P(TS) calibrated against optimal threshold (0.1860):
        - >= 0.75: very_severe
        - >= 0.60: severe
        - >= 0.40: moderate
        - >= 0.1860: weak
        - < 0.1860: none
        """
        if ts_prob >= 0.75:
            return "very_severe"
        if ts_prob >= 0.60:
            return "severe"
        if ts_prob >= 0.40:
            return "moderate"
        if ts_prob >= 0.1860:
            return "weak"
        return "none"


class LightningPredictor:
    """
    Predict lightning probability derived as a simple monotonic function of thunderstorm probability.
    Uses rule-based heuristic scaling (P(LT) = 0.90 * P(TS)) ensuring lightning never exceeds P(TS).
    """

    method: str = "rule-based heuristic"

    def predict(self, features: dict[str, Any] = None, ts_prob: float = 0.0) -> tuple[float, float]:
        """
        Calculate lightning probability and confidence strictly as a monotonic function of P(TS).
        Method: rule-based heuristic.
        Returns: (lightning_probability, confidence)
        """
        # Monotonic scaling: P(LT) = 0.90 * P(TS)
        lightning_prob = min(max(ts_prob * 0.90, 0.0), 0.99)
        # Base confidence derived monotonically from storm probability
        confidence = round(float(np.clip(0.50 + 0.40 * min(ts_prob, 1.0), 0.50, 0.90)), 4)

        return round(lightning_prob, 4), confidence


_global_classifier = None


def get_thunderstorm_classifier() -> "ThunderstormClassifier":
    """Retrieve global singleton ThunderstormClassifier instance."""
    global _global_classifier
    if _global_classifier is None:
        _global_classifier = ThunderstormClassifier()
    return _global_classifier


class ThunderstormClassifier:
    """Calibrated ML classifier with integrity verification and rule-based fallback for thunderstorm nowcasting."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ThunderstormClassifier, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.optimal_threshold = settings.OPTIMAL_THRESHOLD
        self.is_trained = False
        self._initialized = True

        self._load_artifacts()

    @staticmethod
    def _compute_sha256(filepath: str) -> str:
        """Compute the SHA-256 checksum of a file."""
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _verify_model_integrity(self, model_dir: str) -> bool:
        """Verify model files against stored SHA-256 hashes to prevent artifact tampering."""
        hashes_path = os.path.join(model_dir, "model_hashes.json")
        if not os.path.exists(hashes_path):
            logger.warning(f"Integrity check skipped: {hashes_path} not found.")
            return True

        try:
            with open(hashes_path, "r") as f:
                expected_hashes = json.load(f)

            for filename, expected_hash in expected_hashes.items():
                fpath = os.path.join(model_dir, filename)
                if not os.path.exists(fpath):
                    logger.error(f"Integrity check failed: Expected model artifact {filename} missing.")
                    return False
                actual_hash = self._compute_sha256(fpath)
                if actual_hash.lower() != expected_hash.lower():
                    logger.critical(
                        f"CRITICAL SECURITY ALERT: Model artifact '{filename}' SHA-256 mismatch! "
                        f"Expected {expected_hash}, got {actual_hash}. Refusing to load untrusted model."
                    )
                    return False

            logger.info("All ML model artifacts verified successfully against SHA-256 checksums.")
            return True
        except Exception as e:
            logger.error(f"Error during model integrity verification: {e}")
            return False

    def _load_artifacts(self):
        """Load trained model, scaler, feature columns, and optimal threshold with hash verification."""
        model_dir = settings.MODEL_DIR
        try:
            # 1. Verify model integrity first
            if not self._verify_model_integrity(model_dir):
                raise ValueError("Model artifact integrity verification failed.")

            model_path = os.path.join(model_dir, "thunderstorm_model.pkl")
            scaler_path = os.path.join(model_dir, "thunderstorm_scaler.pkl")
            cols_path = os.path.join(model_dir, "feature_columns.pkl")
            thresh_path = os.path.join(model_dir, "optimal_threshold.pkl")

            if not (os.path.exists(model_path) and os.path.exists(scaler_path) and os.path.exists(cols_path)):
                raise FileNotFoundError("One or more required model artifacts are missing in MODEL_DIR.")

            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            self.feature_columns = joblib.load(cols_path)

            if os.path.exists(thresh_path):
                self.optimal_threshold = float(joblib.load(thresh_path))
            else:
                self.optimal_threshold = settings.OPTIMAL_THRESHOLD

            self.is_trained = True
            logger.info(
                f"ThunderstormClassifier loaded successfully from {model_dir}. "
                f"Optimal threshold: {self.optimal_threshold:.4f}"
            )
        except Exception as e:
            self.is_trained = False
            logger.warning(
                f"Failed to load ML artifacts from {model_dir}: {e}. "
                f"Falling back to rule-based convective inference."
            )

    def predict(self, features: dict[str, Any]) -> tuple[float, float, str]:
        """
        Predict thunderstorm probability, dynamic confidence score, and severity category.
        Returns: (probability, confidence, severity)
        """
        if self.is_trained and self.model is not None and self.feature_columns:
            try:
                # Build feature vector in exact order
                X_raw = [float(features.get(col, 0.0)) for col in self.feature_columns]
                X_arr = np.array(X_raw, dtype=np.float64).reshape(1, -1)

                # HistGradientBoosting is trained on UNSCALED features
                prob_array = self.model.predict_proba(X_arr)
                probability = float(prob_array[0][1])

                # Dynamic confidence based on distance from decision threshold (0.1860)
                d = abs(probability - self.optimal_threshold)
                confidence = round(float(np.clip(0.50 + 0.45 * min(d / 0.50, 1.0), 0.50, 0.95)), 4)
                severity = SeverityClassifier.classify(probability)

                return round(probability, 4), confidence, severity
            except Exception as e:
                logger.error(f"Inference error with trained model: {e}. Falling back to rule-based logic.")
                return self._rule_based(features)
        else:
            return self._rule_based(features)

    def _rule_based(self, features: dict[str, Any]) -> tuple[float, float, str]:
        """Rule-based scoring system for convective potential (max score 100)."""
        score = 0.0

        cape = float(features.get("cape", 0.0))
        cin = float(features.get("cin", 0.0))
        humidity = float(features.get("relative_humidity", 0.0))
        dpd = float(features.get("dew_point_depression", 10.0))
        pw = float(features.get("precipitable_water", 0.0))
        cloud_cover = float(features.get("cloud_cover", 0.0))
        hour_sin = float(features.get("hour_sin", 0.0))
        hour_cos = float(features.get("hour_cos", 0.0))
        month_sin = float(features.get("month_sin", 0.0))

        # CAPE score (max 30)
        if cape > 3000:
            score += 30
        elif cape > 2000:
            score += 25
        elif cape > 1000:
            score += 18
        elif cape > 500:
            score += 10
        elif cape > 200:
            score += 5

        # CIN score (low inhibition favors convection, max 15)
        if cin < 25:
            score += 15
        elif cin < 50:
            score += 10
        elif cin < 100:
            score += 5

        # Relative Humidity score (max 10)
        if humidity > 80:
            score += 10
        elif humidity > 65:
            score += 6
        elif humidity > 50:
            score += 3

        # Dew point depression score (low DPD = near saturation, max 10)
        if dpd < 3:
            score += 10
        elif dpd < 5:
            score += 6
        elif dpd < 8:
            score += 3

        # Precipitable water score (max 10)
        if pw > 50:
            score += 10
        elif pw > 35:
            score += 6
        elif pw > 25:
            score += 3

        # Cloud cover score (max 5)
        if cloud_cover > 70:
            score += 5

        # Diurnal peak heating: Afternoon hours (12:00 - 18:00: hour_sin > 0, hour_cos < 0.2)
        if hour_sin > 0 and hour_cos < 0.2:
            score += 10

        # Seasonal pre-monsoon peak (March - June: month_sin > 0.5)
        if month_sin > 0.5:
            score += 5

        probability = float(min(score / 100.0, 0.99))
        confidence = 0.50
        severity = SeverityClassifier.classify(probability)

        return round(probability, 4), confidence, severity
