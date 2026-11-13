"""Check every source and every quote in the evidence base and the paper's references.

    python scripts/verify_citations.py            # report only
    python scripts/verify_citations.py --write    # on success, stamp today's date into the file

The evidence base is db/seeds/knowledge.json and the paper's own references are
db/seeds/paper_references.json. For each cited paper this looks up its DOI in Crossref and
OpenAlex and requires a published article (not a preprint, report or extension bulletin) that
matches the title, journal, year and first author in the file, is recent enough for its role, is
not retracted, and is described the same way by both indexes. It then requires each quote to appear
in the paper's abstract, and each number a summary states to appear in a quote and in the abstract.
Records change, so the verify-citations workflow repeats this every week. A failure means a claim
no longer stands on its source: read the paper again before touching the file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

from biodiv.ingestion.http import PoliteClient
from biodiv.knowledge.references import (
    check_reference,
    find_reference_problems,
    validate_references,
)
from biodiv.knowledge.verify import (
    Problem,
    abstracts_of,
    check_paper,
    find_problems,
    validate_structure,
)

KNOWLEDGE = Path("db/seeds/knowledge.json")
REFERENCES = Path("db/seeds/paper_references.json")
UA = "biodiv-student-project/0.1 (+https://github.com/tfthushaar/biodiversity)"
CROSSREF = "https://api.crossref.org/works/"
OPENALEX = "https://api.openalex.org/works/doi:"
STALE_AFTER_YEARS = 10


async def fetch_all(sources: dict, check) -> tuple[dict[str, list[str]], list[Problem]]:
    """Look up each DOI in both indexes and apply `check(key, source, crossref, openalex)`."""
    texts: dict[str, list[str]] = {}
    problems: list[Problem] = []
    async with PoliteClient(user_agent=UA, per_second=3.0, max_concurrency=4) as http:

        async def lookup(url: str) -> dict | None:
            try:
                return await http.get_json(url)
            except Exception as exc:  # a 404 means the service does not know this DOI
                if getattr(getattr(exc, "response", None), "status_code", None) == 404:
                    return None
                raise

        async def one(key: str, source: dict) -> None:
            doi = quote(source["doi"], safe="/")
            try:
                crossref, openalex = await asyncio.gather(
                    lookup(CROSSREF + doi), lookup(OPENALEX + doi))
            except Exception as exc:
                problems.append(Problem(f"sources.{key}", f"could not look up the DOI "
                                                          f"({type(exc).__name__}: {exc})"))
                return
            message = (crossref or {}).get("message")
            problems.extend(check(key, source, message, openalex))
            texts[key] = abstracts_of(message, openalex)

        await asyncio.gather(*(one(k, s) for k, s in sources.items()))
    return texts, problems


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--write", action="store_true")
    args = p.parse_args()

    knowledge = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    refs = json.loads(REFERENCES.read_text(encoding="utf-8"))
    evidence_dois = {s["doi"].lower() for s in knowledge["sources"].values()}
    problems = list(validate_structure(knowledge)) + list(validate_references(refs, evidence_dois))
    if not problems:
        policy = knowledge.get("_policy", {})
        texts, found = asyncio.run(fetch_all(
            knowledge["sources"], lambda k, s, c, o: check_paper(k, s, c, o, policy)))
        problems += found + find_problems(knowledge, texts)
        ref_texts, ref_found = asyncio.run(fetch_all(
            refs["articles"], lambda k, a, c, o: check_reference(k, a, c, o, refs)))
        problems += ref_found + find_reference_problems(refs, ref_texts)

    rows = len(knowledge["playbooks"]) + len(knowledge["impact_findings"])
    quotes = sum(len(r["quotes"]) for r in knowledge["playbooks"] + knowledge["impact_findings"])
    if problems:
        print(f"{len(problems)} problem(s) across {rows} rows / {quotes} quotes:", file=sys.stderr)
        for line in problems:
            print("  -", line, file=sys.stderr)
        return 1

    floor = knowledge["_policy"]["min_year"]
    n = len(knowledge["sources"])
    print(f"OK: {quotes} quotes in {rows} rows, all found in the abstracts of {n} peer-reviewed "
          f"journal articles published {floor} or later")
    kept = refs["articles"].values()
    print(f"OK: the paper's own references: {len(refs['articles'])} verified articles "
          f"({sum(a['role'] == 'claim' for a in kept)} support a statement, quotes found) "
          f"and {len(refs['resources'])} named resources")
    if date.today().year - floor > STALE_AFTER_YEARS:
        print(f"note: the policy accepts papers from {floor}, more than {STALE_AFTER_YEARS} years "
              "ago; raise min_year in knowledge.json (and the check in migration 0020)",
              file=sys.stderr)
    if args.write:
        knowledge["verified_on"] = date.today().isoformat()
        KNOWLEDGE.write_text(json.dumps(knowledge, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        print("stamped verified_on", knowledge["verified_on"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
