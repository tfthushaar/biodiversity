import numpy as np
import pytest
from PIL import Image

from biodiv.inference.megadetector import (
    INPUT_SIZE,
    Letterbox,
    letterbox,
    nms,
    postprocess,
    visible_box,
)

# A 200x100 image letterboxes to 640 wide: scale 3.2, content 640x320, 160px bars top/bottom.
LB = Letterbox(scale=3.2, pad_left=0, pad_top=160, width=200, height=100)
BOX_640 = [160.0, 240.0, 480.0, 400.0]  # the region (50,25)-(150,75) of the original image
STRONG, WEAK = 5.0, -5.0  # logits: sigmoid(5) = 0.993, sigmoid(-5) = 0.007


def logits(*rows):
    return np.array(rows, dtype=np.float32)


# ---------------------------------------------------------------- letterbox


def test_letterbox_preserves_aspect_ratio_and_pads_grey():
    chw, lb = letterbox(Image.new("RGB", (200, 100), (255, 0, 0)))
    assert chw.shape == (3, INPUT_SIZE, INPUT_SIZE) and chw.dtype == np.float32
    assert (lb.scale, lb.pad_left, lb.pad_top) == (3.2, 0, 160)
    assert 0.0 <= chw.min() and chw.max() <= 1.0
    np.testing.assert_allclose(chw[:, 10, 320], 114 / 255)  # top bar is grey
    np.testing.assert_allclose(chw[:, 320, 320], [1.0, 0.0, 0.0], atol=0.01)  # red content


def test_letterbox_handles_portrait_and_grayscale():
    _, lb = letterbox(Image.new("L", (100, 200)))  # grayscale is converted to RGB
    assert (lb.scale, lb.pad_left, lb.pad_top) == (3.2, 160, 0)


# ---------------------------------------------------------------------- nms


def test_nms_keeps_the_best_of_overlapping_boxes():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=float)
    assert nms(boxes, np.array([0.6, 0.9, 0.5]), iou_threshold=0.5) == [1, 2]


def test_nms_on_a_single_box():
    assert nms(np.array([[0, 0, 1, 1]], dtype=float), np.array([0.3]), 0.5) == [0]


# -------------------------------------------------------------- postprocess


def test_postprocess_maps_a_box_back_to_the_original_image():
    (det,) = postprocess(logits([STRONG, WEAK, WEAK]), np.array([BOX_640]), LB)
    assert det.label == "animal"
    assert det.confidence == pytest.approx(0.9933, abs=1e-3)
    np.testing.assert_allclose(det.box, (0.25, 0.25, 0.75, 0.75), atol=1e-6)


@pytest.mark.parametrize(("column", "label"), [(0, "animal"), (1, "person"), (2, "vehicle")])
def test_postprocess_class_order(column, label):
    row = [WEAK, WEAK, WEAK]
    row[column] = STRONG
    assert postprocess(logits(row), np.array([BOX_640]), LB)[0].label == label


def test_postprocess_drops_scores_below_the_confidence_threshold():
    weak = logits([0.0, WEAK, WEAK])  # sigmoid(0) = 0.5
    assert postprocess(weak, np.array([BOX_640]), LB, confidence=0.6) == []
    assert len(postprocess(weak, np.array([BOX_640]), LB, confidence=0.4)) == 1


def test_postprocess_suppresses_duplicates_within_a_class_only():
    two_same = np.array([BOX_640, [162, 242, 482, 402]])
    animals = postprocess(logits([STRONG, WEAK, WEAK], [4.0, WEAK, WEAK]), two_same, LB)
    assert len(animals) == 1  # near-identical boxes, same class: one survives, the better one
    assert animals[0].confidence == pytest.approx(0.9933, abs=1e-3)

    # The same two boxes as an animal and a person are different objects: both are kept.
    mixed = postprocess(logits([STRONG, WEAK, WEAK], [WEAK, STRONG, WEAK]), two_same, LB)
    assert sorted(d.label for d in mixed) == ["animal", "person"]


def test_postprocess_clips_boxes_that_spill_over_the_edge_and_drops_degenerate_ones():
    spill = np.array([[-50.0, 200.0, 100.0, 440.0]])  # starts in the left padding of the canvas
    (det,) = postprocess(logits([STRONG, WEAK, WEAK]), spill, LB)
    assert det.box[0] == 0.0
    flat = np.array([[100.0, 300.0, 100.0, 300.0]])  # zero area
    assert postprocess(logits([STRONG, WEAK, WEAK]), flat, LB) == []


def test_detections_lying_in_the_letterbox_padding_are_discarded():
    """Real case: the network fires in the grey bars, giving boxes outside the actual image."""
    above = np.array([[0.0, 0.0, 100.0, 100.0]])  # wholly in the top bar (y < 160)
    assert postprocess(logits([STRONG, WEAK, WEAK]), above, LB) == []
    sliver = np.array([[100.0, 100.0, 300.0, 161.0]])  # 1px of a 61px box is inside the image
    assert postprocess(logits([STRONG, WEAK, WEAK]), sliver, LB) == []


@pytest.mark.parametrize(
    ("box", "expected"),
    [
        ((0.2, 0.2, 0.6, 0.6), (0.2, 0.2, 0.6, 0.6)),  # inside: untouched
        ((-0.2, 0.2, 0.6, 0.6), (0.0, 0.2, 0.6, 0.6)),  # 75% visible: clipped, kept
        ((-0.6, 0.2, 0.2, 0.6), None),  # 25% visible: mostly outside
        ((0.2, 1.1, 0.6, 1.5), None),  # entirely outside
        ((0.5, 0.5, 0.5, 0.9), None),  # zero width
    ],
)
def test_visible_box(box, expected):
    got = visible_box(box)
    assert (got is None) == (expected is None)
    if expected:
        np.testing.assert_allclose(got, expected)


def test_postprocess_with_nothing_found():
    assert postprocess(logits([WEAK, WEAK, WEAK]), np.array([BOX_640]), LB) == []


def test_postprocess_orders_results_by_confidence():
    boxes = np.array([BOX_640, [10.0, 170.0, 100.0, 260.0]])
    dets = postprocess(logits([2.0, WEAK, WEAK], [STRONG, WEAK, WEAK]), boxes, LB)
    assert [round(d.confidence, 2) for d in dets] == [0.99, 0.88]
