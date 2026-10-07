-- What the dashboard reads. Everything here is read-only and public: Supabase serves it through
-- its generated REST API with the anon key, so the dashboard needs no server of ours.

-- The full per-zone report (documented findings, co-occurrence, trend), precomputed by the
-- analyse worker. Computed on a schedule rather than per request: the free API host sleeps, and
-- the numbers only change when new data arrives.
create table zone_reports (
  zone_id     integer primary key references zones (id) on delete cascade,
  report      jsonb not null,
  computed_at timestamptz not null default now()
);
alter table zone_reports enable row level security;
revoke all on zone_reports from anon, authenticated;
grant select on zone_reports to anon, authenticated;
create policy public_read on zone_reports for select to anon, authenticated using (true);

-- Health of each data source, for the dashboard's Sources view: what it is, its licence, and how
-- its latest run went, including why records were refused.
create view source_health with (security_invoker = true) as
select s.id, s.name, s.kind, s.license, s.attribution, s.base_url,
       r.finished_at as last_run, r.fetched, r.skipped_dupe, r.failed, r.rejected,
       (select count(*) from media_items m where m.source_id = s.id) as items
from sources s
left join lateral (
  select * from ingestion_runs ir
  where ir.source_id = s.id and ir.finished_at is not null
  order by ir.finished_at desc limit 1
) r on true;
revoke all on source_health from anon, authenticated;
grant select on source_health to anon, authenticated;

-- Zones as GeoJSON with headline counts. Boundaries are lightly simplified for the map.
create function zones_geojson() returns jsonb
language sql stable security invoker as $$
  select jsonb_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(jsonb_agg(jsonb_build_object(
      'type', 'Feature',
      'id', z.id,
      'geometry', st_asgeojson(st_simplify(z.geom, 0.0005))::jsonb,
      'properties', jsonb_build_object(
        'slug', z.slug, 'name', z.name, 'group', z.group_name, 'country', z.country,
        'observations', (select count(*) from detections d where d.zone_id = z.id),
        'species', (select count(distinct species_id) from detections d where d.zone_id = z.id),
        'invasive_records', (select count(*) from invasive_records r where r.zone_id = z.id),
        'invasive_species',
          (select count(distinct species_id) from invasive_records r where r.zone_id = z.id)
      )
    ) order by z.id), '[]'::jsonb)
  )
  from zones z
$$;

-- Sightings as GeoJSON points. kind = 'invasive' (default) or 'all'. Capped, because a map
-- cannot usefully draw more and a public endpoint should not stream a whole table.
create function records_geojson(
  p_zone text default null, p_kind text default 'invasive', p_limit integer default 2000
) returns jsonb
language sql stable security invoker as $$
  select jsonb_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(jsonb_agg(f.feature), '[]'::jsonb)
  )
  from (
    select jsonb_build_object(
      'type', 'Feature',
      'geometry', st_asgeojson(m.geom)::jsonb,
      'properties', jsonb_build_object(
        'species', s.scientific_name, 'common_name', s.common_name,
        'zone', z.slug, 'captured_at', d.captured_at, 'origin', d.origin,
        'class', case
          when i.is_invasive and i.origin_class = 'alien' then 'invasive'
          when i.origin_class in ('alien', 'uncertain') then 'introduced'
          else 'native' end,
        'url', m.uri)
    ) as feature
    from detections d
    join media_items m on m.id = d.media_item_id
    join species s on s.id = d.species_id
    join zones z on z.id = d.zone_id
    left join invasive_status i on i.species_id = d.species_id and i.country = z.country
    where m.geom is not null
      and (p_zone is null or z.slug = p_zone)
      and (p_kind = 'all' or (i.is_invasive and i.origin_class = 'alien'))
    order by d.captured_at desc
    limit least(greatest(p_limit, 1), 5000)
  ) f
$$;

-- Functions are executable by PUBLIC by default; say exactly who may call these.
revoke execute on function zones_geojson() from public;
revoke execute on function records_geojson(text, text, integer) from public;
grant execute on function zones_geojson() to anon, authenticated, service_role;
grant execute on function records_geojson(text, text, integer) to anon, authenticated, service_role;
