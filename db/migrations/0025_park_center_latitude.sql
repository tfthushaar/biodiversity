-- The public role may not call most PostGIS functions (migration 0013), and hotspot_grid called
-- st_centroid to find the latitude at which to size its squares. That works on Supabase, where
-- PostGIS lives in its own schema, and fails on a plain Postgres where the lockdown applies. The
-- latitude of each park's centre is now a column the table's owner computes once, and
-- hotspot_grid reads the column.
alter table zones
  add column center_lat double precision generated always as (st_y(st_centroid(geom))) stored;

create or replace function hotspot_grid(
  p_zone      text,
  p_km        double precision default 2,
  p_species   text default null,
  p_sources   text default null,  -- source names, comma separated
  p_year_from integer default null,
  p_year_to   integer default null,
  p_kingdom   text default null
) returns jsonb
language sql stable security invoker as $$
  with grid as (
    select z.id as zone_id,
           greatest(0.5, least(coalesce(p_km, 2), 50)) as km,
           z.center_lat as lat0
    from zones z
    where z.slug = p_zone
  ),
  steps as (
    select zone_id, km,
           km / 110.574 as dlat,
           km / (111.320 * cos(radians(lat0))) as dlon
    from grid
  ),
  pts as (
    select r.species_id,
           sr.name as source_name,
           extract(year from r.captured_at)::int as yr,
           floor(st_x(r.geom) / s.dlon)::int as cx,
           floor(st_y(r.geom) / s.dlat)::int as cy
    from steps s
    join invasive_records r on r.zone_id = s.zone_id
    join sources sr on sr.id = r.source_id
    join species sp on sp.id = r.species_id
    where (p_species is null or sp.scientific_name = p_species)
      and (p_sources is null or sr.name = any(string_to_array(p_sources, ',')))
      and (p_year_from is null or extract(year from r.captured_at) >= p_year_from)
      and (p_year_to is null or extract(year from r.captured_at) <= p_year_to)
      and (p_kingdom is null or sp.kingdom = p_kingdom)
  ),
  per_species as (
    select cx, cy, species_id,
           count(*) as n, min(yr) as first_year, max(yr) as last_year
    from pts
    group by 1, 2, 3
  ),
  species_json as (
    select ps.cx, ps.cy,
           sum(ps.n)::int as records,
           count(*)::int as species_count,
           jsonb_agg(
             jsonb_build_object(
               'name', s.scientific_name, 'common_name', s.common_name, 'kingdom', s.kingdom,
               'records', ps.n, 'first_year', ps.first_year, 'last_year', ps.last_year)
             order by ps.n desc, s.scientific_name) as species
    from per_species ps
    join species s on s.id = ps.species_id
    group by 1, 2
  ),
  years_json as (
    select cx, cy, jsonb_agg(jsonb_build_array(yr, n) order by yr) as by_year
    from (select cx, cy, yr, count(*) as n from pts group by 1, 2, 3) y
    group by 1, 2
  ),
  sources_json as (
    select cx, cy, jsonb_object_agg(source_name, n) as by_source
    from (select cx, cy, source_name, count(*) as n from pts group by 1, 2, 3) q
    group by 1, 2
  )
  select jsonb_build_object(
    'km', (select km from steps),
    'cells', coalesce(jsonb_agg(
      jsonb_build_object(
        'west', c.cx * st.dlon, 'south', c.cy * st.dlat,
        'east', (c.cx + 1) * st.dlon, 'north', (c.cy + 1) * st.dlat,
        'records', c.records, 'species_count', c.species_count, 'species', c.species,
        'by_year', y.by_year, 'by_source', so.by_source)
      order by c.records desc, c.cx, c.cy), '[]'::jsonb))
  from species_json c
  cross join steps st
  join years_json y on y.cx = c.cx and y.cy = c.cy
  join sources_json so on so.cx = c.cx and so.cy = c.cy
$$;
