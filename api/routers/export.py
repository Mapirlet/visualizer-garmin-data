"""
Export / summary endpoints.

GET /api/export/stats        — overall + monthly statistics
GET /api/export/monthly-csv  — monthly breakdown as CSV download
GET /api/export/llm-prompt   — LLM analysis prompt text
"""
from __future__ import annotations
from datetime import date
from io import StringIO
from typing import Optional

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.deps import state
from api.utils import df_to_records

router = APIRouter()


def _tech_acts(start, end, types):
    type_list = [t.strip() for t in types.split(",") if t.strip()] if types else []

    acts = state.activities.copy()
    acts["date"] = pd.to_datetime(acts["date"])
    if start:
        acts = acts[acts["date"] >= pd.Timestamp(start)]
    if end:
        acts = acts[acts["date"] <= pd.Timestamp(end)]
    if type_list:
        acts = acts[acts["activity_type"].isin(type_list)]

    tech = None
    if state.technique is not None:
        tech = state.technique.copy()
        tech["date"] = pd.to_datetime(tech["date"])
        if start:
            tech = tech[tech["date"] >= pd.Timestamp(start)]
        if end:
            tech = tech[tech["date"] <= pd.Timestamp(end)]
        if type_list:
            tech = tech[tech["activity_type"].isin(type_list)]

    return acts, tech


