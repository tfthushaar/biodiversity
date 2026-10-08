"""Train a classification head on top of the frozen backbone, and measure it on held-out data.

    python scripts/train_head.py plants
    python scripts/train_head.py animals

Embeds every training photo once with the same ONNX backbone used at runtime, fits a regularised
logistic regression, calibrates it, chooses the "name it or say unknown" threshold on a separate
validation set, and only then looks at the test set. The split is by PHOTOGRAPHER (plants) or by
CAMERA (animals), so the test measures people and cameras the model has never seen.

Needs scikit-learn (training only): pip install -e ".[train]"
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression

from biodiv.inference.classifier import Embedder, LinearHead, l2_normalise, softmax
from biodiv.training.metrics import (
    confusion_matrix,
    dangerous_by_kind,
    dangerous_errors,
    expected_calibration_error,
    fit_temperature,
    log_loss,
    per_class,
    pick_threshold,
    pick_threshold_for_precision,
)
from biodiv.training.photos import group_split

TASKS = {
    "plants": {
        "root": Path("data/plants"),
        "classes": Path("docs/training/plant_classes.json"),
        "out": Path("models/heads/plants.json"),
        "metrics": Path("docs/metrics/plants.json"),
        "split": "by observer",
        "mode": "safety",  # cap how often a non-target is called invasive
        "max_dangerous": 0.05,
    },
    "animals": {
        "root": Path("data/animals"),
        "classes": Path("docs/training/animal_classes.json"),
        "out": Path("models/heads/animals.json"),
        "metrics": Path("docs/metrics/animals.json"),
        "split": "by camera location",
        "mode": "precision",  # answers we give must be right this often
        "target_precision": 0.95,
    },
}
C_GRID = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def embed_all(
    rows: list[dict], root: Path, embedder: Embedder, cache: Path, key: str
) -> np.ndarray:
    """Embeddings for every row, cached against the backbone's hash so a stale one is never used."""
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        if str(z["key"]) == key and len(z["emb"]) == len(rows):
            return z["emb"]
    out = []
    for i in range(0, len(rows), 64):
        ims = []
        for r in rows[i : i + 64]:
            with Image.open(root / r["file"]) as im:
                ims.append(im.convert("RGB").copy())
        out.append(embedder.embed(ims))
        print(f"  embedded {min(i + 64, len(rows))}/{len(rows)}", end="\r")
    emb = np.concatenate(out)
    np.savez(cache, emb=emb, key=key)
    print()
    return emb


def report(name: str, truth: list[str], pred: list[str], classes: list[str], kinds: dict) -> dict:
    known = [p != "unknown" for p in pred]
    answered = [(t, p) for t, p in zip(truth, pred, strict=True) if p != "unknown"]
    out = {
        "split": name, "photos": len(truth),
        "top1_accuracy": sum(t == p for t, p in zip(truth, pred, strict=True)) / len(truth),
        "answered": sum(known) / len(truth),
        "accuracy_when_answered": (sum(t == p for t, p in answered) / len(answered))
        if answered else None,
        "per_class": per_class(truth, pred, classes),
    }
    if "invasive" in kinds.values():
        danger, found = dangerous_errors(truth, pred, kinds)
        out["dangerous_errors"] = danger.as_dict()  # a non-target called invasive
        out["dangerous_errors_by_kind"] = {
            kind: rate.as_dict() for kind, rate in dangerous_by_kind(truth, pred, kinds).items()}
        out["invasives_correctly_named"] = found.as_dict()
    return out


