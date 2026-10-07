"""Early-detection alerts: an invasive species recorded in a zone for the first time.

Careful wording matters. "First record" means the first record in OUR SOURCES, not the first
arrival: the species may have been there for years unrecorded, and with citizen-science data that
is the usual case. An alert is raised only when:

  * the first record is recent (within RECENT_DAYS of `as_of`), and
  * the zone had at least MIN_PRIOR_EFFORT observations before it, so that not having seen the
    species earlier means something, and
  * no cited source already reports the species in that zone (a documented problem is not news).

Severity is "high" when the literature documents harm by this species anywhere, otherwise
"medium". It is a prompt to look, never a finding.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import psycopg

RECENT_DAYS = 365
MIN_PRIOR_EFFORT = 50

CAVEAT = (
    "'First record' means first in the data sources used here, not first arrival. The species "
    "may have been present, unrecorded, for some time."
)


def first_record_alerts(
    conn: psycopg.Connection, as_of: date | None = None
) -> list[dict[str, Any]]:
    as_of = as_of or datetime.now(UTC).date()
    rows = conn.execute(
        """
        select s.zone_id, z.slug, s.species_id, sp.scientific_name, s.records, s.first_record,
               s.last_record, s.sources,
               (select count(*) from media_items m
                 where m.zone_id = s.zone_id and m.captured_at < s.first_record) as prior_effort,
               exists (select 1 from impact_findings f
                        where f.invasive_species_id = s.species_id
                          and f.zone_id = s.zone_id) as documented_here,
               exists (select 1 from impact_findings f
                        where f.invasive_species_id = s.species_id
                          and f.certainty in ('experimental', 'observational', 'review'))
                 as documented_harm
        from zone_invasive_summary s
        join zones z on z.id = s.zone_id
        join species sp on sp.id = s.species_id
        where s.first_record::date <= %s
          and s.first_record::date > %s::date - %s * interval '1 day'
        order by z.slug, sp.scientific_name
        """,
        (as_of, as_of, RECENT_DAYS),
    ).fetchall()

    alerts = []
    for (zone_id, slug, species_id, name, records, first, last, sources, prior,
         documented_here, documented_harm) in rows:
        if prior < MIN_PRIOR_EFFORT or documented_here:
            continue
        alerts.append({
            "zone_id": zone_id, "species_id": species_id,
            "severity": "high" if documented_harm else "medium",
            "window_start": first, "window_end": last, "score": float(records),
            "evidence": {
                "zone": slug, "species": name, "records": records, "sources": sources,
                "first_record": first.date().isoformat(), "last_record": last.date().isoformat(),
                "observations_in_zone_before": prior,
                "documented_harm_elsewhere": documented_harm,
                "caveat": CAVEAT,
            },
        })
    return alerts


def upsert_alerts(conn: psycopg.Connection, alerts: list[dict[str, Any]]) -> int:
    """Insert or refresh 'edrr' alerts. Idempotent: one alert per zone and species."""
    for a in alerts:
        conn.execute(
            """
            insert into alerts (kind, severity, zone_id, species_id, window_start, window_end,
                                score, evidence)
            values ('edrr', %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (zone_id, species_id) where kind = 'edrr' do update set
              severity = excluded.severity, window_start = excluded.window_start,
              window_end = excluded.window_end, score = excluded.score,
              evidence = excluded.evidence
            """,
            (a["severity"], a["zone_id"], a["species_id"], a["window_start"], a["window_end"],
             a["score"], json.dumps(a["evidence"])),
        )
    return len(alerts)
