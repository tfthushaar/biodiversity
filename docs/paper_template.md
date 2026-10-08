# Locating Invasive-Species Hotspots and Their Documented Effects in Six National Parks from Open Biodiversity Records and Computer Vision

K N Thushaar Rangan, Yashas S, Amogh P A and G Ritzia

*Affiliations: to be added by the authors.*

Draft of {{SNAPSHOT}}. Code, data pipeline and live dashboard: <https://github.com/tfthushaar/biodiversity>

## Abstract

Park managers need to know where invasive species concentrate and what they do to native species, but the open data that could answer this is scattered, uneven in quality and rarely linked to the evidence on effects. We built an open pipeline that runs entirely on free services and joins iNaturalist observations, GBIF specimen records, curated USGS records of non-native aquatic species, GRIIS invasive-status checklists and a quote-verified evidence base for six national parks in India, Tanzania and the United States. After counted quality rules the database held {{TOTAL_RECORDS}} records, of which {{INV_TOTAL}} are records of species that GRIIS lists as alien and invasive in the park's country. Invasive records are strongly concentrated in the Everglades, where the busiest 10% of 2 km squares hold {{HOT_EVER_SHARE}}% of them. Three parks had enough data for the statistical layers. In Great Smoky Mountains native richness correlated positively with invasive share across {{SMOKIES_CELLS}} squares (Spearman's rho = {{SMOKIES_RHO}}, 95% bootstrap interval {{SMOKIES_LO}} to {{SMOKIES_HI}}), which is consistent with both measures being higher in accessible, disturbed and heavily visited squares. In the Everglades the invasive share of records rose over {{EVER_YEARS}} years (Kendall's tau = {{EVER_TAU}}, p = {{EVER_P}}), a result that does not survive a correction for the {{N_TESTS}} tests we ran and that follows a changing mix of sources. The evidence base holds {{KB_FINDINGS}} cited findings and {{KB_PLAYBOOKS}} management options, each quote checked against its live source, and it covers few of the recorded species. Classifiers on a frozen DINOv2 backbone named invasive plants correctly in 84.9% of test photos by photographers unseen in training and made no native look-alike error in 113 trials, and the MegaDetector V6 detector found 92.6% of animal photos on a held-out camera-trap sample. Invasive counts reflect recording effort as well as presence, the evidence covers a minority of species, and the statistical estimates are confounded by effort and source. The pipeline, its data minimums and its evidence checks are open, so the estimates can sharpen as records accumulate.

**Keywords:** invasive alien species; hotspot mapping; citizen science; camera traps; GRIIS; iNaturalist; USGS NAS; computer vision; decision support

## 1. Introduction

Biological invasions are among the main pressures on biodiversity, and the number of alien species keeps rising with no sign of saturation (Seebens et al. 2017). In protected areas the practical questions are local. Managers want to know which invasive species are present, where they concentrate, what they do to the native species around them, and what has been tried against them elsewhere.

Open data now answers part of each question. Community platforms such as iNaturalist and the Global Biodiversity Information Facility (GBIF) hold millions of georeferenced records. The Global Register of Introduced and Invasive Species (GRIIS) lists which species are alien and invasive in each country (Pagad et al. 2018). Curated databases such as the U.S. Geological Survey's Nonindigenous Aquatic Species (NAS) database record non-native species with their source, positional accuracy and establishment status. These sources are separate, they differ in quality, and community records favour accessible places and conspicuous species (Isaac et al. 2014). Evidence about effects sits in journals and species profiles that a park manager is unlikely to search record by record.

Deep learning has also changed how images are processed. Detectors such as MegaDetector separate animals, people and vehicles from empty camera-trap frames (Beery et al. 2019), classifiers identify species in the frames that remain (Norouzzadeh et al. 2018; Tabak et al. 2019), and self-supervised vision models make accurate small classifiers possible without a large training budget (Oquab et al. 2023).

We built an open pipeline that joins these ingredients for six national parks in India, Tanzania and the United States, and we ask four questions of the data it assembles:

1. Where do invasive-species records concentrate in each park?
2. Which species occur in those hotspots, and what do cited sources report about their effects on the local environment?
3. Do the records support statistical tests of an association between invader density and native richness, or of change in the invasive share over time?
4. How accurately can small classifiers on a frozen vision backbone identify invasive plants and camera-trap animals?

The contributions are: (i) a pipeline from five public sources into a spatial database with explicit, counted quality rules; (ii) a hotspot map with species cards that link each species in a hotspot to cited evidence; (iii) statistical layers that report when the data falls short of stated minimums, with the shortfall; (iv) CPU-only classifiers evaluated on photographers and cameras unseen in training; and (v) a deployment that runs on free tiers without a credit card. Section 2 describes the methods, Section 3 the results, Section 4 our observations and limitations, and Section 5 concludes.

## 2. Methods

### 2.1 Study areas

We chose six national parks (Table 1). Bandipur, Nagarahole and Mudumalai form a contiguous landscape in the Western Ghats of southern India where *Lantana camara* and *Senna spectabilis* invasions are widely reported. Serengeti in Tanzania is a savanna comparison. Everglades and Great Smoky Mountains in the United States add two ecosystems with dense records and well-studied invasions. Park boundaries come from OpenStreetMap (ODbL) and were checked for plausible area.

### 2.2 Data sources

**iNaturalist.** We retrieved research-grade observations inside each park's bounding box through the public API, in ascending identifier order so that each run resumes from the last identifier seen. Photos were used only when their licence allowed it.

**GBIF.** We retrieved preserved specimens, material samples and occurrences. GBIF republishes iNaturalist observations and holds hundreds of thousands of eBird records. We excluded both by default, to avoid counting iNaturalist records twice and to keep a large birds-only dataset out of a small database.

**USGS NAS.** For the two US parks we retrieved NAS occurrence records for the counties that contain each park (three in Florida, five across Tennessee and North Carolina), because the API has no bounding-box search. Each record carries a source type (literature, specimen or personal communication), a coordinate accuracy class (accurate, approximate, centroid) and an establishment status.

**GRIIS.** We imported the national checklists for India, Tanzania and the contiguous United States, which give each species' establishment means and whether it is invasive.

**Caltech Camera Traps.** One thousand photos from this public set (Beery et al. 2018), distributed through LILA BC, served to test the detector.

### 2.3 Record quality rules

Every record passes the same rules, and each refusal is counted by reason. A record must identify a species, carry a day-precision date not in the future, and have a position that is not deliberately obscured and is accurate to 2 km or better. Records with unknown accuracy are accepted. Captive or cultivated records are excluded, as are NAS records of failed introductions. A record must fall inside the park polygon, which we test with a bounding-box check followed by a spatial query. Records are keyed by source and external identifier, so repeated retrieval stores nothing twice. Species names are matched to the GBIF backbone taxonomy.

### 2.4 Invasive status of records

We classify a record by its species and the park's country. A record is *invasive* when GRIIS lists the species as alien and invasive for that country. It is *introduced* when GRIIS lists it as alien but not invasive. Species that GRIIS records as both native and alien in the same country (for example the chital, *Axis axis*, native on the Indian mainland and introduced to the Andaman Islands) are excluded from the invasive class, because the country-level list cannot say which applies at a park.

### 2.5 Hotspot mapping

We grouped invasive records into square cells of a chosen size between 0.005 and 0.5 degrees (about 0.5 to 50 km), performing the grouping in the database so that a client receives one row per occupied cell. The default size depends on the park's extent and its number of records, from 0.005 to 0.1 degrees. We summarise concentration as the share of a park's invasive records that fall in its busiest 10% of occupied cells. The dashboard shades cells by record count in five levels on a square-root scale, which keeps one very busy cell from reducing every other cell to the lightest shade.

### 2.6 Statistical analysis of impact

The analysis has three layers. The first reports cited findings (Section 2.7). The second asks whether native richness is lower where invaders are denser. For each 0.05-degree cell (about 5 km) we computed the share of records that are invasive and the native species richness rarefied to a common sample of 10 native records (Hurlbert 1971), which removes the dependence of richness on how often observers visited a cell. We then computed Spearman's rank correlation with a 95% percentile bootstrap interval from 2,000 resamples (Efron 1979). The third layer asks whether the invasive share of records is changing. We computed yearly invasive and native records per observation and tested each series with the Mann-Kendall test (Mann 1945) and the Theil-Sen slope (Sen 1968). Our implementations agree with SciPy (Virtanen et al. 2020), exactly for Kendall's tau and the slope and within 0.03 for the p-value. Across all parks the layers can run at most {{N_TESTS}} tests (one correlation for each park that meets the co-occurrence minimum, and one test for each of the two series in each park that meets the trend minimum), and we report unadjusted p-values beside a Bonferroni threshold of {{BONF}}.

Each layer runs only above a minimum amount of data. The co-occurrence layer needs at least 20 cells with 10 or more native records, of which at least 5 also hold invasive records. The trend layer needs at least 6 years with 15 or more observations each and at least 30 invasive records in the park. Below these minimums the output is the shortfall and nothing else.

An early-detection alert marks the first record of an invasive species in a park when that record is under a year old, the park had at least 50 observations before it, and no cited source already reports the species there.

### 2.7 Evidence base

We compiled findings on the effects of invasive species and management options from peer-reviewed studies, USGS NAS fact sheets and Global Invasive Species Database profiles. Each row carries a certainty label (experimental, observational, review, preliminary or unverified concern), a note on where the evidence was gathered, and verbatim quotes from the source. A script re-downloads every source and confirms that each quote appears there, tolerating only typography. A row without a verifiable quote is not admitted. A species photograph for each recorded invasive species comes from its iNaturalist taxon page and is kept only when its licence allows display with credit.

### 2.8 Computer-vision models

The detector is the MIT-licensed variant of MegaDetector V6 (YOLOv9-c), converted to ONNX and run on CPU. We checked the conversion against the reference implementation on 60 photos and evaluated the detector on 1,000 Caltech Camera Traps photos (720 with animals, 30 with vehicles, 250 verified empty) against human-drawn boxes.

The classifiers share one frozen DINOv2 ViT-S/14 backbone (Oquab et al. 2023). Each photo is embedded once, and a logistic-regression head is trained on the 768-number embedding. We chose the regularisation strength by validation log-loss and calibrated probabilities by temperature scaling (Guo et al. 2017). Below a threshold the classifier answers "unknown". Each threshold was fixed on validation data before the test set was scored: for the plant classifier, the lowest value at which each kind of non-target plant was called invasive no more than 5% of the time, and for the animal classifier the lowest value at which answers were at least 95% correct. The plant classifier has 15 classes: ten invasives, four native look-alikes drawn from iNaturalist's identification confusions and recorded as native to India, and a class of random other plants. It was trained on 1,407 and tested on 469 CC-licensed photos, with the split made by observer so that no photographer appears on both sides. The animal classifier has 13 North American classes cut from Caltech Camera Traps boxes (1,732 training and 565 test crops), split by camera location. We report 95% Wilson score intervals (Wilson 1927).

### 2.9 System and deployment

Scheduled GitHub Actions jobs ingest, detect and analyse every six hours and write to a Postgres database with PostGIS on Supabase's free plan. A static React dashboard on Vercel reads the database's REST API with a public key whose access the database restricts to reading. An optional FastAPI service on Render serves photo analysis. The database holds only boxes and source links for images, never the images, and people detected in photos are neither cropped nor classified. Ingestion is built for a remote database: progress is saved after every batch, and caps per park and source with a stop at 90% of the 500 MB budget keep the free plan from filling.

## 3. Results

All counts below are generated from the database by `scripts/dataset_summary.py` and `scripts/paper_tables.py`, and the tables in this section are refreshed from the same data. The snapshot date is given at the start of Section 3.1.

### 3.1 Data assembled

On {{SNAPSHOT}} the database held {{TOTAL_RECORDS}} records that passed the quality rules (Table 1): {{ITOTAL}} from iNaturalist, {{GTOTAL}} from GBIF and {{NTOTAL}} from the USGS NAS database. The database occupied {{DBMB}} MB of the 500 MB free-tier budget.

**Table 1.** Records that passed the quality rules, by park and source.

<!-- table:records -->
<!-- /table -->

Most fetched records were refused. Of the {{FETCHED_I}} iNaturalist records fetched, {{I_KEPT_PCT}}% were kept, against {{G_KEPT_PCT}}% of {{FETCHED_G}} GBIF records. The most complete USGS scan read {{FETCHED_N}} records and set {{REFUSED_N}} of them aside (Table 2). Records outside the park boundary but inside its search box were the largest single reason for iNaturalist and USGS, and imprecise positions came next. GBIF's main reason was a record that does not identify a species, and records without a full date were the second.

**Table 2.** Records refused, by reason and source. USGS figures come from the most complete single scan of each park's counties.

<!-- table:refused -->
<!-- /table -->

### 3.2 Invasive records

Invasive records are a small share of all records in the Indian parks, Serengeti and Great Smoky Mountains, and nearly half ({{EVER_SHARE}}%) of all records in the Everglades, where USGS supplies most records (Table 3).

**Table 3.** Invasive records and invasive species by park.

<!-- table:invasive -->
<!-- /table -->

The most recorded invasive species differ sharply between parks (Table 4). In the Everglades, USGS records of the Burmese python dominate. In the three Indian parks the most recorded species have between one and five records each, and *Lantana camara* and *Senna spectabilis*, the two invaders most often reported in these reserves, have {{LANTANA_RECORDS}} and {{SENNA_RECORDS}} records respectively across the three parks.

**Table 4.** The five most recorded invasive species in each park.

<!-- table:top_species -->
<!-- /table -->

### 3.3 Hotspots

Invasive records are unevenly spread inside every park that has enough of them to show a pattern (Table 5). In the Everglades, the busiest 10% of occupied squares hold {{HOT_EVER_SHARE}}% of the park's invasive records, and the busiest single square (about 2 km across) holds {{HOT_EVER_MAX}} of the {{HOT_EVER_N}} records (Figure 1). The Indian parks and Serengeti have too few invasive records for concentration to carry much meaning, and most of their occupied squares hold a single record. In Great Smoky Mountains, {{SMK_INV}} invasive records fall in {{SMK_CELLS_OCC}} squares, {{SMK_ONE}} of which hold one record.

**Table 5.** Concentration of invasive records in 0.02-degree squares (about 2 km).

<!-- table:concentration -->
<!-- /table -->

![Figure 1. Hotspots of invasive records in Everglades National Park. Squares are 0.02 degrees across and shaded by record count; the dashed line is the park boundary. Map data © OpenStreetMap contributors.](docs/figures/hotspots-everglades.png)

![Figure 2. Hotspots of invasive records in Great Smoky Mountains National Park, at the same square size.](docs/figures/hotspots-smokies.png)

![Figure 3. Hotspots of invasive records in Mudumalai National Park, at the same square size.](docs/figures/hotspots-mudumalai.png)

### 3.4 Whether the data supports the statistical layers

Three parks reached the minimum data for at least one statistic (Table 6). We report each result with its interval or p-value, and with the unadjusted p-values compared against the Bonferroni threshold of {{BONF}} for {{N_TESTS}} tests.

*Co-occurrence.* In Great Smoky Mountains, native species richness was positively correlated with the invasive share of records across {{SMOKIES_CELLS}} squares (Spearman's rho = {{SMOKIES_RHO}}, 95% bootstrap interval {{SMOKIES_LO}} to {{SMOKIES_HI}}), and the interval excludes zero. The direction is opposite to a reduction of native richness by invaders. In the Everglades the correlation across {{EVER_CELLS}} squares was also positive and its interval included zero (rho = {{EVER_RHO}}, {{EVER_RHO_LO}} to {{EVER_RHO_HI}}).

*Trend.* In the Everglades ({{EVER_YEARS}} years with data, {{EVER_Y0}} to {{EVER_Y1}}), the number of invasive records per observation rose (Kendall's tau = {{EVER_TAU}}, p = {{EVER_P}}, Theil-Sen slope +{{EVER_SLOPE}} per year), while the native share did not change significantly (tau = {{EVER_NTAU}}, p = {{EVER_NP}}). In Great Smoky Mountains ({{SMK_YEARS}} years, {{SMK_Y0}} to {{SMK_Y1}}) the invasive share did not change significantly (tau = {{SMK_TAU}}, p = {{SMK_P}}) and the native share fell (tau = {{SMK_NTAU}}, p = {{SMK_NP}}). In Mudumalai ({{MUD_YEARS}} years, {{MUD_Y0}} to {{MUD_Y1}}) neither series changed (invasive: tau = {{MUD_TAU}}, p = {{MUD_P}}; native: tau = {{MUD_NTAU}}, p = {{MUD_NP}}). Against the Bonferroni threshold of {{BONF}}, no trend result is significant.

**Table 6.** Readiness of each park for the statistical layers. "Ok" means the minimum data was met and a result was computed.

<!-- table:analysis -->
<!-- /table -->

### 3.5 Evidence on effects

The evidence base holds {{KB_FINDINGS}} cited findings and {{KB_PLAYBOOKS}} management options, rows backed by {{KB_QUOTES}} verbatim quotes from {{KB_SOURCES}} sources, all of which match their live sources. By certainty, the findings are {{KB_CERT}}. Cited findings cover few of the recorded species but cover most records in the Everglades (Table 7).

**Table 7.** Coverage of recorded invasive species by cited evidence.

<!-- table:coverage -->
<!-- /table -->

The Everglades result is a property of one species: the Burmese python has a peer-reviewed field study and a federal literature summary, and accounts for {{EVER_COVER_PCT}}% of the park's invasive records. In the three Indian parks, {{IN_FIND_MIN}} to {{IN_FIND_MAX}} of the {{IN_SPP_MIN}} to {{IN_SPP_MAX}} invasive species recorded in each park have a cited finding.

### 3.6 Alerts

The pipeline raised {{ALERT_COUNT}} early-detection alerts: {{ALERT_TEXT}}. Each rests on a handful of records and carries the caveat that a first record in our sources may follow the species' arrival by an unknown time.

### 3.7 Model performance

**Detector.** On 1,000 Caltech Camera Traps photos, MegaDetector found 92.6% of animal photos at a confidence threshold of 0.2, and 93.2% of the photos it flagged contained an animal. It flagged 17.5% of verified-empty photos, an upper bound on its false-alarm rate because many of those frames show partial or close-up animals that the label missed. The ONNX conversion matched the reference implementation on 60 photos with zero box or confidence difference.

**Invasive-plant classifier.** On 469 test photos by photographers absent from training, top-1 accuracy over 15 classes was 89.3% (majority-class baseline 19%). At the deployed threshold of 0.76 the classifier named 81.2% of photos and was right on 96.6% of those. It named 84.9% of invasive-species photos correctly (225 of 265; 95% interval 80.1 to 88.7%). No native look-alike was called invasive in 113 photos (95% interval 0 to 3.3%), and 6 of 91 random other plants were (6.6%; 3.1 to 13.7%), above the 5% target.

**Camera-trap animal classifier.** On 16 camera locations absent from training, top-1 accuracy over 13 North American classes was 77.2% (baseline 11%), against 81.6% when the same cameras appeared on both sides. At the deployed threshold of 0.77 it named 59% of crops and was right on 98.5% of those.

## 4. Observations

**The source shapes the picture.** The Everglades share of invasive records is {{EVER_SHARE}}%, against {{SHARE_LOW}} to {{SHARE_HIGH}}% elsewhere, and that gap says more about the sources than about the parks. The USGS database records non-native aquatic species and the reptiles and amphibians in its scope. Of the 8,294 Burmese python records it holds for the three Everglades counties (queried 8 October 2026), 7,531 are classed as derived from literature and 760 as museum specimens, so one report can contribute many records. A park's invasive share is therefore comparable with another park's only when both are drawn from the same kind of source. Within a source, differences are informative. Among the other five parks the invasive share ranged from {{SHARE_LOW}}% in {{SHARE_LOW_PARK}} to {{SHARE_HIGH}}% in {{SHARE_HIGH_PARK}}.

**Conspicuous weeds are under-recorded.** *Lantana camara* is reported to cover large areas of the Indian reserves. The three Indian parks hold {{LANTANA_RECORDS}} records of it, and *Senna spectabilis* has {{SENNA_RECORDS}}. People photograph flowers and animals more than common weeds, a known property of community data (Isaac et al. 2014). Counts from these sources describe where species were recorded, and they say little about how much ground a species covers. Any use of the hotspot maps for planning should take recording effort into account. In the Everglades, effort is itself uneven. At 2 km the shaded squares form lines across the park and not an even spread (Figure 1), which is consistent with recording that follows roads, trails and survey routes. We did not test this.

**The statistical results reflect where people go and which sources dominate.** The positive correlation in Great Smoky Mountains runs against what the literature on invader effects would lead one to expect. Apart from the aquatic parrot feather, its most recorded invasive species are widespread naturalised plants of fields and disturbed ground, such as red clover, wild carrot, orchard grass and ribwort plantain (Table 4), so the invasive share is plausibly highest where people walk and record. Native richness at a fixed sample size is also highest in well-visited, varied squares. Both measures plausibly rise with access, disturbance and habitat variety, and the correlation cannot separate them from an effect of invaders. We read it as a warning that raw co-occurrence in community data can point either way, and as no evidence that invaders raise or lower native richness.

The Everglades trend has a similar caveat. The rise in invasive records per observation spans a period in which the mix of sources changed: USGS supplied {{EVER_PRE_USGS}} of the {{EVER_PRE_TOTAL}} invasive records dated up to 2009, iNaturalist grew in the 2010s, and GBIF supplied {{EVER_LATE_GBIF}} of the {{EVER_LATE_TOTAL}} invasive records dated 2020 or later. Its p-value of {{EVER_P}} exceeds the Bonferroni threshold of {{BONF}}, so we do not treat it as established, and a rise in recorded presence is not a rise in abundance. The Smokies result for native records (tau = {{SMK_NTAU}}, p = {{SMK_NP}}) is also above the threshold. The layers report nothing for the parks below the minimums. For the three parks above them, the results mostly show the limits of record-based inference and give little information about effects of invaders.

**Evidence is concentrated on a few species.** Cited findings cover most Everglades records because one species dominates them, and they cover a minority of the species recorded elsewhere. Most findings are species-profile summaries ({{KB_REVIEW}} of {{KB_FINDINGS}}) and only {{KB_EXP}} is a controlled experiment. Several findings come from other regions, for example brown trout studies from Michigan applied to the Smokies, and each row says so. A manager reading a card should treat it as a pointer to the literature.

**The classifiers are accurate on their test sets and untested on ranger photos.** The plant classifier names invasive species correctly in about 85% of test photos and made no look-alike errors in 113 trials. On the test photos taken in India it named 88.1% of invasives correctly and called none of 120 non-target plants invasive. Its training photos are mostly naturalist close-ups, and the snapshots a ranger would take from a distance, in shade or of whole thickets follow another distribution that we have not measured. The animal classifier covers North American species and demonstrates transfer to unseen cameras (a 4.4 point cost) without covering Indian or African fauna. Outputs below a calibrated threshold return "unknown", which the dashboard shows as such.

**Design for free infrastructure shaped the engineering.** Running on free tiers, with scheduled jobs in the United States writing to a database in Asia, meant that each database round trip cost about 0.2 s. Resumable ingestion, batch-level duplicate and boundary checks, per-park caps and a stop at 90% of the database budget kept a first load of thousands of records inside the limits, and the whole database used {{DBMB}} MB of the 500 MB budget.

**Data licences constrain what can be published.** IUCN's terms prohibit republishing Red List data without written permission, so we hold its threat links in the database but hide them from the public interface, and this paper reports none of them. The USGS database asks authors to contact its team before publishing results that depend on it. We note that step as open (Section 6).

**Limitations.** Invasive status comes from country-level lists, which cannot say whether a species is invasive at a particular park. Records reflect observer effort, and we rarefy richness and limit analyses to minimum data but do not model effort explicitly. The study is a snapshot, the pipeline keeps adding records, and later runs will change the numbers. We have no abundance data and no live camera feed: the detector runs over archived images. The cited evidence is a curated selection and does not cover every species in the parks.

## 5. Conclusion

An open pipeline built entirely on free services can join community observations, specimen records, a curated federal database and country checklists into a spatial database for six national parks on three continents, apply counted quality rules, and show where invasive records concentrate together with what cited research reports about each species. Statistical estimates are now computable for three parks. They are confounded by recording effort and by changes in the mix of sources, none of the trend results survives a correction for multiple tests, and we do not read any of them as an effect of invaders. The next steps are a model of recording effort that can separate access from invasion, more field photos for the plant classifier, local labelled camera-trap data, and written permission from IUCN to publish its threat links, which would let the dashboard show which assessed native species named invaders threaten in these parks.

## 6. Data and code availability, and acknowledgements

The code, database migrations, curated evidence and this paper are at <https://github.com/tfthushaar/biodiversity> under the Apache-2.0 licence. A live dashboard is at <https://biodiversity-ecru.vercel.app>. Tables in this paper are produced by `scripts/dataset_summary.py` and `scripts/paper_tables.py` from the database, and the summary is stored at `docs/metrics/dataset_summary.json`. Model evaluations are in `docs/metrics/`.

We thank the iNaturalist community, GBIF and its publishers, the GRIIS contributors, OpenStreetMap contributors, the Labeled Information Library of Alexandria: Biology and Conservation (LILA BC) and Microsoft's AI for Good Lab, whose MegaDetector weights we used under the MIT licence. The U.S. Geological Survey Nonindigenous Aquatic Species Database is cited as: U.S. Geological Survey, Nonindigenous Aquatic Species Database, Gainesville, Florida, accessed 8 October 2026. The database requests that authors contact its team before publication; this contact has not yet been made.

## References

Beery, S., Morris, D. and Yang, S. (2019) Efficient pipeline for camera trap image review. arXiv:1907.06772.

Beery, S., Van Horn, G. and Perona, P. (2018) Recognition in Terra Incognita. In: Proceedings of the European Conference on Computer Vision (ECCV). arXiv:1807.04975.

Dorcas, M.E., Willson, J.D., Reed, R.N., Snow, R.W., Rochford, M.R., Miller, M.A. et al. (2012) Severe mammal declines coincide with proliferation of invasive Burmese pythons in Everglades National Park. Proceedings of the National Academy of Sciences 109(7): 2418-2422. doi:10.1073/pnas.1115226109

Efron, B. (1979) Bootstrap methods: another look at the jackknife. The Annals of Statistics 7(1): 1-26. doi:10.1214/aos/1176344552

GBIF.org (2026) GBIF Occurrence Data. https://www.gbif.org

Global Invasive Species Database (2026) Species profiles. IUCN SSC Invasive Species Specialist Group. https://www.iucngisd.org/gisd/

Guo, C., Pleiss, G., Sun, Y. and Weinberger, K.Q. (2017) On calibration of modern neural networks. In: Proceedings of the 34th International Conference on Machine Learning. arXiv:1706.04599.

Hernandez, A., Miao, Z., Vargas, L., Beery, S., Dodhia, R. et al. (2024) Pytorch-Wildlife: a collaborative deep learning framework for conservation. arXiv:2405.12930.

Hurlbert, S.H. (1971) The nonconcept of species diversity: a critique and alternative parameters. Ecology 52(4): 577-586. doi:10.2307/1934145

iNaturalist contributors (2026) iNaturalist research-grade observations. https://www.inaturalist.org

Isaac, N.J.B., van Strien, A.J., August, T.A., de Zeeuw, M.P. and Roy, D.B. (2014) Statistics for citizen science: extracting signals of change from noisy ecological data. Methods in Ecology and Evolution 5(10): 1052-1060. doi:10.1111/2041-210X.12254

LILA BC (2026) Labeled Information Library of Alexandria: Biology and Conservation. https://lila.science

Mann, H.B. (1945) Nonparametric tests against trend. Econometrica 13(3): 245-259. doi:10.2307/1907187

Miao, Z., Hernandez, A., Vargas, L.F., Chacon, I.D., Ruiz, D. et al. (2025) Pytorch-Wildlife model weights (MegaDetector V6). Zenodo. doi:10.5281/zenodo.15398270

Nerlekar, A.N., Mehta, N., Pokar, R., Bhagwat, M., Misher, C., Joshi, P. et al. (2021) Removal or utilization? Testing alternative approaches to the management of an invasive woody legume in an arid Indian grassland. Restoration Ecology 30(1): e13477. doi:10.1111/rec.13477

Norouzzadeh, M.S., Nguyen, A., Kosmala, M., Swanson, A., Palmer, M.S., Packer, C. et al. (2018) Automatically identifying, counting, and describing wild animals in camera-trap images with deep learning. Proceedings of the National Academy of Sciences 115(25): E5716-E5725. doi:10.1073/pnas.1719367115

OpenStreetMap contributors (2026) OpenStreetMap, licensed under the Open Database Licence. https://www.openstreetmap.org

Oquab, M., Darcet, T., Moutakanni, T., Vo, H., Szafraniec, M. et al. (2023) DINOv2: learning robust visual features without supervision. arXiv:2304.07193.

Pagad, S., Genovesi, P., Carnevali, L., Schigel, D. and McGeoch, M.A. (2018) Introducing the Global Register of Introduced and Invasive Species. Scientific Data 5: 170202. doi:10.1038/sdata.2017.202

Seebens, H., Blackburn, T.M., Dyer, E.E., Genovesi, P., Hulme, P.E., Jeschke, J.M. et al. (2017) No saturation in the accumulation of alien species worldwide. Nature Communications 8: 14435. doi:10.1038/ncomms14435

Sen, P.K. (1968) Estimates of the regression coefficient based on Kendall's tau. Journal of the American Statistical Association 63(324): 1379-1389. doi:10.1080/01621459.1968.10480934

Tabak, M.A., Norouzzadeh, M.S., Wolfson, D.W., Sweeney, S.J., Vercauteren, K.C., Snow, N.P. et al. (2019) Machine learning to classify animal species in camera trap images: applications in ecology. Methods in Ecology and Evolution 10(4): 585-590. doi:10.1111/2041-210X.13120

U.S. Geological Survey (2026) Nonindigenous Aquatic Species Database. Gainesville, Florida. https://nas.er.usgs.gov

Virtanen, P., Gommers, R., Oliphant, T.E., Haberland, M., Reddy, T., Cournapeau, D. et al. (2020) SciPy 1.0: fundamental algorithms for scientific computing in Python. Nature Methods 17(3): 261-272. doi:10.1038/s41592-019-0686-2

Wilson, E.B. (1927) Probable inference, the law of succession, and statistical inference. Journal of the American Statistical Association 22(158): 209-212. doi:10.1080/01621459.1927.10502953
