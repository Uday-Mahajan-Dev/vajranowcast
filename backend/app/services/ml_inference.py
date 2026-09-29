"""Nowcasting inference service orchestrating meteorological data ingestion, feature generation, and ML scoring."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models.schemas import SeverityLevel, ThunderstormPrediction
from app.services.data_ingestion import OpenMeteoService
from app.services.feature_engineering import FeatureEngineer
from app.ml.models.thunderstorm_model import (
    LightningPredictor,
    SeverityClassifier,
    ThunderstormClassifier,
)

logger = logging.getLogger("vajranowcast.inference")


class NowcastingService:
    """End-to-end inference service for thunderstorm and lightning nowcasting."""

    def __init__(self):
        self.data_service = OpenMeteoService()
        self.feature_engineer = FeatureEngineer()
        self.ts_model = ThunderstormClassifier()
        self.lt_model = LightningPredictor()
        self.severity = SeverityClassifier()

    async def predict_for_location(
        self,
        lat: float,
        lon: float,
        lead_hours: list[float] | None = None,
    ) -> list[ThunderstormPrediction]:
        """
        Generate thunderstorm and lightning nowcast predictions for specified lead times.
        Defaults to [0, 1, 2, 3, 6] hour lead times.
        """
        if lead_hours is None:
            lead_hours = [0.0, 1.0, 2.0, 3.0, 6.0]

        weather_data = await self.data_service.fetch_current_weather(lat, lon)
        now = datetime.now(timezone.utc)
        results: list[ThunderstormPrediction] = []

        for lead_hour in lead_hours:
            target_hour_index = max(1, int(lead_hour))

            try:
                features = self.feature_engineer.build_feature_vector(
                    weather_data=weather_data,
                    lat=lat,
                    lon=lon,
                    timestamp=now,
                    target_hour_index=target_hour_index,
                )
            except Exception as e:
                logger.warning(f"Error building full feature vector: {e}. Falling back to simple vector.")
                features = self.feature_engineer.build_feature_vector_simple(
                    weather_data=weather_data,
                    lat=lat,
                    lon=lon,
                    timestamp=now,
                    hour_index=target_hour_index,
                )

            # Predict base probability and confidence
            ts_prob, ts_conf, _ = self.ts_model.predict(features)

            # Apply lead-time decay factor for uncertainty over longer time horizons
            ts_conf = ts_conf * max(0.5, 1.0 - lead_hour * 0.08)
            ts_prob = ts_prob * max(0.6, 1.0 - lead_hour * 0.05)

            # Predict lightning probability based on decayed ts_prob and instability
            lt_prob, lt_conf = self.lt_model.predict(features, ts_prob)

            # Compute severity category from updated probability & CAPE
            severity_str = self.severity.classify(ts_prob, float(features.get("cape", 0.0)))
            try:
                severity_enum = SeverityLevel(severity_str)
            except ValueError:
                severity_enum = SeverityLevel.none

            prediction_time = now + timedelta(hours=lead_hour)

            contributing_factors = {
                "cape": round(float(features.get("cape", 0.0)), 1),
                "cin": round(float(features.get("cin", 0.0)), 1),
                "relative_humidity": round(float(features.get("relative_humidity", 0.0)), 1),
                "dew_point_depression": round(float(features.get("dew_point_depression", 0.0)), 1),
                "precipitable_water": round(float(features.get("precipitable_water", 0.0)), 1),
                "precip_last_3hr": round(float(features.get("precip_last_3hr", 0.0)), 2),
                "pressure_trend": round(float(features.get("pressure_trend", 0.0)), 2),
            }

            pred = ThunderstormPrediction(
                latitude=lat,
                longitude=lon,
                timestamp=now,
                prediction_time=prediction_time,
                lead_time_hours=float(lead_hour),
                thunderstorm_probability=round(ts_prob, 4),
                severity=severity_enum,
                lightning_probability=round(lt_prob, 4),
                confidence=round(ts_conf, 4),
                contributing_factors=contributing_factors,
            )
            results.append(pred)

        return results

    async def predict_for_cities(self, cities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """
        Generate nowcasts concurrently for multiple cities.
        Returns a dictionary mapping city name to list of prediction dicts or error info.
        """
        async def _predict_city(city_info: dict[str, Any]) -> tuple[str, list[Any] | dict[str, str]]:
            name = city_info.get("name", "Unknown")
            lat = city_info["lat"]
            lon = city_info["lon"]
            try:
                preds = await self.predict_for_location(lat, lon)
                return name, [p.model_dump() for p in preds]
            except Exception as e:
                logger.error(f"Error predicting for city {name}: {e}")
                return name, [{"error": str(e)}]

        tasks = [_predict_city(city) for city in cities]
        city_results = await asyncio.gather(*tasks, return_exceptions=True)

        results_dict: dict[str, Any] = {}
        for res in city_results:
            if isinstance(res, Exception):
                continue
            name, preds = res
            results_dict[name] = preds

        return results_dict
