"""Machine learning inference models and rule-based fallbacks for thunderstorm and lightning prediction."""

import os
import logging
from typing import Any
import joblib
import numpy as np
from app.config import settings

logger = logging.getLogger("vajranowcast.ml")


class SeverityClassifier:
    """Classify storm severity based on predicted probability and atmospheric instability (CAPE)."""

    @staticmethod
    def classify(ts_prob: float, cape: float, wind_shear: float = 0.0) -> str:
        """
        Classify severity into none, weak, moderate, severe, or very_severe.
        Threshold is calibrated around optimal_threshold of 0.1860.
        """
        if ts_prob < 0.15:
            return "none"
        if ts_prob > 0.85 and cape > 3500:
            return "very_severe"
        if ts_prob > 0.65 and cape > 2500:
            return "severe"
        if ts_prob > 0.40 and cape > 1000:
            return "moderate"
        if ts_prob >= 0.15:
            return "weak"
        return "none"


class LightningPredictor:
    """Predict lightning probability derived from convective instability and thunderstorm probability."""

    def predict(self, features: dict[str, Any], ts_prob: float) -> tuple[float, float]:
        """
        Calculate lightning probability and confidence based on CAPE and moisture factors.
        Returns: (lightning_probability, confidence)
        """
        lightning = ts_prob * 0.7
        cape = float(features.get("cape", 0.0))
        pw = float(features.get("precipitable_water", 0.0))

        if cape > 2000:
            lightning += 0.20
        elif cape > 1000:
            lightning += 0.10

        if pw > 40:
            lightning += 0.05

        lightning_prob = min(max(lightning, 0.0), 0.99)
        confidence = 0.40

        return round(lightning_prob, 4), confidence


class ThunderstormClassifier:
    """Calibrated ML classifier with rule-based fallback for thunderstorm nowcasting."""

    def __init__(self):
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.optimal_threshold = settings.OPTIMAL_THRESHOLD
        self.is_trained = False

        self._load_artifacts()

    def _load_artifacts(self):
        """Load trained model, scaler, feature columns, and optimal threshold."""
        model_dir = settings.MODEL_DIR
        try:
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
        Predict thunderstorm probability, confidence score, and severity category.
        Returns: (probability, confidence, severity)
        """
        if self.is_trained and self.model is not None and self.scaler is not None and self.feature_columns:
            try:
                # Build feature vector in exact order
                X_raw = [float(features.get(col, 0.0)) for col in self.feature_columns]
                X_arr = np.array(X_raw, dtype=np.float64).reshape(1, -1)
                X_scaled = self.scaler.transform(X_arr)

                # Get calibrated probability
                prob_array = self.model.predict_proba(X_scaled)
                probability = float(prob_array[0][1])
                confidence = 0.85
                severity = SeverityClassifier.classify(probability, float(features.get("cape", 0.0)))

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
        severity = SeverityClassifier.classify(probability, cape)

        return round(probability, 4), confidence, severity
