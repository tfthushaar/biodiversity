# API and data access

There are two ways in. The dashboard reads the database's own REST API with a public key, so it
needs no server of ours and works on hosts that sleep. An optional FastAPI service adds photo
analysis and GraphQL.

```
 dashboard (Vercel) ──public key──▶ Supabase REST (PostgREST)   always on, free, read-only
        │
        └─ optional "try it" ─────▶ FastAPI (Render)           sleeps when idle; photo demo and GraphQL
```

## 1. The data path: Supabase REST

Supabase generates a REST API from the database schema. The browser uses its public key (the anon
or publishable key), which is meant to be visible. Row-level security and grants in the database
decide what any visitor may do, so the database is the security boundary. The dashboard reads
precomputed results such as `zone_reports` and does not ask a server to compute.

| Read | Endpoint |
|---|---|
| Parks with headline counts, as GeoJSON for the map | `GET /rpc/zones_geojson` |
| Invasive records grouped into map squares, with species per square (`p_zone`, `p_cell` in degrees from 0.005 to 0.5, optional `p_species`) | `GET /rpc/hotspot_cells?p_zone=everglades&p_cell=0.02` |
| Individual sightings as GeoJSON points (`p_zone`, `p_kind` = `invasive` or `all`, `p_limit` up to 5000) | `GET /rpc/records_geojson?p_zone=bandipur` |
| How full the free database is | `GET /rpc/storage_status` |
| Per-park three-layer report | `GET /zone_reports?select=report,computed_at&zone_id=eq.1` |
| Alerts with park and species | `GET /alerts?select=*,zones(slug),species(scientific_name)` |
| Cited findings | `GET /impact_findings?select=*,species(scientific_name)` |
| Management options and their quotes | `GET /mitigation_playbooks?select=*,species(scientific_name)` |
| Species with their photo, credit and licence | `GET /species?select=scientific_name,photo_url,photo_credit,photo_license,photo_source_url` |
| Data sources, licences and why records were refused | `GET /source_health` |
| Model versions and measured accuracy | `GET /model_versions` |
| Other public tables and views | `GET /species`, `/invasive_status`, `/zone_invasive_summary`, ... |

### What the public can access

`tests/test_public_surface.py` and `tests/test_hosting_differences.py` check these rules in the
database, and `scripts/smoke_rest.py` checks them over HTTP against a running deployment (it runs
in CI against a real PostgREST and can be pointed at the live project).

The public role can:

- read the tables and views the dashboard uses;
- call `zones_geojson`, `records_geojson`, `hotspot_cells` and `storage_status`.

The public role cannot:

- insert, update, delete or truncate anything;
- call internal functions (`refresh_rollups`, `ensure_detection_partition`);
- read partitions directly or the migration bookkeeping table;
- call PostGIS functions or read PostGIS reference tables beyond the single WGS84 row that
  geometry serialisation needs;
- read rows whose `evidence_source` is `iucn` in `threat_links` (see [iucn.md](iucn.md)).

Three properties of hosted Postgres shaped these rules:

1. **PostGIS exposure.** PostGIS installs about a thousand functions into the schema where it
   lives, and Postgres makes new functions callable by everyone. On a plain server with PostGIS in
   `public`, the REST API publishes them: an unauthenticated request to
   `/rpc/postgis_full_version` returned the server's library versions, and geometry functions
   such as buffers and unions would run on caller-chosen input. Migration 0013 removes them from
   the public roles and allows four back (`st_asgeojson`, `st_simplify`, `st_x`, `st_y`). Migration
   0014 limits the coordinate-system table to one row. Re-run `select restrict_postgis_functions()`
   after any PostGIS upgrade. On Supabase, the migration runner installs PostGIS into the
   `extensions` schema, which the REST API does not publish.
2. **Default grants.** Supabase grants every new table, sequence and function in `public` to the
   public roles. Migration 0016 removes write access everywhere and makes new objects private until
   a migration grants them.
