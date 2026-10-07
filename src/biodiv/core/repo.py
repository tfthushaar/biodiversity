"""Small, explicit database writes shared by the workers."""

from __future__ import annotations

import psycopg


def upsert_species(
    conn: psycopg.Connection,
    *,
    gbif_key: int | None,
    name: str,
    kingdom: str | None,
    rank: str | None,
    common_name: str | None = None,
    inat_taxon_id: int | None = None,
) -> int:
    """Insert or update a species and return its id. Idempotent.

    Species with a GBIF key are identified by it. Without one, we fall back to the exact
    (case-insensitive) name within a kingdom, so re-running an import never duplicates them.
    """
    species_id = _upsert_species_core(conn, gbif_key, name, kingdom, rank)
    if common_name:
        conn.execute(
            "update species set common_name = %s where id = %s and common_name is null",
            (common_name, species_id),
        )
    if inat_taxon_id is not None:
        # inat_taxon_id is unique; two of our species can map to one iNaturalist taxon after
        # synonym merging, so only claim it if nobody else has.
        conn.execute(
            "update species set inat_taxon_id = %s where id = %s and inat_taxon_id is null "
            "and not exists (select 1 from species where inat_taxon_id = %s)",
            (inat_taxon_id, species_id, inat_taxon_id),
        )
    return species_id


def _upsert_species_core(
    conn: psycopg.Connection,
    gbif_key: int | None,
    name: str,
    kingdom: str | None,
    rank: str | None,
) -> int:
    if gbif_key is not None:
        return conn.execute(
            """
            insert into species (gbif_taxon_key, scientific_name, kingdom, taxon_rank)
            values (%s, %s, %s, %s)
            on conflict (gbif_taxon_key) do update set
              scientific_name = excluded.scientific_name,
              kingdom         = coalesce(excluded.kingdom, species.kingdom),
              taxon_rank      = coalesce(excluded.taxon_rank, species.taxon_rank),
              updated_at      = now()
            returning id
            """,
            (gbif_key, name, kingdom, rank),
        ).fetchone()[0]

    row = conn.execute(
        """
        select id from species
        where gbif_taxon_key is null
          and lower(scientific_name) = lower(%s)
          and kingdom is not distinct from %s
        """,
        (name, kingdom),
    ).fetchone()
    if row:
        return row[0]
    return conn.execute(
        "insert into species (scientific_name, kingdom, taxon_rank) values (%s, %s, %s) "
        "returning id",
        (name, kingdom, rank),
    ).fetchone()[0]


def upsert_invasive_status(
    conn: psycopg.Connection,
    *,
    species_id: int,
    country: str,
    is_invasive: bool | None,
    establishment_means: str | None,
    occurrence_status: str | None,
    habitat: str | None,
    source: str,
    source_ref: str,
) -> None:
    conn.execute(
        """
        insert into invasive_status (species_id, country, is_invasive, establishment_means,
                                     occurrence_status, habitat, source, source_ref)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (species_id, country) do update set
          is_invasive         = excluded.is_invasive,
          establishment_means = excluded.establishment_means,
          occurrence_status   = excluded.occurrence_status,
          habitat             = excluded.habitat,
          source              = excluded.source,
          source_ref          = excluded.source_ref
        """,
        (
            species_id, country, is_invasive, establishment_means,
            occurrence_status, habitat, source, source_ref,
        ),
    )
