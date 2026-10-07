import io

import httpx
import psycopg
import pytest
from PIL import Image, ImageDraw

from biodiv.inference.megadetector import Detection
from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.lila import IMAGE_BASE, register_media
from biodiv.ingestion.phash import dhash, hamming
from biodiv.workers.detect import ensure_model_version, reset_stuck, run_detection


def scene(seed: int) -> bytes:
    """Distinct synthetic photos, as JPEG bytes."""
    im = Image.linear_gradient("L").resize((320, 240)).convert("RGB")
    d = ImageDraw.Draw(im)
    for i in range(6):
        d.rectangle([(seed * 31 + i * 47) % 240, (seed * 17 + i * 29) % 170] * 1
                    + [(seed * 31 + i * 47) % 240 + 70, (seed * 17 + i * 29) % 170 + 50],
                    fill=((seed * 40 + i * 33) % 256,) * 3)
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


class FakeDetector:
    """Stands in for the ONNX model: reports an animal in any photo that is not 'empty'."""

    def __init__(self):
        self.seen = 0

    def detect_batch(self, images):
        self.seen += len(images)
        return [[Detection("animal", 0.9, (0.1, 0.2, 0.5, 0.6))] for _ in images]


class EmptyDetector(FakeDetector):
    def detect_batch(self, images):
        self.seen += len(images)
        return [[] for _ in images]


def sample(n, year=2011):
    return [{"id": f"img{i}", "file": f"img{i}.jpg", "width": 320, "height": 240,
             "captured": f"{year}-05-13 23:43:18", "gt": []} for i in range(n)]


def serve(respx_mock, files: dict[str, bytes | int]):
    """Serve each file; an int value is returned as that HTTP error status."""
    for name, body in files.items():
        resp = httpx.Response(body) if isinstance(body, int) else httpx.Response(200, content=body)
        respx_mock.get(IMAGE_BASE + name).mock(return_value=resp)


def client():
    return PoliteClient(user_agent="t", per_second=1000, backoff=0, retries=0)


async def go(url, detector, **kw):
    with psycopg.connect(url, autocommit=True) as conn:
        version = ensure_model_version(conn, "test-model", "test://source")
        async with client() as http:
            return await run_detection(conn, detector, http, version, **kw)


def q(url, sql, params=None):
    with psycopg.connect(url) as conn:
        return conn.execute(sql, params).fetchall()


def register(url, items):
    with psycopg.connect(url, autocommit=True) as conn:
        return register_media(conn, items)


def test_registering_frames_is_idempotent_and_marks_them_as_replay(ingest_db_url):
    assert register(ingest_db_url, sample(3)) == 3
    assert register(ingest_db_url, sample(3)) == 0
    assert q(ingest_db_url, "select kind, license from sources where name like 'LILA%'") == [
        ("replay", "CDLA-Permissive-1.0")]
    # Real capture dates are kept: archive footage must not pose as live.
    assert q(ingest_db_url, "select distinct captured_at::date::text from media_items") == [
        ("2011-05-13",)]


