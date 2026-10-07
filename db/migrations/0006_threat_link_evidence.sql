-- threat_links began as IUCN-only (threat code 8.1.2). The IUCN API needs a human-reviewed
-- token, so rows can also come from cited published literature. Record which it is, so the
-- dashboard never presents a literature finding as an IUCN assessment.
alter table threat_links
  add column evidence_source text not null default 'iucn'
    check (evidence_source in ('iucn', 'literature')),
  add column citation_url text;

alter table threat_links alter column iucn_threat_code drop not null;
alter table threat_links alter column iucn_threat_code drop default;

alter table threat_links add constraint threat_links_iucn_has_code
  check (evidence_source <> 'iucn' or iucn_threat_code is not null);

-- The old uniqueness keyed on the threat code; key it on the evidence source as well.
drop index threat_links_uq;
create unique index threat_links_uq
  on threat_links (native_species_id, coalesce(invasive_species_id, 0),
                   coalesce(invasive_name, ''), evidence_source, coalesce(iucn_threat_code, ''));
