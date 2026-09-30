"""Evaluate alert thresholds (0.186, 0.30, 0.40, 0.50, 0.60) across 10 training cities
using Open-Meteo archive data for convective months (Apr–Sep).
Computes:
  - Alerts per city per month
  - Hit rate (POD / Recall = Hits / Total Positives at t+1)
  - False Alarm Ratio (FAR = False Alarms / Total Alerts Issued)
  - Precision / CSI
"""

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
THRESHOLDS = [0.186, 0.30, 0.40, 0.50, 0.60]


async def fetch_city_month_data(
    client: httpx.AsyncClient,
    city: dict,
    year: int,
    month: int,
    model: ThunderstormClassifier,
) -> tuple[np.ndarray, np.ndarray]:
    """Fetch archive data for a city-month, compute model predictions P(t) and ground truth targets label(t+1)."""
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
        return np.array([]), np.array([])

    hourly = data.get("hourly", {})
    if not hourly or "time" not in hourly:
        return np.array([]), np.array([])

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

    # Target outcome is label at t+1
    valid_mask = ~feat_df[CLEAN_FEATURE_COLS].isna().any(axis=1)
    if not valid_mask.any():
        return np.array([]), np.array([])

    X_mat = feat_df.loc[valid_mask, CLEAN_FEATURE_COLS].values
    probs = model.model.predict_proba(X_mat)[:, 1]

    df.loc[valid_mask, "prob"] = probs

    # Form paired (P(t), label(t+1))
    p_list = []
    target_next_list = []
    for i in range(len(df) - 1):
        if not valid_mask.iloc[i]:
            continue
        p_list.append(df["prob"].iloc[i])
        target_next_list.append(df["label"].iloc[i + 1])

    return np.array(p_list), np.array(target_next_list)


async def main():
    model = ThunderstormClassifier()
    print("=" * 85)
    print("VAJRANOWCAST ALERT THRESHOLD EVALUATION REPORT")
    print(f"Scanning {len(CITIES)} training cities x {len(YEARS)} years x {len(MONTHS)} months ({len(CITIES)*len(YEARS)*len(MONTHS)} city-months)...")
    print("Evaluation Target: Heavy rain (> 2.0 mm with warm humidity) at t+1")
    print("=" * 85)

    all_p = []
    all_target_next = []
    total_city_months = len(CITIES) * len(YEARS) * len(MONTHS)
    processed_count = 0

    async with httpx.AsyncClient() as client:
        for year in YEARS:
            for month in MONTHS:
                for city in CITIES:
                    p_arr, tgt_arr = await fetch_city_month_data(client, city, year, month, model)
                    if len(p_arr) > 0:
                        all_p.append(p_arr)
                        all_target_next.append(tgt_arr)
                    processed_count += 1
                    if processed_count % 30 == 0:
                        print(f"  Processed {processed_count}/{total_city_months} city-months...")
                    await asyncio.sleep(0.15)  # Throttling

    if not all_p:
        print("No data collected!")
        return

    probs = np.concatenate(all_p)
    targets = np.concatenate(all_target_next)
    total_hours = len(probs)
    total_positives = int(np.sum(targets == 1))
    base_rate = (total_positives / total_hours) * 100

    print("\n" + "=" * 85)
    print(f"DATASET SUMMARY:")
    print(f"  Total Valid Hours Evaluated: {total_hours:,}")
    print(f"  Total Convective Events (t+1): {total_positives:,} ({base_rate:.2f}% base rate)")
    print(f"  Total City-Months: {total_city_months}")
    print("=" * 85 + "\n")

    print("+" + "-" * 12 + "+" + "-" * 18 + "+" + "-" * 12 + "+" + "-" * 15 + "+" + "-" * 12 + "+" + "-" * 10 + "+")
    print(f"| {'Threshold':^10} | {'Alerts/City-Mo':^16} | {'Hit Rate (POD)':^10} | {'False Alarm (FAR)':^13} | {'Precision':^10} | {'CSI':^8} |")
    print("+" + "-" * 12 + "+" + "-" * 18 + "+" + "-" * 12 + "+" + "-" * 15 + "+" + "-" * 12 + "+" + "-" * 10 + "+")

    for th in THRESHOLDS:
        alerts = probs >= th
        n_alerts = int(np.sum(alerts))
        alerts_per_city_month = n_alerts / total_city_months

        hits = int(np.sum(alerts & (targets == 1)))
        misses = int(np.sum((~alerts) & (targets == 1)))
        false_alarms = int(np.sum(alerts & (targets == 0)))
        correct_negatives = int(np.sum((~alerts) & (targets == 0)))

        # Hit rate / Recall / POD
        hit_rate = (hits / (hits + misses)) if (hits + misses) > 0 else 0.0
        # Precision
        precision = (hits / (hits + false_alarms)) if (hits + false_alarms) > 0 else 0.0
        # False Alarm Ratio (FAR = FA / (Hits + FA))
        far = (false_alarms / (hits + false_alarms)) if (hits + false_alarms) > 0 else 0.0
        # Critical Success Index (CSI)
        csi = (hits / (hits + misses + false_alarms)) if (hits + misses + false_alarms) > 0 else 0.0

        print(
            f"| {th:^10.3f} | {alerts_per_city_month:^16.1f} | {hit_rate*100:^11.1f}% | {far*100:^14.1f}% | {precision*100:^9.1f}% | {csi:^8.3f} |"
        )

    print("+" + "-" * 12 + "+" + "-" * 18 + "+" + "-" * 12 + "+" + "-" * 15 + "+" + "-" * 12 + "+" + "-" * 10 + "+\n")


if __name__ == "__main__":
    asyncio.run(main())