async def test_detection_end_to_end(ingest_db_url, respx_mock):
    url = ingest_db_url
    register(url, sample(3))
    serve(respx_mock, {f"img{i}.jpg": scene(i) for i in range(3)})
    detector = FakeDetector()

    stats = await go(url, detector)
    assert (stats.claimed, stats.with_detections, stats.detections) == (3, 3, 3)
    assert detector.seen == 3

    rows = q(url, "select d.origin, d.label_raw, d.confidence, d.bbox, d.species_id, "
                  "d.captured_at::date::text, mv.name from detections d "
                  "join model_versions mv on mv.id = d.model_version_id")
    assert len(rows) == 3
    origin, label, conf, bbox, species, when, model = rows[0]
    assert (origin, label, species, when, model) == (
        "model", "animal", None, "2011-05-13", "test-model")  # species is the classifier's job
    assert conf == pytest.approx(0.9)
    assert bbox == {"x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.6}
    assert q(url, "select status, count(*) from media_items group by 1") == [("done", 3)]
    assert q(url, "select count(*) from media_items where phash is not null") == [(3,)]


async def test_empty_frames_are_done_not_dropped(ingest_db_url, respx_mock):
    """An empty camera-trap frame is still observation effort, so it must stay 'done'."""
    url = ingest_db_url
    register(url, sample(2))
    serve(respx_mock, {f"img{i}.jpg": scene(i) for i in range(2)})
    stats = await go(url, EmptyDetector())
    assert (stats.empty, stats.with_detections, stats.detections) == (2, 0, 0)
    assert q(url, "select count(*) from detections") == [(0,)]
    assert q(url, "select status, count(*) from media_items group by 1") == [("done", 2)]


async def test_bad_images_are_recorded_with_a_reason_and_do_not_stop_the_batch(
    ingest_db_url, respx_mock
):
    url = ingest_db_url
    register(url, sample(4))
    serve(respx_mock, {"img0.jpg": scene(0), "img1.jpg": b"this is not a jpeg",
                       "img2.jpg": 404, "img3.jpg": scene(3)})
    stats = await go(url, FakeDetector())
    assert (stats.claimed, stats.failed, stats.with_detections) == (4, 2, 2)
    notes = dict(q(url, "select external_id, status_note from media_items "
                        "where status = 'failed'"))
    assert "corrupt image" in notes["img1"]
    assert "download" in notes["img2"] and "404" in notes["img2"]


async def test_a_recompressed_copy_with_the_same_capture_time_is_skipped(
    ingest_db_url, respx_mock
):
    url = ingest_db_url
    register(url, sample(3))
    original = scene(5)
    copy = io.BytesIO()
    Image.open(io.BytesIO(original)).save(copy, "JPEG", quality=85)
    assert hamming(dhash(Image.open(io.BytesIO(original))),
                   dhash(Image.open(io.BytesIO(copy.getvalue())))) <= 2  # premise
    serve(respx_mock, {"img0.jpg": original, "img1.jpg": copy.getvalue(), "img2.jpg": scene(9)})

    stats = await go(url, FakeDetector(), batch_size=1)  # sequential, so the twin is seen second
    assert (stats.duplicates, stats.with_detections) == (1, 2)
    ((ext, status, note),) = q(url, "select external_id, status, status_note from media_items "
                                    "where status = 'skipped'")
    assert ext == "img1" and note.startswith("near-duplicate of media")


async def test_an_identical_looking_photo_from_a_different_time_is_kept(
    ingest_db_url, respx_mock
):
    """Real finding: empty frames from one camera hash alike. Looking the same is not enough."""
    url = ingest_db_url
    two = sample(2)
    two[1]["captured"] = "2011-09-30 04:12:00"  # same view, months later
    register(url, two)
    same_view = scene(5)
    serve(respx_mock, {"img0.jpg": same_view, "img1.jpg": same_view})
    stats = await go(url, FakeDetector(), batch_size=1)
    assert (stats.duplicates, stats.with_detections) == (0, 2)


async def test_rerunning_does_nothing_and_limit_is_respected(ingest_db_url, respx_mock):
    url = ingest_db_url
    register(url, sample(5))
    serve(respx_mock, {f"img{i}.jpg": scene(i) for i in range(5)})
    first = await go(url, FakeDetector(), limit=3, batch_size=2)
    assert first.claimed == 3
    second = await go(url, FakeDetector())
    assert second.claimed == 2  # only what was left
    third = await go(url, FakeDetector())
    assert third.claimed == 0
    assert q(url, "select count(*) from detections") == [(5,)]


def test_stuck_images_can_be_requeued(ingest_db_url):
    register(ingest_db_url, sample(2))
    with psycopg.connect(ingest_db_url, autocommit=True) as conn:
        conn.execute("update media_items set status = 'processing'")  # a crashed run
        assert reset_stuck(conn) == 2
    assert q(ingest_db_url, "select status, count(*) from media_items group by 1") == [("new", 2)]


async def test_an_autocommit_connection_is_required(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        async with client() as http:
            with pytest.raises(ValueError, match="autocommit"):
                await run_detection(conn, FakeDetector(), http, 1)
