"""
Add a new FIT activity to the project.

Usage:
    uv run python -m src.add_activity path/to/activity.fit

What it does:
  1. Copies the FIT file into data/raw/DI_CONNECT/DI-Connect-Uploaded-Files/
  2. Extracts stats from the session message
  3. Injects a synthetic entry into summarizedActivities.json
  4. Rebuilds fit_index, technique cache, and GPS cache
"""

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data" / "raw"
FIT_DIR  = DATA_DIR / "DI_CONNECT" / "DI-Connect-Uploaded-Files"
ACTIVITIES_DIR = DATA_DIR / "DI_CONNECT" / "DI-Connect-Fitness"
CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"


def _extract_entry(fit_path: Path) -> dict:
    from garmin_fit_sdk import Decoder, Stream

    stream = Stream.from_file(str(fit_path))
    decoder = Decoder(stream)
    messages, _ = decoder.read(
        apply_scale_and_offset=True,
        convert_types_to_strings=True,
        convert_datetimes_to_dates=True,
    )

    s = messages.get("session_mesgs", [{}])[0]
    if not s:
        raise ValueError("No session message found in FIT file.")

    sport = str(s.get("sport", "")).lower()
    start_utc   = pd.Timestamp(s["start_time"]).tz_convert("UTC")
    start_local = start_utc.tz_convert("Europe/Brussels")

    start_gmt_ms   = int(start_utc.timestamp() * 1000)
    start_local_ms = int(start_local.replace(tzinfo=None).timestamp() * 1000)

    avg_speed_cms = s.get("enhanced_avg_speed", s.get("avg_speed", 0)) / 10
    max_speed_cms = s.get("enhanced_max_speed", s.get("max_speed", 0)) / 10

    avg_cad  = s.get("avg_cadence", 0) or 0
    frac_cad = s.get("avg_fractional_cadence", 0) or 0

    # Use filename numeric ID if available, else fall back to timestamp-based ID
    stem = fit_path.stem  # e.g. "22150635874_ACTIVITY"
    numeric = "".join(filter(str.isdigit, stem.split("_")[0]))
    activity_id = int(numeric) if numeric else start_gmt_ms

    # Map FIT sport string → Garmin activity type
    type_map = {
        "running":  "running",
        "trail":    "trail_running",
        "cycling":  "cycling",
        "swimming": "swimming",
        "hiking":   "hiking",
        "walking":  "walking",
    }
    activity_type = next((v for k, v in type_map.items() if k in sport), sport)

    return {
        "activityId":   activity_id,
        "activityType": activity_type,
        "sportType":    sport.upper(),
        "name":         f"Activity {start_local.strftime('%Y-%m-%d')}",
        "startTimeGmt": float(start_gmt_ms),
        "startTimeLocal": float(start_local_ms),
        "distance":     s.get("total_distance", 0) * 100,          # m → cm
        "duration":     s.get("total_timer_time", 0) * 1000,        # s → ms
        "elapsedDuration": s.get("total_elapsed_time", 0) * 1000,
        "movingDuration":  s.get("total_timer_time", 0) * 1000,
        "avgSpeed":     avg_speed_cms,
        "maxSpeed":     max_speed_cms,
        "avgHr":        float(s.get("avg_heart_rate") or 0),
        "maxHr":        float(s.get("max_heart_rate") or 0),
        "calories":     float(s.get("total_calories") or 0),
        "avgRunCadence": float(avg_cad),
        "maxRunCadence": float(s.get("max_cadence") or 0),
        "avgDoubleCadence": avg_cad * 2 + frac_cad * 2,
        "avgVerticalOscillation": (s.get("avg_vertical_oscillation") or 0) / 10,  # mm → cm
        "avgGroundContactTime": float(s.get("avg_stance_time") or 0),              # ms
        "avgVerticalRatio": float(s.get("avg_vertical_ratio") or 0),               # %
        "avgStrideLength": (s.get("avg_step_length") or 0) / 10,                   # mm → cm
        "avgPower":     float(s.get("avg_power") or 0),
        "normPower":    float(s.get("normalized_power") or 0),
        "maxPower":     float(s.get("max_power") or 0),
        "elevationGain": float(s.get("total_ascent") or 0) * 100,   # m → cm
        "elevationLoss": float(s.get("total_descent") or 0) * 100,
        "aerobicTrainingEffect":   float(s.get("total_training_effect") or 0),
        "anaerobicTrainingEffect": float(s.get("total_anaerobic_training_effect") or 0),
        "activityTrainingLoad":    float(s.get("training_load_peak") or 0),
        "steps":        float(s.get("total_strides") or 0),
        "vO2MaxValue":  None,
        "locationName": "",
        "favorite": False, "parent": False, "pr": False,
        "atpActivity": False, "autoCalcCalories": False,
        "decoDive": False, "purposeful": False,
        "splitSummaries": [], "splits": [], "summarizedDiveInfo": {},
    }


def add_activity(fit_path: Path) -> None:
    fit_path = fit_path.resolve()
    if not fit_path.exists():
        raise FileNotFoundError(f"FIT file not found: {fit_path}")

    # 1. Copy to canonical location
    dest = FIT_DIR / fit_path.name
    if dest != fit_path:
        shutil.copy2(fit_path, dest)
        print(f"Copied → {dest}")
    else:
        print(f"Already in place: {dest}")

    # 2. Extract stats
    print("Extracting stats from FIT file…")
    entry = _extract_entry(dest)
    activity_id = entry["activityId"]
    date_str = pd.to_datetime(entry["startTimeLocal"], unit="ms").strftime("%Y-%m-%d")
    dist_km = entry["distance"] / 100_000
    pace = (1000 / (entry["avgSpeed"] * 10) / 60) if entry["avgSpeed"] > 0 else 0
    print(f"  ID:       {activity_id}")
    print(f"  Type:     {entry['activityType']}")
    print(f"  Date:     {date_str}")
    print(f"  Distance: {dist_km:.2f} km")
    print(f"  Pace:     {pace:.2f} min/km")
    print(f"  Avg HR:   {entry['avgHr']:.0f} bpm")

    # 3. Inject into summarizedActivities.json
    json_files = sorted(ACTIVITIES_DIR.glob("*_summarizedActivities.json"))
    if not json_files:
        raise FileNotFoundError("No summarizedActivities.json found.")
    json_path = json_files[-1]

    with open(json_path) as f:
        raw = json.load(f)
    acts = raw[0]["summarizedActivitiesExport"]
    existing_ids = {a["activityId"] for a in acts}

    if activity_id in existing_ids:
        print(f"Activity {activity_id} already in JSON — skipping injection.")
    else:
        acts.append(entry)
        with open(json_path, "w") as f:
            json.dump(raw, f)
        print(f"Injected into {json_path.name}  (total: {len(acts)} activities)")

    # 4. Rebuild caches
    from src.loaders import build_fit_index, build_technique_cache, build_gps_cache

    print("\nRebuilding fit_index…")
    build_fit_index(DATA_DIR, CACHE_DIR / "fit_index.json")

    print("\nRebuilding technique cache…")
    build_technique_cache(DATA_DIR, CACHE_DIR / "technique.parquet")

    print("\nRebuilding GPS cache…")
    build_gps_cache(DATA_DIR, CACHE_DIR / "gps.parquet")

    print("\nDone. Restart the app (or hard-refresh) to see the new activity.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python -m src.add_activity path/to/activity.fit")
        sys.exit(1)
    add_activity(Path(sys.argv[1]))
