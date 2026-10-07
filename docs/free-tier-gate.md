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
