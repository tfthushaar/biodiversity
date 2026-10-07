"""Metrics and calibration for the species classifiers.

The number that matters most is not accuracy. It is how often a *native* plant (or any plant that
is not one of the targets) gets confidently called an invasive one, because that mistake could
get a harmless plant cleared. `dangerous_errors` measures exactly that, and everything here is
plain NumPy so it can be unit-tested without a trained model.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a proportion. Honest about small samples."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def confusion_matrix(
    truth: Sequence[str], pred: Sequence[str], classes: Sequence[str]
) -> np.ndarray:
    """Rows are the true class, columns what was predicted.

    Answers that are not a known class ('unknown') go in an extra last column.
    """
    index = {c: i for i, c in enumerate(classes)}
    m = np.zeros((len(classes), len(classes) + 1), dtype=int)
    for t, p in zip(truth, pred, strict=True):
        m[index[t], index.get(p, len(classes))] += 1
    return m


def per_class(truth: Sequence[str], pred: Sequence[str], classes: Sequence[str]) -> dict:
    out = {}
    for c in classes:
        tp = sum(t == c and p == c for t, p in zip(truth, pred, strict=True))
        support = sum(t == c for t in truth)
        predicted = sum(p == c for p in pred)
        precision = tp / predicted if predicted else None
        recall = tp / support if support else None
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
        out[c] = {"support": support, "precision": precision, "recall": recall, "f1": f1}
    return out


@dataclass(frozen=True)
class Rate:
    count: int
    total: int

    @property
    def value(self) -> float | None:
        return self.count / self.total if self.total else None

    def as_dict(self) -> dict:
        lo, hi = wilson_interval(self.count, self.total)
        return {"count": self.count, "of": self.total, "rate": self.value,
                "ci95": [round(lo, 4), round(hi, 4)]}


def dangerous_errors(
    truth: Sequence[str], pred: Sequence[str], kinds: dict[str, str]
) -> tuple[Rate, Rate]:
    """(native-called-invasive rate, invasive-correctly-named rate).

    `kinds` maps a class to 'invasive', 'native_lookalike' or 'other'. A dangerous error is a
    prediction of any invasive class for a photo that truly is not one. An 'unknown' answer is
    never dangerous: declining to name a plant harms nobody.
    """
    harmless = [(t, p) for t, p in zip(truth, pred, strict=True) if kinds[t] != "invasive"]
    wrong = sum(kinds.get(p) == "invasive" for _, p in harmless)
    targets = [(t, p) for t, p in zip(truth, pred, strict=True) if kinds[t] == "invasive"]
    found = sum(t == p for t, p in targets)
    return Rate(wrong, len(harmless)), Rate(found, len(targets))


def dangerous_by_kind(
    truth: Sequence[str], pred: Sequence[str], kinds: dict[str, str]
) -> dict[str, Rate]:
    """Dangerous-error rate separately for each kind of non-target ('native_lookalike', 'other')."""
    out: dict[str, Rate] = {}
    for kind in sorted({k for k in kinds.values() if k != "invasive"}):
        pairs = [(t, p) for t, p in zip(truth, pred, strict=True) if kinds[t] == kind]
        wrong = sum(kinds.get(p) == "invasive" for _, p in pairs)
        out[kind] = Rate(wrong, len(pairs))
    return out


def log_loss(logits: np.ndarray, y: np.ndarray, temperature: float = 1.0) -> float:
    z = logits / temperature
    z = z - z.max(axis=1, keepdims=True)
    log_p = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
    return float(-log_p[np.arange(len(y)), y].mean())


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """The temperature that minimises validation log-loss, so probabilities mean what they say.

    Classifiers trained to separate classes are typically over-confident; dividing the logits by
    T > 1 fixes that without changing which class wins. Golden-section search on log T.
    """
    lo, hi = math.log(0.05), math.log(20.0)
    phi = (math.sqrt(5) - 1) / 2
    a, b = hi - phi * (hi - lo), lo + phi * (hi - lo)
    fa, fb = log_loss(logits, y, math.exp(a)), log_loss(logits, y, math.exp(b))
    for _ in range(60):
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - phi * (hi - lo)
            fa = log_loss(logits, y, math.exp(a))
        else:
            lo, a, fa = a, b, fb
            b = lo + phi * (hi - lo)
            fb = log_loss(logits, y, math.exp(b))
    return float(math.exp((lo + hi) / 2))


def expected_calibration_error(probs: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """Average gap between stated confidence and actual accuracy (0 = perfectly calibrated)."""
    conf, hit = probs.max(axis=1), probs.argmax(axis=1) == y
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        sel = (conf > lo) & (conf <= hi)
        if sel.any():
            ece += sel.mean() * abs(hit[sel].mean() - conf[sel].mean())
    return float(ece)


def pick_threshold(
    probs: np.ndarray,
    y: np.ndarray,
    classes: Sequence[str],
    kinds: dict[str, str],
    max_dangerous: float = 0.05,
    grid: Sequence[float] | None = None,
) -> float:
    """The lowest confidence threshold at which dangerous errors stay within budget.

    The budget applies to each kind of non-target SEPARATELY and the worst one counts. Pooling
    them hides problems: native look-alikes can be handled perfectly while random plants are
    called invasive 13% of the time, and the blended rate still looks acceptable.

    Lower is better because it names more plants. Chosen on the validation set, so the test set
    remains an honest check.
    """
    truth = [classes[i] for i in y]
    best = probs.argmax(axis=1)
    top = probs.max(axis=1)
    for tau in grid if grid is not None else np.round(np.arange(0.0, 1.0001, 0.01), 2):
        pred = [classes[b] if p >= tau else "unknown" for b, p in zip(best, top, strict=True)]
        rates = [r.value for r in dangerous_by_kind(truth, pred, kinds).values()
                 if r.value is not None]
        if rates and max(rates) <= max_dangerous:
            return float(tau)
    return 1.0


def pick_threshold_for_precision(
    probs: np.ndarray, y: np.ndarray, target: float = 0.95, min_coverage: float = 0.5
) -> float:
    """The lowest threshold at which the answers we do give are right at least `target` of the time.

    For tasks with no notion of a "dangerous" mistake (which animal is this?), the trade is
    between naming more photos and being right when we do. `min_coverage` stops it from
    reaching a high precision by answering almost nothing.
    """
    best, top = probs.argmax(axis=1), probs.max(axis=1)
    for tau in np.round(np.arange(0.0, 1.0001, 0.01), 2):
        answered = top >= tau
        if answered.mean() < min_coverage:
            break
        if (best[answered] == y[answered]).mean() >= target:
            return float(tau)
    return 1.0
