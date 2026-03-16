# Garmin Data Visualizer

Personal dashboard for analyzing Garmin running data from a GDPR export. Built with FastAPI and React.

## Project structure

```
.
├── api/                        FastAPI backend
│   ├── main.py                 App factory, startup data loading, static file serving
│   ├── deps.py                 Shared app state (DataFrames loaded once at startup)
│   ├── utils.py                JSON serialization helpers, OLS trendline
│   └── routers/
│       ├── activities.py       HR vs Pace, HR vs Sleep, Training Load endpoints
│       ├── sleep.py            Sleep trends with period navigation
│       ├── technique.py        Running technique, correlations, drill-down scatter
│       ├── gps.py              GPS heatmap points
│       ├── fit.py              Per-activity FIT file detail and aerobic decoupling
│       ├── progress.py         VO2max, pace-at-HR, decoupling trend, Z2 tracker
│       └── export.py           Overall stats, monthly CSV, LLM prompt
│
├── src/                        Python data layer (no web framework dependency)
│   ├── loaders.py              Load activities, sleep, FIT files, build caches
│   ├── cache.py                CLI: build technique cache
│   ├── gps_cache.py            CLI: build GPS cache
│   ├── fit_index.py            CLI: match FIT files to activity IDs
│   └── add_activity.py         CLI: add a new FIT file to the dataset
│
├── frontend/                   React frontend
│   ├── src/
│   │   ├── App.tsx             Router setup
│   │   ├── store/filters.ts    Zustand global filter state (date range, HR zones)
│   │   ├── lib/api.ts          Axios API client
│   │   ├── lib/types.ts        TypeScript interfaces
│   │   ├── components/         Layout, Sidebar, Chart wrapper, LoadingError
│   │   └── pages/              One component per section (9 total)
│   ├── package.json
│   └── vite.config.ts          Dev proxy /api to localhost:8000
│
├── data/                       Gitignored — your personal Garmin data
│   ├── raw/                    GDPR export files
│   └── cache/                  Precomputed parquets (technique, GPS, fit_index)
│
├── Dockerfile                  Multi-stage build (Node then Python)
├── docker-compose.yml          Local Docker with data volume mount
└── pyproject.toml              Python dependencies (FastAPI, pandas, garmin-fit-sdk...)
```

**How a request flows:** browser → Vite dev server (port 5173) → proxied to FastAPI (port 8000) → `src/loaders.py` reads from `data/` → JSON response → React renders with Plotly and Leaflet.

In production (Docker or Cloud Run) the proxy disappears — FastAPI serves the built React files directly from `frontend/dist/`.

## Setup

```bash
uv sync
cd frontend && npm install
```

## Data

Place your Garmin GDPR export inside `data/raw/` so the structure looks like:

```
data/raw/
  DI_CONNECT/
    DI-Connect-Fitness/     *_summarizedActivities.json
    DI-Connect-Wellness/    *_sleepData.json
    DI-Connect-Uploaded-Files/  **/*.fit
```

## Build caches (first time)

Run these once before launching the app:

```bash
uv run python -m src.fit_index   # match FIT files to activity IDs
uv run python -m src.cache       # compute running technique stats
uv run python -m src.gps_cache   # extract GPS points for heatmap
```

## Launch (local dev)

Two terminals:

```bash
# Terminal 1 — backend
uv run uvicorn api.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

Then open `http://localhost:5173`.

## Adding a new activity

When you have a new FIT file (e.g. downloaded from Garmin Connect):

```bash
uv run python -m src.add_activity ~/Downloads/12345678_ACTIVITY.fit
```

This will:
1. Copy the FIT file into the correct data folder
2. Extract all stats (pace, HR, cadence, vertical oscillation, etc.)
3. Inject the activity into `summarizedActivities.json`
4. Rebuild all caches automatically

Then restart the backend to pick up the new data.

## Docker (local)

```bash
docker compose up
```

Open `http://localhost:8000`. The `data/` folder is mounted as a volume so nothing is baked into the image.

## Deploy to Google Cloud Run

The app is a single container — no microservices needed.

**1. Build and push the image**

The data is baked into the image at build time. The image is private so that is fine for personal health data.

```bash
# Replace YOUR_PROJECT with your GCP project ID
docker build -t gcr.io/YOUR_PROJECT/garmin-visualizer .
docker push gcr.io/YOUR_PROJECT/garmin-visualizer
```

**2. Deploy**

```bash
gcloud run deploy garmin-visualizer \
  --image gcr.io/YOUR_PROJECT/garmin-visualizer \
  --platform managed \
  --region europe-west1 \
  --port 8000 \
  --memory 1Gi \
  --no-allow-unauthenticated
```

`--no-allow-unauthenticated` means only you can access it via `gcloud auth print-identity-token`. After adding a new activity, rebuild and redeploy the image.

## Production build (no Docker)

```bash
cd frontend && npm run build
uv run uvicorn api.main:app --port 8000
```

FastAPI serves the built frontend at `http://localhost:8000`.
