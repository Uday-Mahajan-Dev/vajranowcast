"""Precompute spatial nowcast grid, cities nowcast, and active alerts dataset for GitHub Pages CDN publishing."""

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend root to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import httpx
from app.ml.models.thunderstorm_model import (
    LightningPredictor,
    SeverityClassifier,
    ThunderstormClassifier,
)
from app.services.feature_engineering import FeatureEngineer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vajranowcast.precompute")

MASK_FILE = backend_dir / "app" / "data" / "india_land_mask.json"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
BATCH_SIZE = 35  # 70 points / 35 = 2 requests per run

INDIAN_CITIES = [
    {"name": "Delhi", "lat": 28.61, "lon": 77.21},
    {"name": "Mumbai", "lat": 19.08, "lon": 72.88},
    {"name": "Kolkata", "lat": 22.57, "lon": 88.36},
    {"name": "Chennai", "lat": 13.08, "lon": 80.27},
    {"name": "Bengaluru", "lat": 12.97, "lon": 77.59},
    {"name": "Hyderabad", "lat": 17.39, "lon": 78.49},
    {"name": "Jaipur", "lat": 26.91, "lon": 75.79},
    {"name": "Lucknow", "lat": 26.85, "lon": 80.95},
    {"name": "Guwahati", "lat": 26.14, "lon": 91.74},
    {"name": "Nagpur", "lat": 21.15, "lon": 79.09},
]


async def fetch_batch_weather(
    client: httpx.AsyncClient,
    points: list[dict],
) -> list[dict]:
    """Fetch weather for a batch of coordinates using Open-Meteo multi-location API."""
    lats_str = ",".join(str(p["latitude"]) for p in points)
    lons_str = ",".join(str(p["longitude"]) for p in points)

    params = {
        "latitude": lats_str,
        "longitude": lons_str,
        "current": (
            "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,"
            "wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code"
        ),
        "hourly": (
            "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,"
            "wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,"
            "precipitation_probability,cape,convective_inhibition,"
            "total_column_integrated_water_vapour,weather_code"
        ),
        "forecast_days": 1,
        "past_days": 1,
        "timezone": "Asia/Kolkata",
    }

    response = await client.get(OPEN_METEO_URL, params=params)
    response.raise_for_status()
    raw = response.json()
    if isinstance(raw, list):
        return raw
    return [raw]


