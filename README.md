# Biodiversity Monitoring Using AI Vision

A free, open platform that gathers public wildlife and invasive-species records, identifies animals
and plants in photos with deep-learning models, and shows where invasive species concentrate in
protected landscapes, what peer-reviewed papers report about their effect on native species, and how
they have been managed. It is built for researchers, conservation groups and park managers.

**Nothing appears without a paper.** Every finding and management method rests on a peer-reviewed
journal article published in 2016 or later, with verbatim quotes from its abstract, checked against
Crossref and OpenAlex. A species appears only when such a paper backs it, and a species without one
is neither recorded nor shown. [docs/evidence.md](docs/evidence.md) states the rules and where each is
enforced.

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
| GBIF | Preserved museum and herbarium specimens only, because those trace to a collection |
| GRIIS country checklists | Which species are alien and invasive in each country |
| USGS Nonindigenous Aquatic Species database | Curated records of non-native fishes, reptiles, amphibians, molluscs and aquatic plants in the United States |
| Caltech Camera Traps (LILA BC) | Camera-trap images for testing the detector |
| Peer-reviewed journal articles | Findings on effects and management, 31 papers from 2016 to 2026, each with verbatim quotes |

## What the dashboard offers

- **Overview.** The number of invasive records, invasive species and papers, and records by park,
  by year and by species.
- **Hotspots.** A map of each park with squares of a chosen size in kilometres, shaded red by the
  number of invasive records. Filters narrow it to one species, plants or animals, one source and a
  range of years. The panel beside it follows the square you choose or the part of the park you are
  looking at: its records by year and its species, most recorded first, each with a photo and the
  papers on its effect on the local environment.
- **Species.** Only species a paper backs, most recorded first. For each: where and when it was
  recorded, what papers report, and the management methods tried, each with its paper and quotes.
- **Impact.** Three questions in order of certainty: what papers report, whether native richness is
  lower where invaders are dense, and whether the invasive share is changing. The two statistical
  questions answer only when the data meets stated minimums, and the page shows how far each park
  is from them. Where they answer, a scatter plot and a line chart show the data behind them.
- **Alerts, Models, Sources.** First records of invasive species, measured accuracy of each model,
  and where the data came from with its licence and why records were refused.

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
python scripts/verify_citations.py --write               # check every paper and quote, then stamp the date
python -m biodiv.workers.seed_knowledge --prune          # findings and management methods from papers
python -m biodiv.workers.ingest --source inaturalist --max 2000
python -m biodiv.workers.ingest --source gbif            # preserved specimens only
python -m biodiv.workers.ingest --source usgs_nas        # United States parks only
python -m biodiv.workers.enrich_species                  # one licensed photo per species
python -m biodiv.workers.analyse                         # alerts and per-park reports
```

Load the knowledge before the records: the ingest stores an invasive species only when a paper
backs it. [docs/evidence.md](docs/evidence.md) explains how to add a species and its paper.

Each run is incremental and safe to repeat, and each source is queried politely (rate limited,
retried with backoff, and a park whose source does not answer is recorded and retried at the next
run while the other parks carry on). A cap per park and source keeps the free database from
filling, and ingestion stops at 90% of the database budget. iNaturalist is read oldest first, so a
park that reaches its cap holds nothing newer (see [docs/data-quality.md](docs/data-quality.md)).

Species are named by small trained heads on a shared DINOv2 backbone: an invasive-plant classifier
(ten invasives and native look-alikes, with an explicit "unknown") and a camera-trap animal
classifier. Both run on CPU. [docs/models.md](docs/models.md) reports their measured accuracy.

## Scheduled jobs

Once the `DATABASE_URL` secret exists, GitHub Actions keeps the data current:
[ingest](.github/workflows/ingest.yml) every 6 hours and [analyse](.github/workflows/analytics.yml)
four times a day, and [verify-citations](.github/workflows/verify-citations.yml) every Monday. The
[detect](.github/workflows/infer.yml) workflow runs when started by hand, when camera-trap images are
added. Without the secret each workflow reports that it has nothing to do and exits.

## Documentation

| | |
|---|---|
| [docs/architecture.md](docs/architecture.md) | How the pieces fit and what runs where |
| [docs/dashboard.md](docs/dashboard.md) | Pages, configuration, deployment and design decisions |
| [docs/api.md](docs/api.md) | The public REST path, the API, and what the public can access |
| [docs/evidence.md](docs/evidence.md) | The paper-only rules, how papers and quotes are checked, and where each rule is enforced |
| [docs/models.md](docs/models.md) | The detector and classifiers with measured accuracy and limits |
| [docs/impact.md](docs/impact.md) | How impact is analysed and why the statistics often wait for more data |
| [docs/data-quality.md](docs/data-quality.md) | What the data supports and where it falls short |
| [docs/free-tier-gate.md](docs/free-tier-gate.md) | Accounts, secrets and staying inside free limits |
| [paper.md](paper.md) | A paper for readers: the method, the results and the peer-reviewed evidence behind each finding. Its records and analyses are those of 8 November 2026, and its evidence base was last checked on 9 November 2026 |

## Layout

`src/biodiv/` is the Python package (ingestion, inference, analytics, API, workers, knowledge), `web/`
the dashboard, `db/` the SQL migrations and seeds (`db/seeds/knowledge.json` holds the papers),
`scripts/` the data-preparation, checking and clean-up tools, and `notebooks/` the training notebooks.

## Data and licence

The code is Apache-2.0 ([LICENSE](LICENSE)). Data keeps the licence of its source, shown on the
Sources page. Please cite the sources when you reuse results:

- iNaturalist contributors, via iNaturalist.org and GBIF.org.
- Pagad, S., et al. (2018) Introducing the Global Register of Introduced and Invasive Species.
  Scientific Data 5, 170202.
- U.S. Geological Survey. Nonindigenous Aquatic Species Database. Gainesville, Florida.
  The database asks users to contact its team before publishing results that depend on it.
- The papers behind each finding are listed on the dashboard and in `db/seeds/knowledge.json`.
- Park boundaries: OpenStreetMap contributors, ODbL.
