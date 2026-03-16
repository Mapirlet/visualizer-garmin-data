import streamlit as st
import pandas as pd
import plotly.express as px

from src.loaders import load_activities, load_sleep, load_technique, load_gps, load_fit_activity

st.set_page_config(page_title="Garmin Data", layout="wide")
st.title("Garmin Data Visualizer")

_TAB_NAMES = [
    "HR vs Pace", "HR vs Sleep", "Training Load", "Sleep Trends",
    "Technique", "Routes", "Progress", "Activity Detail", "Summary & Export",
]
if "active_tab" not in st.session_state:
    st.session_state.active_tab = _TAB_NAMES[0]


@st.cache_data
def get_data():
    activities = load_activities()
    sleep = load_sleep()
    return activities, sleep


def _cache_mtime(filename: str) -> float:
    """Return parquet modification time so cache busts automatically after a rebuild."""
    from pathlib import Path
    p = Path(__file__).parent / "data" / "cache" / filename
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_data
def get_technique(_mtime: float = 0.0):
    try:
        return load_technique()
    except FileNotFoundError:
        return None


@st.cache_data
def get_gps(_mtime: float = 0.0):
    try:
        return load_gps()
    except FileNotFoundError:
        return None


@st.cache_data(show_spinner="Loading FIT file…")
def get_fit(activity_id: int):
    return load_fit_activity(activity_id)


try:
    activities, sleep = get_data()
except FileNotFoundError as e:
    st.error(f"Data not found: {e}\n\nCopy your Garmin export into `data/raw/`.")
    st.stop()

technique = get_technique(_mtime=_cache_mtime("technique.parquet"))
gps_data = get_gps(_mtime=_cache_mtime("gps.parquet"))

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.selectbox("Section", _TAB_NAMES, key="active_tab")
    _active = st.session_state.active_tab

    st.header("Filters")

    dates = activities["date"].dropna().sort_values()
    min_date, max_date = dates.iloc[0], dates.iloc[-1]

    start = st.date_input("From", value=min_date, min_value=min_date, max_value=max_date)
    end = st.date_input("To", value=max_date, min_value=min_date, max_value=max_date)
    if start > end:
        st.error("'From' must be before 'To'.")
        st.stop()

    all_types = sorted(activities["activity_type"].dropna().unique())
    running_types = [t for t in all_types if "running" in t and "treadmill" not in t]
    selected_types = st.multiselect("Activity types", all_types, default=running_types)

    st.markdown("---")
    st.header("HR Zones")
    hr_max = st.number_input("Max HR (bpm)", min_value=150, max_value=230, value=212)
    hr_lthr = st.number_input("Lactate Threshold HR (bpm)", min_value=100, max_value=220, value=189)
    hr_rest = st.number_input("Resting HR (bpm)", min_value=30, max_value=100, value=83)

    # Friel 5-zone model based on LTHR (most accurate when threshold is known)
    # Z1 <85%, Z2 85–89%, Z3 90–94%, Z4 95–99%, Z5 ≥100% of LTHR
    hr_zones = [
        int(hr_lthr * 0.85),
        int(hr_lthr * 0.90),
        int(hr_lthr * 0.95),
        int(hr_lthr * 1.00),
        hr_max,
    ]
    zone_labels = [
        f"Z1 recovery (<{hr_zones[0]})",
        f"Z2 aerobic ({hr_zones[0]}–{hr_zones[1]})",
        f"Z3 tempo ({hr_zones[1]}–{hr_zones[2]})",
        f"Z4 threshold ({hr_zones[2]}–{hr_zones[3]})",
        f"Z5 max (>{hr_zones[3]})",
    ]
    st.caption(f"Friel zones from LTHR {hr_lthr}: Z2={hr_zones[0]}–{hr_zones[1]}, Z3={hr_zones[1]}–{hr_zones[2]}, Z4={hr_zones[2]}–{hr_zones[3]}")

# Z2 boundaries available everywhere in the script
z2_lo, z2_hi = hr_zones[0], hr_zones[1]

mask = (
    (activities["date"] >= start)
    & (activities["date"] <= end)
    & (activities["activity_type"].isin(selected_types))
)
acts = activities[mask].copy()

# ---------------------------------------------------------------------------
# Sections (session-state navigation — no tab reset on rerun)
# ---------------------------------------------------------------------------
_active = st.session_state.active_tab

