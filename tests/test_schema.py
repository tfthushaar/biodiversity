from datetime import UTC, datetime

import psycopg
import pytest

from biodiv.workers.migrate import MigrationDriftError, migrate


def _one(conn, sql, params=None):
    return conn.execute(sql, params).fetchone()[0]


def _seed_source(conn) -> int:
    return _one(
        conn,
        "insert into sources (name, kind) values ('test', 'dataset') returning id",
    )


def _zone_id(conn, slug: str) -> int:
    return _one(conn, "select id from zones where slug = %s", (slug,))


def _species(conn, name: str, *, country: str | None = None, invasive: bool | None = None) -> int:
    sid = _one(
        conn,
        "insert into species (scientific_name) values (%s) returning id",
        (name,),
    )
    if country is not None:
        conn.execute(
            "insert into invasive_status (species_id, country, is_invasive) values (%s, %s, %s)",
            (sid, country, invasive),
        )
    return sid


def _media(conn, source_id, zone_id, when, n=1, prefix="m") -> list[int]:
    ids = []
    for i in range(n):
        ids.append(
            _one(
                conn,
                "insert into media_items (source_id, external_id, uri, captured_at, zone_id) "
                "values (%s, %s, 'http://x', %s, %s) returning id",
                (source_id, f"{prefix}{i}", when, zone_id),
            )
        )
    return ids


def _detect(conn, media_id, species_id, when, confidence=0.9, zone_id=None):
    conn.execute(
        "insert into detections (media_item_id, captured_at, species_id, confidence, zone_id) "
        "values (%s, %s, %s, %s, %s)",
        (media_id, when, species_id, confidence, zone_id),
    )


# ---------------------------------------------------------------- migrations


def test_migrations_are_idempotent(db_url):
    assert migrate(db_url) == []


def test_edited_migration_is_rejected(empty_db_url, tmp_path):
    (tmp_path / "0001_a.sql").write_text("create table t (id int);")
    assert migrate(empty_db_url, migrations_dir=tmp_path) == ["0001_a"]
    (tmp_path / "0001_a.sql").write_text("create table t (id int, extra int);")
    with pytest.raises(MigrationDriftError):
        migrate(empty_db_url, migrations_dir=tmp_path)


# --------------------------------------------------------------------- zones


def test_zones_are_valid_real_sized_polygons(conn):
    rows = conn.execute(
        "select slug, st_isvalid(geom), st_area(geom::geography) / 1e6 from zones order by slug"
    ).fetchall()
    assert [r[0] for r in rows] == ["bandipur", "mudumalai", "nagarahole", "serengeti"]
    for slug, valid, km2 in rows:
        assert valid, slug
        assert km2 > 100, f"{slug} is only {km2:.1f} km2, looks degenerate"


def test_point_in_reserve_query(conn):
    """The query the design report cites as the reason for PostGIS."""
    inside = "st_setsrid(st_makepoint(%s, %s), 4326)"
    q = f"select slug from zones where st_within({inside}, geom)"
    assert _one(conn, q, (76.63, 11.67)) == "bandipur"
    assert conn.execute(q, (0.0, 0.0)).fetchone() is None  # open ocean


# --------------------------------------------------------------- detections


def test_detections_route_to_yearly_partitions(conn):
    src = _seed_source(conn)
    (m,) = _media(conn, src, None, datetime(2011, 6, 1, tzinfo=UTC))
    sp = _species(conn, "Panthera pardus")
    _detect(conn, m, sp, datetime(2011, 6, 1, tzinfo=UTC))
    _detect(conn, m, sp, datetime(1985, 1, 1, tzinfo=UTC))

    where = dict(
        conn.execute(
            "select captured_at::date::text, tableoid::regclass::text from detections"
        ).fetchall()
    )
    assert where["2011-06-01"] == "detections_2011"
    assert where["1985-01-01"] == "detections_default"  # outside every yearly partition


def test_ensure_detection_partition_creates_and_is_idempotent(conn):
    assert _one(conn, "select ensure_detection_partition(2045)") == "detections_2045"
    assert _one(conn, "select ensure_detection_partition(2045)") == "detections_2045"
    src = _seed_source(conn)
    (m,) = _media(conn, src, None, datetime(2045, 3, 1, tzinfo=UTC))
    _detect(conn, m, _species(conn, "Lantana camara"), datetime(2045, 3, 1, tzinfo=UTC))
    assert _one(conn, "select tableoid::regclass::text from detections") == "detections_2045"


def test_duplicate_media_is_rejected(conn):
    src = _seed_source(conn)
    _media(conn, src, None, None, n=1, prefix="dup")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _media(conn, src, None, None, n=1, prefix="dup")


def test_confidence_must_be_a_probability(conn):
    src = _seed_source(conn)
    (m,) = _media(conn, src, None, datetime(2012, 1, 1, tzinfo=UTC))
    sp = _species(conn, "Senna spectabilis")
    with pytest.raises(psycopg.errors.CheckViolation):
        _detect(conn, m, sp, datetime(2012, 1, 1, tzinfo=UTC), confidence=1.5)


# -------------------------------------------------------------- mitigation


def test_mitigation_playbook_requires_a_citation(conn):
    sp = _species(conn, "Lantana camara")
    insert = (
        "insert into mitigation_playbooks (species_id, method, description, citation_text) "
        "values (%s, 'mechanical', 'uproot', %s)"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(insert, (sp, "   "))
    conn.rollback()


# ---------------------------------------------------------------- rollups


def test_invasion_index_is_normalised_by_effort(conn):
    """2 invasive sightings out of 10 images = 0.2, however many cameras there are."""
    src = _seed_source(conn)
    zone = _zone_id(conn, "bandipur")
    when = datetime(2012, 3, 10, tzinfo=UTC)

    lantana = _species(conn, "Lantana camara", country="IN", invasive=True)
    chital = _species(conn, "Axis axis")  # native: no invasive_status row
    tame = _species(conn, "Introduced but harmless", country="IN", invasive=False)

    media = _media(conn, src, zone, when, n=10)
    _detect(conn, media[0], lantana, when, zone_id=zone)
    _detect(conn, media[1], lantana, when, zone_id=zone)
    _detect(conn, media[2], chital, when, zone_id=zone)
    _detect(conn, media[3], tame, when, zone_id=zone)

    conn.execute("select refresh_rollups()")

    cols = "species_id, detections, effort, normalised_index"
    inv = conn.execute(f"select {cols} from invasion_index_monthly").fetchall()
    assert inv == [(lantana, 2, 10, pytest.approx(0.2))]

    nat = conn.execute(f"select {cols} from native_trend_monthly").fetchall()
    assert nat == [(chital, 1, 10, pytest.approx(0.1))]  # introduced species: in neither


# ------------------------------------------------------------ access control


def test_public_key_can_read_but_not_write(conn):
    conn.execute("set local role anon")

    assert _one(conn, "select count(*) from zones") == 4
    assert _one(conn, "select count(*) from detections") == 0  # parent: readable

    for sql in (
        "insert into zones (slug, name, country, geom) values ('x', 'x', 'IN', "
        "st_multi(st_geomfromtext('POLYGON((0 0,1 0,1 1,0 0))', 4326)))",
        "delete from zones",
        "select refresh_rollups()",
        "select ensure_detection_partition(2099)",
        "select count(*) from detections_2011",  # partitions are not directly exposed
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(sql)
        conn.rollback()
        conn.execute("set local role anon")
