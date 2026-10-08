# Models

The platform uses three models: a detector that finds animals, people and vehicles in camera-trap
images, and two small classifiers that name plants and animals. All run on CPU.

## Detector: MegaDetector V6 (`MDV6-mit-yolov9-c`)

Finds animals, people and vehicles in camera-trap images and returns a box and confidence for
each. Naming the species is the classifier's job.

| | |
|---|---|
| Source | Microsoft AI for Good Lab, <https://zenodo.org/records/15398270> |
| Architecture | YOLOv9-c, 9.7M parameters, 640 px input |
| Licence | MIT (weights and the library used to run them) |
| Deployed file | ONNX, 29.1 MB, CPU only, no PyTorch at runtime |
| Checkpoint MD5 | `d8626ba22fccbd9c520e0deb19d721f7`, checked before loading |
| ONNX SHA-256 | `9dae0ced1e1a3210ebd6a835303d7a6ffc671f3cd15a51cbcb8adaedc238ddbe` |

**Choice of variant.** Of the nine V6 variants, five are AGPL-3.0 (built on Ultralytics), which
would constrain how the project can be licensed and deployed. Two are Apache-2.0 (RT-DETR, much
larger) and two are MIT. We use the smaller MIT variant, which fits a free CPU runner.

### Conversion to ONNX

The conversion runs once, in a separate environment with PyTorch and the MIT `yolo` library.

```bash
python scripts/export_megadetector_onnx.py --ckpt MDV6-mit-yolov9-c.ckpt \
    --config config_v9s.yaml --out MDV6-mit-yolov9-c.onnx
```

The script checks the checkpoint's MD5 against Zenodo's before loading it, because loading
unpickles the file. It confirms that every weight tensor loaded, since the library only warns
about mismatches and a skipped tensor leaves a layer randomly initialised. It compares the ONNX
output with PyTorch at a batch size the trace did not use: logits agree to 1.5e-4 and boxes to
6e-4. On Windows, use a short path such as `C:\bdx` for the environment, because PyTorch's
package tree exceeds the 260-character path limit in deep directories.

### Agreement with the reference implementation

`scripts/verify_megadetector.py` runs the ONNX and NumPy pipeline and the reference implementation
on the same photos. On 60 images both produce 59 detections, all matched, with zero box
disagreement and zero confidence difference.

One deliberate difference remains. The network sometimes fires inside the grey letterbox padding,
which gives boxes that lie wholly or mostly outside the image (11 of 70 reference detections in
this sample). We drop any detection with less than half its area inside the image
(`MIN_VISIBLE_FRACTION`).

## Detector accuracy

Evaluated on 1,000 Caltech Camera Traps photos (720 with animals, 30 with vehicles, 250 verified
empty, from many camera locations) against human-drawn boxes. Full results are in
[metrics/megadetector_caltech.json](metrics/megadetector_caltech.json). To reproduce, run
`scripts/fetch_lila_sample.py` and then `scripts/eval_megadetector.py`.

| Confidence threshold | 0.2 | 0.5 | 0.7 |
|---|---:|---:|---:|
| Animal images found (recall) | 92.6% | 78.6% | 66.7% |
| Flagged images that had an animal (precision) | 93.2% | 95.4% | 97.4% |
| Empty images flagged | 17.5% | 9.6% | 4.6% |
| Box recall, IoU 0.5 or higher | 81.1% | 72.1% | 63.1% |
| Box precision, IoU 0.5 or higher | 79.3% | 88.5% | 94.0% |

Vehicles are found 96.7% of the time at 0.2, with 83% precision.

At 0.2, recall is lowest for birds (81.6%, n=38), squirrels (87.5%), rabbits (88.1%) and opossums
(90.3%), and highest for dogs (100%), raccoons (97%), deer (96%) and cats (95%). Coyotes and
bobcats are found about 92% of the time. Lizards (2), foxes (8) and badgers (1) are too few to
interpret.

### Reading the results

