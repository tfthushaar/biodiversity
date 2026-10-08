"""Apply db/migrations/*.sql in order, each once, then optionally the idempotent seeds.

    python -m biodiv.workers.migrate [--seed]

Reads DATABASE_URL. On Supabase use the pooler connection string: the direct host is
IPv6-only on the free plan, which GitHub-hosted runners may not reach.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import psycopg

from biodiv.core.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
SEEDS_DIR = REPO_ROOT / "db" / "seeds"

_TRACKING_DDL = """
create table if not exists schema_migrations (
  version    text primary key,
  checksum   text not null,
  applied_at timestamptz not null default now()
)
"""


class MigrationDriftError(RuntimeError):
    """An already-applied migration file was edited. Add a new migration instead."""


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _give_postgis_its_own_schema(conn: psycopg.Connection) -> None:
    """On Supabase, install PostGIS into the `extensions` schema before migration 0001 does.

    Supabase keeps extension objects in `extensions` and owns them there. Installed into `public`
    instead, the tables PostGIS adds (spatial_ref_sys) belong to a Supabase-internal role that the
    `postgres` user cannot alter, and the REST API would publish about a thousand PostGIS functions.
    In `extensions` none of that is exposed. Plain Postgres has no such schema, so this does nothing
    there and PostGIS goes into `public` as before (migrations 0013 and 0014 lock that case down).
    """
    on_supabase = conn.execute(
        "select exists (select from pg_namespace where nspname = 'extensions')"
    ).fetchone()[0]
    if on_supabase:
        conn.execute("create extension if not exists postgis with schema extensions")


def migrate(
    database_url: str,
    *,
    seed: bool = False,
    migrations_dir: Path = MIGRATIONS_DIR,
    seeds_dir: Path = SEEDS_DIR,
) -> list[str]:
    """Apply pending migrations. Returns the versions applied by this call."""
    applied_now: list[str] = []
    with psycopg.connect(database_url) as conn:
        conn.execute(_TRACKING_DDL)
        conn.commit()
        _give_postgis_its_own_schema(conn)
        done = dict(conn.execute("select version, checksum from schema_migrations").fetchall())

        for path in sorted(migrations_dir.glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            digest = _checksum(sql)
            if path.stem in done:
                if done[path.stem] != digest:
                    raise MigrationDriftError(
                        f"{path.name} changed after it was applied; write a new migration"
                    )
                continue
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "insert into schema_migrations (version, checksum) values (%s, %s)",
                    (path.stem, digest),
                )
            applied_now.append(path.stem)

        if seed:
            for path in sorted(seeds_dir.glob("*.sql")):
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
    return applied_now


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", action="store_true", help="also apply db/seeds/*.sql")
    args = parser.parse_args(argv)

    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    applied = migrate(url, seed=args.seed)
    print(f"applied {len(applied)} migration(s): {', '.join(applied) or 'none (up to date)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
