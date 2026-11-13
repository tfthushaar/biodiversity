"""Checks that every claim rests on a peer-reviewed paper and on words that paper contains.

The knowledge base advises on controlling invasive species, so a claim without a checkable
source must never appear. The rules are strict and deliberately separate:

  * `validate_structure` needs no network. Every source is a journal article identified by a
    DOI and published in or after the policy's `min_year`. Web pages, news, fact sheets and
    species profiles have no place in the file. Every row has a quote and says where the
    evidence comes from. It runs in CI on every change.
  * `check_paper` compares each source with the Crossref and OpenAlex records for its DOI. The
    record must be a journal article, not a preprint, report or extension bulletin. Its title,
    journal, year and first author must match what the file says. It must not be retracted, and
    an abstract must be available to quote from.
  * `find_problems` requires each quote to appear in the abstract of the paper it cites. It
    tolerates typography only (curly quotes, dash variants, accents, spacing, case) and never
    wording. A summarising tool once handed me a quote that the page did not contain; this is
    the guard against that.

A number is where a paraphrase goes wrong without anyone noticing, so numbers get their own rule.
Every number in a row's summary must appear in one of its quotes, so the figure a reader sees is
visibly the paper's and not ours. Every number in the summary, "affected" and region note must
also appear in the paper's abstract. Number words (one to twelve) count as the digit they name.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

METHODS = {"mechanical", "chemical", "biological", "cultural", "fire", "grazing", "integrated",
           "detection"}
DESIGNS = {"experimental", "observational", "review", "modelled"}
FINDING_TYPES = {"impact", "spread", "concern"}
MIN_QUOTE_CHARS = 25  # a fragment this short proves nothing
MIN_QUOTE_WORDS = 6
# A preprint server is not peer review. These DOI prefixes belong to arXiv, bioRxiv and medRxiv,
# SSRN, Zenodo, Research Square, OSF, Preprints.org, Authorea and the EcoEvoRxiv family.
PREPRINT_DOI_PREFIXES = ("10.48550/", "10.1101/", "10.2139/", "10.5281/", "10.21203/", "10.31219/",
                         "10.20944/", "10.22541/", "10.32942/", "10.31234/", "10.31235/",
                         "10.31224/", "10.32388/", "10.36227/")
PREPRINT_VENUE_WORDS = ("arxiv", "biorxiv", "medrxiv", "ssrn", "preprints", "researchsquare",
                        "zenodo", "authorea", "ecoevorxiv", "osfpreprints", "preprint")
# OpenAlex files an article as "article", "review" or "data-paper", and all three are published
# papers. These types are not: a preprint, a dataset, a reviewer's report or a correction.
NOT_PEER_REVIEWED_TYPES = frozenset({
    "preprint", "dataset", "peer-review", "erratum", "editorial", "paratext", "letter", "report",
    "supplementary-materials", "retraction", "standard", "grant", "other", "software"})
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")
PAPER_FIELDS = ("doi", "title", "authors", "year", "journal")
RETRACTION_NOTICES = {"retraction", "withdrawal", "removal", "expression_of_concern",
                      "expression-of-concern"}

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
    """Typography-insensitive form for comparing a quote with an abstract."""
    text = html.unescape(text).translate(_DASHES).translate(_QUOTES).replace(" ", " ")
    text = re.sub(r"(?<=\d)·(?=\d)", ".", text)  # 1·5 is how some journals print 1.5
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().lower()


def squash(text: str) -> str:
    """`normalise` with all spacing removed. Italics and markup in abstracts sometimes glue or
    split words ("twoProsopismanagement"), so spacing is not evidence either way."""
    return re.sub(r"\s+", "", normalise(text))


def contains(haystack: str, quote: str) -> bool:
    return squash(quote) in squash(haystack)


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def jats_to_text(abstract: str) -> str:
    """Crossref abstracts arrive wrapped in JATS XML."""
    return html_to_text(abstract)


def alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalise(html_to_text(text)))


def numbers_in(text: str, words: bool = False) -> set[str]:
    """The numbers a text states, as plain strings: "3,367,383" is "3367383" and "14.70" is
    "14.7". With `words`, a number word ("four-year") counts as its digit, which is the form to use
    on the side that supports a claim. A claim is checked by its digits only."""
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", normalise(text))
    out = {re.sub(r"(\.\d*?)0+$", r"\1", m).rstrip(".") for m in re.findall(r"\d+(?:\.\d+)?", t)}
    if words:
        out |= {str(n) for w, n in NUMBER_WORDS.items() if re.search(rf"\b{w}\b", t)}
    return out


def is_preprint_server(doi: str = "", venue: str = "") -> bool:
    return (doi or "").lower().startswith(PREPRINT_DOI_PREFIXES) or any(
        word in alnum(venue or "") for word in PREPRINT_VENUE_WORDS)


def _entries(knowledge: dict[str, Any]):
    for i, row in enumerate(knowledge.get("playbooks", [])):
        yield f"playbooks[{i}] {row.get('species')}/{row.get('method')}", row
    for i, row in enumerate(knowledge.get("impact_findings", [])):
        yield f"impact_findings[{i}] {row.get('species')}/{row.get('zone')}", row


def citation_text(source: dict[str, Any]) -> str:
    """The reference as shown on the dashboard, built from the fields that are verified."""
    place = source["journal"]
    if source.get("volume"):
        place += f" {source['volume']}"
        if source.get("pages"):
            place += f": {source['pages']}"
    return f"{source['authors']} ({source['year']}) {source['title']}. {place}. doi:{source['doi']}"


def citation_url(source: dict[str, Any]) -> str:
    return f"https://doi.org/{source['doi']}"


# ------------------------------------------------------------------------------ structure


def validate_structure(knowledge: dict[str, Any]) -> list[Problem]:
    """Everything that can be checked without reading the sources."""
    problems: list[Problem] = []
    policy = knowledge.get("_policy") or {}
    min_year = policy.get("min_year")
    if not isinstance(min_year, int) or min_year < 2000:
        problems.append(Problem("_policy", "min_year is required: how recent a paper must be"))
        min_year = 0
    blocked = {alnum(v) for v in policy.get("blocked_venues", [])}

    sources = knowledge.get("sources", {})
    for key, s in sources.items():
        where = f"sources.{key}"
        for extra in ("url", "kind", "fetch_url"):
            if extra in s:
                problems.append(Problem(
                    where, f"{extra!r} is not allowed: only peer-reviewed papers, identified by "
                           "DOI, can be cited, never a web page, news story or fact sheet"))
        for field in PAPER_FIELDS:
            if not s.get(field):
                problems.append(Problem(where, f"missing {field}"))
        if s.get("doi") and not DOI_PATTERN.match(s["doi"]):
            problems.append(Problem(where, f"malformed doi {s['doi']!r}"))
        year = s.get("year")
        if not isinstance(year, int):
            problems.append(Problem(where, "year must be a number"))
        elif year < min_year:
            problems.append(Problem(where, f"published in {year}; the policy accepts {min_year} "
                                           "onward"))
        if s.get("journal") and alnum(s["journal"]) in blocked:
            problems.append(Problem(where, f"{s['journal']!r} is not a research journal"))
        if is_preprint_server(s.get("doi", ""), s.get("journal", "")):
            problems.append(Problem(where, "a preprint server is not peer review: cite the "
                                           "published journal article"))
    dois: dict[str, str] = {}
    for key, s in sources.items():
        doi = (s.get("doi") or "").lower()
        if doi and doi in dois:
            problems.append(Problem(f"sources.{key}", f"same doi as sources.{dois[doi]}"))
        dois[doi] = key

    used: set[str] = set()
    seen: set[tuple] = set()
    for where, row in _entries(knowledge):
        if row.get("source") not in sources:
            problems.append(Problem(where, f"unknown source {row.get('source')!r}"))
        used.add(row.get("source"))
        quotes = row.get("quotes") or []
        if not quotes:
            problems.append(Problem(where, "no quotes: no citation, no row"))
        for q in quotes:
            if len(q.strip()) < MIN_QUOTE_CHARS or len(q.split()) < MIN_QUOTE_WORDS:
                problems.append(Problem(where, f"quote too short to be evidence: {q!r}"))
        if len({squash(q) for q in quotes}) < len(quotes):
            problems.append(Problem(where, "the same quote appears twice"))
        stated = numbers_in(row.get("summary") or "")
        unquoted = stated - numbers_in(" ".join(quotes), words=True)
        if unquoted:
            problems.append(Problem(where, f"the summary states {sorted(unquoted)}, which no quote "
                                           "contains: quote the sentence that gives the figure"))
        if not (row.get("summary") or "").strip():
            problems.append(Problem(where, "empty summary"))
        if not (row.get("region_note") or "").strip():
            problems.append(Problem(where, "missing region_note: say where the evidence is from"))

        if "method" in row:
            checks = (("method", METHODS), ("study_design", DESIGNS))
            key = (row.get("species"), row.get("method"), row.get("source"), row.get("summary"))
        else:
            checks = (("finding_type", FINDING_TYPES), ("certainty", DESIGNS))
            key = (row.get("species"), row.get("zone"), row.get("source"), row.get("summary"))
            if not (row.get("affected") or "").strip():
                problems.append(Problem(where, "missing 'affected'"))
        for field, legal in checks:
            if row.get(field) not in legal:
                problems.append(Problem(where, f"{field}={row.get(field)!r} is not one of {legal}"))
        if key in seen:
            problems.append(Problem(where, "duplicate entry"))
        seen.add(key)

    for key in sources:
        if key not in used:
            problems.append(Problem(f"sources.{key}", "cited by no row; remove it"))
    return problems


# ------------------------------------------------------------------------------ the papers


def _years(crossref: dict[str, Any]) -> set[int]:
    out: set[int] = set()
    for field in ("issued", "published", "published-online", "published-print"):
        parts = (crossref.get(field) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and isinstance(parts[0][0], int):
            out.add(parts[0][0])
    return out


def _same_title(record: str, stated: str) -> bool:
    """Equal once punctuation and case are ignored. A footnote marker that the journal appends to
    the title in its record ("...upland forest1") is the only difference allowed."""
    a, b = alnum(record), alnum(stated)
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    return bool(shorter) and longer.startswith(shorter) and len(longer) - len(shorter) <= 2


def check_paper(
    key: str,
    source: dict[str, Any],
    crossref: dict[str, Any] | None,
    openalex: dict[str, Any] | None,
    policy: dict[str, Any],
) -> list[Problem]:
    """Compare one cited paper with what Crossref and OpenAlex know about its DOI."""
    where = f"sources.{key}"
    if not crossref:
        return [Problem(where, f"Crossref has no record of doi {source.get('doi')}")]
    problems: list[Problem] = []

    allowed = set(policy.get("types") or ["journal-article"])
    if crossref.get("type") not in allowed:
        problems.append(Problem(where, f"Crossref types this as {crossref.get('type')!r}, "
                                       f"not one of {sorted(allowed)}"))
    if crossref.get("subtype"):
        problems.append(Problem(where, f"Crossref marks it {crossref['subtype']!r} "
                                       "(a preprint or notice is not a published paper)"))
    venue = (crossref.get("container-title") or [""])[0]
    if not venue or not crossref.get("ISSN"):
        problems.append(Problem(where, "the journal has no ISSN on record"))
    blocked = {alnum(v) for v in policy.get("blocked_venues", [])}
    if venue and alnum(venue) in blocked:
        problems.append(Problem(where, f"{venue!r} is not a research journal"))
    if is_preprint_server(source.get("doi", ""), venue):
        problems.append(Problem(where, "a preprint server is not peer review"))
    if not crossref.get("author"):
        problems.append(Problem(where, "Crossref lists no authors"))

    title = (crossref.get("title") or [""])[0]
    if not _same_title(title, source.get("title", "")):
        problems.append(Problem(where, f"title differs from the record: {title!r}"))
    if venue and alnum(venue) != alnum(source.get("journal", "")):
        problems.append(Problem(where, f"journal differs from the record: {venue!r}"))
    years = _years(crossref)
    if source.get("year") not in years:
        problems.append(Problem(where, f"year {source.get('year')} is not in the record {years}"))
    if years and min(years) < policy.get("min_year", 0):
        problems.append(Problem(where, f"published {min(years)}, before the policy's "
                                       f"{policy.get('min_year')}"))
    if crossref.get("author"):
        first = alnum(crossref["author"][0].get("family") or crossref["author"][0].get("name", ""))
        stated = alnum((source.get("authors") or "").split(",")[0])
        if first and stated and stated not in first and first not in stated:
            problems.append(Problem(where, "first author differs from the record: "
                                           f"{crossref['author'][0].get('family')!r}"))

    notices = {str(u.get("type", "")).lower() for u in crossref.get("updated-by") or []}
    if notices & RETRACTION_NOTICES:
        problems.append(Problem(where, f"carries a notice: {sorted(notices & RETRACTION_NOTICES)}"))
    if not openalex:
        problems.append(Problem(where, "OpenAlex has no record of this doi: one index alone "
                                       "does not vouch for a paper"))
    else:
        if openalex.get("is_retracted"):
            problems.append(Problem(where, "OpenAlex marks it retracted"))
        if crossref.get("type") == "journal-article":
            kind = ((openalex.get("primary_location") or {}).get("source") or {}).get("type")
            if kind and kind != "journal":
                problems.append(Problem(where, f"OpenAlex lists the venue as a {kind!r}, "
                                               "not a journal"))
            if openalex.get("type") in NOT_PEER_REVIEWED_TYPES:
                problems.append(Problem(where, f"OpenAlex types it {openalex['type']!r}"))
        # The two indexes must describe the same paper, or the doi points at something else.
        their_doi = (openalex.get("doi") or "").lower().removeprefix("https://doi.org/")
        if their_doi and their_doi != (source.get("doi") or "").lower():
            problems.append(Problem(where, f"OpenAlex holds this doi as {their_doi!r}"))
        their_title = openalex.get("title") or openalex.get("display_name") or ""
        if their_title and title and not _same_title(their_title, title):
            problems.append(Problem(where, f"OpenAlex and Crossref disagree on the title: "
                                           f"{their_title!r}"))
        year = openalex.get("publication_year")
        if year and years and not any(abs(year - y) <= 1 for y in years):
            problems.append(Problem(where, f"OpenAlex dates it {year}; Crossref says {years}"))
    return problems


def abstract_from_openalex(inverted: dict[str, list[int]] | None) -> str:
    if not inverted:
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted.items():
        for p in positions:
            words[p] = word
    return " ".join(words[i] for i in sorted(words))


def abstracts_of(crossref: dict[str, Any] | None, openalex: dict[str, Any] | None) -> list[str]:
    """Every abstract the two services hold for a paper; a quote may appear in either."""
    found = []
    if crossref and crossref.get("abstract"):
        found.append(jats_to_text(crossref["abstract"]))
    if openalex and openalex.get("abstract_inverted_index"):
        found.append(abstract_from_openalex(openalex["abstract_inverted_index"]))
    return [t for t in found if t.strip()]


def find_problems(knowledge: dict[str, Any], texts: dict[str, list[str]]) -> list[Problem]:
    """Quotes that do not appear in the abstract of the paper they cite."""
    problems: list[Problem] = []
    for where, row in _entries(knowledge):
        source = row.get("source")
        abstracts = texts.get(source) or []
        if not abstracts:
            problems.append(Problem(where, f"no abstract was found for source {source!r}, so "
                                           "nothing can be quoted from it"))
            continue
        for q in row.get("quotes", []):
            if not any(contains(a, q) for a in abstracts):
                problems.append(Problem(where, f"quote not found in {source}: {q[:90]!r}"))
        in_abstract: set[str] = set()
        for a in abstracts:
            in_abstract |= numbers_in(a, words=True)
        for field in ("summary", "affected", "region_note"):
            missing = numbers_in(row.get(field) or "") - in_abstract
            if missing:
                problems.append(Problem(where, f"{field} states {sorted(missing)}, which the "
                                               f"abstract of {source} does not contain"))
    return problems
