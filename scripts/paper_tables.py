# ruff: noqa: E501
"""Print the results tables of paper.md from docs/metrics/dataset_summary.json.

    python scripts/paper_tables.py                  # print every table
    python scripts/paper_tables.py --inject paper.md  # refresh the tables inside paper.md

Run scripts/dataset_summary.py first. The tables are generated, not typed, so the paper's numbers
match the data.
"""

from __future__ import annotations

import json
from pathlib import Path

S = json.loads(Path("docs/metrics/dataset_summary.json").read_text(encoding="utf-8"))
NAMES = {p["slug"]: p["name"].replace(" National Park", "") for p in S["parks"]}
COUNTRY = {p["slug"]: p["country"] for p in S["parks"]}
AREA = {p["slug"]: p["area_km2"] for p in S["parks"]}
ORDER = [p["slug"] for p in S["parks"]]


def n(x: int | float) -> str:
    return f"{x:,.0f}"


def table(head: list[str], rows: list[list[str]], align: str | None = None) -> str:
    align = align or "l" + "r" * (len(head) - 1)
    rule = "|" + "|".join(":---:" if a == "c" else "---:" if a == "r" else "---" for a in align) + "|"
    lines = ["| " + " | ".join(head) + " |", rule]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def records_table() -> str:
    by: dict[str, dict[str, int]] = {}
    for r in S["records_by_park_and_source"]:
        by.setdefault(r["park"], {})[r["source"]] = r["records"]
    sources = ["iNaturalist", "GBIF occurrences", "USGS NAS"]
    rows = []
    for slug in ORDER:
        v = by.get(slug, {})
        rows.append([NAMES[slug], COUNTRY[slug], n(AREA[slug])] + [n(v.get(s, 0)) if s in v else "-" for s in sources]
                    + [n(sum(v.values()))])
    total = [sum(by.get(slug, {}).get(s, 0) for slug in ORDER) for s in sources]
    rows.append(["**Total**", "", ""] + [n(t) for t in total] + [n(sum(total))])
    return table(["Park", "Country", "Area (km2)", "iNaturalist", "GBIF", "USGS NAS", "Records"], rows, "llrrrrr")


def invasive_table() -> str:
    rows = []
    for slug in ORDER:
        inv = S["invasive_records_by_park"].get(slug, 0)
        recs = sum(r["records"] for r in S["records_by_park_and_source"] if r["park"] == slug)
        spp = len(S["invasive_species_by_park"].get(slug, []))
        rows.append([NAMES[slug], n(recs), n(inv), f"{100 * inv / recs:.1f}%" if recs else "-", n(spp)])
    return table(["Park", "Records", "Invasive records", "Share", "Invasive species"], rows)


def top_species(k: int = 5) -> str:
    rows = []
    for slug in ORDER:
        for sp in S["invasive_species_by_park"].get(slug, [])[:k]:
            common = f" ({sp['common_name']})" if sp["common_name"] else ""
            years = str(sp["first_year"]) if sp["first_year"] == sp["last_year"] else f"{sp['first_year']} to {sp['last_year']}"
            rows.append([NAMES[slug], f"*{sp['species']}*{common}", n(sp["records"]), years])
    return table(["Park", "Species", "Records", "Years"], rows, "llrl")


def hotspot_table(cell: str = "0.02") -> str:
    rows = []
    for slug in ORDER:
        h = S["hotspots"].get(slug, {}).get(cell)
        if h:
            rows.append([NAMES[slug], n(h["records"]), n(h["occupied_cells"]), n(h["busiest_cell_records"]),
                         f"{100 * h['share_in_top_10_percent_of_cells']:.0f}%", n(h["cells_with_one_record"])])
    return table(["Park", "Invasive records", "Occupied cells", "Busiest cell", "Share in busiest 10% of cells", "Cells with one record"], rows)


def analysis_table() -> str:
    rows = []
    for slug in ORDER:
        a = S["analysis"].get(slug)
        if not a:
            continue
        co, tr = a["cooccurrence"], a["trend"]
        rows.append([
            NAMES[slug],
            co["status"], f"{n(co.get('cells_usable', 0))} ({n(co.get('required_cells', 20))} needed)",
            tr["status"], f"{n(tr.get('invasive_records', 0))} ({n(tr.get('required_invasive_records', 30))} needed)",
            f"{n(tr.get('usable_years', 0))} ({n(tr.get('required_years', 6))} needed)",
        ])
    return table(["Park", "Co-occurrence", "Usable cells", "Trend", "Invasive records", "Usable years"], rows, "llllll")


def refused_table() -> str:
    reasons: dict[str, dict[str, int]] = {}
    for source, d in S["records_refused_by_reason"].items():
        for reason, count in d.items():
            reasons.setdefault(reason, {})[source] = count
    sources = list(S["records_refused_by_reason"])
    order = sorted(reasons, key=lambda r: -sum(reasons[r].values()))
    rows = [[r.replace("_", " ")] + [n(reasons[r].get(s, 0)) for s in sources] for r in order]
    return table(["Reason"] + sources, rows)


def coverage_table() -> str:
    rows = []
    for slug in ORDER:
        c = S["evidence_coverage"].get(slug)
        if not c:
            continue
        rows.append([NAMES[slug], n(c["invasive_species"]), n(c["with_cited_findings"]), n(c["with_cited_management"]),
                     f"{100 * c['records_of_species_with_findings'] / c['records']:.0f}%"])
    return table(["Park", "Invasive species recorded", "With a cited finding", "With cited management", "Records covered by a finding"], rows)


def trend_pair(slug: str) -> tuple[dict, dict]:
    """(invasive, native) Mann-Kendall results for a park, from the stored analysis."""
    d = S["analysis_detail"][slug]["trend"]
    return d["invasive_per_observation"], d["native_per_observation"]


TABLES = {
    "records": records_table,
    "invasive": invasive_table,
    "top_species": top_species,
    "concentration": hotspot_table,
    "analysis": analysis_table,
    "refused": refused_table,
    "coverage": coverage_table,
}


def inject(path: str) -> int:
    """Replace each block between <!-- table:NAME --> and <!-- /table --> with a fresh table."""
    import re

    text = Path(path).read_text(encoding="utf-8")
    count = 0

    def fill(m: re.Match) -> str:
        nonlocal count
        count += 1
        name = m.group(1)
        return "<!-- table:" + name + " -->" + chr(10) + TABLES[name]() + chr(10) + "<!-- /table -->"

    text = re.sub(r"<!-- table:(\w+) -->.*?<!-- /table -->", fill, text, flags=re.S)
    Path(path).write_text(text, encoding="utf-8")
    return count


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "--inject":
        print(f"updated {inject(sys.argv[2])} tables in {sys.argv[2]}")
        raise SystemExit(0)
    print("## Records by park and source\n" + records_table())
    print("\n## Invasive records\n" + invasive_table())
    print("\n## Most recorded invasive species\n" + top_species())
    print("\n## Concentration (0.02 degree squares)\n" + hotspot_table())
    print("\n## Analysis readiness\n" + analysis_table())
    print("\n## Records refused\n" + refused_table())
    print("\n## Evidence coverage\n" + coverage_table())
    kb = S["knowledge_base"]
    print(f"\nKnowledge base: {kb['findings']} findings {kb['findings_by_certainty']}, "
          f"{kb['management_options']} management options {kb['management_by_method']}, "
          f"{kb['species_with_findings']} species with findings; species with photo {S['species_with_photo']}")
    print(f"Alerts: {S['alerts']}\nDatabase: {S['database_bytes'] / 1e6:.1f} MB; computed {S['computed_at']}")
