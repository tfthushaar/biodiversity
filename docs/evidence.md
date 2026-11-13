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
   quote. Each quote must be at least 25 characters and 6 words, none may repeat, and each must
   appear in the abstract of the paper it cites. A row without a quote does not exist.
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
7. **A number is quoted.** A paraphrase goes wrong most often in a figure, so every number in a
   row's summary must appear in one of its quotes, and every number in the summary, the "affected"
   field and the region note must appear in the paper's abstract. A number word (one to twelve)
   counts as its digit. The figure a reader sees is then visibly the paper's.
8. **No preprints.** A DOI from arXiv, bioRxiv, medRxiv, SSRN, Zenodo, Research Square, OSF,
   Preprints.org or Authorea, or a venue with one of those names, is refused. Peer review is not
   something the platform can assume.
9. **Two indexes vouch for a paper.** Crossref and OpenAlex must both know the DOI and must
   describe the same paper: the same title, the same year (within one, for online-first papers) and
   the same DOI. No DOI may be listed twice.

## What is on file

| | |
|---|---|
| Peer-reviewed papers | 31, from 28 journals, published 2016 to 2026 |
| Findings on effects | 21 (10 field studies, 6 controlled experiments, 4 reviews, 1 model projection) |
| Management rows | 19 (9 controlled experiments, 5 field studies, 5 reviews) |
| Verbatim quotes | 84 |
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
- OpenAlex has no record of it, or holds the DOI under another paper, or gives a different title
  or year from Crossref;
- the title, journal, year or first author in the file differs from the record (a footnote marker
  that the journal adds to a title is the only difference allowed);
- it was published before `min_year`;
- Crossref attaches a retraction, withdrawal or expression-of-concern notice, or OpenAlex marks it
  retracted;
- OpenAlex lists its venue as anything but a journal, or types the work as a preprint, a dataset,
  a reviewer's report, an erratum or another kind of record that is not a published paper
  (a paper typed as an article, a review or a data paper passes).

A quote fails when it does not appear in the abstract that Crossref or OpenAlex holds for the paper.
The match ignores typography (curly quotes, dash variants, accents, spacing, case) and nothing else.
A changed word or number is a failure. A paper with no abstract available cannot be quoted, so it
cannot be used. A row fails when its summary states a number that none of its quotes contains, or
when its summary, "affected" field or region note states a number that the abstract does not.

`--write` stamps `verified_on` into the file after a clean run. A weekly workflow repeats the check
and fails when a record changes.

## Where each rule is enforced

| Rule | Where |
|---|---|
| Source is a paper with a DOI, recent, not a venue on the blocklist, not a preprint server, listed once | `validate_structure` in `src/biodiv/knowledge/verify.py`, run in CI and by the loader |
| A summary's numbers are in its quotes; quotes are 6 words or more and not repeated | `validate_structure`, so it needs no network |
| A row's numbers are in the abstract; both indexes agree on the paper | `find_problems` and `check_paper` (weekly workflow) |
| Paper exists, is published, matches, is not retracted; quotes are in the abstract | `scripts/verify_citations.py` (weekly workflow) |
| DOI shape, year of 2016 or later, journal, study design and quotes on every row | Check constraints in migration 0020, so a row entered by hand cannot break them |
| The public sees only rows whose quotes were verified | The `public_read` policies on `impact_findings` and `mitigation_playbooks` (migration 0020) |
| A species without a paper is not an invasive record | The `invasive_records` view, which joins `researched_species` (migration 0024). The hotspot map, species list, reports, counts and alerts read from it |
| The public API names only species with a paper | `public_read` policies on `species` and `invasive_status` (migration 0024) |
| The ingest does not store such a species | `unresearched_invasives` in `src/biodiv/workers/ingest.py` refuses it with the reason `invasive_without_paper` |
| The analysis counts only such species as invasive | `cooccurrence` and `trend` in `src/biodiv/analytics/impact.py` |
| Records stored before the rule | `scripts/prune_unresearched.py` reports them, and removes them with `--delete` |

## The paper's own references and numbers

The paper (`paper.md`, built from `docs/paper_template.md`) holds itself to the same rules. Its
credibility rests on three files and a build that refuses to write a paper they contradict.

| File | What it holds |
|---|---|
| `db/seeds/paper_references.json` | Every reference the paper cites. An **article** has a DOI and is checked against Crossref and OpenAlex like the evidence base. A `claim` article supports a statement, so it must be recent (2014 or later) and carries verbatim abstract quotes. A `method` article is where a statistical method or tool comes from, and a `dataset` article describes data the study used. Neither supports a claim about the world, so neither needs a quote. Journal articles, conference papers and book chapters are accepted, and preprints are not. A **resource** is data, software or a model (GBIF, iNaturalist, MegaDetector) that is credited by name and never cited as evidence |
| `docs/paper_numbers.json` | Every number typed into the paper's prose, with where it comes from: a value at a named path in a metrics file, a constant in the code, or a line in a document |
| `docs/metrics/*.json` | The measured results the numbers come from, including `usgs_python_sources.json`, which `scripts/usgs_python_sources.py` writes from the USGS API |

`python scripts/build_paper.py` fails, and writes no paper, when:

- a citation in the text names no paper, or two papers, in the evidence base or the references;
- a reference is in the list and no sentence cites it, or a resource is credited and never named;
- a sentence cites a paper and states a number that the paper's quotes do not contain (a cited
  claim and our own count belong in separate sentences);
- the text names a preprint server;
- a number is typed into the prose with no recorded origin, an origin does not hold the number, or
  an entry is left behind for a number that is no longer in the paper;
- a statement about the data (a trend, a share, which park has which records) no longer holds.

The reference list is generated from the registry, never typed. A statement that rests on a source
that cannot be looked up, such as a preprint, is reworded to what a verified paper says, or left out.

## Adding a species or a claim

1. Find the paper in a journal. Check that it has a DOI and an abstract that states the result.
2. Add the DOI to `sources` in `db/seeds/knowledge.json` with its title, authors, year, journal,
   volume and pages exactly as the journal prints them.
3. Add a row that restates the result and quotes the abstract word for word.
4. Quote the sentence that gives each number the summary states.
5. Run `python scripts/verify_citations.py --write`, then `python -m biodiv.workers.seed_knowledge --prune`.

The species then appears on the dashboard with its records. Until a paper backs it, it does not.

## What this leaves out

The statistical layers on the Impact page, and the accuracy of the photo models, are measurements
made here and not claims from a paper. They name no species that lacks a paper, and each states its
data minimums and its limits. The counts of records are counts of what the sources hold.
