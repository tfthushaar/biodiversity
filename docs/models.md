# Models

## Detector: MegaDetector V6, `MDV6-mit-yolov9-c`

Finds **animals, people and vehicles** in camera-trap images, with a box and confidence for each.
It does not name species (that is the classifier's job, Phase 5).

| | |
|---|---|
| Source | Microsoft AI for Good Lab, <https://zenodo.org/records/15398270> |
| Architecture | YOLOv9-c, 9.7M parameters, 640 px input |
| Licence | **MIT** (weights and the library used to run them) |
| Our file | ONNX, 29.1 MB, CPU only, no PyTorch at runtime |
| Checkpoint MD5 | `d8626ba22fccbd9c520e0deb19d721f7` (verified before loading) |
| ONNX SHA-256 | `9dae0ced1e1a3210ebd6a835303d7a6ffc671f3cd15a51cbcb8adaedc238ddbe` |

**Why this variant.** Of the nine V6 variants, five are AGPL-3.0 (built on Ultralytics), which
would constrain how this project can be licensed and deployed; two are Apache-2.0 (RT-DETR, much
larger) and two are MIT. This is the smaller MIT one, small enough for a free CPU runner. A pre-built ONNX of the
AGPL variant exists on Zenodo; it is deliberately not used.

### How the ONNX was made

Done once, in a throwaway environment (torch and the MIT `yolo` library), never at runtime.

```bash
python scripts/export_megadetector_onnx.py --ckpt MDV6-mit-yolov9-c.ckpt \
    --config config_v9s.yaml --out MDV6-mit-yolov9-c.onnx
```

The script refuses to load a checkpoint whose MD5 differs from Zenodo's (loading unpickles it, and
unpickling can run code), checks that **every** weight tensor loaded (the library only warns about
mismatches, which would leave layers randomly initialised), and checks the ONNX output against
PyTorch at a batch size it was not traced with. Result: logits agree to 1.5e-4, boxes to 6e-4.

On Windows use a short path (e.g. `C:\bdx`) for the environment: torch's package tree exceeds
the 260-character path limit under deep directories.

### Verified against the reference implementation

`scripts/verify_megadetector.py` runs our ONNX + NumPy pipeline and the reference implementation
on the same photos. On 60 real images: **59 detections each, all matched, box disagreement
0.0000, confidence difference 0.0000.**

The only difference is deliberate. The network sometimes fires inside the grey letterbox
padding, giving boxes lying wholly or mostly outside the real image (11 of 70 reference detections
here, e.g. a "person" at `y = -0.19 .. -0.00`). We drop any detection with under half its area
inside the image (`MIN_VISIBLE_FRACTION`).

## Accuracy

Evaluated on **1,000 real Caltech Camera Traps photos** (720 with animals, 30 with vehicles, 250
verified empty, spread over many camera locations) against human-drawn boxes. Full results:
[metrics/megadetector_caltech.json](metrics/megadetector_caltech.json). Reproduce with
`scripts/fetch_lila_sample.py` then `scripts/eval_megadetector.py`.

| Confidence threshold | 0.2 | 0.5 | 0.7 |
|---|---:|---:|---:|
| Animal images found (recall) | 92.6% | 78.6% | 66.7% |
| Flagged images that had an animal (precision) | 93.2% | 95.4% | 97.4% |
| Empty images flagged (false alarms) | 17.5% | 9.6% | 4.6% |
| Box recall, IoU >= 0.5 | 81.1% | 72.1% | 63.1% |
| Box precision, IoU >= 0.5 | 79.3% | 88.5% | 94.0% |

Vehicles: 96.7% found, 83% precision at 0.2.

Species it finds least often (recall at 0.2): birds 81.6% (n=38), squirrels 87.5%, rabbits 88.1%,
opossums 90.3%. Deer (96%), raccoons (97%), cats (95%) and dogs (100%) are found most reliably; coyotes and bobcats about 92%. Counts for lizards (2), foxes (8) and badgers (1) are too small to read anything into.

### Read these numbers with care

- **The false-alarm rate is an upper bound, not the model's error rate.** Looking at the most
  confident "false alarms" on verified-empty frames, most are real animals the sequence-level label
  missed: a fur close-up against the lens, legs, a raccoon in a corner, a faint silhouette. A
  minority are genuine errors (rocks). Counting them all as mistakes overstates the problem.
