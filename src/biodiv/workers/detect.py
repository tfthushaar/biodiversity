"""Run the animal/person/vehicle detector over images waiting in the database.

    python -m biodiv.workers.detect --model data/models/MDV6-mit-yolov9-c.onnx --limit 1000

Takes media_items with status 'new' and an image_url, and for each one: downloads the image,
rejects corrupt files and near-duplicates, runs MegaDetector, and stores one detection row per
box (origin = 'model'). Species are not assigned here: MegaDetector says *that* something is
there; naming it is the species classifier's job. Every outcome other than 'done' records why.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import psycopg
from PIL import Image

from biodiv.core.settings import get_settings
from biodiv.inference.megadetector import Detection
from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.phash import dhash

log = logging.getLogger(__name__)

FIRST_PARTITIONED_YEAR = 2000
# Re-encoded or resized copies of one photo differ by 0-2 bits (measured on real camera-trap
# images). But the hash alone is NOT safe here: empty frames from one camera look identical, and
# ~740 of 560k pairs of *different* scenes also fall within 2 bits. So a duplicate must also share
# the capture time and the dimensions, which different visits to the same spot never do.
DUPLICATE_HAMMING = 2


class Detector(Protocol):
    def detect_batch(self, images: list[Image.Image]) -> list[list[Detection]]: ...


@dataclass
class DetectStats:
    claimed: int = 0
    with_detections: int = 0
    empty: int = 0
    detections: int = 0
    duplicates: int = 0
    failed: int = 0


def ensure_model_version(
    conn: psycopg.Connection, name: str, source: str, metrics: dict | None = None
) -> int:
    return conn.execute(
        """
        insert into model_versions (name, task, weights_uri, metrics)
        values (%s, 'detector', %s, %s::jsonb)
        on conflict (name, task) do update
          set weights_uri = excluded.weights_uri,
              metrics = case when excluded.metrics = '{}'::jsonb
                             then model_versions.metrics else excluded.metrics end
        returning id
        """,
        (name, source, json.dumps(metrics or {})),
    ).fetchone()[0]


def summarise_metrics(report: dict) -> dict:
    """The few numbers worth storing on the model row, from a full evaluation report."""
    pick = lambda rows, t: next((r for r in rows if r["threshold"] == t), {})  # noqa: E731
    animal = report.get("animal_image_level", [])
    return {
        "dataset": report.get("dataset"),
        "images": report.get("images"),
        "animal_image_level_at_0.2": {
            k: pick(animal, 0.2).get(k) for k in ("precision", "recall", "f1", "false_alarm_rate")
        },
        "animal_image_level_at_0.5": {
            k: pick(animal, 0.5).get(k) for k in ("precision", "recall", "f1", "false_alarm_rate")
        },
        "images_per_second_4_threads": report.get("timing", {}).get("images_per_second_4_threads"),
        "caveat": "false_alarm_rate is an upper bound: many 'empty' frames contain partial or "
                  "close-up animals. See docs/models.md.",
    }


def reset_stuck(conn: psycopg.Connection) -> int:
    """Put images abandoned mid-run (a crash leaves them 'processing') back in the queue."""
    return conn.execute(
        "update media_items set status = 'new' "
        "where status = 'processing' and image_url is not null"
    ).rowcount


Row = tuple[int, str, datetime | None, int | None, int | None]


def _claim(conn: psycopg.Connection, n: int) -> list[Row]:
    # SKIP LOCKED lets several workers share the queue without picking the same image.
    return conn.execute(
        """
        update media_items set status = 'processing'
        where id in (
          select id from media_items
          where status = 'new' and image_url is not null
          order by id limit %s for update skip locked
        )
        returning id, image_url, captured_at, width, height
        """,
        (n,),
    ).fetchall()


def _mark(conn: psycopg.Connection, media_id: int, status: str, note: str | None,
          phash: int | None = None) -> None:
    conn.execute(
        "update media_items set status = %s, status_note = %s, "
        "phash = coalesce(%s, phash) where id = %s",
        (status, note, phash, media_id),
    )


def _near_duplicate_of(
    conn: psycopg.Connection, row: Row, h: int
) -> int | None:
    media_id, _, captured_at, width, height = row
    if captured_at is None:  # no timestamp to corroborate the hash: never call it a duplicate
        return None
    found = conn.execute(
        "select id from media_items where id <> %s and phash is not null "
        "and bit_count((phash # %s)::bit(64)) <= %s "
        "and captured_at = %s and width is not distinct from %s "
        "and height is not distinct from %s order by id limit 1",
        (media_id, h, DUPLICATE_HAMMING, captured_at, width, height),
    ).fetchone()
    return found[0] if found else None


async def _fetch(http: PoliteClient, url: str) -> bytes | Exception:
    try:
        return await http.get_bytes(url)
    except Exception as exc:  # one bad image must not sink the batch
        return exc


def _decode(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()  # forces a full decode, so truncated files fail here rather than later
    return im.convert("RGB")


async def process_batch(
    conn: psycopg.Connection,
    http: PoliteClient,
    detector: Detector,
    rows: list[Row],
    model_version_id: int,
    stats: DetectStats,
) -> None:
    payloads = await asyncio.gather(*(_fetch(http, r[1]) for r in rows))

    ready: list[tuple[int, Image.Image, int]] = []
    for row, data in zip(rows, payloads, strict=True):
        media_id = row[0]
        if isinstance(data, Exception):
            _mark(conn, media_id, "failed", f"download: {type(data).__name__}: {data}"[:300])
            stats.failed += 1
            continue
        try:
            image = _decode(data)
        except Exception as exc:
            _mark(conn, media_id, "failed", f"corrupt image: {type(exc).__name__}"[:300])
            stats.failed += 1
            continue
        h = dhash(image)
        if (twin := _near_duplicate_of(conn, row, h)) is not None:
            _mark(conn, media_id, "skipped", f"near-duplicate of media {twin}", h)
            stats.duplicates += 1
            continue
        conn.execute("update media_items set phash = %s where id = %s", (h, media_id))
        ready.append((media_id, image, h))

    if not ready:
        return
    # ONNX inference is CPU-bound: keep it off the event loop so downloads keep flowing.
    results = await asyncio.to_thread(detector.detect_batch, [im for _, im, _ in ready])

    with conn.transaction():
        for (media_id, _, _), dets in zip(ready, results, strict=True):
            year = conn.execute(
                "select extract(year from coalesce(captured_at, ingested_at))::int "
                "from media_items where id = %s", (media_id,)).fetchone()[0]
            if year >= FIRST_PARTITIONED_YEAR:
                conn.execute("select ensure_detection_partition(%s)", (year,))
            for d in dets:
                conn.execute(
                    """
                    insert into detections (media_item_id, captured_at, species_id, label_raw,
                                            confidence, bbox, model_version_id, geom, zone_id,
                                            origin)
                    select m.id, coalesce(m.captured_at, m.ingested_at), null, %s, %s, %s::jsonb,
                           %s, m.geom, m.zone_id, 'model'
                    from media_items m where m.id = %s
                    """,
                    (d.label, d.confidence,
                     json.dumps(dict(zip(("x1", "y1", "x2", "y2"), d.box, strict=True))),
                     model_version_id, media_id),
                )
            conn.execute("update media_items set status = 'done', status_note = null "
                         "where id = %s", (media_id,))
            stats.detections += len(dets)
            stats.with_detections += bool(dets)
            stats.empty += not dets


async def run_detection(
    conn: psycopg.Connection,
    detector: Detector,
    http: PoliteClient,
    model_version_id: int,
    *,
    limit: int = 1000,
    batch_size: int = 8,
) -> DetectStats:
    if not conn.autocommit:
        raise ValueError("detect needs an autocommit connection; each step commits on its own")
    stats = DetectStats()
    while stats.claimed < limit:
        rows = _claim(conn, min(batch_size, limit - stats.claimed))
        if not rows:
            break
        stats.claimed += len(rows)
        await process_batch(conn, http, detector, rows, model_version_id, stats)
        if stats.claimed % 100 < batch_size:
            log.info("processed %d images, %d detections", stats.claimed, stats.detections)
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", type=Path, required=True, help="MegaDetector ONNX file")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--confidence", type=float, default=0.2)
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--retry-stuck", action="store_true")
    p.add_argument("--metrics", type=Path, help="evaluation JSON to store on the model version")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    from biodiv.inference.megadetector import MegaDetector

    detector = MegaDetector(args.model, confidence=args.confidence, threads=args.threads)
    meta_path = args.model.with_suffix(".json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    async def go() -> DetectStats:
        async with PoliteClient(user_agent=settings.user_agent, per_second=20,
                                max_concurrency=8) as http:
            with psycopg.connect(settings.database_url, autocommit=True) as conn:
                if args.retry_stuck:
                    log.info("requeued %d stuck images", reset_stuck(conn))
                metrics = (summarise_metrics(json.loads(args.metrics.read_text("utf-8")))
                           if args.metrics else None)
                version = ensure_model_version(
                    conn, meta.get("name", args.model.stem), meta.get("source", str(args.model)),
                    metrics)
                return await run_detection(conn, detector, http, version,
                                           limit=args.limit, batch_size=args.batch)

    t0 = datetime.now()
    s = asyncio.run(go())
    secs = max((datetime.now() - t0).total_seconds(), 1e-9)
    print(f"{s.claimed} images in {secs:.0f}s ({s.claimed / secs:.1f}/s): "
          f"{s.with_detections} with detections, {s.empty} empty, {s.detections} boxes, "
          f"{s.duplicates} duplicates, {s.failed} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
