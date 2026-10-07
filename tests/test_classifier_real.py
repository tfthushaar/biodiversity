"""The real DINOv2 backbone and the trained heads.

Skipped unless BACKBONE_ONNX points at the exported backbone, e.g.
    BACKBONE_ONNX=data/models/dinov2_vits14.onnx pytest tests/test_classifier_real.py
"""

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from biodiv.inference.classifier import Embedder, LinearHead

REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
HEADS = REPO / "models" / "heads"
BACKBONE = Path(os.environ.get("BACKBONE_ONNX", ""))

needs_backbone = pytest.mark.skipif(
    not BACKBONE.is_file(), reason="set BACKBONE_ONNX to the exported backbone to run"
)


# --- these need no backbone: they protect the committed heads from silent drift -------------


@pytest.mark.parametrize("task", ["plants", "animals"])
def test_committed_head_matches_its_class_list(task):
    path = HEADS / f"{task}.json"
    if not path.exists():
        pytest.skip(f"{task} head not trained yet")
    head = LinearHead.load(path)
    spec = json.loads((REPO / "docs" / "training" / f"{task[:-1]}_classes.json").read_text("utf-8"))
    assert head.classes == [c["name"] for c in spec["classes"]]
    assert head.dim == 768  # [CLS | mean patch] of a ViT-S/14
    assert 0.0 < head.threshold <= 1.0 and head.temperature > 0
    assert head.meta["task"] == task and len(head.meta["backbone_sha256"]) == 64
    assert np.isfinite(head.weights).all()


# --- the backbone itself ------------------------------------------------------------------


@pytest.fixture(scope="module")
def embedder():
    return Embedder(BACKBONE)


def photo(name):
    return Image.open(FIXTURES / name)


@needs_backbone
def test_embeddings_have_the_right_shape_and_are_finite(embedder):
    emb = embedder.embed([photo("camera_trap_animal.jpg"), photo("camera_trap_empty.jpg")])
    assert emb.shape == (2, 768) and np.isfinite(emb).all()


@needs_backbone
def test_embedding_is_deterministic_and_batch_independent(embedder):
    a, b = photo("camera_trap_animal.jpg"), photo("camera_trap_vehicle.jpg")
    alone = embedder.embed([a])[0]
    together = embedder.embed([a, b], batch_size=2)[0]
    np.testing.assert_allclose(alone, together, atol=1e-4)
    np.testing.assert_allclose(alone, embedder.embed([a])[0], atol=0)


@needs_backbone
def test_different_scenes_embed_differently_and_the_same_scene_stays_close(embedder):
    animal, vehicle = photo("camera_trap_animal.jpg"), photo("camera_trap_vehicle.jpg")
    e = embedder.embed([animal, vehicle, animal.resize((400, 300))])
    e = e / np.linalg.norm(e, axis=1, keepdims=True)
    assert float(e[0] @ e[2]) > float(e[0] @ e[1]) + 0.05  # a resized copy beats a different scene


@needs_backbone
def test_backbone_file_matches_the_hash_the_heads_were_trained_against(embedder):
    sha = hashlib.sha256(BACKBONE.read_bytes()).hexdigest()
    for task in ("plants", "animals"):
        path = HEADS / f"{task}.json"
        if path.exists():
            assert LinearHead.load(path).meta["backbone_sha256"] == sha, (
                f"{task} head was trained against a different backbone")
