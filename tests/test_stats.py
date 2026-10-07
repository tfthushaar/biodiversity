import itertools
import math
import random

import numpy as np
import pytest

from biodiv.analytics.stats import (
    bootstrap_interval,
    mann_kendall,
    rankdata,
    rarefied_richness,
    spearman,
)

# -------------------------------------------------------------------- ranks


def test_rankdata_gives_tied_values_their_average_rank():
    assert rankdata([10, 20, 20, 30]).tolist() == [1.0, 2.5, 2.5, 4.0]
    assert rankdata([3, 1, 2]).tolist() == [3.0, 1.0, 2.0]
    assert rankdata([5, 5, 5]).tolist() == [2.0, 2.0, 2.0]


# ------------------------------------------------------------------ spearman


def test_spearman_known_cases():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    # Monotone but not linear still gives exactly 1.
    assert spearman([1, 2, 3, 4, 5], [1, 4, 9, 16, 25]) == pytest.approx(1.0)


def test_spearman_is_undefined_not_zero_when_it_cannot_be_computed():
    assert spearman([1, 2], [1, 2]) is None  # too few points
    assert spearman([1, 2, 3], [7, 7, 7]) is None  # one side constant
    with pytest.raises(ValueError):
        spearman([1, 2, 3], [1, 2])


def test_spearman_matches_scipy_including_ties():
    stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(3)
    x = rng.integers(0, 6, 60).astype(float)  # lots of ties
    y = x + rng.normal(0, 2, 60)
    assert spearman(x, y) == pytest.approx(stats.spearmanr(x, y).statistic, abs=1e-12)


# ----------------------------------------------------------------- bootstrap


def test_bootstrap_interval_brackets_the_estimate_and_is_reproducible():
    rng = np.random.default_rng(0)
    x = rng.normal(size=80)
    y = 0.7 * x + rng.normal(scale=0.7, size=80)
    lo, hi = bootstrap_interval(x, y, seed=1)
    assert lo < spearman(x, y) < hi
    assert (lo, hi) == bootstrap_interval(x, y, seed=1)


def test_a_real_relationship_excludes_zero_and_pure_noise_does_not():
    rng = np.random.default_rng(1)
    x = rng.normal(size=100)
    lo, hi = bootstrap_interval(x, x + rng.normal(scale=0.5, size=100))
    assert lo > 0.3
    lo, hi = bootstrap_interval(x, rng.normal(size=100))
    assert lo < 0 < hi


def test_a_small_sample_gives_a_much_wider_interval_than_a_large_one():
    def width(n):
        rng = np.random.default_rng(2)
        x = rng.normal(size=n)
        y = x + rng.normal(size=n)
        lo, hi = bootstrap_interval(x, y, seed=0)
        return hi - lo

    assert width(12) > 2 * width(300)  # twelve points cannot pin a correlation down


# ------------------------------------------------------------ rarefaction


def test_rarefied_richness_known_values():
    # Two species, five records each. A sample of 2 sees one species unless it draws one of each.
    # P(both same) = 2*C(5,2)/C(10,2) = 20/45, so E[S] = 1 * 20/45 + 2 * 25/45 = 70/45.
    assert rarefied_richness([5, 5], 2) == pytest.approx(70 / 45)
    assert rarefied_richness([5, 5], 1) == pytest.approx(1.0)
    assert rarefied_richness([5, 5], 10) == pytest.approx(2.0)  # the whole sample: all species
    assert rarefied_richness([10], 3) == pytest.approx(1.0)  # one species can only ever be one


def test_rarefied_richness_refuses_a_sample_larger_than_the_data():
    assert rarefied_richness([2, 1], 10) is None
    assert rarefied_richness([], 1) is None
    assert rarefied_richness([3], 0) is None


def test_rarefaction_predicts_the_richness_of_smaller_samples():
    """The reason it exists. Raw richness grows with effort, so a heavily sampled place looks
    richer. Rarefied to a common size it predicts what a lightly sampled place would have shown."""
    rng = random.Random(0)
    community = [f"sp{i}" for i in range(30)]
    weights = [1 / (i + 1) for i in range(30)]  # a few common species, a long tail of rare ones

    def counts(sample):
        return [sample.count(s) for s in set(sample)]

    big = rng.choices(community, weights, k=2000)
    small_samples = [rng.choices(community, weights, k=60) for _ in range(300)]
    mean_small = sum(len(set(s)) for s in small_samples) / len(small_samples)

    assert len(set(big)) > mean_small + 3  # raw richness is biased upward by effort
    predicted = rarefied_richness(counts(big), 60)
    assert predicted == pytest.approx(mean_small, rel=0.05)  # rarefaction removes that bias


def test_rarefied_richness_matches_brute_force_expectation():
    counts = [3, 2, 1]
    pool = [0] * 3 + [1] * 2 + [2] * 1
    n = 3
    samples = list(itertools.combinations(range(len(pool)), n))
    brute = sum(len({pool[i] for i in s}) for s in samples) / len(samples)
    assert rarefied_richness(counts, n) == pytest.approx(brute)


# --------------------------------------------------------------- mann-kendall


def test_mann_kendall_detects_a_steady_rise_fall_and_nothing():
    years = list(range(2015, 2025))
    up = mann_kendall(years, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert up.tau == pytest.approx(1.0) and up.p_value < 0.001 and up.slope == pytest.approx(1.0)
    down = mann_kendall(years, [10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
    assert down.tau == pytest.approx(-1.0) and down.slope == pytest.approx(-1.0)
    flat = mann_kendall(years, [5] * 10)
    assert flat.tau == 0.0 and flat.p_value == 1.0 and flat.slope == 0.0


def test_mann_kendall_is_not_fooled_by_one_outlier():
    years = list(range(2015, 2025))
    y = [1, 2, 3, 4, 5, 6, 7, 8, 9, 500]  # one wild year
    assert mann_kendall(years, y).slope == pytest.approx(1.0)  # Theil-Sen ignores it


def test_mann_kendall_declines_to_test_tiny_series():
    assert mann_kendall([1, 2, 3], [1, 2, 3]) is None


def test_mann_kendall_matches_scipy():
    stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(5)
    t = np.arange(14.0)
    y = 0.3 * t + rng.normal(scale=2.0, size=14)
    mine = mann_kendall(t, y)
    assert mine.tau == pytest.approx(stats.kendalltau(t, y).statistic, abs=1e-12)
    assert mine.slope == pytest.approx(stats.theilslopes(y, t).slope, abs=1e-9)
    # SciPy's exact p differs slightly from the normal approximation; they should agree closely.
    assert mine.p_value == pytest.approx(stats.kendalltau(t, y).pvalue, abs=0.03)


def test_mann_kendall_noise_is_usually_not_significant():
    rng = np.random.default_rng(11)
    hits = sum(
        mann_kendall(np.arange(12.0), rng.normal(size=12)).p_value < 0.05 for _ in range(400)
    )
    assert hits / 400 < 0.09  # roughly the 5% a calibrated test should produce


def test_unequal_lengths_are_rejected():
    with pytest.raises(ValueError):
        mann_kendall([1, 2, 3, 4], [1, 2, 3])
    assert math.isfinite(mann_kendall([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]).p_value)
