-- Curated, cited knowledge about invasive species: what they do, and what has been tried.
-- Source of truth is db/seeds/knowledge.json; every row carries the verbatim quotes that
-- support it (checked against the live source by scripts/verify_citations.py), and a note on
-- where the evidence comes from, so a result from a Pacific island is never read as an Indian
-- forest result.

alter table mitigation_playbooks
  add column source_quotes jsonb not null default '[]',
  add column region_note   text,
  add column verified_on   date,
  add column origin        text not null default 'knowledge.json';

alter table mitigation_playbooks
  add constraint playbook_has_quotes check (jsonb_array_length(source_quotes) > 0);

create unique index mitigation_playbooks_uq
  on mitigation_playbooks (species_id, method, citation_url, description);

-- What an invasive species is reported to do to native species and ecosystems. Species-level
-- links to a named threatened native (IUCN 8.1.2) live in threat_links; these are the broader
-- findings from the literature, including the preliminary and the merely worrying, labelled as
-- such.
create table impact_findings (
  id                  bigint generated always as identity primary key,
  invasive_species_id bigint not null references species (id) on delete cascade,
  zone_id             integer references zones (id),         -- null = general, not zone-specific
  finding_type        text not null check (finding_type in ('impact', 'spread', 'concern')),
  affected            text not null check (length(trim(affected)) > 0),
  summary             text not null check (length(trim(summary)) > 0),
  certainty           text not null
                      check (certainty in ('experimental', 'observational', 'preliminary',
                                           'unverified_concern', 'review')),
  region_note         text not null,
  source_quotes       jsonb not null check (jsonb_array_length(source_quotes) > 0),
  citation_text       text not null check (length(trim(citation_text)) > 0),
  citation_url        text not null,
  verified_on         date,
  origin              text not null default 'knowledge.json'
);
create unique index impact_findings_uq
  on impact_findings (invasive_species_id, coalesce(zone_id, 0), citation_url, finding_type,
                      affected);
create index impact_findings_zone_ix on impact_findings (zone_id) where zone_id is not null;

alter table impact_findings enable row level security;
revoke all on impact_findings from anon, authenticated;
grant select on impact_findings to anon, authenticated;
create policy public_read on impact_findings for select to anon, authenticated using (true);
