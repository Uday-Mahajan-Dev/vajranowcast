"""Scan Open-Meteo archive across the 10 training cities for pre-monsoon months (Apr-Jun 2022-2024),
find hours where label rule fired at t+1 AND P(TS) >= 0.186 at t, and display candidate hit events."""

import asyncio
from datetime import datetime
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding="utf-8")
import httpx
import joblib
import numpy as np
import pandas as pd

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.training_features import (
    CLEAN_FEATURE_COLS,
    engineer_training_features_df,
)

CITIES = [
    {"name": "Kolkata", "state": "West Bengal", "lat": 22.57, "lon": 88.36},
    {"name": "Guwahati", "state": "Assam", "lat": 26.14, "lon": 91.74},
    {"name": "Mumbai", "state": "Maharashtra", "lat": 19.08, "lon": 72.88},
    {"name": "Nagpur", "state": "Maharashtra", "lat": 21.15, "lon": 79.09},
    {"name": "Hyderabad", "state": "Telangana", "lat": 17.39, "lon": 78.49},
    {"name": "Chennai", "state": "Tamil Nadu", "lat": 13.08, "lon": 80.27},
    {"name": "Delhi", "state": "National Capital Region", "lat": 28.61, "lon": 77.21},
    {"name": "Lucknow", "state": "Uttar Pradesh", "lat": 26.85, "lon": 80.95},
    {"name": "Jaipur", "state": "Rajasthan", "lat": 26.91, "lon": 75.79},
    {"name": "Bengaluru", "state": "Karnataka", "lat": 12.97, "lon": 77.59},
]

SEASONS = [
    ("2024-04-01", "2024-06-30"),
    ("2023-04-01", "2023-06-30"),
    ("2022-04-01", "2022-06-30"),
]


async def scan_city(client: httpx.AsyncClient, city: dict, model, optimal_thresh: float) -> list[dict]:
    found_hits = []
    for start_date, end_date in SEASONS:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": city["lat"],
            "longitude": city["lon"],
            "start_date": start_date,
            "end_date": end_date,
            "hourly": (
                "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,"
                "wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code"
            ),
            "timezone": "Asia/Kolkata",
        }
        try:
            res = await client.get(url, params=params, timeout=30.0)
            res.raise_for_status()
            data = res.json()
            hourly = data.get("hourly", {})
            if not hourly or "time" not in hourly:
                continue

            df = pd.DataFrame(hourly)
            df["city"] = city["name"]
            df["latitude"] = city["lat"]
            df["longitude"] = city["lon"]

            feat_df = engineer_training_features_df(df)
            feat_df["target_lead_1h"] = feat_df["thunderstorm"].shift(-1)

            X = feat_df[CLEAN_FEATURE_COLS].values
            probs = model.predict_proba(X)[:, 1]
            feat_df["prob"] = probs

            # Find hours where model predicted storm (prob >= optimal_thresh) AND storm occurred at t+1
            hits = feat_df[(feat_df["target_lead_1h"] == 1) & (feat_df["prob"] >= optimal_thresh)]

            for _, row in hits.iterrows():
                t_dt = pd.to_datetime(row["time"])
                found_hits.append({
                    "city": city["name"],
                    "state": city["state"],
                    "latitude": city["lat"],
                    "longitude": city["lon"],
                    "time_ist": row["time"],
                    "date": t_dt.strftime("%Y-%m-%d"),
                    "hour_ist": f"{t_dt.strftime('%H:00')} IST",
                    "hour_idx": t_dt.hour,
                    "prob": float(row["prob"]),
                    "precip_t": float(row["precipitation"]),
                    "temp_t": float(row["temperature_2m"]),
                    "rh_t": float(row["relative_humidity"]),
                    "features": {col: float(row[col]) for col in CLEAN_FEATURE_COLS},
                })
        except Exception as e:
            print(f"Error scanning {city['name']} for {start_date}..{end_date}: {e}")

    return found_hits


async def main():
    model_path = backend_dir / "app" / "ml" / "saved_models" / "thunderstorm_model.pkl"
    model = joblib.load(model_path)
    thresh = 0.1860

    print("Scanning Open-Meteo archive for certified Hit events (P(TS) >= 0.186 and storm at t+1)...")

    all_hits = {}
    async with httpx.AsyncClient() as client:
        for city in CITIES:
            hits = await scan_city(client, city, model, thresh)
            if hits:
                all_hits[city["name"]] = hits
                print(f"✓ {city['name']}: Found {len(hits)} certified HIT events")

    print("\n" + "=" * 80)
    print("TOP HIT CANDIDATES PER CITY:")
    print("=" * 80)
    for city_name, hits in all_hits.items():
        sorted_hits = sorted(hits, key=lambda x: x["prob"], reverse=True)
        top = sorted_hits[0]
        print(f"\nCity: {top['city']} ({top['state']})")
        print(f"  - Replay Hour (t): {top['time_ist']} (P(TS) = {top['prob']:.4f})")
        print(f"  - Storm Verified at t+1: YES (Label=1)")
        print(f"  - Features: CAPE={top['features']['cape']:.1f}, CIN={top['features']['cin']:.1f}, RH={top['features']['relative_humidity']:.1f}%, Temp={top['features']['temperature_2m']:.1f}°C")


if __name__ == "__main__":
    asyncio.run(main())
