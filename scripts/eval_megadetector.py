"""Evaluate the detector on the Caltech Camera Traps sample (see fetch_lila_sample.py).

    python scripts/eval_megadetector.py --onnx data/models/MDV6-mit-yolov9-c.onnx \
        --out docs/metrics/megadetector_caltech.json

Reports image-level and box-level accuracy against human annotations, a per-species breakdown
of what it misses, and CPU throughput (including a 4-thread run to approximate a free CI
runner).
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

from PIL import Image

from biodiv.inference.evaluate import ImageResult, box_level, image_level
from biodiv.inference.megadetector import Detection, MegaDetector

THRESHOLDS = (0.1, 0.2, 0.3, 0.5, 0.7, 0.9)


def run(detector: MegaDetector, items: list[dict], images: Path, batch: int):
    detections: list[list[Detection]] = []
    per_image_ms: list[float] = []
    start = time.perf_counter()
    for i in range(0, len(items), batch):
        chunk = items[i : i + batch]
        t0 = time.perf_counter()
        ims = [Image.open(images / it["file"]).convert("RGB") for it in chunk]
        detections.extend(detector.detect_batch(ims))
        per_image_ms.append((time.perf_counter() - t0) * 1000 / len(chunk))
    wall = time.perf_counter() - start
    return detections, wall, per_image_ms


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--onnx", type=Path, required=True)
    p.add_argument("--sample", type=Path, default=Path("data/lila/caltech/sample.json"))
    p.add_argument("--images", type=Path, default=Path("data/lila/caltech/images"))
    p.add_argument("--out", type=Path, default=Path("docs/metrics/megadetector_caltech.json"))
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--ci-threads", type=int, default=4)
    p.add_argument("--ci-images", type=int, default=100)
    args = p.parse_args()

    items = json.loads(args.sample.read_text(encoding="utf-8"))
    detector = MegaDetector(args.onnx, confidence=min(THRESHOLDS))
    detections, wall, ms = run(detector, items, args.images, args.batch)

    results = [
        ImageResult([(g["label"], tuple(g["box"])) for g in it["gt"]], dets)
        for it, dets in zip(items, detections, strict=True)
    ]

    # Which animals does it miss? Each Caltech image carries a single species label.
    seen, found = defaultdict(int), defaultdict(int)
    for it, r in zip(items, results, strict=True):
        if any(g["label"] == "animal" for g in it["gt"]):
            cat = it["gt"][0]["category"]
            seen[cat] += 1
            found[cat] += any(d.label == "animal" and d.confidence >= 0.2 for d in r.detections)
    by_category = {
        c: {"images": seen[c], "recall_at_0.2": round(found[c] / seen[c], 3)}
        for c in sorted(seen, key=lambda c: -seen[c])
    }

    # Throughput on a runner-like thread budget, on a slice of the same images.
    ci = MegaDetector(args.onnx, confidence=0.2, threads=args.ci_threads)
    _, ci_wall, _ = run(ci, items[: args.ci_images], args.images, args.batch)

    kinds = defaultdict(int)
    for it in items:
        labels = {g["label"] for g in it["gt"]}
        kinds["animal" if "animal" in labels else "vehicle" if labels else "empty"] += 1

    report = {
        "model": json.loads(args.onnx.with_suffix(".json").read_text("utf-8")),
        "dataset": "Caltech Camera Traps via LILA BC (CDLA-Permissive-1.0)",
        "images": len(items), "image_kinds": dict(kinds),
        "timing": {
            "images_per_second_all_threads": round(len(items) / wall, 2),
            "median_ms_per_image": round(statistics.median(ms), 1),
            f"images_per_second_{args.ci_threads}_threads": round(args.ci_images / ci_wall, 2),
        },
        "animal_image_level": [image_level(results, "animal", t) for t in THRESHOLDS],
        "animal_box_level": [box_level(results, "animal", t) for t in (0.2, 0.5, 0.7)],
        "vehicle_image_level": [image_level(results, "vehicle", t) for t in (0.2, 0.5)],
        "animal_recall_by_category": by_category,
        "caveat": (
            "Caltech boxes are annotated for the single labelled species per image, so a correct "
            "detection of an extra, unlabelled animal counts as a false positive in box precision."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"{len(items)} images {dict(kinds)}; {report['timing']}")
    print("\nANIMAL, image level:   thr  precision  recall    f1   false-alarm-on-empty")
    for m in report["animal_image_level"]:
        f = lambda v: "  n/a" if v is None else f"{v:6.3f}"  # noqa: E731
        print(f"                      {m['threshold']:.1f}  {f(m['precision'])}  {f(m['recall'])} "
              f"{f(m['f1'])}   {f(m['false_alarm_rate'])}")
    print("ANIMAL, box level (IoU>=0.5):")
    for m in report["animal_box_level"]:
        print(f"   thr {m['threshold']:.1f}: precision {m['precision']:.3f}  "
              f"recall {m['recall']:.3f}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
