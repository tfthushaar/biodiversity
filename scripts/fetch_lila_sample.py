"""Download a reproducible sample of real camera-trap images with ground-truth boxes.

    python scripts/fetch_lila_sample.py --n 1000 --seed 0

Writes data/lila/caltech/ (gitignored) and sample.json. The sample is images that contain an
animal, plus some with a vehicle and some truly empty ones, so a detector is tested for false
alarms as well as misses. Source and licence: see biodiv/ingestion/lila.py.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import zipfile

import httpx

from biodiv.ingestion.lila import (
    FULL_META_URL,
    LABELS_URL,
    OUT,
    build_sample,
    download,
    empty_images,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--n", type=int, default=1000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--empty-frac", type=float, default=0.25)
    p.add_argument("--car-frac", type=float, default=0.03)
    args = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    labels = OUT / "caltech_bboxes_20200316.json"
    if not labels.exists():
        labels.write_bytes(httpx.get(LABELS_URL, timeout=120, follow_redirects=True).content)

    full = OUT / "caltech_camera_traps.json.zip"
    if not full.exists():
        full.write_bytes(httpx.get(FULL_META_URL, timeout=300, follow_redirects=True).content)
    with zipfile.ZipFile(io.BytesIO(full.read_bytes())) as z:
        empties = empty_images(json.loads(z.read(z.namelist()[0])))

    sample = build_sample(json.loads(labels.read_text("utf-8")), args.n, args.seed,
                          args.empty_frac, args.car_frac, empties)
    bad = asyncio.run(download(sample, OUT / "images"))
    sample = [s for s in sample if s["file"] not in set(bad)]
    (OUT / "sample.json").write_text(json.dumps(sample), encoding="utf-8")
    kinds = {"empty": 0, "vehicle": 0, "animal": 0}
    for s in sample:
        labels_in = {g["label"] for g in s["gt"]}
        kinds["animal" if "animal" in labels_in else "vehicle" if labels_in else "empty"] += 1
    print(f"{len(sample)} images ready in {OUT / 'images'} {kinds}; {len(bad)} corrupted dropped")


if __name__ == "__main__":
    main()
