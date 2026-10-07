import copy
import json
from pathlib import Path

import pytest

from biodiv.training.photos import (
    TrainingPhoto,
    group_split,
    observer_hash,
    parse_photo,
)

FIXTURES = Path(__file__).parent / "fixtures"
REAL = json.loads((FIXTURES / "inat_observations.json").read_text(encoding="utf-8"))
LICENSED = next(o for o in REAL["results"] if o["id"] == REAL["labels"]["plain_research"])
UNLICENSED = next(o for o in REAL["results"] if o["id"] == REAL["labels"]["lantana"])


def with_user(o, uid):
    o = copy.deepcopy(o)
    o["user"] = {"id": uid}
    return o


def test_a_licensed_photo_becomes_provenance_not_a_person():
    photo = parse_photo(with_user(LICENSED, 987654321), "frog")
    assert photo.label == "frog" and photo.license == "cc-by-nc"
    assert "/medium." in photo.url
    assert photo.observation_id == LICENSED["id"]
    assert "987654321" not in repr(photo) and len(photo.observer) == 12  # only an opaque hash


def test_unlicensed_photos_are_refused():
    """The real Lantana record's photo is 'all rights reserved': usable as a record, not as data."""
    assert parse_photo(UNLICENSED, "lantana") is None


@pytest.mark.parametrize("change", [{"captive": True}, {"obscured": True}, {"taxon": None}])
def test_unsuitable_observations_are_refused(change):
    assert parse_photo({**LICENSED, **change}, "x") is None


def test_the_first_acceptably_licensed_photo_is_used():
    o = copy.deepcopy(LICENSED)
    bad = {**o["photos"][0], "license_code": None, "url": "https://x/square.jpg"}
    o["photos"] = [bad, o["photos"][0]]
    assert parse_photo(o, "x").url == o["photos"][1]["url"].replace("/square.", "/medium.")


def test_observer_hash_is_stable_and_distinguishes_people():
    assert observer_hash(1) == observer_hash(1) != observer_hash(2)


def photo(lat, lon):
    return TrainingPhoto("x", 1, 1, "u", "cc0", "h", lat, lon)


def test_in_india_flag():
    assert photo(11.67, 76.63).in_india  # Bandipur
    assert not photo(-2.3, 34.8).in_india  # Serengeti
    assert not photo(None, None).in_india


# ------------------------------------------------------------------ splitting


def items(n_groups=30, per_group=4):
    return [(g, i) for g in range(n_groups) for i in range(per_group)]


def test_no_observer_appears_on_both_sides_of_a_split():
    train, test = group_split(items(), group=lambda x: str(x[0]), fractions=(0.7, 0.3))
    assert {g for g, _ in train}.isdisjoint({g for g, _ in test})
    assert len(train) + len(test) == 120  # nothing lost or duplicated


def test_split_sizes_follow_the_fractions():
    train, val, test = group_split(
        items(60), group=lambda x: str(x[0]), fractions=(0.6, 0.2, 0.2))
    n = 240
    assert abs(len(train) - 0.6 * n) <= 8 and abs(len(val) - 0.2 * n) <= 8


def test_split_is_reproducible_and_seed_dependent():
    a = group_split(items(), lambda x: str(x[0]), (0.5, 0.5), seed=1)
    assert a == group_split(items(), lambda x: str(x[0]), (0.5, 0.5), seed=1)
    assert a != group_split(items(), lambda x: str(x[0]), (0.5, 0.5), seed=2)


def test_one_dominant_observer_cannot_be_split_across_parts():
    data = [("whale", i) for i in range(50)] + [(f"p{g}", 0) for g in range(10)]
    train, test = group_split(data, lambda x: x[0], (0.5, 0.5))
    side = train if ("whale", 0) in train else test
    assert all(("whale", i) in side for i in range(50))  # kept whole, so the split is lopsided


def test_bad_fractions_are_rejected():
    with pytest.raises(ValueError):
        group_split(items(), lambda x: str(x[0]), (0.5, 0.2))
