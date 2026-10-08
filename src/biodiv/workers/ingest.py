"""Fetch observations for monitored zones and store them.

    python -m biodiv.workers.ingest --source inaturalist [--zone bandipur ...] [--max 5000]
    python -m biodiv.workers.ingest --source gbif --gbif-dataset specimens
    python -m biodiv.workers.ingest --source gbif --gbif-dataset ebird --max 2000

Incremental by default: each (source, zone) remembers where it got to. Re-running stores
nothing twice. Records that fail validation are counted by reason, not silently dropped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from biodiv.core.repo import upsert_species
from biodiv.core.settings import get_settings
from biodiv.ingestion import usgs_nas
from biodiv.ingestion.gbif import (
    GbifClient,
    TaxonCache,
    cache_key,
    load_cache,
    resolve_into_cache,
    save_cache,
)
from biodiv.ingestion.gbif_occurrences import (
    DEFAULT_BASIS,
    EBIRD_DATASET,
    GBIF_OCCURRENCE_API,
    is_inaturalist_mirror,
    iter_occurrences,
    parse_occurrence,
)
from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.inaturalist import INAT_API, iter_observations, parse_observation
from biodiv.ingestion.observations import Observation, validate
from biodiv.workers.retention import STOP_AT, storage

log = logging.getLogger(__name__)

BATCH_SIZE = 200
DEFAULT_CACHE = Path("data") / "gbif_match_cache.json"
FIRST_PARTITIONED_YEAR = 2000  # earlier rows fall into the default partition


@dataclass(frozen=True)
class Zone:
    id: int
    slug: str
    country: str
    bbox: tuple[float, float, float, float]  # west, south, east, north


@dataclass(frozen=True)
class SourceSpec:
    name: str
    base_url: str
    license: str
    attribution: str


SOURCES = {
    "inaturalist": SourceSpec(
        "iNaturalist", INAT_API, "Per record (CC); see media_items.license",
        "iNaturalist contributors",
    ),
    "gbif": SourceSpec(
        "GBIF occurrences", GBIF_OCCURRENCE_API, "Per record (CC); see media_items.license",
        "Occurrence data via GBIF.org",
    ),
    "usgs_nas": SourceSpec(
        "USGS NAS", usgs_nas.NAS_API, usgs_nas.NAS_LICENSE,
        "U.S. Geological Survey, Nonindigenous Aquatic Species Database",
    ),
}

PARSERS = {
    "inaturalist": parse_observation,
    "gbif": parse_occurrence,
    "usgs_nas": usgs_nas.parse_occurrence,
}


@dataclass
class IngestStats:
    fetched: int = 0
    stored: int = 0
    skipped_dupe: int = 0
    rejected: Counter[str] = field(default_factory=Counter)
    stopped_early: bool = False  # ran out of the time allowed; the next run carries on

    def merge(self, other: IngestStats) -> None:
        self.stopped_early = self.stopped_early or other.stopped_early
        self.fetched += other.fetched
        self.stored += other.stored
        self.skipped_dupe += other.skipped_dupe
        self.rejected.update(other.rejected)


def load_zones(conn: psycopg.Connection, slugs: list[str] | None) -> list[Zone]:
    rows = conn.execute(
        "select id, slug, country, st_xmin(geom), st_ymin(geom), st_xmax(geom), st_ymax(geom) "
        "from zones where %s::text[] is null or slug = any(%s::text[]) "
        # Parks with the fewest stored records first, so a new park fills before the time limit
        # is spent on parks that are already well covered.
        "order by (select count(*) from media_items m where m.zone_id = zones.id), id",
        (slugs or None, slugs or None),
    ).fetchall()
    return [Zone(r[0], r[1], r[2], (r[3], r[4], r[5], r[6])) for r in rows]


def _ensure_source(conn: psycopg.Connection, spec: SourceSpec) -> int:
    return conn.execute(
        """
        insert into sources (name, kind, base_url, license, attribution)
        values (%s, 'api', %s, %s, %s)
        on conflict (name) do update set base_url = excluded.base_url
        returning id
        """,
        (spec.name, spec.base_url, spec.license, spec.attribution),
    ).fetchone()[0]


def _in_bbox(obs: Observation, bbox: tuple[float, float, float, float]) -> bool:
    west, south, east, north = bbox
    return west <= obs.lon <= east and south <= obs.lat <= north


def _out_of_time(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _save_cursor(conn: psycopg.Connection, source_id: int, scope: str, cursor: str) -> None:
    conn.execute(
        """
        insert into ingestion_cursors (source_id, scope, cursor) values (%s, %s, %s)
        on conflict (source_id, scope) do update
          set cursor = excluded.cursor, updated_at = now()
        """,
        (source_id, scope, cursor),
    )


def _zones_for(conn: psycopg.Connection, batch: list[Observation]) -> list[int | None]:
    """The park containing each observation, or None, found with one query for the whole batch.

    A search box is larger than the park inside it, so many records fall outside every boundary.
    Asking the database about each one separately costs a round trip apiece.
    """
    rows = conn.execute(
        """
        select o.i,
               (select z.id from zones z
                where st_within(st_setsrid(st_makepoint(o.lon, o.lat), 4326), z.geom)
                order by z.id limit 1)
        from unnest(%s::float8[], %s::float8[]) with ordinality as o(lon, lat, i)
        """,
        ([x.lon for x in batch], [x.lat for x in batch]),
    ).fetchall()
    found = dict(rows)
    return [found.get(i + 1) for i in range(len(batch))]


def _store(
    conn: psycopg.Connection, obs: Observation, source_id: int, species_id_fn, zone_id: int
) -> str:
    """Store one observation inside a known park. Returns 'stored' or 'duplicate'."""
    zone = (zone_id,)
    media = conn.execute(
        """
        insert into media_items (source_id, external_id, uri, image_url, captured_at, geom,
                                 zone_id, width, height, license, status)
        values (%s, %s, %s, %s, %s, st_setsrid(st_makepoint(%s, %s), 4326), %s, %s, %s, %s, 'done')
        on conflict (source_id, external_id) do nothing
        returning id
        """,
        (source_id, obs.external_id, obs.record_url, obs.image_url, obs.captured_at,
         obs.lon, obs.lat, zone[0], obs.width, obs.height, obs.record_license),
    ).fetchone()
    if media is None:
        return "duplicate"

    conn.execute(
        """
        insert into detections (media_item_id, captured_at, species_id, label_raw, confidence,
                                geom, zone_id, origin)
        values (%s, %s, %s, %s, 1.0, st_setsrid(st_makepoint(%s, %s), 4326), %s, 'observer')
        """,
        (media[0], obs.captured_at, species_id_fn(obs), obs.taxon_name, obs.lon, obs.lat, zone[0]),
    )
    return "stored"


async def _flush(
    conn: psycopg.Connection,
    batch: list[Observation],
    source_id: int,
    gbif: GbifClient,
    cache: TaxonCache,
    stats: IngestStats,
    species_ids: dict | None = None,
) -> None:
    if not batch:
        return
    # Species already stored earlier in this run are remembered, so a species seen a hundred times
    # costs one round trip to the database, not a hundred. That matters on a slow link: a run on
    # a US runner against a database in Asia pays about 0.2 s for every round trip.
    memo = species_ids if species_ids is not None else {}
    # Records already stored are recognised with one query for the whole batch. A re-run reads the
    # same records again, and a round trip each would make that slow over a distant database.
    known = {
        row[0]
        for row in conn.execute(
            "select external_id from media_items where source_id = %s and external_id = any(%s)",
            (source_id, [o.external_id for o in batch]),
        )
    }
    stats.skipped_dupe += sum(o.external_id in known for o in batch)
    batch[:] = [o for o in batch if o.external_id not in known]
    if not batch:
        return

    # Records outside every park boundary are set aside now, before any taxonomy lookups.
    zone_ids = _zones_for(conn, batch)
    if outside := sum(z is None for z in zone_ids):
        stats.rejected["outside_zone"] += outside
    inside = [(o, z) for o, z in zip(batch, zone_ids, strict=True) if z is not None]
    batch[:] = [o for o, _ in inside]
    zone_of = [z for _, z in inside]
    if not batch:
        return

    # Taxonomy first (network), then one transaction for the whole batch (database).
    await resolve_into_cache(
        gbif, [(o.taxon_name, o.kingdom) for o in batch if o.gbif_taxon_key is None], cache
    )

    def species_id(obs: Observation) -> int:
        taxon = None if obs.gbif_taxon_key else cache.get(cache_key(obs.taxon_name, obs.kingdom))
        gbif_key = obs.gbif_taxon_key or (taxon.key if taxon else None)
        name = taxon.canonical_name if taxon else obs.taxon_name
        kingdom = (taxon.kingdom if taxon else None) or obs.kingdom
        rank = obs.rank.upper() or None
        key = (gbif_key, name, kingdom, rank)
        if key not in memo:
            memo[key] = upsert_species(
                conn, gbif_key=gbif_key, name=name, kingdom=kingdom, rank=rank,
                common_name=obs.common_name, inat_taxon_id=obs.inat_taxon_id,
            )
        return memo[key]

    try:
        with conn.transaction():
            for year in sorted({o.captured_at.year for o in batch if o.captured_at}):
                if year >= FIRST_PARTITIONED_YEAR:
                    conn.execute("select ensure_detection_partition(%s)", (year,))
            for obs, zone_id in zip(batch, zone_of, strict=True):
                outcome = _store(conn, obs, source_id, species_id, zone_id)
                if outcome == "stored":
                    stats.stored += 1
                elif outcome == "duplicate":
                    stats.skipped_dupe += 1
                else:
                    stats.rejected[outcome] += 1
    except Exception:
        memo.clear()  # ids remembered from a rolled-back transaction would point at nothing
        raise
    batch.clear()


async def ingest_zone(
    conn: psycopg.Connection,
    zone: Zone,
    *,
    source: str,
    raw_http: PoliteClient,
    gbif_http: PoliteClient,
    cache: TaxonCache,
    max_results: int = 5000,
    full: bool = False,
    gbif_dataset: str = "specimens",
    deadline: float | None = None,
    species_ids: dict | None = None,
    max_stored: int | None = None,
) -> IngestStats:
    if not conn.autocommit:
        raise ValueError("ingest needs an autocommit connection; each batch is its own transaction")
    if source == "usgs_nas" and zone.slug not in usgs_nas.ZONE_COUNTIES:
        return IngestStats()  # NAS covers the United States only

    spec = SOURCES[source]
    source_id = _ensure_source(conn, spec)
    if max_stored is not None:
        held = conn.execute(
            "select count(*) from media_items where zone_id = %s and source_id = %s",
            (zone.id, source_id),
        ).fetchone()[0]
        if held >= max_stored:
            log.info("%s %s: %d stored, at the cap of %d", zone.slug, source, held, max_stored)
            return IngestStats()
    if source == "inaturalist":
        scope = zone.slug
    elif source == "usgs_nas":
        scope = f"{zone.slug}:nas"
    else:
        scope = f"{zone.slug}:{gbif_dataset}"
    row = conn.execute(
        "select cursor from ingestion_cursors where source_id = %s and scope = %s",
        (source_id, scope),
    ).fetchone()
    cursor = None if full or row is None else row[0]

    run_id = conn.execute(
        "insert into ingestion_runs (source_id, notes) values (%s, %s) returning id",
        (source_id, f"{scope} (cursor={cursor})"),
    ).fetchone()[0]
    started = datetime.now(UTC).date().isoformat()

    stats = IngestStats()
    gbif = GbifClient(gbif_http)
    new_cursor = cursor
    batch: list[Observation] = []
    error: str | None = None

    raw: AsyncIterator[dict[str, Any]]
    if source == "inaturalist":
        raw = iter_observations(
            raw_http, zone.bbox, id_above=int(cursor or 0), max_results=max_results
        )
    elif source == "usgs_nas":
        raw = usgs_nas.iter_occurrences(
            raw_http, usgs_nas.ZONE_COUNTIES[zone.slug], max_results=max_results
        )
    elif gbif_dataset == "ebird":
        raw = iter_occurrences(
            raw_http, zone.bbox, dataset_key=EBIRD_DATASET, last_interpreted=cursor,
            max_results=max_results,
        )
    else:
        raw = iter_occurrences(
            raw_http, zone.bbox, basis_of_record=DEFAULT_BASIS, last_interpreted=cursor,
            max_results=max_results,
        )

    species_ids = {} if species_ids is None else species_ids
    try:
        async for rec in raw:
            if _out_of_time(deadline):
                stats.stopped_early = True
                break
            stats.fetched += 1
            if source == "inaturalist":
                new_cursor = str(max(int(new_cursor or 0), rec["id"]))
            elif source == "gbif" and is_inaturalist_mirror(rec):
                stats.rejected["duplicate_of_inaturalist"] += 1
                continue
            obs = PARSERS[source](rec)
            if obs is None:
                stats.rejected["unparseable"] += 1
                continue
            if reason := validate(obs):
                stats.rejected[reason] += 1
                continue
            if not _in_bbox(obs, zone.bbox):
                stats.rejected["outside_zone"] += 1  # no database round trip needed to know this
                continue
            batch.append(obs)
            if len(batch) >= BATCH_SIZE:
                await _flush(conn, batch, source_id, gbif, cache, stats, species_ids)
                if source == "inaturalist" and new_cursor is not None:
                    # Records arrive in ascending id order and everything up to here is stored or
                    # refused, so a run that is cut off later resumes from here, not from the start.
                    _save_cursor(conn, source_id, scope, new_cursor)
        await _flush(conn, batch, source_id, gbif, cache, stats, species_ids)
        if source != "inaturalist":
            # The date cursor means "everything up to this day". Stopping early leaves a gap, so it
            # is not recorded; the next run starts again and skips what is already stored.
            new_cursor = None if stats.stopped_early else started
        if new_cursor is not None:
            _save_cursor(conn, source_id, scope, new_cursor)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        conn.execute(
            "update ingestion_runs set finished_at = now(), fetched = %s, skipped_dupe = %s, "
            "failed = %s, rejected = %s::jsonb, notes = %s where id = %s",
            (
                stats.fetched, stats.skipped_dupe, 1 if error else 0,
                json.dumps(dict(stats.rejected)),
                f"{scope}: stored {stats.stored}"
                + ("; stopped at the time limit" if stats.stopped_early else "")
                + (f"; FAILED {error}" if error else ""),
                run_id,
            ),
        )
    return stats


async def _amain(args: argparse.Namespace) -> int:
    settings = get_settings()
    cache_path = Path(args.cache)
    cache = load_cache(cache_path)
    rate = {"inaturalist": 1.0, "usgs_nas": 2.0}.get(args.source, 5.0)  # iNaturalist asks ~1/s
    total = IngestStats()
    deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    species_ids: dict = {}
    with psycopg.connect(settings.database_url, autocommit=True) as gate:
        room = storage(gate)
    if room.fraction >= args.stop_at:
        print(
            f"not ingesting: {room.describe()} is at or past the {args.stop_at:.0%} limit. "
            "Free-plan databases go read-only when full; see docs/free-tier-gate.md.",
            file=sys.stderr,
        )
        return 3
    try:
        async with (
            PoliteClient(user_agent=settings.user_agent, per_second=rate) as raw_http,
            PoliteClient(user_agent=settings.user_agent, per_second=10.0, max_concurrency=8) as gb,
        ):
            with psycopg.connect(settings.database_url, autocommit=True) as conn:
                for zone in load_zones(conn, args.zone):
                    if _out_of_time(deadline):
                        log.info("time limit reached; the remaining zones wait for the next run")
                        total.stopped_early = True
                        break
                    s = await ingest_zone(
                        conn, zone, source=args.source, raw_http=raw_http, gbif_http=gb,
                        cache=cache, max_results=args.max, full=args.full,
                        gbif_dataset=args.gbif_dataset, deadline=deadline, species_ids=species_ids,
                        max_stored=args.max_stored_per_zone,
                    )
                    log.info(
                        "%s: fetched %d, stored %d, duplicates %d, rejected %s",
                        zone.slug, s.fetched, s.stored, s.skipped_dupe, dict(s.rejected),
                    )
                    total.merge(s)
    finally:
        save_cache(cache_path, cache)
    print(
        f"{args.source}: fetched {total.fetched}, stored {total.stored}, "
        f"duplicates {total.skipped_dupe}, rejected {dict(total.rejected)}"
        + ("; stopped at the time limit, the next run continues" if total.stopped_early else "")
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", required=True, choices=sorted(SOURCES))
    p.add_argument("--zone", action="append", help="zone slug; repeat for several (default: all)")
    p.add_argument("--max", type=int, default=5000, help="max records per zone per run")
    p.add_argument("--full", action="store_true", help="ignore the saved cursor")
    p.add_argument("--gbif-dataset", choices=["specimens", "ebird"], default="specimens")
    p.add_argument("--cache", default=str(DEFAULT_CACHE))
    p.add_argument("--max-stored-per-zone", type=int, default=None,
                   help="skip a zone once this source has stored this many records there")
    p.add_argument("--max-minutes", type=float, default=None,
                   help="stop cleanly after this long; progress is kept and the next run continues")
    p.add_argument("--stop-at", type=float, default=STOP_AT,
                   help="refuse to ingest once the database is this full (fraction of the budget)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request is noise
    if not get_settings().database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