- **Empty images flagged is an upper bound on the false-alarm rate.** Among the most confident
  flags on verified-empty frames, most show real animals that the sequence-level label missed: a
  fur close-up against the lens, legs, a raccoon in a corner, a faint silhouette. A minority are
  genuine errors such as rocks.
- **Box precision is conservative.** Caltech boxes cover one labelled species per image, so a
  correctly found second animal counts as a false positive.
- **Negative examples.** Images with no annotation are unlabelled, and images that the box file
  marks `empty` but that carry a drawn box show partial animals. Neither serves as a negative
  example. `tests/test_lila.py` pins this rule.
- **Geographic scope.** Caltech covers the US Southwest (bobcats, opossums, raccoons). No labelled
  Indian or African camera-trap set was used, so transfer to Bandipur or Serengeti habitats is not
  measured.

### Choosing a threshold

The detector selects frames for the heavier species classifier. For that job a missed animal costs
more than a false alarm, so the default is 0.2, which finds 92.6% of animal photos. A threshold of
0.5 gives fewer false alarms at the price of more misses.

## Speed

About 10 images per second on a 16-core machine and 9.4 per second limited to 4 threads, which
approximates a free GitHub-hosted runner. The full worker (download, decode, hash, detect, store)
processed 1,000 images in 5 min 19 s (3.1 per second, limited by downloads from a public server).
A 6-hour job has room for tens of thousands of images.

## Privacy

Person detections occur even in wildlife imagery (26 boxes in 1,000 Caltech frames, mostly low
confidence). For these the platform stores a box and a confidence and nothing else: no crop, no
thumbnail, and the dashboard shows none. Images are not copied; only a link to the source is kept.

## Publishing the models for the workflows

The ONNX files are not committed. The detect workflow and the Render service download them from
the `models-v1` GitHub release, which holds the detector, the backbone and `NOTICES.md`.

```bash
gh release create models-v1 data/models/MDV6-mit-yolov9-c.onnx data/models/MDV6-mit-yolov9-c.json \
    data/models/dinov2_vits14.onnx data/models/dinov2_vits14.json third_party/NOTICES.md \
    --title "Models v1" --notes "MegaDetector V6 (MIT) as ONNX, and DINOv2 ViT-S/14 (Apache-2.0)."
```

## Species classifiers

Two small heads share one frozen backbone.

| | |
|---|---|
| Backbone | DINOv2 ViT-S/14 (Apache-2.0, via `timm`), ONNX, 86.7 MB, 224 px input, 768-number embedding |
| Training approach | No free GPU is available, so each photo is embedded once and a logistic-regression head is trained on the embeddings (about a minute on a laptop CPU) |
| Heads | `models/heads/plants.json` (234 KB) and `animals.json` (203 KB), plain JSON, committed |
| Serving | Training and runtime use the same ONNX file. Each head records the backbone's SHA-256, and a test fails if the two drift apart |

Predictions carry a calibrated probability (temperature scaling on held-out data). Below a head's
threshold the answer is "unknown", so a photo of a plant outside the list is not forced into a
listed species.

To reproduce, run `scripts/export_backbone_onnx.py`, `scripts/build_plant_dataset.py`,
`scripts/build_animal_dataset.py`, then `scripts/train_head.py plants|animals`. Full results are in
[metrics/plants.json](metrics/plants.json) and [metrics/animals.json](metrics/animals.json), and
training-data provenance (observation ids, licences, no personal data) is in [training/](training/).

### Invasive plants

Fifteen classes from 2,345 CC-licensed iNaturalist research-grade photos:

- ten invasives: *Lantana camara*, *Senna spectabilis*, *Chromolaena odorata*, *Prosopis
  juliflora*, *Parthenium hysterophorus*, *Opuntia stricta*, *Tridax procumbens*, *Mikania
  micrantha*, *Ageratina adenophora* and *Eichhornia crassipes*;
- four native look-alikes: *Cassia fistula*, *Grangea maderaspatana*, *Coccinia grandis* and
  *Ipomoea pes-caprae*;
