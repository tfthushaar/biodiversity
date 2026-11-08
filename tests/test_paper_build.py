"""The paper is built from the data summary, so its numbers cannot drift from the data."""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture
def built(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)  # the scripts read docs/ and db/ relative to the repository root
    import build_paper

    out = tmp_path / "paper.md"
    build_paper.build("docs/paper_template.md", str(out))
    return out.read_text(encoding="utf-8")


def test_every_token_is_filled_and_every_table_is_present(built):
    assert "{{" not in built and "}}" not in built
    assert built.count("<!-- table:") == built.count("<!-- /table -->") >= 6
    assert "| Park |" in built  # tables were generated, not left empty


def test_the_paper_has_the_sections_a_paper_needs(built):
    for heading in ("## Abstract", "## 1. Introduction", "## 2. Data and methods", "## 3. Results",
                    "## 4. Discussion", "## 5. Conclusion", "## References"):
        assert heading in built


def test_the_paper_describes_its_findings_and_not_how_the_platform_is_built(built):
    """A reader of the paper needs the study, and none of the file paths, commands or services."""
    words = ("scripts/", "python -m", "GitHub Actions", "Supabase", "Vercel", "Render",
             "free tier", "free-tier", "ONNX", "migration", "`")
    for developer_word in words:
        assert developer_word not in built, f"developer detail in the paper: {developer_word!r}"


def test_the_evidence_base_in_the_paper_is_the_verified_knowledge_file(built):
    import json

    kb = json.loads((ROOT / "db" / "seeds" / "knowledge.json").read_text(encoding="utf-8"))
    assert f"{len(kb['sources'])} peer-reviewed papers" in built
    refs = built.split("### Papers in the evidence base", 1)[1]
    for source in kb["sources"].values():
        assert f"doi:{source['doi']}" in refs
    assert "species profiles, fact sheets" in built  # named as sources that were not used


def test_documents_contain_no_em_dashes():
    docs = [ROOT / "README.md", ROOT / "docs" / "paper_template.md", *(ROOT / "docs").glob("*.md")]
    for path in docs:
        assert "—" not in path.read_text(encoding="utf-8"), f"em dash in {path.name}"


def test_cited_works_in_the_text_are_in_the_reference_list(built):
    refs = built.split("## References", 1)[1]
    body = built.split("## References")[0]
    pattern = r"([A-Z][a-zA-Z-]+) et al\. \((?:19|20)\d\d\)|([A-Z][a-zA-Z-]+) et al\. (?:19|20)\d\d"
    cited = set(re.findall(pattern, body))
    names = {a or b for a, b in cited}
    missing = sorted(n for n in names if n not in refs)
    assert not missing, f"cited without a reference entry: {missing}"


# ------------------------------------------------------- the claim guard and its helpers


@pytest.fixture
def builder(monkeypatch):
    monkeypatch.chdir(ROOT)
    import build_paper

    return build_paper


def test_the_headline_numbers_are_the_snapshots(built, builder):
    S = builder.S
    assert f"{S['total_records']:,} records" in built
    assert f"{sum(S['invasive_records_by_park'].values()):,} are records" in built


def test_the_guard_passes_on_the_stored_snapshot(builder):
    builder.check_claims()  # raises SystemExit when the data no longer supports a sentence


@pytest.mark.parametrize(("path", "value", "claim"), [
    # The Everglades trend stops being significant, so "survives a correction" is no longer true.
    (("analysis_detail", "everglades", "trend", "invasive_per_observation", "p_value"), 0.2,
     "Everglades invasive trend rose"),
    # An iNaturalist record from 2020 appears, so "the park holds none after 2019" is false.
    (("records_by_period_and_source", "everglades", "2020 on", "iNaturalist"), 40,
     "no iNaturalist record dated 2020 or later"),
    # A species without a paper is recorded.
    (("invasive_species_by_park", "serengeti"), [{"species": "Unstudied weed", "records": 3,
                                                  "common_name": None, "first_year": 2020,
                                                  "last_year": 2020}],
     "Every invasive species recorded has a paper"),
])
def test_the_guard_stops_the_build_when_the_data_no_longer_supports_a_sentence(
        builder, monkeypatch, path, value, claim):
    node = builder.S
    for key in path[:-1]:
        node = node[key]
    monkeypatch.setitem(node, path[-1], value)
    with pytest.raises(SystemExit) as stopped:
        builder.check_claims()
    assert claim in str(stopped.value)


def test_p_values_carry_their_own_operator(builder):
    assert builder.p_value(1e-13) == "p < 0.001"
    assert builder.p_value(0.009) == "p = 0.009"
    assert builder.p_value(0.2) == "p = 0.20"


def test_the_gbif_source_reads_the_same_under_its_former_name(monkeypatch):
    monkeypatch.chdir(ROOT)
    import paper_tables as T

    old = {"records_by_park_and_source": [{"park": "x", "source": "GBIF occurrences"}],
           "records_refused_by_reason": {"GBIF occurrences": {"no_date": 1}}}
    new = T.renamed(old)
    assert new["records_by_park_and_source"][0]["source"] == "GBIF specimens"
    assert list(new["records_refused_by_reason"]) == ["GBIF specimens"]


def test_phrases_read_naturally_for_none_one_and_many(monkeypatch):
    monkeypatch.chdir(ROOT)
    import paper_tables as T

    assert [T.count_phrase(k) for k in (0, 1, 6)] == ["no records", "1 record", "6 records"]
    assert T.of_phrase(835, 835) == "all 835" and T.of_phrase(471, 650) == "471 of the 650"
    assert T.listing(["a"]) == "a" and T.listing(["a", "b", "c"]) == "a, b and c"


def test_the_paper_leaves_out_what_the_rules_removed(built):
    for stale in ("IUCN", "eBird", "0.02 degrees", "nearly half", "does not survive a correction"):
        assert stale not in built, f"out-of-date wording in the paper: {stale!r}"


def test_the_paper_states_the_limit_on_recent_inaturalist_records(built, builder):
    assert "Three parks lack recent iNaturalist records." in built
    for park, latest in builder.capped_parks().items():
        assert builder.month(latest) in built, park