if _active == "HR vs Pace":
    if technique is None:
        st.info("Technique cache not built yet — using raw summary averages (includes walk segments).\n\nRun `uv run python -m src.cache` once to get clean data.")
        src = acts[acts["avg_pace_min_km"].between(2, 20)].dropna(subset=["avg_hr", "avg_pace_min_km"])
        src = src.rename(columns={"avg_hr": "avg_hr", "avg_pace_min_km": "avg_pace_min_km"})
        clean = False
    else:
        src = technique[
            technique["activity_type"].isin(selected_types)
            & (technique["date"] >= start)
            & (technique["date"] <= end)
        ].dropna(subset=["avg_hr", "avg_pace_min_km"])
        clean = True

    st.subheader("HR vs Pace" + (" (walk segments removed)" if clean else " (raw averages)"))

    if src.empty:
        st.info("No running activities in selected range.")
    else:
        fig = px.scatter(
            src,
            x="avg_pace_min_km",
            y="avg_hr",
            color="activity_type",
            hover_data=["name", "date", "run_ratio"] if clean else ["name", "date"],
            labels={"avg_pace_min_km": "Pace (min/km)", "avg_hr": "HR (bpm)"},
            trendline="ols",
            trendline_scope="overall",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Aerobic efficiency over time
        st.markdown("### Aerobic Efficiency Over Time")
        st.caption("Efficiency Factor = speed (m/s) ÷ HR. Higher = fitter. Filter to a pace band to control for effort.")

        pace_min = float(src["avg_pace_min_km"].min())
        pace_max = float(src["avg_pace_min_km"].max())
        band = st.slider(
            "Pace band (min/km)",
            min_value=round(pace_min, 1),
            max_value=round(pace_max, 1),
            value=(max(round(pace_min, 1), 5.0), min(round(pace_max, 1), 7.0)),
            step=0.1,
        )

        ef_data = src[src["avg_pace_min_km"].between(band[0], band[1])].copy()
        ef_data["efficiency_factor"] = (1000 / (ef_data["avg_pace_min_km"] * 60)) / ef_data["avg_hr"]
        ef_data["date"] = pd.to_datetime(ef_data["date"])
        ef_data = ef_data.sort_values("date")
        ef_data["smoothed_ef"] = ef_data.set_index("date")["efficiency_factor"].rolling("30D").mean().values

        if len(ef_data) < 2:
            st.info("Not enough runs in this pace band. Widen the range.")
        else:
            fig2 = px.scatter(
                ef_data,
                x="date",
                y="efficiency_factor",
                hover_data=["name", "avg_pace_min_km", "avg_hr"],
                labels={"efficiency_factor": "Efficiency Factor", "date": "Date"},
                opacity=0.5,
            )
            fig2.add_scatter(
                x=ef_data["date"],
                y=ef_data["smoothed_ef"],
                mode="lines",
                line=dict(color="#2196F3", width=2),
                name="30-day trend",
            )
            st.plotly_chart(fig2, use_container_width=True)

with tab2:
    st.subheader("HR vs Next-Night Sleep Score")

    # Use clean HR from technique cache if available, fall back to summary
    acts_hr = (
        technique[
            technique["activity_type"].isin(selected_types)
            & (technique["date"] >= start)
            & (technique["date"] <= end)
        ][["date", "name", "avg_hr", "activity_type"]]
        if technique is not None
        else acts[["date", "name", "avg_hr", "activity_type"]].dropna(subset=["avg_hr"])
    )

    sleep_df = sleep[["date", "overall_score"]].copy()
    sleep_df["activity_date"] = (pd.to_datetime(sleep_df["date"]) - pd.Timedelta(days=1)).dt.date

    merged = acts_hr.merge(
        sleep_df[["activity_date", "overall_score"]],
        left_on="date",
        right_on="activity_date",
        how="inner",
    ).dropna(subset=["avg_hr", "overall_score"])

    if merged.empty:
        st.info("No matching activity + sleep data in selected range.")
    else:
        fig = px.scatter(
            merged,
            x="avg_hr",
            y="overall_score",
            color="activity_type",
            hover_data=["name", "date"],
            labels={"avg_hr": "HR (bpm, walk-removed)", "overall_score": "Next-Night Sleep Score"},
            trendline="ols",
        )
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("Training Load Over Time")
    tl = acts.dropna(subset=["training_load"]).sort_values("date")
    if tl.empty:
        st.info("No training load data in selected range.")
    else:
        fig = px.bar(
            tl,
            x="date",
            y="training_load",
            color="activity_type",
            labels={"training_load": "Training Load", "date": "Date"},
        )
        st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("Sleep Trends")

    if "sleep_offset" not in st.session_state:
        st.session_state.sleep_offset = 0

    _sp_raw = st.radio("", ["Week", "Month", "Year", "All"], index=3,
                       horizontal=True, key="sleep_period_radio",
                       label_visibility="collapsed")
    _sp = _sp_raw.lower()
    if st.session_state.get("_sleep_period_prev") != _sp:
        st.session_state.sleep_offset = 0
        st.session_state["_sleep_period_prev"] = _sp

    _stoday = pd.Timestamp.today().normalize()
    _so     = st.session_state.sleep_offset
    _sleep_all = sleep.copy()
    _sleep_all["date"] = pd.to_datetime(_sleep_all["date"])

    if _sp == "week":
        _sw = (_stoday - pd.Timedelta(days=_stoday.dayofweek)) + pd.Timedelta(weeks=_so)
        _se = _sw + pd.Timedelta(days=6)
        _slabel = f"{_sw.strftime('%d %b')} to {_se.strftime('%d %b %Y')}"
        sleep_filtered = _sleep_all[(_sleep_all["date"] >= _sw) & (_sleep_all["date"] <= _se)]
    elif _sp == "month":
        _sref = _stoday + pd.DateOffset(months=_so)
        _slabel = _sref.strftime("%B %Y")
        sleep_filtered = _sleep_all[(_sleep_all["date"].dt.year == _sref.year) & (_sleep_all["date"].dt.month == _sref.month)]
    elif _sp == "year":
        _syear = _stoday.year + _so
        _slabel = str(_syear)
        sleep_filtered = _sleep_all[_sleep_all["date"].dt.year == _syear]
    else:
        _slabel = "All time"
        sleep_filtered = _sleep_all[(_sleep_all["date"] >= pd.Timestamp(start)) & (_sleep_all["date"] <= pd.Timestamp(end))]

    snav_l, snav_mid, snav_r = st.columns([1, 4, 1])
    if snav_l.button("←", use_container_width=True, key="sleep_prev", disabled=(_sp == "all")):
        st.session_state.sleep_offset -= 1
    snav_mid.markdown(f"<div style='text-align:center;padding-top:6px'><b>{_slabel}</b></div>", unsafe_allow_html=True)
    if snav_r.button("→", use_container_width=True, key="sleep_next", disabled=(_sp == "all" or _so >= 0)):
        st.session_state.sleep_offset += 1

    sleep_filtered = sleep_filtered.sort_values("date")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(
            sleep_filtered,
            x="date",
            y="overall_score",
            labels={"overall_score": "Sleep Score", "date": "Date"},
            title="Sleep Score Over Time",
        )
        fig.update_traces(marker_color="#4e91d4")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        sleep_plot = sleep_filtered.rename(columns={
            "deep_min": "Deep",
            "rem_min": "REM",
            "light_min": "Light",
        })
        fig = px.bar(
            sleep_plot,
            x="date",
            y=["Deep", "REM", "Light"],
            labels={"value": "Minutes", "date": "Date", "variable": "Stage"},
            title="Sleep Stage Breakdown",
            barmode="stack",
            color_discrete_map={
                "Deep":  "#1a3a5c",
                "REM":   "#4e91d4",
                "Light": "#aed4f5",
            },
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "**Deep** (dark blue) is the most restorative stage focused on physical recovery, muscle repair and immune function. "
            "Adults need around 1 to 2 hours per night. "
            "**REM** (medium blue) is where dreaming happens and where the brain consolidates memories, learning and mood. "
            "Around 90 minutes per night is ideal. "
            "**Light** (light blue) is the transitional stage between the other two. "
            "It is necessary but the least restorative of the three."
        )

with tab5:
    st.subheader("Running Technique (walk segments removed)")

    if technique is None:
        st.info(
            "Technique cache not built yet. Run this command once:\n\n"
            "```\nuv run python -m src.cache\n```"
        )
    else:
        # Filter to date range and running activities only
        tech = technique[
            technique["activity_type"].isin(selected_types)
            & (technique["date"] >= start)
            & (technique["date"] <= end)
        ].sort_values("date")

        if tech.empty:
            st.info("No technique data in selected range.")
        else:
            # ------------------------------------------------------------------
            # Section 1: Technique over time
            # ------------------------------------------------------------------
            st.markdown("### Technique over time")
            smoothing = st.slider("Rolling average (days)", min_value=1, max_value=30, value=7)

            TECHNIQUE_METRICS = {
                "avg_cadence": "Cadence (spm)",
                "avg_vertical_oscillation": "Vertical Oscillation (cm)",
                "avg_ground_contact_time": "Ground Contact Time (ms)",
                "avg_stride_length": "Stride Length (cm)",
                "avg_vertical_ratio": "Vertical Ratio (%)",
            }

            import plotly.graph_objects as go
            _type_colors = {t: px.colors.qualitative.Plotly[i % 10] for i, t in enumerate(sorted(tech["activity_type"].dropna().unique()))}

            cols = st.columns(2)
            for i, (col_name, label) in enumerate(TECHNIQUE_METRICS.items()):
                if col_name not in tech.columns:
                    continue
                series = tech[["date", col_name, "activity_type"]].dropna()
                if series.empty:
                    continue
                series = series.copy()
                series["date"] = pd.to_datetime(series["date"])
                series = series.sort_values("date")

                fig = go.Figure()
                for atype, grp in series.groupby("activity_type"):
                    color = _type_colors.get(atype, "#888888")
                    grp = grp.set_index("date").sort_index()
                    smoothed = grp[col_name].rolling(f"{smoothing}D").mean().reset_index()
                    fig.add_trace(go.Scatter(
                        x=grp.index, y=grp[col_name],
                        mode="markers", name=atype,
                        marker=dict(color=color, size=5, opacity=0.4),
                        legendgroup=atype, showlegend=True,
                    ))
                    fig.add_trace(go.Scatter(
                        x=smoothed["date"], y=smoothed[col_name],
                        mode="lines", name=f"{atype} (trend)",
                        line=dict(color=color, width=2),
                        legendgroup=atype, showlegend=False,
                    ))
                fig.update_layout(title=label, xaxis_title="Date", yaxis_title=label, height=300, margin=dict(t=40, b=20))
                with cols[i % 2]:
                    st.plotly_chart(fig, use_container_width=True)

            # ------------------------------------------------------------------
            # Section 2: Correlation heatmap
            # ------------------------------------------------------------------
            st.markdown("### Correlation Matrix")
            st.caption("Pearson r between all metrics. Red = positive correlation, blue = negative. Click a cell to drill into the scatter.")

            METRIC_LABELS = {
                "avg_hr": "HR (bpm)",
                "avg_pace_min_km": "Pace (min/km)",
                "avg_cadence": "Cadence (spm)",
                "avg_vertical_oscillation": "Vert. Osc. (cm)",
                "avg_ground_contact_time": "GCT (ms)",
                "avg_stride_length": "Stride (cm)",
                "avg_vertical_ratio": "Vert. Ratio (%)",
            }

            metric_cols = [c for c in METRIC_LABELS if c in tech.columns]
            corr_data = tech[metric_cols].dropna()
            corr_matrix = corr_data.corr()
            corr_matrix.index = [METRIC_LABELS[c] for c in metric_cols]
            corr_matrix.columns = [METRIC_LABELS[c] for c in metric_cols]

            import plotly.graph_objects as go
            heatmap_fig = go.Figure(go.Heatmap(
                z=corr_matrix.values,
                x=list(corr_matrix.columns),
                y=list(corr_matrix.index),
                colorscale="RdBu",
                zmid=0,
                zmin=-1, zmax=1,
                text=[[f"{v:.2f}" for v in row] for row in corr_matrix.values],
                texttemplate="%{text}",
                hovertemplate="%{y} vs %{x}<br>r = %{z:.3f}<extra></extra>",
            ))
            heatmap_fig.update_layout(height=400, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(heatmap_fig, use_container_width=True)

            # ------------------------------------------------------------------
            # Section 3: Drill-down scatter
            # ------------------------------------------------------------------
            st.markdown("### Drill-down Scatter")

            col_a, col_b = st.columns(2)
            with col_a:
                x_metric = st.selectbox("X axis", list(METRIC_LABELS.keys()),
                                        format_func=lambda k: METRIC_LABELS[k], index=2)  # cadence
            with col_b:
                y_metric = st.selectbox("Y axis", list(METRIC_LABELS.keys()),
                                        format_func=lambda k: METRIC_LABELS[k], index=0)  # HR

            scatter_data = tech[[x_metric, y_metric, "name", "date", "run_ratio", "activity_type"]].dropna()
            if len(scatter_data) >= 3:
                scatter_data = scatter_data.copy()
                sfig = px.scatter(
                    scatter_data,
                    x=x_metric,
                    y=y_metric,
                    color="activity_type",
                    hover_data=["name", "date", "run_ratio"],
                    labels={x_metric: METRIC_LABELS[x_metric], y_metric: METRIC_LABELS[y_metric]},
                    trendline="ols",
                    trendline_scope="trace",
                )
                st.plotly_chart(sfig, use_container_width=True)
            else:
                st.info("Not enough data for selected metrics.")

with tab6:
    st.subheader("Route Heatmap")

    if gps_data is None:
        st.info(
            "GPS cache not built yet. Run this command once:\n\n"
            "```\nuv run python -m src.gps_cache\n```"
        )
    else:
        import folium
        from folium.plugins import HeatMap
        from streamlit_folium import folium_static

        # Filter by sidebar date range and activity type
        gps_filtered = gps_data[
            (gps_data["date"] >= start)
            & (gps_data["date"] <= end)
            & (gps_data["activity_type"].isin(selected_types))
        ]

        if gps_filtered.empty:
            st.info("No GPS data in selected range / activity types.")
        else:
            n_acts = gps_filtered["activity_id"].nunique()
            st.caption(f"{len(gps_filtered):,} GPS points from {n_acts} activities")

            # Heatmap controls
            col_ctrl1, col_ctrl2 = st.columns(2)
            with col_ctrl1:
                radius = st.slider("Heat radius (px)", min_value=1, max_value=25, value=6)
            with col_ctrl2:
                blur = st.slider("Blur", min_value=0, max_value=5, value=2)

            pts = gps_filtered[["lat", "lon"]]
            if len(pts) > 200_000:
                pts = pts.sample(200_000, random_state=42)

            # Build folium map centered on Liège
            m = folium.Map(
                location=[50.6326, 5.5797],
                zoom_start=13,
                tiles="CartoDB positron",
            )
            HeatMap(pts.values.tolist(), radius=radius, blur=blur, min_opacity=0.3).add_to(m)

            folium_static(m, width=1200, height=600)

# ---------------------------------------------------------------------------
# Tab 7: Progress
# ---------------------------------------------------------------------------
with tab7:
    st.subheader("Fitness Progress")

    # --- VO2max trend ---
    st.markdown("### VO2max Over Time")
    st.caption("Garmin's estimated VO2max from running activities. Upward trend = improving aerobic fitness.")

    vo2 = acts.dropna(subset=["vo2max"]).copy()
    vo2 = vo2[vo2["vo2max"] > 0].sort_values("date")
    if vo2.empty:
        st.info("No VO2max data in selected range.")
    else:
        vo2["date"] = pd.to_datetime(vo2["date"])
        vo2["smoothed"] = vo2.set_index("date")["vo2max"].rolling("30D").mean().values
        fig_vo2 = px.scatter(
            vo2, x="date", y="vo2max",
            hover_data=["name", "activity_type"],
            labels={"vo2max": "VO2max (ml/kg/min)", "date": "Date"},
            opacity=0.5,
        )
        fig_vo2.add_scatter(
            x=vo2["date"], y=vo2["smoothed"],
            mode="lines", line=dict(color="#2196F3", width=2), name="30-day trend"
        )
        st.plotly_chart(fig_vo2, use_container_width=True)

    # --- Pace at fixed HR ---
    st.markdown("### Pace at Fixed HR (effort-controlled progress)")
    st.caption(
        "Filter to a narrow HR band so effort is constant. "
        "If pace improves over time at the same HR → you're getting fitter. "
        "Uses clean running-only averages (walk segments removed)."
    )

    if technique is None:
        st.info("Technique cache needed. Run `uv run python -m src.cache`.")
    else:
        src_prog = technique[
            technique["activity_type"].isin(selected_types)
            & (technique["date"] >= start)
            & (technique["date"] <= end)
        ].dropna(subset=["avg_hr", "avg_pace_min_km"])

        if src_prog.empty:
            st.info("No data in selected range.")
        else:
            hr_min = int(src_prog["avg_hr"].min())
            hr_max = int(src_prog["avg_hr"].max())
            hr_band = st.slider(
                "HR band (bpm)", min_value=hr_min, max_value=hr_max,
                value=(max(hr_min, z2_lo), min(hr_max, z2_hi)), step=1,
            )
            prog_data = src_prog[src_prog["avg_hr"].between(hr_band[0], hr_band[1])].copy()
            if len(prog_data) < 3:
                st.info("Not enough runs in this HR band. Widen the range.")
            else:
                prog_data["date"] = pd.to_datetime(prog_data["date"])
                prog_data = prog_data.sort_values("date")
                prog_data["smoothed_pace"] = (
                    prog_data.set_index("date")["avg_pace_min_km"].rolling("60D").mean().values
                )
                fig_prog = px.scatter(
                    prog_data, x="date", y="avg_pace_min_km",
                    color="activity_type",
                    hover_data=["name", "avg_hr"],
                    labels={"avg_pace_min_km": "Pace (min/km)", "date": "Date"},
                    opacity=0.5,
                )
                fig_prog.add_scatter(
                    x=prog_data["date"], y=prog_data["smoothed_pace"],
                    mode="lines", line=dict(color="#e53935", width=2), name="60-day trend"
                )
                fig_prog.update_yaxes(autorange="reversed")
                st.plotly_chart(fig_prog, use_container_width=True)
                n = len(prog_data)
                first_pace = prog_data["avg_pace_min_km"].iloc[:max(1, n//5)].mean()
                last_pace = prog_data["avg_pace_min_km"].iloc[-max(1, n//5):].mean()
                delta = first_pace - last_pace
                if abs(delta) > 0.05:
                    direction = "faster" if delta > 0 else "slower"
                    st.metric(
                        label=f"Pace change at HR {hr_band[0]}–{hr_band[1]} bpm",
                        value=f"{last_pace:.2f} min/km",
                        delta=f"{abs(delta*60):.0f}s/km {direction}",
                        delta_color="normal" if delta > 0 else "inverse",
                    )

    # --- Aerobic decoupling trend ---
    st.markdown("### Aerobic Decoupling Over Time")
    st.caption(
        "Efficiency Factor (speed/HR) first half vs second half of each run. "
        "**< 5% = aerobic base solid** for that effort. > 10% = aerobically taxed. "
        "This is the cleanest within-run fitness indicator — it controls for day-to-day variability "
        "because you're comparing yourself against yourself within the same run."
    )

    if technique is not None and "aerobic_decoupling" in technique.columns:
        dec_data = technique[
            technique["activity_type"].isin(selected_types)
            & (technique["date"] >= start)
            & (technique["date"] <= end)
        ].dropna(subset=["aerobic_decoupling"]).copy()
        dec_data["date"] = pd.to_datetime(dec_data["date"])
        dec_data = dec_data.sort_values("date")
        dec_data["smoothed"] = dec_data.set_index("date")["aerobic_decoupling"].rolling("60D").mean().values

        if len(dec_data) >= 3:
            fig_dec = px.scatter(
                dec_data, x="date", y="aerobic_decoupling",
                color="activity_type",
                hover_data=["name"],
                labels={"aerobic_decoupling": "Decoupling (%)", "date": "Date"},
                opacity=0.5,
            )
            fig_dec.add_scatter(
                x=dec_data["date"], y=dec_data["smoothed"],
                mode="lines", line=dict(color="#333", width=2), name="60-day trend"
            )
            # reference lines
            for y, color, label in [(5, "#43a047", "5% — good"), (10, "#e53935", "10% — poor")]:
                fig_dec.add_hline(y=y, line_dash="dash", line_color=color,
                                  annotation_text=label, annotation_position="right")
            st.plotly_chart(fig_dec, use_container_width=True)
        else:
            st.info("Rebuild the technique cache to get decoupling data: `uv run python -m src.cache`")
    else:
        st.info("Rebuild the technique cache to get decoupling data: `uv run python -m src.cache`")

    # --- Z2 fitness tracker ---
    st.markdown("### Z2 Fitness Tracker")
    st.caption(
        f"The best way to see Z2 improvement: at the same low HR, are you running faster over time? "
        f"**Your Z2 = {z2_lo}–{z2_hi} bpm** (85–90% of LTHR {hr_lthr}). "
        f"Adaptations: more mitochondria, better fat oxidation → same effort, faster pace. "
        f"This can take 3–6 months of consistent Z2 work to show up clearly."
    )

    if technique is None:
        st.info("Rebuild cache: `uv run python -m src.cache`")
    else:
        tech_z2 = technique[
            technique["activity_type"].isin(selected_types)
            & (technique["date"] >= start)
            & (technique["date"] <= end)
        ].copy()
        tech_z2["date"] = pd.to_datetime(tech_z2["date"])

        # Assign zones dynamically based on sidebar HR settings
        def _avg_hr_zone(hr):
            if pd.isna(hr):
                return None
            boundaries = [0] + hr_zones
            for i in range(1, 6):
                if hr < boundaries[i]:
                    return i
            return 5
        tech_z2["hr_zone"] = tech_z2["avg_hr"].apply(_avg_hr_zone)

        z2_col1, z2_col2 = st.columns(2)

        # EF at Z2 HR (using sidebar zone boundaries)
        with z2_col1:
            st.markdown(f"**Efficiency Factor in Z2 (HR {z2_lo}–{z2_hi} bpm)**")
            st.caption("Speed / HR — higher = more efficient. Upward trend = Z2 base improving.")
            z2_ef = tech_z2[tech_z2["avg_hr"].between(z2_lo, z2_hi)].dropna(subset=["avg_hr", "avg_pace_min_km"]).copy()
            if len(z2_ef) >= 3:
                z2_ef["ef"] = (1000 / (z2_ef["avg_pace_min_km"] * 60)) / z2_ef["avg_hr"]
                z2_ef = z2_ef.sort_values("date")
                z2_ef["smoothed_ef"] = z2_ef.set_index("date")["ef"].rolling("60D").mean().values
                fig_ef = px.scatter(z2_ef, x="date", y="ef", opacity=0.5,
                                    color="activity_type",
                                    labels={"ef": "Efficiency Factor", "date": "Date"})
                fig_ef.add_scatter(x=z2_ef["date"], y=z2_ef["smoothed_ef"],
                                   mode="lines", line=dict(color="#1565c0", width=2), name="60-day trend")
                st.plotly_chart(fig_ef, use_container_width=True)
                n = len(z2_ef)
                ef_old = z2_ef["ef"].iloc[:max(1, n//4)].mean()
                ef_new = z2_ef["ef"].iloc[-max(1, n//4):].mean()
                pct = (ef_new - ef_old) / ef_old * 100
                st.metric("EF change (first vs last quarter)", f"{ef_new:.4f}",
                          delta=f"{pct:+.1f}%", delta_color="normal")
            else:
                st.info(f"Not enough runs with avg HR in Z2 ({z2_lo}–{z2_hi}) in this range.")

        # HR zone distribution per month — computed dynamically from avg_hr
        with z2_col2:
            st.markdown("**HR zone distribution per month**")
            st.caption(
                f"Based on your zones (Friel/LTHR). "
                f"Polarised = lots of Z1/Z2 ({hr_zones[0]} bpm), some Z4/Z5, minimal Z3."
            )
            if "hr_zone" in tech_z2.columns and tech_z2["hr_zone"].notna().any():
                tech_z2["month"] = tech_z2["date"].dt.to_period("M").astype(str)
                zone_map = {1: "Z1 recovery", 2: "Z2 aerobic", 3: "Z3 tempo", 4: "Z4 threshold", 5: "Z5 max"}
                tech_z2["zone_label"] = tech_z2["hr_zone"].map(zone_map)
                zone_monthly = (
                    tech_z2.dropna(subset=["zone_label"])
                    .groupby(["month", "zone_label"])
                    .size()
                    .reset_index(name="runs")
                )
                # convert to % of runs per month
                month_totals = zone_monthly.groupby("month")["runs"].transform("sum")
                zone_monthly["pct"] = zone_monthly["runs"] / month_totals * 100
                fig_zones = px.bar(
                    zone_monthly, x="month", y="pct", color="zone_label",
                    color_discrete_map={
                        "Z1 recovery": "#90caf9", "Z2 aerobic": "#66bb6a",
                        "Z3 tempo": "#ffa726",    "Z4 threshold": "#ef5350", "Z5 max": "#b71c1c"
                    },
                    labels={"month": "Month", "pct": "% of runs", "zone_label": "Zone"},
                    category_orders={"zone_label": list(zone_map.values())},
                )
                fig_zones.update_layout(barmode="stack", height=350)
                st.plotly_chart(fig_zones, use_container_width=True)
            else:
                st.info("No HR zone data available.")

# ---------------------------------------------------------------------------
# Tab 8: Activity Detail
# ---------------------------------------------------------------------------

# Zone colors: poor → excellent (matches Garmin palette)
_ZONE_COLORS = {
    "walking":   "#aaaaaa",
    "poor":      "#d73027",
    "fair":      "#fc8d59",
    "moderate":  "#fee090",
    "good":      "#91cf60",
    "excellent": "#1a9850",
}
_ZONE_ORDER = ["walking", "poor", "fair", "moderate", "good", "excellent"]

# Zone background bands per metric: list of (y0, y1, zone_name).
# Sources: Garmin official docs + TrainingPeaks/SportTracks research.
# Adjusted for a 182 cm runner (cadence slightly lower than sub-170 cm runners).
_ZONE_BANDS = {
    # Cadence: 165–178 spm optimal for 182 cm (vs 170–180 for shorter runners)
    "cadence_spm": [
        (0,   158, "poor"),
        (158, 165, "fair"),
        (165, 172, "moderate"),
        (172, 178, "good"),
        (178, 999, "excellent"),
    ],
    # Vertical oscillation (cm): lower = better
    "vertical_oscillation": [
        (0,    6.5, "excellent"),
        (6.5,  8.0, "good"),
        (8.0,  9.5, "moderate"),
        (9.5, 11.0, "fair"),
        (11.0, 999, "poor"),
    ],
    # Ground contact time (ms): lower = better
    "ground_contact_time": [
        (0,   200, "excellent"),
        (200, 230, "good"),
        (230, 260, "moderate"),
        (260, 300, "fair"),
        (300, 999, "poor"),
    ],
    # Vertical ratio (%): lower = better.
    # Official Garmin zones (chest HRM): <6.1 purple, 6.1-7.4 blue, 7.5-8.6 green, 8.7-10.1 orange, >10.1 red
    # Waist pod thresholds are more lenient (~+1.5%). We use a midpoint to be fair to both.
    "vertical_ratio": [
        (0,   6.1, "excellent"),
        (6.1, 7.4, "good"),
        (7.4, 8.7, "moderate"),
        (8.7, 10.1, "fair"),
        (10.1, 999, "poor"),
    ],
}

def _assign_zone_series(values: pd.Series, metric: str, grade: pd.Series) -> pd.Series:
    """Assign a zone label per row, with grade adjustments for technique metrics."""
    bands = _ZONE_BANDS.get(metric)
    if bands is None:
        return pd.Series("moderate", index=values.index)

    # Grade adjustments: relax thresholds on uphills
    if metric == "cadence_spm":
        # On steep uphills cadence naturally drops ~5 spm → shift tolerance
        adj = (grade.clip(lower=0) * 0.5).clip(upper=8)
        v = values + adj  # pretend cadence is higher when going uphill
    elif metric == "vertical_oscillation":
        adj = (grade.clip(lower=0) * 0.1).clip(upper=1.5)
        v = values - adj  # tolerate higher VO uphill
    elif metric == "ground_contact_time":
        adj = (grade.clip(lower=0) * 2.0).clip(upper=30)
        v = values - adj
    else:
        v = values

    zones = pd.Series("moderate", index=values.index)
    for y0, y1, zone in bands:
        mask = (v >= y0) & (v < y1)
        zones[mask] = zone
    return zones


with tab8:
    st.subheader("Activity Detail")

    run_acts = acts.dropna(subset=["date"]).sort_values("date", ascending=False)
    if run_acts.empty:
        st.info("No activities in selected range.")
    else:
        run_acts["label"] = (run_acts["date"].astype(str) + "  " + run_acts["name"].fillna("") +
                             "  (" + run_acts["distance_km"].round(1).astype(str) + " km)")
        selected_label = st.selectbox("Activity", run_acts["label"].tolist())
        selected_row = run_acts[run_acts["label"] == selected_label].iloc[0]
        activity_id = int(selected_row["activity_id"])

        fit_df = get_fit(activity_id)

        if fit_df is None or fit_df.empty:
            st.warning("No FIT data found for this activity.")
        else:
            fit_df = fit_df.copy()

            # --- Position ---
            _S2D = 180 / 2**31
            has_gps = "position_lat" in fit_df.columns and "position_long" in fit_df.columns
            if has_gps:
                fit_df = fit_df.dropna(subset=["position_lat", "position_long"])
                fit_df["lat"] = fit_df["position_lat"].astype(float) * _S2D
                fit_df["lon"] = fit_df["position_long"].astype(float) * _S2D

            # --- Speed & pace ---
            speed_col = "enhanced_speed" if "enhanced_speed" in fit_df.columns else "speed"
            if speed_col in fit_df.columns:
                spd = pd.to_numeric(fit_df[speed_col], errors="coerce").fillna(0)
                fit_df["is_walking"] = spd < 2.0
                fit_df["pace"] = (1000 / spd.clip(lower=0.1) / 60).where(spd > 0.5)

            # --- Distance & altitude ---
            if "distance" in fit_df.columns:
                fit_df["distance_km"] = pd.to_numeric(fit_df["distance"], errors="coerce") / 1000
            if "altitude" in fit_df.columns:
                fit_df["altitude"] = pd.to_numeric(fit_df["altitude"], errors="coerce")
            if "heart_rate" in fit_df.columns:
                fit_df["heart_rate"] = pd.to_numeric(fit_df["heart_rate"], errors="coerce")

            # --- Grade (smoothed) ---
            if "altitude" in fit_df.columns and "distance" in fit_df.columns:
                alt_s = fit_df["altitude"].rolling(10, center=True, min_periods=1).mean()
                dist_d = fit_df["distance"].diff().clip(lower=0.5)
                fit_df["grade_pct"] = (alt_s.diff() / dist_d * 100).clip(-30, 30).fillna(0)
            else:
                fit_df["grade_pct"] = 0.0

            # --- Grade Adjusted Pace ---
            if "pace" in fit_df.columns:
                up_factor   = 1 + fit_df["grade_pct"].clip(lower=0) * 0.033
                down_factor = 1 - fit_df["grade_pct"].clip(upper=0).abs() * 0.018
                fit_df["gap"] = fit_df["pace"] / (up_factor * down_factor).clip(lower=0.5)

            # --- Cadence spm ---
            if "cadence" in fit_df.columns:
                fit_df["cadence_spm"] = pd.to_numeric(fit_df["cadence"], errors="coerce") * 2

            # --- Technique columns + outlier clipping ---
            for raw_col, dest_col, scale, valid_range in [
                ("vertical_oscillation", "vertical_oscillation", 1/10,  (3.0, 20.0)),   # cm
                ("stance_time",          "ground_contact_time",  1.0,   (100, 700)),     # ms
                ("vertical_ratio",       "vertical_ratio",       1.0,   (3.0, 20.0)),   # %
                ("step_length",          "stride_length",        1/10,  (20.0, 200.0)), # cm
            ]:
                if raw_col in fit_df.columns:
                    v = pd.to_numeric(fit_df[raw_col], errors="coerce") * scale
                    fit_df[dest_col] = v.where(v.between(*valid_range))

            # Cadence outlier clip: realistic doubled range 100–240 spm
            if "cadence_spm" in fit_df.columns:
                fit_df["cadence_spm"] = fit_df["cadence_spm"].where(fit_df["cadence_spm"].between(100, 240))

            # --- Map: continuous colorscale ---
            color_by = st.radio(
                "Color track by",
                ["pace", "heart_rate", "altitude"],
                format_func=lambda k: {"pace": "Pace", "heart_rate": "Heart Rate", "altitude": "Altitude"}[k],
                horizontal=True,
            )

            if has_gps and color_by in fit_df.columns:
                map_data = fit_df[["lat", "lon", color_by]].dropna()
                if color_by == "pace":
                    map_data = map_data[map_data["pace"].between(3, 12)]
                color_label = {"pace": "Pace (min/km)", "heart_rate": "HR (bpm)", "altitude": "Altitude (m)"}[color_by]
                fig_map = px.scatter_mapbox(
                    map_data, lat="lat", lon="lon", color=color_by,
                    color_continuous_scale="RdYlGn_r",
                    zoom=13, mapbox_style="carto-positron",
                    labels={color_by: color_label}, height=450,
                )
                fig_map.update_traces(marker=dict(size=4, opacity=0.85))
                fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig_map, use_container_width=True)
            elif has_gps:
                st.info(f"'{color_by}' not available for this activity.")

            # --- Charts with zone bands + colored markers ---
            st.markdown("---")
            st.caption(
                "Zone bands based on research benchmarks adjusted for 182 cm. "
                "Thresholds for cadence/VO/GCT are relaxed proportionally on uphills. "
                "Grey markers = walking (excluded from zone evaluation)."
            )

            # --- Aerobic decoupling for this run ---
            from src.loaders import compute_aerobic_decoupling as _compute_decoupling
            if "enhanced_speed" in fit_df.columns or "speed" in fit_df.columns:
                dec = _compute_decoupling(fit_df)
                if dec is not None:
                    if dec < 5:
                        dec_color, dec_label = "normal", f"{dec:.1f}% — aerobic base solid ✓"
                    elif dec < 10:
                        dec_color, dec_label = "off", f"{dec:.1f}% — borderline"
                    else:
                        dec_color, dec_label = "inverse", f"{dec:.1f}% — aerobically taxed for this effort"
                    st.metric(
                        "Aerobic Decoupling (Pa:HR)",
                        value=dec_label,
                        help="Compares efficiency factor (speed/HR) in first vs second half of the run. "
                             "<5% = good aerobic base. >10% = this effort exceeds your current aerobic fitness.",
                        delta_color=dec_color,
                    )

            import plotly.graph_objects as go

            x_col = "distance_km" if "distance_km" in fit_df.columns else None
            x_label = "Distance (km)"

            chart_pairs = [
                ("heart_rate",           "HR (bpm)",                   None),
                ("gap",                  "Grade-Adj. Pace (min/km)",   None),
                ("cadence_spm",          "Cadence (spm)",              "cadence_spm"),
                ("vertical_oscillation", "Vertical Oscillation (cm)",  "vertical_oscillation"),
                ("ground_contact_time",  "Ground Contact Time (ms)",   "ground_contact_time"),
                ("vertical_ratio",       "Vertical Ratio (%)",         "vertical_ratio"),
            ]

            chart_cols = st.columns(2)
            ci = 0
            for col, label, zone_metric in chart_pairs:
                if col not in fit_df.columns:
                    continue
                plot_data = fit_df.dropna(subset=[col] + ([x_col] if x_col else [])).copy()
                if plot_data.empty:
                    continue

                fig_c = go.Figure()

                # Elevation backdrop on secondary y-axis
                if "altitude" in fit_df.columns and x_col:
                    alt_data = fit_df.dropna(subset=["altitude", x_col])
                    fig_c.add_trace(go.Scatter(
                        x=alt_data[x_col], y=alt_data["altitude"],
                        fill="tozeroy", mode="none",
                        fillcolor="rgba(180,180,180,0.18)",
                        yaxis="y2", showlegend=False, hoverinfo="skip",
                    ))

                # Horizontal zone bands (only for technique metrics)
                if zone_metric and zone_metric in _ZONE_BANDS:
                    bands = _ZONE_BANDS[zone_metric]
                    y_vals = plot_data[col].dropna()
                    if not y_vals.empty:
                        y_min = y_vals.min() * 0.97
                        y_max = y_vals.max() * 1.03
                        for y0, y1, zone in bands:
                            b0 = max(y0, y_min)
                            b1 = min(y1, y_max)
                            if b0 >= b1:
                                continue
                            c_rgb = _ZONE_COLORS[zone].lstrip("#")
                            r, g, b = int(c_rgb[0:2], 16), int(c_rgb[2:4], 16), int(c_rgb[4:6], 16)
                            fig_c.add_hrect(
                                y0=b0, y1=b1,
                                fillcolor=f"rgba({r},{g},{b},0.12)",
                                line_width=0, layer="below",
                            )

                # Assign zones and split into walking / running-by-zone
                if zone_metric:
                    grade = plot_data.get("grade_pct", pd.Series(0.0, index=plot_data.index))
                    plot_data["_zone"] = _assign_zone_series(plot_data[col], zone_metric, grade)
                    walking_pts = plot_data[plot_data["is_walking"]] if "is_walking" in plot_data.columns else plot_data.iloc[0:0]
                    run_pts = plot_data[~plot_data["is_walking"]] if "is_walking" in plot_data.columns else plot_data

                    # colored markers per zone
                    for zone in _ZONE_ORDER[1:]:  # skip "walking"
                        pts = run_pts[run_pts["_zone"] == zone]
                        if pts.empty:
                            continue
                        x_vals = pts[x_col] if x_col else pts.index
                        fig_c.add_trace(go.Scatter(
                            x=x_vals, y=pts[col],
                            mode="markers",
                            marker=dict(color=_ZONE_COLORS[zone], size=4, opacity=0.8),
                            name=zone.capitalize(), showlegend=(ci == 0),
                        ))
                    # walking in grey
                    if not walking_pts.empty:
                        x_vals = walking_pts[x_col] if x_col else walking_pts.index
                        fig_c.add_trace(go.Scatter(
                            x=x_vals, y=walking_pts[col],
                            mode="markers", marker=dict(color="#aaaaaa", size=3, opacity=0.5),
                            name="Walking", showlegend=(ci == 0),
                        ))
                else:
                    # HR and pace: simple colored line, walk in grey
                    run_pts  = plot_data[~plot_data["is_walking"]] if "is_walking" in plot_data.columns else plot_data
                    walk_pts = plot_data[plot_data["is_walking"]]  if "is_walking" in plot_data.columns else plot_data.iloc[0:0]
                    line_color = "#e53935" if col == "heart_rate" else "#1e88e5"
                    if not run_pts.empty:
                        x_vals = run_pts[x_col] if x_col else run_pts.index
                        fig_c.add_trace(go.Scatter(x=x_vals, y=run_pts[col],
                            mode="lines", line=dict(color=line_color, width=1.5), name=label, showlegend=False))
                    if not walk_pts.empty:
                        x_vals = walk_pts[x_col] if x_col else walk_pts.index
                        fig_c.add_trace(go.Scatter(x=x_vals, y=walk_pts[col],
                            mode="markers", marker=dict(color="#aaaaaa", size=3), showlegend=False))

                yaxis_cfg = dict(title=label)
                if col == "gap":
                    yaxis_cfg["autorange"] = "reversed"

                fig_c.update_layout(
                    height=250, margin=dict(t=30, b=10, l=10, r=40),
                    title=dict(text=label, font=dict(size=12)),
                    xaxis=dict(title=x_label),
                    yaxis=yaxis_cfg,
                    yaxis2=dict(overlaying="y", side="right", showticklabels=False, showgrid=False),
                    showlegend=(ci == 0 and zone_metric is not None),
                    legend=dict(orientation="h", y=1.1, x=0),
                )
                with chart_cols[ci % 2]:
                    st.plotly_chart(fig_c, use_container_width=True)
                ci += 1

# ---------------------------------------------------------------------------
# Tab 9: Summary & Export
# ---------------------------------------------------------------------------
with tab9:
    st.subheader("Summary & LLM Export")
    st.caption("Statistics computed on running segments only (walk segments excluded). Use the text at the bottom to paste into ChatGPT / Claude for analysis.")

    if technique is None:
        st.info("Technique cache needed. Run `uv run python -m src.cache`.")
    else:
        tech_filtered = technique[
            technique["activity_type"].isin(selected_types)
            & (technique["date"] >= start)
            & (technique["date"] <= end)
        ].copy()

        acts_filtered = acts.copy()

        if tech_filtered.empty:
            st.info("No data in selected range.")
        else:
            tech_filtered["date"] = pd.to_datetime(tech_filtered["date"])
            acts_filtered["date"] = pd.to_datetime(acts_filtered["date"])

            # ── Navigable activity log ───────────────────────────────────────────────
            st.markdown("### Activity Log")

            # Build full merged table (one row per activity)
            _log = acts_filtered[acts_filtered["activity_type"].isin(selected_types)].copy()
            _log["date"] = pd.to_datetime(_log["date"])
            _tech_log = tech_filtered[["date", "activity_type", "avg_cadence",
                                        "avg_vertical_oscillation", "avg_ground_contact_time",
                                        "avg_vertical_ratio", "aerobic_decoupling"]].copy()
            _log = _log.merge(_tech_log, on=["date", "activity_type"], how="left")

            if "nav_offset" not in st.session_state:
                st.session_state.nav_offset = 0

            _nav_raw = st.radio("", ["Week", "Month", "Year", "All"], index=3,
                                horizontal=True, key="nav_period_radio",
                                label_visibility="collapsed")
            period = _nav_raw.lower()
            if st.session_state.get("_nav_period_prev") != period:
                st.session_state.nav_offset = 0
                st.session_state["_nav_period_prev"] = period

            today = pd.Timestamp.today().normalize()
            offset = st.session_state.nav_offset

            if period == "week":
                week_start = (today - pd.Timedelta(days=today.dayofweek)) + pd.Timedelta(weeks=offset)
                week_end   = week_start + pd.Timedelta(days=6)
                period_label = f"{week_start.strftime('%d %b')} to {week_end.strftime('%d %b %Y')}"
                mask = (_log["date"] >= week_start) & (_log["date"] <= week_end)
            elif period == "month":
                ref = today + pd.DateOffset(months=offset)
                period_label = ref.strftime("%B %Y")
                mask = (_log["date"].dt.year == ref.year) & (_log["date"].dt.month == ref.month)
            elif period == "year":
                ref_year = today.year + offset
                period_label = str(ref_year)
                mask = _log["date"].dt.year == ref_year
            else:
                mask = pd.Series(True, index=_log.index)
                period_label = "All time"

            nav_l, nav_mid, nav_r = st.columns([1, 4, 1])
            if nav_l.button("←", use_container_width=True, key="nav_prev", disabled=(period == "all")):
                st.session_state.nav_offset -= 1
            nav_mid.markdown(f"<div style='text-align:center;padding-top:6px'><b>{period_label}</b></div>", unsafe_allow_html=True)
            if nav_r.button("→", use_container_width=True, key="nav_next", disabled=(period == "all" or offset >= 0)):
                st.session_state.nav_offset += 1
            _log_period = _log[mask].sort_values("date", ascending=False)

            if _log_period.empty:
                st.info("No activities in this period.")
            else:
                _display = _log_period.rename(columns={
                    "date":                       "Date",
                    "activity_type":              "Type",
                    "name":                       "Name",
                    "distance_km":                "Dist (km)",
                    "avg_pace_min_km":            "Pace",
                    "avg_hr":                     "HR",
                    "avg_cadence":                "Cadence",
                    "avg_vertical_oscillation":   "VO (cm)",
                    "avg_ground_contact_time":    "GCT (ms)",
                    "avg_vertical_ratio":         "VR (%)",
                    "aerobic_decoupling":         "Decoupling (%)",
                    "training_load":              "Load",
                    "vo2max":                     "VO2max",
                })
                _cols = [c for c in ["Date", "Type", "Name", "Dist (km)", "Pace", "HR",
                                      "Cadence", "VO (cm)", "GCT (ms)", "VR (%)",
                                      "Decoupling (%)", "Load", "VO2max"] if c in _display.columns]
                _display["Date"] = _display["Date"].dt.strftime("%Y-%m-%d")
                st.dataframe(_display[_cols].round(2), use_container_width=True, hide_index=True)

            st.divider()

            # ── Overall statistics ──────────────────────────────────────────────────
            st.markdown("### Overall Statistics")

            STAT_COLS = {
                "avg_pace_min_km":            "Pace (min/km)",
                "avg_hr":                     "HR (bpm)",
                "avg_cadence":                "Cadence (spm)",
                "avg_vertical_oscillation":   "Vert. Osc. (cm)",
                "avg_ground_contact_time":    "GCT (ms)",
                "avg_vertical_ratio":         "Vert. Ratio (%)",
                "aerobic_decoupling":         "Aerobic Decoupling (%)",
            }
            ACT_COLS = {
                "distance_km":    "Distance (km)",
                "duration_min":   "Duration (min)",
                "training_load":  "Training Load",
                "vo2max":         "VO2max",
            }

            stat_rows = []
            for col, label in STAT_COLS.items():
                if col not in tech_filtered.columns:
                    continue
                s = tech_filtered[col].dropna()
                if s.empty:
                    continue
                stat_rows.append({
                    "Metric": label,
                    "Mean":   round(s.mean(), 2),
                    "Median": round(s.median(), 2),
                    "Std":    round(s.std(), 2),
                    "Best":   round(s.min() if "pace" in col or "gct" in col.lower() or "osc" in col.lower() or "ratio" in col.lower() else s.max(), 2),
                    "Worst":  round(s.max() if "pace" in col or "gct" in col.lower() or "osc" in col.lower() or "ratio" in col.lower() else s.min(), 2),
                    "N runs": len(s),
                })
            for col, label in ACT_COLS.items():
                if col not in acts_filtered.columns:
                    continue
                s = acts_filtered[col].dropna()
                s = s[s > 0] if col in ("distance_km", "duration_min", "training_load", "vo2max") else s
                if s.empty:
                    continue
                stat_rows.append({
                    "Metric": label,
                    "Mean":   round(s.mean(), 2),
                    "Median": round(s.median(), 2),
                    "Std":    round(s.std(), 2),
                    "Best":   round(s.max(), 2),
                    "Worst":  round(s.min(), 2),
                    "N runs": len(s),
                })

            overall_df = pd.DataFrame(stat_rows).set_index("Metric")
            st.dataframe(overall_df, use_container_width=True)

            # ── Monthly breakdown ───────────────────────────────────────────────────
            st.markdown("### Monthly Breakdown")

            tech_m = tech_filtered.copy()
            tech_m["month"] = tech_m["date"].dt.to_period("M").astype(str)
            acts_m = acts_filtered.copy()
            acts_m["month"] = acts_m["date"].dt.to_period("M").astype(str)

            monthly_tech = tech_m.groupby("month").agg(
                runs=("avg_hr", "count"),
                pace=("avg_pace_min_km", "mean"),
                hr=("avg_hr", "mean"),
                cadence=("avg_cadence", "mean"),
                vert_osc=("avg_vertical_oscillation", "mean"),
                gct=("avg_ground_contact_time", "mean"),
                vert_ratio=("avg_vertical_ratio", "mean"),
            ).round(2)

            monthly_acts = acts_m.groupby("month").agg(
                total_km=("distance_km", "sum"),
                avg_vo2max=("vo2max", "mean"),
                avg_load=("training_load", "mean"),
            ).round(2)

            monthly = monthly_tech.join(monthly_acts, how="left")
            monthly.index.name = "Month"
            st.dataframe(monthly, use_container_width=True)

            # Download CSV
            csv_bytes = monthly.reset_index().to_csv(index=False).encode()
            st.download_button("Download monthly CSV", csv_bytes, "garmin_monthly.csv", "text/csv")

            # ── LLM export text ─────────────────────────────────────────────────────
            st.markdown("### LLM Prompt")

            n_runs = len(tech_filtered)
            date_range_str = f"{start} to {end}"
            types_str = ", ".join(selected_types)

            # Build the prompt
            lines = [
                f"I want you to analyse my running performance data and give me honest, specific feedback on my progress and weak points.",
                f"",
                f"## Athlete profile",
                f"Male, 26 years old, 182 cm, 72 kg.",
                f"Activity types analysed: {types_str}.",
                f"Date range: {date_range_str} ({n_runs} runs, walk segments removed from all metrics).",
                f"",
                f"## Overall statistics",
                overall_df.to_string(),
                f"",
                f"## Monthly breakdown (averages per month)",
                monthly.to_string(),
                f"",
                f"## HR zones (Friel method, LTHR={hr_lthr}, max HR={hr_max}, resting={hr_rest})",
                f"Z1 recovery: <{hr_zones[0]} bpm",
                f"Z2 aerobic: {hr_zones[0]}–{hr_zones[1]} bpm",
                f"Z3 tempo: {hr_zones[1]}–{hr_zones[2]} bpm",
                f"Z4 threshold: {hr_zones[2]}–{hr_zones[3]} bpm",
                f"Z5 max: >{hr_zones[3]} bpm",
                f"",
                f"## Running form reference zones (Garmin official, chest HRM)",
                f"Cadence: <158 poor | 158-165 fair | 165-172 moderate | 172-178 good | >178 excellent",
                f"Vertical oscillation: >11 poor | 9.5-11 fair | 8-9.5 moderate | 6.5-8 good | <6.5 excellent",
                f"Ground contact time: >300 poor | 260-300 fair | 230-260 moderate | 200-230 good | <200 excellent",
                f"Vertical ratio: >10.1% poor | 8.7-10.1% fair | 7.4-8.7% moderate | 6.1-7.4% good | <6.1% excellent",
                f"Aerobic decoupling: >10% = aerobically taxed for this effort | 5-10% = borderline | <5% = solid aerobic base",
                f"",
                f"## Questions",
                f"1. Where do I sit in each metric relative to the zones above?",
                f"2. Can you identify any genuine fitness progress or regression over the months?",
                f"3. What are my two or three biggest weaknesses based on this data?",
                f"4. What should I focus on to improve?",
            ]
            llm_text = "\n".join(lines)

            st.text_area("Copy this into ChatGPT / Claude", value=llm_text, height=400)
            st.download_button("Download as .txt", llm_text.encode(), "garmin_llm_prompt.txt", "text/plain")
