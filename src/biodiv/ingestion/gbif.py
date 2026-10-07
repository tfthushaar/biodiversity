"""GBIF taxonomic backbone: turn a scientific name into a stable taxon key."""

from __future__ import annotations

from dataclasses import dataclass

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
