-- Where data comes from. One row per connector.
create table sources (
  id             smallint generated always as identity primary key,
  name           text not null unique,
  kind           text not null check (kind in ('api', 'dataset', 'replay')),
  base_url       text,
  license        text,
  attribution    text,
  rate_limit_rpm integer
);

-- Monitored areas, as real boundary polygons.
create table zones (
  id          integer generated always as identity primary key,
  slug        text not null unique,
  name        text not null,
  group_name  text,
  country     char(2) not null,
  is_protected boolean not null default true,
  source_note text,
  geom        geometry(MultiPolygon, 4326) not null
);
create index zones_geom_gix on zones using gist (geom);

create table species (
  id             bigint generated always as identity primary key,
  gbif_taxon_key bigint unique,
  inat_taxon_id  integer unique,
  scientific_name text not null,
  common_name    text,
  kingdom        text,
  taxon_rank     text,
  iucn_category  text check (iucn_category in ('EX','EW','CR','EN','VU','NT','LC','DD','NE')),
  updated_at     timestamptz not null default now()
);
create index species_sciname_ix on species (lower(scientific_name));

-- Is a species introduced / invasive in a given country? Source: GRIIS.
-- "Native" is the absence of a row here, so there is no separate native flag to drift.
create table invasive_status (
  species_id          bigint not null references species (id) on delete cascade,
  country             char(2) not null,
  is_invasive         boolean,                -- null = introduced, invasiveness not assessed
  establishment_means text,
  occurrence_status   text,
  eicat_category      text check (eicat_category in ('NA','MC','MN','MO','MR','MV','DD','NE')),
  habitat             text,
  first_recorded_year smallint,
  source              text not null default 'GRIIS',
  source_ref          text,
  primary key (species_id, country)
);
create index invasive_status_invasive_ix on invasive_status (country) where is_invasive;

-- "Native species X is documented as threatened by invasive species Y."
-- Backbone of the impact analysis: IUCN threat code 8.1.2 (invasive, named species).
-- No inference involved; every row must carry a citation.
create table threat_links (
  id                 bigint generated always as identity primary key,
  native_species_id  bigint not null references species (id) on delete cascade,
  invasive_species_id bigint references species (id) on delete set null,
  invasive_name      text,                    -- as named in the assessment, if unresolved
  iucn_threat_code   text not null default '8.1.2',
  severity           text,
  scope              text,
  timing             text,
  assessment_year    smallint,
  citation           text not null check (length(trim(citation)) > 0)
);
create unique index threat_links_uq
  on threat_links (native_species_id, coalesce(invasive_species_id, 0),
                   coalesce(invasive_name, ''), iucn_threat_code);

create table model_versions (
  id          integer generated always as identity primary key,
  name        text not null,
  task        text not null check (task in ('detector', 'plant_classifier', 'animal_classifier')),
  weights_uri text,
  trained_at  timestamptz,
  metrics     jsonb not null default '{}',
  unique (name, task)
);

-- One row per image/frame/observation we have seen.
create table media_items (
  id          bigint generated always as identity primary key,
  source_id   smallint not null references sources (id),
  external_id text not null,
  uri         text not null,
  captured_at timestamptz,
  geom        geometry(Point, 4326),
  zone_id     integer references zones (id),
  phash       bigint,                          -- 64-bit perceptual hash, for near-duplicates
  width       integer,
  height      integer,
  license     text,
  status      text not null default 'new'
              check (status in ('new', 'processing', 'done', 'failed', 'skipped')),
  ingested_at timestamptz not null default now(),
  unique (source_id, external_id)              -- exact-duplicate guard
);
create index media_items_new_ix on media_items (id) where status = 'new';
create index media_items_zone_time_ix on media_items (zone_id, captured_at);
create index media_items_geom_gix on media_items using gist (geom);
create index media_items_phash_ix on media_items (phash) where phash is not null;

create table ingestion_runs (
  id           bigint generated always as identity primary key,
  source_id    smallint not null references sources (id),
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  fetched      integer not null default 0,
  skipped_dupe integer not null default 0,
  failed       integer not null default 0,
  notes        text
);

-- Control methods for each invasive species. Rule: no citation, no row.
create table mitigation_playbooks (
  id                bigint generated always as identity primary key,
  species_id        bigint not null references species (id) on delete cascade,
  method            text not null
                    check (method in ('mechanical','chemical','biological','cultural','fire','grazing','integrated')),
  description       text not null,
  effectiveness     text check (effectiveness in ('low','moderate','high','variable')),
  evidence_strength text check (evidence_strength in ('low','moderate','high')),
  season            text,
  cost_tier         text check (cost_tier in ('low','medium','high')),
  risks             text,
  failure_cases     text,                      -- documented cases where this backfired
  citation_text     text not null check (length(trim(citation_text)) > 0),
  citation_url      text
);
create index mitigation_species_ix on mitigation_playbooks (species_id);

create table alerts (
  id           bigint generated always as identity primary key,
  kind         text not null check (kind in ('edrr', 'spread', 'impact')),
  severity     text not null check (severity in ('low', 'medium', 'high')),
  zone_id      integer references zones (id),
  species_id   bigint references species (id),
  window_start timestamptz,
  window_end   timestamptz,
  score        double precision,
  evidence     jsonb not null default '{}',    -- why it fired, so the UI can show its work
  created_at   timestamptz not null default now()
);
create index alerts_kind_time_ix on alerts (kind, created_at desc);
