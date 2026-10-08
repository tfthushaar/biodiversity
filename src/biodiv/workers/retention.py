"""Keep the database inside the free tier, and say so when it is getting full.

    python -m biodiv.workers.retention [--keep-runs 50] [--max-age-days 90] [--stop-at 0.9]

What grows without bound is bookkeeping, not data: one row per ingestion run, forever. This
removes old ones, always keeping each source's most recent runs (the Sources page reads them),
and then reports how full the database is.

It never deletes observations, detections or findings. Those are the product; if they ever
fill the budget the right answer is a human decision (narrower zones, or a paid plan), not a
cron job quietly discarding records. The exit code carries that message: 3 when the database is
at or past the stop threshold, so a scheduled run shows red and someone looks.

The thumbnails the original plan budgeted for were never built: only detection boxes and source
URLs are stored, never images.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

import psycopg

from biodiv.core.settings import get_settings

log = logging.getLogger(__name__)

WARN_AT = 0.8
STOP_AT = 0.9


@dataclass(frozen=True)
class Storage:
    db_bytes: int
    budget_bytes: int

    @property
    def fraction(self) -> float:
        return self.db_bytes / self.budget_bytes if self.budget_bytes else 1.0

    def level(self, warn_at: float = WARN_AT, stop_at: float = STOP_AT) -> str:
        if self.fraction >= stop_at:
            return "full"
        return "warning" if self.fraction >= warn_at else "ok"

    def describe(self) -> str:
        mb = 1024 * 1024
        return (
            f"database {self.db_bytes / mb:.1f} MB of {self.budget_bytes / mb:.0f} MB "
            f"({self.fraction:.0%})"
        )


def storage(conn: psycopg.Connection) -> Storage:
    row = conn.execute("select storage_status()").fetchone()[0]
    return Storage(db_bytes=int(row["db_bytes"]), budget_bytes=int(row["budget_bytes"]))


def prune_ingestion_runs(
    conn: psycopg.Connection, *, keep_runs: int = 50, max_age_days: int = 90
) -> int:
    """Delete finished runs that are both old and beyond the newest `keep_runs` of their source.

    Unfinished runs are left alone (one may be running right now), and so is the newest finished
    run of every source whatever its age: the Sources page shows it.
    """
    if keep_runs < 1 or max_age_days < 1:
        raise ValueError("keep_runs and max_age_days must be at least 1")
    return conn.execute(
        """
        with ranked as (
          select id, finished_at,
                 row_number() over (partition by source_id order by finished_at desc, id desc) as rn
          from ingestion_runs
          where finished_at is not null
        )
        delete from ingestion_runs
        where id in (
          select id from ranked
          where rn > %s and finished_at < now() - make_interval(days => %s)
        )
        """,
        (keep_runs, max_age_days),
    ).rowcount


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--keep-runs", type=int, default=50, help="newest runs kept per source")
    p.add_argument("--max-age-days", type=int, default=90)
    p.add_argument("--warn-at", type=float, default=WARN_AT)
    p.add_argument("--stop-at", type=float, default=STOP_AT)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        removed = prune_ingestion_runs(
            conn, keep_runs=args.keep_runs, max_age_days=args.max_age_days
        )
        state = storage(conn)
    level = state.level(args.warn_at, args.stop_at)
    print(f"removed {removed} old ingestion runs; {state.describe()}")
    if level == "warning":
        print("::warning::the free database is getting full; see docs/free-tier-gate.md")
    elif level == "full":
        print(
            "::error::the free database is full enough that ingestion has stopped; "
            "see docs/free-tier-gate.md"
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
