-- One representative photo per species, with the credit and licence its owner chose. Photos are
-- shown only with that credit, and only when the licence allows it (see workers/enrich_species).
alter table species
  add column photo_url        text,
  add column photo_credit     text,
  add column photo_license    text,
  add column photo_source_url text;
