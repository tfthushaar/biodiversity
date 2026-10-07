import io
import time
import zipfile

import httpx
import psycopg
import pytest

from biodiv.ingestion.gbif import GbifClient
from biodiv.ingestion.griis import (
    GRIIS_ARCHIVE_URL,
    canonical_name,
    filter_usable,
    parse_archive,
)
from biodiv.ingestion.http import PoliteClient, RateLimiter
from biodiv.workers.import_griis import import_griis
from biodiv.workers.migrate import migrate
from helpers import exact, mock_gbif

TAXON_HEADER = (
    "id\ttaxonID\tscientificName\tacceptedNameUsage\tkingdom\tphylum\tclass\torder\tfamily"
    "\ttaxonRank\ttaxonomicStatus"
)


def _taxon(i, name, accepted="", kingdom="Plantae", rank="SPECIES", status="ACCEPTED"):
    return f"{i}\t{i}\t{name}\t{accepted}\t{kingdom}\t\t\t\t\t{rank}\t{status}"


def make_archive(rows) -> bytes:
    """rows: (taxon_line, country, establishment_means, is_invasive)"""
    taxon = [TAXON_HEADER]
    dist = ["id\tlocationID\tcountryCode\toccurrenceStatus\testablishmentMeans"]
    prof = ["id\tisInvasive\thabitat"]
    for line, country, means, invasive in rows:
        i = line.split("\t")[0]
        taxon.append(line)
        dist.append(f"{i}\tX\t{country}\tPresent\t{means}")
        prof.append(f"{i}\t{invasive}\tTerrestrial")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("taxon.txt", "\n".join(taxon) + "\n")
        zf.writestr("distribution.txt", "\n".join(dist) + "\n")
        zf.writestr("speciesprofile.txt", "\n".join(prof) + "\n")
    return buf.getvalue()


ROWS = [
    (_taxon(1, "Lantana camara L."), "IN", "Alien", "Invasive"),
    (
        _taxon(2, "Acacia old Syn.", accepted="Acacia new Acc.", status="SYNONYM"),
        "IN", "Alien", "Null",
    ),
    (_taxon(3, "Acacia new Acc."), "IN", "Alien", "Null"),
    (_taxon(4, "Mystery plant Foo"), "IN", "Native|Alien", "Null"),
    (_taxon(5, "Doubtful thing Bar", status="DOUBTFUL"), "IN", "Alien", "Null"),
    (
        _taxon(6, "Mimosa diplotricha var. inermis (Adelb.) Veldkamp", rank="VARIETY"),
        "IN", "Alien", "Invasive",
    ),
    (_taxon(7, "Sus scrofa", kingdom="Animalia"), "IN", "Alien", "Invasive"),
]


# ------------------------------------------------------------------ parsing


def test_parse_joins_the_three_tables():
    recs = {r.taxon_id: r for r in parse_archive(make_archive(ROWS))}
    assert len(recs) == 7
    lantana = recs["1"]
    assert (lantana.country, lantana.is_invasive, lantana.kingdom) == ("IN", True, "Plantae")
    assert lantana.habitat == "Terrestrial"
    assert recs["3"].is_invasive is None  # "Null" means introduced but not assessed
    assert recs["2"].name_to_resolve == "Acacia new Acc."  # GRIIS's own accepted name wins
    assert recs["4"].establishment_means == "Native|Alien"


def test_doubtful_taxa_are_dropped():
    kept, dropped = filter_usable(parse_archive(make_archive(ROWS)))
    assert dropped == 1
    assert all(r.status != "DOUBTFUL" for r in kept)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Lantana camara L.", "Lantana camara"),
        ("Senna spectabilis (DC.) H.S.Irwin & Barneby", "Senna spectabilis"),
        ("Mimosa diplotricha var. inermis (Adelb.) Veldkamp", "Mimosa diplotricha var. inermis"),
        ("Rattus", "Rattus"),
    ],
)
def test_canonical_name_strips_authorship(raw, expected):
    assert canonical_name(raw) == expected


# ------------------------------------------------------------ polite client


def _client(**kw):
    return PoliteClient(user_agent="test", per_second=1000, backoff=0, **kw)


async def test_retries_transient_errors_then_succeeds(respx_mock):
    route = respx_mock.get("https://x.test/a").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"ok": 1}),
        ]
    )
    async with _client() as http:
        assert await http.get_json("https://x.test/a") == {"ok": 1}
    assert route.call_count == 2


