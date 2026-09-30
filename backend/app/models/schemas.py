"""Pydantic v2 schemas and data models for VajraNowcast."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

DEFAULT_DISCLAIMER = "Experimental AI nowcast product — not an official IMD weather warning."


class SeverityLevel(str, Enum):
    """Storm severity classification levels."""
    none = "none"
    weak = "weak"
    moderate = "moderate"
    severe = "severe"
    very_severe = "very_severe"


class LocationInput(BaseModel):
    """Geographic coordinate input model."""
    latitude: float = Field(..., description="Latitude in decimal degrees (-90 to 90)")
    longitude: float = Field(..., description="Longitude in decimal degrees (-180 to 180)")


class ThunderstormPrediction(BaseModel):
    """Detailed thunderstorm prediction for a given location and lead time."""
    latitude: float
    longitude: float
    timestamp: datetime
    prediction_time: datetime
    input_time_ist: Optional[str] = Field(None, description="IST timestamp of the meteorological input row used (e.g. '2026-09-29T14:00:00+05:30')")
    valid_from: Optional[datetime] = Field(None, description="Start of prediction validity window")
    valid_until: Optional[datetime] = Field(None, description="End of prediction validity window")
    lead_time_hours: float
    thunderstorm_probability: float
    severity: SeverityLevel
    lightning_probability: float
    confidence: float
    input_conditions: Optional[dict[str, Any]] = Field(None, description="Physical atmospheric observations and stability indicators")
    contributing_factors: Optional[dict[str, Any]] = Field(None, description="Backward-compatible alias for input_conditions")
    extrapolated_lead_time: bool = Field(False, description="True if lead_time >= 1 hour (uses forecast NWP inputs beyond the 1-hour nowcast)")
    lead_time_note: Optional[str] = Field(None, description="Operational note regarding model validity horizon")
    stale: bool = Field(False, description="True if response is served from fallback cache due to rate-limit/network")
    cached_at: Optional[datetime] = None
    stale_reason: Optional[str] = Field(None, description="Reason why stale data was returned")
    disclaimer: str = DEFAULT_DISCLAIMER


class AlertResponse(BaseModel):
    """Active or generated severe weather alert structure."""
    alert_id: str
    city: str
    latitude: float
    longitude: float
    alert_type: str
    severity: SeverityLevel
    tier: Optional[str] = None  # "watch", "advisory", "warning"
    is_test: bool = False
    thunderstorm_probability: float
    lightning_probability: float
    valid_from: datetime
    valid_until: datetime
    message: str
    is_active: bool
    disclaimer: str = DEFAULT_DISCLAIMER


class TestAlertRequest(BaseModel):
    """Staff payload to create a drill/test alert."""
    city: str
    tier: str = "warning"  # "watch", "advisory", "warning"
    lead_time_hours: float = 1.0


class GenerateAlertsRequest(BaseModel):
    """Optional payload for alert generation with precomputed city predictions."""
    cities: Optional[Dict[str, List[Any]]] = None


class NowcastResponse(BaseModel):
    """Nowcast response payload containing predictions and metadata."""
    request_time: datetime
    predictions: list[ThunderstormPrediction]
    metadata: dict[str, Any]
    stale: bool = Field(False, description="True if results were served from stale cache")
    cached_at: Optional[datetime] = None
    disclaimer: str = DEFAULT_DISCLAIMER


class DataSourceStatus(BaseModel):
    """Health and operational status of a meteorological data source."""
    source_name: str
    status: str
    last_updated: str
    variables: list[str]


class HistoricalResponse(BaseModel):
    """Historical thunderstorm verification response comparing prediction with observed outcome."""
    request_time: datetime
    date: str
    hour: int
    prediction: ThunderstormPrediction
    actual_weather_code: Optional[int] = None
    actual_was_thunderstorm: Optional[bool] = None
    disclaimer: str = DEFAULT_DISCLAIMER


class GridPointPrediction(BaseModel):
    """Prediction item for a single point on the precomputed India spatial grid."""
    latitude: float
    longitude: float
    thunderstorm_probability: float
    severity: SeverityLevel
    lightning_probability: float
    confidence: float
    cape: float
    cin: float
    precipitable_water: float


class GridResponse(BaseModel):
    """Precomputed regional thunderstorm nowcast grid response across India."""
    generated_at: datetime
    valid_until: datetime
    lead_time_hours: float = 1.0
    total_points: int
    resolution_deg: float = 1.6
    grid_resolution_km: float = 175.0
    stale: bool = False
    stale_reason: Optional[str] = None
    points: list[GridPointPrediction]
    disclaimer: str = DEFAULT_DISCLAIMER


class HistoricalReplayEvent(BaseModel):
    """Curated real historical convective event metadata."""
    event_id: str
    event_name: str
    city: str
    state: str
    latitude: float
    longitude: float
    date: str
    hour_ist: str
    hour_utc: str
    synoptic_summary: str
    source: str
    source_url: str
    computed_verdict: Optional[str] = None
    verified_by_human: bool = False
    optimal_threshold: Optional[float] = 0.186
    features_vector: Optional[dict] = None
    prediction: Optional[dict] = None
    actual_outcome: Optional[dict] = None
    timeline: Optional[list[dict]] = None


# ----------------------------------------------------------------------
# Client Direct Open-Meteo Ingestion Schemas (POST /nowcast-from-data)
# ----------------------------------------------------------------------

class ClientHourlyData(BaseModel):
    """Strictly validated Open-Meteo hourly arrays for client-side ingestion."""
    time: List[str]
    temperature_2m: List[float]
    relative_humidity_2m: List[float]
    dew_point_2m: List[float]
    surface_pressure: List[float]
    wind_speed_10m: List[float]
    wind_direction_10m: List[float]
    cloud_cover: List[float]
    precipitation: List[float]
    weather_code: List[float]

    @model_validator(mode="after")
    def validate_arrays_and_ranges(self) -> "ClientHourlyData":
        n = len(self.time)
        if n < 1:
            raise ValueError("Hourly 'time' array cannot be empty.")
        if n > 120:
            raise ValueError(f"Hourly 'time' array length {n} exceeds maximum allowed (120).")

        fields = [
            ("temperature_2m", self.temperature_2m, -40.0, 60.0),
            ("relative_humidity_2m", self.relative_humidity_2m, 0.0, 100.0),
            ("dew_point_2m", self.dew_point_2m, -50.0, 50.0),
            ("surface_pressure", self.surface_pressure, 500.0, 1100.0),
            ("wind_speed_10m", self.wind_speed_10m, 0.0, 200.0),
            ("wind_direction_10m", self.wind_direction_10m, 0.0, 360.0),
            ("cloud_cover", self.cloud_cover, 0.0, 100.0),
            ("precipitation", self.precipitation, 0.0, 500.0),
            ("weather_code", self.weather_code, 0.0, 100.0),
        ]

        for fname, arr, min_v, max_v in fields:
            if len(arr) != n:
                raise ValueError(f"Field '{fname}' length ({len(arr)}) does not match 'time' length ({n}).")
            for i, val in enumerate(arr):
                if val is None or val < min_v or val > max_v:
                    raise ValueError(
                        f"Field '{fname}' element at index {i} ({val}) is out of sane range [{min_v}, {max_v}]."
                    )

        return self


class ClientOpenMeteoPayload(BaseModel):
    """Raw Open-Meteo forecast JSON payload sent directly from client browser."""
    latitude: float = Field(..., ge=6.0, le=38.0, description="Latitude in India domain (6.0 to 38.0)")
    longitude: float = Field(..., ge=68.0, le=98.0, description="Longitude in India domain (68.0 to 98.0)")
    timezone: str = Field(..., description="Timezone must be 'Asia/Kolkata'")
    utc_offset_seconds: int = Field(..., description="UTC offset must be 19800 (+05:30 IST)")
    hourly: ClientHourlyData
    elevation: Optional[float] = None
    generationtime_ms: Optional[float] = None
    timezone_abbreviation: Optional[str] = None
    hourly_units: Optional[Dict[str, str]] = None

    @model_validator(mode="after")
    def validate_timezone_spec(self) -> "ClientOpenMeteoPayload":
        if self.timezone != "Asia/Kolkata":
            raise ValueError(f"Invalid timezone '{self.timezone}'. Must be 'Asia/Kolkata'.")
        if self.utc_offset_seconds != 19800:
            raise ValueError(f"Invalid utc_offset_seconds '{self.utc_offset_seconds}'. Must be 19800.")
        return self


class CityPredictionItem(BaseModel):
    """Prediction item for a single city lead time in alert generation payload."""
    latitude: float = Field(..., ge=6.0, le=38.0)
    longitude: float = Field(..., ge=68.0, le=98.0)
    lead_time_hours: float = Field(..., ge=0.0, le=24.0)
    thunderstorm_probability: float = Field(..., ge=0.0, le=1.0)
    severity: str
    lightning_probability: Optional[float] = Field(0.0, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(0.5, ge=0.0, le=1.0)
    timestamp: Optional[str] = None
    prediction_time: Optional[str] = None
    contributing_factors: Optional[Dict[str, Any]] = None


class GenerateAlertsRequest(BaseModel):
    """Optional precomputed city predictions payload sent to POST /api/v1/alerts/generate."""
    cities: Dict[str, List[CityPredictionItem]]

