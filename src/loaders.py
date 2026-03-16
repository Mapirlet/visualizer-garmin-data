"""
Loaders for Garmin data export files.

Data directory layout (under data/raw/):
  DI_CONNECT/
    DI-Connect-Fitness/   *_summarizedActivities.json
    DI-Connect-Wellness/  *_sleepData.json
    DI-Connect-Uploaded-Files/  **/*.fit
"""

import json
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data" / "raw"


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

def load_activities(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """
    Load summarized activities from Garmin's JSON export.

    Returns one row per activity with columns:
      date, activity_id, name, activity_type, duration_min, distance_km,
      avg_hr, max_hr, avg_pace_min_km, calories, vo2max,
      aerobic_te, anaerobic_te, training_load, avg_power
    """
    pattern = "*_summarizedActivities.json"
    files = list((data_dir / "DI_CONNECT" / "DI-Connect-Fitness").glob(pattern))
    if not files:
        raise FileNotFoundError(f"No summarizedActivities files found in {data_dir}")

    rows = []
    for path in files:
        with open(path) as f:
            raw = json.load(f)
        activities = raw[0]["summarizedActivitiesExport"]
        rows.extend(activities)

    df = pd.DataFrame(rows)

    # Timestamps → datetime
    df["date"] = pd.to_datetime(df["startTimeLocal"], unit="ms").dt.date

    # Distance: cm → km
    df["distance_km"] = df["distance"] / 100_000

    # Duration: ms → minutes
    df["duration_min"] = df["duration"] / 1000 / 60

    # Speed: cm/ms = 10 m/s → pace (min/km)
    df["avg_pace_min_km"] = df["avgSpeed"].apply(
        lambda s: (1000 / (s * 10) / 60) if s and s > 0 else None
    )

    return df.rename(columns={
        "activityId": "activity_id",
        "activityType": "activity_type",
        "avgHr": "avg_hr",
        "maxHr": "max_hr",
        "calories": "calories",
        "vO2MaxValue": "vo2max",
        "aerobicTrainingEffect": "aerobic_te",
        "anaerobicTrainingEffect": "anaerobic_te",
        "activityTrainingLoad": "training_load",
        "avgPower": "avg_power",
    })


# ---------------------------------------------------------------------------
# Sleep
# ---------------------------------------------------------------------------

def load_sleep(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """
    Load sleep data from Garmin's JSON export.

    Returns one row per night with columns:
      date, overall_score, quality_score, duration_score,
      deep_min, light_min, rem_min, awake_min,
      total_sleep_min, avg_stress, avg_respiration, awake_count
    """
    pattern = "*_sleepData.json"
    files = list((data_dir / "DI_CONNECT" / "DI-Connect-Wellness").glob(pattern))
    if not files:
        raise FileNotFoundError(f"No sleepData files found in {data_dir}")

    rows = []
    for path in files:
        with open(path) as f:
            raw = json.load(f)
        rows.extend(raw)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["calendarDate"]).dt.date

    scores = df["sleepScores"].apply(pd.Series)
    df["overall_score"] = scores.get("overallScore")
    df["quality_score"] = scores.get("qualityScore")
    df["duration_score"] = scores.get("durationScore")

    df["deep_min"] = df["deepSleepSeconds"] / 60
    df["light_min"] = df["lightSleepSeconds"] / 60
    df["rem_min"] = df["remSleepSeconds"] / 60
    df["awake_min"] = df["awakeSleepSeconds"] / 60
    df["total_sleep_min"] = df["deep_min"] + df["light_min"] + df["rem_min"]

    return df.rename(columns={
        "avgSleepStress": "avg_stress",
        "averageRespiration": "avg_respiration",
        "awakeCount": "awake_count",
    })[["date", "overall_score", "quality_score", "duration_score",
        "deep_min", "light_min", "rem_min", "awake_min", "total_sleep_min",
        "avg_stress", "avg_respiration", "awake_count"]].drop_duplicates("date")


# ---------------------------------------------------------------------------
# FIT files (detailed per-activity records)
# ---------------------------------------------------------------------------

def load_fit_file(path: Path) -> pd.DataFrame:
    """
    Decode a single .fit file and return a DataFrame of RECORD messages
    (per-second GPS/HR/power/pace data).

    Columns depend on what the device recorded, typically:
      timestamp, heart_rate, speed, distance, power, cadence,
      position_lat, position_long, altitude
    """
    from garmin_fit_sdk import Decoder, Stream

    stream = Stream.from_file(str(path))
    decoder = Decoder(stream)
    messages, errors = decoder.read(
        apply_scale_and_offset=True,
        convert_types_to_strings=True,
        convert_datetimes_to_dates=True,
    )

    records = messages.get("record_mesgs", [])
    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)


