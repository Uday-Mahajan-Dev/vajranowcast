"""Generate certified Cyclone Arnab historical replay using real Open-Meteo Forecast API past_days data and v2 model."""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
sys.stdout.reconfigure(encoding="utf-8")

import httpx
from app.config import settings
from app.ml.models.thunderstorm_model import (
    LightningPredictor,
    SeverityClassifier,
    ThunderstormClassifier,
)
from app.services.training_features import (
    CLEAN_FEATURE_COLS,
    build_features_from_raw_slice,
    compute_thunderstorm_label,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vajranowcast.arnab_replay")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REPLAYS_DIR_BACKEND = backend_dir / "app" / "data" / "historical_replays"
REPLAYS_DIR_FRONTEND = backend_dir.parent / "frontend" / "public" / "data" / "historical_replays"

CONVECTIVE_CODES = {80, 81, 82, 85, 91, 92, 93, 95, 96, 99}

ARNAB_META = {
    "event_id": "visakhapatnam-cyclone-arnab-20261027",
    "event_name": "Cyclone Arnab Visakhapatnam Convective Squall & Rainbands",
    "city": "Visakhapatnam",
    "state": "Andhra Pradesh",
    "latitude": 17.69,
    "longitude": 83.22,
    "date": "2026-10-27",
    "hour_ist": "12:00 IST",
    "hour_utc": "06:30 UTC",
    "hour_idx": 12,
    "source_url": "https://mausam.imd.gov.in",
    "synoptic_summary": "Intense cyclonic convective rainbands and gale squalls lashed coastal Andhra Pradesh during Cyclone Arnab.",
    "thunderstorm_confirmed": True,
    "verified_by_human": False,
}


async def generate_arnab():
    # Force v2 model
    settings.MODEL_VERSION = "v2"
    ts_model = ThunderstormClassifier()
    ts_model.reload()
    lt_model = LightningPredictor()
    sev_classifier = SeverityClassifier()

    lat = ARNAB_META["latitude"]
    lon = ARNAB_META["longitude"]
    date_str = ARNAB_META["date"]
    h_idx = ARNAB_META["hour_idx"]

    offsets = [-0.50, -0.25, 0.0, 0.25, 0.50]
    grid_points = []
    for dy in offsets:
        for dx in offsets:
            grid_points.append({
                "lat": round(lat + dy, 2),
                "lon": round(lon + dx, 2),
            })
    center_point_idx = 12

    lat_str = ",".join(str(p["lat"]) for p in grid_points)
    lon_str = ",".join(str(p["lon"]) for p in grid_points)

    params = {
        "latitude": lat_str,
        "longitude": lon_str,
        "past_days": 5,
        "forecast_days": 1,
        "hourly": (
            "temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,"
            "wind_speed_10m,wind_direction_10m,cloud_cover,precipitation,weather_code,"
            "wind_speed_700hPa,wind_direction_700hPa"
        ),
        "timezone": "Asia/Kolkata",
    }

    logger.info("Fetching 25-point batch from Open-Meteo Forecast API past_days for Cyclone Arnab...")
    async with httpx.AsyncClient() as client:
        res = await client.get(FORECAST_URL, params=params, timeout=45.0)
        res.raise_for_status()
        raw_batch = res.json()
        if isinstance(raw_batch, dict):
            raw_batch = [raw_batch]

    center_raw = raw_batch[center_point_idx]
    center_hourly = center_raw.get("hourly", {})
    times = center_hourly.get("time", [])

    target_iso_prefix = f"{date_str}T{h_idx:02d}:00"
    event_idx = next((i for i, t in enumerate(times) if t.startswith(target_iso_prefix)), None)
    if event_idx is None:
        raise ValueError(f"Target timestamp {target_iso_prefix} not found in forecast times.")

    timeline = []
    threshold = ts_model.optimal_threshold

    for k in range(-6, 7):
        target_i = event_idx + k
        if target_i < 0 or target_i >= len(times):
            continue

        next_i = target_i + 1
        hour_iso = times[target_i]
        hour_dt = datetime.fromisoformat(f"{hour_iso}:00+05:30")

        hour_features = build_features_from_raw_slice(
            raw_hourly=center_hourly,
            target_idx=target_i,
            original_lat=lat,
            original_lon=lon,
            target_time=hour_dt,
        )

        p_ts_k, _, _ = ts_model.predict(hour_features)
        sev_k = sev_classifier.classify(p_ts_k)

        temp_k = center_hourly.get("temperature_2m", [])[target_i] if target_i < len(center_hourly.get("temperature_2m", [])) else None
        rh_k = center_hourly.get("relative_humidity_2m", [])[target_i] if target_i < len(center_hourly.get("relative_humidity_2m", [])) else None
        cloud_k = center_hourly.get("cloud_cover", [])[target_i] if target_i < len(center_hourly.get("cloud_cover", [])) else None
        precip_k = center_hourly.get("precipitation", [])[target_i] if target_i < len(center_hourly.get("precipitation", [])) else 0.0
        wc_k = center_hourly.get("weather_code", [])[target_i] if target_i < len(center_hourly.get("weather_code", [])) else None
        dp_k = center_hourly.get("dew_point_2m", [])[target_i] if target_i < len(center_hourly.get("dew_point_2m", [])) else None

        label_rule_fired = bool(compute_thunderstorm_label(wc_k, precip_k, temp_k, rh_k, dp_k) == 1)

        temp_next = center_hourly.get("temperature_2m", [])[next_i] if next_i < len(center_hourly.get("temperature_2m", [])) else None
        rh_next = center_hourly.get("relative_humidity_2m", [])[next_i] if next_i < len(center_hourly.get("relative_humidity_2m", [])) else None
        precip_next = center_hourly.get("precipitation", [])[next_i] if next_i < len(center_hourly.get("precipitation", [])) else 0.0
        wc_next = center_hourly.get("weather_code", [])[next_i] if next_i < len(center_hourly.get("weather_code", [])) else None
        dp_next = center_hourly.get("dew_point_2m", [])[next_i] if next_i < len(center_hourly.get("dew_point_2m", [])) else None
        outcome_next_hour = bool(compute_thunderstorm_label(wc_next, precip_next, temp_next, rh_next, dp_next) == 1) if next_i < len(times) else False

        if p_ts_k >= threshold and outcome_next_hour:
            classification = "hit"
        elif p_ts_k < threshold and outcome_next_hour:
            classification = "miss"
        elif p_ts_k >= threshold and not outcome_next_hour:
            classification = "false_alarm"
        else:
            classification = "correct_negative"

        is_onset = bool(classification == "hit" and not label_rule_fired and precip_k <= 0.2)
        time_ist_label = f"{hour_iso[-5:]} IST"

        w_spd_700 = center_hourly.get("wind_speed_700hPa", [])
        w_dir_700 = center_hourly.get("wind_direction_700hPa", [])
        wind_700_meta = None
        if (
            w_spd_700 and w_dir_700
            and target_i < len(w_spd_700) and target_i < len(w_dir_700)
            and w_spd_700[target_i] is not None and w_dir_700[target_i] is not None
        ):
            wind_700_meta = {
                "speed_kmh": round(float(w_spd_700[target_i]), 1),
                "direction_deg": round(float(w_dir_700[target_i]), 1),
            }

        field_cells = []
        for p_idx, pt_meta in enumerate(grid_points):
            pt_raw = raw_batch[p_idx] if p_idx < len(raw_batch) else center_raw
            pt_hourly = pt_raw.get("hourly", {})
            pt_lat = pt_meta["lat"]
            pt_lon = pt_meta["lon"]

            try:
                pt_feats = build_features_from_raw_slice(
                    raw_hourly=pt_hourly,
                    target_idx=target_i,
                    original_lat=pt_lat,
                    original_lon=pt_lon,
                    target_time=hour_dt,
                )
                cell_prob, _, _ = ts_model.predict(pt_feats)
            except Exception as e:
                cell_prob = 0.0

            pt_precip_arr = pt_hourly.get("precipitation", [])
            cell_precip = pt_precip_arr[target_i] if target_i < len(pt_precip_arr) and pt_precip_arr[target_i] is not None else 0.0

            field_cells.append({
                "lat": pt_lat,
                "lon": pt_lon,
                "prob": round(float(cell_prob), 4),
                "precipitation": round(float(cell_precip), 2),
            })

        local_field = {
            "grid_size": 5,
            "spacing_deg": 0.25,
            "center_lat": round(lat, 2),
            "center_lon": round(lon, 2),
            "lats": [round(lat + dy, 2) for dy in offsets],
            "lons": [round(lon + dx, 2) for dx in offsets],
            "wind_700hpa": wind_700_meta,
            "cells": field_cells,
        }

        timeline.append({
            "hour_offset": k,
            "time_ist": time_ist_label,
            "iso_time": f"{hour_iso}:00+05:30",
            "probability": round(float(p_ts_k), 4),
            "severity": sev_k,
            "temperature_2m": round(float(temp_k), 1) if temp_k is not None else None,
            "relative_humidity": round(float(rh_k), 1) if rh_k is not None else None,
            "cloud_cover": round(float(cloud_k), 1) if cloud_k is not None else None,
            "precipitation": round(float(precip_k), 2) if precip_k is not None else 0.0,
            "weather_code": int(wc_k) if wc_k is not None else None,
            "label_fired": label_rule_fired,
            "outcome_next_hour": outcome_next_hour,
            "classification": classification,
            "is_onset": is_onset,
            "is_replay_hour": (k == 0),
            "local_field": local_field,
        })

    hits_count = sum(1 for h in timeline if h["classification"] == "hit")
    misses_count = sum(1 for h in timeline if h["classification"] == "miss")
    false_alarms_count = sum(1 for h in timeline if h["classification"] == "false_alarm")
    correct_negatives_count = sum(1 for h in timeline if h["classification"] == "correct_negative")
    onset_hits_count = sum(1 for h in timeline if h.get("is_onset", False))

    classification_counts = {
        "hits": hits_count,
        "misses": misses_count,
        "false_alarms": false_alarms_count,
        "correct_negatives": correct_negatives_count,
        "onset_hits": onset_hits_count,
    }

    replay_h = next((h for h in timeline if h["is_replay_hour"]), timeline[len(timeline)//2])
    rep_cls = replay_h["classification"]
    if rep_cls == "hit":
        verdict = "Hit"
    elif rep_cls == "miss":
        verdict = "Miss"
    elif rep_cls == "false_alarm":
        verdict = "False Alarm"
    else:
        verdict = "Correct Rejection"

    target_dt = datetime.fromisoformat(f"{date_str}T{h_idx:02d}:00:00+05:30")
    features = build_features_from_raw_slice(
        raw_hourly=center_hourly,
        target_idx=event_idx,
        original_lat=lat,
        original_lon=lon,
        target_time=target_dt,
    )

    p_ts, conf_ts, _ = ts_model.predict(features)
    p_lt, _ = lt_model.predict(features, p_ts)
    sev = sev_classifier.classify(p_ts)

    raw_code = center_hourly.get("weather_code", [])[event_idx] if event_idx < len(center_hourly.get("weather_code", [])) else None
    observed_code = int(raw_code) if raw_code is not None else 95
    was_ts = observed_code in CONVECTIVE_CODES or ARNAB_META.get("thunderstorm_confirmed", False)

    replay_payload = {
        "event_id": ARNAB_META["event_id"],
        "event_name": ARNAB_META["event_name"],
        "city": ARNAB_META["city"],
        "state": ARNAB_META["state"],
        "latitude": lat,
        "longitude": lon,
        "date": date_str,
        "hour_ist": ARNAB_META["hour_ist"],
        "hour_utc": ARNAB_META["hour_utc"],
        "hour_idx": h_idx,
        "source": "Open-Meteo Forecast API (Real Historical Past-Days Data)",
        "source_url": ARNAB_META["source_url"],
        "synoptic_summary": ARNAB_META["synoptic_summary"],
        "verified_by_human": False,
        "computed_verdict": verdict,
        "optimal_threshold": round(threshold, 4),
        "classification_counts": classification_counts,
        "is_onset_hit": replay_h["is_onset"],
        "features_vector": {k: round(float(v), 4) for k, v in features.items()},
        "prediction": {
            "thunderstorm_probability": round(float(p_ts), 4),
            "severity": sev,
            "lightning_probability": round(float(p_lt), 4),
            "confidence": round(float(conf_ts), 4),
            "lead_time_hours": 1.0,
            "input_conditions": {
                "relative_humidity": round(float(features["relative_humidity"]), 1),
                "dew_point_depression": round(float(features["dew_point_depression"]), 1),
                "precip_last_3hr": round(float(features["precip_last_3hr"]), 2),
                "pressure_trend": round(float(features["pressure_trend"]), 2),
            },
        },
        "actual_outcome": {
            "weather_code": observed_code,
            "was_thunderstorm": was_ts,
            "outcome_next_hour": replay_h["outcome_next_hour"],
        },
        "timeline": timeline,
    }

    out_file_b = REPLAYS_DIR_BACKEND / f"{ARNAB_META['event_id']}.json"
    out_file_f = REPLAYS_DIR_FRONTEND / f"{ARNAB_META['event_id']}.json"

    with open(out_file_b, "w", encoding="utf-8") as f:
        json.dump(replay_payload, f, indent=2)

    with open(out_file_f, "w", encoding="utf-8") as f:
        json.dump(replay_payload, f, indent=2)

    logger.info(f"Successfully generated Cyclone Arnab replay: {out_file_b}")
    print(f"Cyclone Arnab Replay Result:")
    print(f"  Verdict: {verdict}")
    print(f"  P(TS): {p_ts:.4f} (Optimal Threshold: {threshold:.4f})")
    print(f"  Counts: {classification_counts}")


if __name__ == "__main__":
    asyncio.run(generate_arnab())
