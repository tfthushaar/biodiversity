"""Refresh the rollups, raise early-detection alerts, and report each zone's three layers.

    python -m biodiv.workers.analyse [--zone bandipur] [--json report.json]

Safe to run as often as you like: rollups are rebuilt and alerts are updated in place.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg

from biodiv.analytics.alerts import first_record_alerts, upsert_alerts
from biodiv.analytics.impact import zone_report
from biodiv.core.settings import get_settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--zone", action="append", help="zone slug; repeat for several (default: all)")
    p.add_argument("--json", type=Path, help="write the full reports here")
    args = p.parse_args(argv)
    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("select refresh_rollups()")
        raised = upsert_alerts(conn, first_record_alerts(conn))
        slugs = args.zone or [r[0] for r in conn.execute("select slug from zones order by id")]
        reports = [zone_report(conn, s) for s in slugs]
        for r in reports:  # the dashboard reads these; computing per request would need a server
            conn.execute(
                """
                insert into zone_reports (zone_id, report)
                select id, %s::jsonb from zones where slug = %s
                on conflict (zone_id) do update set report = excluded.report, computed_at = now()
                """,
                (json.dumps(r, default=str), r["zone"]),
            )

    print(f"alerts raised or refreshed: {raised}")
    for r in reports:
        print(f"\n{r['zone']}: {r['observations']} observations, {r['species']} species, "
              f"{len(r['invasive_species'])} invasive species recorded")
        for s in r["invasive_species"]:
            print(f"    {s['species']:28} {s['records']:3} records, "
                  f"{s['first_record']} to {s['last_record']}")
        doc = r["layers"]["documented"]["findings"]
        print(f"  1 documented findings : {len(doc)} cited "
              f"({sum(f['recorded_in_zone'] for f in doc)} about species recorded here)")
        for name in ("cooccurrence", "trend"):
            layer = r["layers"][name]
            note = layer["reason"] if layer["status"] == "insufficient" else "computed"
            print(f"  {'2' if name == 'cooccurrence' else '3'} {name:21} : "
                  f"{layer['status']} ({note})")
    if args.json:
        args.json.write_text(json.dumps(reports, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
