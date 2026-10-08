# Architecture

The platform runs on free tiers without a credit card. Nothing in the design has to stay awake:
scheduled jobs collect and analyse the data, write it to a database, and a static dashboard reads
it.

```
 iNaturalist ──┐                                         ┌─▶ dashboard (static, Vercel)
 GBIF ─────────┤                                         │      reads the REST API directly
 USGS NAS ─────┼─▶ ingest ─▶ ┌───────────────────────┐ ──┤
 GRIIS ────────┘             │  Postgres + PostGIS   │   └─▶ FastAPI (optional, sleeps when idle)
 Caltech Camera Traps ─▶ detect ─▶ │  (Supabase)       │         photo demo, GraphQL
 cited knowledge base ─▶     │  parks, species,      │
 iNaturalist taxon photos ─▶ │  observations,        │
                  analyse ─▶ │  detections, reports  │
                             └───────────────────────┘
```

## What runs where

| Part | Where | Always on | When it runs |
|---|---|---|---|
| Ingest (`workers/ingest.py`) | GitHub Actions | no | every 6 hours, `ingest.yml` |
| Detect (`workers/detect.py`) | GitHub Actions | no | every 6 hours, `infer.yml` |
| Analyse (`workers/analyse.py`) | GitHub Actions | no | four times a day, `analytics.yml` |
| Retention (`workers/retention.py`) | GitHub Actions | no | after every ingest |
| Citation check (`scripts/verify_citations.py`) | GitHub Actions | no | weekly, `verify-citations.yml` |
| Database and public REST API | Supabase | yes | |
| Dashboard | Vercel | yes (static files) | |
| Photo demo and GraphQL | Render | sleeps when idle | on request |

The dashboard depends only on the database and the static host, and both stay up. The optional API
can sleep without affecting it: the photo panel reports when the service is unreachable.

## Parks

Six national parks, with boundaries from OpenStreetMap (`scripts/build_zone_seed.py`):

| Park | Country | Why |
|---|---|---|
| Bandipur, Nagarahole, Mudumalai | India | Contiguous Western Ghats landscape with documented *Lantana* and *Senna* invasions |
| Serengeti | Tanzania | Savanna comparison; wildlife photography rarely records introduced plants |
| Everglades | United States | Dense records and well-studied invasions (Burmese python, melaleuca, climbing fern) |
| Great Smoky Mountains | United States | Temperate forest with kudzu, stiltgrass and non-native trout |

## The data path

1. **Invasive status** comes from GRIIS country checklists (`import_griis`). A species counts as
   invasive in a country when GRIIS lists it as alien and invasive there. A species recorded as
   both native and alien (the chital in India) is left out of the invasive counts.
2. **Sightings** come from three sources. iNaturalist research-grade observations and GBIF specimen
   records are kept when they name a species, carry a full date and a position accurate to 2 km,
   fall inside a park boundary, and are not captive or deliberately obscured. The USGS
   Nonindigenous Aquatic Species database adds curated records of non-native aquatic species in
   the two US parks, each with a source type and a coordinate accuracy class. Failed introductions,
   approximate and centroid positions, and records without a full date are set aside. Each refusal
   is counted by reason and shown on the Sources page. iNaturalist records that GBIF republishes are
   excluded so nothing is counted twice.
3. **Detections** in camera-trap images come from MegaDetector V6 run over an archive (Caltech
   Camera Traps). They are archived images and are labelled as replays.
4. **Analysis** (`analyse`) writes precomputed reports for each park, so the dashboard reads
   results and computes no statistics in the browser.
5. **Knowledge** (cited findings and management options) loads from `db/seeds/knowledge.json`.
   Every claim carries verbatim quotes, and `scripts/verify_citations.py` re-checks each quote
   against the live source.
6. **Photos** (`enrich_species`) attach one licensed photo to each recorded invasive species, with
   the owner's credit and a link back to the photo page.

## Hotspots

`hotspot_cells` (migration 0018) groups a park's invasive records into square cells of a chosen
size and returns one row per occupied cell with its species. The server does the grouping so the
browser downloads a few hundred rows instead of thousands of records. The dashboard shades each
cell by its count and opens a card for each species when a cell is selected.

## Running against a remote database

The scheduled jobs run on GitHub's runners in the United States and the database is in Asia, so
each round trip costs about 0.2 s. That barely affects the small incremental runs. It slows the
first load, so ingestion is built to be interrupted and to use few round trips:

- the iNaturalist cursor is saved after every batch, so a cut-off run resumes where it stopped;
- a batch's duplicates and park membership are found with one query each, not one per record;
- a species seen many times in a run is looked up once;
- `--max-minutes` ends a run cleanly before the workflow's own limit, and the next run continues.
  GBIF's cursor is a date meaning "everything up to here", so it is recorded only when a run reads
  to the end;
- `--max-stored-per-zone` caps each source in each park, and ingestion stops at 90% of the free
  database budget.

## Security model

The public `anon` role is read-only and is the only credential in the browser. The database
enforces that through row-level security and grants, tested in `tests/test_public_surface.py` and
`tests/test_hosting_differences.py` and checked against a live REST API by `scripts/smoke_rest.py`.
Workers write with a service credential held in GitHub Actions secrets. [api.md](api.md) lists
what the public can and cannot do.

## Current limits

- The statistical impact layers report that more data is needed in most parks. [impact.md](impact.md)
  gives the thresholds.
- IUCN Red List threat links are not imported yet. When they are, the database keeps those rows
  hidden from the public API, because IUCN's terms prohibit redistribution without written
  permission. See [iucn.md](iucn.md).
- The animal classifier covers 13 North American species. It shows how a classifier transfers to
  unseen cameras and does not cover Indian or African fauna. See [models.md](models.md).
- Detection runs on archived images. There is no live camera feed.
