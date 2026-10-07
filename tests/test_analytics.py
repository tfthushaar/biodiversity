import random
from datetime import UTC, date, datetime

import psycopg
import pytest

from biodiv.analytics.alerts import (
    MIN_PRIOR_EFFORT,
    first_record_alerts,
    upsert_alerts,
)
from biodiv.analytics.impact import (
    MIN_CELLS,
    MIN_INVASIVE_RECORDS,
    RAREFY_TO,
    cooccurrence,
    documented_findings,
    trend,
    zone_report,
)
from biodiv.knowledge.loader import load_knowledge


class World:
    """Builds small, fully known datasets in a zone."""

    def __init__(self, conn, zone="bandipur"):
        self.conn = conn
        self.zone = zone
        self.zone_id = conn.execute("select id from zones where slug = %s", (zone,)).fetchone()[0]
        self.country = conn.execute("select country from zones where id = %s",
                                    (self.zone_id,)).fetchone()[0]
        self.source = conn.execute(
            "insert into sources (name, kind) values (%s, 'dataset') returning id",
            (f"test-{random.random()}",)).fetchone()[0]
        self.species_ids = {}
        self.n = 0

    def species(self, name, *, invasive=None, means=None):
        if name not in self.species_ids:
            sid = self.conn.execute(
                "insert into species (scientific_name, kingdom) "
                "values (%s, 'Plantae') returning id", (name,)).fetchone()[0]
            self.species_ids[name] = sid
            if invasive is not None or means:
                self.conn.execute(
                    "insert into invasive_status (species_id, country, is_invasive, "
                    "establishment_means) values (%s, %s, %s, %s)",
                    (sid, self.country, invasive, means or "Alien"))
        return self.species_ids[name]

    def observe(self, name, when, lon=76.5, lat=11.7):
        self.n += 1
        sid = self.species_ids[name]
        media = self.conn.execute(
            "insert into media_items (source_id, external_id, uri, captured_at, zone_id, geom) "
            "values (%s, %s, 'u', %s, %s, st_setsrid(st_makepoint(%s, %s), 4326)) returning id",
            (self.source, f"o{self.n}", when, self.zone_id, lon, lat)).fetchone()[0]
        self.conn.execute(
            "insert into detections (media_item_id, captured_at, species_id, confidence, geom, "
            "zone_id, origin) values (%s, %s, %s, 1.0, st_setsrid(st_makepoint(%s, %s), 4326), "
            "%s, 'observer')", (media, when, sid, lon, lat, self.zone_id))


def day(y, m=6, d=15):
    return datetime(y, m, d, tzinfo=UTC)


