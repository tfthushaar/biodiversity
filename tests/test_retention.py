"""Keeping the free-tier database from filling up and refusing to grow once it is nearly full."""

import psycopg
import pytest

from biodiv.core.settings import get_settings
from biodiv.workers import ingest, retention
from biodiv.workers.retention import Storage, prune_ingestion_runs, storage

MB = 1024 * 1024


def test_the_levels_are_ok_then_warning_then_full():
    assert Storage(100 * MB, 500 * MB).level() == "ok"
    assert Storage(400 * MB, 500 * MB).level() == "warning"  # 80%
    assert Storage(449 * MB, 500 * MB).level() == "warning"
    assert Storage(450 * MB, 500 * MB).level() == "full"  # 90%
    assert Storage(600 * MB, 500 * MB).level() == "full"
    assert Storage(1, 0).level() == "full"  # an unknown budget is never "plenty of room"
    assert "100.0 MB of 500 MB (20%)" in Storage(100 * MB, 500 * MB).describe()


def test_the_database_reports_its_size_against_the_free_tier(conn):
    state = storage(conn)
    assert state.budget_bytes == 500 * MB
    assert 0 < state.db_bytes < state.budget_bytes  # a fresh test database is small
    assert state.level() == "ok"


def _runs(conn, source_id, count, *, days_old, finished=True):
    for i in range(count):
        conn.execute(
            "insert into ingestion_runs (source_id, started_at, finished_at, notes) values "
            "(%s, now() - make_interval(days => %s), "
            "case when %s then now() - make_interval(days => %s) end, %s)",
            (source_id, days_old + i, finished, days_old + i, f"run {days_old + i}"),
        )


@pytest.fixture
def two_sources(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        ids = [
            conn.execute(
                "insert into sources (name, kind) values (%s, 'dataset') returning id", (name,)
            ).fetchone()[0]
            for name in ("retention-a", "retention-b")
        ]
        yield conn, ids
        conn.rollback()


def _count(conn, source_id):
    row = conn.execute("select count(*) from ingestion_runs where source_id = %s", (source_id,))
    return row.fetchone()[0]


def test_old_runs_beyond_the_newest_few_are_removed(two_sources):
    conn, (a, _) = two_sources
    _runs(conn, a, 8, days_old=200)  # all old
    _runs(conn, a, 3, days_old=1)  # recent
    removed = prune_ingestion_runs(conn, keep_runs=5, max_age_days=90)
    assert removed == 6  # 11 runs: the newest 5 stay (3 recent + 2 old), the other 6 go
    assert _count(conn, a) == 5


def test_recent_runs_are_kept_even_when_there_are_many(two_sources):
    conn, (a, _) = two_sources
    _runs(conn, a, 20, days_old=1)  # more than keep_runs, but none old enough to remove
    assert prune_ingestion_runs(conn, keep_runs=5, max_age_days=90) == 0
    assert _count(conn, a) == 20


def test_every_sources_latest_run_survives_whatever_its_age(two_sources):
    conn, (a, b) = two_sources
    _runs(conn, a, 1, days_old=400)  # a source not run for over a year
    _runs(conn, b, 4, days_old=400)
    prune_ingestion_runs(conn, keep_runs=1, max_age_days=90)
    assert _count(conn, a) == 1  # the Sources page still shows when it last ran
    assert _count(conn, b) == 1


def test_a_run_still_in_progress_is_never_removed(two_sources):
    conn, (a, _) = two_sources
    _runs(conn, a, 3, days_old=300, finished=False)
    _runs(conn, a, 6, days_old=300)
    prune_ingestion_runs(conn, keep_runs=1, max_age_days=90)
    unfinished = conn.execute(
        "select count(*) from ingestion_runs where source_id = %s and finished_at is null", (a,)
    ).fetchone()[0]
    assert unfinished == 3


def test_pruning_never_touches_the_data_itself(two_sources):
    conn, (a, _) = two_sources
    before = [conn.execute(f"select count(*) from {t}").fetchone()[0]
              for t in ("species", "zones", "media_items", "detections", "impact_findings")]
    _runs(conn, a, 10, days_old=300)
    prune_ingestion_runs(conn, keep_runs=1, max_age_days=1)
    after = [conn.execute(f"select count(*) from {t}").fetchone()[0]
             for t in ("species", "zones", "media_items", "detections", "impact_findings")]
    assert before == after


@pytest.mark.parametrize("keep,age", [(0, 90), (50, 0), (-1, 90)])
def test_nonsense_limits_are_refused_rather_than_deleting_everything(two_sources, keep, age):
    conn, (a, _) = two_sources
    _runs(conn, a, 3, days_old=300)
    with pytest.raises(ValueError):
        prune_ingestion_runs(conn, keep_runs=keep, max_age_days=age)
    assert _count(conn, a) == 3


def _point_at(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()


def test_the_worker_reports_and_succeeds_when_there_is_room(ingest_db_url, monkeypatch, capsys):
    _point_at(monkeypatch, ingest_db_url)
    try:
        assert retention.main([]) == 0
    finally:
        get_settings.cache_clear()
    out = capsys.readouterr().out
    assert "removed 0 old ingestion runs" in out and "of 500 MB" in out


def test_the_worker_fails_loudly_when_the_database_is_too_full(ingest_db_url, monkeypatch, capsys):
    _point_at(monkeypatch, ingest_db_url)
    try:
        assert retention.main(["--stop-at", "0.000001"]) == 3
    finally:
        get_settings.cache_clear()
    assert "::error::" in capsys.readouterr().out


def test_ingestion_refuses_to_grow_a_nearly_full_database(ingest_db_url, monkeypatch, capsys):
    """No network is mocked: if the guard failed, the run would try to reach iNaturalist."""
    _point_at(monkeypatch, ingest_db_url)
    try:
        assert ingest.main(["--source", "inaturalist", "--stop-at", "0.000001"]) == 3
    finally:
        get_settings.cache_clear()
    assert "not ingesting" in capsys.readouterr().err
    with psycopg.connect(ingest_db_url) as conn:
        assert conn.execute("select count(*) from ingestion_runs").fetchone()[0] == 0
