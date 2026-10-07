import numpy as np
import pytest

from biodiv.training.metrics import (
    Rate,
    confusion_matrix,
    dangerous_errors,
    expected_calibration_error,
    fit_temperature,
    log_loss,
    per_class,
    pick_threshold,
    wilson_interval,
)

CLASSES = ["lantana", "senna", "fistula", "other"]
KINDS = {"lantana": "invasive", "senna": "invasive", "fistula": "native_lookalike",
         "other": "other", "unknown": "other"}


def test_wilson_interval_widens_for_small_samples():
    small = wilson_interval(1, 5)
    large = wilson_interval(200, 1000)
    assert (small[1] - small[0]) > 3 * (large[1] - large[0])
    assert wilson_interval(0, 10)[0] == 0.0  # never negative
    assert wilson_interval(10, 10)[1] == 1.0  # never above 1
    assert wilson_interval(0, 0) == (0.0, 1.0)  # no data: total ignorance
    lo, hi = wilson_interval(50, 100)
    assert lo < 0.5 < hi and hi - lo == pytest.approx(0.19, abs=0.01)  # the textbook value


def test_confusion_matrix_puts_declined_answers_in_the_last_column():
    m = confusion_matrix(["a", "a", "b"], ["a", "unknown", "b"], ["a", "b"])
    assert m.tolist() == [[1, 0, 1], [0, 1, 0]]


def test_per_class_precision_recall_and_undefined_cases():
    s = per_class(["a", "a", "b", "b"], ["a", "b", "b", "b"], ["a", "b", "c"])
    assert s["a"]["precision"] == 1.0 and s["a"]["recall"] == 0.5
    assert s["b"]["precision"] == pytest.approx(2 / 3) and s["b"]["recall"] == 1.0
    assert s["c"]["precision"] is None and s["c"]["recall"] is None  # not made up as zero


def test_dangerous_error_is_a_non_target_called_invasive():
    truth = ["fistula", "fistula", "other", "lantana", "senna", "senna"]
    pred = ["senna", "fistula", "unknown", "lantana", "lantana", "unknown"]
    danger, found = dangerous_errors(truth, pred, KINDS)
    assert (danger.count, danger.total) == (1, 3)  # the fistula called senna; unknown is safe
    assert (found.count, found.total) == (1, 3)  # only lantana was named correctly


def test_confusing_two_invasives_is_not_a_dangerous_error():
    """Calling a senna a lantana is wrong, but both are invasive: nothing native is at risk."""
    danger, found = dangerous_errors(["senna"], ["lantana"], KINDS)
    assert danger.total == 0 and found.value == 0.0


def test_rate_reports_a_confidence_interval():
    d = Rate(3, 100).as_dict()
    assert d["count"] == 3 and d["of"] == 100 and d["rate"] == 0.03
    assert d["ci95"][0] < 0.03 < d["ci95"][1]
    assert Rate(0, 0).value is None


def test_temperature_scaling_fixes_overconfidence():
    rng = np.random.default_rng(0)
    n = 4000
    y = rng.integers(0, 3, n)
    logits = rng.normal(size=(n, 3))
    logits[np.arange(n), y] += 1.0  # genuinely informative, but weakly
    overconfident = logits * 5.0  # the same ranking, claimed with far too much certainty
    t = fit_temperature(overconfident, y)
    assert t > 3.0  # it discovers the logits need dividing by roughly 5
    assert log_loss(overconfident, y, t) < log_loss(overconfident, y, 1.0)


def test_temperature_scaling_leaves_a_calibrated_model_alone():
    rng = np.random.default_rng(1)
    logits = rng.normal(size=(5000, 3)) * 2
    p = np.exp(logits) / np.exp(logits).sum(1, keepdims=True)
    y = np.array([rng.choice(3, p=row) for row in p])  # labels drawn from the model's own beliefs
    assert fit_temperature(logits, y) == pytest.approx(1.0, abs=0.15)