- **Box precision is understated too.** Caltech boxes cover only the one labelled species per
  image, so correctly finding a second animal counts as a false positive.
- **Two evaluation mistakes were made and fixed along the way,** both from trusting ground truth
  I had not inspected, and both made the detector look far worse than it is (a 74%, then a 49%,
  false-alarm rate). Images with *no annotation* are unlabelled, not empty; and images the box file
  marks `empty` *with a box drawn on them* are ambiguous partial animals. Neither is used as a
  negative now (`tests/test_lila.py` pins this).
- **This is not an Indian-forest result.** Caltech is the US Southwest: bobcats, opossums,
  raccoons. No labelled Indian camera-trap data is used, so how well the detector transfers to
  Bandipur or Serengeti habitats and species is **unmeasured**. Fine-tuning and a cross-domain test
  are Phase 5.

### Choosing a threshold

The detector's job is triage: spend the heavier species classifier only on frames that contain an
animal. For that, missing an animal costs more than a false alarm, so **0.2** (the default)
is sensible: it finds 92.6% of animal photos. Use 0.5 when you need fewer false alarms and can
afford to miss more.

## Speed

About **10 images/s** on this 16-core machine and **9.4 images/s limited to 4 threads**, which
approximates a free GitHub-hosted runner. The end-to-end worker (download, decode, hash, detect,
store) did 1,000 real images in 5 min 19 s here (3.1/s, bound by downloading images from a public
server). A 6-hour job therefore has room for tens of thousands of images.

## Privacy

`person` detections occur even in wildlife imagery (26 boxes in 1,000 Caltech frames, mostly low
confidence). The platform stores only a box and a confidence for them, never a person's image or
thumbnail, and the dashboard must not display one. Images themselves are never copied; we keep
only a link to the source.

## Publishing the model for the workflows

The ONNX is not committed (29 MB). The inference workflow downloads it from a GitHub release. To
publish it once, from a checkout that has `data/models/`:

```bash
gh release create models-v1 data/models/MDV6-mit-yolov9-c.onnx \
    data/models/MDV6-mit-yolov9-c.json third_party/NOTICES.md \
    --title "Models v1" --notes "MegaDetector V6 (MIT) converted to ONNX. See docs/models.md."
```

## Species classifiers

Two cheap, swappable **heads** on one shared, frozen **backbone**.

| | |
|---|---|
| Backbone | DINOv2 ViT-S/14 (Apache-2.0, via `timm`), ONNX, 86.7 MB, 224 px, 768-number embedding |
| Why frozen | No GPU is available for free, so instead of fine-tuning, each photo is embedded once and a small logistic-regression head is trained on top (about a minute on a laptop CPU) |
| Heads | `models/heads/plants.json` (234 KB) and `animals.json` (203 KB), plain JSON, committed |
| Serving | The same ONNX file is used for training and at runtime, and each head records the backbone's SHA-256; a test (run whenever the model file is present) fails if they drift apart |

Every prediction carries a calibrated probability (temperature-scaled on held-out data). Below
the head's threshold the answer is **"unknown"**, never a forced guess: a photo of a plant that is
not on the list must not be pushed into one of the listed species.

Reproduce: `scripts/export_backbone_onnx.py`, `scripts/build_plant_dataset.py`,
`scripts/build_animal_dataset.py`, then `scripts/train_head.py plants|animals`. Full results:
[metrics/plants.json](metrics/plants.json), [metrics/animals.json](metrics/animals.json). Training-data
provenance (observation ids, licences, no personal data): [training/](training/).

### Invasive plants

15 classes from 2,345 CC-licensed iNaturalist research-grade photos: **10 invasives** (*Lantana
camara*, *Senna spectabilis*, *Chromolaena odorata*, *Prosopis juliflora*, *Parthenium
hysterophorus*, *Opuntia stricta*, *Tridax procumbens*, *Mikania micrantha*, *Ageratina adenophora*,
*Eichhornia crassipes*), **4 native look-alikes** (*Cassia fistula*, *Grangea maderaspatana*,
*Coccinia grandis*, *Ipomoea pes-caprae*), and `other_plant` (385 random plants from India, so
"none of these" is an answer). Photos from India are taken first (up to half of each class), then
topped up from anywhere; only 41 of the 140 *Senna spectabilis* photos could come from India.

