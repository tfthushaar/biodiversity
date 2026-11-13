# ruff: noqa: E501
"""The paper's references, its citations and its numbers: each rule fires on a bad input.

A check that has never been seen to fail gives false comfort, so every rule here is tried on a
case that breaks it as well as one that keeps it.
"""

import json
from pathlib import Path

import pytest

from biodiv.knowledge import references as R
from biodiv.knowledge.paper_text import (
    body_of,
    check_numbers,
    check_text,
    citations,
    literal_numbers,
    split_sentences,
)
from helpers import finding_row, knowledge_file, paper

ROOT = Path(__file__).resolve().parent.parent
REAL_REFS = json.loads((ROOT / "db" / "seeds" / "paper_references.json").read_text(encoding="utf-8"))
REAL_KB = json.loads((ROOT / "db" / "seeds" / "knowledge.json").read_text(encoding="utf-8"))
REAL_NUMBERS = json.loads((ROOT / "docs" / "paper_numbers.json").read_text(encoding="utf-8"))
TEMPLATE = (ROOT / "docs" / "paper_template.md").read_text(encoding="utf-8")


def article(**over):
    base = {
        "doi": "10.1234/ref.2020.1", "title": "A study of examples", "authors": "Smith, J.",
        "year": 2020, "journal": "Journal of Examples", "role": "claim",
        "quotes": ["Examples were found in forty of the sites that we surveyed"],
    }
    return {**base, **over}


def refs_with(**articles):
    return {
        "_policy": {"claim_min_year": 2014},
        "articles": articles or {"smith2020": article()},
        "resources": {"gbif": {"name": "GBIF.org", "mention": "GBIF", "year": 2026, "title": "GBIF data",
                               "url": "https://www.gbif.org", "kind": "data"}},
    }


# ----------------------------------------------------------------------------- the real files


def test_the_real_references_are_structurally_valid():
    evidence = {s["doi"].lower() for s in REAL_KB["sources"].values()}
    assert [str(p) for p in R.validate_references(REAL_REFS, evidence)] == []


def test_no_reference_is_a_preprint_and_every_claim_carries_quotes():
    for key, a in REAL_REFS["articles"].items():
        assert not a["doi"].startswith(("10.48550/", "10.1101/", "10.2139/", "10.5281/")), key
        if a["role"] == "claim":
            assert a["quotes"], key
            assert a["year"] >= REAL_REFS["_policy"]["claim_min_year"], key


def test_the_real_paper_numbers_each_come_from_where_they_say():
    literals = literal_numbers(TEMPLATE)
    assert [str(p) for p in check_numbers(literals, REAL_NUMBERS, ROOT)] == []
    assert len(literals) > 40  # the check is reading the paper, not an empty list


# ----------------------------------------------------------------------------- references


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda r: r["articles"]["smith2020"].update(doi="10.48550/arXiv.1706.04599"), "preprint server"),
        (lambda r: r["articles"]["smith2020"].update(doi="10.1101/2021.01.01.123"), "preprint server"),
        (lambda r: r["articles"]["smith2020"].update(journal="bioRxiv"), "preprint server"),
        (lambda r: r["articles"]["smith2020"].update(doi="not a doi"), "malformed doi"),
        (lambda r: r["articles"]["smith2020"].pop("title"), "missing title"),
        (lambda r: r["articles"]["smith2020"].update(role="decoration"), "role="),
        (lambda r: r["articles"]["smith2020"].update(quotes=[]), "needs a verbatim quote"),
        (lambda r: r["articles"]["smith2020"].update(quotes=["too short"]), "too short"),
        (lambda r: r["articles"]["smith2020"].update(year=2010), "policy accepts 2014"),
        (lambda r: r["articles"]["smith2020"].update(url="https://example.org"), "identified by its DOI"),
        (lambda r: r["articles"].update(copy=article()), "same doi"),
        (lambda r: r["articles"]["smith2020"].update(role="method"), "supports no claim"),
        (lambda r: r["resources"]["gbif"].update(url="http://example.org"), "https"),
        (lambda r: r["resources"]["gbif"].update(kind="opinion"), "kind="),
        (lambda r: r["resources"]["gbif"].pop("mention"), "missing mention"),
        (lambda r: r.pop("_policy"), "claim_min_year"),
    ],
)
def test_the_references_validation_catches_each_kind_of_mistake(mutate, fragment):
    refs = refs_with()
    mutate(refs)
    assert any(fragment in str(p) for p in R.validate_references(refs))


