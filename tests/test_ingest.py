import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
import pytest

from biodiv.ingestion.gbif_occurrences import GBIF_OCCURRENCE_API
from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.inaturalist import INAT_API
from biodiv.workers.ingest import ingest_zone, load_zones
from helpers import exact, mock_gbif

FIXTURES = Path(__file__).parent / "fixtures"
INSIDE_BANDIPUR = (76.63, 11.67)  # lon, lat


def _fixture(name, label):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    wanted = data["labels"][label]
    return next(r for r in data["results"] if (r.get("id") or r.get("key")) == wanted)


def inat_obs(
    oid, name, lonlat=INSIDE_BANDIPUR, *, rank="species", when="2025-03-10T10:00:00+05:30", **over
):
    """A synthetic iNaturalist observation, cloned from a real one so the shape stays honest."""
    o = copy.deepcopy(_fixture("inat_observations.json", "plain_research"))
    o.update(
        id=oid, uri=f"https://www.inaturalist.org/observations/{oid}",
        geojson={"type": "Point", "coordinates": list(lonlat)},
        time_observed_at=when, observed_on=when[:10],
        public_positional_accuracy=10, obscured=False, captive=False,
    )
    o["taxon"] = {
        "id": oid, "name": name, "rank": rank, "iconic_taxon_name": "Plantae",
        "preferred_common_name": f"common {name}",
    }
    o.update(over)
    return o


def mock_inat(respx_mock, observations):
    """Behaves like the real API: id_above paging, ascending ids."""

    def handler(request):
        above, size = int(request.url.params["id_above"]), int(request.url.params["per_page"])
        rows = sorted((o for o in observations if o["id"] > above), key=lambda o: o["id"])
        return httpx.Response(200, json={"results": rows[:size]})

    return respx_mock.get(f"{INAT_API}/observations").mock(side_effect=handler)


def client(**kw):
    return PoliteClient(user_agent="t", per_second=1000, backoff=0, retries=1, **kw)


async def run(url, *, source="inaturalist", **kw):
    with psycopg.connect(url, autocommit=True) as conn:
        zone = load_zones(conn, ["bandipur"])[0]
        async with client() as raw, client() as gb:
            return await ingest_zone(
                conn, zone, source=source, raw_http=raw, gbif_http=gb, cache={}, **kw
            )


def q(url, sql, params=None):
    with psycopg.connect(url) as conn:
        return conn.execute(sql, params).fetchall()


def corner_outside_polygon(url):
    """A point inside Bandipur's search box but outside the reserve itself."""
    ((lon, lat),) = q(url, "select st_xmin(geom) + 0.001, st_ymin(geom) + 0.001 from zones "
                           "where slug = 'bandipur'")
    ((inside,),) = q(url, "select st_within(st_setsrid(st_makepoint(%s, %s), 4326), geom) "
                          "from zones where slug = 'bandipur'", (lon, lat))
    assert not inside, "test premise: the bbox corner must lie outside the polygon"
    return lon, lat


# -------------------------------------------------------------- iNaturalist


async def test_inaturalist_end_to_end(ingest_db_url, respx_mock):
    url = ingest_db_url
    mock_gbif(respx_mock, {"Lantana camara": exact(2925303, "Lantana camara"),
                           "Senna spectabilis": exact(2968573, "Senna spectabilis")})
    mock_inat(respx_mock, [
        inat_obs(100, "Lantana camara"),
        inat_obs(101, "Senna spectabilis", when="2025-03-12T09:00:00+05:30"),
        inat_obs(102, "Lantana camara", lonlat=corner_outside_polygon(url)),
        inat_obs(103, "Lantana camara", obscured=True),
        inat_obs(104, "Lantana", rank="genus"),
        inat_obs(105, "Lantana camara", captive=True),
    ])

    stats = await run(url)
    assert (stats.fetched, stats.stored, stats.skipped_dupe) == (6, 2, 0)
    assert dict(stats.rejected) == {
        "outside_zone": 1, "obscured_location": 1,
        "not_species_level": 1, "captive_or_cultivated": 1,
    }

    # Stored as verified-by-observer records, placed in the zone, linked to GBIF taxa.
    assert q(url, "select count(*) from media_items") == [(2,)]
    assert q(url, "select origin, z.slug from detections d join zones z on z.id = d.zone_id") == [
        ("observer", "bandipur"), ("observer", "bandipur"),
    ]
    assert q(url, "select scientific_name, gbif_taxon_key, common_name, inat_taxon_id "
                  "from species order by 1") == [
        ("Lantana camara", 2925303, "common Lantana camara", 100),
        ("Senna spectabilis", 2968573, "common Senna spectabilis", 101),
    ]

    # The run is auditable: what was fetched, what was refused and why, where it got to.
    ((fetched, rejected, finished),) = q(
        url, "select fetched, rejected, finished_at is not null from ingestion_runs")
    assert fetched == 6 and finished and rejected["obscured_location"] == 1
    assert q(url, "select scope, cursor from ingestion_cursors") == [("bandipur", "105")]