- `other_plant`: 385 random plants from India, so "none of these" is an available answer.

Photos from India are taken first (up to half of each class) and the rest from anywhere. Only 41
of the 140 *Senna spectabilis* photos come from India.

Wrongly calling a native plant invasive is the costly error, because it could lead to the plant
being cleared. Look-alikes come from iNaturalist's own confusion data and are included only when
iNaturalist records them as native to India. *Vachellia nilotica* and *Senna auriculata* were
considered and left out because iNaturalist holds no native record for them in India.

The test set is 469 photos by photographers who contributed nothing to training. The split is by
observer, so one person's near-identical photos never fall on both sides.

| | Result | 95% interval |
|---|---:|---|
| Top-1 accuracy, 15 classes, no threshold (majority-class baseline 19%) | 89.3% | |
| Photos named (the rest are "unknown") | 81.2% | |
| Correct, when a plant is named | 96.6% | |
| Invasives correctly named | 84.9% (225 of 265) | 80.1 to 88.7 |
| Native look-alikes called invasive | 0 of 113 | 0 to 3.3 |
| Random other plants called invasive | 6 of 91 (6.6%) | 3.1 to 13.7 |
| India-only photos: invasives named, non-targets called invasive | 88.1%, 0 of 120 | |

The threshold sets the balance between coverage and safety. The deployed value, 0.76, was fixed on
validation data before the test set was scored.

| Threshold | 0.50 | 0.60 | 0.70 | **0.76** | 0.80 | 0.90 | 0.95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Photos named | 93.8% | 89.1% | 83.8% | **81.2%** | 78.3% | 68.4% | 58.6% |
| Invasives named | 91.7% | 89.1% | 86.0% | **84.9%** | 82.6% | 73.6% | 65.3% |
| Random plant called invasive | 14.3% | 9.9% | 6.6% | **6.6%** | 4.4% | 3.3% | 1.1% |

Limits of these results:

- No look-alike was called invasive in 113 trials. With that many trials the true rate could still
  be as high as 3.3%. Random plants are called invasive 6.6% of the time, above the 5% target,
  though the interval (3.1 to 13.7%) spans it. The safety budget applies to each kind of
  non-target separately, and the worst kind governs the threshold.
- *Senna spectabilis* has the lowest recall (70% at precision 1.0). It matters most for Bandipur
  and Nagarahole, so more field photos of it would help most.
- Training photos are mostly close-ups by naturalists. Ranger snapshots taken from a distance, in
  shade or of whole thickets follow a different distribution, and that shift is unmeasured.
- The classifier labels a photo. It cannot estimate how much ground a species covers.
- Fine-tuning on a GPU would probably improve on a frozen backbone. We have not tried it.

### Camera-trap animals

Thirteen classes (bird, bobcat, cat, coyote, deer, dog, fox, opossum, rabbit, raccoon, rodent,
skunk, squirrel), 220 crops each, cut from Caltech Camera Traps boxes across 85 camera locations.
These are North American species. The head demonstrates the pipeline and measures how well a
classifier transfers to cameras it has not seen. Indian and African fauna are outside its scope.

The test set is 16 camera locations absent from training.

| | Result |
|---|---:|
| Top-1 accuracy on unseen cameras (majority baseline 11%) | **77.2%** |
| Top-1 accuracy when the same cameras appear on both sides | 81.6% |
| Cost of an unseen camera | 4.4 points |
| At the deployed threshold (0.77): crops named, correct when named | 59%, 98.5% |

Many reports give the same-camera figure. It also lets near-identical frames from one burst fall
on both sides, so part of the gap to the unseen-camera figure is leakage. Precision is high for
every species (0.90 to 1.00), and many crops are declined (more than half of opossum and rodent
crops). The threshold buys a 98.5% hit rate at the price of coverage.

### Combined pipeline

`biodiv.inference.pipeline.analyse` detects, crops each animal with a 15% margin, and names it.
People and vehicles stop after detection, so no crop of a person is made or classified. On the
deer test image, both models find and name the deer.
