import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from app.api.auth import init_jwks
from app.api.routes import alerts, predictions, weather
from app.config import settings
from app.core.limiter import limiter
from app.ml.models.thunderstorm_model import ThunderstormClassifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("vajranowcast.main")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware injecting mandatory HTTP security headers on all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    classifier = ThunderstormClassifier()
    logger.info(f"VajraNowcast v{settings.APP_VERSION} started. Model: {classifier.is_trained}, Threshold: {classifier.optimal_threshold}")
    # Prefetch JWKS public keys asynchronously
    await init_jwks()
    yield
    logger.info("VajraNowcast shutdown.")


app = FastAPI(
    title="VajraNowcast API",
    version=settings.APP_VERSION,
    description="AI-powered thunderstorm and lightning nowcasting for India",
    lifespan=lifespan,
)

# Attach rate limiter to application state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Restricted CORS origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(predictions.router, prefix="/api/v1/predictions", tags=["Predictions"])
app.include_router(weather.router, prefix="/api/v1/weather", tags=["Weather"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])


@app.get("/health")
async def health_check():
    classifier = ThunderstormClassifier()
    return {
        "status": "healthy",
        "service": "vajranowcast",
        "version": settings.APP_VERSION,
        "model_loaded": classifier.is_trained,
        "optimal_threshold": settings.OPTIMAL_THRESHOLD,
    }


@app.get("/")
async def root():
    return {
        "message": "VajraNowcast API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "endpoints": ["/api/v1/predictions/nowcast", "/api/v1/weather/current", "/api/v1/alerts/active"],
    }
