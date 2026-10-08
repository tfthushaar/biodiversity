# IUCN Red List threat links

**Goal.** For each native species, record which named invasive species the IUCN Red List says
threaten it. The Red List codes this as threat 8.1.2, "invasive non-native species: named
species".

**Status (October 2026).** The importer is built (`python -m biodiv.workers.import_iucn`) and has
run against Red List version 2026-1 for India, Tanzania and the United States. The database holds
4,362 links for 1,986 assessed species, stored privately. Nothing from the Red List appears in the
dashboard, the public API or the paper's results.

## Terms of use

IUCN's terms (<https://www.iucnredlist.org/terms/terms-of-use>) allow Red List data to be used for
conservation, education, scientific analysis and research. They prohibit reposting, sub-licensing,
reselling and other redistribution of the data "whole or in part, alone or combined with other
data, including within Derivative Works" without IUCN's prior written permission, and they require
a permission waiver for derivative works. Results must carry full acknowledgement and citation,
including the Red List version, and the token holder indemnifies IUCN for violations.

Our database is publicly readable, so displaying IUCN rows on the dashboard would redistribute the
data. Migration 0017 therefore hides rows whose `evidence_source` is `iucn` from the public roles,
and `tests/test_public_surface.py` checks it. Rows from cited literature stay public. The workers
and the database owner see every row.

To publish IUCN-derived results, request written permission from IUCN (contact details are in
section 16 of the terms), then replace the policy in a new migration and add the acknowledgement
and the Red List version wherever the results appear. We do not commit real IUCN responses to the
repository, and tests use synthetic fixtures with the same shape.

## What the API returns

The API is documented at <https://api.iucnredlist.org/>. The token goes in the `Authorization`
header, and the API accepts it with or without a `Bearer ` prefix.

| Endpoint | Use |
|---|---|
| `GET /api/v4/threats/8_1_2` (`latest=true`, `page`, `per_page` up to 100) | Assessments that list threat 8.1.2. Paging follows the `Link` header |
| `GET /api/v4/countries/IN` and `.../TZ` | Assessments for species that occur in India or Tanzania |
| `GET /api/v4/assessment/{id}` | The full assessment |

In a full assessment, each entry in `threats` has a `code`, `timing`, `scope`, `score` and, for
code `8_1_2`, an `ias` field that names the invasive species. For example, an assessment of a
North American fish lists *Ambloplites rupestris* under `8_1_2`.

On Red List version 2026-1 the threat 8.1.2 list has 10,102 assessments. Intersecting it with the
country lists leaves 2,134 assessments that name an invasive species and occur in India (368),
Tanzania (260) or the United States (1,592), with some in more than one country. The run wrote 4,402
links, which merged into 4,362 distinct rows, and 1,307 of the links name an invader that has no
row in our species table, so they are stored by name.

**Rate limit.** The API answered HTTP 429 at about four requests per second with four in flight.
The importer runs at one request per second and honours `Retry-After`.

## The importer

1. List the 8.1.2 assessments and each country's assessments, and intersect them.
2. Fetch each candidate assessment and read its `8_1_2` entries. Names are taken from the `ias`
   field and kept only when they have the shape of a scientific name.
3. Store a row in `threat_links` with `evidence_source = 'iucn'`, the native species, the named
   invasive species (linked to a species row when the name matches, kept as text otherwise), scope,
   timing, impact score, assessment year, the assessment URL and a citation that includes the Red
   List version. A re-run skips assessments already stored. `--dry-run` reads and parses only.

Rows from cited publications use `evidence_source = 'literature'` with a citation, are public, and
are labelled as literature wherever they appear.
