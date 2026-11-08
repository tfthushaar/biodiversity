"""hotspot_grid and the chart summaries: invasive records grouped into square map cells,
callable by the public role."""

import math

import psycopg
import pytest

from helpers import World, day


def grid_spot(conn, zone="bandipur", across=0, up=0, lon=76.5, lat=11.7, km=2.0):
    """The centre of a 2 km square near (lon, lat), `across` squares east and `up` squares north.

    The squares sit on a fixed grid, so a test places its points from the grid. Points placed by
    hand can land on either side of an edge between two squares. The square chosen is in the middle
    of a 50 km block (25 squares a side), so squares a few steps apart still share one 50 km square.
    """
    lat0 = conn.execute("select center_lat from zones where slug = %s", (zone,)).fetchone()[0]
    dlat = km / 110.574
    dlon = km / (111.320 * math.cos(math.radians(lat0)))
    cx = math.floor(lon / dlon / 25) * 25 + 12 + across
    cy = math.floor(lat / dlat / 25) * 25 + 12 + up
    return (cx + 0.5) * dlon, (cy + 0.5) * dlat


@pytest.fixture
def populated(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn)
        w.species("Lantana camara", invasive=True)
        w.species("Senna spectabilis", invasive=True)
        w.species("Axis axis")  # native here: never part of a hotspot
        here = grid_spot(conn)
        quiet = grid_spot(conn, across=2, up=2)  # a second, quieter square
        for _ in range(3):
            w.observe("Lantana camara", day(2020), *here)
        w.observe("Senna spectabilis", day(2023), *here)
        w.observe("Lantana camara", day(2019), *quiet)
        w.observe("Axis axis", day(2020), *here)
        conn.commit()
        conn.execute("set local role anon")
        yield conn
        conn.rollback()


def cells(conn, zone="bandipur", km=2.0, species=None, sources=None, year_from=None,
          year_to=None, kingdom=None):
    return conn.execute(
        "select hotspot_grid(%s, %s, %s, %s, %s, %s, %s)",
        (zone, km, species, sources, year_from, year_to, kingdom)).fetchone()[0]


def size_km(cell):
    """Width and height of a cell in kilometres, from its corners."""
    mid = math.radians((cell["south"] + cell["north"]) / 2)
    return ((cell["east"] - cell["west"]) * 111.320 * math.cos(mid),
            (cell["north"] - cell["south"]) * 110.574)


def test_records_are_grouped_into_cells_busiest_first(populated):
    got = cells(populated)
    assert got["km"] == 2
    assert [c["records"] for c in got["cells"]] == [4, 1]
    top = got["cells"][0]
    assert top["species_count"] == 2
    lon, lat = grid_spot(populated)
    assert top["west"] <= lon < top["east"] and top["south"] <= lat < top["north"]


def test_each_cell_lists_its_species_most_recorded_first(populated):
    top = cells(populated)["cells"][0]
    assert [(s["name"], s["records"]) for s in top["species"]] == [
        ("Lantana camara", 3), ("Senna spectabilis", 1)]
    assert (top["species"][0]["first_year"], top["species"][0]["last_year"]) == (2020, 2020)
    assert top["species"][0]["kingdom"] == "Plantae"


def test_each_cell_carries_its_records_by_year_and_by_source(populated):
    top = cells(populated)["cells"][0]
    assert top["by_year"] == [[2020, 3], [2023, 1]]
    assert sum(top["by_source"].values()) == 4 and len(top["by_source"]) == 1


def test_native_species_never_appear(populated):
    names = {s["name"] for c in cells(populated)["cells"] for s in c["species"]}
    assert names == {"Lantana camara", "Senna spectabilis"}


def test_a_species_filter_narrows_the_result(populated):
    got = cells(populated, species="Senna spectabilis")
    assert [c["records"] for c in got["cells"]] == [1]
    assert cells(populated, species="Not a species")["cells"] == []


