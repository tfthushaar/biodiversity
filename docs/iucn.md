# IUCN Red List threat links

**Goal.** For each native species, record which named invasive species the IUCN Red List says
threaten it. The Red List codes this as threat 8.1.2, "invasive non-native species: named
species".

**Status (October 2026).** We hold an API token and have examined the API. The importer is not
built yet, and no IUCN data is stored in the database.

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

On Red List version 2026-1 the threat 8.1.2 list has about 10,200 assessments. Intersecting it
with the country lists leaves 591 assessments that name an invasive species and occur in India
(368) or Tanzania (260), with 37 in both.

**Rate limit.** The API answered HTTP 429 at about four requests per second with four in flight,
so the importer should stay near one request per second and honour `Retry-After`.

## Planned importer

1. List the 8.1.2 assessments and each country's assessments, and intersect them.
2. Fetch each candidate assessment and read its `8_1_2` entries.
3. Store a row in `threat_links` with `evidence_source = 'iucn'`, the native species, the named
   invasive species (resolved to a species row when the name matches, kept as text otherwise),
   scope, timing, score, assessment year, the assessment URL and a citation that includes the
   Red List version.

Rows from cited publications use `evidence_source = 'literature'` with a citation, are public, and
are labelled as literature wherever they appear.
