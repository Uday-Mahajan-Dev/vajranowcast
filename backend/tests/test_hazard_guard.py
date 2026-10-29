"""Tests for Severe Weather Guard rule-based hazard evaluation."""

import pytest
from app.services.hazard_guard import evaluate_hazards, HazardResult


@pytest.fixture
def cyclone_hourly():
    """6-hour cyclone landfall fixture matching Cyclone Arnab conditions."""
    return {
        "time": [f"2026-10-29T{h:02d}:00" for h in range(6)],
        "temperature_2m": [24.0, 24.0, 24.0, 23.8, 23.5, 23.2],
        "dew_point_2m": [23.2, 23.2, 23.2, 23.0, 22.8, 22.6],
        "relative_humidity_2m": [96.0, 96.0, 96.0, 97.0, 97.0, 98.0],
        "precipitation": [10.0, 12.0, 15.0, 18.0, 21.0, 22.0],
        "wind_speed_10m": [70.0, 72.0, 74.0, 76.0, 78.0, 80.0],
        "surface_pressure": [996.0, 994.0, 992.0, 990.0, 989.0, 988.0],
        "weather_code": [65.0, 65.0, 65.0, 65.0, 65.0, 65.0],
    }


@pytest.fixture
def calm_hourly():
    """Calm summer afternoon fixture."""
    return {
        "time": [f"2026-05-15T{h:02d}:00" for h in range(6)],
        "temperature_2m": [30.0, 31.0, 32.0, 31.5, 30.5, 29.5],
        "dew_point_2m": [18.0, 18.5, 19.0, 19.0, 18.5, 18.0],
        "relative_humidity_2m": [50.0, 48.0, 47.0, 49.0, 52.0, 55.0],
        "precipitation": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "wind_speed_10m": [10.0, 12.0, 10.0, 8.0, 10.0, 9.0],
        "surface_pressure": [1008.0, 1007.5, 1007.0, 1007.2, 1007.8, 1008.0],
        "weather_code": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    }


def test_cyclone_fixture_triggers_warning_and_out_of_range(cyclone_hourly):
    """
    Cyclone fixture: 6 hours, T=24, Td=23.2, RH=96, rain=10->22 mm/h, wind=70->80 km/h,
    pressure 996->988, weather_code 65.
    Expect hazard_tier="warning", flags include "cyclonic_gale" and "very_heavy_rain",
    out_of_training_range=True.
    """
    # Evaluate at index 4 (rain 21 mm/h, t+1 rain 22 mm/h, wind 78-80 km/h)
    res = evaluate_hazards(cyclone_hourly, target_idx=4)
    assert res.hazard_tier == "warning"
    assert "cyclonic_gale" in res.hazard_flags
    assert "very_heavy_rain" in res.hazard_flags
    assert res.out_of_training_range is True
    assert len(res.reasons) >= 2


def test_calm_fixture_produces_no_hazard_tier(calm_hourly):
    """
    Calm fixture (T=30, RH=50, rain 0, wind 10, code 0) -> hazard_tier None,
    out_of_training_range False.
    """
    res = evaluate_hazards(calm_hourly, target_idx=2)
    assert res.hazard_tier is None
    assert len(res.hazard_flags) == 0
    assert len(res.reasons) == 0
    assert res.out_of_training_range is False


def test_weather_code_95_at_t_plus_1_triggers_advisory(calm_hourly):
    """
    Weather code 95 at t+1 only -> 'advisory' hazard_tier with 'thunderstorm_forecast'.
    """
    hourly = {k: list(v) for k, v in calm_hourly.items()}
    # Code is 0 at t=1, 95 at t+1=2
    hourly["weather_code"][1] = 0.0
    hourly["weather_code"][2] = 95.0

    res = evaluate_hazards(hourly, target_idx=1)
    assert res.hazard_tier == "advisory"
    assert "thunderstorm_forecast" in res.hazard_flags


def test_missing_wind_gusts_does_not_raise(calm_hourly):
    """
    Missing wind_gusts_10m must not raise and behaves normally.
    """
    assert "wind_gusts_10m" not in calm_hourly
    res = evaluate_hazards(calm_hourly, target_idx=0)
    assert isinstance(res, HazardResult)
    assert res.hazard_tier is None


def test_damaging_wind_gusts_triggers_warning(calm_hourly):
    """
    Wind gusts >= 90 km/h trigger damaging_gusts warning.
    """
    hourly = {k: list(v) for k, v in calm_hourly.items()}
    hourly["wind_gusts_10m"] = [45.0, 95.0, 40.0, 30.0, 20.0, 10.0]
    res = evaluate_hazards(hourly, target_idx=0)
    assert res.hazard_tier == "warning"
    assert "damaging_gusts" in res.hazard_flags


def test_rapid_pressure_fall_triggers_watch(calm_hourly):
    """
    Pressure fall >= 3 hPa over 3 hours with precipitation >= 2 mm/h triggers rapid_pressure_fall watch.
    """
    hourly = {k: list(v) for k, v in calm_hourly.items()}
    hourly["surface_pressure"] = [1010.0, 1008.0, 1006.0, 1005.0, 1004.0, 1003.0]
    hourly["precipitation"] = [0.0, 0.5, 1.0, 3.5, 2.0, 1.0]

    res = evaluate_hazards(hourly, target_idx=3)
    assert "rapid_pressure_fall" in res.hazard_flags
    assert res.hazard_tier in ("watch", "advisory", "warning")


