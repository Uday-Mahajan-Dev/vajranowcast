"""Application configuration management using Pydantic Settings."""

from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_VERSION: str = "1.1.0"

    # Supabase credentials
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # Machine admin authentication
    ADMIN_TOKEN: str = "vajra_admin_secret_token_dev"

    # Server configurations
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    ALLOWED_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://vajranowcast.vercel.app",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Union[List[str], str]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Reverse proxy trusted configuration
    TRUSTED_PROXY: str = ""  # Set to "cloudflare" if behind Cloudflare
    TRUSTED_PROXY_HOPS: int = 1  # Number of trusted reverse proxy hops (e.g. 1 for Render)

    # Data source URLs
    OPEN_METEO_URL: str = "https://api.open-meteo.com/v1/forecast"
    OPEN_METEO_ARCHIVE_URL: str = "https://archive-api.open-meteo.com/v1/archive"
    GFS_NOMADS_URL: str = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    GITHUB_PAGES_BASE_URL: str = ""  # e.g. "https://uday-mahajan-dev.github.io/vajranowcast"

    # India geographic boundaries
    INDIA_LAT_MIN: float = 6.0
    INDIA_LAT_MAX: float = 38.0
    INDIA_LON_MIN: float = 68.0
    INDIA_LON_MAX: float = 98.0

    # Model & Cache settings
    MODEL_DIR: str = "./app/ml/saved_models"
    CACHE_TTL_MINUTES: int = 15

    # =========================================================================
    # Unified Prediction & Alert Thresholds
    # =========================================================================
    # OPTIMAL_THRESHOLD (0.1860):
    #   Statistical ML decision boundary tuned via Precision-Recall curve F1-score
    #   maximization on Colab validation set. Given extreme class imbalance (~1.5%
    #   positive thunderstorm prevalence), standard 0.50 cutoff fails. P(TS) >= 0.1860
    #   statistically signifies a positive convective storm prediction (Hit vs Miss).
    OPTIMAL_THRESHOLD: float = 0.1860

    # ALERT_PROB_THRESHOLD (0.60):
    #   Operational threshold for generating public severe weather alerts / banners.
    #   Requires substantial convective probability (>60%) to prevent warning fatigue.
    ALERT_PROB_THRESHOLD: float = 0.60

    # SEVERE_PROB_THRESHOLD (0.75):
    #   High-confidence threshold triggering severe/critical storm advisories.
    SEVERE_PROB_THRESHOLD: float = 0.75

    # Rate Limiting
    RATE_LIMIT_NOWCAST: str = "60/hour"
    RATE_LIMIT_CITIES: str = "30/hour"
    RATE_LIMIT_ALERTS: str = "10/hour"


settings = Settings()
