import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import alerts, predictions, weather
from app.config import settings
from app.ml.models.thunderstorm_model import ThunderstormClassifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("vajranowcast.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    classifier = ThunderstormClassifier()
    logger.info(f"VajraNowcast started. Model: {classifier.is_trained}, Threshold: {classifier.optimal_threshold}")
    yield
    logger.info("VajraNowcast shutdown.")


app = FastAPI(
    title="VajraNowcast API",
    version="1.0.0",
    description="AI-powered thunderstorm and lightning nowcasting for India",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
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
        "model_loaded": classifier.is_trained,
        "optimal_threshold": settings.OPTIMAL_THRESHOLD,
    }


@app.get("/")
async def root():
    return {
        "message": "VajraNowcast API",
        "docs": "/docs",
        "endpoints": ["/api/v1/predictions/nowcast", "/api/v1/weather/current", "/api/v1/alerts/active"],
    }
