"""Import a GRIIS country checklist: which species are introduced / invasive where.

    python -m biodiv.workers.import_griis --resource griis-india

The GBIF name-matching results are cached in data/gbif_match_cache.json so a re-run is fast
and gentle on GBIF.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg

from biodiv.core.repo import upsert_invasive_status, upsert_species
from biodiv.core.settings import get_settings
from biodiv.ingestion.gbif import GbifClient, GbifTaxon, load_cache, save_cache
from biodiv.ingestion.griis import (
    GRIIS_ARCHIVE_URL,
    filter_usable,
    parse_archive,
    resolve_records,
)
from biodiv.ingestion.http import PoliteClient

DEFAULT_CACHE = Path("data") / "gbif_match_cache.json"


@dataclass
class ImportStats:
    records: int = 0
    doubtful_skipped: int = 0
    species: int = 0
    gbif_matched: int = 0
    gbif_unmatched: int = 0
    invasive: int = 0


async def import_griis(
    conn: psycopg.Connection,
    http: PoliteClient,
    resource: str,
    cache: dict[str, GbifTaxon | None] | None = None,
) -> ImportStats:
    archive = await http.get_bytes(GRIIS_ARCHIVE_URL, {"r": resource})
    records, doubtful = filter_usable(parse_archive(archive))
    entries = await resolve_records(records, GbifClient(http), cache)

    stats = ImportStats(records=len(records), doubtful_skipped=doubtful, species=len(entries))
    with conn.transaction():
        source_id = conn.execute(
            """
            insert into sources (name, kind, base_url, license, attribution)
            values ('GRIIS', 'dataset', %s, 'CC BY 4.0',
                    'Global Register of Introduced and Invasive Species (GRIIS), via GBIF')
            on conflict (name) do update set base_url = excluded.base_url
            returning id
            """,
            (f"{GRIIS_ARCHIVE_URL}?r={resource}",),
        ).fetchone()[0]
        run_id = conn.execute(
            "insert into ingestion_runs (source_id, notes) values (%s, %s) returning id",
            (source_id, resource),
        ).fetchone()[0]

        for e in entries:
            species_id = upsert_species(
                conn, gbif_key=e.gbif_key, name=e.name, kingdom=e.kingdom, rank=e.rank
            )
            upsert_invasive_status(
                conn,
                species_id=species_id,
                country=e.country,
                is_invasive=e.is_invasive,
                establishment_means=e.establishment_means,
                occurrence_status=e.occurrence_status,
                habitat=e.habitat,
                source="GRIIS",
                source_ref=f"{resource}:{e.source_ref}",
            )
            stats.gbif_matched += e.gbif_key is not None
            stats.gbif_unmatched += e.gbif_key is None
            stats.invasive += bool(e.is_invasive)

        conn.execute(
            "update ingestion_runs set finished_at = now(), fetched = %s, notes = %s where id = %s",
            (stats.species, f"{resource}: {stats.doubtful_skipped} doubtful skipped", run_id),
        )
    return stats


async def _amain(args: argparse.Namespace) -> ImportStats:
    cache_path = Path(args.cache)
    cache = load_cache(cache_path)
    try:
        async with PoliteClient(
            user_agent=get_settings().user_agent, per_second=args.rate, max_concurrency=8
        ) as http:
            with psycopg.connect(get_settings().database_url) as conn:
                return await import_griis(conn, http, args.resource, cache)
    finally:
        save_cache(cache_path, cache)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--resource", default="griis-india", help="GBIF IPT resource, e.g. griis-india")
    p.add_argument("--cache", default=str(DEFAULT_CACHE))
    p.add_argument("--rate", type=float, default=10.0, help="max requests/second to GBIF")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request is noise

    if not get_settings().database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    s = asyncio.run(_amain(args))
    print(
        f"{args.resource}: {s.records} records ({s.doubtful_skipped} doubtful skipped) -> "
        f"{s.species} species, {s.invasive} invasive; GBIF matched {s.gbif_matched}, "
        f"unmatched {s.gbif_unmatched}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
