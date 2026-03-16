"""
Activities endpoints.

GET /api/activities          — filtered activity list
GET /api/activities/types    — unique activity types
GET /api/activities/date-range — min/max dates
GET /api/hr-pace             — scatter data (uses technique cache when available)
GET /api/hr-pace/efficiency  — EF over time
GET /api/hr-sleep            — HR vs next-night sleep score
GET /api/training-load       — training load bars
"""
from __future__ import annotations
from typing import Optional
from datetime import date

import pandas as pd
from fastapi import APIRouter

from api.deps import state
from api.utils import df_to_records, ols_line

router = APIRouter()


def _filter_acts(
    start: Optional[date],
    end: Optional[date],
    types: Optional[str],
) -> pd.DataFrame:
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
    return df


@router.get("/activities")
def get_activities(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    df = _filter_acts(start, end, types)
    cols = [
        "activity_id", "date", "name", "activity_type",
        "distance_km", "duration_min", "avg_hr", "max_hr",
        "avg_pace_min_km", "calories", "vo2max",
        "aerobic_te", "anaerobic_te", "training_load", "avg_power",
    ]
    cols = [c for c in cols if c in df.columns]
    df = df[cols].sort_values("date", ascending=False)
    return {"activities": df_to_records(df)}


@router.get("/activities/types")
def get_activity_types():
    types = sorted(state.activities["activity_type"].dropna().unique().tolist())
    return {"types": types}


@router.get("/activities/date-range")
def get_date_range():
    dates = pd.to_datetime(state.activities["date"].dropna())
    return {
        "min": dates.min().strftime("%Y-%m-%d"),
        "max": dates.max().strftime("%Y-%m-%d"),
    }


@router.get("/hr-pace")
def get_hr_pace(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    type_list = [t.strip() for t in types.split(",") if t.strip()] if types else []

    if state.technique is not None:
        src = state.technique.copy()
        src["date"] = pd.to_datetime(src["date"])
        if start:
            src = src[src["date"] >= pd.Timestamp(start)]
        if end:
            src = src[src["date"] <= pd.Timestamp(end)]
        if type_list:
            src = src[src["activity_type"].isin(type_list)]
        src = src.dropna(subset=["avg_hr", "avg_pace_min_km"])
        has_technique = True
    else:
        src = _filter_acts(start, end, types)
        src = src[src["avg_pace_min_km"].between(2, 20)].dropna(subset=["avg_hr", "avg_pace_min_km"])
        has_technique = False

    trendline = None
    if len(src) >= 3:
        trendline = ols_line(src["avg_pace_min_km"], src["avg_hr"])

    cols = ["date", "activity_id", "name", "activity_type", "avg_hr", "avg_pace_min_km"]
    if "run_ratio" in src.columns:
        cols.append("run_ratio")
    src = src[[c for c in cols if c in src.columns]]

    return {
        "points": df_to_records(src),
        "has_technique": has_technique,
        "trendline": trendline,
    }


@router.get("/hr-pace/efficiency")
def get_efficiency(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
    pace_min: float = 2.0,
    pace_max: float = 20.0,
):
    type_list = [t.strip() for t in types.split(",") if t.strip()] if types else []

    if state.technique is not None:
        src = state.technique.copy()
        src["date"] = pd.to_datetime(src["date"])
        if start:
            src = src[src["date"] >= pd.Timestamp(start)]
        if end:
            src = src[src["date"] <= pd.Timestamp(end)]
        if type_list:
            src = src[src["activity_type"].isin(type_list)]
    else:
        src = _filter_acts(start, end, types)

    src = src.dropna(subset=["avg_hr", "avg_pace_min_km"])
    src = src[src["avg_pace_min_km"].between(pace_min, pace_max)]
    if src.empty:
        return {"points": []}

    src = src.copy()
    src["efficiency_factor"] = (1000 / (src["avg_pace_min_km"] * 60)) / src["avg_hr"]
    src = src.sort_values("date")
    src["smoothed_ef"] = (
        src.set_index("date")["efficiency_factor"].rolling("30D").mean().values
    )

    cols = ["date", "name", "activity_type", "avg_pace_min_km", "avg_hr", "efficiency_factor", "smoothed_ef"]
    src = src[[c for c in cols if c in src.columns]]
    return {"points": df_to_records(src)}


@router.get("/hr-sleep")
def get_hr_sleep(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    type_list = [t.strip() for t in types.split(",") if t.strip()] if types else []

    if state.technique is not None:
        acts_hr = state.technique.copy()
        acts_hr["date"] = pd.to_datetime(acts_hr["date"])
        if start:
            acts_hr = acts_hr[acts_hr["date"] >= pd.Timestamp(start)]
        if end:
            acts_hr = acts_hr[acts_hr["date"] <= pd.Timestamp(end)]
        if type_list:
            acts_hr = acts_hr[acts_hr["activity_type"].isin(type_list)]
        acts_hr = acts_hr[["date", "name", "avg_hr", "activity_type"]].dropna(subset=["avg_hr"])
    else:
        acts_hr = _filter_acts(start, end, types)[["date", "name", "avg_hr", "activity_type"]].dropna(subset=["avg_hr"])

    sleep_df = state.sleep[["date", "overall_score"]].copy()
    sleep_df["date"] = pd.to_datetime(sleep_df["date"])
    sleep_df["activity_date"] = sleep_df["date"] - pd.Timedelta(days=1)

    merged = acts_hr.merge(
        sleep_df[["activity_date", "overall_score"]],
        left_on="date",
        right_on="activity_date",
        how="inner",
    ).dropna(subset=["avg_hr", "overall_score"])

    trendline = None
    if len(merged) >= 3:
        trendline = ols_line(merged["avg_hr"], merged["overall_score"])

    return {
        "points": df_to_records(merged[["date", "name", "activity_type", "avg_hr", "overall_score"]]),
        "trendline": trendline,
    }


@router.get("/training-load")
def get_training_load(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    df = _filter_acts(start, end, types)
    df = df.dropna(subset=["training_load"]).sort_values("date")
    return {"bars": df_to_records(df[["date", "training_load", "activity_type", "name"]])}
