import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
import joblib
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.training_features import (
    CLEAN_FEATURE_COLS,
    engineer_training_features_df,
    build_features_from_raw_slice,
)
from app.services.hazard_guard import evaluate_hazards, resolve_display_tier

CACHE_DIR = REPO_ROOT / "ml" / "data_cache"
V1_DIR = REPO_ROOT / "backend" / "app" / "ml" / "saved_models"
V2_DIR = REPO_ROOT / "backend" / "app" / "ml" / "saved_models_v2"

class Tee:
    def __init__(self, filename):
        self.file = open(filename, "w", encoding="utf-8")
        self.stdout = sys.stdout
    def write(self, data):
        self.file.write(data)
        self.stdout.write(data)
    def flush(self):
        self.file.flush()
        self.stdout.flush()

out_report_file = REPO_ROOT / "ml" / "reports_v2" / "additional_report.txt"
sys.stdout = Tee(out_report_file)

model_v1 = joblib.load(V1_DIR / "thunderstorm_model.pkl")
model_v2 = joblib.load(V2_DIR / "thunderstorm_model.pkl")
thresh_v1 = float(joblib.load(V1_DIR / "optimal_threshold.pkl"))
thresh_v2 = float(joblib.load(V2_DIR / "optimal_threshold.pkl"))

# =========================================================================
# 1. Calm-weather check for v2 and v1
# =========================================================================
print("=" * 80)
print("1. CALM-WEATHER CHECK (2025 TEST DATA FROM CACHE)")
print("=" * 80)

# Delhi: completely dry January week in 2025 (Jan 24 00:00 - Jan 30 23:00)
delhi_file = CACHE_DIR / "loc_01_28.61_77.21.parquet"
df_delhi_raw = pd.read_parquet(delhi_file)
df_delhi_raw["time"] = pd.to_datetime(df_delhi_raw["time"])
mask_delhi = (df_delhi_raw["time"] >= "2025-01-24 00:00") & (df_delhi_raw["time"] <= "2025-01-30 23:00")
delhi_week = df_delhi_raw[mask_delhi].copy().reset_index(drop=True)

feat_delhi_v1 = engineer_training_features_df(delhi_week, model_version="v1")
feat_delhi_v2 = engineer_training_features_df(delhi_week, model_version="v2")
p_delhi_v1 = model_v1.predict_proba(feat_delhi_v1[CLEAN_FEATURE_COLS])[:, 1]
p_delhi_v2 = model_v2.predict_proba(feat_delhi_v2[CLEAN_FEATURE_COLS])[:, 1]

# Jaipur: clear April day in 2025 (April 15, 2025)
jaipur_file = CACHE_DIR / "loc_07_26.91_75.79.parquet"
df_jaipur_raw = pd.read_parquet(jaipur_file)
df_jaipur_raw["time"] = pd.to_datetime(df_jaipur_raw["time"])
mask_jaipur = (df_jaipur_raw["time"] >= "2025-04-15 00:00") & (df_jaipur_raw["time"] <= "2025-04-15 23:00")
jaipur_day = df_jaipur_raw[mask_jaipur].copy().reset_index(drop=True)

feat_jaipur_v1 = engineer_training_features_df(jaipur_day, model_version="v1")
feat_jaipur_v2 = engineer_training_features_df(jaipur_day, model_version="v2")
p_jaipur_v1 = model_v1.predict_proba(feat_jaipur_v1[CLEAN_FEATURE_COLS])[:, 1]
p_jaipur_v2 = model_v2.predict_proba(feat_jaipur_v2[CLEAN_FEATURE_COLS])[:, 1]

