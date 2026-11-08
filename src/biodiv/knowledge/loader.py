"""Load db/seeds/knowledge.json into the database. Idempotent.

The file holds peer-reviewed papers and the claims that rest on them. The loader refuses a file
that breaks the rules in `verify.validate_structure`, and builds each reference from the paper's
verified fields, so the text on the dashboard is the text that was checked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from biodiv.knowledge.verify import citation_text, citation_url, validate_structure


class KnowledgeError(RuntimeError):
    pass


@dataclass
class LoadStats:
    playbooks: int = 0
    findings: int = 0
    pruned: int = 0


def _species_id(conn: psycopg.Connection, name: str) -> int:
    row = conn.execute(
        "select id from species where lower(scientific_name) = lower(%s) order by id limit 1",
        (name,),
    ).fetchone()
    if row is None:
        raise KnowledgeError(
            f"species {name!r} is not in the database. Import the GRIIS checklist first "
            "(python -m biodiv.workers.import_griis), which creates the species rows."
        )
    return row[0]


def _zone_id(conn: psycopg.Connection, slug: str | None) -> int | None:
    if slug is None:
        return None
    row = conn.execute("select id from zones where slug = %s", (slug,)).fetchone()
    if row is None:
        raise KnowledgeError(f"zone {slug!r} is not in the database; run migrate --seed")
    return row[0]


def load_knowledge(
    conn: psycopg.Connection, knowledge: dict[str, Any], *, prune: bool = False
) -> LoadStats:
    problems = validate_structure(knowledge)
    if problems:
        raise KnowledgeError("knowledge file is invalid:\n  " + "\n  ".join(map(str, problems)))
    sources = knowledge["sources"]
    stamp = knowledge.get("verified_on")
    verified = date.fromisoformat(stamp) if stamp else None
    stats = LoadStats()
    keep_playbooks: list[int] = []
    keep_findings: list[int] = []

    with conn.transaction():
        for p in knowledge["playbooks"]:
            src = sources[p["source"]]
            keep_playbooks.append(conn.execute(
                """
                insert into mitigation_playbooks
                  (species_id, method, description, study_design, citation_text, citation_url,
                   citation_doi, citation_year, citation_journal, source_quotes, region_note,
                   verified_on, origin)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'knowledge.json')
                on conflict (species_id, method, citation_url, description) do update set
                  study_design = excluded.study_design, citation_text = excluded.citation_text,
                  citation_doi = excluded.citation_doi, citation_year = excluded.citation_year,
                  citation_journal = excluded.citation_journal,
                  source_quotes = excluded.source_quotes, region_note = excluded.region_note,
                  verified_on = excluded.verified_on
                returning id
                """,
                (_species_id(conn, p["species"]), p["method"], p["summary"], p["study_design"],
                 citation_text(src), citation_url(src), src["doi"], src["year"], src["journal"],
                 Jsonb(p["quotes"]), p["region_note"], verified),
            ).fetchone()[0])
            stats.playbooks += 1

        for f in knowledge["impact_findings"]:
            src = sources[f["source"]]
            keep_findings.append(conn.execute(
                """
                insert into impact_findings
                  (invasive_species_id, zone_id, finding_type, affected, summary, certainty,
                   region_note, source_quotes, citation_text, citation_url, citation_doi,
                   citation_year, citation_journal, verified_on, origin)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'knowledge.json')
                on conflict (invasive_species_id, coalesce(zone_id, 0), citation_url,
                             finding_type, affected) do update set
                  summary = excluded.summary, certainty = excluded.certainty,
                  region_note = excluded.region_note, source_quotes = excluded.source_quotes,
                  citation_text = excluded.citation_text, citation_doi = excluded.citation_doi,
                  citation_year = excluded.citation_year,
                  citation_journal = excluded.citation_journal, verified_on = excluded.verified_on
                returning id
                """,
                (_species_id(conn, f["species"]), _zone_id(conn, f["zone"]), f["finding_type"],
                 f["affected"], f["summary"], f["certainty"], f["region_note"],
                 Jsonb(f["quotes"]), citation_text(src), citation_url(src), src["doi"],
                 src["year"], src["journal"], verified),
            ).fetchone()[0])
            stats.findings += 1

        if prune:  # remove rows this loader created earlier that are no longer in the file
            stats.pruned += conn.execute(
                "delete from mitigation_playbooks where origin = 'knowledge.json' "
                "and not (id = any(%s))", (keep_playbooks,)).rowcount
            stats.pruned += conn.execute(
                "delete from impact_findings where origin = 'knowledge.json' "
                "and not (id = any(%s))", (keep_findings,)).rowcount
    return stats


def load_file(conn: psycopg.Connection, path: str, *, prune: bool = False) -> LoadStats:
    with open(path, encoding="utf-8") as f:
        return load_knowledge(conn, json.load(f), prune=prune)
