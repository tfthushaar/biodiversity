"""Check every quote in db/seeds/knowledge.json against its live source.

    python scripts/verify_citations.py            # report only
    python scripts/verify_citations.py --write    # on success, stamp today's date into the file

Pages can change or disappear, so this is worth re-running (the verify-citations workflow does it
weekly). A failure means a quote is no longer on the page: re-read the source before touching it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from biodiv.ingestion.http import PoliteClient
from biodiv.knowledge.verify import find_problems, html_to_text, jats_to_text, validate_structure

KNOWLEDGE = Path("db/seeds/knowledge.json")
UA = "Mozilla/5.0 (compatible; biodiv-student-project/0.1; +https://github.com/tfthushaar/biodiversity)"


async def fetch_all(sources: dict[str, dict]) -> tuple[dict[str, str], list[str]]:
    texts: dict[str, str] = {}
    errors: list[str] = []
    async with PoliteClient(user_agent=UA, per_second=2.0, max_concurrency=4) as http:

        async def one(key: str, s: dict) -> None:
            try:
                if s["kind"] == "crossref":
                    msg = (await http.get_json(f"https://api.crossref.org/works/{s['doi']}"))["message"]
                    texts[key] = jats_to_text(msg.get("abstract", ""))
                else:
                    resp = await http.get(s.get("fetch_url") or s["url"])
                    texts[key] = html_to_text(resp.text)
            except Exception as exc:
                errors.append(f"{key}: could not fetch ({type(exc).__name__}: {exc})")

        await asyncio.gather(*(one(k, s) for k, s in sources.items()))
    return texts, errors


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--write", action="store_true")
    args = p.parse_args()

    knowledge = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    problems = [str(x) for x in validate_structure(knowledge)]
    texts, errors = asyncio.run(fetch_all(knowledge["sources"]))
    problems += errors + [str(x) for x in find_problems(knowledge, texts)]

    rows = len(knowledge["playbooks"]) + len(knowledge["impact_findings"])
    quotes = sum(len(r["quotes"]) for r in knowledge["playbooks"] + knowledge["impact_findings"])
    if problems:
        print(f"{len(problems)} problem(s) across {rows} rows / {quotes} quotes:", file=sys.stderr)
        for line in problems:
            print("  -", line, file=sys.stderr)
        return 1
    print(f"OK: {quotes} quotes in {rows} rows all found in {len(texts)} sources")
    if args.write:
        knowledge["verified_on"] = date.today().isoformat()
        KNOWLEDGE.write_text(json.dumps(knowledge, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        print("stamped verified_on", knowledge["verified_on"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
