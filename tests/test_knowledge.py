import copy
import json
from pathlib import Path

import psycopg
import pytest

from biodiv.knowledge.loader import KnowledgeError, load_knowledge
from biodiv.knowledge.verify import find_problems, normalise, validate_structure

KNOWLEDGE = Path(__file__).resolve().parent.parent / "db" / "seeds" / "knowledge.json"
REAL = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))


def sample():
    """A tiny valid knowledge file."""
    return {
        "verified_on": "2026-10-07",
        "sources": {"s": {"citation": "A. Author (2020) Title.", "url": "https://example.org/a",
                          "kind": "page"}},
        "playbooks": [{
            "species": "Lantana camara", "method": "mechanical", "summary": "Pull it up.",
            "effectiveness": "low", "evidence_strength": "low", "cost_tier": None, "risks": None,
            "failure_cases": None, "region_note": "Somewhere specific.", "source": "s",
            "quotes": ["Hand pulling is suitable for small areas of infestation."],
        }],
        "impact_findings": [{
            "species": "Lantana camara", "zone": "bandipur", "finding_type": "impact",
            "affected": "large mammals", "summary": "Fewer mammals where it grows.",
            "certainty": "preliminary", "region_note": "Bandipur.", "source": "s",
            "quotes": ["An inverse pattern with large mammals was observed in the area."],
        }],
    }


# -------------------------------------------------------------- the real file


def test_the_curated_file_is_structurally_valid():
    assert validate_structure(REAL) == []


def test_every_row_has_verbatim_evidence_and_says_where_it_comes_from():
    for row in REAL["playbooks"] + REAL["impact_findings"]:
        assert row["quotes"] and row["region_note"].strip()
        assert row["source"] in REAL["sources"]


def test_the_curated_file_carries_the_failures_and_disagreements_too():
    """A dashboard of only successes would teach the wrong lesson."""
    senna = [p for p in REAL["playbooks"] if p["species"] == "Senna spectabilis"]
    assert any(p["failure_cases"] for p in senna)
    assert {p["method"] for p in senna} >= {"mechanical", "integrated", "cultural"}
    # Weak evidence is labelled weak: only the randomised field experiment is rated high.
    high = [p for p in REAL["playbooks"] if p["evidence_strength"] == "high"]
    assert high and all(p["source"] == "nerlekar2021" for p in high)


def test_the_replacement_for_lantana_cautionary_tale_is_recorded():
    texts = " ".join(q for f in REAL["impact_findings"] for q in f["quotes"])
    assert "as a replacement for Lantana camara" in texts


# ------------------------------------------------------------- the verifier


@pytest.mark.parametrize(
    "variant",
    [
        "Mechanical clearing and hand pulling are suitable for small areas.",
        "MECHANICAL CLEARING AND HAND PULLING ARE SUITABLE FOR SMALL AREAS.",
        "Mechanical   clearing\nand hand pulling are suitable for small areas.",
        "Mechanical clearing and hand pulling are suitable for small areas.",
    ],
)
def test_typography_is_tolerated(variant):
    page = {"s": "Intro. Mechanical clearing and hand pulling are suitable for small areas. More. "
                 "An inverse pattern with large mammals was observed in the area."}
    k = sample()
    k["playbooks"][0]["quotes"] = [variant]
    assert find_problems(k, page) == []


def test_curly_quotes_and_dash_variants_match_their_plain_forms():
    assert normalise("it’s a “quote” – and‐hyphen") == \
        normalise("it's a \"quote\" - and-hyphen")


def test_a_changed_word_is_caught():
    page = {"s": "Hand pulling is suitable for small areas of infestation. "
                 "An inverse pattern with large mammals was observed in the area."}
    assert find_problems(sample(), page) == []
    k = sample()
    k["playbooks"][0]["quotes"] = ["Hand pulling is suitable for LARGE areas of infestation."]
    (problem,) = find_problems(k, page)
    assert "quote not found" in str(problem) and "playbooks[0]" in str(problem)


def test_a_source_with_no_fetched_text_is_a_problem_not_a_silent_pass():
    (p1, p2) = find_problems(sample(), {})
    assert "no text was fetched" in str(p1) and "no text was fetched" in str(p2)


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda k: k["playbooks"][0].update(quotes=[]), "no citation, no row"),
        (lambda k: k["playbooks"][0].update(quotes=["too short"]), "too short"),
        (lambda k: k["playbooks"][0].update(method="witchcraft"), "method"),
        (lambda k: k["playbooks"][0].update(source="nope"), "unknown source"),
        (lambda k: k["playbooks"][0].update(region_note=""), "region_note"),
        (lambda k: k["playbooks"][0].update(summary=" "), "empty summary"),
        (lambda k: k["impact_findings"][0].update(certainty="certain"), "certainty"),
        (lambda k: k["impact_findings"][0].update(affected=""), "affected"),
        (lambda k: k["sources"]["s"].update(kind="crossref"), "doi"),
        (lambda k: k["playbooks"].append(copy.deepcopy(k["playbooks"][0])), "duplicate"),
    ],
)
def test_structure_validation_catches_each_kind_of_mistake(mutate, fragment):
    k = sample()
    mutate(k)
    assert any(fragment in str(p) for p in validate_structure(k))


