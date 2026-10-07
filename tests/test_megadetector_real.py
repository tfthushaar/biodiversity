"""The real ONNX model on real camera-trap photos.

Skipped unless MEGADETECTOR_ONNX points at the exported model, e.g.
    MEGADETECTOR_ONNX=data/models/MDV6-mit-yolov9-c.onnx pytest tests/test_megadetector_real.py
"""

import json
import os
from pathlib import Path

import pytest
from PIL import Image

from biodiv.inference.evaluate import box_iou
from biodiv.inference.megadetector import MegaDetector

MODEL = Path(os.environ.get("MEGADETECTOR_ONNX", ""))
FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.skipif(
    not MODEL.is_file(), reason="set MEGADETECTOR_ONNX to the exported model to run"
)

META = json.loads((FIXTURES / "camera_traps.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def detector():
    return MegaDetector(MODEL, confidence=0.2)


def photo(key):
    return Image.open(FIXTURES / META[key]["file"])


def test_finds_the_deer_and_puts_the_box_in_the_right_place(detector):
    dets = detector.detect(photo("animal"))
    animals = [d for d in dets if d.label == "animal"]
    assert animals and animals[0].confidence > 0.8
    truth = tuple(META["animal"]["gt"][0]["box"])
    assert box_iou(animals[0].box, truth) > 0.5
    assert not [d for d in dets if d.label == "vehicle"]


def test_reports_nothing_confident_in_an_empty_frame(detector):
    assert [d for d in detector.detect(photo("empty")) if d.confidence >= 0.5] == []


def test_recognises_a_vehicle_even_as_a_close_up(detector):
    vehicles = [d for d in detector.detect(photo("vehicle")) if d.label == "vehicle"]
    assert vehicles and vehicles[0].confidence > 0.5


def test_batching_does_not_change_the_answer(detector):
    one = [detector.detect(photo(k)) for k in ("animal", "empty", "vehicle")]
    together = detector.detect_batch([photo(k) for k in ("animal", "empty", "vehicle")])
    for a, b in zip(one, together, strict=True):
        assert [d.label for d in a] == [d.label for d in b]
        for x, y in zip(a, b, strict=True):
            assert x.confidence == pytest.approx(y.confidence, abs=1e-3)
            assert x.box == pytest.approx(y.box, abs=1e-3)


def test_greyscale_and_rgba_inputs_are_handled(detector):
    base = photo("animal")
    for converted in (base.convert("L"), base.convert("RGBA")):
        assert isinstance(detector.detect(converted), list)