def fit(emb: np.ndarray, y: np.ndarray, train: list[int], c: float) -> LogisticRegression:
    clf = LogisticRegression(C=c, max_iter=3000, class_weight="balanced")
    return clf.fit(emb[train], y[train])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("task", choices=sorted(TASKS))
    p.add_argument("--backbone", type=Path, default=Path("data/models/dinov2_vits14.onnx"))
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()
    cfg = TASKS[args.task]
    root: Path = cfg["root"]

    rows = [json.loads(line) for line in (root / "manifest.jsonl").read_text("utf-8").splitlines()]
    spec = json.loads(cfg["classes"].read_text("utf-8"))["classes"]
    classes = [c["name"] for c in spec]
    kinds = {c["name"]: c["kind"] for c in spec}
    print(f"{len(rows)} photos, {len(classes)} classes")

    backbone_hash = sha256(args.backbone)
    emb = embed_all(rows, root, Embedder(args.backbone), root / "embeddings.npz", backbone_hash)
    emb = l2_normalise(emb)
    y = np.array([classes.index(r["label"]) for r in rows])

    idx = list(range(len(rows)))
    train, val, test = group_split(idx, lambda i: rows[i]["observer"], (0.6, 0.2, 0.2), args.seed)
    for name, part in (("train", train), ("val", val), ("test", test)):
        print(f"  {name:5} {len(part):5} photos, {len({rows[i]['observer'] for i in part}):4} "
              f"groups, {len(set(y[part]))}/{len(classes)} classes present")

    # Regularisation strength: the best validation log-loss.
    best = None
    for c in C_GRID:
        clf = fit(emb, y, train, c)
        z = np.full((len(val), len(classes)), -30.0)
        z[:, clf.classes_] = clf.decision_function(emb[val])
        loss, acc = log_loss(z, y[val]), (z.argmax(1) == y[val]).mean()
        print(f"  C={c:<6} val log-loss {loss:.4f}  val accuracy {acc:.3f}")
        if best is None or loss < best[0]:
            best = (loss, c, clf)
    _, c_best, clf = best

    def logits(part: list[int]) -> np.ndarray:
        z = np.full((len(part), len(classes)), -30.0)  # a class absent from training can't win
        z[:, clf.classes_] = clf.decision_function(emb[part])
        return z

    temperature = fit_temperature(logits(val), y[val])
    pv = softmax(logits(val) / temperature)
    if cfg["mode"] == "safety":
        tau = pick_threshold(pv, y[val], classes, kinds, cfg["max_dangerous"])
    else:
        tau = pick_threshold_for_precision(pv, y[val], cfg["target_precision"])
    print(f"chosen C={c_best}, temperature={temperature:.2f}, threshold={tau:.2f} "
          f"(val calibration error {expected_calibration_error(pv, y[val]):.3f})")

    def predict(part: list[int]) -> tuple[list[str], np.ndarray]:
        probs = softmax(logits(part) / temperature)
        return [classes[i] if probs[k, i] >= tau else "unknown"
                for k, i in enumerate(probs.argmax(1))], probs

    all_kinds = {**kinds, "unknown": "other"}
    results = {}
    for name, part in (("validation", val), ("test", test)):
        pred, probs = predict(part)
        truth = [classes[i] for i in y[part]]
        results[name] = report(name, truth, pred, classes, all_kinds)
        results[name]["calibration_error"] = expected_calibration_error(probs, y[part])
        results[name]["confusion"] = confusion_matrix(truth, pred, classes).tolist()
    india = [i for i in test if rows[i].get("in_india")]
    if india:
        ipred, _ = predict(india)
        results["test_india_only"] = report(
            "test_india_only", [classes[i] for i in y[india]], ipred, classes, all_kinds)

    raw_pred = softmax(logits(test) / temperature).argmax(1)
    raw_top1 = float((raw_pred == y[test]).mean())

    # How the threshold trades answering more photos against being wrong. This is the dial a
    # user turns; the shipped value was fixed on the validation set, not read off this table.
    probs_t = softmax(logits(test) / temperature)
    top_t, best_t = probs_t.max(1), probs_t.argmax(1)
    truth_t = np.array([classes[i] for i in y[test]])
    tradeoff = []
    for tau_ in (0.3, 0.5, 0.6, 0.7, 0.76, 0.8, 0.9, 0.95):
        ok = top_t >= tau_
        hit = np.array(classes)[best_t] == truth_t
        row = {"threshold": tau_, "answered": float(ok.mean()),
               "accuracy_when_answered": float(hit[ok].mean()) if ok.any() else None}
        if "invasive" in kinds.values():
            pred_ = [classes[b] if o else "unknown" for b, o in zip(best_t, ok, strict=True)]
            danger_, named_ = dangerous_errors(list(truth_t), pred_, all_kinds)
            row["invasives_named"] = named_.as_dict()
            by_kind = dangerous_by_kind(list(truth_t), pred_, all_kinds)
            row["non_target_called_invasive"] = {k: r.as_dict() for k, r in by_kind.items()}
        tradeoff.append(row)
    extra: dict = {}
    if cfg["split"] == "by camera location":
        # What does unseen-camera testing cost us? Compare with a leaky random split where the
        # same cameras appear on both sides: the usual, flattering way to report accuracy.
        rng = np.random.default_rng(args.seed)
        order = rng.permutation(len(rows)).tolist()
        n_tr, n_va = len(train), len(val)
        r_train, r_test = order[:n_tr], order[n_tr + n_va :]
        leaky = fit(emb, y, r_train, c_best)
        z = np.full((len(r_test), len(classes)), -30.0)
        z[:, leaky.classes_] = leaky.decision_function(emb[r_test])
        same = float((z.argmax(1) == y[r_test]).mean())
        extra = {"same_cameras_top1": same, "new_cameras_top1": raw_top1,
                 "generalisation_gap": same - raw_top1}
        print(f"\nSame cameras on both sides: {same:.3f} | cameras never seen: {raw_top1:.3f} "
              f"| gap {same - raw_top1:+.3f}")

    w = np.zeros((len(classes), emb.shape[1]))
    b = np.full(len(classes), -30.0)
    w[clf.classes_] = clf.coef_
    b[clf.classes_] = clf.intercept_
    head = LinearHead(
        classes, w, b, temperature=temperature, threshold=tau,
        meta={
            "task": args.task, "kinds": kinds, "backbone_sha256": backbone_hash,
            "regularisation_C": c_best, "seed": args.seed, "split": cfg["split"] + " 60/20/20",
            "photos": {"train": len(train), "val": len(val), "test": len(test)},
        },
    )
    cfg["out"].parent.mkdir(parents=True, exist_ok=True)
    head.save(cfg["out"])
    cfg["metrics"].parent.mkdir(parents=True, exist_ok=True)
    cfg["metrics"].write_text(json.dumps({
        "task": args.task, "classes": classes, "kinds": kinds, "split": cfg["split"],
        "chosen": {"C": c_best, "temperature": temperature, "threshold": tau},
        "test_top1_without_threshold": raw_top1,
        "majority_class_baseline": max(Counter(y[test]).values()) / len(test),
        **extra,
        "threshold_tradeoff_on_test": tradeoff,
        "results": results,
    }, indent=2) + "\n", encoding="utf-8")

    t = results["test"]
    print(f"\nTEST ({t['photos']} photos, {cfg['split']}):")
    print(f"  top-1 accuracy {raw_top1:.3f} without a threshold | answers {t['answered']:.3f} of "
          f"photos at threshold {tau:.2f}, right {t['accuracy_when_answered']:.3f} of the time")
    if "dangerous_errors" in t:
        d, f = t["dangerous_errors"], t["invasives_correctly_named"]
        print(f"  non-target called invasive: {d['count']}/{d['of']} = {d['rate']:.3f} "
              f"(95% CI {d['ci95'][0]:.3f}-{d['ci95'][1]:.3f})")
        for kind, r in t["dangerous_errors_by_kind"].items():
            print(f"      of which {kind:17} {r['count']}/{r['of']} = {r['rate']:.3f} "
                  f"(95% CI {r['ci95'][0]:.3f}-{r['ci95'][1]:.3f})")
        print(f"  invasives correctly named:  {f['count']}/{f['of']} = {f['rate']:.3f} "
              f"(95% CI {f['ci95'][0]:.3f}-{f['ci95'][1]:.3f})")
    print(f"wrote {cfg['out']} ({cfg['out'].stat().st_size // 1024} KB) and {cfg['metrics']}")


if __name__ == "__main__":
    main()
