# Evidence rules

The platform shows a claim only when a peer-reviewed paper backs it. This page states the rules,
how they are checked, and where each one is enforced.

## The rules

1. **Only peer-reviewed journal articles are cited.** News stories, blogs, project pages, species
   profiles, fact sheets and extension bulletins are never sources. Each source is identified by a
   DOI.
2. **Papers are recent.** A paper must be published in 2016 or later. The cut-off is `min_year` in
   `db/seeds/knowledge.json`, and the database repeats it.
3. **Every claim carries quotes.** A finding or a management option needs at least one verbatim
   quote, each quote must be at least 25 characters, and each must appear in the abstract of the
   paper it cites. A row without a quote does not exist.
4. **Every claim says where its evidence comes from.** The `region_note` names the place, the
   sample and the period of the study, so a result from an arid grassland is never read as a
   result for a forest.
5. **Our own ratings are not claims we can make.** No paper states how well a method works in
   general, what it costs, or what it risks, so none of those fields exists. A row restates what one
   paper reports, with its study design: controlled experiment, field study, review of studies or
   model projection.
6. **A species appears only when a paper backs it.** A species GRIIS lists as invasive counts as
   an invasive species here only when at least one finding or management row about it has verified
   quotes. A species without a paper is not recorded, not counted, not mapped, not listed and not
   raised in an alert.

## What is on file

| | |
|---|---|
| Peer-reviewed papers | 31, from 28 journals, published 2016 to 2026 |
| Findings on effects | 21 (10 field studies, 6 controlled experiments, 4 reviews, 1 model projection) |
| Management rows | 19 (9 controlled experiments, 5 field studies, 5 reviews) |
| Verbatim quotes | 75 |
| Species with a paper | 14 |

The species are *Python bivittatus*, *Osteopilus septentrionalis*, *Schinus terebinthifolia*,
*Melaleuca quinquenervia*, *Lygodium microphyllum*, *Adelges tsugae*, *Microstegium vimineum*,
*Pueraria montana*, *Salmo trutta*, *Lantana camara*, *Senna spectabilis*, *Chromolaena odorata*,
*Parthenium hysterophorus* and *Prosopis juliflora*. Some of them have records in a park and some
have none. The Species page lists all 14 with their papers and says which are not recorded.

The file records null and negative results as well as positive ones. For example, scent lures did
not raise python detections, and the short-term clearing of *Lantana* in a Ugandan forest did not
promote tree establishment.

## How a paper is checked

`python scripts/verify_citations.py` looks up every DOI in Crossref and OpenAlex. A source fails
the check when:

- Crossref has no record of the DOI;
- Crossref types it as anything but a journal article, gives it a subtype such as a preprint, lists
  no ISSN for the journal, or lists no authors;
- the journal is on the policy's list of venues that are not research journals (extension
  bulletins);
- the title, journal, year or first author in the file differs from the record (a footnote marker
  that the journal adds to a title is the only difference allowed);
- it was published before `min_year`;
- Crossref attaches a retraction, withdrawal or expression-of-concern notice, or OpenAlex marks it
  retracted;
- OpenAlex lists its venue as anything but a journal, or types the work as anything but an article.

A quote fails when it does not appear in the abstract that Crossref or OpenAlex holds for the paper.
The match ignores typography (curly quotes, dash variants, accents, spacing, case) and nothing else.
A changed word or number is a failure. A paper with no abstract available cannot be quoted, so it
cannot be used.

`--write` stamps `verified_on` into the file after a clean run. A weekly workflow repeats the check
and fails when a record changes.

## Where each rule is enforced

| Rule | Where |
|---|---|
| Source is a paper with a DOI, recent, not a venue on the blocklist | `validate_structure` in `src/biodiv/knowledge/verify.py`, run in CI and by the loader |
| Paper exists, is published, matches, is not retracted; quotes are in the abstract | `scripts/verify_citations.py` (weekly workflow) |
| DOI shape, year of 2016 or later, journal, study design and quotes on every row | Check constraints in migration 0020, so a row entered by hand cannot break them |
| The public sees only rows whose quotes were verified | The `public_read` policies on `impact_findings` and `mitigation_playbooks` (migration 0020) |
| A species without a paper is not an invasive record | The `invasive_records` view, which joins `researched_species` (migration 0024). The hotspot map, species list, reports, counts and alerts read from it |
| The public API names only species with a paper | `public_read` policies on `species` and `invasive_status` (migration 0024) |
| The ingest does not store such a species | `unresearched_invasives` in `src/biodiv/workers/ingest.py` refuses it with the reason `invasive_without_paper` |
| The analysis counts only such species as invasive | `cooccurrence` and `trend` in `src/biodiv/analytics/impact.py` |
| Records stored before the rule | `scripts/prune_unresearched.py` reports them, and removes them with `--delete` |

## Adding a species or a claim

1. Find the paper in a journal. Check that it has a DOI and an abstract that states the result.
2. Add the DOI to `sources` in `db/seeds/knowledge.json` with its title, authors, year, journal,
   volume and pages exactly as the journal prints them.
3. Add a row that restates the result and quotes the abstract word for word.
4. Run `python scripts/verify_citations.py --write`, then `python -m biodiv.workers.seed_knowledge --prune`.

The species then appears on the dashboard with its records. Until a paper backs it, it does not.

## What this leaves out

The statistical layers on the Impact page, and the accuracy of the photo models, are measurements
made here and not claims from a paper. They name no species that lacks a paper, and each states its
data minimums and its limits. The counts of records are counts of what the sources hold.
