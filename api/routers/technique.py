"""
Running technique endpoints.

GET /api/technique              — filtered technique rows
GET /api/technique/correlations — correlation matrix
"""
from __future__ import annotations
from datetime import date
from typing import Optional

import pandas as pd
from fastapi import APIRouter

from api.deps import state
from api.utils import df_to_records, ols_line

router = APIRouter()

METRIC_LABELS = {
    "avg_hr":                   "HR (bpm)",
    "avg_pace_min_km":          "Pace (min/km)",
    "avg_gap_min_km":           "GAP (min/km)",
    "avg_cadence":              "Cadence (spm)",
    "avg_vertical_oscillation": "Vert. Osc. (cm)",
    "avg_ground_contact_time":  "GCT (ms)",
    "avg_stride_length":        "Stride (cm)",
    "avg_vertical_ratio":       "Vert. Ratio (%)",
}


def _filter(
    start: Optional[date],
    end: Optional[date],
    types: Optional[str],
) -> pd.DataFrame | None:
    if state.technique is None:
        return None
    df = state.technique.copy()
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


@router.get("/technique")
def get_technique(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    df = _filter(start, end, types)
    if df is None:
        return {"rows": [], "has_data": False}
    df = df.sort_values("date")
    return {"rows": df_to_records(df), "has_data": not df.empty}


@router.get("/technique/correlations")
def get_correlations(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    df = _filter(start, end, types)
    if df is None or df.empty:
        return {"labels": [], "matrix": [], "has_data": False}

    metric_cols = [c for c in METRIC_LABELS if c in df.columns]
    corr_data = df[metric_cols].dropna()
    if len(corr_data) < 3:
        return {"labels": [], "matrix": [], "has_data": False}

    corr = corr_data.corr()
    labels = [METRIC_LABELS[c] for c in metric_cols]
    matrix = [[round(v, 3) for v in row] for row in corr.values.tolist()]

    return {"labels": labels, "keys": metric_cols, "matrix": matrix, "has_data": True}


@router.get("/technique/scatter")
def get_technique_scatter(
    x_metric: str = "avg_cadence",
    y_metric: str = "avg_hr",
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    df = _filter(start, end, types)
    if df is None or df.empty:
        return {"points": [], "trendlines": []}

    scatter = df[[x_metric, y_metric, "name", "date", "activity_type"]].dropna()
    if "run_ratio" in df.columns:
        scatter = df[[x_metric, y_metric, "name", "date", "activity_type", "run_ratio"]].dropna()

    trendlines = []
    for atype, grp in scatter.groupby("activity_type"):
        tl = ols_line(grp[x_metric], grp[y_metric])
        if tl:
            tl["activity_type"] = atype
            trendlines.append(tl)

    return {"points": df_to_records(scatter), "trendlines": trendlines}
