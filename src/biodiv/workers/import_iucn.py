"""Import IUCN Red List threat links: native species threatened by named invasive species.

    python -m biodiv.workers.import_iucn [--countries IN TZ US] [--limit N] [--dry-run]

Needs IUCN_API_TOKEN. The rows go into `threat_links` with evidence_source 'iucn', where the
database hides them from the public API: IUCN's terms prohibit redistributing its data without
permission (docs/iucn.md, migration 0017). Re-running skips assessments already imported.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass

import psycopg

from biodiv.core.repo import upsert_species
from biodiv.core.settings import get_settings
from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.iucn import NAMED_SPECIES_THREAT, IucnClient, Threat, parse_assessment

log = logging.getLogger(__name__)
CODE = NAMED_SPECIES_THREAT.replace("_", ".")


@dataclass
class ImportStats:
    candidates: int = 0
    skipped: int = 0
    fetched: int = 0
    links: int = 0
    unresolved_invaders: int = 0


def _find_species(conn: psycopg.Connection, name: str) -> int | None:
    row = conn.execute(
        "select id from species where lower(scientific_name) = lower(%s) "
        "order by (gbif_taxon_key is null), id limit 1",
        (name,),
    ).fetchone()
    return row[0] if row else None


def store(conn: psycopg.Connection, t: Threat, version: str) -> bool:
    """Store one link. Returns whether the invasive species was matched to a species row."""
    native = _find_species(conn, t.native_name) or upsert_species(
        conn, gbif_key=None, name=t.native_name, kingdom=t.kingdom, rank="SPECIES"
    )
    invader = _find_species(conn, t.invasive_name)
    citation = (
        f"IUCN. The IUCN Red List of Threatened Species, version {version}. {t.citation}".strip()
    )
    conn.execute(
        """
        insert into threat_links (native_species_id, invasive_species_id, invasive_name,
                                  iucn_threat_code, severity, scope, timing, assessment_year,
                                  citation, evidence_source, citation_url)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'iucn', %s)
        on conflict (native_species_id, coalesce(invasive_species_id, 0),
                     coalesce(invasive_name, ''), evidence_source, coalesce(iucn_threat_code, ''))
        do update set severity = excluded.severity, scope = excluded.scope,
                      timing = excluded.timing, assessment_year = excluded.assessment_year,
                      citation = excluded.citation, citation_url = excluded.citation_url
        """,
        (native, invader, t.invasive_name, CODE, t.score, t.scope, t.timing, t.year,
         citation, t.url),
    )
    return invader is not None


async def collect(client: IucnClient, countries: list[str]) -> dict[int, dict]:
    """Assessments that name an invasive species and occur in any of the countries."""
    named = await client.assessment_ids(f"/threats/{NAMED_SPECIES_THREAT}")
    log.info("%d assessments list threat %s", len(named), CODE)
    found: dict[int, dict] = {}
    for code in countries:
        here = await client.assessment_ids(f"/countries/{code}")
        hits = {i: a for i, a in here.items() if i in named}
        log.info("%s: %d assessments, %d name an invasive species", code, len(here), len(hits))
        found.update(hits)
    return found


async def run(
    conn: psycopg.Connection | None,
    client: IucnClient,
    countries: list[str],
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> tuple[ImportStats, list[Threat]]:
    stats = ImportStats()
    version = await client.red_list_version()
    candidates = await collect(client, countries)
    stats.candidates = len(candidates)
    done: set[str] = set()
    if conn is not None:
        done = {
            r[0] for r in conn.execute(
                "select distinct citation_url from threat_links where evidence_source = 'iucn'")
        }
    seen: list[Threat] = []
    for aid, summary in sorted(candidates.items()):
        if limit is not None and stats.fetched >= limit:
            break
        if summary.get("url") in done:
            stats.skipped += 1
            continue
        stats.fetched += 1
        threats = parse_assessment(await client.assessment(aid))
        seen.extend(threats)
        if dry_run or conn is None:
            continue
        with conn.transaction():
            for t in threats:
                stats.links += 1
                if not store(conn, t, version):
                    stats.unresolved_invaders += 1
    return stats, seen


async def _amain(args: argparse.Namespace) -> tuple[ImportStats, list[Threat]]:
    settings = get_settings()
    async with PoliteClient(user_agent=settings.user_agent, per_second=args.rate,
                            max_concurrency=1, retries=6, backoff=2.0) as http:
        client = IucnClient(http, settings.iucn_api_token)
        if args.dry_run:
            return await run(None, client, args.countries, limit=args.limit, dry_run=True)
        with psycopg.connect(settings.database_url, autocommit=True) as conn:
            return await run(conn, client, args.countries, limit=args.limit)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--countries", nargs="+", default=["IN", "TZ", "US"])
    p.add_argument("--limit", type=int, default=None, help="fetch at most this many assessments")
    p.add_argument("--dry-run", action="store_true", help="read and parse, write nothing")
    p.add_argument("--rate", type=float, default=1.0, help="requests per second")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    if not settings.iucn_api_token:
        print("IUCN_API_TOKEN is not set", file=sys.stderr)
        return 2
    if not args.dry_run and not settings.database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    stats, seen = asyncio.run(_amain(args))
    if args.dry_run:
        for t in seen:
            print(f"{t.native_name} <- {t.invasive_name} ({t.scope}, {t.timing}, {t.score})")
    print(
        f"{stats.candidates} candidate assessments, {stats.skipped} already imported, "
        f"{stats.fetched} fetched, {stats.links} links stored, "
        f"{stats.unresolved_invaders} named invaders not in the species table"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
