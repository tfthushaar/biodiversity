# Free-tier gate

**Rule: no credit card, anywhere.** Each service below must be signed up for *without* entering
a card before any code depends on it. If a signup asks for a card, stop and tell the team: the
plan has a fallback for every service.

**Honesty note.** The "documented" column reflects what public docs and pricing pages said when
the plan was written (October 2026). It is *not* a signup test. Fill in the last two columns when
you actually create each account. That is the gate.

| Service | Used for | Documented as card-free? | Created (date) | Card asked? |
|---|---|---|---|---|
| GitHub (public repo) | git, CI/CD, scheduled workers | Yes. Free Actions minutes are unlimited on public repos | | |
| Supabase | Postgres + PostGIS, REST, GraphQL, storage | Yes. Free plan, no card | | |
| Vercel (Hobby) | dashboard hosting | Yes. Non-commercial use | | |
| Render (free web service) | optional FastAPI endpoints | **Conflicting sources. Verify** | | |
| Kaggle | free GPU for model training | Yes (phone verification, no card) | | |
| Hugging Face (Hub only) | model weight hosting | Yes for Hub. **Docker/Gradio Spaces are paid since July 2026. Do not use** | | |
| IUCN Red List API | threat links (code 8.1.2) | Yes. Free token, **human-reviewed, apply early** | | |
| eBird API | bird cross-checks | Yes. Instant key | | |
| iNaturalist / GBIF / GRIIS | occurrences + invasive status | Yes. Reads need no key | n/a | n/a |

## Fallbacks if a signup asks for a card

| If this asks for a card | Fallback |
|---|---|
| Render | Drop it. The dashboard uses Supabase's built-in REST and GraphQL; analytics become SQL views and RPC functions. |
| Vercel | Cloudflare Pages or GitHub Pages (both card-free, static). |
| Supabase | Local Postgres in Docker for development; neon.tech free tier as an alternative host. |
| Kaggle | Google Colab free tier. |

## GitHub Actions secrets to add (Settings > Secrets and variables > Actions)

| Secret | Value | Used by |
|---|---|---|
| `SUPABASE_URL` | Project URL | keep-alive, workers |
| `SUPABASE_ANON_KEY` | anon public key | keep-alive |
| `SUPABASE_SERVICE_ROLE_KEY` | service role key (**secret**) | workers (writes) |
| `DATABASE_URL` | Postgres connection string | migrations |
| `API_PUBLIC_URL` | Render service URL | Render keep-alive |
| `IUCN_API_TOKEN` | once approved | workers |
| `EBIRD_API_KEY` | key | workers |

The keep-alive workflow skips cleanly while these are unset, so nothing fails in the meantime.

## Applying the database schema to Supabase

```bash
# DATABASE_URL = Supabase "Session pooler" connection string (IPv4-friendly).
# The direct connection is IPv6-only on the free plan; verify this against your project.
python -m biodiv.workers.migrate --seed
```

Migrations are applied once each and checksummed: editing an already-applied migration is
refused. Add a new numbered file instead. Row-level security allows the public `anon` key to
read only; all writes use the service role from workers.

## After deploying: check the public surface

```bash
python scripts/smoke_rest.py https://YOUR-REF.supabase.co/rest/v1 --key YOUR_ANON_KEY
```

It confirms the dashboard's data is readable and that writes, internal functions and PostGIS
functions are refused. Use the **anon** key. The service-role key must never leave the workers'
secrets. See [api.md](api.md).

## Staying inside the free database (500 MB)

Supabase's free plan puts a project into read-only mode when the database reaches its limit, which
would silently stop every later run. So the limit is watched, not hoped about:

- `storage_status()` (migration 0015) reports the database size against the 500 MB budget. The
  dashboard's Sources page shows it as a meter.
- `python -m biodiv.workers.ingest` refuses to add records once the database is 90% full and exits
  with status 3, so the scheduled run turns red instead of quietly doing nothing.
- `python -m biodiv.workers.retention` runs after every ingest. It removes old ingestion-run logs
  (keeping each source's newest 50, and anything under 90 days old) and prints a warning at 80% and
  an error at 90%.
- It never deletes observations, detections or findings. Those are the product. If they ever fill
  the budget the answer is a human decision: narrower zones, or a paid plan.

The database size comes from `pg_database_size`. Supabase's own dashboard shows its own figure, which
may differ slightly, so the 10% margin is deliberate. Compare the two on a real project before
relying on it.

Only detection boxes and source URLs are stored, never images, so the original plan's thumbnail
budget does not apply. Today's database, with about 2,400 observations, is under 30 MB.
