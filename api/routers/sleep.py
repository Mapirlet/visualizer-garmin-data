"""
Sleep endpoints.

GET /api/sleep  — filtered sleep rows with period navigation
"""
from __future__ import annotations
from datetime import date
from typing import Optional

import pandas as pd
from fastapi import APIRouter

from api.deps import state
from api.utils import df_to_records

router = APIRouter()


@router.get("/sleep")
def get_sleep(
    period: str = "all",
    offset: int = 0,
    start: Optional[date] = None,
    end: Optional[date] = None,
):
    df = state.sleep.copy()
    df["date"] = pd.to_datetime(df["date"])

    today = pd.Timestamp.today().normalize()
    period = period.lower()

    if period == "week":
        week_start = (today - pd.Timedelta(days=today.dayofweek)) + pd.Timedelta(weeks=offset)
        week_end = week_start + pd.Timedelta(days=6)
        label = f"{week_start.strftime('%d %b')} to {week_end.strftime('%d %b %Y')}"
        df = df[(df["date"] >= week_start) & (df["date"] <= week_end)]

    elif period == "month":
        ref = today + pd.DateOffset(months=offset)
        label = ref.strftime("%B %Y")
        df = df[(df["date"].dt.year == ref.year) & (df["date"].dt.month == ref.month)]

    elif period == "year":
        year = today.year + offset
        label = str(year)
        df = df[df["date"].dt.year == year]

    else:  # all — respect sidebar date filter
        label = "All time"
        if start:
            df = df[df["date"] >= pd.Timestamp(start)]
        if end:
            df = df[df["date"] <= pd.Timestamp(end)]

    df = df.sort_values("date")
    cols = ["date", "overall_score", "quality_score", "duration_score",
            "deep_min", "light_min", "rem_min", "awake_min", "total_sleep_min",
            "avg_stress", "avg_respiration", "awake_count"]
    cols = [c for c in cols if c in df.columns]

    return {"rows": df_to_records(df[cols]), "label": label}