# -------------------------------------------------------------- the loader


def insert_species(conn, name):
    return conn.execute(
        "insert into species (scientific_name, kingdom) values (%s, 'Plantae') returning id",
        (name,)).fetchone()[0]


def test_loading_is_idempotent_and_stores_the_evidence(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        insert_species(conn, "Lantana camara")
        conn.commit()
        first = load_knowledge(conn, sample())
        again = load_knowledge(conn, sample())
        assert (first.playbooks, first.findings) == (1, 1) == (again.playbooks, again.findings)

        assert conn.execute("select count(*) from mitigation_playbooks").fetchone()[0] == 1
        assert conn.execute("select count(*) from impact_findings").fetchone()[0] == 1
        row = conn.execute(
            "select citation_text, citation_url, source_quotes, region_note, verified_on::text "
            "from mitigation_playbooks").fetchone()
        assert row[0].startswith("A. Author") and row[1] == "https://example.org/a"
        assert row[2] == ["Hand pulling is suitable for small areas of infestation."]
        assert row[3] == "Somewhere specific." and row[4] == "2026-10-07"
        zone = conn.execute("select z.slug from impact_findings f join zones z on z.id = f.zone_id"
                            ).fetchone()[0]
        assert zone == "bandipur"


def test_loading_updates_changed_text_rather_than_duplicating(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        insert_species(conn, "Lantana camara")
        conn.commit()
        load_knowledge(conn, sample())
        revised = sample()
        revised["impact_findings"][0]["summary"] = "A revised summary."
        revised["impact_findings"][0]["certainty"] = "observational"
        load_knowledge(conn, revised)
        assert conn.execute("select count(*) from impact_findings").fetchone()[0] == 1
        assert conn.execute("select summary, certainty from impact_findings").fetchone() == (
            "A revised summary.", "observational")


def test_a_missing_species_gives_an_actionable_error_and_loads_nothing(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        with pytest.raises(KnowledgeError, match="(?i)import the GRIIS checklist"):
            load_knowledge(conn, sample())
        conn.rollback()
        assert conn.execute("select count(*) from mitigation_playbooks").fetchone()[0] == 0


def test_an_unknown_zone_is_refused(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        insert_species(conn, "Lantana camara")
        conn.commit()
        k = sample()
        k["impact_findings"][0]["zone"] = "atlantis"
        with pytest.raises(KnowledgeError, match="atlantis"):
            load_knowledge(conn, k)


def test_an_invalid_file_is_never_loaded(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        insert_species(conn, "Lantana camara")
        conn.commit()
        k = sample()
        k["playbooks"][0]["quotes"] = []
        with pytest.raises(KnowledgeError, match="invalid"):
            load_knowledge(conn, k)


def test_prune_removes_only_loader_managed_rows_dropped_from_the_file(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        sid = insert_species(conn, "Lantana camara")
        conn.execute(  # a hand-entered row the loader must never touch
            "insert into mitigation_playbooks (species_id, method, description, citation_text, "
            "source_quotes, origin) values (%s, 'fire', 'by hand', 'Someone', '[\"q\"]', 'manual')",
            (sid,))
        conn.commit()
        both = sample()
        both["playbooks"].append({**copy.deepcopy(both["playbooks"][0]), "method": "chemical",
                                  "summary": "Spray it."})
        load_knowledge(conn, both)
        assert conn.execute("select count(*) from mitigation_playbooks").fetchone()[0] == 3

        stats = load_knowledge(conn, sample(), prune=True)  # the chemical row is gone from the file
        assert stats.pruned == 1
        methods = {r[0] for r in conn.execute("select method from mitigation_playbooks")}
        assert methods == {"mechanical", "fire"}  # the hand-entered row survived


def test_the_database_itself_refuses_a_playbook_without_quotes(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        sid = insert_species(conn, "Lantana camara")
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "insert into mitigation_playbooks (species_id, method, description, "
                "citation_text) values (%s, 'fire', 'x', 'cited')", (sid,))


def test_the_public_key_can_read_findings_but_not_change_them(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        insert_species(conn, "Lantana camara")
        conn.commit()
        load_knowledge(conn, sample())
        conn.execute("set local role anon")
        assert conn.execute("select count(*) from impact_findings").fetchone()[0] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("delete from impact_findings")
