"""Pydantic v2 schemas and data models for VajraNowcast."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

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
    cached_at: Optional[datetime] = Field(None, description="Timestamp when the cached data was captured")
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
