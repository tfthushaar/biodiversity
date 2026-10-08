# Biodiversity Monitoring Using AI Vision

A software-only platform that ingests public wildlife imagery and biodiversity records, detects
species with deep-learning vision, and shows **where invasive species are established, how they
are spreading, which native species they threaten, and what the published evidence says to do
about it**, on a dashboard for researchers, NGOs and policymakers.

> Project by K N Thushaar Rangan, Yashas S, Amogh P A and G Ritzia.

## Live

| | |
|---|---|
| Dashboard | <https://biodiversity-ecru.vercel.app> |
| API (photo analysis, GraphQL), with interactive docs | <https://biodiversity-4xvo.onrender.com/docs> |

The data refreshes itself every few hours. The API runs on a free host that sleeps when idle, so a
request after a quiet spell can take about a minute; the dashboard does not depend on it.

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

## Quick start

```bash
# Python backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest && ruff check .
uvicorn biodiv.api.main:app --reload                  # http://localhost:8000/docs

# Dashboard (reads the REST API on :3000; see docs/dashboard.md)
cd web && npm install && npm run dev
npm test && npm run build
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
python -m biodiv.workers.seed_knowledge                           # cited impacts and mitigation
python -m biodiv.workers.analyse                                  # alerts and per-zone report
```

Species are named by small trained heads on a shared DINOv2 backbone: an invasive-plant classifier
(10 invasives plus native look-alikes, with an explicit "unknown") and a camera-trap animal
classifier. Both run on CPU, and both come with honest, reproducible measurements of how often
they are wrong; see the classifier section of [docs/models.md](docs/models.md).

How the data is served (a read-only public REST path with no server of ours, plus a small API for
the live photo demo and GraphQL), and exactly what the public can and cannot do, is in
[docs/api.md](docs/api.md). Run `python scripts/smoke_rest.py <url>` against any deployment.

What invasive species do to a zone is reported in three layers of decreasing certainty (cited
findings, co-occurrence, trend). The statistical ones decline to answer when the data is too thin,
which today it is; the cited knowledge base (impacts and management, every claim backed by a
verbatim quote that a script re-checks against the live source) is described in
[docs/impact.md](docs/impact.md).

The detector is MegaDetector V6 (MIT) converted to ONNX and run on CPU. How it was made, how it
was verified against the reference implementation, and how accurate it is, including the
mistakes made while measuring that: [docs/models.md](docs/models.md).

Each run is incremental and idempotent, and polite to the source APIs (rate-limited, retried
with backoff). Read [docs/data-quality.md](docs/data-quality.md) before interpreting any numbers:
it records what the data can and cannot support.

## Scheduled jobs

Once the `DATABASE_URL` secret exists, GitHub Actions keeps the data fresh on its own:
[ingest](.github/workflows/ingest.yml) every 6 hours, then [detect](.github/workflows/infer.yml),
then [analyse](.github/workflows/analytics.yml). Ingestion stops itself before the free database
fills (see [docs/free-tier-gate.md](docs/free-tier-gate.md)). Until the secret exists each
workflow explains itself and exits cleanly.

## Documentation

| | |
|---|---|
| [docs/architecture.md](docs/architecture.md) | How the pieces fit, what runs where, what is not built yet |
| [docs/free-tier-gate.md](docs/free-tier-gate.md) | Account checklist, secrets, staying inside free limits |
| [docs/dashboard.md](docs/dashboard.md) | The pages, configuration, deploying, design decisions |
| [docs/api.md](docs/api.md) | The public REST path, the API, and what the public cannot do |
| [docs/models.md](docs/models.md) | The detector and classifiers, with measured accuracy and caveats |
| [docs/impact.md](docs/impact.md) | How invasive-species impact is analysed and why it often says "not enough data" |
| [docs/data-quality.md](docs/data-quality.md) | What the data can and cannot support |
| [docs/iucn.md](docs/iucn.md) | The IUCN threat link, waiting on an API token |

## Layout

`src/biodiv/` holds the Python package (ingestion, inference, analytics, api, workers), `web/` the
dashboard, `db/` the SQL migrations and seeds, `notebooks/` the training notebooks.

## Licence

Apache-2.0. See [LICENSE](LICENSE). Third-party data keeps its own licence; the dashboard's
Sources view shows each one.
