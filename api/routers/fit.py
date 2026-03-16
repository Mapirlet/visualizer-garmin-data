"""
FIT activity detail endpoints.

GET /api/fit/{activity_id}             — processed per-second records
GET /api/fit/{activity_id}/decoupling  — aerobic decoupling value
GET /api/fit/activities                — activity list with FIT availability flag
"""
from __future__ import annotations
from functools import lru_cache
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from api.deps import state
from api.utils import df_to_records
from src.loaders import load_fit_activity, compute_aerobic_decoupling

router = APIRouter()

_S2D = 180 / 2**31

# Zone bands (same as app.py _ZONE_BANDS)
_ZONE_BANDS = {
    # Garmin percentile bands: <5% poor, 5-29% fair, 30-69% moderate, 70-95% good, >95% excellent
    "cadence_spm": [
        (0, 151, "poor"), (151, 163, "fair"), (163, 174, "moderate"),
        (174, 185, "good"), (185, 999, "excellent"),
    ],
    "vertical_oscillation": [
        (0, 6.5, "excellent"), (6.5, 8.0, "good"), (8.0, 9.5, "moderate"),
        (9.5, 11.0, "fair"), (11.0, 999, "poor"),
    ],
    # Garmin percentile bands: >95% excellent (<208ms), 70-95% good (208-240ms), 30-69% moderate (241-272ms), 5-29% fair (273-305ms), <5% poor (>305ms)
    "ground_contact_time": [
        (0, 208, "excellent"), (208, 241, "good"), (241, 273, "moderate"),
        (273, 305, "fair"), (305, 999, "poor"),
    ],
    # Garmin percentile bands: >95% excellent (<6.1%), 70-95% good (6.1-7.4%), 30-69% moderate (7.5-8.6%), 5-29% fair (8.7-10.1%), <5% poor (>10.1%)
    "vertical_ratio": [
        (0, 6.1, "excellent"), (6.1, 7.5, "good"), (7.5, 8.7, "moderate"),
        (8.7, 10.1, "fair"), (10.1, 999, "poor"),
    ],
}

_ZONE_COLORS = {
    "walking": "#aaaaaa", "poor": "#d73027", "fair": "#fc8d59",
    "moderate": "#fee090", "good": "#91cf60", "excellent": "#1a9850",
}


def _assign_zones(values: pd.Series, metric: str, grade: pd.Series) -> pd.Series:
    bands = _ZONE_BANDS.get(metric)
    if bands is None:
        return pd.Series("moderate", index=values.index)
    if metric == "cadence_spm":
        v = values + (grade.clip(lower=0) * 0.5).clip(upper=8)
    elif metric == "vertical_oscillation":
        v = values - (grade.clip(lower=0) * 0.1).clip(upper=1.5)
    elif metric == "ground_contact_time":
        v = values - (grade.clip(lower=0) * 2.0).clip(upper=30)
    else:
        v = values
    zones = pd.Series("moderate", index=values.index)
    for y0, y1, zone in bands:
        zones[(v >= y0) & (v < y1)] = zone
    return zones


