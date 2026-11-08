"""Remove stored GBIF records that are not preserved specimens.

    python scripts/prune_gbif_records.py            # report only
    python scripts/prune_gbif_records.py --delete

GBIF records were first taken whatever their basis of record. Only preserved specimens (museum and
herbarium material that can be traced to a collection) are kept now. Each stored record is looked
up in GBIF by its identifier. Records of any other basis are deleted, and so are records GBIF no
longer holds, since their source can no longer be checked. Detections go with their record.
"""

from __future__ import annotations

import argparse
import collections
import sys
import time

import httpx
import psycopg

from biodiv.core.settings import get_settings
from biodiv.ingestion.gbif_occurrences import GBIF_OCCURRENCE_API, SPECIMEN

SOURCES = ("GBIF specimens", "GBIF occurrences")  # the source's name before and after its rename
BATCH = 100


def basis_of_records(ids: list[str], client: httpx.Client) -> dict[str, str]:
    found: dict[str, str] = {}
    for i in range(0, len(ids), BATCH):
        params = [("gbifId", x) for x in ids[i:i + BATCH]] + [("limit", 300)]
        for attempt in range(5):
            try:
                resp = client.get(GBIF_OCCURRENCE_API, params=params)
                resp.raise_for_status()
                break
            except httpx.HTTPError:
                if attempt == 4:
                    raise
                time.sleep(2 * (attempt + 1))
        for r in resp.json()["results"]:
            found[str(r["key"])] = r.get("basisOfRecord", "")
        time.sleep(0.15)
    return found


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--delete", action="store_true")
    args = p.parse_args()
    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        rows = conn.execute(
            "select m.id, m.external_id, z.slug from media_items m "
            "join sources s on s.id = m.source_id left join zones z on z.id = m.zone_id "
            "where s.name = any(%s)", (list(SOURCES),)).fetchall()
        print(f"{len(rows)} GBIF records stored")
        with httpx.Client(timeout=60, headers={"User-Agent": "biodiversity-student-project"}) as c:
            basis = basis_of_records([r[1] for r in rows], c)
        remove = [r for r in rows if basis.get(r[1]) != SPECIMEN]
        by = collections.Counter(basis.get(r[1], "no longer in GBIF") for r in remove)
        print(f"{len(rows) - len(remove)} are preserved specimens and stay")
        print(f"{len(remove)} are not: {dict(by)}")
        print("by park:", dict(collections.Counter(r[2] for r in remove)))
        if not args.delete:
            print("report only; run again with --delete to remove them")
            return 0
        ids = [r[0] for r in remove]
        for i in range(0, len(ids), 500):
            conn.execute("delete from media_items where id = any(%s)", (ids[i:i + 500],))
        print(f"deleted {len(ids)} records and their detections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
