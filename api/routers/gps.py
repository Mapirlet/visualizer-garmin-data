"""
GPS heatmap endpoint.

GET /api/gps — sampled GPS points for the heatmap
"""
from __future__ import annotations
from datetime import date
from typing import Optional

import pandas as pd
from fastapi import APIRouter

from api.deps import state

router = APIRouter()


@router.get("/gps")
def get_gps(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
    max_points: int = 200_000,
):
    if state.gps is None:
        return {"points": [], "activity_count": 0, "has_data": False}

    df = state.gps.copy()
    df["date"] = pd.to_datetime(df["date"])

    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["date"] <= pd.Timestamp(end)]
    if types:
        type_list = [t.strip() for t in types.split(",") if t.strip()]
        if type_list:
            df = df[df["activity_type"].isin(type_list)]

    if df.empty:
        return {"points": [], "activity_count": 0, "has_data": True}

    activity_count = int(df["activity_id"].nunique())

    pts = df[["lat", "lon"]]
    if len(pts) > max_points:
        pts = pts.sample(max_points, random_state=42)

    points = pts.values.tolist()
    return {"points": points, "activity_count": activity_count, "has_data": True}
