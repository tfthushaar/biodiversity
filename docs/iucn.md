# IUCN Red List threat links: status and what is needed

**Goal.** For each native species, record which *named* invasive species IUCN assesses as
threatening it (threat code **8.1.2**, "invasive non-native species: named species"). This is the
zero-inference backbone of the impact analysis.

**Status: blocked on an API token. No IUCN importer is implemented yet, on purpose.**

## Why no importer yet

- The API needs a free token, but it is **reviewed by a human**, so it must be applied for.
  Start from <https://api.iucnredlist.org/> and follow its registration link.
- IUCN's published OpenAPI spec (`/api-docs/v4/openapi.yaml`) lists the endpoints but leaves
  the `GET /api/v4/assessment/{assessment_id}` response schema **empty**. How threat codes,
  timing, scope, severity, and above all the *named invasive species* appear in the payload is
  therefore unknown until a real response is seen. Parsing code written against a guessed shape
  would look finished and silently produce wrong or empty links.

## Endpoints that will matter

| Endpoint | Use |
|---|---|
| `GET /api/v4/threats/8.1.2` (`page`, `per_page` <= 100, `latest=true`, `scope_code=1`) | assessments that list threat 8.1.2 |
| `GET /api/v4/countries/IN` | assessments for species occurring in India, to intersect with the above |
| `GET /api/v4/assessment/{assessment_id}` | full assessment: threat detail and, hopefully, the named species |
| auth | `Authorization` header (the spec says "Your Bearer token"; confirm whether the `Bearer ` prefix is required) |

## When the token arrives

1. Put it in `.env` as `IUCN_API_TOKEN` and fetch one assessment to **look at the real shape**.
2. Build the importer against that shape, with a recorded fixture as its test.
3. Rows go in `threat_links` with `evidence_source = 'iucn'`.

## In the meantime

`threat_links` also accepts `evidence_source = 'literature'` rows, each with a citation
(migration 0006). Phase 6 seeds these from published sources for the pilot species. They are
labelled as literature in the dashboard and are never presented as IUCN assessments.
