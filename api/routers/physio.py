"""
Physio Report endpoint.

GET /api/physio/report   — weekly volume, intensity, sleep, decoupling + auto-flags
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter

from api.deps import state
from api.utils import df_to_records

router = APIRouter()


def _bpm_to_zone(bpm: int, bounds: list[float]) -> int:
    for i, b in enumerate(bounds):
        if bpm < b:
            return i + 1
    return 5


def _histogram_zone_pcts(hist_json: str, bounds: list[float]) -> Optional[dict]:
    try:
        hist = json.loads(hist_json)
    except (TypeError, ValueError):
        return None
    counts = [0] * 5
    total = 0
    for bpm_str, count in hist.items():
        z = _bpm_to_zone(int(bpm_str), bounds)
        counts[z - 1] += count
        total += count
    if total == 0:
        return None
    return {f"z{i+1}": round(counts[i] / total * 100, 1) for i in range(5)}


@router.get("/physio/report")
def get_physio_report(
    injury_date: Optional[date] = None,
    weeks_back: int = 12,
    types: Optional[str] = None,
    zones: str = "141,158,177,188",
):
    # Default injury_date to today
    if injury_date is None:
        injury_date = date.today()

    window_start = injury_date - timedelta(weeks=weeks_back)
    bounds = [float(x) for x in zones.split(",")]

    # ── Activities ─────────────────────────────────────────────────────────
    acts = state.activities.copy()
    acts["date"] = pd.to_datetime(acts["date"])
    acts = acts[
        (acts["date"] >= pd.Timestamp(window_start))
        & (acts["date"] <= pd.Timestamp(injury_date))
    ]
    if types:
        tl = [t.strip() for t in types.split(",") if t.strip()]
        if tl:
            acts = acts[acts["activity_type"].isin(tl)]

    # ── Technique cache ─────────────────────────────────────────────────────
    tech: Optional[pd.DataFrame] = None
    if state.technique is not None:
        tech = state.technique.copy()
        tech["date"] = pd.to_datetime(tech["date"])
        tech = tech[
            (tech["date"] >= pd.Timestamp(window_start))
            & (tech["date"] <= pd.Timestamp(injury_date))
        ]
        if types:
            tl = [t.strip() for t in types.split(",") if t.strip()]
            if tl:
                tech = tech[tech["activity_type"].isin(tl)]

    # ── Weekly volume ───────────────────────────────────────────────────────
    weekly_volume: list[dict] = []
    if not acts.empty:
        acts["week"] = acts["date"].dt.to_period("W").apply(lambda p: str(p.start_time.date()))
        elevation_col = "totalElevationGain" if "totalElevationGain" in acts.columns else None
        grp = acts.groupby("week").agg(
            km=("distance_km", "sum"),
            n_runs=("distance_km", "count"),
        ).reset_index()
        if elevation_col:
            elev = acts.groupby("week")[elevation_col].sum().reset_index()
            elev.columns = ["week", "elevation_m"]
            grp = grp.merge(elev, on="week", how="left")
        else:
            grp["elevation_m"] = None
        grp["km"] = grp["km"].round(1)
        weekly_volume = df_to_records(grp.sort_values("week"))

    # ── Weekly intensity (from hr_histogram if available) ──────────────────
    weekly_intensity: list[dict] = []
    if tech is not None and not tech.empty and "hr_histogram" in tech.columns:
        tech2 = tech.dropna(subset=["hr_histogram"]).copy()
        tech2["week"] = tech2["date"].dt.to_period("W").apply(lambda p: str(p.start_time.date()))
        records = []
        for week, grp in tech2.groupby("week"):
            totals = {f"z{i+1}": 0.0 for i in range(5)}
            n = 0
            for hist_json in grp["hr_histogram"]:
                zpcts = _histogram_zone_pcts(hist_json, bounds)
                if zpcts:
                    for k, v in zpcts.items():
                        totals[k] += v
                    n += 1
            if n > 0:
                records.append({
                    "week": week,
                    **{k: round(v / n, 1) for k, v in totals.items()},
                })
        weekly_intensity = sorted(records, key=lambda r: r["week"])

    # ── Weekly sleep ────────────────────────────────────────────────────────
    weekly_sleep: list[dict] = []
    if state.sleep is not None and not state.sleep.empty:
        sl = state.sleep.copy()
        sl["date"] = pd.to_datetime(sl["date"])
        sl = sl[
            (sl["date"] >= pd.Timestamp(window_start))
            & (sl["date"] <= pd.Timestamp(injury_date))
        ]
        if not sl.empty and "overall_score" in sl.columns:
            sl["week"] = sl["date"].dt.to_period("W").apply(lambda p: str(p.start_time.date()))
            grp = sl.groupby("week")["overall_score"].mean().reset_index()
            grp["overall_score"] = grp["overall_score"].round(1)
            grp.columns = ["week", "avg_score"]
            weekly_sleep = df_to_records(grp.sort_values("week"))

    # ── Decoupling per activity ─────────────────────────────────────────────
    decoupling: list[dict] = []
    if tech is not None and not tech.empty and "aerobic_decoupling" in tech.columns:
        dec = tech.dropna(subset=["aerobic_decoupling"])[
            ["date", "name", "aerobic_decoupling"]
        ].sort_values("date")
        decoupling = df_to_records(dec)

    # ── Weekly technique averages ───────────────────────────────────────────
    weekly_technique: list[dict] = []
    if tech is not None and not tech.empty:
        tech3 = tech.copy()
        tech3["week"] = tech3["date"].dt.to_period("W").apply(lambda p: str(p.start_time.date()))
        agg: dict = {}
        for col, alias in [
            ("avg_cadence", "cadence"),
            ("avg_ground_contact_time", "gct"),
            ("avg_vertical_ratio", "vr"),
        ]:
            if col in tech3.columns:
                agg[alias] = (col, "mean")
        if agg:
            grp = tech3.groupby("week").agg(**{k: v for k, v in agg.items()}).reset_index()
            for col in ["cadence", "gct", "vr"]:
                if col in grp.columns:
                    grp[col] = grp[col].round(1)
            weekly_technique = df_to_records(grp.sort_values("week"))

    # ── Auto-flags ──────────────────────────────────────────────────────────
    flags: list[dict] = []

    if len(weekly_volume) >= 4:
        weeks_sorted = sorted(weekly_volume, key=lambda r: r["week"])
        recent_km = [r["km"] for r in weeks_sorted[-4:]]
        prior_km = [r["km"] for r in weeks_sorted[:-4]] if len(weeks_sorted) > 4 else []

        # Week-over-week spike (any single week >20% above rolling 4-week avg)
        for i in range(1, len(weeks_sorted)):
            prev_avg = sum(r["km"] for r in weeks_sorted[max(0, i-4):i]) / min(i, 4)
            cur = weeks_sorted[i]["km"]
            if prev_avg > 0 and cur > prev_avg * 1.20:
                flags.append({
                    "severity": "warning",
                    "category": "Volume",
                    "message": f"Volume spike on week of {weeks_sorted[i]['week']}: {cur:.0f} km vs {prev_avg:.0f} km rolling avg (+{(cur/prev_avg-1)*100:.0f}%)",
                })
                break

        # Sustained load increase: last 4 weeks vs prior 4 weeks
        if prior_km:
            avg_recent = sum(recent_km) / len(recent_km)
            avg_prior = sum(prior_km[-4:]) / min(len(prior_km), 4)
            if avg_prior > 0 and avg_recent > avg_prior * 1.15:
                flags.append({
                    "severity": "info",
                    "category": "Volume",
                    "message": f"Sustained load increase: last 4 weeks avg {avg_recent:.0f} km/week vs prior {avg_prior:.0f} km/week (+{(avg_recent/avg_prior-1)*100:.0f}%)",
                })

    # Sleep degradation
    if len(weekly_sleep) >= 4:
        sleep_sorted = sorted(weekly_sleep, key=lambda r: r["week"])
        recent_sleep = [r["avg_score"] for r in sleep_sorted[-2:]]
        prior_sleep = [r["avg_score"] for r in sleep_sorted[:-2]]
        if prior_sleep and recent_sleep:
            avg_recent = sum(recent_sleep) / len(recent_sleep)
            avg_prior = sum(prior_sleep[-4:]) / min(len(prior_sleep), 4)
            drop = avg_prior - avg_recent
            if drop >= 5:
                flags.append({
                    "severity": "warning",
                    "category": "Sleep",
                    "message": f"Sleep score dropped {drop:.0f} points in the 2 weeks before injury ({avg_recent:.0f} vs prior avg {avg_prior:.0f})",
                })

    # Intensity shift toward hard sessions
    if len(weekly_intensity) >= 4:
        intens_sorted = sorted(weekly_intensity, key=lambda r: r["week"])
        recent_hard = [(r.get("z4", 0) + r.get("z5", 0)) for r in intens_sorted[-4:]]
        prior_hard = [(r.get("z4", 0) + r.get("z5", 0)) for r in intens_sorted[:-4]]
        if prior_hard:
            avg_recent = sum(recent_hard) / len(recent_hard)
            avg_prior = sum(prior_hard[-4:]) / min(len(prior_hard), 4)
            if avg_recent > avg_prior + 5:
                flags.append({
                    "severity": "warning",
                    "category": "Intensity",
                    "message": f"Shift toward harder efforts: Z4/Z5 averaged {avg_recent:.0f}% in last 4 weeks vs {avg_prior:.0f}% before",
                })

    # Decoupling worsening trend
    if len(decoupling) >= 4:
        dec_sorted = sorted(decoupling, key=lambda r: r["date"])
        recent_dec = [r["aerobic_decoupling"] for r in dec_sorted[-4:]]
        prior_dec = [r["aerobic_decoupling"] for r in dec_sorted[:-4]]
        if prior_dec:
            avg_recent = sum(recent_dec) / len(recent_dec)
            avg_prior = sum(prior_dec[-4:]) / min(len(prior_dec), 4)
            if avg_recent > avg_prior + 2:
                flags.append({
                    "severity": "info",
                    "category": "Fatigue",
                    "message": f"Aerobic decoupling worsened: {avg_recent:.1f}% average in recent activities vs {avg_prior:.1f}% before",
                })

    if not flags:
        flags.append({
            "severity": "ok",
            "category": "General",
            "message": "No significant load, sleep or intensity anomalies detected in this window.",
        })

    return {
        "injury_date": str(injury_date),
        "window_start": str(window_start),
        "weekly_volume": weekly_volume,
        "weekly_intensity": weekly_intensity,
        "weekly_sleep": weekly_sleep,
        "decoupling": decoupling,
        "weekly_technique": weekly_technique,
        "flags": flags,
    }
