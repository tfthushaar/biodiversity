import io
import json
import os
from pathlib import Path

import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from biodiv.api import deps
from biodiv.api.deps import RateLimiter, get_conn, get_limiter, get_registry
from biodiv.api.main import app
from biodiv.api.routes import _optional_conn
from biodiv.inference.classifier import LinearHead, Prediction
from biodiv.inference.megadetector import Detection

FIXTURES = Path(__file__).parent / "fixtures"


def jpeg(size=(200, 150), color=(120, 90, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def upload(client, path, data, content_type="image/jpeg", **kw):
    return client.post(path, files={"file": ("photo.jpg", data, content_type)}, **kw)


# ----------------------------------------------------------------- fakes for the models


class FakeDetector:
    def __init__(self, detections):
        self.detections = detections

    def detect(self, image):
        return self.detections


class RecordingNamer:
    def __init__(self):
        self.crops = []

    def classify(self, images):
        self.crops.extend(images)
        return [Prediction("deer", 0.91, "deer") for _ in images]


class FakeEmbedder:
    def embed(self, images, batch_size=16):
        return np.tile(np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32), (len(images), 1))


class FakePlantClassifier:
    def __init__(self, head):
        self.head, self.embedder = head, FakeEmbedder()


def plant_head(threshold=0.6, sharp=8.0):
    w = np.zeros((3, 4), dtype=np.float32)
    w[0, 0] = sharp  # the fake embedder always points along axis 0: "Lantana camara"
    head = LinearHead(["Lantana camara", "Cassia fistula", "other_plant"], w, np.zeros(3),
                      threshold=threshold)
    head.meta = {"kinds": {"Lantana camara": "invasive", "Cassia fistula": "native_lookalike",
                           "other_plant": "other"}, "photos": {"train": 1}, "split": "by observer"}
    return head


class FakeRegistry:
    def __init__(self, detector=None, animal_namer=None, plant=None):
        self.detector, self._animal, self._plant = detector, animal_namer, plant

    def classifier(self, task):
        return self._animal if task == "animals" else self._plant

    def availability(self):
        return {"detector": self.detector is not None, "plants": self._plant is not None,
                "animals": self._animal is not None}


@pytest.fixture
def client():
    app.dependency_overrides[get_limiter] = lambda: RateLimiter(1000)
    yield TestClient(app)
    app.dependency_overrides.clear()


def use(registry=None, overrides=None):
    app.dependency_overrides[get_registry] = lambda: registry
    for dep, value in (overrides or {}).items():
        app.dependency_overrides[dep] = value


# -------------------------------------------------------------------------- basics


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_the_documented_endpoints_exist(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert {"/api/v1/models", "/api/v1/infer/animals", "/api/v1/infer/plants",
            "/api/v1/zones/{slug}/report", "/health"} <= paths


def test_models_reports_unavailable_models_instead_of_failing(client):
    use(FakeRegistry())
    body = client.get("/api/v1/models").json()
    assert body["available"] == {"detector": False, "plants": False, "animals": False}


# ------------------------------------------------------------------ upload safety


@pytest.mark.parametrize("path", ["/api/v1/infer/animals", "/api/v1/infer/plants"])
def test_unsupported_file_types_are_refused(client, path):
    use(FakeRegistry(FakeDetector([]), plant=FakePlantClassifier(plant_head())))
    r = upload(client, path, b"%PDF-1.4 not an image", content_type="application/pdf")
    assert r.status_code == 415


def test_oversized_uploads_are_refused_without_reading_them_all(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    from biodiv.core import settings as s

    s.get_settings.cache_clear()
    use(FakeRegistry(FakeDetector([])))
    r = upload(client, "/api/v1/infer/animals", b"\xff\xd8" + b"0" * (2 * 1024 * 1024))
    s.get_settings.cache_clear()
    assert r.status_code == 413


def test_a_corrupt_image_is_a_clean_400_not_a_crash(client):
    use(FakeRegistry(FakeDetector([])))
    r = upload(client, "/api/v1/infer/animals", b"this is not a jpeg at all")
    assert r.status_code == 400 and "not a readable image" in r.json()["detail"]


def test_an_empty_upload_is_refused(client):
    use(FakeRegistry(FakeDetector([])))
    assert upload(client, "/api/v1/infer/animals", b"").status_code == 400


def test_a_decompression_bomb_is_refused(client, monkeypatch):
    from PIL import Image as PILImage

    monkeypatch.setattr(PILImage, "MAX_IMAGE_PIXELS", 10_000)  # tiny limit for the test
    use(FakeRegistry(FakeDetector([])))
    r = upload(client, "/api/v1/infer/animals", jpeg((400, 400)))  # 160,000 px > limit
    assert r.status_code == 400


def test_the_rate_limit_is_enforced_with_a_retry_hint(client):
    use(FakeRegistry(FakeDetector([])))
    app.dependency_overrides[get_limiter] = lambda: deps_limiter
    deps_limiter = RateLimiter(2)
    statuses = [upload(client, "/api/v1/infer/animals", jpeg()).status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
    blocked = upload(client, "/api/v1/infer/animals", jpeg())
    assert int(blocked.headers["Retry-After"]) >= 1


def test_limiter_window_slides_and_clients_are_independent():
    lim = RateLimiter(2)
    assert lim.check("a", now=0) is None and lim.check("a", now=1) is None
    assert lim.check("a", now=2) == pytest.approx(58)  # blocked until the first hit ages out
    assert lim.check("b", now=2) is None  # someone else is unaffected
    assert lim.check("a", now=61) is None  # the window has moved on


def test_the_client_is_taken_from_the_proxy_header():
    class Req:
        headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}
        client = None

    assert deps.client_id(Req()) == "203.0.113.9"


# ------------------------------------------------------------------- animal analysis


def test_animals_are_named_but_people_are_never_cropped_or_classified(client):
    dets = [Detection("animal", 0.9, (0.1, 0.1, 0.5, 0.5)),
            Detection("person", 0.8, (0.6, 0.1, 0.9, 0.9))]
    namer = RecordingNamer()
    use(FakeRegistry(FakeDetector(dets), animal_namer=namer))
    body = upload(client, "/api/v1/infer/animals", jpeg()).json()

    by_label = {f["label"]: f for f in body["findings"]}
    assert by_label["animal"]["species"]["answer"] == "deer"
    assert by_label["person"]["species"] is None
    assert len(namer.crops) == 1  # exactly one crop was ever made: the animal
    assert "never cropped or classified" in body["notice"]


def test_detection_still_works_when_no_species_classifier_is_loaded(client):
    use(FakeRegistry(FakeDetector([Detection("animal", 0.9, (0, 0, 1, 1))]), animal_namer=None))
    body = upload(client, "/api/v1/infer/animals", jpeg()).json()
    assert body["species_named"] is False and body["findings"][0]["species"] is None


def test_a_missing_detector_is_a_503_with_a_reason(client):
    use(FakeRegistry(detector=None))
    r = upload(client, "/api/v1/infer/animals", jpeg())
    assert r.status_code == 503 and "detector" in r.json()["detail"]


# ------------------------------------------------------------------- plant analysis


def test_a_confident_answer_names_the_plant(client):
    use(FakeRegistry(plant=FakePlantClassifier(plant_head())), {_optional_conn: lambda: None})
    r = upload(client, "/api/v1/infer/plants", jpeg())
    body = r.json()
    assert body["answer"] == "Lantana camara" and body["kind"] == "invasive"
    assert body["probability"] > 0.9 and len(body["alternatives"]) == 3
    assert "decision aid" in body["notice"]


def test_an_unsure_answer_is_unknown_but_still_shows_the_leaning(client):
    use(FakeRegistry(plant=FakePlantClassifier(plant_head(threshold=0.999999))),
        {_optional_conn: lambda: None})
    body = upload(client, "/api/v1/infer/plants", jpeg()).json()
    assert body["answer"] == "unknown" and body["kind"] is None
    assert body["best_guess"] == "Lantana camara"  # it may lean, but it does not claim


def test_the_catch_all_class_is_not_reported_as_a_species(client):
    head = plant_head()
    head.weights[:] = 0
    head.weights[2, 0] = 8.0  # the embedder now points at "other_plant"
    use(FakeRegistry(plant=FakePlantClassifier(head)), {_optional_conn: lambda: None})
    body = upload(client, "/api/v1/infer/plants", jpeg()).json()
    assert body["answer"] == "other_plant" and body["kind"] == "other" and body["context"] is None


def test_a_missing_plant_model_is_a_503(client):
    use(FakeRegistry(plant=None), {_optional_conn: lambda: None})
    assert upload(client, "/api/v1/infer/plants", jpeg()).status_code == 503


# ----------------------------------------------------- database-backed endpoints


@pytest.fixture
def api_db(ingest_db_url):
    def conn():
        with psycopg.connect(ingest_db_url) as c:
            yield c

    app.dependency_overrides[get_limiter] = lambda: RateLimiter(1000)
    app.dependency_overrides[get_conn] = conn
    app.dependency_overrides[_optional_conn] = conn
    yield ingest_db_url
    app.dependency_overrides.clear()


def seed_lantana(url):
    with psycopg.connect(url) as c:
        sid = c.execute("insert into species (scientific_name, common_name, kingdom) "
                        "values ('Lantana camara', 'common lantana', 'Plantae') returning id"
                        ).fetchone()[0]
        c.execute("insert into invasive_status (species_id, country, is_invasive, "
                  "establishment_means) values (%s, 'IN', true, 'Alien')", (sid,))
        c.execute("insert into mitigation_playbooks (species_id, method, description, "
                  "citation_text, source_quotes) values (%s, 'mechanical', 'x', 'c', '[\"q\"]')",
                  (sid,))
        c.commit()


def test_plant_answers_carry_what_the_database_knows_about_the_species(api_db):
    seed_lantana(api_db)
    use(FakeRegistry(plant=FakePlantClassifier(plant_head())),
        {get_limiter: lambda: RateLimiter(1000), get_conn: app.dependency_overrides[get_conn],
           _optional_conn: app.dependency_overrides[_optional_conn]})
    body = upload(TestClient(app), "/api/v1/infer/plants", jpeg()).json()
    ctx = body["context"]
    assert ctx["scientific_name"] == "Lantana camara" and ctx["invasive_in_india"] is True
    assert ctx["playbooks"] == 1 and ctx["impact_findings"] == 0


def test_zone_report_comes_from_the_precomputed_table(api_db):
    c = TestClient(app)
    assert c.get("/api/v1/zones/atlantis/report").status_code == 404
    assert "No report" in c.get("/api/v1/zones/bandipur/report").json()["detail"]
    with psycopg.connect(api_db) as conn:
        conn.execute("insert into zone_reports (zone_id, report) select id, %s::jsonb "
                     "from zones where slug = 'bandipur'", (json.dumps({"observations": 7}),))
        conn.commit()
    body = c.get("/api/v1/zones/bandipur/report").json()
    assert body["report"] == {"observations": 7} and body["computed_at"]


def test_without_a_database_the_report_endpoint_says_so(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    from biodiv.core import settings as s

    s.get_settings.cache_clear()
    try:
        r = TestClient(app).get("/api/v1/zones/bandipur/report")
    finally:
        s.get_settings.cache_clear()
    assert r.status_code == 503


# ----------------------------------------------------------------- the real models

DETECTOR = Path(os.environ.get("MEGADETECTOR_ONNX", ""))
BACKBONE = Path(os.environ.get("BACKBONE_ONNX", ""))
HEADS = Path(__file__).resolve().parent.parent / "models" / "heads"


@pytest.mark.skipif(not (DETECTOR.is_file() and BACKBONE.is_file()),
                    reason="set MEGADETECTOR_ONNX and BACKBONE_ONNX to run with the real models")
def test_the_real_service_finds_and_names_a_deer_over_http(client):
    from biodiv.api.deps import ModelRegistry
    from biodiv.core.settings import Settings

    registry = ModelRegistry(Settings(megadetector_onnx=str(DETECTOR),
                                      backbone_onnx=str(BACKBONE), heads_dir=str(HEADS)))
    use(registry)
    meta = json.loads((FIXTURES / "camera_traps.json").read_text("utf-8"))
    data = (FIXTURES / meta["animal"]["file"]).read_bytes()
    body = upload(client, "/api/v1/infer/animals", data).json()
    animal = next(f for f in body["findings"] if f["label"] == "animal")
    assert animal["species"]["best_guess"] == "deer"
    assert registry.availability() == {"detector": True, "plants": True, "animals": True}
