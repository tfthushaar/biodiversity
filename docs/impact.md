# Impact analysis and mitigation knowledge

How the platform reasons about what invasive species do to a zone's native ecosystem, and what it
knows about managing them. The design rule throughout: **say what the evidence is, and decline to
answer when it is too thin.**

Run it: `python -m biodiv.workers.analyse` (all zones, or `--zone bandipur`).

## Three layers, in decreasing certainty

| Layer | Question | Needs | Status on today's data |
|---|---|---|---|
| **1. Documented findings** | What do cited sources report about these species here? | nothing: no inference by us | **Available.** 13 findings from 7 sources |
| **2. Co-occurrence** | Where invasives are denser, is native richness lower? | 20+ grid cells with 10+ native records, 5+ of them also holding invasives | **Insufficient** in every zone (6 to 14 usable cells) |
| **3. Trend** | Is the invasive share rising while natives fall? | 6+ years with 15+ observations each, and 30+ invasive records | **Insufficient** in every zone (at most 8 invasive records) |

Layers 2 and 3 are implemented, tested, and gated. On the real data they answer
*"insufficient: only 8 invasive records in the zone (need 30)"* and give the reason and what would
help, rather than a number. A confident-looking statistic computed from a handful of records
would be worse than no statistic.

### Layer 1: documented findings

`db/seeds/knowledge.json`, loaded into `impact_findings` and `mitigation_playbooks`. Every row
carries **verbatim quotes** from a named source, a note on **where the evidence is from**, and a
certainty label (`experimental`, `observational`, `review`, `preliminary`, `unverified_concern`).

- **`scripts/verify_citations.py`** re-downloads each source and checks that every quote really
  appears, tolerating only typography (curly quotes, dashes, case, spacing), never wording. All 50
  quotes in 28 rows currently verify. It exists because a summarising tool once produced a "quote"
  the page did not contain. A weekly workflow re-runs it to catch pages that change or vanish.
- Findings about a zone are shown even when we hold no record of the species there, flagged
  **"reported, not recorded here"**. A worry is not an occurrence.
- Species-level IUCN threat links (code 8.1.2) are still pending an API token
  ([iucn.md](iucn.md)).

What it says about the pilot reserves, as sources report it (none of it measured by this project):

- **Bandipur:** a 2007 project page reports preliminary work finding "a striking inverse pattern"
  between invasive plants (*Lantana*, *Eupatorium/Chromolaena*, *Parthenium*) and dominant large
  mammals, and says the infestation's extent and effects were still unquantified.
- **Bandipur and Nagarahole:** the Karnataka forest department planted *Senna spectabilis* in the
  early 2000s **as a replacement for *Lantana***, a decision now regarded as a mistake. The same
  article says management attempts are underway there.
- **Mudumalai:** an elephant researcher pointed to *Senna* thickets near the reserve and called it an
  emerging problem in Tamil Nadu's reserves; the article presents this alongside what it calls
  "anecdotal evidence" of spread in other southern protected areas.

### Layer 2: co-occurrence (when there is enough data)

For each ~5 km grid cell: the share of records that are invasive, against the **rarefied** native
species richness. Raw richness would be useless: a cell observers visited more simply records more
species. Hurlbert's rarefaction asks how many species a fixed-size sample (10 records) would
show, which makes cells comparable. Spearman's rank correlation with a bootstrap 95% interval
gives a relationship and its uncertainty. Tested on synthetic grids with a known answer: a built-in
negative relationship is recovered (rho below -0.7, interval wholly below zero), and unrelated data
gives an interval spanning zero.

**It is correlation, and the result says so.** Invasives and natives can both depend on
disturbance, road access, or where observers go.

### Layer 3: trend (when there is enough data)

Yearly invasive and native records per observation, tested with Mann-Kendall and the Theil-Sen
slope (no normality assumption; one odd year cannot move it). The implementations match SciPy:
Kendall's tau and the slope exactly, and the p-value to within 0.03 of SciPy's exact value. A
trend in records is not a trend in abundance, and not evidence of cause.

## Early-detection alerts

An alert means one thing: **the first record of an invasive species in a zone, in our sources,
after enough observation that not seeing it earlier means something.** It is raised only if the
first record is within a year, the zone had 50+ observations before it, and no cited source already
reports the species there. Every alert carries the caveat that "first record" is not "first
arrival". Severity is "high" when the literature documents harm by the species anywhere, otherwise
"medium": a prompt to look, not a finding. There are none on the current data, because no
invasive record in these zones is less than a year old.

## Mitigation knowledge

15 playbook rows for 5 species, each with its quotes, the region the evidence comes from, and
evidence strength. The honest picture:

- **Only one result is strong evidence:** a four-year randomised field experiment on *Prosopis*
  in Gujarat's Banni grassland (Nerlekar et al. 2021, *Restoration Ecology*). Mechanical removal
  tripled native herb richness and multiplied cover sixfold; lopping did nothing; removal was costly; and it
  was an arid grassland, not a forest.
- **For *Senna*, nothing documented works reliably, and the experts disagree.** The Kerala forest
  department's girdling of 19,500 trees was reported counterproductive; a practitioner reports uprooting
  worked on 0.6 sq km; the researcher who mapped the spread warns uprooting at scale could cause
  erosion on steep, high-rainfall ground. All of this is shown, not a single tidy "recommendation".
- ***Lantana* biocontrol:** "none of the over 40 agents trialled have resulted in total control."
- ***Chromolaena* biocontrol** worked in Guam; no result in India is reported by that source.
- **Five of the ten classified invasives have no guidance yet** (*Opuntia stricta*, *Tridax*,
  *Mikania*, *Ageratina*, *Eichhornia*): "no citation, no row" means no row.

None of this is advice to act. It is a summary of what published sources report, with their
caveats, for someone who then decides.