def list_fit_files(data_dir: Path = DATA_DIR) -> list[Path]:
    """Return all .fit files in the data directory."""
    base = data_dir / "DI_CONNECT" / "DI-Connect-Uploaded-Files"
    return sorted(base.rglob("*.fit"))


def load_fit_activity(activity_id: int, data_dir: Path = DATA_DIR) -> Optional[pd.DataFrame]:
    """Load FIT records for a specific activity using the fit index (timestamp-matched)."""
    index = _load_fit_index(data_dir)
    if index is None or activity_id not in index:
        return None
    return load_fit_file(Path(index[activity_id]))


def _load_fit_index(data_dir: Path = DATA_DIR) -> Optional[dict]:
    """Load the activity_id → fit_path index, or None if not built yet."""
    cache_path = data_dir.parent.parent / "data" / "cache" / "fit_index.json"
    if not cache_path.exists():
        return None
    import json as _json
    with open(cache_path) as f:
        return {int(k): v for k, v in _json.load(f).items()}


def _grade_adjusted_speed(speed: pd.Series, altitude: pd.Series) -> pd.Series:
    """
    Compute grade-adjusted speed using altitude gradient.

    GAP_speed = raw_speed / (1 + grade_pct * 0.033)

    This normalises uphill/downhill effort so that EF is not inflated
    when the second half of a trail run has more climbing.
    """
    alt = altitude.ffill().bfill()
    # grade in fraction (rise/run), then percent
    grade_frac = alt.diff() / speed.replace(0, float("nan"))
    grade_pct = grade_frac.clip(-0.30, 0.30) * 100  # cap at ±30%
    # Uphill: you go slow but effort is high → GAP_speed > raw_speed (* factor > 1)
    # Downhill: you go fast but effort is low → GAP_speed < raw_speed (* factor < 1)
    factor = 1 + grade_pct * 0.033
    factor = factor.clip(0.5, 2.0)  # safety bounds
    return speed * factor


def compute_aerobic_decoupling(df: pd.DataFrame) -> Optional[float]:
    """
    Compute aerobic decoupling (Pa:HR) for a FIT DataFrame already filtered
    to running segments.

    Uses Grade Adjusted Speed when altitude data is available so that trail
    runs with a hilly second half are not penalised unfairly.

    Aerobic decoupling = (EF_first_half - EF_second_half) / EF_first_half * 100
    where EF = gap_speed / HR  (or raw speed if no altitude).

    Interpretation (TrainingPeaks standard):
        < 5%  → aerobic base solid for this effort
        5-10% → borderline
        > 10% → aerobically under-conditioned for this pace

    Returns None if there is not enough data.
    """
    speed_col = "enhanced_speed" if "enhanced_speed" in df.columns else "speed"
    if speed_col not in df.columns or "heart_rate" not in df.columns:
        return None

    spd = pd.to_numeric(df[speed_col], errors="coerce")
    hr  = pd.to_numeric(df["heart_rate"], errors="coerce")
    valid = (spd > _RUN_SPEED_MS) & hr.notna() & (hr > 60)
    run = df[valid].copy()
    if len(run) < 20:
        return None

    # Use grade-adjusted speed when altitude is available
    alt_col = "enhanced_altitude" if "enhanced_altitude" in run.columns else (
        "altitude" if "altitude" in run.columns else None
    )
    run_spd = pd.to_numeric(run[speed_col], errors="coerce")
    if alt_col is not None:
        alt = pd.to_numeric(run[alt_col], errors="coerce")
        if alt.notna().sum() > len(run) * 0.5:  # only use GAP if mostly present
            run_spd = _grade_adjusted_speed(run_spd, alt)

    run_hr = pd.to_numeric(run["heart_rate"], errors="coerce")

    mid = len(run) // 2
    spd_f = run_spd.iloc[:mid].mean()
    hr_f  = run_hr.iloc[:mid].mean()
    spd_s = run_spd.iloc[mid:].mean()
    hr_s  = run_hr.iloc[mid:].mean()

    if hr_f <= 0 or hr_s <= 0:
        return None

    ef_first  = spd_f / hr_f
    ef_second = spd_s / hr_s
    if ef_first <= 0:
        return None

    return round((ef_first - ef_second) / ef_first * 100, 2)


