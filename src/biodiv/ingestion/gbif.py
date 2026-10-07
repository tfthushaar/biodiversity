"""GBIF taxonomic backbone: turn a scientific name into a stable taxon key."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable, MutableMapping
from dataclasses import asdict, dataclass
from pathlib import Path

from biodiv.ingestion.http import PoliteClient

GBIF_API = "https://api.gbif.org/v1"
MIN_FUZZY_CONFIDENCE = 95


@dataclass(frozen=True)
class GbifTaxon:
    key: int
    canonical_name: str
    kingdom: str | None
    rank: str | None


class GbifClient:
    def __init__(self, http: PoliteClient) -> None:
        self._http = http

    async def resolve(self, name: str, kingdom: str | None = None) -> GbifTaxon | None:
        """Best backbone match for a name, with synonyms resolved to the accepted taxon.

        Returns None rather than guessing: higher-rank-only and low-confidence fuzzy matches
        would attach a species to the wrong taxon, which is worse than no key.
        """
        params = {"scientificName": name}
        if kingdom:
            params["kingdom"] = kingdom
        m = await self._http.get_json(f"{GBIF_API}/species/match", params)

        match_type = m.get("matchType")
        if "usageKey" not in m or match_type not in ("EXACT", "FUZZY"):
            return None
        if match_type == "FUZZY" and m.get("confidence", 0) < MIN_FUZZY_CONFIDENCE:
            return None

        accepted = m.get("acceptedUsageKey")
        if accepted and accepted != m["usageKey"]:
            sp = await self._http.get_json(f"{GBIF_API}/species/{accepted}")
            return GbifTaxon(
                key=accepted,
                canonical_name=sp.get("canonicalName") or sp["scientificName"],
                kingdom=sp.get("kingdom"),
                rank=sp.get("rank"),
            )
        return GbifTaxon(
            key=m["usageKey"],
            canonical_name=m.get("canonicalName") or m["scientificName"],
            kingdom=m.get("kingdom"),
            rank=m.get("rank"),
        )


TaxonCache = MutableMapping[str, GbifTaxon | None]


def cache_key(name: str, kingdom: str | None) -> str:
    return f"{kingdom}|{name}"


def load_cache(path: Path) -> dict[str, GbifTaxon | None]:
    """Name-match results persisted between runs, so re-runs are fast and gentle on GBIF."""
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: (GbifTaxon(**v) if v else None) for k, v in raw.items()}


def save_cache(path: Path, cache: TaxonCache) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = {k: (asdict(v) if v else None) for k, v in cache.items()}
    path.write_text(json.dumps(raw, indent=0, sort_keys=True), encoding="utf-8")


async def resolve_into_cache(
    gbif: GbifClient, pairs: Iterable[tuple[str, str | None]], cache: TaxonCache
) -> None:
    """Resolve every uncached (name, kingdom) pair concurrently; results land in `cache`."""
    todo = {(n, k) for n, k in pairs if cache_key(n, k) not in cache}

    async def one(name: str, kingdom: str | None) -> None:
        cache[cache_key(name, kingdom)] = await gbif.resolve(name, kingdom)

    await asyncio.gather(*(one(n, k) for n, k in todo))