def test_expected_calibration_error():
    y = np.zeros(1000, dtype=int)
    sure_and_right = np.tile([0.99, 0.01], (1000, 1))
    assert expected_calibration_error(sure_and_right, y) < 0.02
    sure_but_wrong = np.tile([0.01, 0.99], (1000, 1))
    assert expected_calibration_error(sure_but_wrong, y) > 0.9


def test_threshold_is_the_lowest_one_that_meets_the_safety_budget():
    # Three confidently-right invasives; one native confidently mistaken (0.95), one
    # tentatively mistaken (0.55).
    probs = np.array([
        [0.97, 0.01, 0.01, 0.01],  # lantana, correct
        [0.01, 0.96, 0.02, 0.01],  # senna, correct
        [0.02, 0.95, 0.02, 0.01],  # fistula called senna at 0.95  (dangerous unless tau > 0.95)
        [0.05, 0.55, 0.30, 0.10],  # fistula called senna at 0.55
    ])
    y = np.array([0, 1, 2, 2])
    # Allowing 0 of 2 natives to be mistaken forces the threshold above both bad answers.
    tau = pick_threshold(probs, y, CLASSES, KINDS, max_dangerous=0.0)
    assert 0.95 < tau <= 0.96
    # A 50% budget lets one of the two natives through. The cheapest way to stay inside it is to
    # decline the tentative mistake (0.55); the confident one (0.95) is the one that slips by.
    assert 0.55 < pick_threshold(probs, y, CLASSES, KINDS, max_dangerous=0.5) <= 0.95


def test_precision_threshold_trades_coverage_for_accuracy():
    #            conf   right?
    probs = np.array([
        [0.99, 0.01],  # 0.99 correct
        [0.95, 0.05],  # 0.95 correct
        [0.90, 0.10],  # 0.90 correct
        [0.70, 0.30],  # 0.70 WRONG (true class is 1)
        [0.60, 0.40],  # 0.60 WRONG
    ])
    y = np.array([0, 0, 0, 1, 1])
    from biodiv.training.metrics import pick_threshold_for_precision

    # Answering everything is only 60% right; to reach 100% it must stop below 0.90.
    tau = pick_threshold_for_precision(probs, y, target=1.0, min_coverage=0.5)
    assert 0.70 < tau <= 0.90
    # Demanding perfection while forced to answer nearly everything cannot be satisfied.
    assert pick_threshold_for_precision(probs, y, target=1.0, min_coverage=0.9) == 1.0


def test_the_safety_budget_applies_to_each_kind_of_non_target_not_their_average():
    """Regression from real data: look-alikes were handled perfectly (0 of 113) while random
    plants were called invasive 13% of the time. Pooling them gave a comfortable ~6% and hid it."""
    from biodiv.training.metrics import dangerous_by_kind

    truth = ["fistula"] * 10 + ["other"] * 10
    pred = ["fistula"] * 10 + ["senna"] * 2 + ["other"] * 8  # 0/10 look-alikes, 2/10 random
    by_kind = dangerous_by_kind(truth, pred, KINDS)
    assert (by_kind["native_lookalike"].count, by_kind["other"].count) == (0, 2)
    pooled, _ = dangerous_errors(truth, pred, KINDS)
    assert pooled.value == pytest.approx(0.10)  # the blended figure looks fine under a 15% budget

    # Two groups: look-alikes always scored low on invasives; random plants sometimes scored high.
    probs = np.array([[0.05, 0.05, 0.85, 0.05]] * 10          # look-alikes: confident, correct
                     + [[0.05, 0.90, 0.03, 0.02]] * 2         # random plants wrongly sure of senna
                     + [[0.05, 0.05, 0.05, 0.85]] * 8)        # random plants correctly 'other'
    y = np.array([2] * 10 + [3] * 10)
    # Pooled error at tau=0.0 is 2/20 = 10%, within a 12% budget, but random plants alone are
    # 20% wrong. Per-kind budgeting must refuse that and push the threshold above 0.90.
    assert pick_threshold(probs, y, CLASSES, KINDS, max_dangerous=0.12) > 0.90
