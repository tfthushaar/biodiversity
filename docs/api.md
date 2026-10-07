# API and data access

There are two ways in, by design. The dashboard needs no server of ours, because free hosts sleep
and may want a card.

```
 dashboard (Vercel) ──public anon key──▶ Supabase REST (PostgREST)   always on, free, read-only
        │
        └─ optional "try it" ───────────▶ FastAPI (Render)           sleeps when idle; live demo only
```

## 1. The data path: Supabase REST (what the dashboard uses)

Supabase serves every table and view through a REST API generated from the schema, using the
**public `anon` key**, which is meant to be visible in the browser. So the *database* is the
security boundary: row-level security and grants decide what the whole internet may do. The
dashboard reads precomputed results (`zone_reports`) rather than asking a server to compute.

| Read | Endpoint |
|---|---|
| Zones with headline counts, as GeoJSON for the map | `GET /rpc/zones_geojson` |
| Sightings as GeoJSON points (`p_zone`, `p_kind` = `invasive`/`all`, `p_limit` up to 5000) | `GET /rpc/records_geojson?p_zone=bandipur` |
| Per-zone three-layer report | `GET /zone_reports?select=report,computed_at&zone_id=eq.1` |
| Alerts with zone and species | `GET /alerts?select=*,zones(slug),species(scientific_name)` |
| Cited impact findings | `GET /impact_findings?select=*,species(scientific_name)` |
| Mitigation playbooks and their quotes | `GET /mitigation_playbooks?select=*,species(scientific_name)` |
| Data-source health, licences, why records were refused | `GET /source_health` |
| Model versions and their measured accuracy | `GET /model_versions` |
| Anything else public | `GET /species`, `/invasive_status`, `/zone_invasive_summary`, ... |

### What the public can NOT do

Checked by `tests/test_public_surface.py` (the database rules) and `scripts/smoke_rest.py`
(the live HTTP surface, run in CI against a real PostgREST):

- write, update or delete anything;
- call internal functions (`refresh_rollups`, `ensure_detection_partition`);
- read partitions directly or migration bookkeeping, or see more of PostGIS's coordinate-system
  table than the one definition (WGS84) that geometry serialisation needs (migration 0014);
- **call PostGIS functions.** This was a real hole found by testing the HTTP path: PostGIS puts
  about a thousand functions in `public`, Postgres makes new functions callable by everyone, and
  the REST API publishes them. An unauthenticated request to `/rpc/postgis_full_version` returned
  the server's library versions, and any geometry function (buffers, unions) would have run on
  attacker-chosen input. Migration 0013 denies them by default and allows only the four the
  public functions need. Re-run `select restrict_postgis_functions()` after any PostGIS upgrade.

### Check any deployment

```bash
python scripts/smoke_rest.py https://YOUR-REF.supabase.co/rest/v1 --key YOUR_ANON_KEY
```

Use the **anon** key, never the service-role key. 22 checks; non-zero exit on any failure.

### Run the same stack locally

```bash
docker compose -f docker-compose.dev.yml up -d db
DATABASE_URL=postgresql://postgres:dev@localhost:54329/biodiv python -m biodiv.workers.migrate --seed
docker compose -f docker-compose.dev.yml up -d rest      # http://localhost:3000
python scripts/smoke_rest.py http://localhost:3000
```

## 2. The compute path: FastAPI

Interactive docs at `/docs`. Everything is read-only apart from the two photo endpoints, which
store nothing.

| Endpoint | What it does |
|---|---|
| `GET /health` | Liveness (also used to keep the host warm) |
| `GET /api/v1/models` | Which models this server can run and what each was trained to say |
| `POST /api/v1/infer/animals` | Camera-trap photo in; animals, people, vehicles out, each animal named |
| `POST /api/v1/infer/plants` | Plant photo in; an invasive species, a native look-alike, or `unknown` |
| `GET /api/v1/zones/{slug}/report` | The precomputed zone report |
| `POST /graphql` | Flexible filtering for researchers |

```bash
curl -F "file=@leaf.jpg" https://YOUR-API/api/v1/infer/plants
```
```json
{ "answer": "Senna spectabilis", "probability": 0.91, "threshold": 0.76, "kind": "invasive",
  "alternatives": [{"label": "Senna spectabilis", "probability": 0.91},
                   {"label": "Cassia fistula", "probability": 0.05}, ...],
  "context": {"invasive_in_india": true, "playbooks": 4, "impact_findings": 5},
  "notice": "A decision aid, not an identification. Confirm with a botanist ..." }
```

An answer below the threshold is `"unknown"` (with the leaning still shown as `best_guess`), and
`other_plant` means "none of the listed species". Probabilities are calibrated: about nine in ten
answers given at 0.9 are right. See [models.md](models.md) for the measured error rates.

**Uploads are untrusted.** Only JPEG, PNG and WebP; a size cap (`MAX_UPLOAD_MB`, default 8); a
decompression-bomb guard; a per-client rate limit (`INFER_REQUESTS_PER_MINUTE`, default 10, with
`Retry-After`). Images are analysed in memory and never written or logged. **People are
detected but never cropped or classified.**

### GraphQL

The design report's example query, verbatim in spirit:

```graphql
{ detections(species: "Panthera pardus", since: "2026-07-01T00:00:00Z", minConfidence: 0.9) {
    capturedAt confidence zone species origin } }
```

Also `zones`, `species(search, invasiveOnly)`, `alerts(zone, kind)`, `playbooks(species)`. Filters
are bound parameters, never spliced into SQL (tested with an injection attempt); results are capped
at 500 rows. `origin` says whether a person or the model made the identification.

Supabase additionally serves GraphQL itself (`pg_graphql`, at `/graphql/v1`). That is Supabase's
own feature and has **not** been exercised here; this repository's GraphQL endpoint is the tested one.

## Configuration

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | Postgres connection (Supabase **session pooler** string; the direct host is IPv6-only on the free plan) |
| `MEGADETECTOR_ONNX`, `BACKBONE_ONNX`, `HEADS_DIR` | Where the models are; unset means those endpoints return 503, nothing else breaks |
| `CORS_ORIGINS` | Comma-separated allowed origins (default `*`: the API is public and uses no cookies) |
| `MAX_UPLOAD_MB`, `INFER_REQUESTS_PER_MINUTE` | Upload hygiene |

On Render's free tier (512 MB) the detector plus the species backbone are close to the memory
limit. If the demo is killed for it, the rest of the API is unaffected, because models load on
first use.
