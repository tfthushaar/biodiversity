"""Caltech Camera Traps via LILA BC: real camera-trap frames with human-drawn boxes.

Licence: Community Data License Agreement, permissive variant (attribution required).
These are historical archives, so they enter the system as a *replay* source: every record
keeps its true original capture date and is labelled as replayed, never passed off as live.
"""

from __future__ import annotations

import asyncio
import random
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from PIL import Image

from biodiv.ingestion.http import PoliteClient

LABELS_URL = (
    "https://storage.googleapis.com/public-datasets-lila/caltechcameratraps/labels/"
    "caltech_bboxes_20200316.json"
)
IMAGE_BASE = "https://storage.googleapis.com/public-datasets-lila/caltech-unzipped/cct_images/"
OUT = Path("data") / "lila" / "caltech"
FULL_META_URL = (
    "https://storage.googleapis.com/public-datasets-lila/caltechcameratraps/labels/"
    "caltech_camera_traps.json.zip"
)
CAR, EMPTY = 33, 30


def _spread(images: list[dict], k: int, rng: random.Random) -> list[dict]:
    """Pick k images, taking turns across camera locations so one busy camera cannot dominate."""
    by_loc: dict[str | None, list[dict]] = defaultdict(list)
    for im in sorted(images, key=lambda i: i["id"]):
        by_loc[im.get("location")].append(im)
    for group in by_loc.values():
        rng.shuffle(group)
    locations = sorted(by_loc, key=str)
    rng.shuffle(locations)
    out: list[dict] = []
    while len(out) < k and any(by_loc.values()):
        for loc in locations:
            if by_loc[loc] and len(out) < k:
                out.append(by_loc[loc].pop())
    return out


def empty_images(full_meta: dict) -> list[dict]:
    """Images the dataset labels 'empty' at image level (the standard clean negatives)."""
    empty_ids = {
        c["id"] for c in full_meta["categories"] if c["name"] == "empty"
    }
    flagged = {a["image_id"] for a in full_meta["annotations"] if a["category_id"] in empty_ids}
    return [im for im in full_meta["images"] if im["id"] in flagged]


def build_sample(
    meta: dict,
    n: int,
    seed: int,
    empty_frac: float,
    car_frac: float,
    empties: list[dict] | None = None,
) -> list[dict]:
    """A reproducible mix of animal, vehicle and empty images with ground truth.

    `meta` is the bounding-box file (boxes for animals and cars). `empties` are verified-empty
    images from the full image-level metadata (see empty_images).

    Two kinds of image are deliberately never used as negatives, because both turned out to be
    unreliable and made a good detector look bad:
      - images with NO annotation: unlabelled, usually the unboxed sibling frames of a burst
        whose animal was boxed in another frame;
      - images the bounding-box file marks 'empty' *with a box drawn on them*: partial animals,
        close-ups and blur that annotators flagged as ambiguous, not clean blanks.
    """
    cats = {c["id"]: c["name"] for c in meta["categories"]}
    boxes: dict[str, list[dict]] = defaultdict(list)
    for a in meta["annotations"]:
        if a["category_id"] != EMPTY and "bbox" in a:
            boxes[a["image_id"]].append(a)

    images = {i["id"]: i for i in meta["images"]}
    animal = sorted(i for i, b in boxes.items() if any(x["category_id"] != CAR for x in b))
    vehicle = sorted(i for i, b in boxes.items() if all(x["category_id"] == CAR for x in b))
    blanks = [e for e in (empties or []) if e["id"] not in boxes]

    rng = random.Random(seed)
    n_empty = min(int(n * empty_frac), len(blanks))
    n_car = min(int(n * car_frac), len(vehicle))
    n_animal = min(n - n_empty - n_car, len(animal))
    sample = []
    for image_id in rng.sample(vehicle, n_car) + rng.sample(animal, n_animal):
        im = images[image_id]
        w, h = im["width"], im["height"]
        gt = []
        for a in boxes[image_id]:
            x, y, bw, bh = a["bbox"]
            gt.append({
                "label": "vehicle" if a["category_id"] == CAR else "animal",
                "category": cats[a["category_id"]],
                "box": [x / w, y / h, (x + bw) / w, (y + bh) / h],
            })
        sample.append(_entry(im, gt))
    sample += [_entry(im, []) for im in _spread(blanks, n_empty, rng)]
    return sample


def _entry(im: dict, gt: list[dict]) -> dict:
    return {
        "id": im["id"], "file": im["file_name"], "width": im["width"], "height": im["height"],
        "location": im.get("location"), "captured": im.get("date_captured"), "gt": gt,
    }


async def download(sample: list[dict], dest: Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    bad: list[str] = []
    async with PoliteClient(user_agent="biodiv-student-project/0.1", per_second=20,
                            max_concurrency=8) as http:

        async def one(item: dict) -> None:
            path = dest / item["file"]
            if not path.exists():
                path.write_bytes(await http.get_bytes(IMAGE_BASE + item["file"]))
            try:
                with Image.open(path) as im:
                    im.load()
            except Exception:  # corrupted frames are real in camera-trap data
                bad.append(item["file"])
                path.unlink(missing_ok=True)

        await asyncio.gather(*(one(i) for i in sample))
    return bad


def register_media(conn: psycopg.Connection, sample: list[dict]) -> int:
    """Add sampled frames to media_items as 'new', awaiting detection. Idempotent.

    Returns how many were newly added. Frames carry no coordinates, so they have no zone.
    """
    source_id = conn.execute(
        """
        insert into sources (name, kind, base_url, license, attribution)
        values ('LILA BC: Caltech Camera Traps', 'replay', %s, 'CDLA-Permissive-1.0',
                'Caltech Camera Traps, via LILA BC (lila.science)')
        on conflict (name) do update set base_url = excluded.base_url
        returning id
        """,
        (LABELS_URL,),
    ).fetchone()[0]
    added = 0
    for item in sample:
        # Camera clocks are local time with no zone; stored as wall-clock UTC. Good enough for
        # monthly rollups, not for sub-hour analysis.
        when = datetime.strptime(item["captured"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        url = IMAGE_BASE + item["file"]
        added += conn.execute(
            """
            insert into media_items (source_id, external_id, uri, image_url, captured_at,
                                     width, height, license, status)
            values (%s, %s, %s, %s, %s, %s, %s, 'CDLA-Permissive-1.0', 'new')
            on conflict (source_id, external_id) do nothing
            """,
            (source_id, item["id"], url, url, when, item["width"], item["height"]),
        ).rowcount
    return added
