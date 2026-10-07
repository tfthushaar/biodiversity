"""Detector evaluation against human-labelled boxes.

Two views, because they answer different questions:
  - image level: "did it notice there is an animal in this photo?" (what triage needs)
  - box level:   "did it put the box in the right place?" (matched at IoU >= 0.5)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from biodiv.inference.megadetector import Detection

Box = tuple[float, float, float, float]


def box_iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


@dataclass(frozen=True)
class ImageResult:
    gt: Sequence[tuple[str, Box]]  # (label, box) from human annotation
    detections: Sequence[Detection]


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def match_boxes(
    preds: Sequence[Detection], gts: Sequence[Box], iou_threshold: float = 0.5
) -> tuple[int, int, int]:
    """Greedy match, most confident prediction first. Returns (tp, fp, fn)."""
    unmatched = list(gts)
    tp = 0
    for det in sorted(preds, key=lambda d: -d.confidence):
        best = max(unmatched, key=lambda g: box_iou(det.box, g), default=None)
        if best is not None and box_iou(det.box, best) >= iou_threshold:
            unmatched.remove(best)
            tp += 1
    return tp, len(preds) - tp, len(unmatched)


def image_level(results: Sequence[ImageResult], label: str, threshold: float) -> dict:
    """Confusion counts for 'is there at least one <label> in the image?'."""
    tp = fp = fn = tn = 0
    for r in results:
        truth = any(lab == label for lab, _ in r.gt)
        pred = any(d.label == label and d.confidence >= threshold for d in r.detections)
        tp += truth and pred
        fp += (not truth) and pred
        fn += truth and (not pred)
        tn += (not truth) and (not pred)
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    f1 = _ratio(2 * precision * recall, precision + recall) if precision and recall else None
    return {
        "threshold": threshold, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "false_alarm_rate": _ratio(fp, fp + tn),  # share of animal-free images wrongly flagged
    }


def box_level(
    results: Sequence[ImageResult], label: str, threshold: float, iou_threshold: float = 0.5
) -> dict:
    tp = fp = fn = 0
    for r in results:
        preds = [d for d in r.detections if d.label == label and d.confidence >= threshold]
        a, b, c = match_boxes(preds, [box for lab, box in r.gt if lab == label], iou_threshold)
        tp, fp, fn = tp + a, fp + b, fn + c
    return {
        "threshold": threshold, "iou": iou_threshold, "tp": tp, "fp": fp, "fn": fn,
        "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn),
    }
