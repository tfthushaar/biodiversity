# ruff: noqa: E501
"""IUCN importer. Fixtures are synthetic and shaped like the real API: IUCN's terms do not allow
Red List data to be redistributed, so no real response is kept in the repository."""

import httpx
import psycopg
import pytest

from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.iucn import IUCN_API, IucnClient, parse_assessment, split_names
from biodiv.workers.import_iucn import run


def client():
    return PoliteClient(user_agent="t", per_second=1000, backoff=0, retries=1)


def assessment(aid=1, native="Example nativus", ias="Example invasor", code="8_1_2", **over):
    return {
        "assessment_id": aid, "year_published": "2020",
        "url": f"https://www.iucnredlist.org/species/{aid}/{aid}",
        "citation": f"Someone 2020. {native}. The IUCN Red List of Threatened Species 2020.",
        "red_list_category": {"code": "VU"},
        "taxon": {"scientific_name": native, "kingdom_name": "ANIMALIA", "sis_id": aid},
        "threats": [
            {"code": "9_3_4", "scope": "Whole (>90%)", "timing": "Ongoing", "score": "Low Impact: 5", "ias": None},
            {"code": code, "scope": "Majority (50-90%)", "timing": "Ongoing", "score": "Low Impact: 5",
             "ias": ias},
        ],
        **over,
    }


# ----------------------------------------------------------------------------------- parsing


@pytest.mark.parametrize("raw,expected", [
    ("Ambloplites rupestris", ["Ambloplites rupestris"]),
    ("Rattus rattus; Felis catus", ["Rattus rattus", "Felis catus"]),
    ("Rattus rattus and Mus musculus", ["Rattus rattus", "Mus musculus"]),
    ("Sus scrofa (feral pig), Canis lupus familiaris", ["Sus scrofa", "Canis lupus familiaris"]),
    ("Oncorhynchus mykiss var. irideus", ["Oncorhynchus mykiss var. irideus"]),
    ("Rattus rattus; Rattus rattus", ["Rattus rattus"]),
    ("various species", []),
    ("Rats", []),
    ("", []),
    (None, []),
])
def test_names_are_taken_from_the_ias_field_and_only_scientific_names_are_kept(raw, expected):
    assert split_names(raw) == expected


def test_only_named_species_threats_are_read():
    got = parse_assessment(assessment(ias="Example invasor"))
    assert [(t.native_name, t.invasive_name) for t in got] == [("Example nativus", "Example invasor")]
    t = got[0]
    assert (t.scope, t.timing, t.score, t.year, t.category) == (
        "Majority (50-90%)", "Ongoing", "Low Impact: 5", 2020, "VU")
    assert t.url.endswith("/1/1") and "IUCN Red List" in t.citation
    assert parse_assessment(assessment(code="8_1_1")) == []  # a different invasive threat code


def test_an_assessment_with_no_usable_name_gives_nothing():
    assert parse_assessment(assessment(ias="various species")) == []
    assert parse_assessment({"assessment_id": 5, "taxon": {}}) == []


# ------------------------------------------------------------------------------------ client


async def test_the_client_follows_next_links_and_sends_the_token(respx_mock):
    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers.get("authorization")))
        if "page=2" in str(request.url):
            return httpx.Response(200, json={"assessments": [{"assessment_id": 3}]})
        return httpx.Response(200, headers={
            "link": f'<{IUCN_API}/threats/8_1_2?latest=true&page=2>; rel="next"'},
            json={"assessments": [{"assessment_id": 1}, {"assessment_id": 2}]})

    respx_mock.get(url__startswith=f"{IUCN_API}/threats/8_1_2").mock(side_effect=handler)
    async with client() as http:
        got = await IucnClient(http, "secret-token").assessment_ids("/threats/8_1_2")
    assert sorted(got) == [1, 2, 3]
    assert len(seen) == 2 and all(auth == "secret-token" for _, auth in seen)


