import copy
import json
from pathlib import Path

import psycopg
import pytest

from biodiv.knowledge.loader import KnowledgeError, load_knowledge
from biodiv.knowledge.verify import (
    abstract_from_openalex,
    check_paper,
    citation_text,
    contains,
    find_problems,
    normalise,
    validate_structure,
)
from helpers import finding_row, knowledge_file, paper, playbook_row

KNOWLEDGE = Path(__file__).resolve().parent.parent / "db" / "seeds" / "knowledge.json"
REAL = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
POLICY = {"min_year": 2016, "blocked_venues": ["EDIS"]}


def sample():
    return knowledge_file(
        playbooks=[playbook_row()],
        findings=[finding_row(zone="bandipur", quotes=[
            "An inverse pattern with large mammals was observed in the area."])],
    )


# -------------------------------------------------------------- the real file


def test_the_curated_file_is_structurally_valid():
    assert validate_structure(REAL) == []


def test_every_source_is_a_recent_journal_article_with_a_doi():
    floor = REAL["_policy"]["min_year"]
    assert floor >= 2016
    assert REAL["sources"]
    for key, s in REAL["sources"].items():
        assert s["doi"].startswith("10."), key
        assert s["year"] >= floor, key
        assert not ({"url", "kind", "fetch_url"} & s.keys()), f"{key} is not a paper"


def test_every_row_has_verbatim_evidence_and_says_where_it_comes_from():
    for row in REAL["playbooks"] + REAL["impact_findings"]:
        assert row["quotes"] and row["region_note"].strip()
        assert row["source"] in REAL["sources"]


def test_no_row_carries_a_claim_that_is_not_in_a_paper():
    """Fields the papers do not state (our own ratings of cost, risk or effectiveness) are gone."""
    for p in REAL["playbooks"]:
        assert not ({"effectiveness", "evidence_strength", "cost_tier", "risks",
                     "failure_cases"} & p.keys())
        assert p["study_design"] in {"experimental", "observational", "review", "modelled"}


def test_the_file_records_null_and_negative_results_too():
    """A dashboard of only successes would teach the wrong lesson."""
    text = " ".join(q for r in REAL["playbooks"] + REAL["impact_findings"] for q in r["quotes"])
    assert "no evidence of" in text.lower() or "not promote" in text.lower()
    designs = {r["study_design"] for r in REAL["playbooks"]}
    assert "review" in designs and "experimental" in designs


def test_the_files_own_text_follows_the_house_style():
    raw = KNOWLEDGE.read_text(encoding="utf-8")
    assert "—" not in raw
    for r in REAL["playbooks"] + REAL["impact_findings"]:
        assert "not only" not in r["summary"].lower()


# ------------------------------------------------------------- the verifier


@pytest.mark.parametrize(
    "variant",
    [
        "Mechanical clearing and hand pulling are suitable for small areas.",
        "MECHANICAL CLEARING AND HAND PULLING ARE SUITABLE FOR SMALL AREAS.",
        "Mechanical   clearing\nand hand pulling are suitable for small areas.",
        "Mechanical clearing and hand pulling are suitable for small areas.",
        "Mechanicalclearing and hand pulling are suitable for small areas.",
    ],
)
def test_typography_and_spacing_are_tolerated(variant):
    abstract = ("Intro. Mechanical clearing and hand pulling are suitable for small areas. More. "
                "An inverse pattern with large mammals was observed in the area.")
    k = sample()
    k["playbooks"][0]["quotes"] = [variant]
    assert find_problems(k, {"s": [abstract]}) == []


def test_curly_quotes_dash_variants_accents_and_decimal_dots_match_their_plain_forms():
    assert normalise("it’s a “quote” – and‐hyphen") == normalise("it's a \"quote\" - and-hyphen")
    abstract = "Invader-experienced natives were naïve"
    assert contains(abstract, "invader-experienced natives were naive")
    assert contains("a score of 4·6 on the scale", "a score of 4.6 on the scale")


def test_a_changed_word_or_number_is_caught():
    abstract = ("Hand pulling is suitable for small areas of infestation. "
                "An inverse pattern with large mammals was observed in the area.")
    assert find_problems(sample(), {"s": [abstract]}) == []
    k = sample()
    k["playbooks"][0]["quotes"] = ["Hand pulling is suitable for LARGE areas of infestation."]
    (problem,) = find_problems(k, {"s": [abstract]})
    assert "quote not found" in str(problem) and "playbooks[0]" in str(problem)
    # A number is wording too: 1.5 must not pass for 15.
    assert not contains("a score of 15 on the scale", "a score of 1.5 on the scale")