3. **Row-level security alone is not enough.** Supabase switches row-level security on for new
   tables, which hides rows, but a granted `truncate` ignores it. The rules above rely on grants
   as well.

### Checking a deployment

```bash
python scripts/smoke_rest.py https://YOUR-REF.supabase.co/rest/v1 --key YOUR_ANON_KEY
```

Use the anon (public) key and never the service-role key. The script runs 23 checks and exits
non-zero on any failure.

### Running the same stack locally

```bash
docker compose -f docker-compose.dev.yml up -d db
DATABASE_URL=postgresql://postgres:dev@localhost:54329/biodiv python -m biodiv.workers.migrate --seed
docker compose -f docker-compose.dev.yml up -d rest      # http://localhost:3000
python scripts/smoke_rest.py http://localhost:3000
```

## 2. The compute path: FastAPI

Interactive documentation is at `/docs`. Every endpoint is read-only except the two photo
endpoints, which store nothing.

| Endpoint | What it does |
|---|---|
| `GET /health` | Liveness check, also used by uptime monitors and the keep-alive workflow. Answers `GET` and `HEAD` |
| `GET /api/v1/models` | Which models this server can run and what each was trained to say |
| `POST /api/v1/infer/animals` | Camera-trap photo in; animals, people and vehicles out, each animal named |
| `POST /api/v1/infer/plants` | Plant photo in; an invasive species, a native look-alike, or `unknown` |
| `GET /api/v1/zones/{slug}/report` | The precomputed park report |
| `POST /graphql` | Flexible filtering for researchers |

```bash
curl -F "file=@leaf.jpg" https://YOUR-API/api/v1/infer/plants
```
```json
{ "answer": "Senna spectabilis", "probability": 0.91, "threshold": 0.76, "kind": "invasive",
  "alternatives": [{"label": "Senna spectabilis", "probability": 0.91},
                   {"label": "Cassia fistula", "probability": 0.05}, ...],
  "context": {"invasive_in_india": true, "playbooks": 4, "impact_findings": 5},
  "notice": "Treat this as a decision aid and confirm with a botanist or ranger before acting." }
```

An answer below the threshold is `"unknown"`, with the leaning still shown as `best_guess`.
`other_plant` means none of the listed species. Probabilities are calibrated: about nine in ten
answers given at 0.9 are right. [models.md](models.md) lists the measured error rates.

**Uploads.** The endpoints accept JPEG, PNG and WebP only, up to `MAX_UPLOAD_MB` (default 8),
guard against decompression bombs, and rate-limit each client (`INFER_REQUESTS_PER_MINUTE`,
default 10, with `Retry-After`). Images are analysed in memory and are not written or logged.
People in images are detected and left uncropped and unclassified.

### GraphQL

```graphql
{ detections(species: "Panthera pardus", since: "2026-07-01T00:00:00Z", minConfidence: 0.9) {
    capturedAt confidence zone species origin } }
```

Also `zones`, `species(search, invasiveOnly)`, `alerts(zone, kind)` and `playbooks(species)`.
Filters are bound parameters (tested with an injection attempt) and results are capped at 500
rows. `origin` tells whether a person or the model made the identification.

Supabase also serves GraphQL itself through `pg_graphql` at `/graphql/v1`. We have not exercised
that endpoint; this repository's GraphQL endpoint is the tested one.

## Configuration

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | Postgres connection. On Supabase use the session pooler string, because the direct host is IPv6-only on the free plan |
| `MEGADETECTOR_ONNX`, `BACKBONE_ONNX`, `HEADS_DIR` | Where the models are. When unset, the matching endpoints return 503 and nothing else is affected |
| `CORS_ORIGINS` | Comma-separated allowed origins (default `*`; the API is public and uses no cookies) |
| `MAX_UPLOAD_MB`, `INFER_REQUESTS_PER_MINUTE` | Upload limits |

On Render's free tier (512 MB) the detector and the species backbone together come close to the
memory limit. If the demo is stopped for memory, the rest of the API keeps running, because models
load on first use.
