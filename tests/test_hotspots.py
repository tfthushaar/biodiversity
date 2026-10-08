"""hotspot_cells: invasive records grouped into map cells, callable by the public role."""

import psycopg
import pytest

from helpers import World, day


@pytest.fixture
def populated(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn)
        w.species("Lantana camara", invasive=True)
        w.species("Senna spectabilis", invasive=True)
        w.species("Axis axis")  # native here: never part of a hotspot
        for _ in range(3):
            w.observe("Lantana camara", day(2020), 76.501, 11.701)
        w.observe("Senna spectabilis", day(2023), 76.505, 11.705)
        w.observe("Lantana camara", day(2019), 76.601, 11.801)  # a second, quieter cell
        w.observe("Axis axis", day(2020), 76.501, 11.701)
        conn.commit()
        conn.execute("set local role anon")
        yield conn
        conn.rollback()


def cells(conn, *args):
    return conn.execute("select hotspot_cells(%s, %s, %s)", args).fetchone()[0]


def test_records_are_grouped_into_cells_busiest_first(populated):
    got = cells(populated, "bandipur", 0.02, None)
    assert got["cell"] == 0.02
    assert [c["records"] for c in got["cells"]] == [4, 1]
    top = got["cells"][0]
    assert top["species_count"] == 2
    assert top["west"] <= 76.501 < top["east"] and top["south"] <= 11.701 < top["north"]
    assert round(top["east"] - top["west"], 6) == 0.02


def test_each_cell_lists_its_species_most_recorded_first(populated):
    top = cells(populated, "bandipur", 0.02, None)["cells"][0]
    assert [(s["name"], s["records"]) for s in top["species"]] == [
        ("Lantana camara", 3), ("Senna spectabilis", 1)]
    assert (top["species"][0]["first_year"], top["species"][0]["last_year"]) == (2020, 2020)


def test_native_species_never_appear(populated):
    names = {s["name"] for c in cells(populated, "bandipur", 0.02, None)["cells"]
             for s in c["species"]}
    assert names == {"Lantana camara", "Senna spectabilis"}


def test_a_species_filter_narrows_the_result(populated):
    got = cells(populated, "bandipur", 0.02, "Senna spectabilis")
    assert [c["records"] for c in got["cells"]] == [1]
    assert cells(populated, "bandipur", 0.02, "Not a species")["cells"] == []


def test_an_unknown_zone_is_empty_not_an_error(populated):
    assert cells(populated, "nowhere", 0.02, None) == {"cell": 0.02, "cells": []}


def test_the_cell_size_is_kept_within_sensible_bounds(populated):
    assert cells(populated, "bandipur", 50.0, None)["cell"] == 0.5
    assert cells(populated, "bandipur", 0.0001, None)["cell"] == 0.005
    assert cells(populated, "bandipur", None, None)["cell"] == 0.02


def test_a_large_cell_merges_neighbours(populated):
    got = cells(populated, "bandipur", 0.5, None)
    assert [c["records"] for c in got["cells"]] == [5]
