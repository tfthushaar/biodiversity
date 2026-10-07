"""Species classification: a frozen DINOv2 backbone plus a small trained linear head.

The backbone (ONNX, shared by every task) turns a photo into a 768-number embedding. A head is
a few hundred KB of weights, trained per task (invasive plants, camera-trap animals), applied
here in plain NumPy. One backbone and many cheap heads means a new species list needs minutes of
training on a laptop CPU and no GPU, and training and serving use the very same ONNX file, so they
cannot drift apart.

Predictions carry a calibrated probability. Below the head's `threshold` the answer is
"unknown" rather than a guess: a field photo of an unlisted plant must not be forced into one of
the known species.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)
UNKNOWN = "unknown"


def preprocess(image: Image.Image, size: int = SIZE) -> np.ndarray:
    """Resize the short side to `size` (bicubic), centre-crop square, normalise. CHW float32."""
    image = image.convert("RGB")
    w, h = image.size
    scale = size / min(w, h)
    nw, nh = max(size, round(w * scale)), max(size, round(h * scale))
    image = image.resize((nw, nh), Image.Resampling.BICUBIC)
    left, top = (nw - size) // 2, (nh - size) // 2
    image = image.crop((left, top, left + size, top + size))
    chw = np.asarray(image, dtype=np.float32).transpose(2, 0, 1) / 255.0
    return (chw - MEAN) / STD


def l2_normalise(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-12)


def softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


@dataclass(frozen=True)
class Prediction:
    label: str  # a class name, or UNKNOWN when nothing is confident enough
    probability: float  # of `best`, calibrated
    best: str  # the most likely class, even when we decline to name it

    @property
    def is_known(self) -> bool:
        return self.label != UNKNOWN


class LinearHead:
    def __init__(
        self,
        classes: Sequence[str],
        weights: np.ndarray,
        bias: np.ndarray,
        *,
        temperature: float = 1.0,
        threshold: float = 0.0,
        meta: dict | None = None,
    ) -> None:
        if weights.shape != (len(classes), weights.shape[1]) or bias.shape != (len(classes),):
            raise ValueError("weights/bias do not match the class list")
        self.classes = list(classes)
        self.weights = weights.astype(np.float32)
        self.bias = bias.astype(np.float32)
        self.temperature = float(temperature)
        self.threshold = float(threshold)
        self.meta = meta or {}

    @property
    def dim(self) -> int:
        return self.weights.shape[1]

    def probabilities(self, embeddings: np.ndarray) -> np.ndarray:
        logits = l2_normalise(embeddings) @ self.weights.T + self.bias
        return softmax(logits / self.temperature)

    def predict(self, embeddings: np.ndarray) -> list[Prediction]:
        probs = self.probabilities(embeddings)
        out = []
        for row in probs:
            i = int(row.argmax())
            p = float(row[i])
            out.append(Prediction(self.classes[i] if p >= self.threshold else UNKNOWN, p,
                                  self.classes[i]))
        return out

    # -- persistence: plain JSON, so heads are reviewable, diffable and tiny -----------------
    def to_json(self) -> dict:
        return {
            "classes": self.classes,
            "weights": np.round(self.weights, 6).tolist(),
            "bias": np.round(self.bias, 6).tolist(),
            "temperature": self.temperature,
            "threshold": self.threshold,
            "meta": self.meta,
        }

    @classmethod
    def from_json(cls, data: dict) -> LinearHead:
        return cls(
            data["classes"], np.array(data["weights"], dtype=np.float32),
            np.array(data["bias"], dtype=np.float32), temperature=data["temperature"],
            threshold=data["threshold"], meta=data.get("meta"),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_json()) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> LinearHead:
        return cls.from_json(json.loads(Path(path).read_text(encoding="utf-8")))


class Embedder:
    """The shared ONNX backbone: images in, 768-d embeddings out."""

    def __init__(self, model_path: str | Path, *, threads: int | None = None) -> None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        if threads:
            opts.intra_op_num_threads = threads
        self._session = ort.InferenceSession(
            str(model_path), opts, providers=["CPUExecutionProvider"])
        self._input = self._session.get_inputs()[0].name

    def embed(self, images: Sequence[Image.Image], batch_size: int = 16) -> np.ndarray:
        out = []
        for i in range(0, len(images), batch_size):
            batch = np.stack([preprocess(im) for im in images[i : i + batch_size]])
            out.append(self._session.run(None, {self._input: batch})[0])
        return np.concatenate(out) if out else np.zeros((0, 0), dtype=np.float32)


class SpeciesClassifier:
    def __init__(self, embedder: Embedder, head: LinearHead) -> None:
        self.embedder, self.head = embedder, head

    def classify(self, images: Sequence[Image.Image]) -> list[Prediction]:
        return self.head.predict(self.embedder.embed(images))
