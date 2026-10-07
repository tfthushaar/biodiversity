import json
import os
from pathlib import Path

import pytest
from PIL import Image

from biodiv.inference.classifier import LinearHead, Prediction, SpeciesClassifier
from biodiv.inference.megadetector import Detection, MegaDetector
from biodiv.inference.pipeline import analyse, crop_box

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parent.parent


class FakeDetector:
    def __init__(self, detections):
        self.detections = detections

    def detect(self, image):
        return self.detections


class RecordingNamer:
    """Records exactly which crops it is asked to name."""

    def __init__(self):
        self.seen = []

    def classify(self, images):
        self.seen.extend(images)
        return [Prediction("deer", 0.9, "deer") for _ in images]


def test_crop_box_is_padded_and_stays_inside_the_image():
    im = Image.new("RGB", (1000, 500))
    # Box (0.4,0.4)-(0.6,0.6) is 200x100 px; 15% padding adds 30x15 px each side.
    assert crop_box(im, (0.4, 0.4, 0.6, 0.6)).size == (260, 130)
    edge = crop_box(im, (0.0, 0.0, 0.2, 0.2))  # padding past the edge is clipped, not an error
    assert edge.size == (230, 115) and edge.size[0] <= 1000
    assert crop_box(im, (0.5, 0.5, 0.5, 0.5)).size[0] >= 1  # a degenerate box still yields pixels


def test_only_animals_are_named_and_in_order():
    im = Image.new("RGB", (400, 300))
    dets = [Detection("animal", 0.9, (0.1, 0.1, 0.4, 0.4)),
            Detection("vehicle", 0.8, (0.5, 0.5, 0.9, 0.9)),
            Detection("animal", 0.5, (0.6, 0.1, 0.9, 0.4))]
    namer = RecordingNamer()
    findings = analyse(im, FakeDetector(dets), namer)

    assert [f.label for f in findings] == ["animal", "vehicle", "animal"]
    assert findings[0].species and findings[2].species and findings[1].species is None
    assert len(namer.seen) == 2  # the vehicle never reached the species classifier


def test_a_person_is_detected_but_never_classified_or_cropped():
    """Privacy by construction: nothing about a person is passed on."""
    im = Image.new("RGB", (400, 300))
    namer = RecordingNamer()
    (finding,) = analyse(im, FakeDetector([Detection("person", 0.9, (0.1, 0.1, 0.5, 0.9))]), namer)
    assert finding.label == "person" and finding.species is None
    assert namer.seen == []  # no crop of a person was ever made available


def test_low_confidence_detections_are_dropped_and_the_namer_is_optional():
    im = Image.new("RGB", (100, 100))
    dets = [Detection("animal", 0.9, (0, 0, 1, 1)), Detection("animal", 0.1, (0, 0, 1, 1))]
    findings = analyse(im, FakeDetector(dets), None, min_confidence=0.2)
    assert len(findings) == 1 and findings[0].species is None


def test_nothing_found_means_no_work():
    namer = RecordingNamer()
    assert analyse(Image.new("RGB", (50, 50)), FakeDetector([]), namer) == []
    assert namer.seen == []


# --- both real models, on a real photograph ------------------------------------------------

DETECTOR = Path(os.environ.get("MEGADETECTOR_ONNX", ""))
BACKBONE = Path(os.environ.get("BACKBONE_ONNX", ""))
HEAD = REPO / "models" / "heads" / "animals.json"


@pytest.mark.skipif(
    not (DETECTOR.is_file() and BACKBONE.is_file() and HEAD.exists()),
    reason="set MEGADETECTOR_ONNX and BACKBONE_ONNX to run with the real models",
)
def test_real_models_find_and_name_the_deer():
    from biodiv.inference.classifier import Embedder

    meta = json.loads((FIXTURES / "camera_traps.json").read_text("utf-8"))
    photo = Image.open(FIXTURES / meta["animal"]["file"])
    assert meta["animal"]["gt"][0]["category"] == "deer"  # the human annotation

    classifier = SpeciesClassifier(Embedder(BACKBONE), LinearHead.load(HEAD))
    findings = analyse(photo, MegaDetector(DETECTOR, confidence=0.2), classifier)
    animal = next(f for f in findings if f.label == "animal")
    assert animal.species.best == "deer"  # whether or not it clears the answer threshold
