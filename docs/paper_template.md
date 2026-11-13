# Invasive-species hotspots in six national parks, and what peer-reviewed research reports about them

K N Thushaar Rangan, Yashas S, Amogh P A and G Ritzia

*Affiliations: to be added by the authors.*

Records and analyses are those held on {{SNAPSHOT}}. The evidence base was last checked on {{KB_VERIFIED}}. A dashboard with the maps and papers is at <https://biodiversity-ecru.vercel.app>.

## Abstract

Park managers need to know where invasive species concentrate and what they do to native species, but the open records that could answer this are scattered, uneven in quality and seldom linked to the research on effects. We combined iNaturalist observations, GBIF specimen records, curated USGS records of non-native aquatic species and GRIIS invasive-status checklists for six national parks in India, Tanzania and the United States, and linked species to peer-reviewed papers. A species counts as invasive in a park only when GRIIS lists it as alien and invasive in the park's country and a peer-reviewed paper in our evidence base reports on it. After explicit quality rules the study held {{TOTAL_RECORDS}} records, of which {{INV_TOTAL}} are records of {{INV_SPECIES_TOTAL}} such invasive species. We set aside {{PRUNED_RECORDS}} records of {{PRUNED_SPECIES}} further species that GRIIS lists as invasive and for which we found no paper. Invasive records are concentrated in the Everglades, where the busiest 10% of 2 km squares hold {{HOT_EVER_SHARE}}% of them. They are sparse elsewhere: {{IN_REC_MIN}} to {{IN_REC_MAX}} in each Indian park, {{SMK_INV}} in Great Smoky Mountains and none in Serengeti. Two parks had enough data for statistical tests. In Great Smoky Mountains native richness correlated positively with invasive share across {{SMOKIES_CELLS}} squares, {{SMK_CELLS_WITH}} of which held invasive records (Spearman's rho = {{SMOKIES_RHO}}, 95% bootstrap interval {{SMOKIES_LO}} to {{SMOKIES_HI}}), which is consistent with both measures being higher in accessible, disturbed and heavily visited squares. In the Everglades the number of invasive records per observation rose over {{EVER_YEARS}} years (Kendall's tau = {{EVER_TAU}}, {{EVER_P}}), a result that survives a correction for the {{N_TESTS}} tests we ran and that follows the mix of sources: one species supplies {{EVER_TOP_PCT}}% of the invasive records, one database supplies {{EVER_USGS_PCT}}%, and the park's iNaturalist records end in {{EVER_INAT_LAST}}. Findings on effects and management come only from journal articles: {{KB_PAPERS}} peer-reviewed papers published {{KB_Y0}} to {{KB_Y1}} support {{KB_FINDINGS}} findings and {{KB_MANAGEMENT}} management rows for {{KB_SPECIES}} species, and every quotation was checked against the abstract of its paper. Classifiers on a frozen DINOv2 backbone named invasive plants correctly in 84.9% of test photos by photographers unseen in training and made no native look-alike error in 113 trials, and the MegaDetector V6 detector found 92.6% of animal photos on a held-out camera-trap sample. Invasive counts reflect recording effort as well as presence, a species without a paper in the evidence base is not recorded, the iNaturalist records of three parks end early, and the statistical estimates are confounded by effort and source.

**Keywords:** invasive alien species; hotspot mapping; citizen science; camera traps; GRIIS; iNaturalist; USGS NAS; computer vision; decision support

## 1. Introduction

Biological invasions are among the main pressures on biodiversity, and the number of alien species keeps rising with no sign of saturation (Seebens et al. 2017). In protected areas the practical questions are local. Managers want to know which invasive species are present, where they concentrate, what they do to the native species around them, and what has been tried against them elsewhere.

Open data now answers part of each question. Community platforms such as iNaturalist and the Global Biodiversity Information Facility (GBIF) hold millions of georeferenced records. The Global Register of Introduced and Invasive Species (GRIIS) lists which species are alien and invasive in each country (Pagad et al. 2018). Curated databases such as the U.S. Geological Survey's Nonindigenous Aquatic Species (NAS) database record non-native species with their source, positional accuracy and establishment status. These sources are separate, they differ in quality, and opportunistic records are relatively unstructured, with recorder activity that varies (Isaac et al. 2014). Evidence about effects sits in journals that a park manager is unlikely to search record by record.

Deep learning has also changed how images are processed. Detectors such as MegaDetector have been tested at finding humans and animals in camera-trap images against manual classification (Fennell et al. 2022), deep learning is used to detect objects such as animals, humans and vehicles and to classify species (Vélez et al. 2022), and classifiers identify species in camera-trap images (Norouzzadeh et al. 2018; Tabak et al. 2019). We test whether a frozen self-supervised vision backbone, DINOv2, can serve as the base for small classifiers of invasive plants and camera-trap animals.

We joined these ingredients for six national parks in India, Tanzania and the United States, and ask four questions of the data:

1. Where do invasive-species records concentrate in each park?
2. Which species occur in those hotspots, and what do peer-reviewed papers report about their effects on the local environment?
3. Do the records support statistical tests of an association between invader density and native richness, or of change in the invasive share over time?
4. How accurately can small classifiers on a frozen vision backbone identify invasive plants and camera-trap animals?

Our contributions are: (i) a record set drawn from four public sources under explicit, counted quality rules; (ii) hotspot maps that link each species to the papers that report on it; (iii) statistical tests that are run only when the data meets stated minimums, and that report the shortfall otherwise; and (iv) CPU-only classifiers evaluated on photographers and cameras unseen in training. Section 2 describes the data and methods, Section 3 the results, Section 4 discusses them and their limits, and Section 5 concludes.

## 2. Data and methods

### 2.1 Study areas

We chose six national parks (Table 1). Bandipur, Nagarahole and Mudumalai form a contiguous landscape in the Western Ghats of southern India. Serengeti in Tanzania is a savanna comparison. Everglades and Great Smoky Mountains in the United States add two ecosystems with dense records and many studies of invasions. Park boundaries come from OpenStreetMap (ODbL) and were checked for plausible area.

### 2.2 Data sources

**iNaturalist.** We retrieved research-grade observations inside each park's bounding box through the public API, oldest first, and stored at most {{INAT_CAP}} per park. Three parks reached that limit, so their iNaturalist records stop early: the Everglades in {{EVER_INAT_LAST}}, Great Smoky Mountains in {{SMK_INAT_LAST}} and Serengeti in {{SER_INAT_LAST}}. Photos were used only when their licence allowed it.

**GBIF.** We retrieved preserved specimens only. A specimen traces to a collection in a museum or herbarium. Human observations, machine observations, material samples and records of unspecified origin do not, and GBIF also republishes iNaturalist observations, which would be counted twice. An earlier version of our query took every kind of record, and we removed the {{GBIF_PRUNED}} of the {{GBIF_HELD}} GBIF records it had stored that were not specimens.

**USGS NAS.** For the two US parks we retrieved NAS occurrence records for the counties that contain each park (three in Florida, five across Tennessee and North Carolina), because the API has no bounding-box search. Each record carries a source type (literature, specimen or personal communication), a coordinate accuracy class (accurate, approximate, centroid) and an establishment status.

**GRIIS.** We used the national checklists for India, Tanzania and the contiguous United States, which give each species' establishment means and whether it is invasive.

**Caltech Camera Traps.** One thousand photos from this public set (Beery et al. 2018), distributed through LILA BC, served to test the detector.

### 2.3 Record quality rules

Every record passes the same rules, and each refusal is counted by reason. A record must identify a species, carry a day-precision date that is not in the future, and have a position that is not deliberately obscured and is accurate to 2 km or better. Records with unknown accuracy are accepted. Captive or cultivated records are excluded, as are NAS records of failed introductions. A record must fall inside the park boundary, which we test with a bounding-box check followed by an exact polygon test. Duplicate records are removed. Species names are matched to the GBIF backbone taxonomy. A record of an invasive species is stored only when a peer-reviewed paper in the evidence base reports on that species (Section 2.7). When we applied this rule to the records already stored, we removed {{PRUNED_RECORDS}} records of {{PRUNED_SPECIES}} species.

### 2.4 Invasive status of records

We classify a record by its species and the park's country. A record is *invasive* when GRIIS lists the species as alien and invasive for that country and the evidence base holds a peer-reviewed paper on the species. It is *introduced* when GRIIS lists it as alien but not invasive. Species that GRIIS records as both native and alien in the same country (for example the chital, *Axis axis*) are excluded from the invasive class, because a country-level list cannot say which applies at a park.

### 2.5 Hotspot mapping

We grouped invasive records into square cells 2 km on a side. A cell is sized from the park's latitude, so that it is as wide as it is tall on the ground. We summarise concentration as the share of a park's invasive records that fall in its busiest 10% of occupied cells, and we report the number of records in the busiest cell. Maps shade cells by record count in five levels on a square-root scale, which keeps one very busy cell from reducing every other cell to the lightest shade.

### 2.6 Statistical analysis of impact

The analysis has two layers beyond the published evidence (Section 2.7). The first asks whether native richness is lower where invaders are denser. For each 0.05-degree cell (about 5 km) we computed the share of records that are invasive and the native species richness rarefied to a common sample of 10 native records (Hurlbert 1971), which removes the dependence of richness on how often observers visited a cell. We then computed Spearman's rank correlation with a 95% percentile bootstrap interval from 2,000 resamples (Efron 1979). The second layer asks whether the invasive share of records is changing. We computed yearly invasive and native records per observation and tested each series with the Mann-Kendall test (Mann 1945) and the Theil-Sen slope (Sen 1968). Our implementations agree with SciPy (Virtanen et al. 2020), exactly for Kendall's tau and the slope and within 0.03 for the p-value. In this study {{N_TESTS}} tests met their minimums and were run: one correlation for each of the two parks that met the co-occurrence minimum, and one test for each of the two series in the one park that met the trend minimum. We report unadjusted p-values beside a Bonferroni threshold of {{BONF}}. The two series of a park share their denominator and are correlated, so the threshold is conservative.

Each layer runs only above a minimum amount of data. The co-occurrence layer needs at least 20 cells with 10 or more native records, of which at least 5 also hold invasive records. The trend layer needs at least 6 years with 15 or more observations each and at least 30 invasive records in the park. Below these minimums the output is the shortfall and nothing else.

### 2.7 Evidence from published research

Findings on the effects of invasive species and on management options come from peer-reviewed journal articles only. We did not use news, reports, web pages, species profiles, fact sheets or preprints. A paper entered the evidence base when it was a journal article with a DOI, published in {{KB_Y0}} or later, whose Crossref and OpenAlex records matched its title, journal, year and first author and showed no retraction. Each row of the evidence base restates the result of one paper, with the setting of the study (place, sample and period) and its design: controlled experiment, field study, review of studies or model projection. Each row is supported by verbatim quotations from the abstract of the paper, and a program confirmed that every quotation appears there, ignoring typography only. We made no ratings of our own, such as how well a method works or what it costs, because no paper states them in general. Null and negative results were recorded alongside positive ones. A species is reported with findings only when a paper backs it.

### 2.8 Computer-vision models

The detector is the MIT-licensed variant of MegaDetector V6 (YOLOv9-c), run on an ordinary CPU. We checked our conversion of the model against the reference implementation on 60 photos and evaluated the detector on 1,000 Caltech Camera Traps photos (720 with animals, 30 with vehicles, 250 verified empty) against human-drawn boxes.

The classifiers share one frozen DINOv2 ViT-S/14 backbone. Each photo is embedded once, and a logistic-regression head is trained on the 768-number embedding. We chose the regularisation strength by validation log-loss and calibrated probabilities by temperature scaling, which divides the scores by one number fitted on validation data. Below a threshold the classifier answers "unknown". Each threshold was fixed on validation data before the test set was scored: for the plant classifier, the lowest value at which each kind of non-target plant was called invasive no more than 5% of the time, and for the animal classifier the lowest value at which answers were at least 95% correct. The plant classifier has 15 classes: ten invasives, four native look-alikes drawn from iNaturalist's identification confusions and recorded as native to India, and a class of random other plants. It was trained on 1,407 and tested on 469 CC-licensed photos, with the split made by observer so that no photographer appears on both sides. The animal classifier has 13 North American classes cut from Caltech Camera Traps boxes (1,732 training and 565 test crops), split by camera location. We report 95% Wilson score intervals (Wilson 1927).

### 2.9 Data handling

We kept only detection boxes and source links for images, never the images. People detected in photos were neither cropped nor classified.

## 3. Results

All counts in this section are from the study database on {{SNAPSHOT}}.

### 3.1 Data assembled

The database held {{TOTAL_RECORDS}} records that passed the quality rules (Table 1): {{ITOTAL}} from iNaturalist, {{GTOTAL}} from GBIF and {{NTOTAL}} from the USGS NAS database.

**Table 1.** Records that passed the quality rules, by park and source.

<!-- table:records -->
<!-- /table -->

Most fetched records were refused. Of the {{FETCHED_I}} iNaturalist records fetched, {{I_KEPT_PCT}}% were kept, against {{G_KEPT_PCT}}% of {{FETCHED_G}} GBIF records. The GBIF count includes early runs made before we limited the query to specimens. The most complete USGS scan read {{FETCHED_N}} records and set {{REFUSED_N}} of them aside (Table 2). The largest reasons were, for iNaturalist, {{REASONS_I}}; for GBIF, {{REASONS_G}}; and for USGS, {{REASONS_N}}.

**Table 2.** Records refused, by reason and source. USGS figures come from the most complete single scan of each park's counties.

<!-- table:refused -->
<!-- /table -->

### 3.2 Invasive records

Invasive records are a small share of all records in every park except the Everglades, where they make up {{EVER_SHARE}}% (Table 3). USGS supplies {{EVER_USGS_PCT}}% of the Everglades invasive records. Serengeti has none.

**Table 3.** Invasive records and invasive species by park.

<!-- table:invasive -->
<!-- /table -->

The most recorded invasive species differ sharply between parks (Table 4). In the Everglades, *{{EVER_TOP_SPECIES}}* ({{EVER_TOP_COMMON}}) makes up {{EVER_TOP_PCT}}% of the invasive records. In the three Indian parks no species has more than {{IN_SPECIES_MAX}} records. *Lantana camara* and *Senna spectabilis* are both described as invaders of Indian forests (Negi et al. 2019; Bargavi et al. 2025). Across the three parks the study holds {{LANTANA_PHRASE}} of the first and {{SENNA_PHRASE}} of the second.

**Table 4.** The five most recorded invasive species in each park.

<!-- table:top_species -->
<!-- /table -->

### 3.3 Hotspots

Only the Everglades has enough invasive records for concentration to carry much meaning (Table 5). There the busiest 10% of occupied squares hold {{HOT_EVER_SHARE}}% of the park's invasive records, and the busiest single square (2 km across) holds {{HOT_EVER_MAX}} of the {{HOT_EVER_N}} records (Figure 1). The Indian parks hold {{IN_REC_MIN}} to {{IN_REC_MAX}} invasive records each and Serengeti holds none. In Great Smoky Mountains, {{SMK_INV}} invasive records fall in {{SMK_CELLS_OCC}} squares, {{SMK_ONE}} of which hold one record.

**Table 5.** Concentration of invasive records in squares 2 km on a side.

<!-- table:concentration -->
<!-- /table -->

![Figure 1. Hotspots of invasive records in Everglades National Park. Squares are 2 km across and shaded by record count; the dashed line is the park boundary. Map data © OpenStreetMap contributors.](docs/figures/hotspots-everglades.png)

![Figure 2. Hotspots of invasive records in Great Smoky Mountains National Park, at the same square size.](docs/figures/hotspots-smokies.png)

![Figure 3. Hotspots of invasive records in Mudumalai National Park, at the same square size.](docs/figures/hotspots-mudumalai.png)

### 3.4 Whether the data supports the statistical tests

Two parks reached the minimum data for at least one statistic (Table 6). We report each result with its interval or p-value, and compare the p-values with the Bonferroni threshold of {{BONF}} for {{N_TESTS}} tests.

*Co-occurrence.* In Great Smoky Mountains, native species richness was positively correlated with the invasive share of records across {{SMOKIES_CELLS}} squares, {{SMK_CELLS_WITH}} of which held invasive records (Spearman's rho = {{SMOKIES_RHO}}, 95% bootstrap interval {{SMOKIES_LO}} to {{SMOKIES_HI}}), and the interval excludes zero. The direction is opposite to a reduction of native richness by invaders. In the Everglades the correlation across {{EVER_CELLS}} squares, {{EVER_CELLS_WITH}} of which held invasive records, was also positive and its interval included zero (rho = {{EVER_RHO}}, {{EVER_RHO_LO}} to {{EVER_RHO_HI}}).

*Trend.* Only the Everglades held the {{REQUIRED_INV}} invasive records the trend test needs. In the Everglades ({{EVER_YEARS}} years with data, {{EVER_Y0}} to {{EVER_Y1}}), the number of invasive records per observation rose (Kendall's tau = {{EVER_TAU}}, {{EVER_P}}, Theil-Sen slope +{{EVER_SLOPE}} per year) and the number of native records per observation fell (tau = {{EVER_NTAU}}, {{EVER_NP}}). Both p-values are below the Bonferroni threshold of {{BONF}}. The two series share a denominator, so a rise in the invasive share leaves less room for the native share, and the second result adds little to the first. No other park held more than {{OTHER_INV_MAX}} invasive records, so the trend test did not run for them.

**Table 6.** Readiness of each park for the statistical tests. "Ok" means the minimum data was met and a result was computed.

<!-- table:analysis -->
<!-- /table -->

### 3.5 Published evidence on the species

The evidence base holds {{KB_FINDINGS}} findings ({{KB_FINDING_DESIGNS}}) and {{KB_MANAGEMENT}} management rows ({{KB_MANAGEMENT_DESIGNS}}), supported by {{KB_QUOTES}} quotations from {{KB_PAPERS}} papers in {{KB_JOURNALS}} journals, published {{KB_Y0}} to {{KB_Y1}}. They cover {{KB_SPECIES}} species (Table 7). All {{INV_SPECIES_TOTAL}} invasive species recorded in the parks on {{SNAPSHOT}} are among them, and the other {{KB_NOT_RECORDED}} have no record in a park.

**Table 7.** Species with at least one peer-reviewed paper in the evidence base. Study designs count the findings and management rows of each species.

<!-- table:evidence -->
<!-- /table -->

The papers describe a range of effects and of results. In the Everglades, mammal declines have been linked to the spread of the Burmese python (Willson 2017; Hoyer et al. 2017). In India, a review reports that *Lantana camara* has invaded vast tracts of forest and has potentially altered biodiversity, landscape ecology and ecosystem services (Negi et al. 2019), and a study in central India found lower tree species richness in invaded sites (Lone et al. 2025). Management results include null findings, for example that scent lures did not raise python detections (Miller et al. 2025) and that short-term clearing of *Lantana* in a Ugandan rainforest did not promote tree establishment (Barahukwa et al. 2023). A four-year randomised experiment in the Banni grasslands of Gujarat found that mechanical removal of *Prosopis juliflora* tripled native herb richness while lopping did not differ from the control (Nerlekar et al. 2021). Each row states the setting of its study, and several come from other regions than the parks.

### 3.6 Model performance

**Detector.** On 1,000 Caltech Camera Traps photos, MegaDetector found 92.6% of animal photos at a confidence threshold of 0.2, and 93.2% of the photos it flagged contained an animal. It flagged 17.5% of verified-empty photos, an upper bound on its false-alarm rate because many of those frames show partial or close-up animals that the label missed. Our converted model matched the reference implementation on 60 photos with zero box or confidence difference.

**Invasive-plant classifier.** On 469 test photos by photographers absent from training, top-1 accuracy over 15 classes was 89.3% (majority-class baseline 19%). At the deployed threshold of 0.76 the classifier named 81.2% of photos and was right on 96.6% of those. It named 84.9% of invasive-species photos correctly (225 of 265; 95% interval 80.1 to 88.7%). No native look-alike was called invasive in 113 photos (95% interval 0 to 3.3%), and 6 of 91 random other plants were (6.6%; 3.1 to 13.7%), above the 5% target.

**Camera-trap animal classifier.** On 16 camera locations absent from training, top-1 accuracy over 13 North American classes was 77.2% (baseline 11%), against 81.6% when the same cameras appeared on both sides. At the deployed threshold of 0.77 it named 59% of crops and was right on 98.5% of those.

## 4. Discussion

**The source shapes the picture.** The Everglades share of invasive records is {{EVER_SHARE}}%, and USGS supplies {{EVER_USGS_PCT}}% of those records. The USGS database records non-native aquatic species and the reptiles and amphibians in its scope. Of the {{PY_TOTAL}} Burmese python records it holds for the three Everglades counties (queried {{PY_DATE}}), {{PY_LITERATURE}} are classed as derived from literature and {{PY_SPECIMEN}} as specimens, so one report can contribute many records. A park's invasive share is therefore comparable with another park's only when both are drawn from the same kind of source. The share also counts only the {{INV_SPECIES_TOTAL}} species that the evidence base covers, so it is lower than the share of records of every species GRIIS lists as invasive. Among the other five parks the invasive share ranged from {{SHARE_LOW}}% in {{SHARE_LOW_PARK}} to {{SHARE_HIGH}}% in {{SHARE_HIGH_PARK}}.

**Three parks lack recent iNaturalist records.** We read iNaturalist oldest first and stored at most {{INAT_CAP}} records per park. The Everglades, Great Smoky Mountains and Serengeti reached that limit, so their iNaturalist records end in {{EVER_INAT_LAST}}, {{SMK_INAT_LAST}} and {{SER_INAT_LAST}}. For these parks the maps and counts describe the earlier years better than the recent ones, and a recent record is measured against a smaller and different set of records than an earlier one. The three Indian parks are below the limit, and their iNaturalist records run to at least {{IN_INAT_LAST}}.

**Conspicuous weeds are under-recorded.** *Lantana camara* is described as having invaded vast tracts of Indian forest and pasture (Negi et al. 2019), and *Senna spectabilis* as a widespread invader in India (Bargavi et al. 2025). The three Indian parks hold {{LANTANA_PHRASE}} of the first and {{SENNA_PHRASE}} of the second. Observers may photograph flowers and animals more often than common weeds, and community records vary with recorder activity (Isaac et al. 2014). We did not test whether this explains the few records of these weeds. Counts from these sources describe where species were recorded, and they say little about how much ground a species covers. Any use of the hotspot maps for planning should take recording effort into account. In the Everglades, effort is itself uneven. At 2 km the shaded squares form lines across the park (Figure 1), which is consistent with recording that follows roads, trails and survey routes. We did not test this.

**The statistical results reflect where people go and which sources dominate.** The positive correlation in Great Smoky Mountains runs against what studies of invader effects would lead one to expect, for example lower richness in invaded forest (Lone et al. 2025). It rests on {{SMK_INV}} invasive records in {{SMK_CELLS_WITH}} squares. Native richness at a fixed sample size is highest in well-visited, varied squares, so both measures plausibly rise with access, disturbance and habitat variety. The correlation cannot separate those influences from an effect of invaders, and we did not test them. We read it as a warning that raw co-occurrence in community data can point either way, and as no evidence that invaders raise or lower native richness.

The Everglades trend is the clearest statistical result and the least informative about invaders. Its p-value is far below the Bonferroni threshold of {{BONF}}, and the records offer three reasons for a rise that involves no change in invasion. First, one species and one source dominate: *{{EVER_TOP_SPECIES}}* makes up {{EVER_TOP_PCT}}% of the invasive records and USGS supplies {{EVER_USGS_PCT}}%. Second, the mix of sources changed. USGS supplied {{EVER_PRE_USGS}} invasive records dated up to 2009 and {{EVER_LATE_USGS}} dated 2020 or later. Across all Everglades records, USGS supplied {{EVER_USGS_ALL_PRE}}%, {{EVER_USGS_ALL_MID}}% and {{EVER_USGS_ALL_LATE}}% in the periods up to 2009, 2010 to 2019 and 2020 on, and iNaturalist supplied {{EVER_INAT_PRE}}%, {{EVER_INAT_MID}}% and {{EVER_INAT_LATE}}%. Third, the invasive share of all records was {{EVER_SHARE_PRE}}%, {{EVER_SHARE_MID}}% and {{EVER_SHARE_LATE}}% in those periods, so the rise sits in the period for which the study holds no iNaturalist records. The records cannot separate a real spread of invaders from a change in who recorded what, and a rise in recorded presence says nothing about abundance. The fall in native records per observation partly mirrors the rise (Section 3.4). The tests report nothing for the parks below the minimums. For the two parks above them, the results mostly show the limits of record-based inference and give little information about effects of invaders.

**The evidence base decides which species appear.** A species is recorded as invasive only when a peer-reviewed paper in the evidence base reports on it, so every invasive species in the study has papers behind it and the study can state what they report. The cost is coverage. Applying the rule removed {{PRUNED_RECORDS}} records of {{PRUNED_SPECIES}} species that GRIIS lists as invasive, {{PRUNED_EVER}} of them in the Everglades and {{PRUNED_SMOKIES}} in Great Smoky Mountains, so the maps show a narrower picture than the GRIIS lists, and a species absent from them may still be spreading. The evidence base covers {{KB_SPECIES}} species, and {{KB_NOT_RECORDED}} of them have no record in a park. The papers themselves vary in strength. The {{KB_FINDINGS}} findings rest on {{KB_FINDING_DESIGNS}}, and only the controlled experiments and the reviews support general statements. Several studies took place in other regions, and a manager reading a result should read the setting stated beside it.

**The classifiers are accurate on their test sets and untested on ranger photos.** The plant classifier names invasive species correctly in about 85% of test photos and made no look-alike errors in 113 trials. On the test photos taken in India it named 88.1% of invasives correctly and called none of 120 non-target plants invasive. Its training photos are mostly naturalist close-ups, and the snapshots a ranger would take from a distance, in shade or of whole thickets follow another distribution that we have not measured. The animal classifier covers North American species and demonstrates transfer to unseen cameras (a 4.4 point cost) without covering Indian or African fauna. Outputs below a calibrated threshold return "unknown".

**Limitations.** Invasive status comes from country-level lists, which cannot say whether a species is invasive at a particular park. Records reflect observer effort, and we rarefy richness and limit analyses to minimum data but do not model effort explicitly. Three parks lack recent iNaturalist records (above). The study is a snapshot of records that keep accumulating, and later data will change the numbers. We have no abundance data and no live camera feed: the detector runs over archived images.

## 5. Conclusion

Four public sources and country checklists can be combined for six national parks on three continents, filtered by counted quality rules, and used to show where invasive records concentrate together with what peer-reviewed research reports about each species. The study records only species that a paper backs, which leaves {{INV_TOTAL}} invasive records of {{INV_SPECIES_TOTAL}} species and sets aside {{PRUNED_RECORDS}} records of {{PRUNED_SPECIES}} more. Statistical estimates are computable for two parks. They are confounded by recording effort, by one dominant species and source in the Everglades, and by iNaturalist records that end early in three parks, and we do not read any of them as an effect of invaders. The first needs are a wider evidence base, so that more of the species GRIIS lists can be recorded, and iNaturalist records for the years after the limit in the three parks. The next steps are a model of recording effort that can separate access from invasion, more field photos for the plant classifier, local labelled camera-trap data, and peer-reviewed studies of the species most recorded in the Indian parks.

## 6. Data availability and acknowledgements

The code, the evidence base and this paper are at <https://github.com/tfthushaar/biodiversity> under the Apache-2.0 licence, and the maps and papers are at <https://biodiversity-ecru.vercel.app>. The figures and tables in this paper were generated from the study database as it stood on {{SNAPSHOT}}, and the summary is stored in the repository. The dashboard reads the same database, which keeps growing, so its counts will differ from those here as records are added.

We thank the iNaturalist community, GBIF and its publishers, the GRIIS contributors, OpenStreetMap contributors, the Labeled Information Library of Alexandria: Biology and Conservation (LILA BC) and Microsoft's AI for Good Lab, whose MegaDetector weights we used under the MIT licence. The U.S. Geological Survey Nonindigenous Aquatic Species Database is cited as: U.S. Geological Survey, Nonindigenous Aquatic Species Database, Gainesville, Florida, accessed in October and November 2026. The database requests that authors contact its team before publication, and we have not yet done so.

## References

{{REFERENCES}}

### Papers in the evidence base

Each paper below supports at least one finding or management row, and each quotation from it was checked against its abstract.

{{KB_REFERENCES}}
