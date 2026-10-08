# The dashboard

A static React + TypeScript app (`web/`). It has no server of its own: it reads the database's
public REST API and draws what it finds. That is what lets it run on a free static host that never
sleeps. See [api.md](api.md) for why the database, not a server, is the security boundary.

## Pages

| Page | What it answers | Where its numbers come from |
|---|---|---|
| Overview | How many records, how many are invasive, any early-detection alerts, and what the data can and cannot support | `zones_geojson()`, `zone_reports`, `alerts` |
| Map | Where every sighting was recorded, with invasive records emphasised | `zones_geojson()`, `records_geojson()` |
| Impact | What cited sources report, and whether there is enough data for a co-occurrence or trend statistic | `zone_reports` (precomputed by the analyse worker) |
| Species | One invasive species: where it was recorded, what research reports, what management has been tried | `invasive_status`, `impact_findings`, `mitigation_playbooks` |
| Alerts | Early detections: an invasive species recorded in a zone for the first time | `alerts` |
| Models | Measured accuracy of each model, with the caveats that go with it | `model_versions` |
| Sources | Where the data came from, its licence, why records were refused, and how full the free database is | `source_health`, `storage_status()` |

The Models page has a "try it on a photo" panel. It needs the optional analysis service
(`VITE_API_URL`); without one the panel says so instead of offering a button that cannot work.

## Run it locally

```bash
docker compose -f docker-compose.dev.yml up -d db rest      # database + the REST API on :3000
cd web
npm install
npm run dev                                                 # http://localhost:5173
npm test                                                    # component and behaviour tests
npm run build                                               # type-check, then bundle into dist/
```

With no configuration it reads `http://localhost:3000`.

## Configuration

Set at build time (Vercel: Project Settings, Environment Variables). All three are public by
design: they end up in the browser bundle.

| Variable | Meaning | Default |
|---|---|---|
| `VITE_REST_URL` | The REST API, e.g. `https://REF.supabase.co/rest/v1` | `http://localhost:3000` |
| `VITE_ANON_KEY` | Supabase's **anon** key. Never the service-role key. | none |
| `VITE_API_URL` | The optional FastAPI service for the live photo demo | none (panel explains itself) |

## Deploying (Vercel Hobby, no card)

Import the repository, set the root directory to `web`, add the variables above. `web/vercel.json`
already holds the build command, output directory and the single-page-app rewrite. Run
`python scripts/smoke_rest.py https://REF.supabase.co/rest/v1 --key ANON_KEY` first: if that
passes, the dashboard has everything it needs and nothing it should not.

## Design decisions worth knowing

**It would rather say "not enough data" than show a number.** The two statistical layers on the
Impact page refuse to answer below a minimum amount of data (see [impact.md](impact.md)). A meter
shows how far off each requirement is, so "insufficient" is informative rather than a dead end.
On today's data every zone is insufficient; that is the honest result, not a bug.

**Counts are recorded presence, never abundance.** The Overview says this before it shows a
number, because citizen-science photos badly under-record the plants that dominate these reserves.

**Every claim carries its evidence.** Findings and management options show verbatim quotes from
the cited source (each checked against the live page by `scripts/verify_citations.py`), the
certainty of the evidence, and the place and year it applies to. Links from the database are
rendered only if they are http(s): a stored `javascript:` URL is shown as text.

**Charts follow a few fixed rules.**

- One y-axis per chart, never two. A chart with two or more series always has a legend; direct
  end-labels are added only when they fit without colliding.
- A zero draws no bar, so none never looks like a little.
- Every chart has a "View as table" twin with the same values, and the tooltip is never the only
  place a value appears. Keyboard users get the same tooltip: Tab to a chart, then the arrow keys,
  Home and End.
- Colour follows the thing, not its rank: invasive is always orange, native always blue, and a
  colour is never the only cue (each kind also carries a word).
- Light and dark themes are chosen separately, not inverted, and follow the system setting unless
  the visitor picks one.

**Refetching never flashes.** On a refetch the previous result stays on screen, slightly dimmed.
A failed request says what failed and offers a retry.

## Tests

`npm test` runs the formatting and scale helpers, the shared components (meter wording, zero bars,
legends, keyboard tooltips, table twins, link safety), and the pages against a mocked REST API:
insufficient-data states, empty and failed loads, the map's default zone, and the photo demo's
disabled, rate-limited and asleep-service states. CI runs them on every push.
