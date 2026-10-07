"""GBIF occurrence connector.

In practice GBIF here is dominated by two datasets we deliberately do NOT ingest by default:
iNaturalist research-grade observations (already fetched directly, so ingesting them again would
double-count) and eBird (hundreds of thousands of bird records: too large for a free database
and birds only). The default is museum and herbarium specimens, which carry the *historical*
record of where a species was first collected and so complement the live feeds. eBird remains
available as an explicit, capped opt-in.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.observations import Observation, short_license, usable_image

GBIF_OCCURRENCE_API = "https://api.gbif.org/v1/occurrence/search"

INATURALIST_DATASET = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"
EBIRD_DATASET = "4fa7b334-ce0d-4e88-aaae-2e0c138d049e"

DEFAULT_BASIS = ("PRESERVED_SPECIMEN", "MATERIAL_SAMPLE", "OCCURRENCE")
MAX_OFFSET = 100_000  # GBIF's search endpoint refuses to page past this


def is_inaturalist_mirror(o: dict[str, Any]) -> bool:
    return o.get("datasetKey") == INATURALIST_DATASET


def parse_occurrence(o: dict[str, Any]) -> Observation | None:
    """Map one GBIF occurrence to an Observation, or None if it lacks the essentials."""
    lat, lon = o.get("decimalLatitude"), o.get("decimalLongitude")
    if not (o.get("key") and lat is not None and lon is not None):
        return None

    species_key = o.get("speciesKey")
    # Species-level identity comes from speciesKey. taxonRank is unreliable for this: GBIF
    # reports e.g. UNRANKED for perfectly good species records.
    name = o.get("species") or o.get("scientificName") or ""
    rank = "species" if species_key else (o.get("taxonRank") or "").lower()

    year, month, day = o.get("year"), o.get("month"), o.get("day")
    when = datetime(year, month, day, tzinfo=UTC) if year and month and day else None

    media = next((m for m in o.get("media") or [] if m.get("type") == "StillImage"), {})
    image_license = short_license(media.get("license"))

    return Observation(
        source="gbif",
        external_id=str(o["key"]),
        record_url=f"https://www.gbif.org/occurrence/{o['key']}",
        taxon_name=name,
        rank=rank,
        lat=lat,
        lon=lon,
        captured_at=when,
        kingdom=o.get("kingdom"),
        gbif_taxon_key=species_key,
        image_url=usable_image(media.get("identifier"), image_license),
        image_license=image_license,
        record_license=short_license(o.get("license")),
        uncertainty_m=o.get("coordinateUncertaintyInMeters"),
        obscured=bool(o.get("dataGeneralizations") or o.get("informationWithheld")),
        captive=o.get("establishmentMeans") == "MANAGED"
        or o.get("basisOfRecord") == "LIVING_SPECIMEN",
    )


async def iter_occurrences(
    http: PoliteClient,
    bbox: tuple[float, float, float, float],
    *,
    basis_of_record: Sequence[str] = DEFAULT_BASIS,
    dataset_key: str | None = None,
    last_interpreted: str | None = None,
    max_results: int = 5000,
    page_size: int = 300,
) -> AsyncIterator[dict[str, Any]]:
    """Yield raw occurrences inside bbox=(west, south, east, north)."""
    west, south, east, north = bbox
    params: dict[str, Any] = {
        "decimalLongitude": f"{west},{east}",
        "decimalLatitude": f"{south},{north}",
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT",
    }
    if dataset_key:
        params["datasetKey"] = dataset_key
    else:
        params["basisOfRecord"] = list(basis_of_record)
    if last_interpreted:
        params["lastInterpreted"] = f"{last_interpreted},*"

    offset = 0
    while offset < min(max_results, MAX_OFFSET):
        size = min(page_size, max_results - offset)
        page = await http.get_json(GBIF_OCCURRENCE_API, {**params, "limit": size, "offset": offset})
        for o in page.get("results", []):
            yield o
        offset += size
        if page.get("endOfRecords", True):
            return
