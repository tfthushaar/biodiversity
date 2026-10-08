"""USGS Nonindigenous Aquatic Species (NAS) database connector.

NAS is a curated U.S. Geological Survey database of where non-native aquatic species have been
found in the United States: fishes, reptiles, amphibians, molluscs, crustaceans and aquatic plants.
Every record is a non-native species by definition, each with a source type (literature, museum
specimen or personal communication), a coordinate accuracy class and an establishment status.
USGS data are U.S. Government works. The database asks users to cite it and to contact the team
before publishing results that depend on it.

API: https://nas.er.usgs.gov/api/documentation.aspx
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.observations import Observation

NAS_API = "https://nas.er.usgs.gov/api/v2/occurrence/search"
NAS_RECORD_URL = "https://nas.er.usgs.gov/queries/SpecimenViewer.aspx?SpecimenID={key}"
NAS_LICENSE = "Public domain (U.S. Government work); cite USGS NAS"

# The API has no bounding-box search, so each zone is covered by the counties it lies in and the
# zone polygon decides which of those records are inside. Only zones listed here are queried.
ZONE_COUNTIES: dict[str, list[tuple[str, str]]] = {
    "everglades": [("FL", "Miami-Dade"), ("FL", "Monroe"), ("FL", "Collier")],
    "smokies": [("TN", "Sevier"), ("TN", "Blount"), ("TN", "Cocke"), ("NC", "Swain"),
                ("NC", "Haywood")],
}

# NAS's own coordinate accuracy classes, as a position uncertainty in metres. Only "Accurate" is
# precise enough for zone-level analysis; "Approximate" and "Centroid" fail the 2 km rule.
ACCURACY_M = {"accurate": 100.0, "approximate": 10_000.0, "centroid": 50_000.0}

# Status values that mean the population did not take hold at the site.
NOT_ESTABLISHED = frozenset({"failed"})


def _kingdom(group: str | None) -> str | None:
    g = (group or "").lower()
    if g.startswith(("plant", "algae")):
        return "Plantae"
    return "Animalia" if g else None


def parse_occurrence(o: dict[str, Any]) -> Observation | None:
    """Map one NAS occurrence record to an Observation, or None if it lacks the essentials."""
    lat, lon = o.get("decimalLatitude"), o.get("decimalLongitude")
    genus, species = (o.get("genus") or "").strip(), (o.get("species") or "").strip()
    if not (o.get("key") and lat not in (None, "") and lon not in (None, "")):
        return None

    year, month, day = o.get("year"), o.get("month"), o.get("day")
    try:
        when = datetime(int(year), int(month), int(day), tzinfo=UTC)
    except (TypeError, ValueError):
        when = None  # a year alone cannot place a record in a month

    accuracy = (o.get("latLongAccuracy") or "").strip().lower()
    status = (o.get("status") or "").strip().lower()
    return Observation(
        source="usgs_nas",
        external_id=str(o["key"]),
        record_url=NAS_RECORD_URL.format(key=o["key"]),
        taxon_name=(o.get("scientificName") or f"{genus} {species}").strip(),
        rank="species" if genus and species else "",
        lat=float(lat),
        lon=float(lon),
        captured_at=when,
        kingdom=_kingdom(o.get("group")),
        common_name=o.get("commonName") or None,
        record_license=NAS_LICENSE,
        uncertainty_m=ACCURACY_M.get(accuracy, ACCURACY_M["centroid"]),
        not_established=status in NOT_ESTABLISHED,
    )


async def iter_occurrences(
    http: PoliteClient,
    counties: list[tuple[str, str]],
    *,
    max_results: int = 20000,
    page_size: int = 500,
) -> AsyncIterator[dict[str, Any]]:
    """Yield raw NAS occurrences for each (state, county) in turn, up to max_results in all."""
    produced = 0
    for state, county in counties:
        offset = 0
        while produced < max_results:
            page = await http.get_json(
                NAS_API,
                {"state": state, "county": county, "limit": page_size, "offset": offset},
            )
            results = page.get("results") or []
            for rec in results:
                yield rec
                produced += 1
                if produced >= max_results:
                    return
            offset += page_size
            # The API reports this as the string "true" or "false".
            if str(page.get("endOfRecords")).lower() == "true" or not results:
                break
