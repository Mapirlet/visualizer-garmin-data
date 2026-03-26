"""
Fitness progress endpoints.

GET /api/progress/vo2max       — VO2max trend
GET /api/progress/pace-at-hr   — pace at fixed HR band
GET /api/progress/decoupling   — aerobic decoupling trend
GET /api/progress/z2           — EF at Z2 + monthly zone distribution
"""
from __future__ import annotations
from datetime import date
from typing import Optional

import json
import pandas as pd
from fastapi import APIRouter

from api.deps import state
from api.utils import df_to_records

router = APIRouter()


def _tech_filtered(start, end, types):
    if state.technique is None:
        return None
    df = state.technique.copy()
    df["date"] = pd.to_datetime(df["date"])
    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["date"] <= pd.Timestamp(end)]
    if types:
        tl = [t.strip() for t in types.split(",") if t.strip()]
        if tl:
            df = df[df["activity_type"].isin(tl)]
    return df


def _acts_filtered(start, end, types):
    df = state.activities.copy()
    df["date"] = pd.to_datetime(df["date"])
    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["date"] <= pd.Timestamp(end)]
    if types:
        tl = [t.strip() for t in types.split(",") if t.strip()]
        if tl:
            df = df[df["activity_type"].isin(tl)]
    return df


@router.get("/progress/vo2max")
def get_vo2max(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    df = _acts_filtered(start, end, types)
    df = df.dropna(subset=["vo2max"])
    df = df[df["vo2max"] > 0].sort_values("date")
    if df.empty:
        return {"points": []}
    df["smoothed"] = df.set_index("date")["vo2max"].rolling("30D").mean().values
    cols = ["date", "name", "activity_type", "vo2max", "smoothed"]
    return {"points": df_to_records(df[cols])}


@router.get("/progress/pace-at-hr")
def get_pace_at_hr(
    hr_min: int = 150,
    hr_max: int = 165,
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    df = _tech_filtered(start, end, types)
    if df is None:
        return {"points": [], "has_data": False}
    # Prefer grade-adjusted pace so trail runs with D+ compare fairly
    pace_col = "avg_gap_min_km" if "avg_gap_min_km" in df.columns and df["avg_gap_min_km"].notna().sum() > 0 else "avg_pace_min_km"
    df = df.dropna(subset=["avg_hr", pace_col])
    df = df[df["avg_hr"].between(hr_min, hr_max)].copy()
    if len(df) < 3:
        return {"points": [], "has_data": True}
    df = df.sort_values("date")
    df["smoothed_pace"] = df.set_index("date")[pace_col].rolling("60D").mean().values
    df["pace_display"] = df[pace_col]
    cols = ["date", "name", "activity_type", "avg_hr", "pace_display", "smoothed_pace"]
    return {"points": df_to_records(df[cols]), "has_data": True, "pace_label": "GAP (min/km)" if pace_col == "avg_gap_min_km" else "Pace (min/km)"}


@router.get("/progress/decoupling")
def get_decoupling_trend(
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    df = _tech_filtered(start, end, types)
    if df is None or "aerobic_decoupling" not in df.columns:
        return {"points": [], "has_data": False}
    df = df.dropna(subset=["aerobic_decoupling"]).sort_values("date")
    if len(df) < 3:
        return {"points": [], "has_data": True}
    df["smoothed"] = df.set_index("date")["aerobic_decoupling"].rolling("60D").mean().values
    cols = ["date", "name", "activity_type", "aerobic_decoupling", "smoothed"]
    return {"points": df_to_records(df[cols]), "has_data": True}


@router.get("/progress/z2")
def get_z2(
    zones: str = "141,158,177,188",
    start: Optional[date] = None,
    end: Optional[date] = None,
    types: Optional[str] = None,
):
    df = _tech_filtered(start, end, types)
    if df is None:
        return {"ef_points": [], "zone_dist": [], "has_data": False}

    bounds = [float(x) for x in zones.split(",")]
    z2_lo, z2_hi = int(bounds[0]), int(bounds[1])

    # EF at Z2 — use GAP when available so trail runs don't inflate EF on downhills
    pace_col_z2 = "avg_gap_min_km" if "avg_gap_min_km" in df.columns and df["avg_gap_min_km"].notna().sum() > 0 else "avg_pace_min_km"
    z2 = df[df["avg_hr"].between(z2_lo, z2_hi)].dropna(subset=["avg_hr", pace_col_z2]).copy()
    if len(z2) >= 3:
        z2 = z2.sort_values("date")
        z2["ef"] = (1000 / (z2[pace_col_z2] * 60)) / z2["avg_hr"]
        z2["smoothed_ef"] = z2.set_index("date")["ef"].rolling("60D").mean().values
        ef_points = df_to_records(z2[["date", "activity_type", "ef", "smoothed_ef"]])
    else:
        ef_points = []

    zone_label_map = {1: "Z1 recovery", 2: "Z2 aerobic", 3: "Z3 tempo", 4: "Z4 threshold", 5: "Z5 max"}

    def _bpm_to_zone(bpm: int) -> int:
        for i, b in enumerate(bounds):
            if bpm < b:
                return i + 1
        return 5

    def _histogram_zone_pcts(hist_json: str) -> Optional[dict]:
        """Return {zone_label: pct} from a stored HR histogram JSON string."""
        try:
            hist = json.loads(hist_json)
        except (TypeError, ValueError):
            return None
        counts = [0] * 5
        total = 0
        for bpm_str, count in hist.items():
            z = _bpm_to_zone(int(bpm_str))
            counts[z - 1] += count
            total += count
        if total == 0:
            return None
        return {zone_label_map[i + 1]: round(counts[i] / total * 100, 1) for i in range(5)}

    use_histogram = "hr_histogram" in df.columns and df["hr_histogram"].notna().sum() > 0
    df2 = df.copy()
    df2["month"] = df2["date"].dt.to_period("M").astype(str)

    if use_histogram:
        records_list = []
        for month, grp in df2.dropna(subset=["hr_histogram"]).groupby("month"):
            zone_totals = {label: 0.0 for label in zone_label_map.values()}
            n = 0
            for hist_json in grp["hr_histogram"]:
                zpcts = _histogram_zone_pcts(hist_json)
                if zpcts:
                    for label, pct in zpcts.items():
                        zone_totals[label] += pct
                    n += 1
            if n > 0:
                for label, total_pct in zone_totals.items():
                    records_list.append({"month": month, "zone_label": label,
                                         "pct": round(total_pct / n, 1)})
        zone_monthly = pd.DataFrame(records_list)
    else:
        # Fallback: avg_hr per activity (less accurate — no warmup/cooldown resolution)
        def _zone_from_avg(hr):
            for i, b in enumerate(friel_bounds):
                if hr < b:
                    return i + 1
            return 5
        df2 = df2.dropna(subset=["avg_hr"]).copy()
        df2["hr_zone"] = df2["avg_hr"].apply(_zone_from_avg)
        df2["zone_label"] = df2["hr_zone"].map(zone_label_map)
        zone_monthly = (
            df2.dropna(subset=["zone_label"])
            .groupby(["month", "zone_label"])
            .size()
            .reset_index(name="runs")
        )
        month_totals = zone_monthly.groupby("month")["runs"].transform("sum")
        zone_monthly["pct"] = (zone_monthly["runs"] / month_totals * 100).round(1)

    return {
        "ef_points": ef_points,
        "zone_dist": df_to_records(zone_monthly),
        "has_data": True,
    }
