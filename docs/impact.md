# Impact analysis and management knowledge

This document describes how the platform estimates what invasive species do to a park's native
ecosystem and what it records about managing them. Each claim states its evidence, and an analysis
declines to answer when the data is too thin to support it.

Run it with `python -m biodiv.workers.analyse` (all parks, or `--zone bandipur`).

## Three layers, from most to least certain

| Layer | Question | Needs | Status |
|---|---|---|---|
| 1. Documented findings | What do peer-reviewed papers report about these species here? | A paper for each species | Available for the 14 species that have one |
| 2. Co-occurrence | Where invasives are denser, is native richness lower? | 20 or more grid cells with 10 or more native records each, and 5 or more of those also holding invasive records | Computed where the data reaches the minimum, and "insufficient" elsewhere |
| 3. Trend | Is the invasive share rising while natives fall? | 6 or more years with 15 or more observations each, and 30 or more invasive records in the park | Computed where the data reaches the minimum, and "insufficient" elsewhere |

An invasive record is a record of a species that GRIIS lists as alien and invasive in the park's
country **and** that a peer-reviewed paper backs ([evidence.md](evidence.md)). Layers 2 and 3 count
only those records as invasive. Which parks reach the minimums changes as records accumulate, and
the Impact page shows each park's status and its distance from each minimum.

Layers 2 and 3 are implemented, tested and gated by those minimums. Where they run, recording effort
and the mix of sources shape their results, so they describe records and give limited information
about the effects of invaders. Below the minimums the result is "insufficient", with the reason and
what would help, for example *"only 8 invasive records in the zone (need 30)"*. A statistic computed
from a handful of records would suggest more certainty than the records support, so none is shown.
The dashboard draws each statistic from the data behind it. For the correlation it shows the
estimate with its interval on a scale from -1 to +1, then every map square as a dot, grouped by the
share of its records that are invasive (none, then up to three groups of similar size), with the
middle of each group marked and each group's size stated. For the trend it shows the invasive share
for each year as a dot whose area is the observations that year rests on, with the Theil-Sen line, and
beneath it a column chart of the observations in each year. That second chart shows what the trend
rests on: a sudden change in effort can produce a trend in the share. The native share is not drawn,
because it moves against the invasive share (both are shares of the same records), and both tests
are in the table.

### Layer 1: documented findings

`db/seeds/knowledge.json` is loaded into `impact_findings` and `mitigation_playbooks`. [evidence.md](evidence.md)
states the rules: only peer-reviewed journal articles from 2016 on, every claim with verbatim quotes
from the paper's abstract, and a note on where the study took place. Each finding carries its study
design (controlled experiment, field study, review of studies or model projection) and its paper's
reference, linked to the DOI.

- `scripts/verify_citations.py` looks up each paper in Crossref and OpenAlex and checks every quote
  against the abstract. It tolerates typography (curly quotes, dashes, accents, case, spacing) and
  nothing else. The current file has 40 rows backed by 84 quotes from 31 papers, and all of them
  verify. Each number a summary states is also in a quote, and in the abstract. A weekly workflow
  repeats the check, and covers the paper's own references too ([evidence.md](evidence.md)).
- A finding about a park is shown even when we hold no record of the species there, and the page
  marks it as reported and not recorded. A report of a species in the literature is not a sighting.
- Where a paper reports work from another region, the row's region note says so. For example, the
  *Lantana* finding from Kibale National Park concerns an African rainforest.

### Layer 2: co-occurrence

For each grid cell of about 5 km, the analysis compares the share of records that are invasive
with the rarefied native species richness. Raw richness depends on how often observers visited a
cell, since a well-visited cell records more species. Hurlbert's rarefaction (Hurlbert 1971)
removes that dependence by asking how many species a fixed sample of 10 records would show.
Spearman's rank correlation with a bootstrap 95% interval then reports the relationship and its
uncertainty. On synthetic grids with a known answer, a built-in negative relationship is recovered
(rho below -0.7 with an interval wholly below zero) and unrelated data gives an interval that
spans zero.

The result is a correlation. Invasives and natives can both depend on disturbance, road access or
where observers go, and the output carries that caution.

### Layer 3: trend

The analysis computes yearly invasive and native records per observation and tests each series
with the Mann-Kendall test (Mann 1945) and the Theil-Sen slope (Sen 1968). Neither assumes a normal
distribution, and a single unusual year cannot move the slope much. The implementations match SciPy:
Kendall's tau and the slope exactly, and the p-value to within 0.03 of SciPy's exact value. A trend
in records reflects recorded presence over time and does not show a change in abundance or its
cause.

## Early-detection alerts

An alert marks the first record of an invasive species in a park, in our sources, after enough
observation that its earlier absence means something. It is raised only for a species a paper backs,
only when the first record is less than a year old, the park had at least 50 observations before it,
and no finding already reports the species in that park. Each alert carries the caveat that a first
record in our sources may come long after the species arrived. Severity is high when a paper
reports harm by the species anywhere, and medium otherwise. An alert is a prompt to look.

## Management knowledge

`mitigation_playbooks` holds 19 rows, each restating what one paper reports about a method, with
the setting of the study and its design. No row rates a method: no paper states how well a method
works in general, so the platform does not either.

- Methods covered are biological control (5 rows), mechanical removal (4), chemical control (4),
  combined methods (3), detection (2) and use and community-based management (1).
- The rows include null and negative results. Rabbit scent lures did not raise Burmese python
  detections in the Everglades, and short-term cutting and uprooting of *Lantana* in a Ugandan
  rainforest did not promote tree establishment.
- A four-year randomised field experiment in the Banni grassland of Gujarat (Nerlekar et al. 2021)
  found that mechanical removal of *Prosopis juliflora* tripled native herb richness and raised
  cover sixfold, that lopping did not differ from the control, and that removal is costly. The site
  is an arid grassland.
- A species with no management paper has no management row, and the Species page leaves the
  section out.

A method that worked in one habitat or country may not work in another.
