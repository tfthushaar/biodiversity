"""USGS Nonindigenous Aquatic Species connector.

The fixture's first record is a real NAS record (a U.S. Government work); the rest are variants of
it that change one field each, so every rejection rule is exercised on realistic data.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
import pytest

from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.observations import validate
from biodiv.ingestion.usgs_nas import (
    NAS_API,
    NAS_LICENSE,
    ZONE_COUNTIES,
    iter_occurrences,
    parse_occurrence,
)
from biodiv.workers.ingest import ingest_zone, load_zones
from helpers import exact, mock_gbif

DATA = json.loads((Path(__file__).parent / "fixtures" / "nas_occurrences.json").read_text("utf-8"))
RECORDS = {label: next(r for r in DATA["results"] if r["key"] == key)
           for label, key in DATA["labels"].items()}


def client():
    return PoliteClient(user_agent="t", per_second=1000, backoff=0, retries=1)


# ------------------------------------------------------------------------------------ parsing


def test_a_normal_record_is_mapped_and_valid():
    obs = parse_occurrence(RECORDS["established_python"])
    assert obs.source == "usgs_nas" and obs.external_id == "164538"
    assert obs.taxon_name == "Python bivittatus" and obs.rank == "species"
    assert obs.kingdom == "Animalia" and obs.common_name == "Burmese Python"
    assert (obs.lat, obs.lon) == (25.387147, -80.59433)
    assert obs.captured_at == datetime(2005, 6, 25, tzinfo=UTC)
    assert obs.record_url.endswith("SpecimenID=164538")
    assert obs.record_license == NAS_LICENSE
    assert validate(obs) is None


@pytest.mark.parametrize("label,reason", [
    ("failed", "not_established"),
    ("approximate", "imprecise_location"),
    ("centroid", "imprecise_location"),
    ("year_only", "no_date"),
])
def test_records_that_cannot_support_analysis_are_refused_for_a_stated_reason(label, reason):
    assert validate(parse_occurrence(RECORDS[label])) == reason


def test_a_record_without_coordinates_is_unparseable():
    assert parse_occurrence({**RECORDS["established_python"], "decimalLatitude": None}) is None
    assert parse_occurrence({**RECORDS["established_python"], "decimalLongitude": ""}) is None
    assert parse_occurrence({"decimalLatitude": 1, "decimalLongitude": 1}) is None  # no key


def test_plants_are_placed_in_the_plant_kingdom():
    plant = {**RECORDS["established_python"], "group": "Plants", "genus": "Eichhornia",
             "species": "crassipes", "scientificName": "Eichhornia crassipes"}
    assert parse_occurrence(plant).kingdom == "Plantae"


# ------------------------------------------------------------------------------------- paging


async def test_paging_walks_each_county_and_reads_the_string_end_marker(respx_mock):
    rec = RECORDS["established_python"]
    calls = []

    def handler(request):
        p = dict(request.url.params)
        calls.append(p)
        if p["county"] == "Miami-Dade" and p["offset"] == "0":
            return httpx.Response(200, json={"endOfRecords": "false", "results": [rec, rec]})
        if p["county"] == "Miami-Dade":
            return httpx.Response(200, json={"endOfRecords": "true", "results": [rec]})
        return httpx.Response(200, json={"endOfRecords": "true", "results": []})

    respx_mock.get(NAS_API).mock(side_effect=handler)
    async with client() as http:
        got = [r async for r in iter_occurrences(
            http, [("FL", "Miami-Dade"), ("FL", "Monroe")], page_size=2)]
    assert len(got) == 3
    assert [(c["county"], c["offset"]) for c in calls] == [
        ("Miami-Dade", "0"), ("Miami-Dade", "2"), ("Monroe", "0")]


async def test_the_cap_on_records_is_respected(respx_mock):
    rec = RECORDS["established_python"]
    respx_mock.get(NAS_API).mock(return_value=httpx.Response(
        200, json={"endOfRecords": "false", "results": [rec] * 5}))
    async with client() as http:
        got = [r async for r in iter_occurrences(http, [("FL", "Monroe")], max_results=7,
                                                 page_size=5)]
    assert len(got) == 7


# --------------------------------------------------------------------------- the whole pipeline


def q(url, sql, params=None):
    with psycopg.connect(url) as conn:
        return conn.execute(sql, params).fetchall()


async def run_zone(url, slug, **kw):
    with psycopg.connect(url, autocommit=True) as conn:
        zone = load_zones(conn, [slug])[0]
        async with client() as raw, client() as gb:
            return await ingest_zone(conn, zone, source="usgs_nas", raw_http=raw, gbif_http=gb,
                                     cache={}, **kw)


async def test_nas_records_flow_through_to_the_database(ingest_db_url, respx_mock):
    url = ingest_db_url
    inside = q(url, "select st_within(st_setsrid(st_makepoint(-80.59433, 25.387147), 4326), geom) "
                    "from zones where slug = 'everglades'")
    assert inside == [(True,)], "test premise: the real record lies inside the Everglades polygon"

    mock_gbif(respx_mock, {"Python bivittatus": exact(1234567, "Python bivittatus",
                                                      kingdom="Animalia")})
    respx_mock.get(NAS_API).mock(side_effect=lambda request: httpx.Response(
        200, json={"endOfRecords": "true",
                   "results": DATA["results"] if request.url.params["county"] == "Miami-Dade"
                   else []}))

    stats = await run_zone(url, "everglades")
    assert (stats.fetched, stats.stored) == (6, 1)
    assert dict(stats.rejected) == {"not_established": 1, "imprecise_location": 2, "no_date": 1,
                                    "outside_zone": 1}

    assert q(url, "select s.scientific_name, d.captured_at::date::text, d.origin "
                  "from detections d join species s on s.id = d.species_id") == [
        ("Python bivittatus", "2005-06-25", "observer")]
    ((license_, uri, source),) = q(
        url, "select m.license, m.uri, s.name from media_items m "
             "join sources s on s.id = m.source_id")
    assert license_ == NAS_LICENSE and uri.endswith("164538") and source == "USGS NAS"
    assert q(url, "select scope from ingestion_cursors") == [("everglades:nas",)]


async def test_nas_is_skipped_outside_the_united_states(ingest_db_url):
    assert "bandipur" not in ZONE_COUNTIES
    stats = await run_zone(ingest_db_url, "bandipur")  # no HTTP is mocked: a request would fail
    assert (stats.fetched, stats.stored) == (0, 0)
    assert q(ingest_db_url, "select count(*) from ingestion_runs") == [(0,)]
