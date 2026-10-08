"""The schema on a host whose defaults differ from plain Postgres, which Supabase's do.

Both of these were found by running the migrations against a real Supabase project, which plain
Postgres cannot reproduce on its own, so each difference is imitated here.
"""

import psycopg
from psycopg.conninfo import conninfo_to_dict

from biodiv.workers.migrate import migrate

ROLES = """
do $$ begin
  if not exists (select from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end $$
"""


def test_nothing_is_public_by_default_even_when_the_host_grants_everything(empty_db_url):
    """Supabase hands every new table, sequence and function to the public roles. Our schema must
    still leave them read-only, and keep tables made later private."""
    with psycopg.connect(empty_db_url, autocommit=True) as conn:
        conn.execute(ROLES)
        for kind in ("tables", "sequences"):
            conn.execute(
                f"alter default privileges in schema public grant all on {kind} "
                "to anon, authenticated, service_role"
            )
        conn.execute(
            "alter default privileges in schema public grant execute on functions "
            "to anon, authenticated, service_role"
        )
    migrate(empty_db_url, seed=True)

    with psycopg.connect(empty_db_url) as conn:
        writable = conn.execute(
            """
            select c.relname, p from pg_class c
            cross join unnest(array['insert', 'update', 'delete', 'truncate']) p
            where c.relnamespace = 'public'::regnamespace and c.relkind in ('r', 'p', 'v', 'm')
              and (has_table_privilege('anon', c.oid, p)
                   or has_table_privilege('authenticated', c.oid, p))
            """
        ).fetchall()
        assert writable == []

        assert not conn.execute(
            "select has_table_privilege('anon', 'schema_migrations', 'select')"
        ).fetchone()[0]
        sequences = conn.execute(
            """
            select relname from pg_class
            where relnamespace = 'public'::regnamespace and relkind = 'S'
              and (has_sequence_privilege('anon', oid, 'usage')
                   or has_sequence_privilege('anon', oid, 'update'))
            """
        ).fetchall()
        assert sequences == []

        conn.execute("create table made_later (id int)")
        assert not conn.execute(
            "select has_table_privilege('anon', 'made_later', 'select')"
        ).fetchone()[0]

        # What the dashboard needs is still there.
        conn.execute("set local role anon")
        assert conn.execute("select count(*) from zones").fetchone()[0] == 4
        assert conn.execute("select zones_geojson()").fetchone()[0]["features"]


def test_postgis_goes_into_the_extensions_schema_when_the_host_has_one(empty_db_url):
    """On Supabase PostGIS belongs in `extensions`: its tables are owned by a role we cannot
    alter, and the REST API does not publish that schema."""
    name = conninfo_to_dict(empty_db_url)["dbname"]
    with psycopg.connect(empty_db_url, autocommit=True) as conn:
        conn.execute("create schema extensions")
        conn.execute(f'alter database "{name}" set search_path to "$user", public, extensions')

    migrate(empty_db_url, seed=True)  # must not fail on the table-level steps of 0013 and 0014

    with psycopg.connect(empty_db_url) as conn:
        home = conn.execute(
            "select n.nspname from pg_extension e join pg_namespace n on n.oid = e.extnamespace "
            "where e.extname = 'postgis'"
        ).fetchone()[0]
        assert home == "extensions"
        assert conn.execute("select to_regclass('public.spatial_ref_sys')").fetchone()[0] is None
        assert conn.execute("select zones_geojson()").fetchone()[0]["features"]
