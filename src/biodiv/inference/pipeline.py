"""Image in, findings out: detect animals, people and vehicles, then name each animal.

Two stages, because they do different jobs. The detector (MegaDetector) answers "is there an
animal, and where?" on every frame cheaply. Only the crops it finds are passed to the heavier
species classifier. People and vehicles stop after detection: we record that something was
there, never who, and nothing about a person is passed on or kept.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from biodiv.inference.classifier import Prediction
from biodiv.inference.megadetector import Detection

CROP_MARGIN = 0.15  # the animal head was trained on boxes padded by this fraction of their size


class Detector(Protocol):
    def detect(self, image: Image.Image) -> list[Detection]: ...


class Namer(Protocol):
    def classify(self, images: Sequence[Image.Image]) -> list[Prediction]: ...


@dataclass(frozen=True)
class Finding:
    label: str  # animal | person | vehicle
    confidence: float  # the detector's
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 as fractions of the image
    species: Prediction | None = None  # animals only, and only if a classifier was supplied


def crop_box(
    image: Image.Image, box: tuple[float, float, float, float], margin: float = CROP_MARGIN
) -> Image.Image:
    """The region of `image` inside a normalised box, padded by `margin` of its own size."""
    w, h = image.size
    x1, y1, x2, y2 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    left, top = max(0, int(x1 - mx)), max(0, int(y1 - my))
    right, bottom = min(w, int(x2 + mx)), min(h, int(y2 + my))
    return image.convert("RGB").crop((left, top, max(right, left + 1), max(bottom, top + 1)))


def analyse(
    image: Image.Image,
    detector: Detector,
    animal_namer: Namer | None = None,
    *,
    min_confidence: float = 0.2,
    cropper: Callable[..., Image.Image] = crop_box,
) -> list[Finding]:
    detections = [d for d in detector.detect(image) if d.confidence >= min_confidence]
    animals = [d for d in detections if d.label == "animal"]
    names: list[Prediction | None] = [None] * len(animals)
    if animal_namer is not None and animals:
        names = list(animal_namer.classify([cropper(image, d.box) for d in animals]))

    named = iter(names)
    findings = []
    for d in detections:
        findings.append(Finding(d.label, d.confidence, d.box,
                                next(named) if d.label == "animal" else None))
    return findings
