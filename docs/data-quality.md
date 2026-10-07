# Data quality and what the data can and cannot support

Measured on the first live ingestion (7 Oct 2026). These limits shape what the dashboard may
honestly claim, so they are stated up front rather than buried.

## What was ingested

| Source | Fetched | Stored | Duplicates | Rejected |
|---|---:|---:|---:|---:|
| iNaturalist (research grade, up to 2,000 per zone) | 8,000 | 1,902 | 235 | 5,863 |
| GBIF museum / herbarium specimens | 4,309 | 471 | 129 | 3,709 |

**Why so much is rejected.** Every record must have a day-precision date, a usable position
(not deliberately obscured, accurate to 2 km or better), species-level identification, a wild
origin, and sit inside a monitored reserve. Rejections are counted by reason in
`ingestion_runs.rejected`. For iNaturalist:

| Reason | Count | Share |
|---|---:|---:|
| accuracy worse than 2 km | 2,114 | 26% |
| outside the reserve boundary (inside the search box) | 2,072 | 26% |
| position deliberately obscured | 1,671 | 21% |
| not species-level | 6 | <1% |

The 2 km threshold (`MAX_UNCERTAINTY_M`) is a judgement call. A looser one keeps more data but
blurs which reserve a record belongs to. Records with *unknown* accuracy are accepted.

## Limitations that matter

**1. Citizen science badly undercounts the dominant invasive plants.** Across about 1,500
observations in three Indian reserves, only 12 are of invasive species, and just **one** is
*Lantana camara*, which is widely reported to have invaded large areas of these reserves. *Senna spectabilis*,
*Prosopis juliflora* and *Parthenium hysterophorus* have **no** records at all. People
photograph animals, flowers and the unusual, not ubiquitous weeds. The data measures what
observers choose to photograph, not what is on the ground. The "invasion index" is therefore a
**relative index of recorded presence, not abundance or cover**, and must be labelled so.

**2. Threatened species are probably under-represented.** Obscured positions are discarded, and
iNaturalist hides the exact location of taxa it considers sensitive. The effect is likely to
thin out exactly the threatened natives whose decline we care about. The split between
user-chosen and automatic obscuring has not been measured.

**3. GRIIS is country-level, and some species are native in part of a country.** Chital
(*Axis axis*) is listed for India as `Native|Alien` (native on the mainland, introduced to the
Andaman Islands) and flagged invasive there. Counting mainland chital as invasive made it the
top "invasive" species in every Indian zone (6 to 11% of records) before this was caught. Mixed
and uncertain origins are now excluded from the invasive statistics (`origin_class`, migration
0008), which brought the invasive share to 0.2 to 1.7%. GBIF also hosts protected-area GRIIS
lists (e.g. Serengeti NP, `pa-griis-serengetinp`) which would be more precise; none exist for
Bandipur, Nagarahole or Mudumalai. Supporting zone-level lists needs a schema change and is
future work.

**4. Effort is approximated.** Effort for a zone and month is the number of observations there
that month. That corrects for "more observers means more of everything", but not for observers
favouring certain species or places.

**5. Observation dates are not all equally precise.** Specimens often carry only a year; those
are rejected (`no_date`) because a monthly index needs a real day. Records before 2000 land in
the default partition of `detections`.

**6. Photo licences.** Both *Lantana* and *Senna* sample photos on iNaturalist are "all rights
reserved", so they are stored as occurrence records only, never as training images. Only CC0,
CC-BY, CC-BY-NC, CC-BY-SA and CC-BY-NC-SA photos are used (`IMAGE_LICENSES`).

**7. Overlapping search boxes.** Adjacent reserves' boxes overlap, so a record can be fetched
twice. The `(source, external_id)` unique key stores it once (the "duplicates" column).

## Deliberately not ingested

- **GBIF's iNaturalist dataset** (99.7% of the first 300 GBIF records in Bandipur): already
  fetched directly, so ingesting it again would double-count.
- **eBird via GBIF** (about 198,000 records from 2000 onward in the Bandipur search box alone): birds only, and large
  enough to threaten the 500 MB free database. Available as an opt-in:
  `--source gbif --gbif-dataset ebird --max N`.

## What this means for the project

The pipeline is sound and the numbers are honest, but open feeds alone cannot quantify the
spread of *Lantana* or *Senna* in these reserves. Options, roughly in order of effort:

1. Present the data as recorded presence with these caveats on the dashboard (done by design).
2. Ingest *unverified* (`needs_id`) observations of known invasive taxa and have the plant
   classifier (Phase 5) verify them, which turns a data gap into a use for the AI component.
3. Let staff upload their own geotagged photos through the classifier, so field teams can fill
   gaps the public feeds leave.
