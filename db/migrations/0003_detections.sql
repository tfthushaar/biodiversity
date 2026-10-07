-- Every detection (species, location, time, confidence) as a structured record,
-- time-partitioned so trend queries stay fast as the log grows.
--
-- Native yearly partitioning instead of TimescaleDB: Supabase deprecates that extension
-- on Postgres 17, and pg_partman is not guaranteed on the free tier. Camera-trap archives
-- carry their original (often decade-old) timestamps, so partitions are per year.
create sequence detections_id_seq;

create table detections (
  id               bigint not null default nextval('detections_id_seq'),
  media_item_id    bigint not null references media_items (id) on delete cascade,
  captured_at      timestamptz not null,
  species_id       bigint references species (id),
  label_raw        text,                       -- classifier output before taxonomy matching
  confidence       real not null check (confidence >= 0 and confidence <= 1),
  bbox             jsonb,                      -- x, y, w, h normalised to 0-1
  model_version_id integer references model_versions (id),
  geom             geometry(Point, 4326),
  zone_id          integer references zones (id),
  thumb_path       text,
  primary key (id, captured_at)
) partition by range (captured_at);
alter sequence detections_id_seq owned by detections.id;

-- Safety net: rows outside every yearly partition land here instead of failing.
create table detections_default partition of detections default;

create index detections_species_time_ix on detections (species_id, captured_at);
create index detections_zone_time_ix on detections (zone_id, captured_at);
create index detections_media_ix on detections (media_item_id);
create index detections_geom_gix on detections using gist (geom);
create index detections_time_brin on detections using brin (captured_at);

-- Create the partition for a year if it is missing. Call this before inserting rows for a
-- new year: Postgres refuses to create a partition that overlaps rows already sitting in
-- the default partition.
create function ensure_detection_partition(p_year int) returns text
language plpgsql as $$
declare
  part   text := format('detections_%s', p_year);
  v_from timestamptz := make_timestamptz(p_year, 1, 1, 0, 0, 0, 'UTC');
  v_to   timestamptz := make_timestamptz(p_year + 1, 1, 1, 0, 0, 0, 'UTC');
begin
  if to_regclass(format('public.%I', part)) is null then
    execute format(
      'create table public.%I partition of public.detections for values from (%L) to (%L)',
      part, v_from, v_to);
    -- Supabase grants new tables to anon by default, and a partition is directly queryable
    -- through the API. Lock it down: RLS on, no policies, no grants.
    execute format('alter table public.%I enable row level security', part);
    execute format('revoke all on public.%I from anon, authenticated', part);
  end if;
  return part;
end
$$;

select ensure_detection_partition(y) from generate_series(2000, 2030) as y;
