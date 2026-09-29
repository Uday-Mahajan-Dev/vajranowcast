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
    lead_time_hours: float
    thunderstorm_probability: float
    severity: SeverityLevel
    lightning_probability: float
    confidence: float
    contributing_factors: Optional[dict[str, Any]] = None
    disclaimer: str = DEFAULT_DISCLAIMER


class AlertResponse(BaseModel):
    """Active or generated severe weather alert structure."""
    alert_id: str
    city: str
    latitude: float
    longitude: float
    alert_type: str
    severity: SeverityLevel
    thunderstorm_probability: float
    lightning_probability: float
    valid_from: datetime
    valid_until: datetime
    message: str
    is_active: bool
    disclaimer: str = DEFAULT_DISCLAIMER


class NowcastResponse(BaseModel):
    """Nowcast response payload containing predictions and metadata."""
    request_time: datetime
    predictions: list[ThunderstormPrediction]
    metadata: dict[str, Any]
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
