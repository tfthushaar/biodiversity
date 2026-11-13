"""Count the USGS records of the Burmese python in the Everglades' counties, by record type.

    python scripts/usgs_python_sources.py            # writes docs/metrics/usgs_python_sources.json

The paper says that one report in the USGS database can contribute many records, and backs it
with these counts. This reads the public API, so the figures can be checked and refreshed, and
the paper takes them from the file the script writes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.usgs_nas import NAS_API, ZONE_COUNTIES

UA = "biodiv-student-project/0.1 (+https://github.com/tfthushaar/biodiversity)"
GENUS, SPECIES = "Python", "bivittatus"


async def count(zone: str = "everglades") -> dict:
    by_type: Counter[str] = Counter()
    async with PoliteClient(user_agent=UA, per_second=1.0, max_concurrency=1) as http:
        for state, county in ZONE_COUNTIES[zone]:
            offset = 0
            while True:
                page = await http.get_json(NAS_API, {
                    "genus": GENUS, "species": SPECIES, "state": state, "county": county,
                    "limit": 500, "offset": offset})
                results = page.get("results") or []
                by_type.update((r.get("recordType") or "unknown") for r in results)
                offset += 500
                if str(page.get("endOfRecords")).lower() == "true" or not results:
                    break
    return {
        "species": f"{GENUS} {SPECIES}",
        "counties": [f"{c}, {s}" for s, c in ZONE_COUNTIES[zone]],
        "queried_on": datetime.now(UTC).date().isoformat(),
        "source": NAS_API,
        "total": sum(by_type.values()),
        "by_record_type": dict(by_type.most_common()),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="docs/metrics/usgs_python_sources.json")
    args = p.parse_args()
    result = asyncio.run(count())
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{result['total']} records: {result['by_record_type']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
