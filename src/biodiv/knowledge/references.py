"""The paper's own references: every one a verified peer-reviewed article, or a named resource.

The evidence base (`db/seeds/knowledge.json`) holds the papers that back findings about species.
A paper about invasive species cites more than that: the sources of its statistics, the tools it
used, the studies behind its background statements. This registry holds those, under the same
rule as the evidence base: no preprints and nothing that cannot be looked up.

Each reference is one of two kinds, and the paper's text may use only these.

  * An **article** has a DOI and is checked against Crossref and OpenAlex. Its role says what the
    paper does with it. A `claim` article supports a statement about the world, so it carries
    verbatim quotes from its abstract, like the evidence base, and must be recent. A `method`
    article is the source of a statistical method or software (Mann 1945, SciPy 2020), and a
    `dataset` article describes the data the study used. Neither supports a claim about invasive
    species, so neither needs a quote, and neither is held to the recency rule.
  * A **resource** is data, software or a model the study used: GBIF, iNaturalist, MegaDetector.
    It is credited by name and link, never cited as evidence, and the text mentions it by name.

An article published only as a preprint, or without a DOI that the two indexes agree on, cannot be
an article here. It can be a resource if the study used it as a tool, and then the text says what
it is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from biodiv.knowledge.verify import (
    DOI_PATTERN,
    MIN_QUOTE_CHARS,
    MIN_QUOTE_WORDS,
    Problem,
    abstracts_of,
    alnum,
    check_paper,
    citation_text,
    contains,
    is_preprint_server,
    squash,
)

ROLES = {"claim", "method", "dataset"}
KINDS = {"data", "software", "model"}
ARTICLE_TYPES = ["journal-article", "proceedings-article", "book-chapter"]
ARTICLE_FIELDS = ("doi", "title", "authors", "year", "journal", "role")
RESOURCE_FIELDS = ("name", "mention", "year", "title", "url", "kind")
DEFAULT_PATH = Path("db/seeds/paper_references.json")


def load(path: Path | str = DEFAULT_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def first_surname(authors: str) -> str:
    """"Negi, V.S., Maikhuri, R.K." -> "Negi". Authors are written surname first."""
    return (authors or "").split(",")[0].strip()


def validate_references(
    refs: dict[str, Any], evidence_dois: set[str] | None = None
) -> list[Problem]:
    """Everything that can be checked without the network."""
    problems: list[Problem] = []
    policy = refs.get("_policy") or {}
    claim_min_year = policy.get("claim_min_year")
    if not isinstance(claim_min_year, int) or claim_min_year < 2000:
        problems.append(Problem("_policy", "claim_min_year is required: how recent a paper that "
                                           "supports a statement must be"))
        claim_min_year = 0

    seen: dict[str, str] = {}
    for key, a in (refs.get("articles") or {}).items():
        where = f"articles.{key}"
        for field in ARTICLE_FIELDS:
            if not a.get(field):
                problems.append(Problem(where, f"missing {field}"))
        for extra in ("url", "kind", "fetch_url"):
            if extra in a:
                problems.append(Problem(where, f"{extra!r} is not allowed on an article: it is "
                                               "identified by its DOI"))
        doi = a.get("doi") or ""
        if doi and not DOI_PATTERN.match(doi):
            problems.append(Problem(where, f"malformed doi {doi!r}"))
        if is_preprint_server(doi, a.get("journal", "")):
            problems.append(Problem(where, "a preprint server is not peer review"))
        if doi.lower() in seen:
            problems.append(Problem(where, f"same doi as articles.{seen[doi.lower()]}"))
        seen[doi.lower()] = key
        if evidence_dois and doi.lower() in evidence_dois:
            problems.append(Problem(where, "already in the evidence base: cite it there"))
        if not isinstance(a.get("year"), int):
            problems.append(Problem(where, "year must be a number"))
        role = a.get("role")
        if role and role not in ROLES:
            problems.append(Problem(where, f"role={role!r} is not one of {sorted(ROLES)}"))
        quotes = a.get("quotes") or []
        if role == "claim":
            if isinstance(a.get("year"), int) and a["year"] < claim_min_year:
                problems.append(Problem(where, f"supports a statement but dates from {a['year']}; "
                                               f"the policy accepts {claim_min_year} onward"))
            if not quotes:
                problems.append(Problem(where, "a claim needs a verbatim quote from the abstract"))
            for q in quotes:
                if len(q.strip()) < MIN_QUOTE_CHARS or len(q.split()) < MIN_QUOTE_WORDS:
                    problems.append(Problem(where, f"quote too short to be evidence: {q!r}"))
            if len({squash(q) for q in quotes}) < len(quotes):
                problems.append(Problem(where, "the same quote appears twice"))
        elif quotes:
            problems.append(Problem(where, f"a {role} reference supports no claim: no quotes"))

    for key, r in (refs.get("resources") or {}).items():
        where = f"resources.{key}"
        for field in RESOURCE_FIELDS:
            if not r.get(field):
                problems.append(Problem(where, f"missing {field}"))
        if r.get("kind") and r["kind"] not in KINDS:
            problems.append(Problem(where, f"kind={r['kind']!r} is not one of {sorted(KINDS)}"))
        if r.get("url") and not str(r["url"]).startswith("https://"):
            problems.append(Problem(where, "url must be an https link"))
    return problems


def policy_for(refs: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    """The rules for checking one article against the indexes."""
    base = refs.get("_policy") or {}
    recent = article.get("role") == "claim"
    return {"types": ARTICLE_TYPES, "min_year": base.get("claim_min_year", 0) if recent else 0,
            "blocked_venues": base.get("blocked_venues", [])}


def check_reference(key: str, article: dict[str, Any], crossref: dict[str, Any] | None,
                    openalex: dict[str, Any] | None, refs: dict[str, Any]) -> list[Problem]:
    found = check_paper(key, article, crossref, openalex, policy_for(refs, article))
    return [Problem(f"articles.{p.where.removeprefix('sources.')}", p.message) for p in found]


def find_reference_problems(refs: dict[str, Any], texts: dict[str, list[str]]) -> list[Problem]:
    """Quotes of a claim article that are not in its abstract."""
    problems: list[Problem] = []
    for key, a in (refs.get("articles") or {}).items():
        if a.get("role") != "claim":
            continue
        abstracts = texts.get(key) or []
        if not abstracts:
            problems.append(Problem(f"articles.{key}", "no abstract was found, so nothing can be "
                                                       "quoted from it"))
            continue
        for q in a.get("quotes", []):
            if not any(contains(t, q) for t in abstracts):
                problems.append(Problem(f"articles.{key}", f"quote not found: {q[:90]!r}"))
    return problems


def abstract_texts(key: str, crossref: dict[str, Any] | None, openalex: dict[str, Any] | None
                   ) -> dict[str, list[str]]:
    return {key: abstracts_of(crossref, openalex)}


# ------------------------------------------------------------------------------ rendering


def render_article(a: dict[str, Any]) -> str:
    return citation_text(a)


def render_resource(r: dict[str, Any]) -> str:
    return f"{r['name']} ({r['year']}) {r['title']}. {r['url']}"


def articles_sorted(refs: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted((refs.get("articles") or {}).values(),
                  key=lambda a: (alnum(first_surname(a["authors"])), a["year"]))


def render_references(refs: dict[str, Any]) -> str:
    """The Markdown the paper ends with: the verified articles, then the resources."""
    articles = "\n\n".join(render_article(a) for a in articles_sorted(refs))
    resources = "\n\n".join(render_resource(r) for r in sorted(
        (refs.get("resources") or {}).values(), key=lambda r: alnum(r["name"])))
    return (
        f"{articles}\n\n### Data, software and models\n\n"
        "These were used by the study. None of them is cited as evidence about a species.\n\n"
        f"{resources}"
    )


def match_name_year(refs: dict[str, Any]) -> dict[tuple[str, int], list[str]]:
    index: dict[tuple[str, int], list[str]] = {}
    for key, a in (refs.get("articles") or {}).items():
        index.setdefault((alnum(first_surname(a["authors"])), a["year"]), []).append(key)
    return index

