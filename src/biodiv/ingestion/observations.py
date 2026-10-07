"""A source-neutral observation record, plus the validation every record must pass.

Connectors turn each platform's JSON into `Observation`; `validate` then decides whether it is
fit for analysis. Rejections carry a reason so ingestion can report *why* data was dropped.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

# Photo licences we will use as training images. "-nd" (no derivatives) is excluded: resizing
# and cropping for a model is a derivative. Anything unlicensed (all rights reserved) is out.
IMAGE_LICENSES = frozenset({"cc0", "cc-by", "cc-by-nc", "cc-by-sa", "cc-by-nc-sa"})

SPECIES_RANKS = frozenset(
    {"species", "subspecies", "variety", "form", "hybrid", "infraspecies", "infrahybrid"}
)
MAX_UNCERTAINTY_M = 2000.0  # zone-level analysis tolerates ~2 km; coarser is mostly noise


@dataclass(frozen=True)
class Observation:
    source: str  # 'inaturalist' | 'gbif'
    external_id: str
    record_url: str
    taxon_name: str
    rank: str
    lat: float
    lon: float
    captured_at: datetime | None
    kingdom: str | None = None
    common_name: str | None = None
    inat_taxon_id: int | None = None
    gbif_taxon_key: int | None = None
    image_url: str | None = None
    image_license: str | None = None
    record_license: str | None = None
    width: int | None = None
    height: int | None = None
    uncertainty_m: float | None = None
    obscured: bool = False
    captive: bool = False


_CC_URL = re.compile(r"creativecommons\.org/(licenses|publicdomain)/([a-z-]+)", re.I)


def short_license(value: str | None) -> str | None:
    """'http://creativecommons.org/licenses/by-nc/4.0/' -> 'cc-by-nc'; short codes pass through."""
    if not value:
        return None
    m = _CC_URL.search(value)
    if m:
        kind, code = m.group(1).lower(), m.group(2).lower()
        return "cc0" if kind == "publicdomain" or code == "zero" else f"cc-{code}"
    return value.strip().lower()


def usable_image(url: str | None, license_code: str | None) -> str | None:
    """The image URL, only if its licence lets us use it."""
    if url and (license_code or "").lower() in IMAGE_LICENSES:
        return url
    return None


def validate(obs: Observation, *, now: datetime | None = None) -> str | None:
    """Return None if the observation is usable, otherwise a short rejection reason."""
    now = now or datetime.now(UTC)
    if not (-90 <= obs.lat <= 90 and -180 <= obs.lon <= 180):
        return "bad_coordinates"
    if obs.lat == 0 and obs.lon == 0:
        return "null_island"  # the classic "no coordinates" default
    if obs.obscured:
        return "obscured_location"  # position deliberately randomised: would misplace it
    if obs.uncertainty_m is not None and obs.uncertainty_m > MAX_UNCERTAINTY_M:
        return "imprecise_location"
    if obs.captured_at is None:
        return "no_date"
    if obs.captured_at > now:
        return "future_date"
    if obs.rank.lower() not in SPECIES_RANKS:
        return "not_species_level"
    if obs.captive:
        return "captive_or_cultivated"  # planted or caged: not a wild occurrence
    if not obs.taxon_name:
        return "no_taxon"
    return None


def validate_all(observations: list[Observation]) -> tuple[list[Observation], Counter[str]]:
    kept: list[Observation] = []
    rejected: Counter[str] = Counter()
    for obs in observations:
        reason = validate(obs)
        if reason:
            rejected[reason] += 1
        else:
            kept.append(obs)
    return kept, rejected