The natives matter more than the invasives: calling a harmless native plant invasive is the mistake
that could get it cleared. Look-alikes come from iNaturalist's own confusion data and qualify only
if iNaturalist records them **native to India**. Two obvious extra candidates, *Vachellia nilotica*
and *Senna auriculata*, were left out because iNaturalist holds no native record for them in India,
and a claim without a citation is not made.

Tested on **469 photos by photographers the model never saw** (split by observer, so one person's
near-identical photos never sit on both sides):

| | Result | 95% interval |
|---|---:|---:|
| Top-1 accuracy (15 classes, no threshold; majority-class baseline 19%) | 89.3% | |
| Photos it names (rest "unknown") | 81.2% | |
| Right, when it names one | 96.6% | |
| Invasives correctly named | 84.9% (225/265) | 80.1 to 88.7 |
| **Native look-alike called invasive** | **0/113** | **0 to 3.3** |
| Random other plant called invasive | 6/91 = 6.6% | 3.1 to 13.7 |
| India-only photos: invasives named / non-targets called invasive | 88.1% / 0 of 120 | |

How the threshold trades coverage for safety (test set; the shipped 0.76 was fixed on validation
data, not read from this table):

| Threshold | 0.50 | 0.60 | 0.70 | **0.76** | 0.80 | 0.90 | 0.95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Photos named | 93.8% | 89.1% | 83.8% | **81.2%** | 78.3% | 68.4% | 58.6% |
| Invasives named | 91.7% | 89.1% | 86.0% | **84.9%** | 82.6% | 73.6% | 65.3% |
| Random plant called invasive | 14.3% | 9.9% | 6.6% | **6.6%** | 4.4% | 3.3% | 1.1% |

**Read this carefully.**

- "0 of 113" is the absence of observed errors, not proof of none: the interval allows up to
  3.3%. Random plants are called invasive 6.6% of the time, **above the 5% target** (the interval,
  3 to 14%, straddles it). The safety budget was first applied to all non-targets pooled, which
  looked fine at about 6% while hiding that look-alikes were perfect and random plants were not;
  it now applies to each kind separately and the worst counts.
- The weakest invasive is *Senna spectabilis*: 70% recall at precision 1.0. It is also the one that
  matters most for Bandipur and Nagarahole, so this is where more field photos would help most.
- Training photos are mostly close-ups by naturalists. Ranger snapshots taken from a distance, in
  shade or of whole thickets are a different distribution, and **that shift is unmeasured**.
- It labels a photo. It cannot say how much ground a species covers.
- A GPU fine-tune would likely beat this frozen-backbone approach; that was not tried.

### Camera-trap animals

13 classes (bird, bobcat, cat, coyote, deer, dog, fox, opossum, rabbit, raccoon, rodent, skunk,
squirrel), 220 crops each, cut from Caltech Camera Traps boxes and spread across 85 camera
locations. **These are North American species**: this head demonstrates the pipeline and measures
generalisation on real camera-trap crops; it is not a model of Indian or African fauna.

Tested on **16 camera locations never seen in training**:

| | Result |
|---|---:|
| Top-1 accuracy, cameras never seen (majority baseline 11%) | **77.2%** |
| Top-1 accuracy when the same cameras appear on both sides | 81.6% |
| Cost of an unseen camera | 4.4 points |
| At the shipped threshold (0.77): crops named / right when named | 59% / 98.5% |

The "same cameras" figure is the flattering one most reports give; it also lets near-identical frames
from one burst fall on both sides, so part of that gap is leakage rather than camera difference.
Precision is high for every species (0.90 to 1.00) but many crops are declined (more than half
of opossum and rodent crops): the threshold buys a 98.5% hit rate at the price of coverage.

### Putting it together

`biodiv.inference.pipeline.analyse` detects, crops each animal with a 15% margin, and names it.
People and vehicles stop after detection: no crop of a person is ever made or classified. On the
real deer fixture, both real models find and name the deer.

## Publishing the models for the workflows

Extend the earlier release command to include the backbone:

```bash
gh release upload models-v1 data/models/dinov2_vits14.onnx data/models/dinov2_vits14.json
```