def test_an_unknown_zone_is_empty_not_an_error(populated):
    assert cells(populated, zone="nowhere") == {"km": None, "cells": []}


def test_the_cell_size_is_kept_within_sensible_bounds(populated):
    assert cells(populated, km=500.0)["km"] == 50
    assert cells(populated, km=0.01)["km"] == 0.5
    assert cells(populated, km=None)["km"] == 2


def test_a_large_cell_merges_neighbours(populated):
    got = cells(populated, km=50)
    assert [c["records"] for c in got["cells"]] == [5]


@pytest.mark.parametrize(("zone", "lon", "lat"), [
    ("bandipur", 76.50, 11.70),     # close to the equator
    ("everglades", -80.90, 25.30),
    ("smokies", -83.50, 35.60),     # where a degree of longitude is 19% shorter
])
def test_cells_are_square_wherever_the_park_is(ingest_db_url, zone, lon, lat):
    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn, zone)
        w.species("Lantana camara", invasive=True)
        w.observe("Lantana camara", day(2020), lon, lat)
        conn.commit()
        conn.execute("set local role anon")
        for km in (0.5, 2.0, 10.0):
            (cell,) = cells(conn, zone, km)["cells"]
            width, height = size_km(cell)
            assert width == pytest.approx(km, rel=0.01) and height == pytest.approx(km, rel=0.01)


def test_sources_years_and_kingdoms_each_narrow_the_result(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn)
        w.species("Lantana camara", invasive=True)
        w.species("Python bivittatus", invasive=True, kingdom="Animalia")
        museum = w.add_source("GBIF specimens")
        here = grid_spot(conn)
        w.observe("Lantana camara", day(2019), *here)
        w.observe("Lantana camara", day(2024), *here)
        w.observe("Lantana camara", day(2024), *here, source=museum)
        w.observe("Python bivittatus", day(2024), *here)
        conn.commit()
        conn.execute("set local role anon")

        def total(**kw):
            return sum(c["records"] for c in cells(conn, **kw)["cells"])

        assert total() == 4
        assert total(sources="GBIF specimens") == 1
        assert total(sources="GBIF specimens,nothing") == 1
        assert total(year_from=2020) == 3
        assert total(year_to=2019) == 1
        assert total(year_from=2020, year_to=2024) == 3
        assert total(kingdom="Animalia") == 1
        assert total(kingdom="Plantae", year_from=2024, sources="GBIF specimens") == 1
        assert total(kingdom="Fungi") == 0


def test_the_yearly_summary_counts_by_year_for_a_park_or_everywhere(populated):
    by_year = populated.execute("select invasive_by_year('bandipur')").fetchone()[0]
    assert by_year == [{"year": 2019, "records": 1}, {"year": 2020, "records": 3},
                       {"year": 2023, "records": 1}]
    assert populated.execute("select invasive_by_year()").fetchone()[0] == by_year
    senna = populated.execute("select invasive_by_year('bandipur', 'Senna spectabilis')"
                              ).fetchone()[0]
    assert senna == [{"year": 2023, "records": 1}]
    assert populated.execute("select invasive_by_year('nowhere')").fetchone()[0] == []


def test_the_species_profile_gathers_what_the_species_page_charts(populated):
    got = populated.execute("select species_profile('Lantana camara')").fetchone()[0]
    assert got["records"] == 4 and (got["first_year"], got["last_year"]) == (2019, 2020)
    assert got["by_park"] == [{"slug": "bandipur", "park": got["by_park"][0]["park"],
                               "records": 4}]
    assert got["by_year"] == [{"year": 2019, "records": 1}, {"year": 2020, "records": 3}]
    assert [s["records"] for s in got["by_source"]] == [4]
    empty = populated.execute("select species_profile('Not a species')").fetchone()[0]
    assert empty["records"] == 0 and empty["by_park"] == [] and empty["by_year"] == []
