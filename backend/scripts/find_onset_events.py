"""Scan Open-Meteo archive across the 10 training cities for convective months (Apr–Sep 2022–2024),
find 'onset hits' where P(t) >= 0.186, label at t is False, and label at t+1 is True,
and rank the top 10 candidates by P(t) and precipitation amount at t+1."""

import asyncio
import calendar
from datetime import datetime
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8")
import httpx
import numpy as np
import pandas as pd

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.ml.models.thunderstorm_model import ThunderstormClassifier
from app.services.training_features import (
    CLEAN_FEATURE_COLS,
    compute_thunderstorm_label,
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

YEARS = [2024, 2023, 2022]
MONTHS = [4, 5, 6, 7, 8, 9]  # Apr–Sep


async def scan_city_month(
    client: httpx.AsyncClient,
    city: dict,
    year: int,
    month: int,
    model: ThunderstormClassifier,
) -> list[dict]:
    num_days = calendar.monthrange(year, month)[1]
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{num_days:02d}"

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
    except Exception as e:
        print(f"Error fetching {city['name']} {year}-{month:02d}: {e}")
        return []

    hourly = data.get("hourly", {})
    if not hourly or "time" not in hourly:
        return []

    df = pd.DataFrame(hourly)
    df["latitude"] = city["lat"]
    df["longitude"] = city["lon"]
    df["time"] = pd.to_datetime(df["time"])

    # Compute features dataframe
    feat_df = engineer_training_features_df(df)

    # Compute labels at each hour
    labels = []
    for i in range(len(df)):
        wc = df["weather_code"].iloc[i]
        p = df["precipitation"].iloc[i]
        t = df["temperature_2m"].iloc[i]
        rh = df["relative_humidity_2m"].iloc[i]
        dp = df["dew_point_2m"].iloc[i]
        lbl = compute_thunderstorm_label(wc, p, t, rh, dp)
        labels.append(lbl)
    df["label"] = labels

    # Predict probabilities for available valid rows (dropping initial lag NaNs)
    valid_mask = ~feat_df[CLEAN_FEATURE_COLS].isna().any(axis=1)
    if not valid_mask.any():
        return []

    X_mat = feat_df.loc[valid_mask, CLEAN_FEATURE_COLS].values
    probs = model.model.predict_proba(X_mat)[:, 1]

    df.loc[valid_mask, "prob"] = probs

    onset_events = []
    threshold = model.optimal_threshold  # 0.186

    for i in range(len(df) - 1):
        if not valid_mask.iloc[i]:
            continue

        p_t = df["prob"].iloc[i]
        lbl_t = df["label"].iloc[i]
        lbl_next = df["label"].iloc[i + 1]
        precip_t = df["precipitation"].iloc[i]
        precip_next = df["precipitation"].iloc[i + 1]
        time_t = df["time"].iloc[i]

        # Onset Hit condition: P(t) >= threshold, label(t) == 0 (no ongoing rain), label(t+1) == 1
        if p_t >= threshold and lbl_t == 0 and precip_t <= 0.2 and lbl_next == 1 and precip_next >= 2.0:
            onset_events.append({
                "city": city["name"],
                "state": city["state"],
                "latitude": city["lat"],
                "longitude": city["lon"],
                "date": time_t.strftime("%Y-%m-%d"),
                "hour_ist": time_t.strftime("%H:00 IST"),
                "hour_idx": time_t.hour,
                "p_t": round(float(p_t), 4),
                "precip_t": round(float(precip_t), 2),
                "precip_next": round(float(precip_next), 2),
                "temp_t": round(float(df["temperature_2m"].iloc[i]), 1),
                "rh_t": round(float(df["relative_humidity_2m"].iloc[i]), 1),
            })

    return onset_events


async def main():
    model = ThunderstormClassifier()
    print("=" * 80)
    print("Scanning Open-Meteo Archive for Onset Hits across 10 Training Cities (Apr–Sep 2022–2024)...")
    print("Criteria: P(t) >= 0.186, label(t) == 0 (rain not started), label(t+1) == 1 (rain >= 2mm at t+1)")
    print("=" * 80)

    all_onset_events = []

    async with httpx.AsyncClient() as client:
        for year in YEARS:
            for month in MONTHS:
                for city in CITIES:
                    events = await scan_city_month(client, city, year, month, model)
                    if events:
                        all_onset_events.extend(events)
                    await asyncio.sleep(0.3)  # Polite throttling

    # Deduplicate events occurring in consecutive hours for the same city/date
    unique_events = []
    seen = set()
    for ev in all_onset_events:
        key = (ev["city"], ev["date"])
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    # Rank by P(t) descending and precip_next descending
    ranked_events = sorted(
        unique_events,
        key=lambda x: (x["p_t"] >= 0.35, x["p_t"] * x["precip_next"]),
        reverse=True,
    )

    print("\n" + "=" * 80)
    print(f"TOP 10 CANDIDATE ONSET HITS FOUND (Total unique candidate days: {len(unique_events)}):")
    print("=" * 80)

    for idx, ev in enumerate(ranked_events[:10], 1):
        print(
            f"{idx:2d}. {ev['city']:10s} | Date: {ev['date']} at {ev['hour_ist']:9s} | "
            f"P(t): {ev['p_t']:.4f} (Threshold: 0.1860) | Rain at t+1: {ev['precip_next']:5.1f} mm | "
            f"Temp: {ev['temp_t']}°C, RH: {ev['rh_t']}%"
        )
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