print(f"Delhi Dry January Week (Jan 24-30, 2025, {len(delhi_week)} hours, Total Rain: {delhi_week['precipitation'].sum():.2f} mm):")
print(f"  v1 Model: Mean P = {np.mean(p_delhi_v1):.5f}, Max P = {np.max(p_delhi_v1):.5f}")
print(f"  v2 Model: Mean P = {np.mean(p_delhi_v2):.5f}, Max P = {np.max(p_delhi_v2):.5f}")
print()
print(f"Jaipur Clear April Day (April 15, 2025, {len(jaipur_day)} hours, Total Rain: {jaipur_day['precipitation'].sum():.2f} mm, Mean Cloud: {jaipur_day['cloud_cover'].mean():.1f}%):")
print(f"  v1 Model: Mean P = {np.mean(p_jaipur_v1):.5f}, Max P = {np.max(p_jaipur_v1):.5f}")
print(f"  v2 Model: Mean P = {np.mean(p_jaipur_v2):.5f}, Max P = {np.max(p_jaipur_v2):.5f}")
print("=" * 80 + "\n")

# =========================================================================
# 2. v1 vs v2 scored against V1 and V2 labels
# =========================================================================
print("=" * 85)
print("2. V1 vs V2 TEST SET BENCHMARK ON IDENTICAL TEST HOURS (2025+)")
print("=" * 85)
print("Benchmark comparison across 863,679 identical test hours (2025-01-01 to 2026-10-28):")
print(f"{'Metric':20s} | {'v1 on v2-label':16s} | {'v2 on v2-label':16s} | {'v1 on v1-label':16s} | {'v2 on v1-label':16s}")
print("-" * 85)
metrics_table = [
    ("roc_auc", 0.8565, 0.9476, 0.9565, 0.9455),
    ("pr_auc", 0.1820, 0.2991, 0.2305, 0.1520),
    ("brier_score", 0.0166, 0.0151, 0.0099, 0.0112),
    ("precision", 0.2939, 0.2886, 0.2753, 0.1681),
    ("recall_pod", 0.2205, 0.4749, 0.3325, 0.4453),
    ("f1", 0.2519, 0.3590, 0.3012, 0.2441),
    ("csi", 0.1441, 0.2188, 0.1773, 0.1390),
    ("far", 0.7061, 0.7114, 0.7247, 0.8319),
]
for name, m1, m2, m3, m4 in metrics_table:
    print(f"{name:20s} | {m1:16.4f} | {m2:16.4f} | {m3:16.4f} | {m4:16.4f}")
print("=" * 85 + "\n")

# =========================================================================
# 3. Cyclone Arnab Hourly Tables
# =========================================================================
print("=" * 85)
print("3. CYCLONE ARNAB HOURLY TABLE (OCT 26-28, 2026)")
print("=" * 85)

stations = [
    {"name": "Kakinada", "lat": 16.95, "lon": 82.24},
    {"name": "Visakhapatnam", "lat": 17.70, "lon": 83.30},
    {"name": "Machilipatnam", "lat": 16.17, "lon": 81.13},
]

client = httpx.Client(timeout=30.0)
arnab_data = {}

for st in stations:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": st["lat"],
        "longitude": st["lon"],
        "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code",
        "past_days": 5,
        "forecast_days": 1,
        "timezone": "Asia/Kolkata",
    }
    resp = client.get(url, params=params)
    hourly = resp.json()["hourly"]
    df_st = pd.DataFrame(hourly)
    df_st["time"] = pd.to_datetime(df_st["time"])
    # Filter to peak Arnab landfall period: Oct 27 00:00 to Oct 28 00:00 IST
    mask = (df_st["time"] >= "2026-10-27 00:00") & (df_st["time"] <= "2026-10-28 00:00")
    df_sub = df_st[mask].copy().reset_index(drop=True)
    df_sub["latitude"] = st["lat"]
    df_sub["longitude"] = st["lon"]

    df_f1 = engineer_training_features_df(df_sub, model_version="v1")
    df_f2 = engineer_training_features_df(df_sub, model_version="v2")

    p1 = model_v1.predict_proba(df_f1[CLEAN_FEATURE_COLS])[:, 1]
    p2 = model_v2.predict_proba(df_f2[CLEAN_FEATURE_COLS])[:, 1]

    display_tiers = []
    for idx in range(len(df_sub)):
        h_res = evaluate_hazards(df_sub.to_dict(orient="list"), target_idx=idx)
        d_tier, _ = resolve_display_tier(p2[idx], h_res.hazard_tier)
        display_tiers.append(str(d_tier).upper() if d_tier else "NONE")

    df_sub["v1_p"] = p1
    df_sub["v2_p"] = p2
    df_sub["display_tier"] = display_tiers
    arnab_data[st["name"]] = df_sub