def atomic_write_json(filepath: Path, payload: dict) -> None:
    """Atomically write JSON payload to prevent partial reads."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(dir=filepath.parent, prefix="pub_", suffix=".tmp")
    with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(temp_path, filepath)


async def run_precomputation(output_dir: Path) -> bool:
    """
    Generate grid_latest.json, cities_latest.json, and alerts_latest.json
    without creating git commits or triggering server redeployments.
    """
    if not MASK_FILE.exists():
        logger.error(f"Land mask file not found: {MASK_FILE}")
        return False

    with open(MASK_FILE, "r", encoding="utf-8") as f:
        mask_data = json.load(f)

    points = mask_data.get("points", [])
    if not points:
        logger.error("No points found in land mask.")
        return False

    logger.info(f"Loaded {len(points)} grid points for India precomputation.")
    fe = FeatureEngineer()
    ts_model = ThunderstormClassifier()
    lt_model = LightningPredictor()
    sev_classifier = SeverityClassifier()
    now = datetime.now(timezone.utc)

    # 1. Fetch grid atmospheric conditions in batches
    grid_weather = []
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            for i in range(0, len(points), BATCH_SIZE):
                batch_points = points[i : i + BATCH_SIZE]
                logger.info(f"Fetching grid batch {i // BATCH_SIZE + 1} ({len(batch_points)} points)...")
                batch_res = await fetch_batch_weather(client, batch_points)
                grid_weather.extend(batch_res)
                if i + BATCH_SIZE < len(points):
                    await asyncio.sleep(0.5)

            # Ingest cities batch
            cities_points = [{"latitude": c["lat"], "longitude": c["lon"]} for c in INDIAN_CITIES]
            logger.info("Fetching 10 metro cities batch...")
            cities_weather = await fetch_batch_weather(client, cities_points)

    except Exception as e:
        logger.error(f"Network error during precomputation batch fetch: {e}")
        return False

    if len(grid_weather) < len(points):
        logger.error(f"Incomplete grid data received ({len(grid_weather)}/{len(points)}). Aborting.")
        return False

    # 2. Build Grid Predictions
    grid_points = []
    for point_meta, weather in zip(points, grid_weather):
        lat = point_meta["latitude"]
        lon = point_meta["longitude"]

        if "hourly" in weather and "total_column_integrated_water_vapour" in weather["hourly"]:
            weather["hourly"]["precipitable_water"] = weather["hourly"]["total_column_integrated_water_vapour"]

        try:
            features, _ = fe.build_feature_vector(
                weather_data=weather,
                lat=lat,
                lon=lon,
                timestamp=now,
                target_hour_index=1,
            )
        except Exception as e:
            logger.error(f"Failed to build canonical feature vector for grid point ({lat}, {lon}): {e}")
            continue

        ts_prob, ts_conf, _ = ts_model.predict(features)
        lt_prob, _ = lt_model.predict(features, ts_prob)
        severity_str = sev_classifier.classify(ts_prob)

        grid_points.append({
            "latitude": lat,
            "longitude": lon,
            "region": point_meta.get("region", "India"),
            "thunderstorm_probability": round(float(ts_prob), 4),
            "severity": severity_str,
            "lightning_probability": round(float(lt_prob), 4),
            "confidence": round(float(ts_conf), 4),
            "cape": round(float(features.get("cape", 0.0)), 1),
            "cin": round(float(features.get("cin", 0.0)), 1),
            "precipitable_water": round(float(features.get("precipitable_water", 0.0)), 1),
        })

    grid_payload = {
        "generated_at": now.isoformat(),
        "valid_until": (now + timedelta(hours=1)).isoformat(),
        "lead_time_hours": 1.0,
        "total_points": len(grid_points),
        "resolution_deg": mask_data.get("resolution_degrees", 1.6),
        "grid_resolution_km": mask_data.get("grid_resolution_km", 175.0),
        "stale": False,
        "stale_reason": None,
        "points": grid_points,
        "disclaimer": "Experimental AI nowcast product — not an official IMD weather warning.",
    }

    # 3. Build Cities Predictions
    cities_payload = {
        "generated_at": now.isoformat(),
        "valid_until": (now + timedelta(hours=1)).isoformat(),
        "cities_count": len(INDIAN_CITIES),
        "cities": {},
        "disclaimer": "Experimental AI nowcast product — not an official IMD weather warning.",
    }

    alerts_list = []
    for city_meta, weather in zip(INDIAN_CITIES, cities_weather):
        c_name = city_meta["name"]
        c_lat = city_meta["lat"]
        c_lon = city_meta["lon"]

        if "hourly" in weather and "total_column_integrated_water_vapour" in weather["hourly"]:
            weather["hourly"]["precipitable_water"] = weather["hourly"]["total_column_integrated_water_vapour"]

        city_preds = []
        for lead_h in [0.0, 1.0, 2.0, 3.0, 6.0]:
            h_idx = int(lead_h)
            try:
                feats, row_dt_ist = fe.build_feature_vector(weather, c_lat, c_lon, now, h_idx)
            except Exception as e:
                logger.error(f"Failed to build canonical feature vector for city {c_name} lead +{lead_h}h: {e}")
                continue

            p_ts, conf_ts, _ = ts_model.predict(feats)
            p_lt, _ = lt_model.predict(feats, p_ts)
            sev = sev_classifier.classify(p_ts)

            city_preds.append({
                "latitude": c_lat,
                "longitude": c_lon,
                "timestamp": now.isoformat(),
                "prediction_time": (now + timedelta(hours=lead_h)).isoformat(),
                "lead_time_hours": lead_h,
                "thunderstorm_probability": round(float(p_ts), 4),
                "severity": sev,
                "lightning_probability": round(float(p_lt), 4),
                "confidence": round(float(conf_ts), 4),
                "contributing_factors": {
                    "cape": round(float(feats.get("cape", 0.0)), 1),
                    "cin": round(float(feats.get("cin", 0.0)), 1),
                },
            })

            # Check for alert condition at 1h lead time
            if lead_h == 1.0 and p_ts >= 0.60:
                alerts_list.append({
                    "city": c_name,
                    "latitude": c_lat,
                    "longitude": c_lon,
                    "alert_type": "thunderstorm",
                    "severity": sev,
                    "thunderstorm_probability": round(float(p_ts), 4),
                    "lightning_probability": round(float(p_lt), 4),
                    "valid_from": now.isoformat(),
                    "valid_until": (now + timedelta(hours=2)).isoformat(),
                    "message": f"⚠️ {sev.upper()} thunderstorm expected in {c_name} within 1h (Probability: {int(p_ts*100)}%)",
                    "is_active": True,
                })

        cities_payload["cities"][c_name] = city_preds

    alerts_payload = {
        "generated_at": now.isoformat(),
        "total_active_alerts": len(alerts_list),
        "alerts": alerts_list,
        "disclaimer": "Experimental AI nowcast product — not an official IMD weather warning.",
    }

    # 4. Atomic writes to destination directory
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / "grid_latest.json", grid_payload)
    atomic_write_json(output_dir / "cities_latest.json", cities_payload)
    atomic_write_json(output_dir / "alerts_latest.json", alerts_payload)

    logger.info(f"Successfully published precomputed artifacts to {output_dir}")

    # 5. If backend URL and Admin Token are provided, wake Render and post precomputed alerts
    if backend_url and admin_token:
        logger.info(f"Triggering Render alert generation at {backend_url}...")
        await wake_render_and_generate_alerts(backend_url, admin_token, cities_payload)

    return True


async def wake_render_and_generate_alerts(
    backend_url: str,
    admin_token: str,
    cities_payload: dict,
) -> bool:
    """
    Ping /health on Render (up to 3 retries, 30s apart) to wake sleeping instance,
    then POST precomputed city predictions with X-Admin-Token to /api/v1/alerts/generate.
    """
    health_url = f"{backend_url.rstrip('/')}/health"
    generate_url = f"{backend_url.rstrip('/')}/api/v1/alerts/generate"

    logger.info(f"Connecting to Render backend at {backend_url}...")
    async with httpx.AsyncClient(timeout=45.0) as client:
        # Step 1: Health check retry loop (wake-up)
        healthy = False
        for attempt in range(1, 4):
            try:
                logger.info(f"Health check attempt {attempt}/3 at {health_url}...")
                resp = await client.get(health_url)
                if resp.status_code == 200:
                    logger.info("Render backend is awake and healthy.")
                    healthy = True
                    break
                else:
                    logger.warning(f"Health check returned status {resp.status_code}")
            except Exception as e:
                logger.warning(f"Health check attempt {attempt} failed: {e}")

            if attempt < 3:
                logger.info("Waiting 30 seconds for Render instance to spin up...")
                await asyncio.sleep(30)

        if not healthy:
            logger.error("Render backend did not respond to health checks. Cannot post alerts.")
            return False

        # Step 2: POST precomputed city predictions
        headers = {
            "Content-Type": "application/json",
            "X-Admin-Token": admin_token,
        }
        body = {
            "cities": cities_payload.get("cities", {}),
        }
        try:
            logger.info(f"Posting precomputed city predictions to {generate_url}...")
            post_resp = await client.post(generate_url, json=body, headers=headers)
            if post_resp.status_code == 200:
                logger.info(f"Successfully triggered alert generation on Render: {post_resp.json()}")
                return True
            else:
                logger.error(f"Alert generation failed with status {post_resp.status_code}: {post_resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to post alert generation request: {e}")
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate precomputed nowcasting datasets for Pages CDN")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(backend_dir / "public_pages"),
        help="Target output directory for JSON artifacts",
    )
    parser.add_argument(
        "--backend-url",
        type=str,
        default=os.environ.get("RENDER_BACKEND_URL") or os.environ.get("BACKEND_URL") or os.environ.get("VAJRA_BACKEND_URL"),
        help="Backend URL to wake and post precomputed alerts to",
    )
    parser.add_argument(
        "--admin-token",
        type=str,
        default=os.environ.get("ADMIN_TOKEN") or os.environ.get("X_ADMIN_TOKEN"),
        help="X-Admin-Token for authenticating alert generation",
    )
    args = parser.parse_args()
    success = asyncio.run(run_precomputation(Path(args.output_dir), args.backend_url, args.admin_token))
    sys.exit(0 if success else 1)

