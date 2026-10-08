# Data quality and what the data supports

This document lists the rules each record passes, what the rules remove, and the limits that
follow for anyone reading the dashboard. The tables are generated from the database by
`scripts/paper_tables.py --inject docs/data-quality.md`, using the summary that
`scripts/dataset_summary.py` writes to `docs/metrics/dataset_summary.json`.

## What a record must satisfy

Every record from every source passes the same rules. Each refusal is counted by reason in
`ingestion_runs.rejected` and shown on the Sources page.

- It identifies a species. Genus-level and coarser identifications are refused (`not_species_level`).
- It has a day-precision date that is not in the future. Specimens that carry only a year are
  refused (`no_date`), because the monthly index needs a day.
- Its position is not deliberately obscured (`obscured_location`) and is accurate to 2 km or
  better (`imprecise_location`). A looser limit keeps more records and blurs which park a record
  belongs to. Records with unknown accuracy are accepted.
- It is a wild occurrence. Captive or cultivated records (`captive_or_cultivated`) and USGS records
  of failed introductions (`not_established`) are refused.
- It lies inside a park boundary (`outside_zone`). Each source is searched by bounding box or by
  county, which is larger than the park, so many records fall outside.
- It is new. Records are keyed by source and external identifier (`duplicate`).

USGS records add their own rules: only the "accurate" coordinate class passes, since the
"approximate" and "centroid" classes exceed 2 km.

**Table 1.** Records that passed, by park and source.

<!-- table:records -->
| Park | Country | Area (km2) | iNaturalist | GBIF | USGS NAS | Records |
|---|---|---:|---:|---:|---:|---:|
| Bandipur | IN | 949 | 688 | 210 | - | 898 |
| Nagarahole | IN | 680 | 1,428 | 18 | - | 1,446 |
| Mudumalai | IN | 336 | 1,413 | 96 | - | 1,509 |
| Serengeti | TZ | 12,947 | 2,065 | 84 | - | 2,149 |
| Everglades | US | 6,237 | 919 | 555 | 4,352 | 5,826 |
| Great Smoky Mountains | US | 2,107 | 1,544 | 578 | 65 | 2,187 |
| **Total** |  |  | 8,057 | 1,541 | 4,417 | 14,015 |
<!-- /table -->

**Table 2.** Records refused, by reason. USGS figures come from the most complete single scan of
each park's counties, because that source re-reads every record on each run.

<!-- table:refused -->
| Reason | iNaturalist | GBIF occurrences | USGS NAS |
|---|---:|---:|---:|
| outside zone | 7,486 | 1,530 | 9,325 |
| imprecise location | 6,369 | 306 | 1,898 |
| obscured location | 5,887 | 58 | 0 |
| not species level | 38 | 3,138 | 0 |
| no date | 0 | 647 | 6 |
| not established | 0 | 0 | 32 |
<!-- /table -->

## Limits that follow

**1. Citizen science under-records the dominant invasive plants.** Across the three Indian parks,
*Lantana camara* has a handful of records and *Senna spectabilis*, *Prosopis juliflora* and
*Parthenium hysterophorus* have almost none, though all are widely reported in these reserves.
People photograph animals, flowers and unusual plants more than common weeds. A count describes
where a species was recorded, and it says little about how much ground the species covers. The
dashboard labels its counts as recorded presence.

**2. Sources differ in what they record.** The USGS database lists non-native aquatic species,
reptiles and amphibians only, so the Everglades share of invasive records is high because of the
source and says little about the park compared with the others. Shares are comparable between
parks only when the parks draw on the same kinds of source.

**3. Recording effort is uneven.** Effort in a park and month is approximated by the number of
observations there, which corrects for "more observers record more of everything". It does not
correct for observers favouring certain species or places, and in the Everglades removal campaigns
and road access shape where invasive records fall.

**4. Threatened species are probably under-represented.** Obscured positions are discarded, and
iNaturalist hides the exact location of taxa it considers sensitive. This thins the records of
exactly the threatened natives whose decline matters. We have not measured how much of the
obscuring is chosen by the observer and how much is automatic.

**5. Invasive status comes from country-level lists.** GRIIS lists the chital (*Axis axis*) for
India as native and alien (native on the mainland, introduced to the Andaman Islands). Counting
mainland chital as invasive made it the top invasive species in every Indian park, so species of
mixed or uncertain origin are excluded from the invasive statistics (`origin_class`, migration
0008). GBIF also hosts protected-area GRIIS lists, for example for Serengeti National Park, and
these would be more precise. None exists for the other parks, and supporting park-level lists
needs a schema change.

**6. Photo licences.** Both *Lantana* and *Senna* photos in our sample are all-rights-reserved on
iNaturalist, so they are stored as occurrence records and not used as training images. Only CC0,
CC BY, CC BY-NC, CC BY-SA and CC BY-NC-SA photos are used for training (`IMAGE_LICENSES`), and a
species photo on the dashboard is shown only with its credit and licence.

**7. Overlapping search areas.** Adjacent parks' search boxes overlap, so a record can be fetched
twice. The `(source, external_id)` key stores it once.

## Sources left out on purpose

- **GBIF's iNaturalist dataset.** iNaturalist is fetched directly, so including it again would
  double-count.
- **eBird through GBIF.** It holds hundreds of thousands of records in one park's search box,
  covers birds only, and would threaten the 500 MB free database. It remains available as an
  explicit, capped option: `--source gbif --gbif-dataset ebird --max N`.
- **IUCN Red List data in the public interface.** The terms of use prohibit redistribution
  without written permission (see [iucn.md](iucn.md)).

## Evidence coverage

Cited findings exist for only some of the species recorded in each park. Where one species
dominates a park's records, as the Burmese python does in the Everglades, a single species'
evidence covers most records.

**Table 3.** Invasive species recorded in each park and how many have cited evidence.

<!-- table:coverage -->
| Park | Invasive species recorded | With a cited finding | With cited management | Records covered by a finding |
|---|---:|---:|---:|---:|
| Bandipur | 14 | 1 | 1 | 12% |
| Nagarahole | 6 | 2 | 2 | 29% |
| Mudumalai | 18 | 4 | 4 | 27% |
| Serengeti | 2 | 0 | 0 | 0% |
| Everglades | 17 | 1 | 1 | 73% |
| Great Smoky Mountains | 34 | 2 | 0 | 10% |
<!-- /table -->

## What this means for use

The pipeline's numbers are exact counts of what the sources contain after the rules above. They
support statements about recorded presence and about where records concentrate. They do not
support statements about abundance, and statistical results appear only above the data minimums
in [impact.md](impact.md). Ways to widen what the data can support, roughly in order of effort:

1. State recorded presence with these caveats wherever a number appears, which the dashboard does.
2. Ingest unverified (`needs_id`) observations of known invasive taxa and have the plant
   classifier check them, which turns a data gap into a use for the classifier.
3. Let park staff upload geotagged photos through the classifier, so field teams can fill gaps
   that public feeds leave.
