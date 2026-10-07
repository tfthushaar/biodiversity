"""Build the invasive-plant training set from iNaturalist (CC-licensed research-grade photos).

    python scripts/build_plant_dataset.py --per-class 140

Classes are the target invasive species, the native species they are most often confused with,
and an `other_plant` class of random plants so the model can say "none of these". Look-alikes are
chosen from iNaturalist's own confusion data, and only species iNaturalist records as NATIVE to
India qualify: calling a native plant invasive is the harmful mistake, so natives are the
negatives that matter. Writes data/plants/ (gitignored) plus docs/training/ (provenance).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PIL import Image

from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.observations import IMAGE_LICENSES
from biodiv.training.photos import TrainingPhoto, parse_photo

API = "https://api.inaturalist.org/v1"
INDIA = 6681
PLANTAE = 47126
LICENSES = ",".join(sorted(IMAGE_LICENSES))
UA = "biodiv-student-project/0.1 (+https://github.com/tfthushaar/biodiversity)"

# All are flagged invasive in India by GRIIS and are present in or near the pilot reserves.
INVASIVES = [
    "Lantana camara", "Senna spectabilis", "Chromolaena odorata", "Prosopis juliflora",
    "Parthenium hysterophorus", "Opuntia stricta", "Tridax procumbens", "Mikania micrantha",
    "Ageratina adenophora", "Eichhornia crassipes",
]
# Native look-alikes that iNaturalist's confusion list does not surface but botany does.
MANUAL_LOOKALIKES = {
    "Cassia fistula": "Golden shower tree: native, with yellow flower sprays easily mistaken for "
                      "Senna spectabilis, the invader the Western Ghats forest departments "
                      "once planted as a replacement for Lantana.",
    "Senna auriculata": "Tanner's cassia: a native yellow-flowered shrub of the same genus as "
                        "Senna spectabilis, chosen on botanical judgement (not from confusion "
                        "data).",
    "Vachellia nilotica": "Babul: a native thorny acacia with similar pinnate leaves, pods and "
                          "spines to Prosopis juliflora; chosen on botanical judgement (not from "
                          "confusion data).",
}
OTHER = "other_plant"
OUT = Path("data") / "plants"
DOCS = Path("docs") / "training"


async def resolve_taxon(api: PoliteClient, name: str) -> dict[str, Any]:
    results = (await api.get_json(f"{API}/taxa", {"q": name, "rank": "species", "per_page": 5}))[
        "results"
    ]
    # iNaturalist follows newer taxonomy than GRIIS (Prosopis juliflora is now Neltuma juliflora,
    # Eichhornia crassipes is Pontederia crassipes). `matched_term` says which old name hit.
    want = name.lower()
    exact = next(
        (t for t in results
         if t["name"].lower() == want or (t.get("matched_term") or "").lower() == want),
        None,
    )
    if exact is None:
        raise SystemExit(f"no iNaturalist species matches {name!r}")
    return exact


async def native_in_india(api: PoliteClient, taxon_id: int) -> str | None:
    full = (await api.get_json(f"{API}/taxa/{taxon_id}", {"place_id": INDIA}))["results"][0]
    return (full.get("establishment_means") or {}).get("establishment_means")


async def find_lookalikes(api: PoliteClient, invasive: dict[str, Any], keep: int) -> list[dict]:
    sim = (await api.get_json(
        f"{API}/identifications/similar_species", {"taxon_id": invasive["id"]}))["results"]
    found: list[dict] = []
    for s in sim:
        t = s["taxon"]
        if t["rank"] != "species" or t["id"] == invasive["id"]:
            continue
        status = await native_in_india(api, t["id"])
        if status in ("native", "endemic"):
            found.append({**t, "confused_with": invasive["name"], "times_confused": s["count"]})
            if len(found) == keep:
                break
    return found


async def photos_for(
    api: PoliteClient, label: str, taxon_id: int | None, want: int, india_share: float,
    without: list[int] | None = None,
) -> list[TrainingPhoto]:
    """India first (the region we care about), then anywhere to fill the quota."""
    got: dict[int, TrainingPhoto] = {}
    base: dict[str, Any] = {
        "quality_grade": "research", "photo_license": LICENSES, "captive": "false",
        "order_by": "random", "per_page": 200, "photos": "true",
        "taxon_id": taxon_id or PLANTAE,
    }
    if without:
        base["without_taxon_id"] = ",".join(map(str, without))
    for place, quota in ((INDIA, int(want * india_share)), (None, want)):
        params = dict(base, **({"place_id": place} if place else {}))
        for o in (await api.get_json(f"{API}/observations", params))["results"]:
            if len(got) >= quota:
                break
            if o["id"] not in got and (p := parse_photo(o, label)):
                got[o["id"]] = p
    return list(got.values())


async def download(photos: list[TrainingPhoto], root: Path) -> list[dict]:
    rows: list[dict] = []
    async with PoliteClient(user_agent=UA, per_second=20, max_concurrency=8) as http:

        async def one(p: TrainingPhoto) -> None:
            path = root / "images" / p.label / f"{p.observation_id}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if not path.exists():
                    path.write_bytes(await http.get_bytes(p.url))
                with Image.open(path) as im:
                    im.load()
            except Exception:
                path.unlink(missing_ok=True)
                return
            rows.append({**asdict(p), "in_india": p.in_india,
                         "file": str(path.relative_to(root)).replace("\\", "/")})

        await asyncio.gather(*(one(p) for p in photos))
    return sorted(rows, key=lambda r: (r["label"], r["observation_id"]))


async def extend(per_class: int, india_share: float) -> None:
    """Add any MANUAL_LOOKALIKES missing from an existing build, without redoing discovery."""
    spec = json.loads((DOCS / "plant_classes.json").read_text("utf-8"))
    classes = spec["classes"]
    have = {c["name"] for c in classes}
    rows = [json.loads(line) for line in (OUT / "manifest.jsonl").read_text("utf-8").splitlines()]
    new_photos: list[TrainingPhoto] = []
    async with PoliteClient(user_agent=UA, per_second=1.0, max_concurrency=1) as api:
        for name, why in MANUAL_LOOKALIKES.items():
            if name in have:
                continue
            t = await resolve_taxon(api, name)
            status = await native_in_india(api, t["id"])
            if status not in ("native", "endemic"):
                # No citable record, so we do not claim it: skip it rather than guess.
                print(f"  SKIPPED {name}: iNaturalist has no native record for India ({status!r})")
                continue
            ps = await photos_for(api, name, t["id"], per_class, india_share)
            entry = {"name": name, "taxon_id": t["id"], "kind": "native_lookalike",
                     "common_name": t.get("preferred_common_name"), "why": why, "photos": len(ps)}
            classes.insert(next(i for i, c in enumerate(classes) if c["kind"] == "other"), entry)
            new_photos += ps
            print(f"  added {name}: {len(ps)} photos ({sum(p.in_india for p in ps)} in India)")
    rows += await download(new_photos, OUT)
    rows.sort(key=lambda r: (r["label"], r["observation_id"]))
    write_outputs(rows, classes)


def write_outputs(rows: list[dict], classes: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    manifest = "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n"
    (OUT / "manifest.jsonl").write_text(manifest, encoding="utf-8")
    # The observer hash exists only to keep one photographer's photos on one side of a split. A
    # hash of a small integer id is easily reversed, so it is NOT safe to publish; neither are
    # exact coordinates. Provenance keeps what is needed to find the record, and nothing more.
    private = ("file", "observer", "lat", "lon")
    provenance = [{k: v for k, v in r.items() if k not in private} for r in rows]
    (DOCS / "plants_manifest.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in provenance) + "\n", encoding="utf-8")
    spec = {"classes": classes, "photo_licenses": sorted(IMAGE_LICENSES)}
    (DOCS / "plant_classes.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    counts = Counter(r["label"] for r in rows)
    print(f"\n{len(rows)} images across {len(counts)} classes; smallest: {min(counts.values())}")


async def build(per_class: int, india_share: float, other: int) -> None:
    async with PoliteClient(user_agent=UA, per_second=1.0, max_concurrency=1) as api:
        invasives = [await resolve_taxon(api, n) for n in INVASIVES]
        # Classes keep the GRIIS name we use everywhere else; iNaturalist's own name is recorded.
        classes: list[dict] = [
            {"name": want, "inat_name": t["name"], "taxon_id": t["id"], "kind": "invasive",
             "common_name": t.get("preferred_common_name")}
            for want, t in zip(INVASIVES, invasives, strict=True)]
        seen = {t["id"] for t in invasives}

        for inv in invasives:
            for t in await find_lookalikes(api, inv, keep=2):
                if t["id"] not in seen:
                    seen.add(t["id"])
                    classes.append({
                        "name": t["name"], "taxon_id": t["id"], "kind": "native_lookalike",
                        "common_name": t.get("preferred_common_name"),
                        "why": f"iNaturalist users confuse it with {t['confused_with']} "
                               f"({t['times_confused']} identifications); recorded native to India",
                    })
        for name, why in MANUAL_LOOKALIKES.items():
            t = await resolve_taxon(api, name)
            status = await native_in_india(api, t["id"])
            if status not in ("native", "endemic"):
                print(f"  SKIPPED {name}: iNaturalist has no native record for India ({status!r})")
                continue
            if t["id"] not in seen:
                seen.add(t["id"])
                classes.append({"name": name, "taxon_id": t["id"], "kind": "native_lookalike",
                                "common_name": t.get("preferred_common_name"), "why": why})

        photos: list[TrainingPhoto] = []
        for c in classes:
            ps = await photos_for(api, c["name"], c["taxon_id"], per_class, india_share)
            c["photos"] = len(ps)
            photos += ps
            print(f"  {c['kind']:17} {c['name']:28} {len(ps):4} photos "
                  f"({sum(p.in_india for p in ps)} in India)")
        ps = await photos_for(api, OTHER, None, other, 1.0, without=sorted(seen))
        classes.append({"name": OTHER, "taxon_id": None, "kind": "other", "photos": len(ps),
                        "why": "random plants from India, none of the classes above"})
        photos += ps
        print(f"  {'other':17} {OTHER:28} {len(ps):4} photos")

    rows = await download(photos, OUT)
    write_outputs(rows, classes)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--per-class", type=int, default=140)
    p.add_argument("--india-share", type=float, default=0.5,
                   help="fraction of each class to take from India before filling globally")
    p.add_argument("--other", type=int, default=400)
    p.add_argument("--extend", action="store_true",
                   help="only add missing manual look-alikes to an existing build")
    args = p.parse_args()
    if args.extend:
        asyncio.run(extend(args.per_class, args.india_share))
    else:
        asyncio.run(build(args.per_class, args.india_share, args.other))


if __name__ == "__main__":
    main()
