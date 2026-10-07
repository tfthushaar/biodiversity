"""What invasive species do to the native ecosystem of a zone, in three layers of decreasing
certainty. Each layer says what it is, and refuses to answer when the data cannot support one.

  1. Documented findings. What cited sources report. No inference by us. Includes preliminary
     findings and plain worries, labelled as such.
  2. Co-occurrence. Where invasive records are denser, is native richness lower? Correlational:
     observer effort and access confound it, so richness is rarefied to a common sample size.
  3. Trend. Is the invasive share rising over the years while native records fall? Even a clear
     trend would not show cause.

Citizen-science data for these reserves is currently far too thin for layers 2 and 3 (see
docs/data-quality.md). They are implemented, tested, and gated, and on today's data they report
"insufficient data" with the reason, rather than a number.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

import psycopg

from biodiv.analytics.stats import (
    bootstrap_interval,
    mann_kendall,
    rarefied_richness,
    spearman,
)

CELL_DEGREES = 0.05  # about 5 km
RAREFY_TO = 10  # native records per cell that richness is compared at
MIN_CELLS = 20  # cells that must be usable before a co-occurrence is reported
MIN_INVASIVE_CELLS = 5  # cells with any invasive record: with fewer there is nothing to correlate
MIN_YEARS = 6  # years with enough effort for a trend
MIN_RECORDS_PER_YEAR = 15  # observations in a zone-year for it to count
MIN_INVASIVE_RECORDS = 30  # invasive records needed in a zone for a trend

CAUTION_COOCCURRENCE = (
    "Correlation, not cause. Invasives and natives may both depend on disturbance, access or "
    "where observers go; richness is rarefied to reduce, not remove, the effect of effort."
)
CAUTION_TREND = (
    "A trend in records is not a trend in abundance, and says nothing about cause. Observer "
    "numbers and habits change over the years."
)


@dataclass
class LayerResult:
    layer: str
    status: str  # 'ok' | 'insufficient'
    reason: str | None = None  # why not, when insufficient
    needs: str | None = None  # what would make it possible
    caution: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _zone(conn: psycopg.Connection, slug: str) -> tuple[int, str]:
    row = conn.execute("select id, country from zones where slug = %s", (slug,)).fetchone()
    if row is None:
        raise ValueError(f"unknown zone {slug!r}")
    return row[0], row[1]


# ---------------------------------------------------------------------------- layer 1


def documented_findings(conn: psycopg.Connection, zone_slug: str) -> list[dict[str, Any]]:
    """Cited findings relevant to a zone: those about species recorded there, those written
    about the zone itself, and general ones for any species recorded in it."""
    zone_id, _ = _zone(conn, zone_slug)
    rows = conn.execute(
        """
        select f.id, s.scientific_name, s.common_name, z.slug, f.finding_type, f.affected,
               f.summary, f.certainty, f.region_note, f.source_quotes, f.citation_text,
               f.citation_url, f.verified_on::text,
               coalesce(r.records, 0) as records_here
        from impact_findings f
        join species s on s.id = f.invasive_species_id
        left join zones z on z.id = f.zone_id
        left join (select species_id, records from zone_invasive_summary where zone_id = %s) r
               on r.species_id = f.invasive_species_id
        where f.zone_id = %s or (f.zone_id is null and r.records is not null)
        order by (f.zone_id is null), s.scientific_name, f.finding_type
        """,
        (zone_id, zone_id),
    ).fetchall()
    keys = ("id", "species", "common_name", "zone", "finding_type", "affected", "summary",
            "certainty", "region_note", "quotes", "citation", "url", "verified_on",
            "records_in_zone")
    findings = [dict(zip(keys, r, strict=True)) for r in rows]
    for f in findings:
        # A zone-specific worry about a species we have no records of is still worth showing,
        # but it must not be mistaken for a record.
        f["recorded_in_zone"] = f["records_in_zone"] > 0
    return findings


# ---------------------------------------------------------------------------- layer 2


def cooccurrence(conn: psycopg.Connection, zone_slug: str) -> LayerResult:
    zone_id, country = _zone(conn, zone_slug)
    rows = conn.execute(
        """
        select floor(st_x(m.geom) / %s)::int, floor(st_y(m.geom) / %s)::int, d.species_id,
               coalesce(i.is_invasive and i.origin_class = 'alien', false),
               coalesce(i.origin_class in ('alien', 'uncertain'), false)
        from detections d
        join media_items m on m.id = d.media_item_id
        left join invasive_status i on i.species_id = d.species_id and i.country = %s
        where d.zone_id = %s and m.geom is not null and d.species_id is not null
        """,
        (CELL_DEGREES, CELL_DEGREES, country, zone_id),
    ).fetchall()

    cells: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {"all": 0, "invasive": 0, "native": defaultdict(int)})
    for cx, cy, species_id, invasive, non_native in rows:
        c = cells[(cx, cy)]
        c["all"] += 1
        c["invasive"] += bool(invasive)
        if not non_native:
            c["native"][species_id] += 1

    usable = []
    for c in cells.values():
        richness = rarefied_richness(list(c["native"].values()), RAREFY_TO)
        if richness is not None:
            usable.append((c["invasive"] / c["all"], richness, c["invasive"]))

    with_invasives = sum(1 for _, _, inv in usable if inv > 0)
    base = {"cells_total": len(cells), "cells_usable": len(usable), "cell_degrees": CELL_DEGREES,
            "richness_compared_at": RAREFY_TO, "cells_with_invasives": with_invasives,
            "required_cells": MIN_CELLS, "required_invasive_cells": MIN_INVASIVE_CELLS}
    needs = (f"at least {MIN_CELLS} grid cells with {RAREFY_TO}+ native records, of which "
             f"{MIN_INVASIVE_CELLS}+ also hold invasive records")
    if len(usable) < MIN_CELLS:
        return LayerResult("cooccurrence", "insufficient",
                           f"only {len(usable)} usable grid cells (need {MIN_CELLS})", needs,
                           detail=base)
    if with_invasives < MIN_INVASIVE_CELLS:
        return LayerResult("cooccurrence", "insufficient",
                           f"invasive records appear in only {with_invasives} usable cells "
                           f"(need {MIN_INVASIVE_CELLS}), so there is nothing to compare", needs,
                           detail=base)

    share, richness = [u[0] for u in usable], [u[1] for u in usable]
    rho = spearman(share, richness)
    if rho is None:
        return LayerResult("cooccurrence", "insufficient", "no variation to correlate", needs,
                           detail=base)
    return LayerResult("cooccurrence", "ok", caution=CAUTION_COOCCURRENCE, detail={
        **base, "spearman_rho": rho,
        "ci95": bootstrap_interval(share, richness)})


# ---------------------------------------------------------------------------- layer 3


def trend(conn: psycopg.Connection, zone_slug: str) -> LayerResult:
    zone_id, country = _zone(conn, zone_slug)
    needs = (f"{MIN_YEARS}+ years with {MIN_RECORDS_PER_YEAR}+ observations each, and "
             f"{MIN_INVASIVE_RECORDS}+ invasive records in the zone")
    years = conn.execute(
        """
        select extract(year from m.captured_at)::int as yr,
               count(distinct m.id) as effort,
               count(*) filter (where i.is_invasive and i.origin_class = 'alien') as invasive,
               count(*) filter (where d.species_id is not null
                                and coalesce(i.origin_class, 'native') = 'native') as native
        from media_items m
        join detections d on d.media_item_id = m.id
        left join invasive_status i on i.species_id = d.species_id and i.country = %s
        where m.zone_id = %s and m.captured_at is not null
        group by 1 order by 1
        """,
        (country, zone_id),
    ).fetchall()
    total_invasive = sum(r[2] for r in years)
    usable = [r for r in years if r[1] >= MIN_RECORDS_PER_YEAR]
    detail = {"years_with_data": len(years), "usable_years": len(usable),
              "invasive_records": total_invasive, "required_years": MIN_YEARS,
              "required_invasive_records": MIN_INVASIVE_RECORDS,
              "required_records_per_year": MIN_RECORDS_PER_YEAR}

    if len(usable) < MIN_YEARS:
        return LayerResult("trend", "insufficient",
                           f"only {len(usable)} years have {MIN_RECORDS_PER_YEAR}+ observations "
                           f"(need {MIN_YEARS})", needs, detail=detail)
    if total_invasive < MIN_INVASIVE_RECORDS:
        return LayerResult("trend", "insufficient",
                           f"only {total_invasive} invasive records in the zone "
                           f"(need {MIN_INVASIVE_RECORDS})", needs, detail=detail)

    t = [r[0] for r in usable]
    invasive_index = [r[2] / r[1] for r in usable]  # invasive records per observation
    native_index = [r[3] / r[1] for r in usable]
    inv, nat = mann_kendall(t, invasive_index), mann_kendall(t, native_index)
    return LayerResult("trend", "ok", caution=CAUTION_TREND, detail={
        **detail, "years": [min(t), max(t)],
        "invasive_per_observation": asdict(inv) if inv else None,
        "native_per_observation": asdict(nat) if nat else None})


# ------------------------------------------------------------------------ the report


def zone_report(conn: psycopg.Connection, zone_slug: str) -> dict[str, Any]:
    zone_id, _ = _zone(conn, zone_slug)
    records = conn.execute(
        """
        select s.scientific_name, s.common_name, z.records, z.first_record::date::text,
               z.last_record::date::text, z.sources
        from zone_invasive_summary z join species s on s.id = z.species_id
        where z.zone_id = %s order by z.records desc, s.scientific_name
        """,
        (zone_id,),
    ).fetchall()
    totals = conn.execute(
        "select count(*), count(distinct species_id) from detections where zone_id = %s",
        (zone_id,),
    ).fetchone()
    return {
        "zone": zone_slug,
        "observations": totals[0],
        "species": totals[1],
        "invasive_species": [dict(zip(
            ("species", "common_name", "records", "first_record", "last_record", "sources"),
            r, strict=True)) for r in records],
        "layers": {
            "documented": {
                "status": "ok",
                "findings": documented_findings(conn, zone_slug),
                "note": "Only what cited sources report. Species-level IUCN threat links are "
                        "pending an API token (docs/iucn.md).",
            },
            "cooccurrence": cooccurrence(conn, zone_slug).as_dict(),
            "trend": trend(conn, zone_slug).as_dict(),
        },
    }