def test_a_paper_with_no_abstract_cannot_be_quoted():
    (p1, p2) = find_problems(sample(), {"s": []})
    assert "nothing can be quoted" in str(p1) and "nothing can be quoted" in str(p2)
    (p3, _) = find_problems(sample(), {})
    assert "no abstract was found" in str(p3)


def test_a_quote_may_come_from_either_services_abstract():
    k = sample()
    k["playbooks"][0]["quotes"] = ["Hand pulling is suitable for small areas of infestation."]
    k["impact_findings"][0]["quotes"] = ["An inverse pattern with large mammals was observed here."]
    texts = {"s": ["Hand pulling is suitable for small areas of infestation.",
                   "An inverse pattern with large mammals was observed here."]}
    assert find_problems(k, texts) == []


def test_openalex_abstracts_are_rebuilt_in_word_order():
    assert abstract_from_openalex({"world": [1], "Hello": [0], "again": [2]}) == "Hello world again"
    assert abstract_from_openalex(None) == ""


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda k: k["playbooks"][0].update(quotes=[]), "no citation, no row"),
        (lambda k: k["playbooks"][0].update(quotes=["too short"]), "too short"),
        (lambda k: k["playbooks"][0].update(method="witchcraft"), "method"),
        (lambda k: k["playbooks"][0].update(study_design="hunch"), "study_design"),
        (lambda k: k["playbooks"][0].update(source="nope"), "unknown source"),
        (lambda k: k["playbooks"][0].update(region_note=""), "region_note"),
        (lambda k: k["playbooks"][0].update(summary=" "), "empty summary"),
        (lambda k: k["impact_findings"][0].update(certainty="unverified_concern"), "certainty"),
        (lambda k: k["impact_findings"][0].update(certainty="preliminary"), "certainty"),
        (lambda k: k["impact_findings"][0].update(affected=""), "affected"),
        (lambda k: k["playbooks"].append(copy.deepcopy(k["playbooks"][0])), "duplicate"),
        # Only papers can be cited.
        (lambda k: k["sources"]["s"].update(url="https://example.org/a"), "only peer-reviewed"),
        (lambda k: k["sources"]["s"].update(kind="page"), "only peer-reviewed"),
        (lambda k: k["sources"]["s"].pop("doi"), "missing doi"),
        (lambda k: k["sources"]["s"].update(doi="not-a-doi"), "malformed doi"),
        (lambda k: k["sources"]["s"].update(year=2012), "2016 onward"),
        (lambda k: k["sources"]["s"].update(journal="EDIS"), "not a research journal"),
        (lambda k: k["sources"].update(extra=paper(doi="10.1234/extra")), "cited by no row"),
        (lambda k: k.pop("_policy"), "min_year"),
    ],
)
def test_structure_validation_catches_each_kind_of_mistake(mutate, fragment):
    k = sample()
    mutate(k)
    assert any(fragment in str(p) for p in validate_structure(k))


CROSSREF = {
    "type": "journal-article", "container-title": ["Journal of Examples"], "ISSN": ["1234-5678"],
    "title": ["Invasive plants in tropical forests"], "author": [{"family": "Author"}],
    "issued": {"date-parts": [[2021, 3]]},
}
OPENALEX = {"type": "article", "is_retracted": False,
            "primary_location": {"source": {"type": "journal"}}}


def problems_with(crossref=None, openalex=OPENALEX, source=None):
    record = {**CROSSREF, **(crossref or {})}
    return [str(p) for p in check_paper("s", source or paper(), record, openalex, POLICY)]


def test_a_matching_journal_article_passes():
    assert problems_with() == []


