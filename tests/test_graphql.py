from datetime import UTC, datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from biodiv.api.deps import get_conn
from biodiv.api.main import app
from biodiv.knowledge.loader import load_knowledge
from helpers import World, day


@pytest.fixture
def gql(ingest_db_url):
    """A client wired to a database holding a small, known world."""
    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn)
        w.species("Panthera pardus")
        conn.execute("update species set common_name = 'Leopard' where scientific_name = "
                     "'Panthera pardus'")
        w.species("Lantana camara", invasive=True)
        conn.execute("update species set common_name = 'common lantana' where scientific_name = "
                     "'Lantana camara'")
        w.species("Axis axis")
        w.observe("Panthera pardus", day(2026, 8, 1), 76.6, 11.7)
        w.observe("Panthera pardus", day(2026, 8, 20), 76.6, 11.7)
        w.observe("Panthera pardus", day(2024, 2, 1), 76.6, 11.7)
        w.observe("Lantana camara", day(2026, 8, 5), 76.6, 11.7)
        w.observe("Axis axis", day(2026, 8, 6), 76.6, 11.7)
        # give two leopard sightings different confidences
        conn.execute("update detections d set confidence = 0.95 from species s "
                     "where s.id = d.species_id and s.scientific_name = 'Panthera pardus' "
                     "and d.captured_at >= '2026-08-10'")
        conn.execute("update detections d set confidence = 0.60 from species s "
                     "where s.id = d.species_id and s.scientific_name = 'Panthera pardus' "
                     "and d.captured_at < '2026-08-10' and d.captured_at > '2026-01-01'")
        conn.commit()

    def conn_dep():
        with psycopg.connect(ingest_db_url) as c:
            yield c

    app.dependency_overrides[get_conn] = conn_dep
    yield lambda query, **vars: TestClient(app).post(
        "/graphql", json={"query": query, "variables": vars}).json()
    app.dependency_overrides.clear()


def test_the_design_reports_own_example_query(gql):
    """'All leopard sightings this quarter with confidence > 0.9'."""
    out = gql("""query { detections(species: "Panthera pardus", since: "2026-07-01T00:00:00Z",
                                    minConfidence: 0.9) { capturedAt confidence zone species } }""")
    rows = out["data"]["detections"]
    assert len(rows) == 1  # the other two are too old or too unsure
    assert rows[0]["species"] == "Panthera pardus" and rows[0]["confidence"] == pytest.approx(0.95)
    assert rows[0]["zone"] == "bandipur"


def test_species_can_be_matched_by_common_name_in_any_case(gql):
    out = gql('{ detections(species: "LEOPARD") { species } }')
    assert {r["species"] for r in out["data"]["detections"]} == {"Panthera pardus"}


def test_invasive_only_filter(gql):
    out = gql("{ detections(invasiveOnly: true) { species invasive } }")
    assert out["data"]["detections"] == [{"species": "Lantana camara", "invasive": True}]


def test_time_window_is_half_open(gql):
    out = gql('{ detections(since: "2026-08-01T00:00:00Z", until: "2026-08-06T00:00:00Z") '
              '{ species } }')
    got = {r["species"] for r in out["data"]["detections"]}
    assert got == {"Panthera pardus", "Lantana camara"}


def test_filters_combine_and_an_empty_result_is_not_an_error(gql):
    out = gql('{ detections(species: "Panthera pardus", zone: "serengeti") { id } }')
    assert out["data"]["detections"] == [] and "errors" not in out


def test_results_are_capped(gql):
    out = gql("{ detections(limit: 100000) { id } }")
    assert len(out["data"]["detections"]) <= 500


def test_filter_values_cannot_inject_sql(gql):
    nasty = "'; drop table detections; --"
    out = gql("query($s: String) { detections(species: $s) { id } }", s=nasty)
    assert out["data"]["detections"] == []
    assert len(gql("{ detections { id } }")["data"]["detections"]) == 5  # the table is intact


def test_zones_and_species_queries(gql):
    zones = gql("{ zones { slug observations invasiveRecords } }")["data"]["zones"]
    bandipur = next(z for z in zones if z["slug"] == "bandipur")
    assert bandipur["observations"] == 5 and bandipur["invasiveRecords"] == 1
    sp = gql('{ species(search: "lantana") { scientificName invasiveInIndia } }')["data"]["species"]
    assert sp == [{"scientificName": "Lantana camara", "invasiveInIndia": True}]


def test_playbooks_expose_their_evidence(gql, ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        load_knowledge(conn, {
            "verified_on": "2026-10-07",
            "sources": {"s": {"citation": "A. Author (2020)", "url": "https://x.org/s",
                              "kind": "page"}},
            "playbooks": [{"species": "Lantana camara", "method": "mechanical",
                           "summary": "Pull it up.", "effectiveness": "low",
                           "evidence_strength": "low", "cost_tier": None, "risks": None,
                           "failure_cases": None, "region_note": "Somewhere.", "source": "s",
                           "quotes": ["Hand pulling is suitable for small infestations only."]}],
            "impact_findings": []})
    out = gql('{ playbooks(species: "Lantana camara") { method quotes citation regionNote '
              'verifiedOn evidenceStrength } }')
    (row,) = out["data"]["playbooks"]
    assert row["quotes"] == ["Hand pulling is suitable for small infestations only."]
    assert row["citation"] == "A. Author (2020)" and row["verifiedOn"] == "2026-10-07"


def test_alerts_query(gql, ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        conn.execute(
            "insert into alerts (kind, severity, zone_id, species_id, evidence) "
            "select 'edrr', 'medium', z.id, s.id, '{\"caveat\": \"first in our sources\"}' "
            "from zones z, species s where z.slug = 'bandipur' and s.scientific_name = "
            "'Lantana camara'")
        conn.commit()
    out = gql('{ alerts(zone: "bandipur", kind: "edrr") { severity species caveat } }')
    assert out["data"]["alerts"] == [
        {"severity": "medium", "species": "Lantana camara", "caveat": "first in our sources"}]


def test_a_malformed_query_is_a_graphql_error_not_a_server_error(gql):
    out = gql("{ detections(nonsense: 1) { id } }")
    assert out["errors"]  # reported to the caller as a GraphQL error


def test_timestamps_survive_round_trip(gql):
    (row,) = gql('{ detections(species: "Axis axis") { capturedAt } }')["data"]["detections"]
    assert datetime.fromisoformat(row["capturedAt"]) == datetime(2026, 8, 6, tzinfo=UTC)
