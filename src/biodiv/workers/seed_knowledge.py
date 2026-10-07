"""Load the curated, cited knowledge base (mitigation playbooks, impact findings).

    python -m biodiv.workers.seed_knowledge [--prune]

Run after the GRIIS import, which creates the species rows these entries refer to.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

from biodiv.core.settings import get_settings
from biodiv.knowledge.loader import KnowledgeError, load_file

KNOWLEDGE = Path(__file__).resolve().parents[3] / "db" / "seeds" / "knowledge.json"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--prune", action="store_true",
                   help="delete rows this loader created earlier that are no longer in the file")
    p.add_argument("--file", default=str(KNOWLEDGE))
    args = p.parse_args(argv)
    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        with psycopg.connect(url) as conn:
            s = load_file(conn, args.file, prune=args.prune)
    except KnowledgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"loaded {s.playbooks} playbook rows and {s.findings} impact findings"
          + (f"; pruned {s.pruned}" if args.prune else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
