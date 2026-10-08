# Architecture

Everything runs on free tiers with no credit card, so the design avoids anything that must stay
awake: data is gathered and analysed by scheduled jobs, written to a database, and read by a static
dashboard.

```
 iNaturalist ─┐                                       ┌─▶ dashboard (static, Vercel)
 GBIF ────────┼─▶ ingest ─▶ ┌────────────────────┐ ──┤      reads the REST API directly
 GRIIS ───────┘             │ Postgres + PostGIS │   │
 Caltech Camera Traps ─▶ detect ─▶ (Supabase)    │   └─▶ FastAPI (optional, sleeps when idle)
                            │  zones, species,   │         live photo demo, GraphQL
 cited knowledge base ─▶    │  observations,     │
                            │  detections,       │
                  analyse ─▶│  zone_reports      │
                            └────────────────────┘
```

## What runs where

| Part | Where | Always on? | When it runs |
|---|---|---|---|
| Ingest (`workers/ingest.py`) | GitHub Actions | no | every 6 hours, `ingest.yml` |
| Detect (`workers/detect.py`) | GitHub Actions | no | every 6 hours, `infer.yml` |
| Analyse (`workers/analyse.py`) | GitHub Actions | no | four times a day, `analytics.yml` |
| Retention (`workers/retention.py`) | GitHub Actions | no | after every ingest |
| Citation check (`scripts/verify_citations.py`) | GitHub Actions | no | weekly, `verify-citations.yml` |
| Database and public REST API | Supabase | yes | n/a |
| Dashboard | Vercel | yes (static files) | n/a |
| Photo demo and GraphQL | Render | no, sleeps | on request |

Only the database and the static dashboard need to be awake for the dashboard to work, and both
are. The optional API can sleep without anything on the dashboard breaking: its panel explains
itself when the service is unreachable.

## The data path

1. **Which species count as invasive** comes from GRIIS country checklists (`import_griis`). A
   species is invasive for a country only if GRIIS lists it as alien; a species recorded as both
   native and alien (the chital) is left out, because counting it would call a native animal invasive.
2. **Sightings** come from iNaturalist research-grade observations and GBIF specimen records, kept
   only when they name a species, have a usable and unobscured location, and fall inside a
   monitored zone. Each refusal is counted by reason and shown on the Sources page. Mirrors of one
   source inside another (iNaturalist records re-published through GBIF) are excluded so nothing is
   counted twice.
3. **Detections** in camera-trap images come from MegaDetector V6 over an archive (Caltech Camera
   Traps). These are replays of historic images, labelled as such, never presented as live.
4. **Analysis** (`analyse`) writes precomputed per-zone reports, so the dashboard reads results and
   never computes statistics in the browser.
5. **Knowledge** (cited impacts and management options) is loaded from `db/seeds/knowledge.json`.
   Every claim carries a verbatim quote, and `scripts/verify_citations.py` re-checks each quote
   against the live source.

## Security model

The public `anon` role is read-only and is the only credential in the browser. The database, not a
server, enforces that: row-level security and grants, tested in `tests/test_public_surface.py` and
checked against a real PostgREST in CI (`scripts/smoke_rest.py`). Workers write with a service
credential that lives only in GitHub Actions secrets. See [api.md](api.md).

## What is not built or not live yet

- **Nothing is deployed.** The accounts (Supabase, Vercel, optionally Render) have to be created by
  a person; the steps and fallbacks are in [free-tier-gate.md](free-tier-gate.md). Until the
  `DATABASE_URL` secret exists, every scheduled workflow explains itself and exits cleanly.
- **IUCN threat links** wait for an API token, which is human-reviewed. See [iucn.md](iucn.md).
- **The statistical impact layers report "not enough data"** on today's records, by design. See
  [impact.md](impact.md).
- **The animal classifier covers 13 North American species.** It demonstrates the pipeline and
  measures how well a model transfers to unseen cameras; it is not a model of Indian or African
  fauna. See [models.md](models.md).
- **Detection runs on archived images.** There is no live camera feed.