async def test_gives_up_after_the_retry_budget(respx_mock):
    route = respx_mock.get("https://x.test/a").mock(return_value=httpx.Response(503))
    async with _client(retries=2) as http:
        with pytest.raises(httpx.HTTPStatusError):
            await http.get_json("https://x.test/a")
    assert route.call_count == 3


async def test_client_errors_are_not_retried(respx_mock):
    route = respx_mock.get("https://x.test/a").mock(return_value=httpx.Response(404))
    async with _client() as http:
        with pytest.raises(httpx.HTTPStatusError):
            await http.get_json("https://x.test/a")
    assert route.call_count == 1


async def test_rate_limiter_spaces_requests():
    limiter = RateLimiter(per_second=50)  # 20 ms apart
    start = time.monotonic()
    for _ in range(6):
        await limiter.wait()
    assert time.monotonic() - start >= 0.09


# --------------------------------------------------------------------- gbif


async def test_gbif_resolves_synonyms_to_the_accepted_taxon(respx_mock):
    mock_gbif(
        respx_mock,
        {"Old name": exact(1, "Old name", acceptedUsageKey=2)},
        {2: {"canonicalName": "New name", "kingdom": "Plantae", "rank": "SPECIES"}},
    )
    async with _client() as http:
        taxon = await GbifClient(http).resolve("Old name", "Plantae")
    assert (taxon.key, taxon.canonical_name) == (2, "New name")


@pytest.mark.parametrize(
    "response",
    [
        {"matchType": "NONE"},
        {"usageKey": 9, "matchType": "HIGHERRANK", "confidence": 99},  # only the genus matched
        {"usageKey": 9, "matchType": "FUZZY", "confidence": 80, "canonicalName": "x"},
    ],
)
async def test_gbif_refuses_to_guess(respx_mock, response):
    mock_gbif(respx_mock, {"Thing": response})
    async with _client() as http:
        assert await GbifClient(http).resolve("Thing", "Plantae") is None


# --------------------------------------------------------- end-to-end import


@pytest.fixture
def migrated_url(empty_db_url):
    migrate(empty_db_url)
    return empty_db_url


def _mock_world(respx_mock):
    respx_mock.get(GRIIS_ARCHIVE_URL).mock(
        return_value=httpx.Response(200, content=make_archive(ROWS))
    )
    mock_gbif(
        respx_mock,
        {
            "Lantana camara L.": exact(100, "Lantana camara"),
            "Acacia new Acc.": exact(200, "Acacia new Acc"),
            "Mimosa diplotricha var. inermis (Adelb.) Veldkamp": exact(
                301, "Mimosa diplotricha inermis", acceptedUsageKey=300, rank="VARIETY"
            ),
            "Sus scrofa": exact(400, "Sus scrofa", kingdom="Animalia"),
        },
        {300: {"canonicalName": "Mimosa diplotricha", "kingdom": "Plantae", "rank": "SPECIES"}},
    )


async def test_import_is_correct_and_idempotent(migrated_url, respx_mock):
    _mock_world(respx_mock)

    async def run():
        async with _client() as http:
            with psycopg.connect(migrated_url) as conn:
                return await import_griis(conn, http, "griis-test")

    stats = await run()
    assert stats.records == 6 and stats.doubtful_skipped == 1
    # Lantana, Acacia (synonym + accepted merged), Mystery, Mimosa, Sus.
    assert stats.species == 5
    assert (stats.gbif_matched, stats.gbif_unmatched) == (4, 1)
    assert stats.invasive == 3  # Lantana, Mimosa, Sus

    with psycopg.connect(migrated_url) as conn:
        rows = conn.execute(
            "select s.scientific_name, s.gbif_taxon_key, i.is_invasive, i.country "
            "from invasive_status i join species s on s.id = i.species_id order by 1"
        ).fetchall()
    assert rows == [
        ("Acacia new Acc", 200, None, "IN"),
        ("Lantana camara", 100, True, "IN"),
        ("Mimosa diplotricha", 300, True, "IN"),
        ("Mystery plant", None, None, "IN"),
        ("Sus scrofa", 400, True, "IN"),
    ]

    stats2 = await run()  # re-running must not duplicate anything
    assert stats2.species == 5
    with psycopg.connect(migrated_url) as conn:
        assert conn.execute("select count(*) from species").fetchone()[0] == 5
        assert conn.execute("select count(*) from invasive_status").fetchone()[0] == 5
        assert conn.execute("select count(*) from sources where name = 'GRIIS'").fetchone()[0] == 1
        assert conn.execute("select count(*) from ingestion_runs").fetchone()[0] == 2