def test_a_good_registry_passes():
    assert R.validate_references(refs_with()) == []


def test_a_paper_already_in_the_evidence_base_is_cited_there():
    problems = R.validate_references(refs_with(), {"10.1234/ref.2020.1"})
    assert any("already in the evidence base" in str(p) for p in problems)


def test_a_method_or_dataset_article_needs_no_quote_and_no_recent_date():
    refs = refs_with(mann1945=article(doi="10.2307/1907187", authors="Mann, H.B.", year=1945,
                                      role="method", quotes=None))
    refs["articles"]["mann1945"].pop("quotes")
    assert R.validate_references(refs) == []


CROSSREF = {"type": "journal-article", "container-title": ["Journal of Examples"], "ISSN": ["1234-5678"],
            "title": ["A study of examples"], "author": [{"family": "Smith"}],
            "issued": {"date-parts": [[2020]]}}
OPENALEX = {"type": "article", "is_retracted": False, "primary_location": {"source": {"type": "journal"}},
            "title": "A study of examples", "publication_year": 2020, "doi": "https://doi.org/10.1234/ref.2020.1"}


def test_a_reference_is_held_to_the_indexes_like_the_evidence_base():
    refs = refs_with()
    a = refs["articles"]["smith2020"]
    assert R.check_reference("smith2020", a, CROSSREF, OPENALEX, refs) == []
    preprint = R.check_reference("smith2020", a, {**CROSSREF, "type": "posted-content"}, OPENALEX, refs)
    assert any("not one of" in str(p) for p in preprint)
    assert all(str(p).startswith("articles.smith2020") for p in preprint)


def test_a_conference_paper_or_book_chapter_is_accepted_but_not_a_report():
    refs = refs_with()
    a = refs["articles"]["smith2020"]
    for kind in ("proceedings-article", "book-chapter"):
        assert R.check_reference("s", a, {**CROSSREF, "type": kind}, {**OPENALEX, "type": kind}, refs) == []
    report = R.check_reference("s", a, {**CROSSREF, "type": "report"}, OPENALEX, refs)
    assert any("not one of" in str(p) for p in report)


def test_only_a_claim_must_be_recent():
    refs = refs_with()
    old = {**CROSSREF, "issued": {"date-parts": [[1971]]}}
    method = article(year=1971, role="method")
    claim = article(year=1971, role="claim")
    assert R.check_reference("m", method, old, OPENALEX | {"publication_year": 1971}, refs) == []
    assert any("before the policy" in str(p)
               for p in R.check_reference("c", claim, old, OPENALEX | {"publication_year": 1971}, refs))


def test_a_claim_quote_must_be_in_the_abstract():
    refs = refs_with()
    good = {"smith2020": ["Examples were found in forty of the sites that we surveyed, in all."]}
    assert R.find_reference_problems(refs, good) == []
    bad = {"smith2020": ["Something else entirely was found in this abstract instead of that"]}
    assert any("quote not found" in str(p) for p in R.find_reference_problems(refs, bad))
    assert any("no abstract" in str(p) for p in R.find_reference_problems(refs, {}))


def test_the_reference_list_is_generated_in_order_with_resources_apart():
    refs = refs_with(zeta=article(doi="10.1/z", authors="Zeta, A.", year=2019),
                     alpha=article(doi="10.1/a", authors="Alpha, B.", year=2021))
    text = R.render_references(refs)
    assert text.index("Alpha, B.") < text.index("Zeta, A.") < text.index("### Data, software and models")
    assert "GBIF.org (2026) GBIF data. https://www.gbif.org" in text
    assert "doi:10.1/a" in text


# ----------------------------------------------------------------------------- citations in the text