def build_fit_index(
    data_dir: Path = DATA_DIR,
    cache_path: Optional[Path] = None,
    progress: bool = True,
) -> dict:
    """
    Scan all FIT files, read only session_mesgs to match start timestamps
    to activity IDs, and save a fit_index.json mapping activity_id → fit_path.

    Much faster than building the full GPS cache since it skips record_mesgs.
    """
    import json as _json
    from garmin_fit_sdk import Decoder, Stream

    if cache_path is None:
        cache_path = data_dir.parent.parent / "data" / "cache" / "fit_index.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    activities = load_activities(data_dir)
    acts_raw = activities.copy()
    acts_raw["start_utc"] = pd.to_datetime(acts_raw["startTimeGmt"], unit="ms", utc=True).dt.floor("min")
    ts_to_id = {row["start_utc"]: int(row["activity_id"]) for _, row in acts_raw.iterrows()}

    fit_files = list_fit_files(data_dir)
    index = {}
    skipped = 0

    iterator = fit_files
    if progress:
        try:
            from tqdm import tqdm
            iterator = tqdm(fit_files, desc="Building FIT index", unit="file")
        except ImportError:
            pass

    for path in iterator:
        try:
            stream = Stream.from_file(str(path))
            decoder = Decoder(stream)
            messages, _ = decoder.read(convert_datetimes_to_dates=True)
        except Exception:
            skipped += 1
            continue

        sessions = messages.get("session_mesgs", [])
        if not sessions:
            skipped += 1
            continue

        start_time = sessions[0].get("start_time")
        if start_time is None:
            skipped += 1
            continue

        start_floor = pd.Timestamp(start_time).tz_convert("UTC").floor("min")
        activity_id = ts_to_id.get(start_floor)
        if activity_id is None:
            skipped += 1
            continue

        index[activity_id] = str(path)

    with open(cache_path, "w") as f:
        _json.dump(index, f)

    print(f"Indexed: {len(index)} activities | Skipped: {skipped} | Saved to: {cache_path}")
    return index


# ---------------------------------------------------------------------------
# Running technique cache
# ---------------------------------------------------------------------------

# Speed threshold (m/s) above which a record is considered running
_RUN_SPEED_MS = 2.0

# HR zone boundaries (bpm) — 5-zone model based on 195 bpm max for 26-year-old (220-age)
# Z1 recovery <117, Z2 aerobic 117-137, Z3 tempo 137-156, Z4 threshold 156-176, Z5 max >176
_HR_ZONES = [0, 117, 137, 156, 176, 999]


def _hr_zone_pcts(running_df: pd.DataFrame) -> dict:
    """Return fraction of running time in each HR zone (Z1–Z5)."""
    if "heart_rate" not in running_df.columns:
        return {f"pct_z{i}": None for i in range(1, 6)}
    hr = pd.to_numeric(running_df["heart_rate"], errors="coerce").dropna()
    if hr.empty:
        return {f"pct_z{i}": None for i in range(1, 6)}
    total = len(hr)
    result = {}
    for i in range(1, 6):
        lo, hi = _HR_ZONES[i - 1], _HR_ZONES[i]
        result[f"pct_z{i}"] = round(((hr >= lo) & (hr < hi)).sum() / total * 100, 1)
    return result


