# Free-tier checklist

The project runs without a credit card. Each service below should be signed up for without
entering one before anything depends on it. If a signup asks for a card, use the fallback in the
second table.

The "documented" column records what each service's public documentation said in October 2026.
Fill in the last two columns when you create each account.

| Service | Used for | Documented as card-free | Created | Card asked |
|---|---|---|---|---|
| GitHub (public repository) | Git, CI, scheduled jobs. Actions minutes are unlimited on public repositories | Yes | | |
| Supabase | Postgres with PostGIS, REST API | Yes, free plan | | |
| Vercel (Hobby) | Dashboard hosting, for non-commercial use | Yes | | |
| Render (free web service) | Optional FastAPI service | Sources differ, so check at signup | | |
| Kaggle | Free GPU for model training | Yes (phone verification) | | |
| Hugging Face (Hub only) | Model weights. Docker and Gradio Spaces became paid in July 2026 and are not used | Yes | | |
| IUCN Red List API | Threat links (code 8.1.2). The token is reviewed by a person, so apply early | Yes, free token | | |
| iNaturalist, GBIF, GRIIS, USGS NAS | Occurrences and invasive status. Reads need no key | Yes | n/a | n/a |

## Fallbacks

| If this asks for a card | Use |
|---|---|
| Render | Drop it. The dashboard reads Supabase's REST API directly, so only the photo demo and GraphQL are lost |
| Vercel | Cloudflare Pages or GitHub Pages, both card-free and static |
| Supabase | Local Postgres in Docker for development, or Neon's free tier as a host |
| Kaggle | Google Colab's free tier |

## GitHub Actions secrets

Set these under Settings, Secrets and variables, Actions, as **repository secrets**. No workflow
declares an environment, so environment secrets would not reach them.

| Secret | Value | Used by |
|---|---|---|
| `DATABASE_URL` | Supabase session-pooler connection string | ingest, detect, analyse, retention |
| `SUPABASE_URL` | `https://REF.supabase.co` | keep-alive |
| `SUPABASE_ANON_KEY` | The anon or publishable key | keep-alive |
| `API_PUBLIC_URL` | The Render service address. Optional when an uptime monitor already pings it | keep-alive |

Each scheduled workflow reports that it has nothing to do and exits when its secrets are missing.
URL-encode special characters in the database password. Letters and digits avoid the question.

## Applying the schema to Supabase

```bash
# DATABASE_URL is the session-pooler string. The direct host is IPv6-only on the free plan.
python -m biodiv.workers.migrate --seed
```

Each migration is applied once and checksummed, so editing an applied migration is refused. Add a
new numbered file instead. The runner applies each pending migration in its own transaction. A
migration that alters a busy table such as `species` needs an exclusive lock, so run it while no
long import is running, and set a lock timeout (`PGOPTIONS="-c lock_timeout=4000"`) so a busy
moment fails the attempt and does not stall the live site.

### Where Supabase differs from plain Postgres

Both differences surfaced when the migrations first ran on a Supabase project, and both are
handled.

- **PostGIS lives in the `extensions` schema.** The migration runner installs it there when that
  schema exists. In `public`, its tables belong to a Supabase-internal role that the `postgres`
  user cannot alter, and the REST API would publish about a thousand of its functions. The
  table-level steps of migrations 0013 and 0014 run only where PostGIS is in `public`.
- **New objects are public by default.** Supabase grants every new table, sequence and function in
  `public` to the public roles. Migration 0016 removes write access everywhere and makes new
  objects private until a migration grants them. Without it, the migration bookkeeping table kept
  insert, update, delete and truncate for the public role.

If you applied migration 0013 or 0014 to a local database before this was handled, the runner
reports that they changed. Rebuild the local database; it holds nothing that cannot be ingested
again.

## Staying inside the free database (500 MB)

Supabase's free plan puts a project into read-only mode when the database reaches its limit, which
would stop every later run. The limit is monitored:

- `storage_status()` (migration 0015) reports the database size against the 500 MB budget, and the
  Sources page shows it as a meter.
- `python -m biodiv.workers.ingest` refuses to add records once the database is 90% full and exits
  with status 3, so the scheduled run turns red.
- `--max-stored-per-zone` caps each source in each park, so one busy park cannot fill the budget.
- `python -m biodiv.workers.retention` runs after every ingest. It removes old ingestion-run logs
  (keeping each source's newest 50 and anything under 90 days old), warns at 80% and fails at 90%.
- It never deletes observations, detections or findings. If those ever fill the budget, narrower
  parks or a paid plan are the options.

The database size comes from `pg_database_size`. Supabase's dashboard shows its own figure, which
may differ slightly, so the 10% margin is deliberate. Only detection boxes and source URLs are
stored, never images. With about 4,000 observations the database was under 35 MB.

## Keeping the services awake

Supabase pauses a project after about a week of inactivity, and Render stops a free service after
15 minutes without requests. The keep-alive workflow reads a Supabase table daily and warms the API
during waking hours. An external uptime monitor pointed at `/health` every few minutes also keeps
the API up. The endpoint answers `HEAD` as well as `GET`, which is what most monitors send. One
free Render service running all month uses about 744 of the 750 free instance hours, which leaves
no room for a second free service.

GitHub disables scheduled workflows in a repository with no activity for 60 days, and any commit
re-enables them. Check the Actions tab before a demonstration.

## After deploying

```bash
python scripts/smoke_rest.py https://YOUR-REF.supabase.co/rest/v1 --key YOUR_ANON_KEY
```

The script confirms that the dashboard's data is readable and that writes, internal functions and
PostGIS functions are refused. Use the anon key. The service-role key stays in the workers'
secrets. See [api.md](api.md).
