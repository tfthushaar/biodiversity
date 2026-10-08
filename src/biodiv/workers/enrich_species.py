"""Attach one representative photo, with its credit and licence, to each invasive species.

    python -m biodiv.workers.enrich_species [--limit 100] [--refresh]

The photo comes from the species' page on iNaturalist, where each photo carries the licence its
owner chose. A photo is stored only if that licence allows showing it with credit (Creative
Commons, excluding no-derivatives), and it is always shown with the credit and a link back to the
photo. Species without a usable photo are left without one, and the dashboard says so.

Only species that have invasive records in a monitored zone are looked up, a few dozen.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Any

import psycopg

from biodiv.core.settings import get_settings
from biodiv.ingestion.http import PoliteClient
from biodiv.ingestion.observations import IMAGE_LICENSES, short_license

log = logging.getLogger(__name__)

INAT_TAXA = "https://api.inaturalist.org/v1/taxa"
INAT_PHOTO_PAGE = "https://www.inaturalist.org/photos/{id}"


@dataclass(frozen=True)
class Photo:
    url: str
    credit: str
    license: str
    source_url: str


def _usable(photo: dict[str, Any] | None) -> Photo | None:
    """The photo, if it has an address, a credit, and a licence that allows showing it."""
    if not photo:
        return None
    code = short_license(photo.get("license_code"))
    url, credit = photo.get("medium_url"), (photo.get("attribution") or "").strip()
    if not (url and credit and photo.get("id") and code in IMAGE_LICENSES):
        return None
    page = INAT_PHOTO_PAGE.format(id=photo["id"])
    return Photo(url=url, credit=credit, license=code, source_url=page)


async def find_photo(http: PoliteClient, scientific_name: str) -> Photo | None:
    found = await http.get_json(
        INAT_TAXA, {"q": scientific_name, "rank": "species", "per_page": 5, "is_active": "true"}
    )
    taxon = next(
        (t for t in found.get("results", [])
         if t.get("name", "").lower() == scientific_name.lower()),
        None,
    )
    if taxon is None:
        return None
    if photo := _usable(taxon.get("default_photo")):
        return photo
    # The default photo is not freely licensed; another photo of the species may be.
    detail = await http.get_json(f"{INAT_TAXA}/{taxon['id']}")
    for result in detail.get("results", []):
        for item in result.get("taxon_photos", []):
            if photo := _usable(item.get("photo")):
                return photo
    return None


def species_needing_photos(
    conn: psycopg.Connection, limit: int, refresh: bool
) -> list[tuple[int, str]]:
    return conn.execute(
        """
        select s.id, s.scientific_name
        from species s
        where s.id in (select distinct species_id from invasive_records)
          and (%s or s.photo_url is null)
        order by (select count(*) from invasive_records r where r.species_id = s.id) desc, s.id
        limit %s
        """,
        (refresh, limit),
    ).fetchall()


async def enrich(
    conn: psycopg.Connection, http: PoliteClient, *, limit: int = 100, refresh: bool = False
) -> tuple[int, int]:
    """Returns (species given a photo, species left without one)."""
    added = missing = 0
    for species_id, name in species_needing_photos(conn, limit, refresh):
        photo = await find_photo(http, name)
        if photo is None:
            log.info("no usable photo for %s", name)
            missing += 1
            continue
        conn.execute(
            "update species set photo_url = %s, photo_credit = %s, photo_license = %s, "
            "photo_source_url = %s where id = %s",
            (photo.url, photo.credit, photo.license, photo.source_url, species_id),
        )
        conn.commit()
        added += 1
    return added, missing


async def _amain(args: argparse.Namespace) -> tuple[int, int]:
    async with PoliteClient(user_agent=get_settings().user_agent, per_second=1.0) as http:
        with psycopg.connect(get_settings().database_url) as conn:
            return await enrich(conn, http, limit=args.limit, refresh=args.refresh)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--refresh", action="store_true", help="look up species that already have one")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not get_settings().database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    added, missing = asyncio.run(_amain(args))
    print(f"photos added for {added} species; {missing} had no usable photo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
