"""Nowcasting inference service orchestrating meteorological data ingestion, feature generation, and ML scoring."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from app.core.cache import meteo_cache
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
        lead_hours: Optional[List[float]] = None,
        force_refresh: bool = False,
    ) -> List[ThunderstormPrediction]:
        """
        Generate thunderstorm and lightning nowcast predictions for specified lead times.
        Defaults to [0, 1, 2, 3, 6] hour lead times.
        """
        if lead_hours is None:
            lead_hours = [0.0, 1.0, 2.0, 3.0, 6.0]

        weather_data, is_stale, cached_at, stale_reason = await self.data_service.fetch_current_weather(
            lat, lon, force_refresh=force_refresh
        )
        now = datetime.now(timezone.utc)
        results: List[ThunderstormPrediction] = []

        for lead_hour in lead_hours:
            target_hour_index = max(0, int(lead_hour))

            try:
                features, row_dt_ist = self.feature_engineer.build_feature_vector(
                    weather_data=weather_data,
                    lat=lat,
                    lon=lon,
                    timestamp=now,
                    target_hour_index=target_hour_index,
                )
            except Exception as e:
                logger.error(f"Error building canonical feature vector for ({lat}, {lon}) lead +{lead_hour}h: {e}")
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Insufficient data to compute nowcast for this hour",
                )

            # Predict base probability and dynamic confidence from unscaled features
            ts_prob, ts_conf, _ = self.ts_model.predict(features)

            # Lead factor: 1.0 at lead 0, decreasing to ~0.60 at lead 6
            lead_factor = max(0.60, 1.0 - (lead_hour / 6.0) * 0.40)
            scaled_confidence = round(float(ts_conf * lead_factor), 4)

            # Model predicts the hour AFTER its input time (lead 0 -> input_hour..input_hour+1h)
            # Aligned strictly to the round hour of the meteorological row in UTC
            valid_from = row_dt_ist.astimezone(timezone.utc)
            valid_until = (row_dt_ist + timedelta(hours=1)).astimezone(timezone.utc)
            prediction_time = valid_from
            input_time_ist_str = row_dt_ist.isoformat()

            # Mark every lead that uses forecast (not analysis) inputs as extrapolated (lead >= 1)
            is_extrapolated = lead_hour >= 1.0
            lead_note = (
                f"extrapolated lead time using forecast NWP inputs (valid {row_dt_ist.strftime('%H:%M')} to {(row_dt_ist + timedelta(hours=1)).strftime('%H:%M')} IST; model trained on 1-hour ahead nowcast)"
                if is_extrapolated
                else f"t+1h nowcast using current-hour model data (valid {row_dt_ist.strftime('%H:%M')} to {(row_dt_ist + timedelta(hours=1)).strftime('%H:%M')} IST)"
            )

            # Predict lightning probability (monotonic rule-based heuristic function of P(TS))
            lt_prob, lt_conf = self.lt_model.predict(features, ts_prob)

            # Compute severity category from updated probability
            severity_str = self.severity.classify(ts_prob)
            try:
                severity_enum = SeverityLevel(severity_str)
            except ValueError:
                severity_enum = SeverityLevel.none

            input_conditions = {
                "cape_index_derived": round(float(features.get("cape", 0.0)), 1),
                "cin_index_derived": round(float(features.get("cin", 0.0)), 1),
                "pw_index_derived": round(float(features.get("precipitable_water", 0.0)), 1),
                "temperature_2m": round(float(features.get("temperature_2m", 0.0)), 1),
                "relative_humidity": round(float(features.get("relative_humidity", 0.0)), 1),
                "cloud_cover": round(float(features.get("cloud_cover", 0.0)), 1),
                "wind_speed_10m": round(float(features.get("wind_speed_10m", 0.0)), 1),
                "precip_1hr_ago": round(float(features.get("precip_1hr_ago", 0.0)), 2),
                "precip_last_3hr": round(float(features.get("precip_last_3hr", 0.0)), 2),
                "pressure_trend": round(float(features.get("pressure_trend", 0.0)), 2),
                "dew_point_depression": round(float(features.get("dew_point_depression", 0.0)), 1),
            }

            contributing_factors = {
                "cape": round(float(features.get("cape", 0.0)), 1),
                "cin": round(float(features.get("cin", 0.0)), 1),
                "precipitable_water": round(float(features.get("precipitable_water", 0.0)), 1),
                "relative_humidity": round(float(features.get("relative_humidity", 0.0)), 1),
                "dew_point_depression": round(float(features.get("dew_point_depression", 0.0)), 1),
                "precip_last_3hr": round(float(features.get("precip_last_3hr", 0.0)), 2),
                "pressure_trend": round(float(features.get("pressure_trend", 0.0)), 2),
            }

            pred = ThunderstormPrediction(
                latitude=lat,
                longitude=lon,
                timestamp=now,
                prediction_time=prediction_time,
                input_time_ist=input_time_ist_str,
                valid_from=valid_from,
                valid_until=valid_until,
                lead_time_hours=float(lead_hour),
                thunderstorm_probability=round(ts_prob, 4),
                severity=severity_enum,
                lightning_probability=round(lt_prob, 4),
                confidence=scaled_confidence,
                input_conditions=input_conditions,
                contributing_factors=contributing_factors,
                extrapolated_lead_time=is_extrapolated,
                lead_time_note=lead_note,
                stale=is_stale,
                cached_at=cached_at,
                stale_reason=stale_reason,
            )
            results.append(pred)

        return results

    async def predict_for_cities(
        self,
        cities: List[Dict[str, Any]],
        force_refresh: bool = False,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generate nowcasts for multiple cities using a SINGLE batched Open-Meteo HTTP request.
        Utilizes 15-minute TTL caching.
        """
        if not force_refresh:
            cached = meteo_cache.get_cities_nowcast()
            if cached is not None:
                data, is_stale, cached_at = cached
                if not is_stale:
                    return data

        # Ingest weather for all cities in a single batched network call
        city_weather_list, is_stale, cached_at, stale_reason = await self.data_service.fetch_multiple_cities(
            cities, force_refresh=force_refresh
        )

        results_dict: Dict[str, List[Dict[str, Any]]] = {}
        now = datetime.now(timezone.utc)

        for item in city_weather_list:
            city_name = item.get("city", "Unknown")
            lat = item.get("lat")
            lon = item.get("lon")
            weather_data = item.get("data")

            if not weather_data:
                results_dict[city_name] = [{"error": "Weather data unavailable"}]
                continue

            city_preds = []
            for lead_hour in [0.0, 1.0, 2.0, 3.0, 6.0]:
                target_hour_index = max(0, int(lead_hour))
                try:
                    features, row_dt_ist = self.feature_engineer.build_feature_vector(
                        weather_data=weather_data,
                        lat=lat,
                        lon=lon,
                        timestamp=now,
                        target_hour_index=target_hour_index,
                    )
                except Exception as e:
                    logger.error(f"Error building feature vector for city {city_name} lead +{lead_hour}h: {e}")
                    continue

                ts_prob, ts_conf, _ = self.ts_model.predict(features)
                lead_factor = max(0.60, 1.0 - (lead_hour / 6.0) * 0.40)
                scaled_confidence = round(float(ts_conf * lead_factor), 4)

                valid_from = row_dt_ist.astimezone(timezone.utc)
                valid_until = (row_dt_ist + timedelta(hours=1)).astimezone(timezone.utc)
                prediction_time = valid_from
                input_time_ist_str = row_dt_ist.isoformat()

                is_extrapolated = lead_hour >= 1.0
                lead_note = (
                    f"extrapolated lead time using forecast NWP inputs (valid {row_dt_ist.strftime('%H:%M')} to {(row_dt_ist + timedelta(hours=1)).strftime('%H:%M')} IST; model trained on 1-hour ahead nowcast)"
                    if is_extrapolated
                    else f"t+1h nowcast using current-hour model data (valid {row_dt_ist.strftime('%H:%M')} to {(row_dt_ist + timedelta(hours=1)).strftime('%H:%M')} IST)"
                )

                lt_prob, _ = self.lt_model.predict(features, ts_prob)

                severity_str = self.severity.classify(ts_prob)
                try:
                    severity_enum = SeverityLevel(severity_str)
                except ValueError:
                    severity_enum = SeverityLevel.none

                input_conditions = {
                    "cape_index_derived": round(float(features.get("cape", 0.0)), 1),
                    "cin_index_derived": round(float(features.get("cin", 0.0)), 1),
                    "pw_index_derived": round(float(features.get("precipitable_water", 0.0)), 1),
                    "temperature_2m": round(float(features.get("temperature_2m", 0.0)), 1),
                    "relative_humidity": round(float(features.get("relative_humidity", 0.0)), 1),
                    "cloud_cover": round(float(features.get("cloud_cover", 0.0)), 1),
                    "wind_speed_10m": round(float(features.get("wind_speed_10m", 0.0)), 1),
                    "precip_1hr_ago": round(float(features.get("precip_1hr_ago", 0.0)), 2),
                    "precip_last_3hr": round(float(features.get("precip_last_3hr", 0.0)), 2),
                    "pressure_trend": round(float(features.get("pressure_trend", 0.0)), 2),
                    "dew_point_depression": round(float(features.get("dew_point_depression", 0.0)), 1),
                }

                contributing_factors = {
                    "cape": round(float(features.get("cape", 0.0)), 1),
                    "cin": round(float(features.get("cin", 0.0)), 1),
                    "precipitable_water": round(float(features.get("precipitable_water", 0.0)), 1),
                    "relative_humidity": round(float(features.get("relative_humidity", 0.0)), 1),
                    "dew_point_depression": round(float(features.get("dew_point_depression", 0.0)), 1),
                    "precip_last_3hr": round(float(features.get("precip_last_3hr", 0.0)), 2),
                    "pressure_trend": round(float(features.get("pressure_trend", 0.0)), 2),
                }

                pred = ThunderstormPrediction(
                    latitude=lat,
                    longitude=lon,
                    timestamp=now,
                    prediction_time=prediction_time,
                    input_time_ist=input_time_ist_str,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    lead_time_hours=float(lead_hour),
                    thunderstorm_probability=round(ts_prob, 4),
                    severity=severity_enum,
                    lightning_probability=round(lt_prob, 4),
                    confidence=scaled_confidence,
                    input_conditions=input_conditions,
                    contributing_factors=contributing_factors,
                    extrapolated_lead_time=is_extrapolated,
                    lead_time_note=lead_note,
                    stale=is_stale,
                    cached_at=cached_at,
                    stale_reason=stale_reason,
                )
                city_preds.append(pred.model_dump())

            results_dict[city_name] = city_preds

        meteo_cache.set_cities_nowcast(results_dict)
        return results_dict