async def test_rerunning_is_incremental_and_never_duplicates(ingest_db_url, respx_mock):
    url = ingest_db_url
    mock_gbif(respx_mock, {"Lantana camara": exact(2925303, "Lantana camara")})
    both = [inat_obs(100, "Lantana camara"), inat_obs(101, "Lantana camara")]
    route = mock_inat(respx_mock, both)

    await run(url)
    again = await run(url)  # incremental: resumes after id 101, so nothing comes back
    assert (again.fetched, again.stored) == (0, 0)
    assert route.calls.last.request.url.params["id_above"] == "101"

    full = await run(url, full=True)  # ignores the cursor: refetches, finds all already stored
    assert (full.fetched, full.stored, full.skipped_dupe) == (2, 0, 2)
    assert q(url, "select count(*) from media_items") == [(2,)]
    assert q(url, "select count(*) from detections") == [(2,)]


async def test_observations_feed_the_effort_normalised_rollups(ingest_db_url, respx_mock):
    url = ingest_db_url
    mock_gbif(respx_mock, {"Lantana camara": exact(2925303, "Lantana camara"),
                           "Axis axis": exact(5219771, "Axis axis", kingdom="Animalia")})
    mock_inat(respx_mock, [inat_obs(1, "Lantana camara"), inat_obs(2, "Axis axis")])
    await run(url)

    with psycopg.connect(url) as conn:
        conn.execute(
            "insert into invasive_status (species_id, country, is_invasive) "
            "select id, 'IN', true from species where scientific_name = 'Lantana camara'")
        conn.execute("select refresh_rollups()")
        conn.commit()
    # Two observations that month; one is the invader: index 1/2. The chital counts as native.
    assert q(url, "select detections, effort, normalised_index from invasion_index_monthly") == [
        (1, 2, 0.5)]
    assert q(url, "select detections, effort, normalised_index from native_trend_monthly") == [
        (1, 2, 0.5)]


async def test_a_failed_run_is_recorded_and_does_not_advance_the_cursor(ingest_db_url, respx_mock):
    url = ingest_db_url
    mock_gbif(respx_mock, {"Lantana camara": exact(2925303, "Lantana camara")})
    page = [inat_obs(i, "Lantana camara") for i in range(1, 201)]  # one full page

    def handler(request):
        if int(request.url.params["id_above"]) == 0:
            return httpx.Response(200, json={"results": page})
        return httpx.Response(500)  # the second page fails for good

    respx_mock.get(f"{INAT_API}/observations").mock(side_effect=handler)
    with pytest.raises(httpx.HTTPStatusError):
        await run(url)

    ((failed, notes),) = q(url, "select failed, notes from ingestion_runs")
    assert failed == 1 and "FAILED" in notes
    assert q(url, "select count(*) from ingestion_cursors") == [(0,)]  # will retry from the start
    assert q(url, "select count(*) from media_items") == [(200,)]  # the good batch was kept
    # ...and retrying later cannot duplicate it.
    mock_inat(respx_mock, [inat_obs(i, "Lantana camara") for i in range(1, 201)])
    retry = await run(url)
    assert (retry.stored, retry.skipped_dupe) == (0, 200)


async def test_an_autocommit_connection_is_required(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:  # autocommit off
        zone = load_zones(conn, ["bandipur"])[0]
        async with client() as raw, client() as gb:
            with pytest.raises(ValueError, match="autocommit"):
                await ingest_zone(conn, zone, source="inaturalist", raw_http=raw,
                                  gbif_http=gb, cache={})


# --------------------------------------------------------------------- GBIF


async def test_gbif_specimens_skip_the_inaturalist_mirror_and_keep_real_dates(
    ingest_db_url, respx_mock
):
    url = ingest_db_url
    lon, lat = INSIDE_BANDIPUR
    specimen = _fixture("gbif_occurrences.json", "specimen_full_date") | {
        "decimalLongitude": lon, "decimalLatitude": lat}
    results = [
        _fixture("gbif_occurrences.json", "inat_mirror"),
        specimen,
        _fixture("gbif_occurrences.json", "specimen_year_only"),
    ]
    respx_mock.get(GBIF_OCCURRENCE_API).mock(
        return_value=httpx.Response(200, json={"results": results, "endOfRecords": True})
    )
    match = mock_gbif(respx_mock, {})

    stats = await run(url, source="gbif")
    assert (stats.fetched, stats.stored) == (3, 1)
    assert dict(stats.rejected) == {"duplicate_of_inaturalist": 1, "no_date": 1}
    assert not match.called  # GBIF records already carry a taxon key: no name matching needed

    assert q(url, "select s.scientific_name, s.gbif_taxon_key, d.captured_at::date::text "
                  "from detections d join species s on s.id = d.species_id") == [
        ("Apis cerana", specimen["speciesKey"], "2025-03-20")]
    ((scope, cursor),) = q(url, "select scope, cursor from ingestion_cursors")
    assert scope == "bandipur:specimens"
    assert cursor == datetime.now(UTC).date().isoformat()  # GBIF cursors are dates