# ------------------------------------------------------------------------------- the import


def mock_api(respx_mock, named, in_country, full):
    respx_mock.get(f"{IUCN_API}/information/red_list_version").mock(
        return_value=httpx.Response(200, json={"red_list_version": "2026-1"}))
    respx_mock.get(url__startswith=f"{IUCN_API}/threats/8_1_2").mock(return_value=httpx.Response(
        200, json={"assessments": [{"assessment_id": i, "url": f"u{i}"} for i in named]}))
    respx_mock.get(url__startswith=f"{IUCN_API}/countries/IN").mock(return_value=httpx.Response(
        200, json={"assessments": [{"assessment_id": i, "url": f"u{i}"} for i in in_country]}))
    for aid, body in full.items():
        respx_mock.get(f"{IUCN_API}/assessment/{aid}").mock(return_value=httpx.Response(200, json=body))


async def test_links_are_stored_privately_and_a_rerun_skips_them(ingest_db_url, respx_mock):
    full = {
        1: assessment(1, "Example nativus", "Lantana camara; Unknown invadus", url="u1"),
        2: assessment(2, "Other nativus", "Lantana camara", url="u2"),
    }
    mock_api(respx_mock, named=[1, 2, 3], in_country=[1, 2, 4], full=full)
    with psycopg.connect(ingest_db_url, autocommit=True) as conn:
        conn.execute("insert into species (scientific_name, kingdom) values ('Lantana camara', 'Plantae')")
        async with client() as http:
            stats, _ = await run(conn, IucnClient(http, "t"), ["IN"])
        assert (stats.candidates, stats.fetched, stats.links, stats.unresolved_invaders) == (2, 2, 3, 1)

        rows = conn.execute(
            "select n.scientific_name, t.invasive_name, t.invasive_species_id is not null, "
            "t.iucn_threat_code, t.evidence_source, t.citation_url, t.citation "
            "from threat_links t join species n on n.id = t.native_species_id order by 1, 2").fetchall()
        assert [r[:6] for r in rows] == [
            ("Example nativus", "Lantana camara", True, "8.1.2", "iucn", "u1"),
            ("Example nativus", "Unknown invadus", False, "8.1.2", "iucn", "u1"),
            ("Other nativus", "Lantana camara", True, "8.1.2", "iucn", "u2"),
        ]
        assert "version 2026-1" in rows[0][6]  # the Red List version travels with the row

        async with client() as http:
            again, _ = await run(conn, IucnClient(http, "t"), ["IN"])
        assert (again.skipped, again.fetched, again.links) == (2, 0, 0)
        assert conn.execute("select count(*) from threat_links").fetchone()[0] == 3

    # Hidden from the public: IUCN's terms forbid redistribution.
    with psycopg.connect(ingest_db_url) as conn:
        conn.execute("set local role anon")
        assert conn.execute("select count(*) from threat_links").fetchone()[0] == 0


async def test_a_dry_run_reads_and_parses_but_writes_nothing(ingest_db_url, respx_mock):
    mock_api(respx_mock, named=[1], in_country=[1], full={1: assessment(1, url="u1")})
    async with client() as http:
        stats, seen = await run(None, IucnClient(http, "t"), ["IN"], dry_run=True)
    assert stats.fetched == 1 and [t.invasive_name for t in seen] == ["Example invasor"]
    with psycopg.connect(ingest_db_url) as conn:
        assert conn.execute("select count(*) from threat_links").fetchone()[0] == 0


async def test_the_limit_stops_fetching(ingest_db_url, respx_mock):
    full = {i: assessment(i, f"Native {i}", url=f"u{i}") for i in (1, 2, 3)}
    mock_api(respx_mock, named=[1, 2, 3], in_country=[1, 2, 3], full=full)
    async with client() as http:
        stats, _ = await run(None, IucnClient(http, "t"), ["IN"], limit=2, dry_run=True)
    assert stats.fetched == 2
