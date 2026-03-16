"""
FastAPI application — Garmin Data Visualizer backend.

Run from repo root:
    uv run uvicorn api.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.deps import state
from src.loaders import load_activities, load_sleep, load_technique, load_gps


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all data caches once at startup."""
    print("Loading activities and sleep data…")
    state.activities = load_activities()
    state.sleep = load_sleep()

    try:
        state.technique = load_technique()
        print(f"Technique cache loaded: {len(state.technique)} activities")
    except FileNotFoundError:
        state.technique = None
        print("Technique cache not found — run: uv run python -m src.cache")

    try:
        state.gps = load_gps()
        print(f"GPS cache loaded: {len(state.gps):,} points")
    except FileNotFoundError:
        state.gps = None
        print("GPS cache not found — run: uv run python -m src.gps_cache")

    print("Ready.")
    yield


app = FastAPI(title="Garmin Visualizer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
from api.routers import activities, sleep, technique, gps, fit, export, progress

app.include_router(activities.router, prefix="/api")
app.include_router(sleep.router,      prefix="/api")
app.include_router(technique.router,  prefix="/api")
app.include_router(gps.router,        prefix="/api")
app.include_router(fit.router,        prefix="/api")
app.include_router(export.router,     prefix="/api")
app.include_router(progress.router,   prefix="/api")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "activities": len(state.activities),
        "technique": len(state.technique) if state.technique is not None else None,
        "gps_points": len(state.gps) if state.gps is not None else None,
    }


# Serve React build (production)
_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")
