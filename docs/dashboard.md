# The dashboard

A static React and TypeScript app (`web/`). It has no server of its own: it reads the database's
public REST API and draws the results, which lets it run on a free static host that never sleeps.
[api.md](api.md) explains why the database is the security boundary.

## Pages

| Page | What it answers | Source of its numbers |
|---|---|---|
| Overview | How many invasive records, how many invasive species, how many papers, and how records are spread over parks, years and species | `zones_geojson()`, `zone_reports`, `invasive_by_year()`, `impact_findings`, `mitigation_playbooks` |
| Hotspots | Where invasive records concentrate in a park, which species are there, and what papers report about their effect on the local environment | `hotspot_grid()`, `invasive_by_year()`, `species` (photos), `impact_findings`, `mitigation_playbooks`, `source_health` |
| Species | One invasive species: where and when it was recorded, what papers report, and what management has been tried | `species_profile()`, `zone_reports`, `impact_findings`, `mitigation_playbooks` |
| Impact | What papers report, and whether the data supports a co-occurrence or trend statistic | `zone_reports`, computed by the analyse worker |
| Alerts | An invasive species recorded in a park for the first time | `alerts` |
| Models | What each model does with 100 photos, how far each measured rate can be trusted, accuracy against guessing, and the limits | `model_versions` |
| Sources | Where the data came from, its licence, why records were refused, and the limits of the data | `source_health` |

A species appears on any page only when a peer-reviewed paper backs it ([evidence.md](evidence.md)).
Every finding and management method shows its paper, linked to the DOI, with the quotes it rests on.

The Models page has a photo panel. It needs the optional analysis service (`VITE_API_URL`) and
reports when that service is not connected.

### The Hotspots page

1. Choose a park. Parks are grouped by country. The other filters narrow what the map and the list
   count: one species, plants or animals, one source, and a range of years. "Reset filters"
   clears them.
2. The map shows square cells shaded from light to dark red by the number of invasive records in
   them. The scale under the map explains the shading, and each cell's tooltip gives its count.
3. Squares are measured in kilometres and are square wherever the park lies. The Square size menu
   offers 0.5, 1, 2, 5, 10 and 20 km, and "Automatic" picks a size that suits the park and its
   number of records and says which. The database builds the grid at the park's own latitude, so a
   square in the Great Smoky Mountains is as wide as it is tall.
4. The panel beside the map describes a region, and its heading says which: **This square** when
   one is selected, **In the map view** after zooming or moving the map, and **Whole park**
   otherwise. It shows the records and species in that region, the busiest squares, a chart of
   records by year, and the species ranked by records, most recorded first. The first species is open
   and shows its photo with its credit, its record count and years, and up to two findings with their
   papers. "Show the whole park" returns the map to the full park.
5. Clicking empty ground clears the selected square.

The ranked list of squares and a table under the map list the same cells, so the page works with a
keyboard and a screen reader. Map shapes cannot take focus.

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

- a chart is laid out at the width it is shown, so its text is 12 px at every screen size and the
  labels along an axis are spaced by the room there is;
- the axis always reaches the highest value, so no bar or dot sits above it;
- one y-axis per chart;
- a legend for two or more series, with direct labels added only when they fit without colliding;
- a zero draws no bar;
- every chart has a "View as table" twin with the same values, and tooltips repeat information
  that is also in the table;
- keyboard users reach the same tooltips: Tab to a chart, then use the arrow keys, Home and End.

The kinds of chart are chosen for what the data is:

| Data | Chart |
|---|---|
| A count over years | Columns, with long records grouped into 5 or 10 years |
| A magnitude by category | Horizontal bars |
| A value over time where years rest on different amounts of data | Dots whose area is the data behind each year, with a trend line |
| Many squares, some at the same value | Dots in columns by class, with each class's median and size |
| One estimate with its range | A dot on a fixed scale with its interval, and what each end means |
| What happens to a whole (photos named correctly, wrongly, left as "unknown") | A stacked bar. Each part differs by fill (solid, hatched, pale) and is also written out |
| Several rates with their uncertainty | Each rate on a 0 to 100% scale with its interval, marked higher or lower is better |
| The effect of a setting | Lines, with the setting in use marked |

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

**Counts reflect recording effort.** The Overview says so before it shows a number. A species that
observers rarely record can be common and still have few records.

**Every claim carries its paper.** Findings and management options show the paper's reference,
linked to its DOI, the design of the study, where it took place, and verbatim quotes from its abstract.
`scripts/verify_citations.py` checks each paper and quote ([evidence.md](evidence.md)). Links from
the database render only when they are http(s), so a stored `javascript:` address appears as text.

**Nothing appears without a paper.** The Species page lists only species a paper backs. The charts,
counts and map read from views that hold only those species, and the browser applies no second
filter that could drift from the database.

**Only what a visitor uses is on the page.** The Overview holds three numbers and three charts, with
the year chart across the full width.
Operator details such as how full the database is stay out of the interface, and a control appears
only when it changes what the page shows.

**Estimates are not drawn as data.** When one species is chosen, the database counts its records
for each square and year exactly, and the browser never scales a total to stand in for them.

**Photos carry their credit.** A species photo is stored only when its licence allows showing it
with credit. The card shows the credit and links to the photo page, and says when no licensed photo
exists.

## Tests

`npm test` runs the formatting, scale, binning, label-spacing, grouping and grid helpers, the shared
components (meter wording, zero bars, legends, axis labels, column charts, yearly dots with a trend,
grouped dots, interval plots, share bars, rate ranges, keyboard tooltips, table twins, link safety,
paper citations), and the pages against a mocked REST API. The page tests cover
insufficient-data states, empty and failed loads, the Hotspots page (default park, region-following
panel, filters sent to the database, exact species counts, unsafe image addresses), the Species page
(only species with a paper are listed), the Impact page's charts, the Models page (the outcome bars
are worked out from how many photos a model names and how often it is right), the Overview, the
Sources page and the photo demo's disabled, rate-limited and asleep-service states. CI runs them on every push.