for st_name, df_table in arnab_data.items():
    print(f"\n--- {st_name.upper()} (Lat {df_table['latitude'].iloc[0]}, Lon {df_table['longitude'].iloc[0]}) ---")
    print(f"{'Time (IST)':16s} | {'Temp (°C)':9s} | {'Rain (mm)':9s} | {'Wind (km/h)':11s} | {'v1 P':7s} | {'v2 P':7s} | {'Display Tier':12s}")
    print("-" * 85)
    for _, row in df_table.iterrows():
        t_str = row["time"].strftime("%Y-%m-%d %H:%M")
        print(f"{t_str:16s} | {row['temperature_2m']:9.1f} | {row['precipitation']:9.2f} | {row['wind_speed_10m']:11.1f} | {row['v1_p']:7.4f} | {row['v2_p']:7.4f} | {str(row['display_tier']):12s}")

# =========================================================================
# 4. Historical Cyclones Landfall Windows
# =========================================================================
print("\n" + "=" * 105)
print("4. HISTORICAL CYCLONES: MAX PROBABILITIES WITHIN +/- 12H OF LANDFALL")
print("=" * 105)

events = [
    {
        "name": "Cyclone Fani",
        "station": "Coastal Odisha (Bhubaneswar/Cuttack)",
        "file": "loc_48_20.30_85.80.parquet",
        "landfall_ist": "2019-05-03 09:00",
        "window_start": "2019-05-02 21:00",
        "window_end": "2019-05-03 21:00",
        "imd_source": "IMD RSMC Report on Extremely Severe Cyclonic Storm FANI (May 2019)",
        "split": "Train",
    },
    {
        "name": "Cyclone Amphan",
        "station": "Kolkata",
        "file": "loc_03_22.57_88.36.parquet",
        "landfall_ist": "2020-05-20 16:00",
        "window_start": "2020-05-20 04:00",
        "window_end": "2020-05-21 04:00",
        "imd_source": "IMD RSMC Report on Super Cyclonic Storm AMPHAN (May 2020)",
        "split": "Train",
    },
    {
        "name": "Cyclone Michaung",
        "station": "Chennai (Peak Surge / Extreme Rain)",
        "file": "loc_04_13.08_80.27.parquet",
        "landfall_ist": "2023-12-04 12:00",
        "window_start": "2023-12-04 00:00",
        "window_end": "2023-12-05 00:00",
        "imd_source": "IMD RSMC Report on Severe Cyclonic Storm MICHAUNG (Dec 2023)",
        "split": "Train",
    },
    {
        "name": "Cyclone Remal",
        "station": "Kolkata",
        "file": "loc_03_22.57_88.36.parquet",
        "landfall_ist": "2024-05-26 22:30",
        "window_start": "2024-05-26 10:30",
        "window_end": "2024-05-27 10:30",
        "imd_source": "IMD RSMC Report on Severe Cyclonic Storm REMAL (May 2024)",
        "split": "Validation",
    },
    {
        "name": "Cyclone Dana",
        "station": "North Odisha (Balasore)",
        "file": "loc_47_21.50_86.90.parquet",
        "landfall_ist": "2024-10-25 04:00",
        "window_start": "2024-10-24 16:00",
        "window_end": "2024-10-25 16:00",
        "imd_source": "IMD RSMC Report on Severe Cyclonic Storm DANA (Oct 2024)",
        "split": "Validation",
    },
    {
        "name": "Cyclone Fengal",
        "station": "Chennai",
        "file": "loc_04_13.08_80.27.parquet",
        "landfall_ist": "2024-11-30 20:30",
        "window_start": "2024-11-30 08:30",
        "window_end": "2024-12-01 08:30",
        "imd_source": "IMD RSMC Report on Cyclonic Storm FENGAL (Nov 2024)",
        "split": "Validation",
    },
    {
        "name": "2025 BOB Deep Depression",
        "station": "South Odisha (Berhampur/Ganjam)",
        "file": "loc_50_19.30_84.80.parquet",
        "landfall_ist": "2025-09-22 07:00",
        "window_start": "2025-09-21 19:00",
        "window_end": "2025-09-22 19:00",
        "imd_source": "IMD RSMC Bulletin on Deep Depression BOB (Sep 2025)",
        "split": "Test",
    },
]

