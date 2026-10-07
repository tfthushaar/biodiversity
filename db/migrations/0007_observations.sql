-- Observations from public platforms (iNaturalist, GBIF) sit beside model detections.

-- media_items is "one row per observation, image or frame". uri is the stable record page
-- (provenance and identity); image_url is the picture itself, and is null when there is none
-- or when its licence does not allow us to use it.
alter table media_items add column image_url text;

-- Who identified the species. 'model' = our detector/classifier. 'observer' = a person
-- (e.g. iNaturalist research grade). Keeping them apart stops human records from being
-- reported as model accuracy, and lets us measure the model against them.
alter table detections
  add column origin text not null default 'model'
    check (origin in ('model', 'observer'));

-- Where the last successful incremental fetch got to, per source and scope (zone).
create table ingestion_cursors (
  source_id  smallint not null references sources (id) on delete cascade,
  scope      text not null,
  cursor     text not null,
  updated_at timestamptz not null default now(),
  primary key (source_id, scope)
);
alter table ingestion_cursors enable row level security;
revoke all on ingestion_cursors from anon, authenticated;

-- Rows we saw but refused, by reason, so the Sources view can show why data was dropped.
alter table ingestion_runs add column rejected jsonb not null default '{}';
