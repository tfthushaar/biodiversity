from biodiv.ingestion.lila import CAR, EMPTY, build_sample, empty_images


def image(i, location="1"):
    return {"id": i, "file_name": f"{i}.jpg", "width": 100, "height": 50,
            "location": location, "date_captured": "2011-01-01 00:00:00"}


def ann(i, cat, box):
    return {"image_id": i, "category_id": cat, "bbox": box}


CATS = [
    {"id": 1, "name": "opossum"},
    {"id": CAR, "name": "car"},
    {"id": EMPTY, "name": "empty"},
]


def bbox_meta():
    """The bounding-box file: an animal, a car, an 'empty with a box', and an unannotated image."""
    return {
        "categories": CATS,
        "images": [image(n) for n in ("animal", "car", "boxed_empty", "unannotated")],
        "annotations": [
            ann("animal", 1, [10, 5, 20, 10]),
            ann("car", CAR, [0, 0, 50, 25]),
            ann("boxed_empty", EMPTY, [0, 0, 100, 50]),
        ],
    }


def test_neither_unannotated_nor_boxed_empty_frames_are_used_as_negatives():
    """Regression, from two real mistakes.

    'No annotation' means unknown (unboxed sibling frames of a burst, which contained animals),
    and 'empty with a box drawn on it' means ambiguous (partial animals, close-ups, blur).
    Using either as a clean negative made a good detector look like it raised false alarms on
    50-74% of 'empty' photos.
    """
    sample = build_sample(bbox_meta(), n=8, seed=0, empty_frac=0.5, car_frac=0.25, empties=[])
    assert {s["id"] for s in sample} == {"animal", "car"}


def test_verified_empties_come_from_the_image_level_labels():
    full = {
        "categories": CATS,
        "images": [image("blank1"), image("blank2"), image("animal"), image("other")],
        "annotations": [
            {"image_id": "blank1", "category_id": EMPTY},
            {"image_id": "blank2", "category_id": EMPTY},
            {"image_id": "animal", "category_id": 1},
        ],
    }
    blanks = empty_images(full)
    assert {b["id"] for b in blanks} == {"blank1", "blank2"}

    sample = build_sample(bbox_meta(), n=4, seed=0, empty_frac=0.5, car_frac=0.25, empties=blanks)
    by_id = {s["id"]: s for s in sample}
    assert {"blank1", "blank2"} <= set(by_id)
    assert by_id["blank1"]["gt"] == []


def test_an_empty_that_also_has_boxes_is_not_used_as_empty():
    conflicted = [image("animal")]  # labelled empty at image level, but the bbox file boxes it
    sample = build_sample(bbox_meta(), n=4, seed=0, empty_frac=0.5, car_frac=0.0,
                          empties=conflicted)
    (entry,) = [s for s in sample if s["id"] == "animal"]
    assert entry["gt"] != []  # it kept its boxes rather than being relabelled blank


def test_empties_are_spread_across_camera_locations():
    busy = [image(f"a{i}", location="busy") for i in range(50)]
    quiet = [image("q1", location="quiet"), image("q2", location="other")]
    sample = build_sample(bbox_meta(), n=8, seed=0, empty_frac=0.5, car_frac=0.0,
                          empties=busy + quiet)
    locations = {s["location"] for s in sample if not s["gt"]}
    assert locations == {"busy", "quiet", "other"}  # the busy camera cannot crowd out the rest


def test_ground_truth_boxes_are_normalised_and_labelled():
    sample = {s["id"]: s for s in build_sample(bbox_meta(), n=2, seed=0, empty_frac=0.0,
                                               car_frac=0.5)}
    (animal,) = sample["animal"]["gt"]
    assert animal["label"] == "animal" and animal["category"] == "opossum"
    assert animal["box"] == [0.1, 0.1, 0.3, 0.3]  # [x, y, w, h] pixels -> x1 y1 x2 y2 fractions
    assert sample["car"]["gt"][0]["label"] == "vehicle"


def test_the_sample_is_reproducible():
    args = dict(n=3, seed=7, empty_frac=0.3, car_frac=0.3, empties=[image("b1"), image("b2")])
    assert [s["id"] for s in build_sample(bbox_meta(), **args)] == [
        s["id"] for s in build_sample(bbox_meta(), **args)]