def test_nowcast_from_data_cyclone_integration():
    """
    Integration test: POST /api/v1/predictions/nowcast-from-data with the cyclone fixture
    at Kakinada (16.95, 82.24) -> thunderstorm_probability unchanged from the raw model (< 0.05),
    display_tier="warning", tier_source="hazard_guard".
    """
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    times = [(base_time + timedelta(hours=h - 24)).strftime("%Y-%m-%dT%H:00") for h in range(72)]

    payload = {
        "latitude": 16.95,
        "longitude": 82.24,
        "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "hourly": {
            "time": times,
            "temperature_2m": [24.0] * 72,
            "relative_humidity_2m": [96.0] * 72,
            "dew_point_2m": [23.2] * 72,
            "surface_pressure": [996.0 - min(h, 8) * 1.0 for h in range(72)],
            "wind_speed_10m": [74.0] * 72,
            "wind_direction_10m": [80.0] * 72,
            "cloud_cover": [100.0] * 72,
            "precipitation": [22.0] * 72,
            "weather_code": [65.0] * 72,
        },
    }

    res = client.post(
        "/api/v1/predictions/nowcast-from-data",
        params={"lead_hours": "1"},
        json=payload,
    )
    assert res.status_code == 200, f"Error: {res.text}"
    data = res.json()
    assert "predictions" in data
    pred = data["predictions"][0]

    from app.config import settings
    if settings.MODEL_VERSION.lower() == "v2":
        # v2 learned cool rain: raw ML probability detects the cyclone (~0.74)
        assert pred["thunderstorm_probability"] >= 0.50, f"Expected v2 ML prob >= 0.50, got {pred['thunderstorm_probability']}"
        assert pred["display_tier"] == "warning"
        assert pred["tier_source"] in ("ml", "hazard_guard")
    else:
        # v1: model probability remains uninflated (< 0.05), operational tier promoted by hazard guard
        assert pred["thunderstorm_probability"] < 0.05, f"Expected raw ML prob < 0.05, got {pred['thunderstorm_probability']}"
        assert pred["display_tier"] == "warning"
        assert pred["tier_source"] == "hazard_guard"

    assert pred["out_of_training_range"] is True
    assert "cyclonic_gale" in pred["hazard_flags"]
    assert "very_heavy_rain" in pred["hazard_flags"]
    assert len(pred["hazard_reasons"]) > 0


def test_out_of_training_range_model_version_aware():
    """
    Test that out_of_training_range is model-version aware:
    - Case: 23 °C, 5 mm/h rain, 30 km/h wind, 1005 hPa pressure.
      Must be False under v2 (trained on cool rain) and True under v1 (cliff below 25 °C).
    - Extreme wind (>= 62 km/h) or pressure (< 995 hPa) must trigger out_of_training_range=True
      under both v1 and v2.
    """
    cool_rain_hourly = {
        "time": ["2026-10-29T00:00", "2026-10-29T01:00"],
        "temperature_2m": [23.0, 23.0],
        "dew_point_2m": [22.0, 22.0],
        "relative_humidity_2m": [95.0, 95.0],
        "precipitation": [5.0, 5.0],
        "wind_speed_10m": [30.0, 30.0],
        "surface_pressure": [1005.0, 1005.0],
        "weather_code": [61.0, 61.0],
    }

    # Under v1: True (rain >= 2 mm/h with temp <= 25 °C was outside v1 training domain)
    res_v1 = evaluate_hazards(cool_rain_hourly, target_idx=0, model_version="v1")
    assert res_v1.out_of_training_range is True

    # Under v2: False (cool rain was included in v2 training)
    res_v2 = evaluate_hazards(cool_rain_hourly, target_idx=0, model_version="v2")
    assert res_v2.out_of_training_range is False

    # Extreme wind (e.g. 65 km/h >= 62 km/h) triggers out_of_training_range on both
    extreme_wind_hourly = {k: list(v) for k, v in cool_rain_hourly.items()}
    extreme_wind_hourly["wind_speed_10m"] = [65.0, 65.0]
    assert evaluate_hazards(extreme_wind_hourly, target_idx=0, model_version="v1").out_of_training_range is True
    assert evaluate_hazards(extreme_wind_hourly, target_idx=0, model_version="v2").out_of_training_range is True

    # Extreme low pressure (e.g. 990 hPa < 995 hPa) triggers out_of_training_range on both
    extreme_press_hourly = {k: list(v) for k, v in cool_rain_hourly.items()}
    extreme_press_hourly["surface_pressure"] = [990.0, 990.0]
    assert evaluate_hazards(extreme_press_hourly, target_idx=0, model_version="v1").out_of_training_range is True
    assert evaluate_hazards(extreme_press_hourly, target_idx=0, model_version="v2").out_of_training_range is True


