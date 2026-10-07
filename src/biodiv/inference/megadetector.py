"""MegaDetector V6 (MIT, YOLOv9-c) running on ONNX Runtime: finds animals, people and vehicles.

Needs only onnxruntime, numpy and Pillow: no PyTorch at runtime, so it fits a free CPU runner.
The ONNX graph is produced by scripts/export_megadetector_onnx.py. It contains the network and
the box decoding; what remains here is the part that is cheap and easy to verify: letterboxing
in, thresholding and non-maximum suppression out. Every step mirrors the reference
implementation (MultimediaTechLab/YOLO, as used by Microsoft's PytorchWildlife).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

CLASS_NAMES = ("animal", "person", "vehicle")
INPUT_SIZE = 640
PAD_COLOR = (114, 114, 114)

# Defaults match the reference pipeline's NMS settings. Callers choose their own confidence
# threshold: lower finds more animals but admits more false alarms.
DEFAULT_CONFIDENCE = 0.2
DEFAULT_IOU = 0.5
MAX_DETECTIONS = 300
# The network sometimes fires inside the grey letterbox padding, producing boxes that lie mostly
# or wholly outside the real image (the reference implementation reports them). A detection must
# have at least this fraction of its area inside the image to count.
MIN_VISIBLE_FRACTION = 0.5


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2, as fractions of the image (0-1)


@dataclass(frozen=True)
class Letterbox:
    scale: float
    pad_left: int
    pad_top: int
    width: int  # original image size
    height: int


def letterbox(image: Image.Image, size: int = INPUT_SIZE) -> tuple[np.ndarray, Letterbox]:
    """Resize keeping aspect ratio, centre on a grey square. Returns CHW float32 in [0, 1]."""
    image = image.convert("RGB")
    w, h = image.size
    scale = min(size / w, size / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    pad_left, pad_top = (size - new_w) // 2, (size - new_h) // 2
    canvas = Image.new("RGB", (size, size), PAD_COLOR)
    canvas.paste(resized, (pad_left, pad_top))
    chw = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1) / 255.0
    return chw, Letterbox(scale, pad_left, pad_top, w, h)


def visible_box(
    box: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    """Clip a normalised box to the image, or None if too little of it is actually inside."""
    x1, y1, x2, y2 = box
    full = (x2 - x1) * (y2 - y1)
    clipped = tuple(min(max(v, 0.0), 1.0) for v in box)
    inside = (clipped[2] - clipped[0]) * (clipped[3] - clipped[1])
    if full <= 0 or inside <= 0 or inside / full < MIN_VISIBLE_FRACTION:
        return None
    return clipped  # type: ignore[return-value]


def iou_one_to_many(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area = (box[2] - box[0]) * (box[3] - box[1])
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    return inter / np.maximum(area + areas - inter, 1e-9)


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    """Greedy non-maximum suppression. Returns kept indices, best score first."""
    order = np.argsort(-scores, kind="stable")
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        order = rest[iou_one_to_many(boxes[i], boxes[rest]) <= iou_threshold]
    return keep


def postprocess(
    cls_logits: np.ndarray,
    boxes: np.ndarray,
    lb: Letterbox,
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    iou: float = DEFAULT_IOU,
    max_detections: int = MAX_DETECTIONS,
) -> list[Detection]:
    """Turn one image's raw network output into detections.

    cls_logits: (N, 3) raw class logits.  boxes: (N, 4) x1y1x2y2 in 640-pixel letterbox space.
    Classes are scored independently (sigmoid, not softmax), and NMS runs per class.
    """
    scores = 1.0 / (1.0 + np.exp(-cls_logits.astype(np.float64)))
    anchor_idx, class_idx = np.nonzero(scores > confidence)
    if anchor_idx.size == 0:
        return []
    cand_scores = scores[anchor_idx, class_idx]
    cand_boxes = boxes[anchor_idx].astype(np.float64)

    results: list[tuple[float, int, np.ndarray]] = []
    for cls in np.unique(class_idx):
        sel = np.nonzero(class_idx == cls)[0]
        for k in nms(cand_boxes[sel], cand_scores[sel], iou):
            results.append((float(cand_scores[sel[k]]), int(cls), cand_boxes[sel[k]]))
    results.sort(key=lambda r: -r[0])

    out: list[Detection] = []
    for score, cls, box in results[:max_detections]:
        # Undo the letterbox: remove the padding, undo the scale, then normalise.
        x1 = (box[0] - lb.pad_left) / lb.scale / lb.width
        y1 = (box[1] - lb.pad_top) / lb.scale / lb.height
        x2 = (box[2] - lb.pad_left) / lb.scale / lb.width
        y2 = (box[3] - lb.pad_top) / lb.scale / lb.height
        if (clipped := visible_box((x1, y1, x2, y2))) is not None:
            out.append(Detection(CLASS_NAMES[cls], score, clipped))
    return out


class MegaDetector:
    def __init__(
        self,
        model_path: str | Path,
        *,
        confidence: float = DEFAULT_CONFIDENCE,
        iou: float = DEFAULT_IOU,
        threads: int | None = None,
    ) -> None:
        import onnxruntime as ort  # imported here so the rest of the package needs no ONNX

        opts = ort.SessionOptions()
        if threads:
            opts.intra_op_num_threads = threads
        self._session = ort.InferenceSession(
            str(model_path), opts, providers=["CPUExecutionProvider"]
        )
        self._input = self._session.get_inputs()[0].name
        self.confidence, self.iou = confidence, iou

    def detect(self, image: Image.Image) -> list[Detection]:
        return self.detect_batch([image])[0]

    def detect_batch(self, images: Sequence[Image.Image]) -> list[list[Detection]]:
        prepared = [letterbox(im) for im in images]
        batch = np.stack([p[0] for p in prepared])
        cls_logits, boxes = self._session.run(None, {self._input: batch})
        return [
            postprocess(cls_logits[i], boxes[i], prepared[i][1],
                        confidence=self.confidence, iou=self.iou)
            for i in range(len(images))
        ]
