"""REST endpoints. Read-only, apart from the stateless photo-analysis ones, which store nothing."""

from __future__ import annotations

from typing import Any

import psycopg
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from biodiv.api.deps import ModelRegistry, get_conn, get_registry, rate_limited
from biodiv.api.uploads import read_image
from biodiv.core.settings import get_settings
from biodiv.inference.classifier import UNKNOWN, LinearHead
from biodiv.inference.pipeline import analyse

router = APIRouter(prefix="/api/v1")

NOTICE = (
    "A decision aid, not an identification. Confirm with a botanist or ranger before acting. "
    "Your image was analysed in memory and not stored."
)


# ------------------------------------------------------------------------- models


class Prob(BaseModel):
    label: str
    probability: float


class SpeciesAnswer(BaseModel):
    answer: str  # a class name, or "unknown" when not confident enough to name it
    best_guess: str
    probability: float


class AnimalFinding(BaseModel):
    label: str  # animal | person | vehicle
    confidence: float
    box: tuple[float, float, float, float]
    species: SpeciesAnswer | None = None


class AnimalResult(BaseModel):
    task: str = "animals"
    findings: list[AnimalFinding]
    species_named: bool
    notice: str = NOTICE + " People are never cropped or classified."


class SpeciesContext(BaseModel):
    scientific_name: str
    common_name: str | None
    invasive_in_india: bool | None
    establishment_means: str | None
    playbooks: int
    impact_findings: int


class PlantResult(BaseModel):
    task: str = "plants"
    answer: str
    best_guess: str
    probability: float
    threshold: float
    kind: str | None  # invasive | native_lookalike | other
    alternatives: list[Prob]
    context: SpeciesContext | None = None
    notice: str = NOTICE


# --------------------------------------------------------------------- helpers


def _need(model, name: str):
    if model is None:
        raise HTTPException(503, f"The {name} model is not available on this server.")
    return model


def species_context(conn: psycopg.Connection, name: str) -> SpeciesContext | None:
    row = conn.execute(
        """
        select s.scientific_name, s.common_name, i.is_invasive and i.origin_class = 'alien',
               i.establishment_means,
               (select count(*) from mitigation_playbooks p where p.species_id = s.id),
               (select count(*) from impact_findings f where f.invasive_species_id = s.id)
        from species s
        left join invasive_status i on i.species_id = s.id and i.country = 'IN'
        where lower(s.scientific_name) = lower(%s) order by s.id limit 1
        """,
        (name,),
    ).fetchone()
    return SpeciesContext(**dict(zip(
        ("scientific_name", "common_name", "invasive_in_india", "establishment_means",
         "playbooks", "impact_findings"), row, strict=True))) if row else None


def _optional_conn():
    """Context enrichment is a bonus: without a database the endpoint still answers."""
    url = get_settings().database_url
    if not url:
        yield None
        return
    with psycopg.connect(url) as conn:
        yield conn


# -------------------------------------------------------------------------- routes


@router.get("/models", tags=["meta"])
def models(registry: ModelRegistry = Depends(get_registry)) -> dict[str, Any]:
    """Which models this server can run, and what each head was trained to say."""
    out: dict[str, Any] = {"available": registry.availability(), "heads": {}}
    for task in ("plants", "animals"):
        classifier = registry.classifier(task)
        if classifier is not None:
            head: LinearHead = classifier.head
            out["heads"][task] = {"classes": head.classes, "threshold": head.threshold,
                                  "trained_on": head.meta.get("photos"),
                                  "split": head.meta.get("split")}
    return out


@router.post("/infer/animals", response_model=AnimalResult, tags=["infer"],
             dependencies=[Depends(rate_limited)])
def infer_animals(file: UploadFile = File(...),
                  registry: ModelRegistry = Depends(get_registry)) -> AnimalResult:
    """Find animals, people and vehicles in a camera-trap photo, and name each animal."""
    image = read_image(file, get_settings().max_upload_mb * 1024 * 1024)
    detector = _need(registry.detector, "detector")
    namer = registry.classifier("animals")  # optional: detection still works without it
    findings = analyse(image, detector, namer)
    return AnimalResult(
        species_named=namer is not None,
        findings=[
            AnimalFinding(
                label=f.label, confidence=round(f.confidence, 4),
                box=tuple(round(v, 4) for v in f.box),
                species=SpeciesAnswer(answer=f.species.label, best_guess=f.species.best,
                                      probability=round(f.species.probability, 4))
                if f.species else None)
            for f in findings
        ],
    )


@router.post("/infer/plants", response_model=PlantResult, tags=["infer"],
             dependencies=[Depends(rate_limited)])
def infer_plants(file: UploadFile = File(...),
                 registry: ModelRegistry = Depends(get_registry),
                 conn: psycopg.Connection | None = Depends(_optional_conn)) -> PlantResult:
    """Say which of the target invasive plants (or native look-alikes) a photo shows, or
    'unknown'. Calibrated: a probability of 0.9 means about nine in ten such answers are right."""
    image = read_image(file, get_settings().max_upload_mb * 1024 * 1024)
    classifier = _need(registry.classifier("plants"), "plant classifier")
    head = classifier.head
    probs = head.probabilities(classifier.embedder.embed([image]))[0]
    order = probs.argsort()[::-1]
    best = head.classes[int(order[0])]
    p = float(probs[order[0]])
    answer = best if p >= head.threshold else UNKNOWN
    kinds = head.meta.get("kinds", {})
    named_species = answer not in (UNKNOWN, "other_plant")
    return PlantResult(
        answer=answer, best_guess=best, probability=round(p, 4), threshold=head.threshold,
        kind=kinds.get(answer) if answer != UNKNOWN else None,
        alternatives=[Prob(label=head.classes[int(i)], probability=round(float(probs[i]), 4))
                      for i in order[:3]],
        context=species_context(conn, answer) if (named_species and conn is not None) else None,
    )


@router.get("/zones/{slug}/report", tags=["analysis"])
def zone_report_endpoint(slug: str, conn: psycopg.Connection = Depends(get_conn)) -> dict[str, Any]:
    """The precomputed three-layer report for a zone (refreshed by the analyse worker)."""
    row = conn.execute(
        "select z.slug, r.report, r.computed_at from zones z "
        "left join zone_reports r on r.zone_id = z.id where z.slug = %s", (slug,)).fetchone()
    if row is None:
        raise HTTPException(404, f"No zone called {slug!r}.")
    if row[1] is None:
        raise HTTPException(404, "No report has been computed for this zone yet.")
    return {"zone": row[0], "computed_at": row[2].isoformat(), "report": row[1]}
