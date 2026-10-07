import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from biodiv.ingestion.gbif_occurrences import (
    GBIF_OCCURRENCE_API,
    is_inaturalist_mirror,
    iter_occurrences,
    parse_occurrence,
)
from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.inaturalist import INAT_API, iter_observations, parse_observation
from biodiv.ingestion.observations import (
    Observation,
    short_license,
    usable_image,
    validate,
    validate_all,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    by_id = {r.get("id") or r.get("key"): r for r in data["results"]}
    return {label: by_id[i] for label, i in data["labels"].items()}


INAT = load("inat_observations.json")
GBIF = load("gbif_occurrences.json")

GOOD = Observation(
    source="inaturalist", external_id="1", record_url="u", taxon_name="Lantana camara",
    rank="species", lat=11.67, lon=76.63, captured_at=datetime(2025, 3, 1, tzinfo=UTC),
)
NOW = datetime(2027, 1, 1, tzinfo=UTC)  # pinned, and later than every fixture record


# --------------------------------------------------------------- validation


def test_a_good_observation_passes():
    assert validate(GOOD, now=NOW) is None


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"lat": 91.0}, "bad_coordinates"),
        ({"lon": -181.0}, "bad_coordinates"),
        ({"lat": 0.0, "lon": 0.0}, "null_island"),
        ({"obscured": True}, "obscured_location"),
        ({"uncertainty_m": 5000.0}, "imprecise_location"),
        ({"captured_at": None}, "no_date"),
        ({"captured_at": datetime(2030, 1, 1, tzinfo=UTC)}, "future_date"),
        ({"rank": "genus"}, "not_species_level"),
        ({"captive": True}, "captive_or_cultivated"),
        ({"taxon_name": ""}, "no_taxon"),
    ],
)
def test_each_rule_rejects_with_its_reason(change, reason):
    assert validate(replace(GOOD, **change), now=NOW) == reason


def test_unknown_accuracy_is_accepted_but_known_coarse_is_not():
    assert validate(replace(GOOD, uncertainty_m=None), now=NOW) is None
    assert validate(replace(GOOD, uncertainty_m=2000.0), now=NOW) is None
    assert validate(replace(GOOD, uncertainty_m=2000.1), now=NOW) == "imprecise_location"


def test_validate_all_counts_rejections_by_reason():
    fuzzed = replace(GOOD, obscured=True)
    kept, rejected = validate_all([GOOD, fuzzed, fuzzed])
    assert kept == [GOOD] and rejected == {"obscured_location": 2}


@pytest.mark.parametrize(
    ("raw", "short"),
    [
        ("http://creativecommons.org/licenses/by-nc/4.0/legalcode", "cc-by-nc"),
        ("http://creativecommons.org/publicdomain/zero/1.0/", "cc0"),
        ("CC-BY-SA", "cc-by-sa"),
        (None, None),
    ],
)
def test_short_license(raw, short):
    assert short_license(raw) == short


@pytest.mark.parametrize(
    ("lic", "usable"),
    [
        ("cc-by", True),
        ("cc0", True),
        ("cc-by-nd", False),
        (None, False),
        ("all rights reserved", False),
    ],
)
def test_only_permissively_licensed_images_are_usable(lic, usable):
    assert (usable_image("http://img", lic) is not None) is usable


# ----------------------------------------------- iNaturalist (real fixtures)


def test_inaturalist_records_get_the_right_verdict():
    verdicts = {k: validate(parse_observation(v), now=NOW) for k, v in INAT.items()}
    assert verdicts == {
        "lantana": None,
        "senna": None,
        "plain_research": None,
        "obscured": "obscured_location",  # deliberately fuzzed position
        "unlicensed_photo": "imprecise_location",  # real record, accurate only to ~2.9 km
        "genus_only": "not_species_level",
    }