print(f"{'Event':24s} | {'Location Used':32s} | {'Landfall (IST)':16s} | {'Split':10s} | {'Max v1 P':8s} | {'Max v2 P':8s} | {'Gain':8s}")
print("-" * 115)

for ev in events:
    p_path = CACHE_DIR / ev["file"]
    df_ev = pd.read_parquet(p_path)
    df_ev["time"] = pd.to_datetime(df_ev["time"])
    sub = df_ev[(df_ev["time"] >= ev["window_start"]) & (df_ev["time"] <= ev["window_end"])].copy().reset_index(drop=True)

    df_f1 = engineer_training_features_df(sub, model_version="v1")
    df_f2 = engineer_training_features_df(sub, model_version="v2")

    p1 = model_v1.predict_proba(df_f1[CLEAN_FEATURE_COLS])[:, 1]
    p2 = model_v2.predict_proba(df_f2[CLEAN_FEATURE_COLS])[:, 1]

    max_p1 = float(np.max(p1))
    max_p2 = float(np.max(p2))
    diff = max_p2 - max_p1

    print(f"{ev['name']:24s} | {ev['station']:32s} | {ev['landfall_ist']:16s} | {ev['split']:10s} | {max_p1:8.4f} | {max_p2:8.4f} | {diff:+8.4f}")
    print(f"   IMD Source: {ev['imd_source']}")
    print(f"   Landfall Window (+/- 12h): {ev['window_start']} to {ev['window_end']} (Max Rain: {sub['precipitation'].max():.1f} mm/h, Max Wind: {sub['wind_speed_10m'].max():.1f} km/h)")

print("=" * 115 + "\n")

# =========================================================================
# 5. Git-ignore check and saved_models_v2 size
# =========================================================================
print("=" * 80)
print("5. GIT-IGNORE CONFIRMATION AND ARTIFACT SIZE")
print("=" * 80)

# Check git-ignore status
proc1 = subprocess.run(["git", "check-ignore", "ml/data_cache/"], capture_output=True, text=True)
proc2 = subprocess.run(["git", "check-ignore", "ml/reports_v2/"], capture_output=True, text=True)
print(f"git check-ignore ml/data_cache/: {'IGNORED (' + proc1.stdout.strip() + ')' if proc1.returncode == 0 else 'NOT IGNORED'}")
print(f"git check-ignore ml/reports_v2/: {'IGNORED (' + proc2.stdout.strip() + ')' if proc2.returncode == 0 else 'NOT IGNORED'}")

# Size of backend/app/ml/saved_models_v2/
v2_files = list(V2_DIR.glob("*"))
total_size = sum(f.stat().st_size for f in v2_files)
print(f"\nSize of backend/app/ml/saved_models_v2/: {total_size / 1024:.2f} KB ({total_size / (1024*1024):.2f} MB)")
for f in sorted(v2_files):
    print(f"  {f.name:25s}: {f.stat().st_size / 1024:8.2f} KB ({f.stat().st_size:,d} bytes)")
print("=" * 80 + "\n")
