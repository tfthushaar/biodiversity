-- Hotspots in true squares, with filters, and the summaries the charts read.

-- hotspot_cells grouped records into squares of a fixed number of degrees. A degree of longitude
-- is shorter than a degree of latitude away from the equator (about 19% shorter at 35 degrees
-- north), so those "squares" were narrow rectangles in the Great Smoky Mountains. The grid is now
-- set in kilometres and converted to degrees at the park's own latitude, so every cell is square
-- to within a percent and its size is the size the dashboard states.
--
-- The new function is hotspot_grid. hotspot_cells stays until the dashboard that calls it has been
-- replaced (migration 0023 removes it).
--
-- The filters narrow what is counted: one species, one or more sources, a range of years, one
-- kingdom. Each cell also carries its records by year and by source, so the dashboard can chart
-- any group of cells (a square, the map view, the whole park) without another request.
create function hotspot_grid(
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
           st_y(st_centroid(z.geom)) as lat0
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

revoke all on function hotspot_grid(text, double precision, text, text, integer, integer, text)
  from public;
grant execute on function hotspot_grid(text, double precision, text, text, integer, integer, text)
  to anon, authenticated, service_role;

-- Invasive records per year and per source, for one park or for all of them, and optionally for
-- one species. Feeds the "records over time" charts without sending every record to the browser.
create function invasive_by_year(p_zone text default null, p_species text default null)
returns jsonb
language sql stable security invoker as $$
  select coalesce(jsonb_agg(
           jsonb_build_object('year', yr, 'records', n) order by yr), '[]'::jsonb)
  from (
    select extract(year from r.captured_at)::int as yr, count(*) as n
    from invasive_records r
    join zones z on z.id = r.zone_id
    join species sp on sp.id = r.species_id
    where (p_zone is null or z.slug = p_zone)
      and (p_species is null or sp.scientific_name = p_species)
    group by 1
  ) y
$$;

revoke all on function invasive_by_year(text, text) from public;
grant execute on function invasive_by_year(text, text) to anon, authenticated, service_role;

-- Everything the species page charts for one species: its records by park, by year and by source.
create function species_profile(p_species text) returns jsonb
language sql stable security invoker as $$
  with recs as (
    select z.slug, z.name as park, sr.name as source_name,
           extract(year from r.captured_at)::int as yr
    from invasive_records r
    join species sp on sp.id = r.species_id
    join zones z on z.id = r.zone_id
    join sources sr on sr.id = r.source_id
    where sp.scientific_name = p_species
  )
  select jsonb_build_object(
    'records', (select count(*) from recs),
    'first_year', (select min(yr) from recs),
    'last_year', (select max(yr) from recs),
    'by_park', coalesce((select jsonb_agg(jsonb_build_object(
                  'slug', slug, 'park', park, 'records', n) order by n desc, park)
                from (select slug, park, count(*) as n from recs group by 1, 2) a), '[]'::jsonb),
    'by_year', coalesce((select jsonb_agg(jsonb_build_object('year', yr, 'records', n) order by yr)
                from (select yr, count(*) as n from recs group by 1) b), '[]'::jsonb),
    'by_source', coalesce((select jsonb_agg(jsonb_build_object(
                  'source', source_name, 'records', n) order by n desc)
                from (select source_name, count(*) as n from recs group by 1) c), '[]'::jsonb))
$$;

revoke all on function species_profile(text) from public;
grant execute on function species_profile(text) to anon, authenticated, service_role;