def test_citations_are_read_from_parentheses_only():
    text = ("Alien species keep rising (Seebens et al. 2017). Two papers agree (Negi et al. 2019; "
            "Willson 2017) and (Vélez and Tabak 2022) too. The park held 2010 to 2019 records "
            "(Figure 1) and (Spearman's rho = 0.35, 2019). Great Smoky Mountains 2010 is not one.")
    found, unread = citations(text)
    assert [(c.name, c.year) for c in found] == [
        ("Seebens", 2017), ("Negi", 2019), ("Willson", 2017), ("Vélez", 2022)]
    assert unread == []


def test_a_citation_the_reader_cannot_parse_is_reported():
    found, unread = citations("It is known (Smith 2020; see also the 2019 review).")
    assert [(c.name, c.year) for c in found] == [("Smith", 2020)]
    assert unread == ["see also the 2019 review"]


def test_sentences_do_not_break_at_et_al():
    assert len(split_sentences("Seebens et al. 2017 reported it. Another sentence follows.")) == 2


def evidence_with(quote="Density fell by 40% in 2019 after treatment began on four sites."):
    k = knowledge_file(findings=[finding_row(quotes=[quote])])
    k["sources"]["s"] = paper(authors="Author, A.B.", year=2021)
    return k


def text_problems(body, evidence=None, refs=None):
    return [str(p) for p in check_text(body, evidence or evidence_with(), refs or refs_with())]


FULL = "Smith 2020 and Author 2021 are cited. GBIF is named."


def test_every_citation_must_name_one_known_paper():
    ok = text_problems("It rose (Smith et al. 2020) and fell (Author et al. 2021). GBIF holds records.")
    assert ok == []
    unknown = text_problems("It rose (Jones et al. 2020). It rose (Smith et al. 2020). (Author 2021) GBIF.")
    assert any("cites Jones 2020" in p for p in unknown)
    wrong_year = text_problems("It rose (Smith et al. 2019). (Smith 2020) (Author 2021) GBIF.")
    assert any("cites Smith 2019" in p for p in wrong_year)


def test_a_name_and_year_that_fit_two_papers_are_refused():
    refs = refs_with(a=article(doi="10.1/a"), b=article(doi="10.1/b", title="Another"))
    problems = text_problems("(Smith 2020) (Author 2021) GBIF.", refs=refs)
    assert any("names more than one paper" in p for p in problems)


def test_an_accent_does_not_hide_a_paper():
    refs = refs_with(smith2020=article(), velez=article(doi="10.1/v", authors="Vélez, J.", year=2022))
    body = "(Velez et al. 2022) and (Vélez 2022) (Smith 2020) (Author 2021) GBIF."
    problems = text_problems(body, refs=refs)
    assert not any("cites" in p for p in problems)


def test_a_reference_nobody_cites_is_an_error():
    problems = text_problems("Only this is cited (Author et al. 2021). GBIF.")
    assert any("articles.smith2020" in p and "no sentence cites it" in p for p in problems)


def test_a_resource_the_text_never_names_is_an_error():
    problems = text_problems("(Smith 2020) (Author 2021) and nothing else.")
    assert any("resources.gbif" in p for p in problems)


def test_a_number_beside_a_citation_must_be_in_the_papers_quotes():
    ok = text_problems("Density fell by 40% on four sites (Author et al. 2021). (Smith 2020) GBIF.")
    assert ok == []
    bad = text_problems("Density fell by 45% on four sites (Author et al. 2021). (Smith 2020) GBIF.")
    assert any("['45']" in p for p in bad)


def test_table_figure_section_labels_and_dates_beside_a_citation_are_not_claims():
    body = "As Section 2.7 and Table 3 show (Author et al. 2021), measured on 8 October 2026. (Smith 2020) GBIF."
    assert text_problems(body) == []


def test_a_method_reference_may_sit_beside_any_number():
    refs = refs_with(mann1945=article(doi="10.2307/1907187", authors="Mann, H.B.", year=1945, role="method"))
    refs["articles"]["mann1945"].pop("quotes")
    body = "We ran 8 tests with the Mann-Kendall test (Mann 1945) on 12 years. (Author 2021) GBIF."
    assert text_problems(body, refs=refs) == []


