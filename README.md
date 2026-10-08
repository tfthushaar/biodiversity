# Biodiversity Monitoring Using AI Vision

A free, open platform that gathers public wildlife and invasive-species records, identifies animals
and plants in photos with deep-learning models, and shows where invasive species concentrate in
protected landscapes, what published research reports about their effect on native species, and how
they have been managed. It is built for researchers, conservation groups and park managers.

Project by K N Thushaar Rangan, Yashas S, Amogh P A and G Ritzia.

## Live

| | |
|---|---|
| Dashboard | <https://biodiversity-ecru.vercel.app> |
| API (photo analysis, GraphQL), with interactive documentation | <https://biodiversity-4xvo.onrender.com/docs> |

The data refreshes every few hours. The API runs on a free host that sleeps when idle, so a request
after a quiet spell can take about a minute. The dashboard works without it.

## What it covers

Six national parks on three continents:

| Park | Country |
|---|---|
| Bandipur, Nagarahole, Mudumalai | India |
| Serengeti | Tanzania |
| Everglades, Great Smoky Mountains | United States |

Sources of records and status:

| Source | Used for |
|---|---|
| iNaturalist (research grade) | Community observations of plants and animals |
| GBIF | Museum and herbarium specimens |
| GRIIS country checklists | Which species are alien and invasive in each country |
| USGS Nonindigenous Aquatic Species database | Curated records of non-native fishes, reptiles, amphibians, molluscs and aquatic plants in the United States |
| Caltech Camera Traps (LILA BC) | Camera-trap images for testing the detector |
| Published literature and species profiles | Cited findings on effects and management, each with verbatim quotes |

## What the dashboard offers

- **Hotspots.** A map of each park with squares shaded red by the number of invasive records.
  Selecting a square lists the species there, each with a photo, the number of records, and the
  cited research on its effect on the local environment.
- **Species.** One page per species: where it is recorded, what research reports, and the
  management options that have been tried.
- **Impact.** Three questions in order of certainty: what cited sources report, whether native
  richness is lower where invaders are dense, and whether the invasive share is changing. The two
  statistical questions answer only when the data meets stated minimums, and the page shows how far
  each park is from them.
- **Alerts, Models, Sources.** First records of invasive species, measured accuracy of each model,
  and where the data came from with its licence.

## Hosting and cost

Everything runs on free tiers that need no credit card.

| Part | Host |
|---|---|
| Dashboard (React 18, TypeScript) | Vercel Hobby |
| Database (Postgres with PostGIS), REST API | Supabase free |
| Photo analysis and GraphQL API (FastAPI), optional | Render free |
| Data collection, inference and analysis | GitHub Actions on a public repository |
| Model training | Kaggle free GPU |

[docs/free-tier-gate.md](docs/free-tier-gate.md) has the signup checklist, the secrets to set, and
the fallback for each service.

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

Copy `.env.example` to `.env` for local settings. Keep real keys out of version control.

## Loading data

```bash
export DATABASE_URL=postgresql://...                     # a Postgres with PostGIS
python -m biodiv.workers.migrate --seed                  # schema and the six parks
python -m biodiv.workers.import_griis --resource griis-india
python -m biodiv.workers.import_griis --resource griis_tanzania
python -m biodiv.workers.import_griis --resource griis-contiguous-united-states-of-america
python -m biodiv.workers.ingest --source inaturalist --max 2000
python -m biodiv.workers.ingest --source gbif
python -m biodiv.workers.ingest --source usgs_nas        # United States parks only
python -m biodiv.workers.seed_knowledge                  # cited findings and management options
python -m biodiv.workers.enrich_species                  # one licensed photo per species
python -m biodiv.workers.analyse                         # alerts and per-park reports
```

Each run is incremental and safe to repeat, and each source is queried politely (rate limited,
retried with backoff). A cap per park and source keeps the free database from filling, and
ingestion stops at 90% of the database budget.

Species are named by small trained heads on a shared DINOv2 backbone: an invasive-plant classifier
(ten invasives and native look-alikes, with an explicit "unknown") and a camera-trap animal
classifier. Both run on CPU. [docs/models.md](docs/models.md) reports their measured accuracy.

## Scheduled jobs

Once the `DATABASE_URL` secret exists, GitHub Actions keeps the data current:
[ingest](.github/workflows/ingest.yml) every 6 hours, then [detect](.github/workflows/infer.yml),
then [analyse](.github/workflows/analytics.yml). Without the secret each workflow reports that it
has nothing to do and exits.

## Documentation

| | |
|---|---|
| [docs/architecture.md](docs/architecture.md) | How the pieces fit and what runs where |
| [docs/dashboard.md](docs/dashboard.md) | Pages, configuration, deployment and design decisions |
| [docs/api.md](docs/api.md) | The public REST path, the API, and what the public can access |
| [docs/models.md](docs/models.md) | The detector and classifiers with measured accuracy and limits |
| [docs/impact.md](docs/impact.md) | How impact is analysed and why the statistics often wait for more data |
| [docs/data-quality.md](docs/data-quality.md) | What the data supports and where it falls short |
| [docs/free-tier-gate.md](docs/free-tier-gate.md) | Accounts, secrets and staying inside free limits |
| [docs/iucn.md](docs/iucn.md) | IUCN Red List data: terms of use and current status |
| [paper.md](paper.md) | A paper describing the method and results |

## Layout

`src/biodiv/` is the Python package (ingestion, inference, analytics, API, workers), `web/` the
dashboard, `db/` the SQL migrations and seeds, `scripts/` the data-preparation and checking tools,
and `notebooks/` the training notebooks.

## Data and licence

The code is Apache-2.0 ([LICENSE](LICENSE)). Data keeps the licence of its source, shown on the
Sources page. Please cite the sources when you reuse results:

- iNaturalist contributors, via iNaturalist.org and GBIF.org.
- Pagad, S., et al. (2018) Introducing the Global Register of Introduced and Invasive Species.
  Scientific Data 5, 170202.
- U.S. Geological Survey. Nonindigenous Aquatic Species Database. Gainesville, Florida.
  The database asks users to contact its team before publishing results that depend on it.
- Park boundaries: OpenStreetMap contributors, ODbL.
