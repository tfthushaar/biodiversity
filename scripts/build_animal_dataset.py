"""Build the camera-trap animal-species training set: crops of human-boxed animals.

    python scripts/build_animal_dataset.py --per-class 220

Source: Caltech Camera Traps via LILA BC (CDLA-Permissive-1.0). Each example is one animal cut
out with its human-drawn box (plus a margin), labelled with the species the annotators gave it.
Classes are drawn evenly across camera LOCATIONS, which is what lets us later test on cameras the
model never saw. Full frames are fetched, cropped, and deleted: only crops stay on disk.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from biodiv.ingestion.lila import CAR, EMPTY, LABELS_URL, download
from biodiv.ingestion.lila import OUT as LILA

ROOT = Path("data") / "animals"
DOCS = Path("docs") / "training"
MARGIN = 0.15
MIN_SIDE = 64
# Too few examples, or not an animal in the usual sense.
SKIP = {"car", "empty", "bat", "insect", "lizard", "badger", "mountain_lion", "cow", "pig"}


def pick(meta: dict, per_class: int, seed: int) -> list[dict]:
    cats = {c["id"]: c["name"] for c in meta["categories"]}
    images = {i["id"]: i for i in meta["images"]}
    by_class: dict[str, list[dict]] = defaultdict(list)
    for a in meta["annotations"]:
        name = cats[a["category_id"]]
        if a["category_id"] in (CAR, EMPTY) or name in SKIP or "bbox" not in a:
            continue
        im = images[a["image_id"]]
        x, y, w, h = a["bbox"]
        if min(w, h) >= MIN_SIDE / 2:  # tiny boxes are unrecognisable even to a person
            by_class[name].append({
                "label": name, "annotation": a["id"], "image": im["id"], "file": im["file_name"],
                "location": im.get("location"), "box": [x, y, w, h],
            })
    rng = random.Random(seed)
    chosen: list[dict] = []
    for _, items in sorted(by_class.items()):
        # One crop per image, taking turns across locations so no single camera dominates.
        by_loc: dict = defaultdict(dict)
        for it in sorted(items, key=lambda i: i["annotation"]):
            by_loc[it["location"]].setdefault(it["image"], it)
        pools = [list(v.values()) for _, v in sorted(by_loc.items(), key=lambda kv: str(kv[0]))]
        for pool in pools:
            rng.shuffle(pool)
        rng.shuffle(pools)
        picked: list[dict] = []
        while len(picked) < per_class and any(pools):
            for pool in pools:
                if pool and len(picked) < per_class:
                    picked.append(pool.pop())
        chosen += picked
    return chosen


def crop(im: Image.Image, item: dict) -> Image.Image:
    x, y, w, h = item["box"]
    mx, my = w * MARGIN, h * MARGIN
    box = (max(0, x - mx), max(0, y - my), min(im.width, x + w + mx), min(im.height, y + h + my))
    c = im.convert("RGB").crop(tuple(int(v) for v in box))
    c.thumbnail((448, 448))
    return c


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--per-class", type=int, default=220)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    labels = LILA / "caltech_bboxes_20200316.json"
    if not labels.exists():
        import httpx

        LILA.mkdir(parents=True, exist_ok=True)
        labels.write_bytes(httpx.get(LABELS_URL, timeout=120, follow_redirects=True).content)
    items = pick(json.loads(labels.read_text("utf-8")), args.per_class, args.seed)
    print(f"{len(items)} crops across {len(set(i['label'] for i in items))} species, "
          f"{len(set(i['location'] for i in items))} camera locations")

    src = ROOT / "_frames"
    frames = list({i["file"]: {"file": i["file"]} for i in items}.values())
    bad = set(asyncio.run(download(frames, src)))

    rows = []
    for it in items:
        if it["file"] in bad:
            continue
        out = ROOT / "images" / it["label"] / f"{it['annotation']}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src / it["file"]) as im:
            crop(im, it).save(out, "JPEG", quality=90)
        rel = str(out.relative_to(ROOT)).replace(chr(92), "/")
        rows.append({"label": it["label"], "annotation": it["annotation"], "image": it["image"],
                     "location": it["location"], "file": rel,
                     "observer": f"cam{it['location']}", "in_india": False})
    shutil.rmtree(src, ignore_errors=True)  # keep only the crops

    (ROOT / "manifest.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    DOCS.mkdir(parents=True, exist_ok=True)
    counts = Counter(r["label"] for r in rows)
    (DOCS / "animal_classes.json").write_text(json.dumps({
        "source": "Caltech Camera Traps via LILA BC (CDLA-Permissive-1.0)",
        "classes": [{"name": n, "kind": "animal", "photos": c} for n, c in sorted(counts.items())],
        "note": "Species are North American. This head demonstrates the pipeline on real "
                "camera-trap crops; it is not a model of Indian or African fauna.",
    }, indent=2) + "\n", encoding="utf-8")
    private = ("file", "observer", "in_india")
    provenance = [{k: v for k, v in r.items() if k not in private} for r in rows]
    (DOCS / "animals_manifest.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in provenance) + "\n", encoding="utf-8")
    print(f"{len(rows)} crops written; per class: {dict(counts)}")


if __name__ == "__main__":
    main()