def test_the_text_may_not_name_a_preprint_server():
    body = "(Smith 2020) (Author 2021) GBIF. A result is on arXiv. Another is a preprint."
    assert len([p for p in text_problems(body) if "preprint server" in p]) == 2
    allowed = "(Smith 2020) (Author 2021) GBIF. We did not use news, web pages or preprints."
    assert text_problems(allowed) == []


def test_the_reference_list_is_not_part_of_the_checked_body():
    text = "Body (Smith 2020) (Author 2021) GBIF.\n\n## References\n\nJones (2019) is only listed here."
    assert "Jones" not in body_of(text)


# ----------------------------------------------------------------------------- numbers


def test_numbers_in_the_prose_are_found_and_data_values_are_not():
    template = (
        "# 1. Title 2020\n\n## 2.1 Heading\n\n1. A list item with 7 in it\n\n"
        "We held {{TOTAL}} records, 84.9% were right, in 2,000 resamples (Efron 1979) on 8 October 2026 "
        "at 0.05 degrees with top-1 accuracy, Apache-2.0 and ViT-S/14 (Table 3, Figure 2, Section 2.8).\n\n"
        "<!-- table:records -->\n| 999 | 888 |\n<!-- /table -->\n\n![Figure 1. A map 77](docs/x.png)\n\n"
        "See <https://example.org/12345>.\n\n## References\n\nRef 1234 (1999) 55.\n"
    )
    assert literal_numbers(template) == ["7", "84.9%", "2,000", "0.05"]


def test_a_number_with_no_recorded_origin_fails():
    problems = [str(p) for p in check_numbers(["84.9%"], {"numbers": {}}, ROOT)]
    assert any("no recorded origin" in p for p in problems)


def test_a_registered_number_that_the_origin_does_not_hold_fails(tmp_path):
    (tmp_path / "m.json").write_text(json.dumps({"results": {"rate": 0.8490566, "n": 265, "ci": [0.801, 0.8872]}}))
    registry = {"numbers": {
        "84.9%": {"json": "m.json", "path": "results.rate"},
        "265": {"json": "m.json", "path": "results"},
        "80.1": {"json": "m.json", "path": "results.ci"},
        "88.7%": {"json": "m.json", "path": "results.ci"},
    }}
    assert check_numbers(["84.9%", "265", "80.1", "88.7%"], registry, tmp_path) == []
    wrong = {"numbers": {"85.9%": {"json": "m.json", "path": "results.rate"}}}
    assert any("is not a value at results.rate" in str(p) for p in check_numbers(["85.9%"], wrong, tmp_path))


def test_a_number_must_come_from_the_path_named_not_from_elsewhere_in_the_file(tmp_path):
    (tmp_path / "m.json").write_text(json.dumps({"weights": [0.2, 0.9], "chosen": {"threshold": 0.76}}))
    elsewhere = {"numbers": {"0.2": {"json": "m.json", "path": "chosen"}}}
    assert check_numbers(["0.2"], elsewhere, tmp_path)
    assert check_numbers(["0.76"], {"numbers": {"0.76": {"json": "m.json", "path": "chosen.threshold"}}}, tmp_path) == []
    missing_path = {"numbers": {"0.2": {"json": "m.json"}}}
    assert any("needs a path" in str(p) for p in check_numbers(["0.2"], missing_path, tmp_path))


def test_the_length_of_a_list_can_be_the_origin(tmp_path):
    (tmp_path / "m.json").write_text(json.dumps({"classes": ["a", "b", "c"]}))
    origin = {"json": "m.json", "path": "classes", "length": True}
    assert check_numbers(["3"], {"numbers": {"3": origin}}, tmp_path) == []
    problems = check_numbers(["4"], {"numbers": {"4": origin}}, tmp_path)
    assert any("has 3 items, not 4" in str(p) for p in problems)


