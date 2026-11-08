"""Remove stored records of invasive species that no peer-reviewed paper backs.

    python scripts/prune_unresearched.py            # report only
    python scripts/prune_unresearched.py --delete

A species GRIIS lists as alien and invasive in a park's country counts as an invasive species here
only when a paper backs a claim about it (the researched_species view). The ingest refuses the
rest. This removes the records stored before that rule: each one with its detections. Records of
species GRIIS does not list as invasive are untouched.
"""

from __future__ import annotations

import argparse
import sys

import psycopg

from biodiv.core.settings import get_settings

FIND = """
select m.id, s.scientific_name, z.slug
from media_items m
join detections d on d.media_item_id = m.id
join zones z on z.id = d.zone_id
join species s on s.id = d.species_id
join invasive_status i on i.species_id = d.species_id and i.country = z.country
                      and i.is_invasive and i.origin_class = 'alien'
where d.species_id not in (select species_id from researched_species)
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--delete", action="store_true")
    args = p.parse_args()
    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        rows = conn.execute(FIND).fetchall()
        species = {r[1] for r in rows}
        print(f"{len(rows)} records of {len(species)} invasive species with no paper")
        by_park: dict[str, int] = {}
        for _, _, slug in rows:
            by_park[slug] = by_park.get(slug, 0) + 1
        print("by park:", by_park)
        kept = conn.execute("select count(*), count(distinct species_id) from invasive_records"
                            ).fetchone()
        print(f"{kept[0]} records of {kept[1]} species stay (each has a paper)")
        if not args.delete:
            print("report only; run again with --delete to remove them")
            return 0
        ids = sorted({r[0] for r in rows})
        for i in range(0, len(ids), 500):
            conn.execute("delete from media_items where id = any(%s)", (ids[i:i + 500],))
        print(f"deleted {len(ids)} records and their detections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
