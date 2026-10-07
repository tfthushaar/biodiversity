"""GRIIS (Global Register of Introduced and Invasive Species) country checklists.

Published as Darwin Core Archives through GBIF. A species listed for a country is introduced
there; the `isInvasive` flag says whether it is known to cause harm. "Native" is therefore
the *absence* of a record, which is why we never store a native flag of our own.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import zipfile
from collections.abc import MutableMapping
from dataclasses import dataclass

from biodiv.ingestion.gbif import GbifClient, GbifTaxon

log = logging.getLogger(__name__)

GRIIS_ARCHIVE_URL = "https://cloud.gbif.org/griis/archive.do"
INFRA_MARKERS = {"var.", "subsp.", "ssp.", "f.", "forma"}


@dataclass(frozen=True)
class GriisRecord:
    taxon_id: str
    name: str
    accepted_name: str | None
    kingdom: str | None
    rank: str | None
    status: str  # ACCEPTED | SYNONYM | DOUBTFUL
    country: str
    occurrence_status: str | None
    establishment_means: str | None
    is_invasive: bool | None
    habitat: str | None

    @property
    def name_to_resolve(self) -> str:
        # GRIIS's own taxonomy decides what a synonym means, not GBIF's.
        return self.accepted_name or self.name


@dataclass
class SpeciesEntry:
    """One species in one country, after taxonomy resolution and de-duplication."""

    gbif_key: int | None
    name: str
    kingdom: str | None
    rank: str | None
    country: str
    is_invasive: bool | None
    establishment_means: str | None
    occurrence_status: str | None
    habitat: str | None
    source_ref: str


def canonical_name(name: str) -> str:
    """Strip authorship: 'Lantana camara L.' -> 'Lantana camara'. Fallback for unmatched names."""
    tokens = name.split()
    if len(tokens) < 2:
        return name.strip()
    out = [tokens[0], tokens[1]]
    for i, tok in enumerate(tokens[2:], start=2):
        if tok in INFRA_MARKERS and i + 1 < len(tokens):
            out += [tok, tokens[i + 1]]
            break
    return " ".join(out)


def _parse_invasive(value: str | None) -> bool | None:
    v = (value or "").strip().lower()
    if v == "invasive":
        return True
    if v.startswith("not"):
        return False
    return None


def _table(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    if name not in zf.namelist():
        return []
    text = io.TextIOWrapper(zf.open(name), encoding="utf-8", newline="")
    return list(csv.DictReader(text, delimiter="\t", quoting=csv.QUOTE_NONE))


def parse_archive(data: bytes) -> list[GriisRecord]:
    """Join taxon + distribution + species-profile tables of a GRIIS Darwin Core Archive."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        taxa = _table(zf, "taxon.txt")
        dists = _table(zf, "distribution.txt")
        profiles = {r["id"]: r for r in _table(zf, "speciesprofile.txt")}

    by_taxon: dict[str, list[dict[str, str]]] = {}
    for d in dists:
        by_taxon.setdefault(d["id"], []).append(d)

    records: list[GriisRecord] = []
    for t in taxa:
        profile = profiles.get(t["id"], {})
        seen: set[str] = set()
        for d in by_taxon.get(t["id"], []):
            country = d.get("countryCode", "").strip().upper()
            if len(country) != 2 or country in seen:
                continue
            seen.add(country)
            records.append(
                GriisRecord(
                    taxon_id=t["taxonID"] or t["id"],
                    name=t["scientificName"].strip(),
                    accepted_name=(t.get("acceptedNameUsage") or "").strip() or None,
                    kingdom=(t.get("kingdom") or "").strip() or None,
                    rank=(t.get("taxonRank") or "").strip() or None,
                    status=(t.get("taxonomicStatus") or "").strip().upper(),
                    country=country,
                    occurrence_status=(d.get("occurrenceStatus") or "").strip() or None,
                    establishment_means=(d.get("establishmentMeans") or "").strip() or None,
                    is_invasive=_parse_invasive(profile.get("isInvasive")),
                    habitat=(profile.get("habitat") or "").strip() or None,
                )
            )
    return records


def filter_usable(records: list[GriisRecord]) -> tuple[list[GriisRecord], int]:
    """Drop DOUBTFUL taxa: flagging a possibly-native species as introduced would be wrong."""
    kept = [r for r in records if r.status != "DOUBTFUL"]
    return kept, len(records) - len(kept)


def _merge_invasive(a: bool | None, b: bool | None) -> bool | None:
    if a is True or b is True:
        return True
    if a is False or b is False:
        return False
    return None


async def resolve_records(
    records: list[GriisRecord],
    gbif: GbifClient,
    cache: MutableMapping[str, GbifTaxon | None] | None = None,
) -> list[SpeciesEntry]:
    """Resolve names to GBIF taxa and merge records that turn out to be the same species."""
    cache = cache if cache is not None else {}
    unique = {(r.name_to_resolve, r.kingdom) for r in records}

    done = 0

    async def lookup(name: str, kingdom: str | None) -> None:
        nonlocal done
        k = f"{kingdom}|{name}"
        if k not in cache:
            cache[k] = await gbif.resolve(name, kingdom)
        done += 1
        if done % 250 == 0 or done == len(unique):
            log.info("matched %d/%d names against GBIF", done, len(unique))

    await asyncio.gather(*(lookup(n, k) for n, k in unique))

    merged: dict[tuple, SpeciesEntry] = {}
    for r in records:
        taxon = cache[f"{r.kingdom}|{r.name_to_resolve}"]
        name = taxon.canonical_name if taxon else canonical_name(r.name_to_resolve)
        identity = (r.country, taxon.key) if taxon else (r.country, name.lower(), r.kingdom)
        entry = merged.get(identity)
        if entry is None:
            merged[identity] = SpeciesEntry(
                gbif_key=taxon.key if taxon else None,
                name=name,
                kingdom=(taxon.kingdom if taxon else None) or r.kingdom,
                rank=(taxon.rank if taxon else None) or r.rank,
                country=r.country,
                is_invasive=r.is_invasive,
                establishment_means=r.establishment_means,
                occurrence_status=r.occurrence_status,
                habitat=r.habitat,
                source_ref=r.taxon_id,
            )
        else:
            entry.is_invasive = _merge_invasive(entry.is_invasive, r.is_invasive)
    return list(merged.values())