@pytest.fixture
def world(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        w = World(conn)
        w.species("Lantana camara", invasive=True)
        w.species("Axis axis", invasive=True, means="Native|Alien")  # chital: native on mainland
        for i in range(12):
            w.species(f"Native {i}")
        yield w
        conn.rollback()


# ------------------------------------------------------------------------ views


def test_invasive_records_include_only_purely_alien_flagged_species(world):
    world.observe("Lantana camara", day(2020))
    world.observe("Axis axis", day(2020))  # native in part of India: must not count
    world.observe("Native 0", day(2020))
    rows = world.conn.execute(
        "select s.scientific_name from invasive_records r join species s on s.id = r.species_id"
    ).fetchall()
    assert rows == [("Lantana camara",)]


def test_zone_summary_counts_and_dates(world):
    for y in (2018, 2020, 2022):
        world.observe("Lantana camara", day(y))
    (row,) = world.conn.execute(
        "select records, first_record::date::text, last_record::date::text, sources "
        "from zone_invasive_summary").fetchall()
    assert row == (3, "2018-06-15", "2022-06-15", 1)


# ------------------------------------------------------------ layer 2: co-occurrence


def build_grid(world, *, diversity_for, side=6):
    """A side x side grid of cells. Cell (i, j) gets k invasive records and 14 native ones spread
    over diversity_for(k) species."""
    for i in range(side):
        for j in range(side):
            lon, lat = 76.30 + 0.05 * i + 0.01, 11.60 + 0.05 * j + 0.01
            k = (i * 7 + j * 3) % 7
            for _ in range(k):
                world.observe("Lantana camara", day(2020), lon, lat)
            d = diversity_for(k)
            for r in range(14):
                world.observe(f"Native {r % d}", day(2020), lon, lat)


def test_where_invasives_are_denser_native_richness_is_lower_when_that_is_true(world):
    build_grid(world, diversity_for=lambda k: max(1, 8 - k))
    result = cooccurrence(world.conn, "bandipur")
    assert result.status == "ok"
    d = result.detail
    assert d["cells_usable"] == 36 and d["richness_compared_at"] == RAREFY_TO
    assert d["spearman_rho"] < -0.7
    assert d["ci95"][1] < 0  # the whole interval is below zero
    assert "Correlation, not cause" in result.caution


def test_no_relationship_gives_an_interval_that_includes_zero(world):
    rng = random.Random(4)
    build_grid(world, diversity_for=lambda k: rng.randint(2, 8))  # unrelated to k
    d = cooccurrence(world.conn, "bandipur").detail
    assert d["ci95"][0] < 0 < d["ci95"][1]


def test_too_few_cells_is_refused_with_the_reason_and_what_would_help(world):
    build_grid(world, diversity_for=lambda k: 5, side=3)  # only 9 cells
    r = cooccurrence(world.conn, "bandipur")
    assert r.status == "insufficient"
    assert f"need {MIN_CELLS}" in r.reason and "grid cells" in r.needs
    assert "spearman_rho" not in r.detail  # no number at all, not a weak one


def test_no_invasives_anywhere_means_nothing_to_compare(world):
    for i in range(6):
        for j in range(6):
            for r in range(14):
                world.observe(f"Native {r % 5}", day(2020), 76.30 + 0.05 * i + 0.01,
                              11.60 + 0.05 * j + 0.01)
    r = cooccurrence(world.conn, "bandipur")
    assert r.status == "insufficient" and "nothing to compare" in r.reason


def test_cells_with_too_few_native_records_are_not_compared(world):
    """A cell with only a handful of records cannot be rarefied to a fair sample size."""
    for _ in range(3):
        world.observe("Native 0", day(2020), 76.31, 11.61)  # 3 < RAREFY_TO
    r = cooccurrence(world.conn, "bandipur")
    assert r.detail["cells_total"] == 1 and r.detail["cells_usable"] == 0


# ----------------------------------------------------------------- layer 3: trend


def build_years(world, years, invasive_per_year, per_year=40):
    for y in years:
        k = invasive_per_year(y)
        for _ in range(k):
            world.observe("Lantana camara", day(y))
        for r in range(per_year - k):
            world.observe(f"Native {r % 6}", day(y))


def test_a_rising_invasive_share_and_falling_native_share_is_detected(world):
    build_years(world, range(2012, 2020), lambda y: 4 * (y - 2012))
    r = trend(world.conn, "bandipur")
    assert r.status == "ok"
    inv, nat = r.detail["invasive_per_observation"], r.detail["native_per_observation"]
    assert inv["tau"] == pytest.approx(1.0) and inv["p_value"] < 0.01 and inv["slope"] > 0
    assert nat["tau"] < 0 and nat["slope"] < 0
    assert "not a trend in abundance" in r.caution


def test_too_few_years_is_refused(world):
    build_years(world, range(2017, 2020), lambda y: 20)
    r = trend(world.conn, "bandipur")
    assert r.status == "insufficient" and "years" in r.reason


def test_too_few_invasive_records_is_refused_even_with_many_years(world):
    build_years(world, range(2010, 2020), lambda y: 2 if y == 2015 else 0)  # just 2 records
    r = trend(world.conn, "bandipur")
    assert r.status == "insufficient"
    assert f"need {MIN_INVASIVE_RECORDS}" in r.reason


def test_a_year_with_too_little_effort_does_not_count(world):
    build_years(world, range(2012, 2018), lambda y: 5)  # six good years
    for _ in range(5):
        world.observe("Native 0", day(2019))  # a thin year: ignored
    assert trend(world.conn, "bandipur").detail["usable_years"] == 6


# -------------------------------------------------------------- layer 1: documented


def finding(species, zone, summary):
    return {"species": species, "zone": zone, "finding_type": "concern", "affected": "forest",
            "summary": summary, "certainty": "unverified_concern", "region_note": "here",
            "source": "s", "quotes": ["a quote long enough to count as evidence here"]}


def load(world, findings):
    load_knowledge(world.conn, {
        "verified_on": "2026-10-07",
        "sources": {"s": {"citation": "C", "url": "https://x.org/s", "kind": "page"}},
        "playbooks": [], "impact_findings": findings})


def test_zone_specific_findings_show_even_when_the_species_is_not_recorded(world):
    load(world, [finding("Lantana camara", "bandipur", "Concern about Bandipur")])
    (f,) = documented_findings(world.conn, "bandipur")
    assert f["species"] == "Lantana camara" and f["recorded_in_zone"] is False
    assert f["records_in_zone"] == 0  # a worry is not a record, and is labelled so


def test_general_findings_appear_only_for_species_recorded_in_the_zone(world):
    load(world, [finding("Lantana camara", None, "General finding")])
    assert documented_findings(world.conn, "bandipur") == []  # not recorded here
    world.observe("Lantana camara", day(2020))
    (f,) = documented_findings(world.conn, "bandipur")
    assert f["recorded_in_zone"] is True and f["records_in_zone"] == 1


def test_findings_for_another_zone_are_not_shown(world):
    load(world, [finding("Lantana camara", "mudumalai", "Mudumalai only")])
    assert documented_findings(world.conn, "bandipur") == []


# -------------------------------------------------------------------------- alerts


def make_alert_world(world, *, prior=MIN_PRIOR_EFFORT, first=None):
    first = first or day(2025, 3, 1)
    for _ in range(prior):
        world.observe("Native 0", day(2024))
    world.observe("Lantana camara", first)
    return date(2025, 6, 1)


def test_a_recent_first_record_after_real_effort_raises_an_alert(world):
    as_of = make_alert_world(world)
    (a,) = first_record_alerts(world.conn, as_of)
    assert a["severity"] == "medium" and a["zone_id"] == world.zone_id
    ev = a["evidence"]
    assert ev["species"] == "Lantana camara" and ev["observations_in_zone_before"] >= 50
    assert "not first arrival" in ev["caveat"]  # the wording that stops it being misread


def test_too_little_prior_effort_means_absence_proves_nothing(world):
    as_of = make_alert_world(world, prior=MIN_PRIOR_EFFORT - 1)
    assert first_record_alerts(world.conn, as_of) == []


def test_an_old_first_record_is_not_news(world):
    as_of = make_alert_world(world, first=day(2022, 3, 1))
    assert first_record_alerts(world.conn, as_of) == []


def test_a_species_already_documented_in_the_zone_is_not_flagged(world):
    as_of = make_alert_world(world)
    load(world, [finding("Lantana camara", "bandipur", "Already known to be here")])
    assert first_record_alerts(world.conn, as_of) == []


def test_severity_is_high_when_harm_is_documented_elsewhere(world):
    as_of = make_alert_world(world)
    f = finding("Lantana camara", None, "Reduces richness")
    f["certainty"] = "review"
    load(world, [f])
    (a,) = first_record_alerts(world.conn, as_of)
    assert a["severity"] == "high" and a["evidence"]["documented_harm_elsewhere"] is True


def test_alerts_are_idempotent_and_refresh_in_place(world):
    as_of = make_alert_world(world)
    assert upsert_alerts(world.conn, first_record_alerts(world.conn, as_of)) == 1
    world.observe("Lantana camara", day(2025, 4, 1))  # more evidence arrives
    upsert_alerts(world.conn, first_record_alerts(world.conn, as_of))
    rows = world.conn.execute("select score, evidence->>'records' from alerts").fetchall()
    assert rows == [(2.0, "2")]  # one alert, updated, not duplicated


# ----------------------------------------------------------------------- the report


def test_zone_report_on_thin_data_says_so_for_each_statistical_layer(world):
    world.observe("Lantana camara", day(2020))
    world.observe("Native 0", day(2020))
    r = zone_report(world.conn, "bandipur")
    assert r["observations"] == 2 and r["species"] == 2
    assert [s["species"] for s in r["invasive_species"]] == ["Lantana camara"]
    assert r["layers"]["documented"]["status"] == "ok"
    for name in ("cooccurrence", "trend"):
        layer = r["layers"][name]
        assert layer["status"] == "insufficient" and layer["reason"] and layer["needs"]


def test_unknown_zone_is_an_error(world):
    with pytest.raises(ValueError, match="atlantis"):
        zone_report(world.conn, "atlantis")
