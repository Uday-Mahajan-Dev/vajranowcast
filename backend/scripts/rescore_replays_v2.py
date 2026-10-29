"""Re-score historical replays with Model v2 using genuine cached Open-Meteo archive data."""

import json
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
sys.stdout.reconfigure(encoding="utf-8")

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

REPLAYS_DIR_BACKEND = backend_dir / "app" / "data" / "historical_replays"
REPLAYS_DIR_FRONTEND = backend_dir.parent / "frontend" / "public" / "data" / "historical_replays"
CACHE_DIR = backend_dir.parent / "ml" / "data_cache"

CONVECTIVE_CODES = {80, 81, 82, 85, 91, 92, 93, 95, 96, 99}

EVENT_PARQUETS = {
    "delhi-record-downpour-20240628": "loc_01_28.61_77.21.parquet",
    "mumbai-monsoon-squall-20240620": "loc_02_19.08_72.88.parquet",
    "kolkata-cyclone-remal-20240527": "loc_03_22.57_88.36.parquet",
    "bengaluru-thunderstorm-20230521": "loc_05_12.97_77.59.parquet",
}


def rescore_event(event_id: str, parquet_file: str):
    settings.MODEL_VERSION = "v2"
    ts_model = ThunderstormClassifier()
    ts_model.reload()
    lt_model = LightningPredictor()
    sev_classifier = SeverityClassifier()
    threshold = ts_model.optimal_threshold  # 0.1798

    json_path = REPLAYS_DIR_BACKEND / f"{event_id}.json"
    with open(json_path, "r", encoding="utf-8") as f:
        replay = json.load(f)

    before_verdict = replay["computed_verdict"]
    before_counts = dict(replay["classification_counts"])
    before_prob = replay["prediction"]["thunderstorm_probability"]

    # Load genuine parquet data
    parquet_path = CACHE_DIR / parquet_file
    df = pd.read_parquet(parquet_path)

    date_str = replay["date"]
    h_idx = replay["hour_idx"]
    lat = replay["latitude"]
    lon = replay["longitude"]

    # Find the target event index in parquet
    target_iso_prefix = f"{date_str}T{h_idx:02d}:00"
    times = [t.strftime("%Y-%m-%dT%H:%M") if hasattr(t, "strftime") else str(t) for t in df["time"]]
    event_idx = next((i for i, t in enumerate(times) if t.startswith(target_iso_prefix)), None)
    if event_idx is None:
        raise ValueError(f"Could not find {target_iso_prefix} in {parquet_file}")

    raw_hourly = {
        "time": times,
        "temperature_2m": df["temperature_2m"].tolist(),
        "relative_humidity_2m": df["relative_humidity_2m"].tolist(),
        "dew_point_2m": df["dew_point_2m"].tolist(),
        "surface_pressure": df["surface_pressure"].tolist(),
        "wind_speed_10m": df["wind_speed_10m"].tolist(),
        "wind_direction_10m": df["wind_direction_10m"].tolist(),
        "cloud_cover": df["cloud_cover"].tolist(),
        "precipitation": df["precipitation"].tolist(),
        "weather_code": df["weather_code"].tolist(),
    }

    # Update timeline hours
    for h_entry in replay["timeline"]:
        k = h_entry["hour_offset"]
        target_i = event_idx + k
        if target_i < 0 or target_i >= len(times):
            continue

        next_i = target_i + 1
        hour_iso = times[target_i]
        hour_dt = datetime.fromisoformat(f"{hour_iso}:00+05:30")

        hour_features = build_features_from_raw_slice(
            raw_hourly=raw_hourly,
            target_idx=target_i,
            original_lat=lat,
            original_lon=lon,
            target_time=hour_dt,
        )

        p_ts_k, _, _ = ts_model.predict(hour_features)
        sev_k = sev_classifier.classify(p_ts_k)

        temp_k = raw_hourly["temperature_2m"][target_i]
        rh_k = raw_hourly["relative_humidity_2m"][target_i]
        precip_k = raw_hourly["precipitation"][target_i] or 0.0
        wc_k = raw_hourly["weather_code"][target_i]
        dp_k = raw_hourly["dew_point_2m"][target_i]

        label_rule_fired = bool(compute_thunderstorm_label(wc_k, precip_k, temp_k, rh_k, dp_k) == 1)

        temp_next = raw_hourly["temperature_2m"][next_i] if next_i < len(times) else None
        rh_next = raw_hourly["relative_humidity_2m"][next_i] if next_i < len(times) else None
        precip_next = raw_hourly["precipitation"][next_i] if next_i < len(times) else 0.0
        wc_next = raw_hourly["weather_code"][next_i] if next_i < len(times) else None
        dp_next = raw_hourly["dew_point_2m"][next_i] if next_i < len(times) else None
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

        h_entry["probability"] = round(float(p_ts_k), 4)
        h_entry["severity"] = sev_k
        h_entry["label_fired"] = label_rule_fired
        h_entry["outcome_next_hour"] = outcome_next_hour
        h_entry["classification"] = classification
        h_entry["is_onset"] = is_onset

    # Recompute summary counts
    timeline = replay["timeline"]
    hits_count = sum(1 for h in timeline if h["classification"] == "hit")
    misses_count = sum(1 for h in timeline if h["classification"] == "miss")
    false_alarms_count = sum(1 for h in timeline if h["classification"] == "false_alarm")
    correct_negatives_count = sum(1 for h in timeline if h["classification"] == "correct_negative")
    onset_hits_count = sum(1 for h in timeline if h.get("is_onset", False))

    after_counts = {
        "hits": hits_count,
        "misses": misses_count,
        "false_alarms": false_alarms_count,
        "correct_negatives": correct_negatives_count,
        "onset_hits": onset_hits_count,
    }

    replay_h = next((h for h in timeline if h["is_replay_hour"]), timeline[len(timeline)//2])
    rep_cls = replay_h["classification"]
    if rep_cls == "hit":
        after_verdict = "Hit"
    elif rep_cls == "miss":
        after_verdict = "Miss"
    elif rep_cls == "false_alarm":
        after_verdict = "False Alarm"
    else:
        after_verdict = "Correct Rejection"

    target_dt = datetime.fromisoformat(f"{date_str}T{h_idx:02d}:00:00+05:30")
    features = build_features_from_raw_slice(
        raw_hourly=raw_hourly,
        target_idx=event_idx,
        original_lat=lat,
        original_lon=lon,
        target_time=target_dt,
    )
    p_ts, conf_ts, _ = ts_model.predict(features)
    p_lt, _ = lt_model.predict(features, p_ts)
    sev = sev_classifier.classify(p_ts)

    replay["optimal_threshold"] = round(threshold, 4)
    replay["computed_verdict"] = after_verdict
    replay["classification_counts"] = after_counts
    replay["is_onset_hit"] = replay_h["is_onset"]
    replay["features_vector"] = {k: round(float(v), 4) for k, v in features.items()}
    replay["prediction"]["thunderstorm_probability"] = round(float(p_ts), 4)
    replay["prediction"]["severity"] = sev
    replay["prediction"]["lightning_probability"] = round(float(p_lt), 4)
    replay["prediction"]["confidence"] = round(float(conf_ts), 4)

    # Save to both backend and frontend directories
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(replay, f, indent=2)

    frontend_path = REPLAYS_DIR_FRONTEND / f"{event_id}.json"
    with open(frontend_path, "w", encoding="utf-8") as f:
        json.dump(replay, f, indent=2)

    return {
        "event_id": event_id,
        "event_name": replay["event_name"],
        "before_verdict": before_verdict,
        "after_verdict": after_verdict,
        "before_prob": before_prob,
        "after_prob": round(float(p_ts), 4),
        "before_counts": before_counts,
        "after_counts": after_counts,
    }


def main():
    scorecards = []
    for ev_id, p_file in EVENT_PARQUETS.items():
        res = rescore_event(ev_id, p_file)
        scorecards.append(res)

    print("=" * 80)
    print("HISTORICAL REPLAYS v1 -> v2 RESCORING RESULTS (REAL CACHED ARCHIVE DATA)")
    print("=" * 80)
    for sc in scorecards:
        print(f"\n• {sc['event_name']} ({sc['event_id']})")
        print(f"   Verdict: {sc['before_verdict']} -> {sc['after_verdict']}")
        print(f"   P(TS):   {sc['before_prob']:.4f} -> {sc['after_prob']:.4f}")
        print(f"   Counts (v1): Hits: {sc['before_counts']['hits']}, Misses: {sc['before_counts']['misses']}, False Alarms: {sc['before_counts']['false_alarms']}, Correct Neg: {sc['before_counts']['correct_negatives']}")
        print(f"   Counts (v2): Hits: {sc['after_counts']['hits']}, Misses: {sc['after_counts']['misses']}, False Alarms: {sc['after_counts']['false_alarms']}, Correct Neg: {sc['after_counts']['correct_negatives']}")


if __name__ == "__main__":
    main()
