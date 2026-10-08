"""IUCN Red List API v4: which native species are threatened by which named invasive species.

An assessment lists its threats, and a threat with code 8_1_2 ("invasive non-native species,
named species") carries an `ias` field with the invasive species' name. See docs/iucn.md for the
API's behaviour and for IUCN's terms of use, which prohibit redistributing the data without
permission: rows built from this module are stored but hidden from the public API (migration 0017).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from biodiv.ingestion.http import PoliteClient

IUCN_API = "https://api.iucnredlist.org/api/v4"
NAMED_SPECIES_THREAT = "8_1_2"
RED_LIST_VERSION_URL = f"{IUCN_API}/information/red_list_version"

_NEXT = re.compile(r'<([^>]+)>\s*;\s*rel="next"')
_BINOMIAL = re.compile(
    r"^[A-Z][a-z]+(?:-[a-z]+)? [a-z][a-z-]+"
    r"(?: (?:subsp\.|var\.|ssp\.) ?[a-z-]+| [a-z][a-z-]+)?$"
)
_PARENS = re.compile(r"\s*\([^)]*\)")
_SPLIT = re.compile(r"\s*(?:;|\n|\band\b|&|\+|,)\s*")


@dataclass(frozen=True)
class Threat:
    """One named invasive species threatening one assessed species."""

    assessment_id: int
    native_name: str
    kingdom: str | None
    invasive_name: str
    scope: str | None
    timing: str | None
    score: str | None
    year: int | None
    url: str
    citation: str
    category: str | None


def split_names(raw: str | None) -> list[str]:
    """The species named in an `ias` field.

    Assessors write one name, or several separated by ';', 'and', '&' or commas, sometimes with
    a common name in brackets. Only strings shaped like a scientific name (genus then species) are
    kept; anything else, such as "various species" or a group name, is dropped rather than guessed.
    """
    if not raw:
        return []
    names: list[str] = []
    for part in _SPLIT.split(_PARENS.sub("", raw).strip()):
        part = part.strip().strip(".").strip()
        if _BINOMIAL.match(part) and part not in names:
            names.append(part)
    return names


def parse_assessment(a: dict[str, Any]) -> list[Threat]:
    """All named-invasive threats in one full assessment."""
    taxon = a.get("taxon") or {}
    native = (taxon.get("scientific_name") or "").strip()
    if not native or not a.get("assessment_id"):
        return []
    year = a.get("year_published")
    out: list[Threat] = []
    for t in a.get("threats") or []:
        if t.get("code") != NAMED_SPECIES_THREAT:
            continue
        for name in split_names(t.get("ias")):
            out.append(
                Threat(
                    assessment_id=int(a["assessment_id"]),
                    native_name=native,
                    kingdom=taxon.get("kingdom_name"),
                    invasive_name=name,
                    scope=t.get("scope"),
                    timing=t.get("timing"),
                    score=t.get("score"),
                    year=int(year) if str(year or "").isdigit() else None,
                    url=a.get("url")
                    or f"https://www.iucnredlist.org/species/{taxon.get('sis_id')}/{a['assessment_id']}",
                    citation=(a.get("citation") or "").strip(),
                    category=(a.get("red_list_category") or {}).get("code"),
                )
            )
    return out


class IucnClient:
    def __init__(self, http: PoliteClient, token: str) -> None:
        self._http = http
        self._headers = {"Authorization": token, "Accept": "application/json"}

    async def red_list_version(self) -> str:
        data = (await self._http.get(RED_LIST_VERSION_URL, headers=self._headers)).json()
        return str(data["red_list_version"])

    async def assessments(self, path: str, **params: Any) -> AsyncIterator[dict[str, Any]]:
        """Summaries of the assessments at `path`, following the Link header's next page."""
        url: str | None = f"{IUCN_API}{path}"
        query: dict[str, Any] | None = params
        while url:
            resp = await self._http.get(url, query, headers=self._headers)
            for item in resp.json().get("assessments", []):
                yield item
            match = _NEXT.search(resp.headers.get("link", ""))
            url, query = (match.group(1) if match else None), None

    async def assessment_ids(self, path: str) -> dict[int, dict[str, Any]]:
        return {a["assessment_id"]: a async for a in self.assessments(path, latest="true")}

    async def assessment(self, assessment_id: int) -> dict[str, Any]:
        return (
            await self._http.get(f"{IUCN_API}/assessment/{assessment_id}", headers=self._headers)
        ).json()
