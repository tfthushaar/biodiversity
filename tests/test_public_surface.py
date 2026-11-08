"""What an anonymous visitor to the public REST API can and cannot do, checked at the database.

Supabase serves the dashboard's data through a generated REST API using the public 'anon' role,
so whatever that role can do in Postgres is what the whole internet can do.
"""

import json

import psycopg
import pytest

from biodiv.analytics.impact import zone_report


@pytest.fixture
def anon(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        conn.execute("set local role anon")
        yield conn
        conn.rollback()


@pytest.mark.parametrize(
    "sql",
    [
        "select postgis_full_version()",  # leaks server library versions
        "select st_buffer(geom, 1) from zones",  # heavy geometry work on attacker input
        "select st_union(geom) from zones",
        "select st_astext(geom) from zones",
        "select refresh_rollups()",
        "select ensure_detection_partition(2099)",
        "select restrict_postgis_functions()",
        "select count(*) from detections_2011",  # partitions are not directly exposed
        "select count(*) from ingestion_cursors",
        "select count(*) from schema_migrations",
    ],
)
def test_anonymous_visitors_cannot_reach_these(anon, sql):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        anon.execute(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "insert into species (scientific_name) values ('x')",
        "update zones set name = 'x'",
        "delete from alerts",
        "insert into zone_reports (zone_id, report) values (1, '{}')",
        "delete from mitigation_playbooks",
        "truncate detections",
    ],
)
def test_anonymous_visitors_cannot_write(anon, sql):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        anon.execute(sql)


def test_geometry_columns_can_be_read_as_json_by_the_public(anon):
    """Regression: locking down spatial_ref_sys once broke every public read of a geometry
    column, because PostGIS looks up the coordinate system whenever it serialises one."""
    row = anon.execute("select row_to_json(z) from (select slug, geom from zones limit 1) z"
                       ).fetchone()[0]
    assert row["slug"] and row["geom"]
    anon.execute("select to_jsonb(m) from media_items m limit 1").fetchall()


def test_the_public_sees_only_the_wgs84_definition(anon):
    assert [r[0] for r in anon.execute("select srid from spatial_ref_sys")] == [4326]


def test_the_dashboards_own_data_is_readable(anon):
    assert anon.execute("select count(*) from zones").fetchone()[0] == 6
    for table in ("species", "invasive_status", "alerts", "mitigation_playbooks",
                  "impact_findings", "zone_reports", "source_health", "invasive_records",
                  "zone_invasive_summary", "researched_species",
                  "model_versions", "sources", "ingestion_runs"):
        anon.execute(f"select * from {table} limit 1").fetchall()


def test_the_geojson_functions_work_for_the_public_role(anon):
    zones = anon.execute("select zones_geojson()").fetchone()[0]
    assert zones["type"] == "FeatureCollection" and len(zones["features"]) == 6
    slugs = {f["properties"]["slug"] for f in zones["features"]}
    assert slugs == {"bandipur", "nagarahole", "mudumalai", "serengeti", "everglades", "smokies"}
    assert zones["features"][0]["geometry"]["type"] in ("MultiPolygon", "Polygon")


def test_the_public_can_see_how_full_the_database_is(anon):
    status = anon.execute("select storage_status()").fetchone()[0]
    assert set(status) == {"db_bytes", "budget_bytes"}  # two numbers and nothing else
    assert status["budget_bytes"] == 500 * 1024 * 1024 and status["db_bytes"] > 0


def test_no_table_holds_data_the_platform_may_not_republish(anon):
    """IUCN's terms forbid redistributing Red List data, so none is stored (migration 0021)."""
    assert anon.execute("select to_regclass('public.threat_links')").fetchone()[0] is None
    cols = {r[0] for r in anon.execute(
        "select column_name from information_schema.columns where table_name = 'species'")}
    assert "iucn_category" not in cols


def test_the_public_sees_only_species_a_paper_backs(ingest_db_url):
    """No paper, no species: the API names a species, and its invasive status, only for those a
    verified paper backs (migration 0024)."""
    from helpers import World

    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn)
        w.species("Lantana camara", invasive=True)  # has a paper
        w.species("Senna spectabilis", invasive=True, paper=False)  # GRIIS lists it, no paper
        w.species("Axis axis")  # a native
        conn.commit()
        assert conn.execute("select count(*) from species").fetchone()[0] == 3  # the owner sees all
        conn.execute("set local role anon")
        assert [r[0] for r in conn.execute("select scientific_name from species")] == [
            "Lantana camara"]
        assert conn.execute("select count(*) from invasive_status").fetchone()[0] == 1
        assert [r[0] for r in conn.execute("select species_id from researched_species")] == [
            w.species_ids["Lantana camara"]]


def test_a_species_without_a_paper_is_not_an_invasive_record(ingest_db_url):
    from helpers import World, day

    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn)
        w.species("Lantana camara", invasive=True)
        w.species("Senna spectabilis", invasive=True, paper=False)
        w.observe("Lantana camara", day(2020))
        w.observe("Senna spectabilis", day(2020))
        conn.commit()
        names = [r[0] for r in conn.execute(
            "select s.scientific_name from invasive_records r "
            "join species s on s.id = r.species_id")]
    assert names == ["Lantana camara"]


def test_the_rollups_and_the_individual_records_function_are_not_public(anon):
    for sql in ("select * from invasion_index_monthly", "select * from native_trend_monthly"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            anon.execute(sql)
        anon.rollback()  # a refused statement aborts the transaction
        anon.execute("set local role anon")
    assert anon.execute("select to_regprocedure('records_geojson(text,text,integer)')"
                        ).fetchone()[0] is None


def test_restricting_postgis_is_repeatable_and_does_not_break_the_public_functions(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        first = conn.execute("select restrict_postgis_functions()").fetchone()[0]
        second = conn.execute("select restrict_postgis_functions()").fetchone()[0]
        assert first == second > 100  # touches the whole PostGIS function set each time
        conn.execute("set local role anon")
        assert conn.execute("select zones_geojson()").fetchone()[0]["features"]
        # Only the four allowlisted functions (and our own) remain callable.
        callable_names = {r[0] for r in conn.execute(
            "select distinct p.proname from pg_proc p join pg_depend d on d.objid = p.oid "
            "and d.deptype = 'e' join pg_extension e on e.oid = d.refobjid "
            "and e.extname = 'postgis' where p.pronamespace = 'public'::regnamespace "
            "and has_function_privilege('anon', p.oid, 'execute')")}
        assert callable_names == {"st_asgeojson", "st_simplify", "st_x", "st_y"}


def test_a_stored_zone_report_is_what_the_dashboard_would_read(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        report = zone_report(conn, "bandipur")
        conn.execute("insert into zone_reports (zone_id, report) select id, %s::jsonb "
                     "from zones where slug = 'bandipur'", (json.dumps(report, default=str),))
        conn.commit()
        conn.execute("set local role anon")
        got = conn.execute("select report from zone_reports").fetchone()[0]
    assert got["layers"]["cooccurrence"]["status"] == "insufficient"
    assert got["layers"]["trend"]["needs"]
