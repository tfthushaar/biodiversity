import numpy as np
import pytest
from PIL import Image

from biodiv.inference.classifier import (
    SIZE,
    UNKNOWN,
    LinearHead,
    l2_normalise,
    preprocess,
    softmax,
)

CLASSES = ["lantana", "senna", "other"]


def head(threshold=0.0, temperature=1.0, dim=4):
    # Each class "owns" one axis of the embedding space.
    w = np.zeros((3, dim), dtype=np.float32)
    w[0, 0] = w[1, 1] = w[2, 2] = 8.0
    return LinearHead(CLASSES, w, np.zeros(3), temperature=temperature, threshold=threshold)


def test_preprocess_shape_dtype_and_normalisation():
    x = preprocess(Image.new("RGB", (640, 480), (124, 116, 104)))  # ~ImageNet mean colour
    assert x.shape == (3, SIZE, SIZE) and x.dtype == np.float32
    assert abs(float(x.mean())) < 0.05  # mean colour maps to ~0 after normalisation


@pytest.mark.parametrize("size", [(100, 400), (400, 100), (224, 224), (50, 50)])
def test_preprocess_handles_any_aspect_ratio_and_small_images(size):
    assert preprocess(Image.new("RGB", size)).shape == (3, SIZE, SIZE)


def test_preprocess_centre_crops_the_subject_not_the_edges():
    im = Image.new("RGB", (600, 300), (0, 0, 0))
    im.paste((255, 255, 255), (225, 0, 375, 300))  # a white band down the middle
    x = preprocess(im)
    assert x[0, SIZE // 2, SIZE // 2] > 1.5  # centre is white
    assert x[0, SIZE // 2, 2] < -1.5  # left edge of the crop is the dark side


def test_preprocess_accepts_grayscale_and_rgba():
    assert preprocess(Image.new("L", (300, 300))).shape == (3, SIZE, SIZE)
    assert preprocess(Image.new("RGBA", (300, 300))).shape == (3, SIZE, SIZE)


def test_softmax_is_a_probability_distribution_and_stable():
    p = softmax(np.array([[1000.0, 1001.0, 999.0]]))  # would overflow a naive exp
    assert np.isfinite(p).all() and p.sum() == pytest.approx(1.0)


def test_l2_normalise_and_zero_vector():
    assert np.linalg.norm(l2_normalise(np.array([[3.0, 4.0]]))) == pytest.approx(1.0)
    assert np.isfinite(l2_normalise(np.zeros((1, 4)))).all()


def test_head_predicts_the_class_whose_axis_the_embedding_points_along():
    emb = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 5, 0]], dtype=np.float32)
    assert [p.label for p in head().predict(emb)] == CLASSES


def test_a_confident_answer_is_named_an_unsure_one_is_unknown():
    clear = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    vague = np.array([[1.0, 1.0, 1.0, 0.0]], dtype=np.float32)  # equidistant from every class
    h = head(threshold=0.8)
    assert h.predict(clear)[0].label == "lantana"
    p = h.predict(vague)[0]
    assert p.label == UNKNOWN and not p.is_known
    assert p.best in CLASSES and p.probability < 0.8  # we still know what it leaned towards


def test_temperature_softens_without_changing_the_ranking():
    emb = np.array([[1.0, 0.4, 0.0, 0.0]], dtype=np.float32)
    sharp, soft = head(temperature=1.0), head(temperature=4.0)
    assert sharp.predict(emb)[0].best == soft.predict(emb)[0].best
    assert soft.predict(emb)[0].probability < sharp.predict(emb)[0].probability


def test_head_round_trips_through_json(tmp_path):
    original = head(threshold=0.7, temperature=1.3)
    original.meta = {"task": "plants"}
    path = tmp_path / "head.json"
    original.save(path)
    loaded = LinearHead.load(path)
    emb = np.random.default_rng(0).normal(size=(5, 4)).astype(np.float32)
    np.testing.assert_allclose(loaded.probabilities(emb), original.probabilities(emb), atol=1e-5)
    assert (loaded.threshold, loaded.temperature, loaded.meta) == (0.7, 1.3, {"task": "plants"})


def test_mismatched_head_is_rejected():
    with pytest.raises(ValueError):
        LinearHead(CLASSES, np.zeros((2, 4)), np.zeros(3))
