"""Application configuration management using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase credentials
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # Server configurations
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Data source URLs
    OPEN_METEO_URL: str = "https://api.open-meteo.com/v1/forecast"
    OPEN_METEO_ARCHIVE_URL: str = "https://archive-api.open-meteo.com/v1/archive"
    GFS_NOMADS_URL: str = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"

    # India geographic boundaries
    INDIA_LAT_MIN: float = 6.0
    INDIA_LAT_MAX: float = 38.0
    INDIA_LON_MIN: float = 68.0
    INDIA_LON_MAX: float = 98.0

    # Model & Cache settings
    MODEL_DIR: str = "./app/ml/saved_models"
    CACHE_TTL_MINUTES: int = 15

    # Prediction & Alert thresholds
    ALERT_PROB_THRESHOLD: float = 0.6
    SEVERE_PROB_THRESHOLD: float = 0.75
    OPTIMAL_THRESHOLD: float = 0.1860


settings = Settings()
