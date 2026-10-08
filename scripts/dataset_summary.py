"""Summarise the data in the database: the numbers the paper and the data-quality notes quote.

    python scripts/dataset_summary.py [--out docs/metrics/dataset_summary.json]

Reads DATABASE_URL. Everything printed or written here is computed from the database at the time
of the run, with the date stamped into the output, so the figures can be reproduced.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from biodiv.core.settings import get_settings


def rows(conn, sql, params=None):
    return conn.execute(sql, params).fetchall()


def hotspot_concentration(conn, slug: str, cell: float) -> dict | None:
    result = conn.execute("select hotspot_cells(%s, %s, null)", (slug, cell)).fetchone()[0]
    counts = sorted((c["records"] for c in result["cells"]), reverse=True)
    if not counts:
        return None
    total = sum(counts)
    top = max(1, round(len(counts) * 0.1))
    return {
        "cell_degrees": result["cell"],
        "occupied_cells": len(counts),
        "records": total,
        "busiest_cell_records": counts[0],
        "share_in_top_10_percent_of_cells": round(sum(counts[:top]) / total, 3),
        "cells_with_one_record": sum(1 for c in counts if c == 1),
    }


def summarise(conn: psycopg.Connection) -> dict:
    out: dict = {"computed_at": datetime.now(UTC).isoformat(timespec="seconds")}

    out["parks"] = [
        {"slug": s, "name": n, "country": c, "area_km2": round(a)}
        for s, n, c, a in rows(conn, "select slug, name, country, st_area(geom::geography) / 1e6 "
                                     "from zones order by id")
    ]

    out["records_by_park_and_source"] = [
        {"park": z, "source": s, "records": n}
        for z, s, n in rows(conn, """
            select z.slug, s.name, count(*) from media_items m
            join zones z on z.id = m.zone_id join sources s on s.id = m.source_id
            group by 1, 2 order by 1, 2""")
    ]
    out["total_records"] = rows(conn, "select count(*) from media_items")[0][0]
    out["species_recorded"] = rows(conn, "select count(distinct species_id) from detections")[0][0]

    out["records_by_year"] = {
        z: {int(y): n for y, n in rows(conn, """
            select extract(year from d.captured_at), count(*) from detections d
            join zones zz on zz.id = d.zone_id where zz.slug = %s group by 1 order by 1""", (z,))}
        for z in [p["slug"] for p in out["parks"]]
    }

    # iNaturalist resumes after the last identifier and GBIF asks only for records changed since the
    # last run, so their runs do not overlap and can be summed. USGS NAS has no such cursor: every
    # run re-reads each park's counties. For it we take the most complete single scan per park, so
    # no record is counted twice.
    refused: dict[str, Counter] = {}
    fetched: Counter = Counter()
    nas_best: dict[str, tuple[int, dict]] = {}
    for source, notes, n_fetched, rejected in rows(conn, """
            select s.name, coalesce(r.notes, ''), r.fetched, r.rejected
            from ingestion_runs r join sources s on s.id = r.source_id
            where s.name <> 'GRIIS' and r.finished_at is not null"""):
        if source == "USGS NAS":
            scope = notes.split(": stored")[0]
            if ": stored" in notes and n_fetched > nas_best.get(scope, (-1, {}))[0]:
                nas_best[scope] = (n_fetched, rejected)
            continue
        fetched[source] += n_fetched
        refused.setdefault(source, Counter()).update(rejected)
    for n_fetched, rejected in nas_best.values():
        fetched["USGS NAS"] += n_fetched
        refused.setdefault("USGS NAS", Counter()).update(rejected)
    out["records_fetched_by_source"] = dict(fetched)
    out["records_refused_by_reason"] = {k: dict(v.most_common()) for k, v in refused.items()}

    out["invasive_records_by_park"] = {
        z: n for z, n in rows(conn, """
            select z.slug, count(*) from invasive_records r join zones z on z.id = r.zone_id
            group by 1 order by 1""")
    }
    out["invasive_species_by_park"] = {
        z: [
            {"species": sp, "common_name": cn, "records": n,
             "first_year": int(y0), "last_year": int(y1)}
            for sp, cn, n, y0, y1 in rows(conn, """
                select s.scientific_name, s.common_name, count(*),
                       extract(year from min(r.captured_at)), extract(year from max(r.captured_at))
                from invasive_records r join species s on s.id = r.species_id
                join zones zz on zz.id = r.zone_id where zz.slug = %s
                group by 1, 2 order by 3 desc, 1""", (z,))
        ]
        for z in [p["slug"] for p in out["parks"]]
    }

    out["hotspots"] = {}
    for p in out["parks"]:
        n = out["invasive_records_by_park"].get(p["slug"], 0)
        if n == 0:
            continue
        for cell in (0.01, 0.02, 0.05):
            h = hotspot_concentration(conn, p["slug"], cell)
            if h:
                out["hotspots"].setdefault(p["slug"], {})[str(cell)] = h

    out["analysis"] = {
        z: {
            "observations": rep["observations"],
            "species": rep["species"],
            "invasive_species": len(rep["invasive_species"]),
            "cooccurrence": {"status": rep["layers"]["cooccurrence"]["status"],
                             **{k: v for k, v in rep["layers"]["cooccurrence"]["detail"].items()
                                if isinstance(v, int | float)}},
            "trend": {"status": rep["layers"]["trend"]["status"],
                      **{k: v for k, v in rep["layers"]["trend"]["detail"].items()
                         if isinstance(v, int | float)}},
            "documented_findings": len(rep["layers"]["documented"]["findings"]),
        }
        for z, rep in rows(conn, "select z.slug, r.report from zone_reports r "
                                 "join zones z on z.id = r.zone_id order by z.id")
    }

    out["analysis_detail"] = {
        z: {
            "cooccurrence": rep["layers"]["cooccurrence"]["detail"],
            "trend": rep["layers"]["trend"]["detail"],
        }
        for z, rep in rows(conn, "select z.slug, r.report from zone_reports r "
                                 "join zones z on z.id = r.zone_id order by z.id")
    }

    out["alerts"] = [
        {"park": z, "species": sp, "severity": sev, "first_record": str(first)}
        for z, sp, sev, first in rows(conn, """
            select z.slug, s.scientific_name, a.severity, a.window_start::date
            from alerts a join zones z on z.id = a.zone_id join species s on s.id = a.species_id""")
    ]

    out["knowledge_base"] = {
        "findings": rows(conn, "select count(*) from impact_findings")[0][0],
        "findings_by_certainty": dict(
            rows(conn, "select certainty, count(*) from impact_findings group by 1")),
        "management_options": rows(conn, "select count(*) from mitigation_playbooks")[0][0],
        "management_by_method": dict(
            rows(conn, "select method, count(*) from mitigation_playbooks group by 1")),
        "species_with_findings": rows(
            conn, "select count(distinct invasive_species_id) from impact_findings")[0][0],
    }
    out["evidence_coverage"] = {
        z: {"invasive_species": sp, "with_cited_findings": wf, "with_cited_management": wm,
            "records": n, "records_of_species_with_findings": rf}
        for z, sp, wf, wm, n, rf in rows(conn, """
            select z.slug, count(distinct r.species_id),
                   count(distinct r.species_id) filter (where exists (
                       select 1 from impact_findings f where f.invasive_species_id = r.species_id)),
                   count(distinct r.species_id) filter (where exists (
                       select 1 from mitigation_playbooks p where p.species_id = r.species_id)),
                   count(*),
                   count(*) filter (where exists (
                       select 1 from impact_findings f where f.invasive_species_id = r.species_id))
            from invasive_records r join zones z on z.id = r.zone_id group by 1 order by 1""")
    }
    out["species_with_photo"] = rows(
        conn, "select count(*) from species where photo_url is not null")[0][0]
    out["database_bytes"] = rows(conn, "select pg_database_size(current_database())")[0][0]
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="docs/metrics/dataset_summary.json")
    args = p.parse_args(argv)
    if not get_settings().database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(get_settings().database_url) as conn:
        summary = summarise(conn)
    text = json.dumps(summary, indent=1, ensure_ascii=False) + "\n"
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"wrote {args.out}: {summary['total_records']} records, "
          f"{sum(summary['invasive_records_by_park'].values())} invasive records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