@pytest.mark.parametrize(
    ("crossref", "openalex", "fragment"),
    [
        ({"type": "posted-content"}, OPENALEX, "not a journal article"),
        ({"type": "report"}, OPENALEX, "not a journal article"),
        ({"subtype": "preprint"}, OPENALEX, "preprint"),
        ({"container-title": ["EDIS"]}, OPENALEX, "not a research journal"),
        ({"ISSN": []}, OPENALEX, "no ISSN"),
        ({"author": []}, OPENALEX, "no authors"),
        ({"title": ["A different title"]}, OPENALEX, "title differs"),
        ({"container-title": ["Another Journal"]}, OPENALEX, "journal differs"),
        ({"issued": {"date-parts": [[2012]]}}, OPENALEX, "year 2021 is not in the record"),
        ({"author": [{"family": "Someone Else"}]}, OPENALEX, "first author differs"),
        ({"updated-by": [{"type": "retraction"}]}, OPENALEX, "carries a notice"),
        ({"updated-by": [{"type": "expression_of_concern"}]}, OPENALEX, "carries a notice"),
        ({}, {**OPENALEX, "is_retracted": True}, "retracted"),
        ({}, {**OPENALEX, "primary_location": {"source": {"type": "repository"}}}, "not a journal"),
        ({}, {**OPENALEX, "type": "preprint"}, "OpenAlex types it"),
    ],
)
def test_the_paper_check_rejects_what_is_not_a_published_matching_paper(
    crossref, openalex, fragment
):
    assert any(fragment in p for p in problems_with(crossref, openalex))


def test_a_doi_crossref_does_not_know_is_rejected():
    (p,) = [str(x) for x in check_paper("s", paper(), None, None, POLICY)]
    assert "no record" in p


def test_a_paper_older_than_the_policy_year_is_rejected():
    old = {"issued": {"date-parts": [[2012]]}}
    assert any("before the policy" in p
               for p in problems_with(old, source=paper(year=2012)))


def test_a_footnote_marker_in_the_journals_title_is_the_only_difference_allowed():
    assert problems_with({"title": ["Invasive plants in tropical forests1"]}) == []
    assert any("title differs" in p
               for p in problems_with({"title": ["Invasive plants in tropical forests today"]}))


def test_the_reference_shown_on_the_dashboard_is_built_from_the_verified_fields():
    assert citation_text(paper()) == (
        "Author, A.B. (2021) Invasive plants in tropical forests. Journal of Examples 12: 1-10. "
        "doi:10.1234/example.2021.001")


# -------------------------------------------------------------- the loader


def insert_species(conn, name):
    return conn.execute(
        "insert into species (scientific_name, kingdom) values (%s, 'Plantae') returning id",
        (name,)).fetchone()[0]


