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
        "select * from spatial_ref_sys",
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


def test_the_dashboards_own_data_is_readable(anon):
    assert anon.execute("select count(*) from zones").fetchone()[0] == 4
    for table in ("species", "invasive_status", "alerts", "mitigation_playbooks",
                  "impact_findings", "zone_reports", "source_health", "invasive_records",
                  "zone_invasive_summary", "invasion_index_monthly", "native_trend_monthly",
                  "model_versions", "sources", "ingestion_runs"):
        anon.execute(f"select * from {table} limit 1").fetchall()


def test_the_geojson_functions_work_for_the_public_role(anon):
    zones = anon.execute("select zones_geojson()").fetchone()[0]
    assert zones["type"] == "FeatureCollection" and len(zones["features"]) == 4
    slugs = {f["properties"]["slug"] for f in zones["features"]}
    assert slugs == {"bandipur", "nagarahole", "mudumalai", "serengeti"}
    assert zones["features"][0]["geometry"]["type"] in ("MultiPolygon", "Polygon")
    points = anon.execute("select records_geojson('bandipur', 'invasive', 10)").fetchone()[0]
    assert points == {"type": "FeatureCollection", "features": []}  # none yet, but valid


def test_the_point_query_is_capped_whatever_the_caller_asks_for(ingest_db_url):
    from helpers import World, day

    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn)
        w.species("Lantana camara", invasive=True)
        for i in range(12):
            w.observe("Lantana camara", day(2020, 1 + i % 12), 76.5 + i * 0.001, 11.7)
        conn.commit()
        conn.execute("set local role anon")
        for asked, expected in ((5, 5), (0, 1), (-3, 1), (10**9, 12)):
            fc = conn.execute("select records_geojson('bandipur', 'invasive', %s)",
                              (asked,)).fetchone()[0]
            assert len(fc["features"]) == expected
        feature = fc["features"][0]
        assert feature["properties"]["class"] == "invasive"
        assert feature["geometry"]["type"] == "Point"


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