def test_a_constant_in_the_code_must_equal_the_number():
    ok = {"numbers": {"20": {"code": "biodiv.analytics.impact:MIN_CELLS"}}}
    assert check_numbers(["20"], ok, ROOT) == []
    wrong = {"numbers": {"21": {"code": "biodiv.analytics.impact:MIN_CELLS"}}}
    assert any("is 20" in str(p) for p in check_numbers(["21"], wrong, ROOT))
    gone = {"numbers": {"20": {"code": "biodiv.analytics.impact:NO_SUCH_CONSTANT"}}}
    assert any("does not exist" in str(p) for p in check_numbers(["20"], gone, ROOT))


def test_a_document_must_contain_the_text_it_is_registered_for(tmp_path):
    (tmp_path / "d.md").write_text("The test set is 16 camera locations absent from training.")
    ok = {"numbers": {"16": {"doc": "d.md", "contains": "16 camera locations"}}}
    assert check_numbers(["16"], ok, tmp_path) == []
    gone = {"numbers": {"16": {"doc": "d.md", "contains": "16 trap sites"}}}
    assert any("does not contain" in str(p) for p in check_numbers(["16"], gone, tmp_path))


def test_an_external_figure_must_say_when_and_how_it_was_checked():
    bare = {"numbers": {"7": {"external": True}}}
    assert any("checked_on and how" in str(p) for p in check_numbers(["7"], bare, ROOT))
    done = {"numbers": {"7": {"external": True, "checked_on": "2026-11-13", "how": "queried the API"}}}
    assert check_numbers(["7"], done, ROOT) == []


def test_an_entry_for_a_number_no_longer_in_the_paper_is_removed():
    problems = [str(p) for p in check_numbers([], {"numbers": {"84.9%": {"doc": "x"}}}, ROOT)]
    assert any("no longer in the paper" in p for p in problems)


def test_an_entry_naming_no_origin_fails():
    assert any("names no origin" in str(p) for p in check_numbers(["7"], {"numbers": {"7": {}}}, ROOT))


@pytest.mark.parametrize(("literal", "stored", "ok"), [
    ("84.9%", 0.8490566, True), ("85%", 0.8490566, True), ("84.8%", 0.8490566, False),
    ("4.4", 0.0442, True), ("4.5", 0.0442, False), ("3.3%", 0.0329, True), ("0", 0.0, True),
    ("225", 225, True), ("226", 225, False), ("0.76", 0.76, True),
])
def test_a_stored_value_matches_the_number_typed_in_the_paper_to_the_places_given(literal, stored, ok, tmp_path):
    (tmp_path / "m.json").write_text(json.dumps({"v": stored}))
    entry = {"numbers": {literal: {"json": "m.json", "path": "v"}}}
    assert (check_numbers([literal], entry, tmp_path) == []) is ok


# ----------------------------------------------------------------------------- a single mistake in the real paper


def test_changing_one_figure_in_the_real_template_is_caught():
    broken = TEMPLATE.replace("84.9%", "94.9%")
    problems = [str(p) for p in check_numbers(literal_numbers(broken), REAL_NUMBERS, ROOT)]
    assert any("94.9%" in p for p in problems)
    assert any("84.9%" in p and "no longer in the paper" in p for p in problems)


def test_citing_an_unlisted_paper_in_the_real_template_is_caught():
    broken = TEMPLATE.replace("(Pagad et al. 2018)", "(Madeup et al. 2018)", 1)
    found = [str(p) for p in check_text(body_of(broken), REAL_KB, REAL_REFS)]
    assert any("cites Madeup 2018" in p for p in found)
    assert any("articles.pagad2018" in p and "no sentence cites it" in p for p in found)


def test_putting_a_number_beside_a_real_citation_that_its_quotes_lack_is_caught():
    broken = TEMPLATE.replace("(Seebens et al. 2017)", "(Seebens et al. 2017), at 98% of taxa", 1)
    found = [str(p) for p in check_text(body_of(broken), REAL_KB, REAL_REFS)]
    assert any("['98']" in p for p in found)


def test_the_real_evidence_has_no_preprint_among_its_sources():
    for key, source in REAL_KB["sources"].items():
        assert not source["doi"].startswith(("10.48550/", "10.1101/", "10.2139/", "10.5281/")), key
