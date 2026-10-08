-- Where invasive records concentrate.

-- hotspot_cells: invasive records grouped into square cells of p_cell degrees (0.02 is about 2 km),
-- with the species recorded in each cell. Grouping happens here so the dashboard downloads one row
-- per occupied cell instead of every record, which matters where a species has thousands of them.
-- p_species limits the result to one species by scientific name. The cell size is kept between
-- 0.005 and 0.5 degrees so a caller cannot ask for something expensive or meaningless.
create function hotspot_cells(
  p_zone text, p_cell double precision default 0.02, p_species text default null
) returns jsonb
language sql stable security invoker as $$
  with params as (
    select greatest(0.005, least(coalesce(p_cell, 0.02), 0.5)) as cell
  ),
  pts as (
    select r.species_id,
           extract(year from r.captured_at)::int as yr,
           st_x(r.geom) as lon,
           st_y(r.geom) as lat
    from invasive_records r
    join zones z on z.id = r.zone_id
    where z.slug = p_zone
      and (p_species is null
           or r.species_id in (select id from species where scientific_name = p_species))
  ),
  per_species as (
    select floor(lon / (select cell from params))::int as cx,
           floor(lat / (select cell from params))::int as cy,
           species_id,
           count(*) as n,
           min(yr) as first_year,
           max(yr) as last_year
    from pts
    group by 1, 2, 3
  ),
  per_cell as (
    select ps.cx, ps.cy,
           sum(ps.n)::int as records,
           count(*)::int as species_count,
           jsonb_agg(
             jsonb_build_object(
               'name', s.scientific_name, 'common_name', s.common_name, 'records', ps.n,
               'first_year', ps.first_year, 'last_year', ps.last_year)
             order by ps.n desc, s.scientific_name) as species
    from per_species ps
    join species s on s.id = ps.species_id
    group by 1, 2
  )
  select jsonb_build_object(
    'cell', (select cell from params),
    'cells', coalesce(jsonb_agg(
      jsonb_build_object(
        'west', c.cx * p.cell, 'south', c.cy * p.cell,
        'east', (c.cx + 1) * p.cell, 'north', (c.cy + 1) * p.cell,
        'records', c.records, 'species_count', c.species_count, 'species', c.species)
      order by c.records desc, c.cx, c.cy), '[]'::jsonb))
  from per_cell c cross join params p
$$;

revoke all on function hotspot_cells(text, double precision, text) from public;
grant execute on function hotspot_cells(text, double precision, text)
  to anon, authenticated, service_role;
