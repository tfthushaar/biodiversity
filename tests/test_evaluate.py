import pytest

from biodiv.inference.evaluate import (
    ImageResult,
    box_iou,
    box_level,
    image_level,
    match_boxes,
)
from biodiv.inference.megadetector import Detection

A = (0.1, 0.1, 0.5, 0.5)
FAR = (0.6, 0.6, 0.9, 0.9)


def det(label, conf, box):
    return Detection(label, conf, box)


def test_box_iou():
    assert box_iou(A, A) == 1.0
    assert box_iou(A, FAR) == 0.0
    # Half-overlapping boxes of equal size: intersection 1/2, union 3/2 -> 1/3.
    assert box_iou((0, 0, 2, 1), (1, 0, 3, 1)) == pytest.approx(1 / 3)
    assert box_iou((0, 0, 0, 0), (0, 0, 0, 0)) == 0.0  # degenerate, no division by zero


def test_match_boxes_counts_hits_false_alarms_and_misses():
    preds = [det("animal", 0.9, A), det("animal", 0.8, (0.0, 0.7, 0.1, 0.8))]
    assert match_boxes(preds, [A, FAR]) == (1, 1, 1)  # one hit, one false alarm, one miss


def test_one_ground_truth_box_cannot_be_claimed_twice():
    twice = [det("animal", 0.9, A), det("animal", 0.8, A)]
    assert match_boxes(twice, [A]) == (1, 1, 0)  # the duplicate is a false positive


def test_the_more_confident_prediction_gets_the_match():
    near = (0.12, 0.1, 0.5, 0.5)
    preds = [det("animal", 0.4, A), det("animal", 0.95, near)]
    assert match_boxes(preds, [near], iou_threshold=0.99) == (1, 1, 0)


def test_image_level_confusion_and_rates():
    results = [
        ImageResult([("animal", A)], [det("animal", 0.9, A)]),  # hit
        ImageResult([("animal", A)], []),  # missed
        ImageResult([], [det("animal", 0.7, A)]),  # false alarm on an empty photo
        ImageResult([], []),  # correctly empty
        ImageResult([], [det("animal", 0.1, A)]),  # below threshold: ignored
    ]
    m = image_level(results, "animal", 0.5)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 2)
    assert m["precision"] == 0.5 and m["recall"] == 0.5
    assert m["false_alarm_rate"] == pytest.approx(1 / 3)  # 1 of 3 animal-free photos


def test_image_level_threshold_trades_recall_for_precision():
    results = [
        ImageResult([("animal", A)], [det("animal", 0.3, A)]),
        ImageResult([], [det("animal", 0.3, A)]),
    ]
    assert image_level(results, "animal", 0.2)["recall"] == 1.0
    assert image_level(results, "animal", 0.5)["recall"] == 0.0


def test_metrics_are_none_not_zero_when_undefined():
    only_empty = [ImageResult([], [])]
    m = image_level(only_empty, "animal", 0.5)
    assert m["precision"] is None and m["recall"] is None and m["f1"] is None


def test_labels_are_scored_separately():
    results = [ImageResult([("vehicle", A)], [det("animal", 0.9, A), det("vehicle", 0.9, A)])]
    assert image_level(results, "vehicle", 0.5)["tp"] == 1
    assert image_level(results, "animal", 0.5)["fp"] == 1
    assert box_level(results, "vehicle", 0.5)["recall"] == 1.0
