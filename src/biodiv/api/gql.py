"""GraphQL: flexible, nested filtering for researchers, as the design report calls for.

    { detections(species: "Panthera pardus", since: "2026-07-01T00:00:00Z", minConfidence: 0.9) {
        capturedAt confidence zone species } }

Read-only. Every filter is a bound parameter (never spliced into SQL), and result sizes are capped.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Any, TypeVar

import psycopg
import strawberry
from fastapi import Depends
from strawberry.types import Info

from biodiv.api.deps import get_conn

MAX_ROWS = 500


@strawberry.type
class Zone:
    slug: str
    name: str
    country: str
    group: str | None
    observations: int
    species: int
    invasive_records: int


@strawberry.type
class Species:
    scientific_name: str
    common_name: str | None
    kingdom: str | None
    iucn_category: str | None
    invasive_in_india: bool | None
    establishment_means: str | None


@strawberry.type
class Detection:
    id: int
    captured_at: datetime
    zone: str | None
    label: str | None
    species: str | None
    common_name: str | None
    confidence: float
    origin: str  # 'observer' (a person identified it) or 'model' (our detector/classifier did)
    invasive: bool
    longitude: float | None
    latitude: float | None
    source: str | None
    record_url: str | None


@strawberry.type
class Alert:
    id: int
    kind: str
    severity: str
    zone: str | None
    species: str | None
    created_at: datetime
    caveat: str | None


@strawberry.type
class Playbook:
    species: str
    method: str
    summary: str
    effectiveness: str | None
    evidence_strength: str | None
    region_note: str | None
    quotes: list[str]
    citation: str
    url: str | None
    verified_on: date | None
    risks: str | None
    failure_cases: str | None


T = TypeVar("T")


def _build(cls: type[T], rows: list[tuple]) -> list[T]:
    """Make `cls` objects from rows whose columns follow the class's field order.

    Strawberry types accept keyword arguments only, so build by name.
    """
    names = [f.name for f in dataclasses.fields(cls)]
    return [cls(**dict(zip(names, row, strict=True))) for row in rows]


def _rows(info: Info, sql: str, params: tuple) -> list[tuple]:
    conn: psycopg.Connection = info.context["conn"]
    return conn.execute(sql, params).fetchall()


@strawberry.type
class Query:
    @strawberry.field
    def zones(self, info: Info) -> list[Zone]:
        rows = _rows(info, """
            select z.slug, z.name, z.country, z.group_name,
                   (select count(*) from detections d where d.zone_id = z.id),
                   (select count(distinct species_id) from detections d where d.zone_id = z.id),
                   (select count(*) from invasive_records r where r.zone_id = z.id)
            from zones z order by z.id""", ())
        return _build(Zone, rows)

    @strawberry.field
    def species(self, info: Info, search: str | None = None, invasive_only: bool = False,
                limit: int = 50) -> list[Species]:
        rows = _rows(info, """
            select s.scientific_name, s.common_name, s.kingdom, s.iucn_category,
                   i.is_invasive and i.origin_class = 'alien', i.establishment_means
            from species s
            left join invasive_status i on i.species_id = s.id and i.country = 'IN'
            where (%s::text is null or s.scientific_name ilike '%%' || %s || '%%'
                   or s.common_name ilike '%%' || %s || '%%')
              and (not %s or (i.is_invasive and i.origin_class = 'alien'))
            order by s.scientific_name limit %s""",
            (search, search, search, invasive_only, min(max(limit, 1), MAX_ROWS)))
        return _build(Species, rows)

    @strawberry.field
    def detections(
        self, info: Info, species: str | None = None, zone: str | None = None,
        min_confidence: float | None = None, since: datetime | None = None,
        until: datetime | None = None, origin: str | None = None,
        invasive_only: bool = False, limit: int = 100,
    ) -> list[Detection]:
        rows = _rows(info, """
            select d.id, d.captured_at, z.slug, d.label_raw, s.scientific_name, s.common_name,
                   d.confidence, d.origin,
                   coalesce(i.is_invasive and i.origin_class = 'alien', false),
                   st_x(m.geom), st_y(m.geom), src.name, m.uri
            from detections d
            join media_items m on m.id = d.media_item_id
            join sources src on src.id = m.source_id
            left join zones z on z.id = d.zone_id
            left join species s on s.id = d.species_id
            left join invasive_status i on i.species_id = d.species_id and i.country = z.country
            where (%s::text is null or lower(s.scientific_name) = lower(%s)
                   or lower(s.common_name) = lower(%s))
              and (%s::text is null or z.slug = %s)
              and (%s::real is null or d.confidence >= %s)
              and (%s::timestamptz is null or d.captured_at >= %s)
              and (%s::timestamptz is null or d.captured_at < %s)
              and (%s::text is null or d.origin = %s)
              and (not %s or (i.is_invasive and i.origin_class = 'alien'))
            order by d.captured_at desc limit %s""",
            (species, species, species, zone, zone, min_confidence, min_confidence, since, since,
             until, until, origin, origin, invasive_only, min(max(limit, 1), MAX_ROWS)))
        return _build(Detection, rows)

    @strawberry.field
    def alerts(self, info: Info, zone: str | None = None, kind: str | None = None,
               limit: int = 50) -> list[Alert]:
        rows = _rows(info, """
            select a.id, a.kind, a.severity, z.slug, s.scientific_name, a.created_at,
                   a.evidence->>'caveat'
            from alerts a left join zones z on z.id = a.zone_id
            left join species s on s.id = a.species_id
            where (%s::text is null or z.slug = %s) and (%s::text is null or a.kind = %s)
            order by a.created_at desc limit %s""",
            (zone, zone, kind, kind, min(max(limit, 1), MAX_ROWS)))
        return _build(Alert, rows)

    @strawberry.field
    def playbooks(self, info: Info, species: str | None = None) -> list[Playbook]:
        rows = _rows(info, """
            select s.scientific_name, p.method, p.description, p.effectiveness,
                   p.evidence_strength, p.region_note, p.source_quotes, p.citation_text,
                   p.citation_url, p.verified_on, p.risks, p.failure_cases
            from mitigation_playbooks p join species s on s.id = p.species_id
            where %s::text is null or lower(s.scientific_name) = lower(%s)
            order by s.scientific_name, p.method""", (species, species))
        return _build(Playbook, [(*r[:6], list(r[6]), *r[7:]) for r in rows])


schema = strawberry.Schema(query=Query)


def get_context(conn: psycopg.Connection = Depends(get_conn)) -> dict[str, Any]:
    return {"conn": conn}
