"""Record each model and its measured accuracy in the database, for the dashboard's Model page.

    python -m biodiv.workers.register_models

Reads the evaluation files the training scripts write (docs/metrics/*.json) and the trained heads
(models/heads/*.json). Safe to re-run; the numbers shown on the dashboard are exactly these.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg

from biodiv.core.settings import get_settings
from biodiv.inference.classifier import LinearHead
from biodiv.workers.detect import ensure_model_version, summarise_metrics

ROOT = Path(__file__).resolve().parents[3]
CAVEATS = {
    "plants": [
        "Trained on naturalist close-ups; ranger snapshots taken from a distance are a "
        "different distribution, and that shift is unmeasured.",
        "Zero native look-alikes called invasive is the absence of observed errors, not proof of "
        "none: the 95% interval reaches 3.3%.",
        "It labels a photo. It cannot say how much ground a species covers.",
    ],
    "animals": [
        "North American species from Caltech Camera Traps: a demonstration of the pipeline and a "
        "measure of generalisation, not a model of Indian or African fauna.",
        "The 'same cameras' figure also lets near-identical burst frames fall on both sides, so "
        "part of the gap to unseen cameras is leakage.",
    ],
}


def head_metrics(task: str, head: LinearHead, report: dict) -> dict:
    test = report["results"]["test"]
    return {
        "classes": report["classes"],
        "kinds": report["kinds"],
        "split": report["split"],
        "chosen": report["chosen"],
        "test_photos": test["photos"],
        "test_top1_without_threshold": report["test_top1_without_threshold"],
        "majority_class_baseline": report["majority_class_baseline"],
        "answered": test["answered"],
        "accuracy_when_answered": test["accuracy_when_answered"],
        "dangerous_errors": test.get("dangerous_errors"),
        "dangerous_errors_by_kind": test.get("dangerous_errors_by_kind"),
        "invasives_correctly_named": test.get("invasives_correctly_named"),
        "india_only": report["results"].get("test_india_only"),
        "same_cameras_top1": report.get("same_cameras_top1"),
        "new_cameras_top1": report.get("new_cameras_top1"),
        "per_class": test["per_class"],
        "threshold_tradeoff_on_test": report["threshold_tradeoff_on_test"],
        "backbone_sha256": head.meta.get("backbone_sha256"),
        "caveats": CAVEATS[task],
    }


def register(conn: psycopg.Connection) -> list[str]:
    done = []
    detector_report = ROOT / "docs" / "metrics" / "megadetector_caltech.json"
    if detector_report.exists():
        report = json.loads(detector_report.read_text("utf-8"))
        ensure_model_version(
            conn, "MDV6-mit-yolov9-c", report["model"]["source"], summarise_metrics(report))
        done.append("detector")
    for task, kind in (("plants", "plant_classifier"), ("animals", "animal_classifier")):
        head_file = ROOT / "models" / "heads" / f"{task}.json"
        report_file = ROOT / "docs" / "metrics" / f"{task}.json"
        if head_file.exists() and report_file.exists():
            head = LinearHead.load(head_file)
            report = json.loads(report_file.read_text("utf-8"))
            ensure_model_version(conn, f"{task}-head-dinov2-vits14", f"models/heads/{task}.json",
                                 head_metrics(task, head, report), task=kind)
            done.append(kind)
    return done


def main() -> int:
    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        print("registered:", ", ".join(register(conn)) or "nothing (no metrics files found)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