def test_inaturalist_unlicensed_photos_are_kept_as_records_but_not_as_images():
    lantana = parse_observation(INAT["lantana"])
    assert lantana.taxon_name == "Lantana camara"
    assert lantana.image_url is None  # all rights reserved: usable as an occurrence only

    licensed = parse_observation(INAT["plain_research"])
    assert licensed.image_license == "cc-by-nc"
    assert "/medium." in licensed.image_url  # upgraded from the 75px "square" thumbnail
    assert "/square." not in licensed.image_url


def test_inaturalist_times_are_normalised_to_utc():
    obs = parse_observation(INAT["plain_research"])
    assert obs.captured_at.tzinfo is not None
    assert obs.captured_at.utcoffset().total_seconds() == 0


def test_inaturalist_record_without_a_taxon_is_unparseable():
    assert parse_observation({**INAT["lantana"], "taxon": None}) is None
    assert parse_observation({**INAT["lantana"], "geojson": None}) is None


# ------------------------------------------------------ GBIF (real fixtures)


def test_gbif_records_get_the_right_verdict():
    verdicts = {
        k: validate(parse_occurrence(v), now=NOW)
        for k, v in GBIF.items()
    }
    assert verdicts["specimen_full_date"] is None
    assert verdicts["specimen_year_only"] == "no_date"  # a monthly index needs a real day
    assert verdicts["genus_only"] == "not_species_level"
    assert verdicts["ebird"] is None


def test_gbif_species_level_comes_from_species_key_not_the_rank_string():
    """Apis cerana is reported as taxonRank=UNRANKED but is a perfectly good species."""
    rec = GBIF["specimen_full_date"]
    assert rec["taxonRank"] == "UNRANKED"
    obs = parse_occurrence(rec)
    assert obs.rank == "species" and obs.gbif_taxon_key == rec["speciesKey"]


def test_gbif_inaturalist_mirror_is_detected_and_keeps_its_licensed_image():
    assert is_inaturalist_mirror(GBIF["inat_mirror"])
    assert not is_inaturalist_mirror(GBIF["ebird"])
    obs = parse_occurrence(GBIF["inat_mirror"])
    assert obs.image_license == "cc-by-nc" and obs.image_url


# ------------------------------------------------------------ pagination


def _http():
    return PoliteClient(user_agent="t", per_second=1000, backoff=0)


async def test_inaturalist_pages_by_id_above(respx_mock):
    seen = []

    def handler(request):
        above = int(request.url.params["id_above"])
        seen.append((above, int(request.url.params["per_page"])))
        data = [{"id": i} for i in (1, 2, 3, 4, 5) if i > above][:2]
        return httpx.Response(200, json={"results": data})

    respx_mock.get(f"{INAT_API}/observations").mock(side_effect=handler)
    async with _http() as http:
        got = [o["id"] async for o in iter_observations(http, (0, 0, 1, 1), per_page=2)]
    assert got == [1, 2, 3, 4, 5]
    assert [s[0] for s in seen] == [0, 2, 4]  # each page resumes after the last id seen


async def test_inaturalist_respects_max_results(respx_mock):
    respx_mock.get(f"{INAT_API}/observations").mock(
        side_effect=lambda r: httpx.Response(
            200, json={"results": [{"id": i} for i in range(1, int(r.url.params["per_page"]) + 1)]}
        )
    )
    async with _http() as http:
        got = [o async for o in iter_observations(http, (0, 0, 1, 1), max_results=5)]
    assert len(got) == 5


async def test_gbif_pages_until_end_of_records(respx_mock):
    offsets = []

    def handler(request):
        off = int(request.url.params["offset"])
        offsets.append(off)
        return httpx.Response(
            200, json={"results": [{"key": off}, {"key": off + 1}], "endOfRecords": off >= 2}
        )

    respx_mock.get(GBIF_OCCURRENCE_API).mock(side_effect=handler)
    async with _http() as http:
        got = [o async for o in iter_occurrences(http, (0, 0, 1, 1), page_size=2)]
    assert [o["key"] for o in got] == [0, 1, 2, 3]
    assert offsets == [0, 2]