def test_loading_is_idempotent_and_stores_the_paper_and_the_evidence(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        insert_species(conn, "Lantana camara")
        conn.commit()
        first = load_knowledge(conn, sample())
        again = load_knowledge(conn, sample())
        assert (first.playbooks, first.findings) == (1, 1) == (again.playbooks, again.findings)

        assert conn.execute("select count(*) from mitigation_playbooks").fetchone()[0] == 1
        assert conn.execute("select count(*) from impact_findings").fetchone()[0] == 1
        row = conn.execute(
            "select citation_text, citation_url, citation_doi, citation_year, citation_journal, "
            "study_design, source_quotes, region_note, verified_on::text "
            "from mitigation_playbooks").fetchone()
        assert row[0].startswith("Author, A.B. (2021)")
        assert row[1] == "https://doi.org/10.1234/example.2021.001"
        assert row[2:6] == ("10.1234/example.2021.001", 2021, "Journal of Examples", "experimental")
        assert row[6] == ["Hand pulling is suitable for small areas of infestation."]
        assert row[7] == "A forest in southern India." and row[8] == "2026-10-07"
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
        revised["impact_findings"][0]["certainty"] = "experimental"
        load_knowledge(conn, revised)
        assert conn.execute("select count(*) from impact_findings").fetchone()[0] == 1
        assert conn.execute("select summary, certainty from impact_findings").fetchone() == (
            "A revised summary.", "experimental")


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


@pytest.mark.parametrize(
    "mutate",
    [
        lambda k: k["playbooks"][0].update(quotes=[]),
        lambda k: k["sources"]["s"].update(url="https://example.org/a", kind="page"),
        lambda k: k["sources"]["s"].update(year=2010),
        lambda k: k["sources"]["s"].pop("doi"),
    ],
)
def test_an_invalid_file_is_never_loaded(ingest_db_url, mutate):
    with psycopg.connect(ingest_db_url) as conn:
        insert_species(conn, "Lantana camara")
        conn.commit()
        k = sample()
        mutate(k)
        with pytest.raises(KnowledgeError, match="invalid"):
            load_knowledge(conn, k)
        assert conn.execute("select count(*) from mitigation_playbooks").fetchone()[0] == 0


def hand_entered(conn, species_id, **over):
    row = {"species_id": species_id, "method": "fire", "description": "by hand",
           "study_design": "review", "citation_text": "Someone (2020)",
           "citation_url": "https://doi.org/10.1234/hand", "citation_doi": "10.1234/hand",
           "citation_year": 2020, "citation_journal": "Journal", "source_quotes": '["q"]',
           "origin": "manual", **over}
    marks = ", ".join(["%s"] * len(row))
    conn.execute(f"insert into mitigation_playbooks ({', '.join(row)}) values ({marks})",
                 list(row.values()))


def test_prune_removes_only_loader_managed_rows_dropped_from_the_file(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        sid = insert_species(conn, "Lantana camara")
        hand_entered(conn, sid)  # a row the loader must never touch
        conn.commit()
        both = sample()
        both["playbooks"].append(playbook_row(method="chemical", summary="Spraying it."))
        load_knowledge(conn, both)
        assert conn.execute("select count(*) from mitigation_playbooks").fetchone()[0] == 3

        stats = load_knowledge(conn, sample(), prune=True)  # the chemical row is gone from the file
        assert stats.pruned == 1
        methods = {r[0] for r in conn.execute("select method from mitigation_playbooks")}
        assert methods == {"mechanical", "fire"}  # the hand-entered row survived


# ------------------------------------------------- the database enforces the rule itself


def test_the_database_refuses_a_playbook_without_quotes(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        sid = insert_species(conn, "Lantana camara")
        with pytest.raises(psycopg.errors.CheckViolation):
            hand_entered(conn, sid, source_quotes="[]")


@pytest.mark.parametrize(
    ("override", "error"),
    [
        ({"citation_doi": None}, psycopg.errors.NotNullViolation),
        ({"citation_doi": "not-a-doi"}, psycopg.errors.CheckViolation),
        ({"citation_year": 2012}, psycopg.errors.CheckViolation),
        ({"citation_year": None}, psycopg.errors.NotNullViolation),
        ({"citation_journal": "  "}, psycopg.errors.CheckViolation),
        ({"citation_url": None}, psycopg.errors.NotNullViolation),
        ({"study_design": "hunch"}, psycopg.errors.CheckViolation),
        ({"study_design": None}, psycopg.errors.NotNullViolation),
    ],
)
def test_the_database_refuses_a_playbook_that_is_not_backed_by_a_recent_paper(
    ingest_db_url, override, error
):
    with psycopg.connect(ingest_db_url) as conn:
        sid = insert_species(conn, "Lantana camara")
        with pytest.raises(error):
            hand_entered(conn, sid, **override)


def test_the_database_refuses_a_finding_without_a_recent_paper(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        sid = insert_species(conn, "Lantana camara")
        conn.commit()
        base = {"invasive_species_id": sid, "finding_type": "impact", "affected": "x",
                "summary": "y", "certainty": "observational", "region_note": "z",
                "source_quotes": '["q"]', "citation_text": "c", "citation_url": "u",
                "citation_doi": "10.1234/x", "citation_year": 2020, "citation_journal": "J"}

        def insert(**over):
            row = {**base, **over}
            conn.execute(f"insert into impact_findings ({', '.join(row)}) "
                         f"values ({', '.join(['%s'] * len(row))})", list(row.values()))

        for over, error in (({"citation_doi": None}, psycopg.errors.NotNullViolation),
                            ({"citation_doi": "web page"}, psycopg.errors.CheckViolation),
                            ({"citation_year": 2009}, psycopg.errors.CheckViolation),
                            ({"certainty": "unverified_concern"}, psycopg.errors.CheckViolation),
                            ({"certainty": "preliminary"}, psycopg.errors.CheckViolation)):
            with pytest.raises(error):
                insert(**over)
            conn.rollback()


def test_the_public_key_sees_only_rows_whose_quotes_were_verified(ingest_db_url):
    with psycopg.connect(ingest_db_url) as conn:
        insert_species(conn, "Lantana camara")
        conn.commit()
        load_knowledge(conn, sample())
        load_knowledge(conn, knowledge_file(
            verified_on=None, playbooks=[playbook_row(method="chemical", summary="Spraying.")],
            findings=[finding_row(affected="grass", summary="Less grass.")]))
        assert conn.execute("select count(*) from impact_findings").fetchone()[0] == 2  # owner
        conn.execute("set local role anon")
        assert conn.execute("select count(*) from impact_findings").fetchone()[0] == 1
        assert conn.execute("select count(*) from mitigation_playbooks").fetchone()[0] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("delete from impact_findings")
