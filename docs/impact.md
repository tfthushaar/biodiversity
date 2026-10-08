# Impact analysis and management knowledge

This document describes how the platform estimates what invasive species do to a park's native
ecosystem and what it records about managing them. Each claim states its evidence, and an analysis
declines to answer when the data is too thin to support it.

Run it with `python -m biodiv.workers.analyse` (all parks, or `--zone bandipur`).

## Three layers, from most to least certain

| Layer | Question | Needs | Status |
|---|---|---|---|
| 1. Documented findings | What do cited sources report about these species here? | Nothing beyond the sources | Available for the species with cited findings |
| 2. Co-occurrence | Where invasives are denser, is native richness lower? | 20 or more grid cells with 10 or more native records each, and 5 or more of those also holding invasive records | STATUS_CO |
| 3. Trend | Is the invasive share rising while natives fall? | 6 or more years with 15 or more observations each, and 30 or more invasive records in the park | STATUS_TREND |

Layers 2 and 3 are implemented, tested and gated by those minimums. Below them, the result is
"insufficient", with the reason and what would help, for example *"only 8 invasive records in the
zone (need 30)"*. A statistic computed from a handful of records would suggest more certainty than
the records support, so none is shown. The dashboard's Impact page shows each park's distance from
each minimum as a meter.

### Layer 1: documented findings

`db/seeds/knowledge.json` is loaded into `impact_findings` and `mitigation_playbooks`. Every row
carries verbatim quotes from a named source, a note on where the evidence was gathered, and a
certainty label: `experimental`, `observational`, `review`, `preliminary` or `unverified_concern`.

- `scripts/verify_citations.py` downloads each source and checks that every quote appears on it.
  It tolerates typography (curly quotes, dashes, case, spacing) and nothing else. The current
  file has 41 rows backed by 83 quotes from 17 sources, and all of them verify.
  A weekly workflow repeats the check to catch pages that change or disappear.
- A finding about a park is shown even when we hold no record of the species there, and the page
  marks it as reported and not recorded. A report of a species in the literature is not a sighting.
- IUCN threat links are described in [iucn.md](iucn.md).

Sources include a peer-reviewed field study (Dorcas et al. 2012, on mammal declines as Burmese
pythons spread through Everglades National Park), USGS Nonindigenous Aquatic Species fact sheets,
and Global Invasive Species Database profiles, which summarise published studies. Where a source
reports work from another region, the row's region note says so. For example, the brown trout
finding for the Great Smoky Mountains cites studies from Michigan and Pennsylvania.

What the sources report about the Indian parks, none of it measured by this project:

- **Bandipur.** A 2007 project page reports preliminary work finding "a striking inverse pattern"
  between invasive plants (*Lantana*, *Eupatorium* and *Chromolaena*, *Parthenium*) and dominant large
  mammals, and says the extent and effects of the infestation were still unquantified.
- **Bandipur and Nagarahole.** The Karnataka forest department planted *Senna spectabilis* in the
  early 2000s as a replacement for *Lantana*, a decision now regarded as a mistake. The same article
  says management attempts are under way.
- **Mudumalai.** An elephant researcher pointed to *Senna* thickets near the reserve and called
  them an emerging problem in Tamil Nadu's reserves. The article sets this beside what it calls
  "anecdotal evidence" of spread in other southern protected areas.

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
observation that its earlier absence means something. It is raised only when the first record is
less than a year old, the park had at least 50 observations before it, and no cited source already
reports the species there. Each alert carries the caveat that a first record in our sources may
predate the species' arrival in our data by an unknown time. Severity is high when the literature
documents harm by the species anywhere, and medium otherwise. An alert is a prompt to look.

## Management knowledge

`mitigation_playbooks` holds 19 management options for 9 species, each with its quotes,
the region the evidence comes from, and an evidence-strength label.

- One result is strong evidence: a four-year randomised field experiment on *Prosopis* in the Banni
  grassland of Gujarat (Nerlekar et al. 2021). Mechanical removal tripled native herb richness and
  multiplied cover sixfold, lopping had no effect, removal was costly, and the site is an arid
  grassland and not a forest.
- For *Senna spectabilis* no documented method works reliably, and experts disagree. The Kerala forest
  department's girdling of 19,500 trees was reported as counterproductive. A practitioner reports that
  uprooting worked on 0.6 sq km. The researcher who mapped the spread warns that uprooting at scale
  could cause erosion on steep, high-rainfall ground. The dashboard shows all three accounts.
- *Lantana* biocontrol: "none of the over 40 agents trialled have resulted in total control."
- For melaleuca, climbing fern and Burmese pythons in the Everglades, the sources describe
  combinations of herbicide, removal, fire and biological control with their limits. Herbicide
  killed back climbing fern in a Florida trial, and thousands of new plants germinated afterwards
  from a mass spore release.
- Several species recorded in the parks have no cited management guidance yet. A row exists only
  when a verbatim quote supports it.

The rows summarise what published sources report, with their caveats. A method that worked in one
habitat or country may not work in another.