def compute_clean_run_stats(fit_path: Path) -> Optional[dict]:
    """
    Load a FIT file, filter to running segments (speed > _RUN_SPEED_MS m/s),
    and return a dict of clean running-only averages.

    Returns None if the file has no records or no running segments.
    """
    df = load_fit_file(fit_path)
    if df.empty or "enhanced_speed" not in df.columns:
        return None

    total = len(df)
    running = df[df["enhanced_speed"] > _RUN_SPEED_MS]
    if running.empty:
        return None

    def _mean(col):
        if col in running.columns:
            vals = pd.to_numeric(running[col], errors="coerce").dropna()
            return float(vals.mean()) if not vals.empty else None
        return None

    # Pace: speed in m/s → min/km
    speeds = pd.to_numeric(running["enhanced_speed"], errors="coerce").dropna()
    avg_pace = float((1000 / speeds / 60).mean()) if not speeds.empty else None

    # Grade-adjusted pace — uses altitude if available, else falls back to raw pace
    alt_col = "enhanced_altitude" if "enhanced_altitude" in running.columns else (
        "altitude" if "altitude" in running.columns else None
    )
    avg_gap: Optional[float] = None
    if alt_col is not None and not speeds.empty:
        alt = pd.to_numeric(running[alt_col], errors="coerce")
        if alt.notna().sum() > len(running) * 0.5:
            gap_speeds = _grade_adjusted_speed(
                pd.to_numeric(running["enhanced_speed"], errors="coerce"), alt
            ).dropna()
            if not gap_speeds.empty:
                avg_gap = float((1000 / gap_speeds.clip(lower=0.1) / 60).mean())

    # vertical_oscillation and step_length are in mm → convert to cm
    vo_mm = _mean("vertical_oscillation")
    sl_mm = _mean("step_length")

    raw_cadence = _mean("cadence")

    # HR histogram: compact per-bpm count so the API can apply any zone boundaries at query time
    hr_histogram: Optional[str] = None
    if "heart_rate" in running.columns:
        hr_vals = pd.to_numeric(running["heart_rate"], errors="coerce").dropna().astype(int)
        if not hr_vals.empty:
            hr_histogram = json.dumps(hr_vals.value_counts().to_dict())

    return {
        "avg_hr": _mean("heart_rate"),
        "avg_pace_min_km": avg_pace,
        "avg_gap_min_km": avg_gap,
        "avg_cadence": raw_cadence * 2 if raw_cadence is not None else None,  # single-foot → total steps/min
        "avg_vertical_oscillation": vo_mm / 10 if vo_mm is not None else None,  # mm → cm
        "avg_ground_contact_time": _mean("stance_time"),                         # ms
        "avg_stride_length": sl_mm / 10 if sl_mm is not None else None,          # mm → cm
        "avg_vertical_ratio": _mean("vertical_ratio"),                           # %
        "run_ratio": len(running) / total,
        "aerobic_decoupling": compute_aerobic_decoupling(df),
        "hr_histogram": hr_histogram,
        **_hr_zone_pcts(running),
    }


def build_technique_cache(
    data_dir: Path = DATA_DIR,
    cache_path: Optional[Path] = None,
    progress: bool = True,
) -> pd.DataFrame:
    """
    Process all FIT files, compute clean running stats, and save to parquet.
    Matches FIT files to activities by start timestamp (UTC, within 60s tolerance).

    Returns the resulting DataFrame.
    """
    from garmin_fit_sdk import Decoder, Stream

    if cache_path is None:
        cache_path = data_dir.parent.parent / "data" / "cache" / "technique.parquet"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    activities = load_activities(data_dir)
    # Build lookup: UTC timestamp (floored to minute) → activity metadata
    acts_raw = activities.copy()
    acts_raw["start_utc"] = pd.to_datetime(acts_raw["startTimeGmt"], unit="ms", utc=True).dt.floor("min")
    ts_to_meta = {
        row["start_utc"]: {
            "activity_id": row["activity_id"],
            "date": row["date"],
            "name": row["name"],
            "activity_type": row["activity_type"],
        }
        for _, row in acts_raw.iterrows()
    }

    fit_files = list_fit_files(data_dir)

    rows = []
    skipped = 0

    iterator = fit_files
    if progress:
        try:
            from tqdm import tqdm
            iterator = tqdm(fit_files, desc="Processing FIT files", unit="file")
        except ImportError:
            pass

    for path in iterator:
        # Read session message to get start_time and sport
        try:
            stream = Stream.from_file(str(path))
            decoder = Decoder(stream)
            messages, _ = decoder.read(convert_datetimes_to_dates=True)
        except Exception:
            skipped += 1
            continue

        sessions = messages.get("session_mesgs", [])
        if not sessions:
            skipped += 1
            continue

        session = sessions[0]
        sport = str(session.get("sport", "")).lower()
        if "run" not in sport:
            skipped += 1
            continue

        start_time = session.get("start_time")
        if start_time is None:
            skipped += 1
            continue

        # Match to activity by start timestamp (floor to minute)
        start_floor = pd.Timestamp(start_time).tz_convert("UTC").floor("min")
        meta = ts_to_meta.get(start_floor)
        if meta is None:
            skipped += 1
            continue

        stats = compute_clean_run_stats(path)
        if stats is None:
            skipped += 1
            continue

        rows.append({**meta, **stats})

    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_parquet(cache_path, index=False)

    print(f"Processed: {len(rows)} | Skipped: {skipped} | Saved to: {cache_path}")
    return df


