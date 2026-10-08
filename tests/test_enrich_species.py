"""Species photos: stored only with a usable licence and a credit."""

import httpx
import psycopg
import pytest

from biodiv.ingestion.http import PoliteClient
from biodiv.workers.enrich_species import INAT_TAXA, enrich, find_photo
from helpers import World, day


def client():
    return PoliteClient(user_agent="t", per_second=1000, backoff=0, retries=1)


def photo(code="cc-by-nc", pid=56087430,
          credit="(c) A. Photographer, some rights reserved (CC BY-NC)"):
    return {"id": pid, "license_code": code, "attribution": credit,
            "medium_url": f"https://example.org/photos/{pid}/medium.jpeg"}


def taxon(name="Lantana camara", default=None, tid=1):
    return {"id": tid, "name": name, "rank": "species", "default_photo": default}


def mock_taxa(respx_mock, results, detail=None):
    respx_mock.get(INAT_TAXA).mock(return_value=httpx.Response(200, json={"results": results}))
    if detail is not None:
        respx_mock.get(f"{INAT_TAXA}/1").mock(
            return_value=httpx.Response(200, json={"results": [detail]}))


async def test_a_freely_licensed_default_photo_is_used_with_its_credit(respx_mock):
    mock_taxa(respx_mock, [taxon(default=photo())])
    async with client() as http:
        got = await find_photo(http, "Lantana camara")
    assert got.url.endswith("/medium.jpeg") and got.license == "cc-by-nc"
    assert "A. Photographer" in got.credit
    assert got.source_url == "https://www.inaturalist.org/photos/56087430"


@pytest.mark.parametrize("bad", [
    photo(code=None),                      # all rights reserved
    photo(code="cc-by-nd"),                # no derivatives: not used
    photo(credit=""),                      # no credit to show
    {**photo(), "medium_url": None},       # no image
])
async def test_a_photo_that_cannot_be_shown_properly_is_not_used(respx_mock, bad):
    mock_taxa(respx_mock, [taxon(default=bad)], detail={"taxon_photos": []})
    async with client() as http:
        assert await find_photo(http, "Lantana camara") is None


async def test_another_photo_is_tried_when_the_default_is_not_free(respx_mock):
    mock_taxa(respx_mock, [taxon(default=photo(code=None))],
              detail={"taxon_photos": [{"photo": photo(code=None, pid=2)},
                                       {"photo": photo(code="cc-by", pid=3)}]})
    async with client() as http:
        got = await find_photo(http, "Lantana camara")
    assert got.license == "cc-by" and got.source_url.endswith("/3")


async def test_the_match_must_be_the_exact_species(respx_mock):
    mock_taxa(respx_mock, [taxon(name="Lantana montevidensis", default=photo())])
    async with client() as http:
        assert await find_photo(http, "Lantana camara") is None


async def test_only_species_with_invasive_records_are_enriched_and_only_once(
    ingest_db_url, respx_mock
):
    route = respx_mock.get(INAT_TAXA).mock(
        return_value=httpx.Response(200, json={"results": [taxon(default=photo())]}))
    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn)
        w.species("Lantana camara", invasive=True)
        w.species("Axis axis")  # native here: not looked up
        w.observe("Lantana camara", day(2020))
        w.observe("Axis axis", day(2020))
        conn.commit()

        async with client() as http:
            assert await enrich(conn, http) == (1, 0)
            assert route.call_count == 1
            assert await enrich(conn, http) == (0, 0)  # already has one
            assert route.call_count == 1

        row = conn.execute(
            "select photo_url, photo_credit, photo_license, photo_source_url from species "
            "where scientific_name = 'Lantana camara'").fetchone()
        assert row[2] == "cc-by-nc" and "A. Photographer" in row[1] and row[3].endswith("56087430")
        other = conn.execute(
            "select photo_url from species where scientific_name = 'Axis axis'").fetchone()
        assert other == (None,)


async def test_species_with_no_usable_photo_are_counted_not_failed(ingest_db_url, respx_mock):
    respx_mock.get(INAT_TAXA).mock(return_value=httpx.Response(200, json={"results": []}))
    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn)
        w.species("Lantana camara", invasive=True)
        w.observe("Lantana camara", day(2020))
        conn.commit()
        async with client() as http:
            assert await enrich(conn, http) == (0, 1)
