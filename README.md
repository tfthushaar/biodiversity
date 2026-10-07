# Biodiversity Monitoring Using AI Vision

A software-only platform that ingests public wildlife imagery and biodiversity records, detects
species with deep-learning vision, and shows **where invasive species are established, how they
are spreading, which native species they threaten, and what the published evidence says to do
about it**, on a dashboard for researchers, NGOs and policymakers.

> Project by K N Thushaar Rangan, Yashas S, Amogh P A and G Ritzia.

## Everything is free, with no credit card

| Part | Host |
|---|---|
| Dashboard (React 18 + TypeScript) | Vercel Hobby |
| Database (Postgres + PostGIS) with REST and GraphQL | Supabase free |
| Custom API (FastAPI), optional | Render free |
| Ingestion, inference, analytics | GitHub Actions cron (free on public repos) |
| Model training | Kaggle free GPU |
| Model weights | Hugging Face Hub |

See [docs/free-tier-gate.md](docs/free-tier-gate.md) for the signup checklist and fallbacks.

## How it differs from the original report

Real-time GPU streaming does not exist at zero cost, so ingestion and inference run as scheduled
batch workers (near-real-time, not streaming). TimescaleDB is replaced by native Postgres
partitioning (`pg_partman`) because Supabase deprecates the extension. Poaching detection is out
of scope; the analytical focus is invasive species and their ecosystem impact.

## Quick start

```bash
# Python backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest && ruff check .
uvicorn biodiv.api.main:app --reload                  # http://localhost:8000/docs

# Dashboard
cd web && npm install && npm run dev
```

Copy `.env.example` to `.env` for local configuration. Never commit real keys.

## Loading data

```bash
export DATABASE_URL=postgresql://...                     # a Postgres with PostGIS
python -m biodiv.workers.migrate --seed                  # schema + monitored zones
python -m biodiv.workers.import_griis --resource griis-india      # which species are invasive
python -m biodiv.workers.import_griis --resource griis_tanzania
python -m biodiv.workers.ingest --source inaturalist --max 2000   # community observations
python -m biodiv.workers.ingest --source gbif                     # museum/herbarium specimens
python -m biodiv.workers.detect --model data/models/MDV6-mit-yolov9-c.onnx   # find animals in images
```

The detector is MegaDetector V6 (MIT) converted to ONNX and run on CPU. How it was made, how it
was verified against the reference implementation, and how accurate it is, including the
mistakes made while measuring that: [docs/models.md](docs/models.md).

Each run is incremental and idempotent, and polite to the source APIs (rate-limited, retried
with backoff). Read [docs/data-quality.md](docs/data-quality.md) before interpreting any numbers:
it records what the data can and cannot support.

## Layout

`src/biodiv/` holds the Python package (ingestion, inference, analytics, api, workers), `web/` the
dashboard, `db/` the SQL migrations and seeds, `notebooks/` the training notebooks.

## Licence

Apache-2.0. See [LICENSE](LICENSE). Third-party data keeps its own licence; the dashboard's
Sources view shows each one.