def load_technique(cache_path: Optional[Path] = None) -> pd.DataFrame:
    """Load the pre-built technique cache parquet file."""
    if cache_path is None:
        cache_path = Path(__file__).parent.parent / "data" / "cache" / "technique.parquet"
    if not cache_path.exists():
        raise FileNotFoundError(
            f"Technique cache not found at {cache_path}. "
            "Run: uv run python -m src.cache"
        )
    return pd.read_parquet(cache_path)


# ---------------------------------------------------------------------------
# GPS heatmap cache
# ---------------------------------------------------------------------------

def build_gps_cache(
    data_dir: Path = DATA_DIR,
    cache_path: Optional[Path] = None,
    progress: bool = True,
) -> pd.DataFrame:
    """
    Extract GPS points from all running FIT files and save to parquet.

    Returns a DataFrame with columns:
      activity_id, date, activity_type, lat, lon
    """
    from garmin_fit_sdk import Decoder, Stream

    if cache_path is None:
        cache_path = data_dir.parent.parent / "data" / "cache" / "gps.parquet"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    activities = load_activities(data_dir)
    acts_raw = activities.copy()
    acts_raw["start_utc"] = pd.to_datetime(acts_raw["startTimeGmt"], unit="ms", utc=True).dt.floor("min")
    ts_to_meta = {
        row["start_utc"]: {
            "activity_id": row["activity_id"],
            "date": row["date"],
            "activity_type": row["activity_type"],
        }
        for _, row in acts_raw.iterrows()
    }

    fit_files = list_fit_files(data_dir)
    rows = []
    skipped = 0

    iterator = fit_files
    if progress:
        try:
            from tqdm import tqdm
            iterator = tqdm(fit_files, desc="Extracting GPS", unit="file")
        except ImportError:
            pass

    for path in iterator:
        try:
            stream = Stream.from_file(str(path))
            decoder = Decoder(stream)
            messages, _ = decoder.read(
                apply_scale_and_offset=True,
                convert_types_to_strings=True,
                convert_datetimes_to_dates=True,
            )
        except Exception:
            skipped += 1
            continue

        sessions = messages.get("session_mesgs", [])
        if not sessions:
            skipped += 1
            continue

        session = sessions[0]
        sport = str(session.get("sport", "")).lower()
        if "run" not in sport:
            skipped += 1
            continue

        start_time = session.get("start_time")
        if start_time is None:
            skipped += 1
            continue

        start_floor = pd.Timestamp(start_time).tz_convert("UTC").floor("min")
        meta = ts_to_meta.get(start_floor)
        if meta is None:
            skipped += 1
            continue

        _SEMI_TO_DEG = 180 / 2**31
        records = messages.get("record_mesgs", [])
        for rec in records:
            lat = rec.get("position_lat")
            lon = rec.get("position_long")
            if lat is None or lon is None:
                continue
            try:
                lat = float(lat) * _SEMI_TO_DEG
                lon = float(lon) * _SEMI_TO_DEG
            except (TypeError, ValueError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            rows.append({**meta, "lat": lat, "lon": lon})

    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_parquet(cache_path, index=False)

    print(f"GPS points: {len(rows)} | Skipped files: {skipped} | Saved to: {cache_path}")
    return df


def load_gps(cache_path: Optional[Path] = None) -> pd.DataFrame:
    """Load the pre-built GPS cache parquet file."""
    if cache_path is None:
        cache_path = Path(__file__).parent.parent / "data" / "cache" / "gps.parquet"
    if not cache_path.exists():
        raise FileNotFoundError(
            f"GPS cache not found at {cache_path}. "
            "Run: uv run python -m src.gps_cache"
        )
    return pd.read_parquet(cache_path)
