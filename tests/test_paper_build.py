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
    for heading in ("## Abstract", "## 1. Introduction", "## 2. Methods", "## 3. Results",
                    "## 4. Observations", "## 5. Conclusion", "## References"):
        assert heading in built


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
