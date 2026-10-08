# The dashboard

A static React and TypeScript app (`web/`). It has no server of its own: it reads the database's
public REST API and draws the results, which lets it run on a free static host that never sleeps.
[api.md](api.md) explains why the database is the security boundary.

## Pages

| Page | What it answers | Source of its numbers |
|---|---|---|
| Overview | How many records, how many are invasive, any early-detection alerts, and what the data supports | `zones_geojson()`, `zone_reports`, `alerts` |
| Hotspots | Where invasive records concentrate in a park, which species are there, and what research reports about their effect on the local environment | `hotspot_cells()`, `species` (photos), `impact_findings`, `mitigation_playbooks` |
| Species | One invasive species: where it is recorded, what research reports, and what management has been tried | `zone_reports`, `impact_findings`, `mitigation_playbooks` |
| Impact | What cited sources report, and whether the data supports a co-occurrence or trend statistic | `zone_reports`, computed by the analyse worker |
| Alerts | An invasive species recorded in a park for the first time | `alerts` |
| Models | Measured accuracy of each model, with its limits | `model_versions` |
| Sources | Where the data came from, its licence, why records were refused, and how full the free database is | `source_health`, `storage_status()` |

The Models page has a photo panel. It needs the optional analysis service (`VITE_API_URL`) and
reports when that service is not connected.

### The Hotspots page

1. Choose a park and, optionally, one species. Parks are grouped by country.
2. The map shows square cells shaded from light to dark red by the number of invasive records in
   them. The scale under the map explains the shading, and each cell's tooltip gives its count.
3. The square size defaults to a value that suits the park and its number of records. The
   Square size menu offers 0.5, 1, 2, 5 and 10 km.
4. Selecting a cell, on the map or in the ranked list beside it, opens a card for each species
   there: a photo with its credit and a link to the photo page, the number of records and the years
   they span, and up to two cited findings on the species' effect on the local environment. When no
   cited research is on file, the card says so. A link leads to the full species page.
5. "Show individual records" draws the park's 5,000 most recent invasive records as small dots.

The ranked list and a table under the map list the same cells, so the page works with a keyboard
and a screen reader. Map shapes cannot take focus.

## Visual design

The interface is monochrome. Greys carry the layout, and red appears only on the map, where it
marks hotspots and their legend. Where colour would normally separate things, the interface uses
shade, line style, fill and words instead:

- chart series differ by dash pattern as well as shade, so they stay distinct in greyscale and in
  print;
- record kinds differ by fill and outline and always carry a label;
- icons are drawn in the interface and no emoji or symbol characters are used.

Light and dark themes are designed separately and follow the system setting unless the visitor
picks one. The map's base tiles are greyscale in both themes.

Charts follow a few rules:

- one y-axis per chart;
- a legend for two or more series, with direct labels added only when they fit without colliding;
- a zero draws no bar;
- every chart has a "View as table" twin with the same values, and tooltips repeat information
  that is also in the table;
- keyboard users reach the same tooltips: Tab to a chart, then use the arrow keys, Home and End.

On a refetch the previous result stays on screen, slightly dimmed. A failed request says what
failed and offers a retry.

## Run it locally

```bash
docker compose -f docker-compose.dev.yml up -d db rest      # database and REST API on :3000
cd web
npm install
npm run dev                                                 # http://localhost:5173
npm test                                                    # component and behaviour tests
npm run build                                               # type-check, then bundle into dist/
```

With no configuration the app reads `http://localhost:3000`.

## Configuration

These variables are set at build time. They are public, because they are compiled into the
browser bundle. Copy `web/.env.example` to `web/.env.local` for local use.

| Variable | Meaning | Default |
|---|---|---|
| `VITE_REST_URL` | The REST API, for example `https://REF.supabase.co/rest/v1` | `http://localhost:3000` |
| `VITE_ANON_KEY` | Supabase's anon or publishable key. Never the service-role key | none |
| `VITE_API_URL` | The optional FastAPI service for the photo demo | none |

## Deploying (Vercel Hobby, no card)

Import the repository, set the root directory to `web`, and add the variables above. `web/vercel.json`
holds the build command, the output directory and the single-page-app rewrite. Every push to `main`
redeploys the site. Environment variables are read at build time, so changing one needs a
redeploy. Before relying on a deployment, run
`python scripts/smoke_rest.py https://REF.supabase.co/rest/v1 --key ANON_KEY`.

## Design decisions

**Statistics wait for enough data.** The two statistical layers on the Impact page decline to
answer below a minimum amount of data ([impact.md](impact.md)). A meter shows how far each park
is from each requirement, so an insufficient result tells the reader what would change it.

**Counts reflect recording effort.** The Overview says so before it shows a number, because
citizen-science photos under-record the plants that dominate these reserves.

**Every claim carries its evidence.** Findings and management options show verbatim quotes from
the cited source, the certainty of the evidence, and where it was gathered. `scripts/verify_citations.py`
checks each quote against the live page. Links from the database render only when they are http(s),
so a stored `javascript:` address appears as text.

**Photos carry their credit.** A species photo is stored only when its licence allows showing it
with credit. The card shows the credit and links to the photo page, and says when no licensed photo
exists.

## Tests

`npm test` runs the formatting, scale and grid helpers, the shared components (meter wording, zero
bars, legends, keyboard tooltips, table twins, link safety), and the pages against a mocked REST
API. The page tests cover insufficient-data states, empty and failed loads, the Hotspots page
(default park, species filter, cards with and without a photo or research, unsafe image addresses)
and the photo demo's disabled, rate-limited and asleep-service states. CI runs them on every push.
