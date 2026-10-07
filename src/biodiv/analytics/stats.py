"""The statistics behind the impact analysis, in plain NumPy so each can be checked by hand.

Three pieces, each guarding against a specific way of fooling ourselves:

  * Rarefied richness. A place with more observations records more species simply because it
    was looked at more. Hurlbert's rarefaction asks instead: how many species would we expect
    to see in a fixed-size sample? That makes places with different effort comparable.
  * Spearman correlation with a bootstrap interval, because the relationships are monotone at
    best and the samples are small, so a bare coefficient would overstate what we know.
  * Mann-Kendall trend with the Theil-Sen slope, which needs no assumption of normality and is
    not thrown by one odd year.

Each returns None (or an explicit reason) instead of a number when the data cannot support one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


def rankdata(x: Sequence[float]) -> np.ndarray:
    """Ranks starting at 1, with tied values sharing their average rank."""
    a = np.asarray(x, dtype=float)
    order = np.argsort(a, kind="stable")
    ranks = np.empty(len(a), dtype=float)
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman's rho, or None if it is undefined (fewer than 3 points, or one side constant)."""
    if len(x) != len(y):
        raise ValueError("x and y must be the same length")
    if len(x) < 3:
        return None
    rx, ry = rankdata(x), rankdata(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def bootstrap_interval(
    x: Sequence[float], y: Sequence[float], n_boot: int = 2000, seed: int = 0, level: float = 0.95
) -> tuple[float, float] | None:
    """Percentile bootstrap interval for Spearman's rho. Deterministic for a given seed."""
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(xa), len(xa))
        r = spearman(xa[idx], ya[idx])
        if r is not None:
            draws.append(r)
    if len(draws) < n_boot // 2:
        return None  # too many degenerate resamples to trust
    tail = (1 - level) / 2 * 100
    lo, hi = np.percentile(draws, [tail, 100 - tail])
    return float(lo), float(hi)


def _log_comb(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def rarefied_richness(counts: Sequence[int], n: int) -> float | None:
    """Expected number of species in a random sample of n individuals (Hurlbert 1971).

    `counts` is the number of records of each species at a place. Returns None when the place has
    fewer than n records in total: it simply cannot be compared at that sample size.
    """
    counts = [c for c in counts if c > 0]
    total = sum(counts)
    if n < 1 or total < n:
        return None
    log_all = _log_comb(total, n)
    expected = 0.0
    for c in counts:
        absent = math.exp(_log_comb(total - c, n) - log_all) if total - c >= n else 0.0
        expected += 1.0 - absent
    return expected


@dataclass(frozen=True)
class Trend:
    n: int
    tau: float  # Kendall's tau: +1 always rising, -1 always falling
    p_value: float  # two-sided, normal approximation with tie correction
    slope: float  # Theil-Sen: median slope between every pair of points, per unit of time


def mann_kendall(t: Sequence[float], y: Sequence[float]) -> Trend | None:
    """Monotonic trend test. None for fewer than 4 points, where no test is meaningful."""
    t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    n = len(y)
    if n != len(t):
        raise ValueError("t and y must be the same length")
    if n < 4:
        return None
    s, slopes = 0, []
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += int(np.sign(y[j] - y[i])) * int(np.sign(t[j] - t[i]))
            if t[j] != t[i]:
                slopes.append((y[j] - y[i]) / (t[j] - t[i]))
    # Variance with a correction for tied values.
    _, tie_counts = np.unique(y, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - sum(c * (c - 1) * (2 * c + 5) for c in tie_counts)) / 18
    if var <= 0:
        return Trend(n, 0.0, 1.0, 0.0)
    z = 0.0 if s == 0 else (s - np.sign(s)) / math.sqrt(var)  # continuity correction
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    pairs = n * (n - 1) / 2
    return Trend(n, float(s / pairs), float(p), float(np.median(slopes)) if slopes else 0.0)