@router.get("/export/stats")
def get_stats(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    acts, tech = _tech_acts(start, end, types)

    STAT_COLS = {
        "avg_pace_min_km": "Pace (min/km)",
        "avg_hr": "HR (bpm)",
        "avg_cadence": "Cadence (spm)",
        "avg_vertical_oscillation": "Vert. Osc. (cm)",
        "avg_ground_contact_time": "GCT (ms)",
        "avg_vertical_ratio": "Vert. Ratio (%)",
        "aerobic_decoupling": "Aerobic Decoupling (%)",
    }
    ACT_COLS = {
        "distance_km": "Distance (km)",
        "duration_min": "Duration (min)",
        "training_load": "Training Load",
        "vo2max": "VO2max",
    }

    stat_rows = []
    LOW_IS_GOOD = {"avg_pace_min_km", "avg_ground_contact_time", "avg_vertical_oscillation", "avg_vertical_ratio"}

    src = tech if tech is not None else acts
    for col, label in STAT_COLS.items():
        if col not in src.columns:
            continue
        s = src[col].dropna()
        if s.empty:
            continue
        stat_rows.append({
            "metric": label,
            "mean": round(s.mean(), 2),
            "median": round(s.median(), 2),
            "std": round(s.std(), 2),
            "best": round(s.min() if col in LOW_IS_GOOD else s.max(), 2),
            "worst": round(s.max() if col in LOW_IS_GOOD else s.min(), 2),
            "n": len(s),
        })

    for col, label in ACT_COLS.items():
        if col not in acts.columns:
            continue
        s = acts[col].dropna()
        s = s[s > 0] if col in ("distance_km", "duration_min", "training_load", "vo2max") else s
        if s.empty:
            continue
        stat_rows.append({
            "metric": label,
            "mean": round(s.mean(), 2),
            "median": round(s.median(), 2),
            "std": round(s.std(), 2),
            "best": round(s.max(), 2),
            "worst": round(s.min(), 2),
            "n": len(s),
        })

    # Monthly breakdown
    monthly_rows = []
    if tech is not None and not tech.empty:
        tech["month"] = tech["date"].dt.to_period("M").astype(str)
        monthly_tech = tech.groupby("month").agg(
            runs=("avg_hr", "count"),
            pace=("avg_pace_min_km", "mean"),
            hr=("avg_hr", "mean"),
            cadence=("avg_cadence", "mean"),
            vert_osc=("avg_vertical_oscillation", "mean"),
            gct=("avg_ground_contact_time", "mean"),
            vert_ratio=("avg_vertical_ratio", "mean"),
        ).round(2)
        acts["month"] = acts["date"].dt.to_period("M").astype(str)
        monthly_acts = acts.groupby("month").agg(
            total_km=("distance_km", "sum"),
            avg_vo2max=("vo2max", "mean"),
            avg_load=("training_load", "mean"),
        ).round(2)
        monthly = monthly_tech.join(monthly_acts, how="left").reset_index()
        monthly_rows = df_to_records(monthly)

    return {"overall": stat_rows, "monthly": monthly_rows}


@router.get("/export/monthly-csv")
def download_monthly_csv(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    acts, tech = _tech_acts(start, end, types)
    src = tech if tech is not None else acts
    if src.empty:
        return StreamingResponse(StringIO("No data"), media_type="text/csv")

    src["month"] = src["date"].dt.to_period("M").astype(str)
    monthly = src.groupby("month").agg(
        runs=("avg_hr", "count"),
        pace=("avg_pace_min_km", "mean"),
        hr=("avg_hr", "mean"),
    ).round(2).reset_index()

    buf = StringIO()
    monthly.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=garmin_monthly.csv"},
    )


@router.get("/export/llm-prompt")
def get_llm_prompt(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
    hr_max: int = 212,
    hr_lthr: int = 189,
    hr_rest: int = 83,
):
    stats = get_stats(start=start, end=end, types=types)
    overall = stats["overall"]
    monthly = stats["monthly"]

    hr_zones = [
        int(hr_lthr * 0.85),
        int(hr_lthr * 0.90),
        int(hr_lthr * 0.95),
        int(hr_lthr * 1.00),
        hr_max,
    ]

    n_runs = sum(r["n"] for r in overall if r["metric"] == "HR (bpm)")
    date_range_str = f"{start} to {end}" if start and end else "all time"
    types_str = types or "all"

    overall_text = "\n".join(
        f"  {r['metric']}: mean={r['mean']}, median={r['median']}, best={r['best']}, n={r['n']}"
        for r in overall
    )
    monthly_text = "\n".join(
        "  " + ", ".join(f"{k}={v}" for k, v in row.items())
        for row in monthly
    )

    lines = [
        "I want you to analyse my running performance data and give me honest, specific feedback on my progress and weak points.",
        "",
        "## Athlete profile",
        "Male, 26 years old, 182 cm, 72 kg.",
        f"Activity types analysed: {types_str}.",
        f"Date range: {date_range_str} ({n_runs} runs, walk segments removed from all metrics).",
        "",
        "## Overall statistics",
        overall_text,
        "",
        "## Monthly breakdown",
        monthly_text,
        "",
        f"## HR zones (Friel method, LTHR={hr_lthr}, max HR={hr_max}, resting={hr_rest})",
        f"Z1 recovery below {hr_zones[0]} bpm",
        f"Z2 aerobic {hr_zones[0]} to {hr_zones[1]} bpm",
        f"Z3 tempo {hr_zones[1]} to {hr_zones[2]} bpm",
        f"Z4 threshold {hr_zones[2]} to {hr_zones[3]} bpm",
        f"Z5 max above {hr_zones[3]} bpm",
        "",
        "## Running form reference zones",
        "Cadence below 158 poor, 158-165 fair, 165-172 moderate, 172-178 good, above 178 excellent",
        "Vertical oscillation above 11 poor, 9.5-11 fair, 8-9.5 moderate, 6.5-8 good, below 6.5 excellent",
        "Ground contact time above 300 poor, 260-300 fair, 230-260 moderate, 200-230 good, below 200 excellent",
        "Vertical ratio above 10.1% poor, 8.7-10.1% fair, 7.4-8.7% moderate, 6.1-7.4% good, below 6.1% excellent",
        "Aerobic decoupling above 10% taxed for this effort, 5-10% borderline, below 5% solid aerobic base",
        "",
        "## Questions",
        "1. Where do I sit in each metric relative to the zones above?",
        "2. Can you identify any genuine fitness progress or regression over the months?",
        "3. What are my two or three biggest weaknesses based on this data?",
        "4. What should I focus on to improve?",
    ]

    return {"text": "\n".join(lines)}
