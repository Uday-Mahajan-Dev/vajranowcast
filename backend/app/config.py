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
    # Unified Prediction & 3-Tier Alert Thresholds
    # =========================================================================
    # OPTIMAL_THRESHOLD (0.1860):
    #   Statistical ML decision boundary tuned via Precision-Recall curve F1-score
    #   maximization on Colab validation set. P(TS) >= 0.1860 signifies a positive storm prediction.
    OPTIMAL_THRESHOLD: float = 0.1860

    # 3 Alert Tiers:
    #   WATCH (>= 0.30): Convective storm conditions developing (8.9 alerts/city-mo, 47.3% precision)
    #   ADVISORY (>= 0.40): Heavy rain / localized downpour likely (6.4 alerts/city-mo, 51.2% precision)
    #   WARNING (>= 0.60): High-confidence severe convective storm expected (0.3 alerts/city-mo, 76.9% precision)
    ALERT_TIER_WATCH: float = 0.30
    ALERT_TIER_ADVISORY: float = 0.40
    ALERT_TIER_WARNING: float = 0.60

    # Backward compatibility alias (minimum probability to generate any alert tier)
    ALERT_PROB_THRESHOLD: float = 0.30
    SEVERE_PROB_THRESHOLD: float = 0.60

    # Rate Limiting
    RATE_LIMIT_NOWCAST: str = "60/hour"
    RATE_LIMIT_CITIES: str = "30/hour"
    RATE_LIMIT_ALERTS: str = "10/hour"


settings = Settings()
