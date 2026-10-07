"""Training photos from iNaturalist: licence filtering, provenance, and honest train/test splits.

Only photos whose licence permits use as training data are kept, and what we store about each is
provenance (observation id and URL, licence), not the photographer: observers are reduced to an
opaque hash that exists solely so that photos by one person never land on both sides of a split.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from biodiv.ingestion.observations import IMAGE_LICENSES, short_license

# India, roughly. Used only to report how a model does on in-region photos, never to filter.
INDIA_BBOX = (68.0, 6.5, 97.5, 37.1)  # west, south, east, north

T = TypeVar("T")


@dataclass(frozen=True)
class TrainingPhoto:
    label: str
    observation_id: int
    taxon_id: int
    url: str
    license: str
    observer: str  # opaque hash, for group-aware splitting only
    lat: float | None
    lon: float | None

    @property
    def in_india(self) -> bool:
        if self.lat is None or self.lon is None:
            return False
        west, south, east, north = INDIA_BBOX
        return west <= self.lon <= east and south <= self.lat <= north


def observer_hash(user_id: int | str) -> str:
    return hashlib.sha256(f"observer:{user_id}".encode()).hexdigest()[:12]


def parse_photo(o: dict[str, Any], label: str) -> TrainingPhoto | None:
    """One usable training photo from an iNaturalist observation, or None.

    Rejects captive/cultivated plants and animals (a planted ornamental is not evidence of what a
    wild invader looks like), obscured locations, and any photo whose licence forbids our use.
    """
    if o.get("captive") or o.get("obscured") or not o.get("taxon"):
        return None
    for photo in o.get("photos") or []:
        licence = short_license(photo.get("license_code"))
        if licence in IMAGE_LICENSES and photo.get("url"):
            geo = (o.get("geojson") or {}).get("coordinates") or [None, None]
            user = (o.get("user") or {}).get("id", o["id"])  # fall back to per-observation
            return TrainingPhoto(
                label=label,
                observation_id=o["id"],
                taxon_id=o["taxon"]["id"],
                url=photo["url"].replace("/square.", "/medium."),
                license=licence,
                observer=observer_hash(user),
                lon=geo[0],
                lat=geo[1],
            )
    return None


def group_split(
    items: Sequence[T],
    group: Callable[[T], str],
    fractions: Sequence[float],
    seed: int = 0,
) -> list[list[T]]:
    """Split items so that all items of one group land in the same part.

    A random split lets one observer's near-identical photos of the same plant appear in both
    train and test, which makes a model look better than it is. Splitting by observer measures
    what we actually care about: does it work on photos from people it has never seen?
    """
    if abs(sum(fractions) - 1.0) > 1e-9:
        raise ValueError("fractions must sum to 1")
    groups: dict[str, list[T]] = defaultdict(list)
    for item in items:
        groups[group(item)].append(item)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)

    parts: list[list[T]] = [[] for _ in fractions]
    targets = [f * len(items) for f in fractions]
    for key in keys:
        # Put the group where there is most room left relative to the target.
        i = max(range(len(parts)), key=lambda j: targets[j] - len(parts[j]))
        parts[i].extend(groups[key])
    return parts
