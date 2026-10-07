"""Checks that curated knowledge is actually said by the sources it cites.

The knowledge base advises on controlling invasive plants in tiger reserves, so every claim must
rest on a verbatim quote from a named source, and that quote must really appear there. Two
checks, deliberately separate:

  * `validate_structure` needs no network: right fields, legal values, no row without a quote.
    It runs in CI on every change.
  * `find_problems` compares each quote with the source's text. It tolerates typography only
    (curly quotes, dash variants, whitespace, case) and never wording. A summarising tool once
    handed me a quote that the page did not contain; this is the guard against that.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

METHODS = {"mechanical", "chemical", "biological", "cultural", "fire", "grazing", "integrated"}
EFFECTIVENESS = {"low", "moderate", "high", "variable"}
EVIDENCE = {"low", "moderate", "high"}
COST = {"low", "medium", "high", None}
FINDING_TYPES = {"impact", "spread", "concern"}
CERTAINTY = {"experimental", "observational", "preliminary", "unverified_concern", "review"}
MIN_QUOTE_CHARS = 25  # a fragment this short proves nothing

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")
_QUOTES = {ord(c): "'" for c in "‘’‚′�"}
_QUOTES |= {ord(c): '"' for c in "“”„″"}


@dataclass(frozen=True)
class Problem:
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


def normalise(text: str) -> str:
    """Typography-insensitive form for comparing a quote with a page."""
    text = html.unescape(text).translate(_DASHES).translate(_QUOTES).replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def jats_to_text(abstract: str) -> str:
    """Crossref abstracts arrive wrapped in JATS XML."""
    return html_to_text(abstract)


def _entries(knowledge: dict[str, Any]):
    for i, row in enumerate(knowledge.get("playbooks", [])):
        yield f"playbooks[{i}] {row.get('species')}/{row.get('method')}", row
    for i, row in enumerate(knowledge.get("impact_findings", [])):
        yield f"impact_findings[{i}] {row.get('species')}/{row.get('zone')}", row


def validate_structure(knowledge: dict[str, Any]) -> list[Problem]:
    """Everything that can be checked without reading the sources."""
    problems: list[Problem] = []
    sources = knowledge.get("sources", {})
    for key, s in sources.items():
        for field in ("citation", "url", "kind"):
            if not s.get(field):
                problems.append(Problem(f"sources.{key}", f"missing {field}"))
        if s.get("kind") == "crossref" and not s.get("doi"):
            problems.append(Problem(f"sources.{key}", "crossref source needs a doi"))
        if s.get("kind") not in ("page", "crossref"):
            problems.append(Problem(f"sources.{key}", f"unknown kind {s.get('kind')!r}"))

    seen: set[tuple] = set()
    for where, row in _entries(knowledge):
        if row.get("source") not in sources:
            problems.append(Problem(where, f"unknown source {row.get('source')!r}"))
        quotes = row.get("quotes") or []
        if not quotes:
            problems.append(Problem(where, "no quotes: no citation, no row"))
        for q in quotes:
            if len(q.strip()) < MIN_QUOTE_CHARS:
                problems.append(Problem(where, f"quote too short to be evidence: {q!r}"))
        if not (row.get("summary") or "").strip():
            problems.append(Problem(where, "empty summary"))
        if not (row.get("region_note") or "").strip():
            problems.append(Problem(where, "missing region_note: say where the evidence is from"))

        if "method" in row:
            checks = (("method", METHODS), ("effectiveness", EFFECTIVENESS),
                      ("evidence_strength", EVIDENCE), ("cost_tier", COST))
            key = (row.get("species"), row.get("method"), row.get("source"), row.get("summary"))
        else:
            checks = (("finding_type", FINDING_TYPES), ("certainty", CERTAINTY))
            key = (row.get("species"), row.get("zone"), row.get("source"), row.get("summary"))
            if not (row.get("affected") or "").strip():
                problems.append(Problem(where, "missing 'affected'"))
        for field, legal in checks:
            if row.get(field) not in legal:
                problems.append(Problem(where, f"{field}={row.get(field)!r} is not one of {legal}"))
        if key in seen:
            problems.append(Problem(where, "duplicate entry"))
        seen.add(key)
    return problems


def find_problems(knowledge: dict[str, Any], texts: dict[str, str]) -> list[Problem]:
    """Quotes that do not appear in their source's text."""
    haystack = {k: normalise(t) for k, t in texts.items()}
    problems: list[Problem] = []
    for where, row in _entries(knowledge):
        source = row.get("source")
        if source not in haystack:
            problems.append(Problem(where, f"no text was fetched for source {source!r}"))
            continue
        for q in row.get("quotes", []):
            if normalise(q) not in haystack[source]:
                problems.append(Problem(where, f"quote not found in {source}: {q[:90]!r}"))
    return problems
