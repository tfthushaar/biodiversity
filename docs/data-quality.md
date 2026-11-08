# Data quality and what the data supports

This document lists the rules each record passes, what the rules remove, and the limits that
follow for anyone reading the dashboard. The tables are generated from the database by
`scripts/paper_tables.py --inject docs/data-quality.md`, using the summary that
`scripts/dataset_summary.py` writes to `docs/metrics/dataset_summary.json`.

The tables below are a snapshot of 8 November 2026, taken after the records stored before two
rules were removed: GBIF supplies preserved specimens only, and a species counts as invasive only
when a peer-reviewed paper backs it ([evidence.md](evidence.md)).

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
- For GBIF, it is a preserved specimen (`not_a_specimen`). Specimens trace to a museum or herbarium
  collection. Human observations, machine observations, material samples and records of
  unspecified origin do not.
- It is not a record of an invasive species that no paper backs (`invasive_without_paper`). A
  species GRIIS lists as alien and invasive in the park's country is stored only when a
  peer-reviewed paper reports on it.

USGS records add their own rules: only the "accurate" coordinate class passes, since the
"approximate" and "centroid" classes exceed 2 km.

**Table 1.** Records that passed, by park and source.

<!-- table:records -->
| Park | Country | Area (km2) | iNaturalist | GBIF | USGS NAS | Records |
|---|---|---:|---:|---:|---:|---:|
| Bandipur | IN | 949 | 686 | 204 | - | 890 |
| Nagarahole | IN | 680 | 1,433 | 7 | - | 1,440 |
| Mudumalai | IN | 336 | 1,401 | 80 | - | 1,481 |
| Serengeti | TZ | 12,947 | 8,290 | 846 | - | 9,136 |
| Everglades | US | 6,237 | 8,169 | 3,432 | 4,198 | 15,799 |
| Great Smoky Mountains | US | 2,107 | 8,164 | 4,451 | 54 | 12,669 |
| **Total** |  |  | 28,143 | 9,020 | 4,252 | 41,415 |
<!-- /table -->

**Table 2.** Records refused, by reason. USGS figures come from the most complete single scan of
each park's counties, because that source re-reads every record on each run.

<!-- table:refused -->
| Reason | iNaturalist | GBIF specimens | USGS NAS |
|---|---:|---:|---:|
| outside zone | 23,910 | 58,365 | 13,413 |
| imprecise location | 16,662 | 25,917 | 2,424 |
| not species level | 250 | 32,757 | 0 |
| no date | 0 | 29,724 | 6 |
| obscured location | 16,034 | 977 | 0 |
| not established | 0 | 0 | 36 |
<!-- /table -->

## Limits that follow

**1. A record shows presence, and a count shows where species were recorded.** The records hold no
measure of how much ground a species covers or how many individuals there are. A species that
observers record rarely may be common and still have few records. The dashboard labels its counts
as recorded presence.

**2. Sources differ in what they record.** The USGS Nonindigenous Aquatic Species database holds
curated records of non-native aquatic species, and only the two US parks draw on it. The share of
invasive records in the Everglades is high because of the source and says little about the park
compared with the others. Shares are comparable between parks only when the parks draw on the same
kinds of source.

**3. Recording effort is uneven and unmeasured.** Effort in a park and month is approximated by the
number of observations there, which corrects for the number of records. It does not correct for
which species or places observers choose.

**4. Hidden positions are discarded.** Records with a deliberately obscured position are refused and
counted (`obscured_location`). A species whose records are often hidden is thinner in the data than
it is on the ground.

**5. Invasive status comes from country-level lists.** GRIIS lists the chital (*Axis axis*) for India
as native and alien. Counting it as invasive made it the top invasive species in every Indian park,
so species of mixed or uncertain origin are excluded from the invasive statistics (`origin_class`,
migration 0008). GBIF also hosts protected-area GRIIS lists, for example for Serengeti National
Park, and these would be more precise. None exists for the other parks, and supporting park-level
lists needs a schema change.

**6. Photo licences.** *Lantana* and *Senna* photos in our sample are all-rights-reserved on
iNaturalist, so they are stored as occurrence records and not used as training images. Only CC0,
CC BY, CC BY-NC, CC BY-SA and CC BY-NC-SA photos are used for training (`IMAGE_LICENSES`), and a
species photo on the dashboard is shown only with its credit and licence.

**7. Overlapping search areas.** Adjacent parks' search boxes overlap, so a record can be fetched
twice. The `(source, external_id)` key stores it once.

**8. The dashboard is narrower than the GRIIS lists.** Only 14 species have a peer-reviewed paper on
file, so only those appear as invasive species. A species with many records and no paper does not
appear until a paper backs it. This keeps every claim sourced and means a count here is smaller than
a count of everything GRIIS lists. Applying the rule removed 1,213 records of 192 species, 959 of
them in the Everglades and 205 in Great Smoky Mountains.

**9. Three parks lack recent iNaturalist records.** iNaturalist is read oldest first, and at most
8,000 records are stored per park (`--max-stored-per-zone` in the ingest workflow). The Everglades,
Great Smoky Mountains and Serengeti reached that limit. On 8 November 2026 their iNaturalist
records ended in January 2019, February 2019 and March 2024. For these parks the counts describe the
earlier years better than the recent ones, and any change over time mixes a change in the records
with a change in what was fetched. The Everglades invasive trend is the clearest case: no
iNaturalist record of the park is dated 2020 or later, and the invasive share of all records is
55% from 2020 on against 10% in 2010 to 2019.

## Sources left out on purpose

- **GBIF's iNaturalist dataset.** iNaturalist is fetched directly, so including it again would
  double-count.
- **GBIF records that are not preserved specimens.** Of the 9,751 GBIF records stored, 731 were not
  specimens: 485 unspecified occurrences, 239 material samples such as DNA extracts and 7 that GBIF
  no longer holds. They were removed. The query now asks for preserved specimens only, and eBird,
  which GBIF also carries, is no longer an option.
- **IUCN Red List data.** The terms of use prohibit redistribution without written permission, and
  nothing on the dashboard read the 4,362 threat links that were imported, so the importer and the
  table were removed (migration 0021).
- **Records of invasive species that no paper backs.** See limit 8.

## Evidence coverage

Every invasive species recorded has at least one paper behind it. A species can have a paper on its
management and none on its effect, or the reverse, so the columns below can differ. Where one
species dominates a park's records, as the Burmese python does in the Everglades, a single species'
evidence covers most records.

**Table 3.** Invasive species recorded in each park and how many have cited evidence.

<!-- table:coverage -->
| Park | Invasive species recorded | With a cited finding | With cited management | Records covered by a finding |
|---|---:|---:|---:|---:|
| Bandipur | 1 | 1 | 1 | 100% |
| Nagarahole | 2 | 2 | 2 | 100% |
| Mudumalai | 3 | 3 | 3 | 100% |
| Everglades | 4 | 2 | 3 | 99% |
| Great Smoky Mountains | 4 | 4 | 3 | 100% |
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