@lru_cache(maxsize=64)
def _load_and_process(activity_id: int) -> Optional[dict]:
    """Load and process a FIT file. Result is cached by activity_id."""
    raw = load_fit_activity(activity_id)
    if raw is None or raw.empty:
        return None

    df = raw.copy()

    # GPS
    has_gps = "position_lat" in df.columns and "position_long" in df.columns
    if has_gps:
        df = df.dropna(subset=["position_lat", "position_long"])
        df["lat"] = df["position_lat"].astype(float) * _S2D
        df["lon"] = df["position_long"].astype(float) * _S2D

    # Speed / pace / walk flag
    speed_col = "enhanced_speed" if "enhanced_speed" in df.columns else "speed"
    if speed_col in df.columns:
        spd = pd.to_numeric(df[speed_col], errors="coerce").fillna(0)
        df["is_walking"] = (spd < 2.0).astype(bool)
        df["pace"] = (1000 / spd.clip(lower=0.1) / 60).where(spd > 0.5)

    # Distance / altitude / HR
    if "distance" in df.columns:
        df["distance_km"] = pd.to_numeric(df["distance"], errors="coerce") / 1000
    if "altitude" in df.columns:
        df["altitude"] = pd.to_numeric(df["altitude"], errors="coerce")
    if "heart_rate" in df.columns:
        df["heart_rate"] = pd.to_numeric(df["heart_rate"], errors="coerce")

    # Grade
    if "altitude" in df.columns and "distance" in df.columns:
        alt_s = df["altitude"].rolling(10, center=True, min_periods=1).mean()
        dist_d = pd.to_numeric(df["distance"], errors="coerce").diff().clip(lower=0.5)
        df["grade_pct"] = (alt_s.diff() / dist_d * 100).clip(-30, 30).fillna(0)
    else:
        df["grade_pct"] = 0.0

    # Grade-Adjusted Pace
    if "pace" in df.columns:
        up = 1 + df["grade_pct"].clip(lower=0) * 0.033
        down = 1 - df["grade_pct"].clip(upper=0).abs() * 0.018
        df["gap"] = df["pace"] / (up * down).clip(lower=0.5)

    # Cadence
    if "cadence" in df.columns:
        df["cadence_spm"] = pd.to_numeric(df["cadence"], errors="coerce") * 2

    # Technique columns
    for raw_col, dest_col, scale, valid_range in [
        ("vertical_oscillation", "vertical_oscillation", 1 / 10, (3.0, 20.0)),
        ("stance_time", "ground_contact_time", 1.0, (100, 700)),
        ("vertical_ratio", "vertical_ratio", 1.0, (3.0, 20.0)),
        ("step_length", "stride_length", 1 / 10, (20.0, 200.0)),
    ]:
        if raw_col in df.columns:
            v = pd.to_numeric(df[raw_col], errors="coerce") * scale
            df[dest_col] = v.where(v.between(*valid_range))

    if "cadence_spm" in df.columns:
        df["cadence_spm"] = df["cadence_spm"].where(df["cadence_spm"].between(100, 240))

    # Assign zone labels
    grade = df.get("grade_pct", pd.Series(0.0, index=df.index))
    for metric in ("cadence_spm", "vertical_oscillation", "ground_contact_time", "vertical_ratio"):
        if metric in df.columns:
            df[f"{metric}_zone"] = _assign_zones(df[metric], metric, grade)

    # Select output columns
    keep = [
        "distance_km", "heart_rate", "pace", "gap", "altitude", "grade_pct",
        "cadence_spm", "vertical_oscillation", "ground_contact_time",
        "vertical_ratio", "stride_length", "is_walking",
        "cadence_spm_zone", "vertical_oscillation_zone",
        "ground_contact_time_zone", "vertical_ratio_zone",
    ]
    if has_gps:
        keep += ["lat", "lon"]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].reset_index(drop=True)

    return {"records": df_to_records(df), "has_gps": has_gps}


@router.get("/fit/activities")
def get_fit_activities(
    start: Optional[str] = None,
    end: Optional[str] = None,
    types: Optional[str] = None,
):
    """Activity list for the Activity Detail selector."""
    df = state.activities.copy()
    df["date"] = pd.to_datetime(df["date"])
    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["date"] <= pd.Timestamp(end)]
    if types:
        type_list = [t.strip() for t in types.split(",") if t.strip()]
        if type_list:
            df = df[df["activity_type"].isin(type_list)]

    df = df.dropna(subset=["date"]).sort_values("date", ascending=False)
    df["label"] = (
        df["date"].dt.strftime("%Y-%m-%d") + "  " +
        df["name"].fillna("") + "  (" +
        df["distance_km"].round(1).astype(str) + " km)"
    )
    cols = ["activity_id", "date", "name", "activity_type", "distance_km",
            "duration_min", "avg_hr", "avg_pace_min_km", "label"]
    cols = [c for c in cols if c in df.columns]
    return {"activities": df_to_records(df[cols])}


@router.get("/fit/{activity_id}")
def get_fit(activity_id: int):
    result = _load_and_process(activity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="FIT data not found for this activity")
    return result


@router.get("/fit/{activity_id}/decoupling")
def get_decoupling(activity_id: int):
    raw = load_fit_activity(activity_id)
    if raw is None or raw.empty:
        return {"decoupling": None, "label": None, "level": None}
    dec = compute_aerobic_decoupling(raw)
    if dec is None:
        return {"decoupling": None, "label": None, "level": None}
    if dec < 5:
        level, label = "good", f"{dec:.1f}% — aerobic base solid"
    elif dec < 10:
        level, label = "borderline", f"{dec:.1f}% — borderline"
    else:
        level, label = "poor", f"{dec:.1f}% — aerobically taxed for this effort"
    return {"decoupling": dec, "label": label, "level": level}
