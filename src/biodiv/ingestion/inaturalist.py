"""iNaturalist connector: community-verified, geotagged wildlife and plant observations.

We fetch research-grade observations (two or more identifiers agree), which is the platform's
own bar for "verified". iNaturalist asks API clients to stay under about one request/second.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.observations import Observation, short_license, usable_image

INAT_API = "https://api.inaturalist.org/v1"

# iNaturalist names an organism's "iconic" group (a class, mostly). We only need a kingdom
# hint to disambiguate homonyms when matching names to the GBIF backbone.
_KINGDOMS = {k: k for k in ("Plantae", "Fungi", "Protozoa", "Chromista")}


def _kingdom(iconic: str | None) -> str | None:
    if not iconic or iconic == "unknown":
        return None
    return _KINGDOMS.get(iconic, "Animalia")


def _when(o: dict[str, Any]) -> datetime | None:
    if o.get("time_observed_at"):
        return datetime.fromisoformat(o["time_observed_at"]).astimezone(UTC)
    if o.get("observed_on"):
        d = date.fromisoformat(o["observed_on"])
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    return None


def parse_observation(o: dict[str, Any]) -> Observation | None:
    """Map one iNaturalist observation to an Observation, or None if it lacks the essentials."""
    taxon, geo = o.get("taxon"), o.get("geojson")
    if not (o.get("id") and taxon and taxon.get("name") and geo and geo.get("coordinates")):
        return None
    lon, lat = geo["coordinates"]

    photos = o.get("photos") or []
    photo = photos[0] if photos else {}
    url = photo.get("url")
    if url:
        url = url.replace("/square.", "/medium.")  # the API returns a 75px thumbnail
    dims = photo.get("original_dimensions") or {}

    return Observation(
        source="inaturalist",
        external_id=str(o["id"]),
        record_url=o["uri"],
        taxon_name=taxon["name"],
        rank=taxon.get("rank") or "",
        lat=lat,
        lon=lon,
        captured_at=_when(o),
        kingdom=_kingdom(taxon.get("iconic_taxon_name")),
        common_name=taxon.get("preferred_common_name"),
        inat_taxon_id=taxon.get("id"),
        image_url=usable_image(url, short_license(photo.get("license_code"))),
        image_license=short_license(photo.get("license_code")),
        record_license=short_license(o.get("license_code")),
        width=dims.get("width"),
        height=dims.get("height"),
        # Unknown accuracy is common on research-grade records and is accepted; known-coarse
        # positions are rejected by validate().
        uncertainty_m=o.get("public_positional_accuracy"),
        obscured=bool(o.get("obscured")),
        captive=bool(o.get("captive")),
    )


async def iter_observations(
    http: PoliteClient,
    bbox: tuple[float, float, float, float],
    *,
    id_above: int = 0,
    max_results: int = 5000,
    quality_grade: str = "research",
    per_page: int = 200,
) -> AsyncIterator[dict[str, Any]]:
    """Yield raw observations inside bbox=(west, south, east, north), oldest id first.

    Paging by `id_above` instead of page numbers avoids iNaturalist's 10,000-result cap and
    makes the last id seen a natural cursor for the next incremental run.
    """
    west, south, east, north = bbox
    fetched, cursor = 0, id_above
    while fetched < max_results:
        size = min(per_page, max_results - fetched)
        page = await http.get_json(
            f"{INAT_API}/observations",
            {
                "swlng": west, "swlat": south, "nelng": east, "nelat": north,
                "quality_grade": quality_grade, "photos": "true",
                "order_by": "id", "order": "asc", "id_above": cursor, "per_page": size,
            },
        )
        results = page.get("results", [])
        for o in results:
            yield o
        fetched += len(results)
        if len(results) < size:
            return
        cursor = results[-1]["id"]
