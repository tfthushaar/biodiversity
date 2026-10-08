-- Migration 0013 revoked all access to PostGIS's spatial_ref_sys table from the public roles.
-- That broke something it should not: PostGIS looks up the coordinate system (srid 4326) in that
-- table whenever it turns a geometry column into JSON, so any public query that selected a
-- geometry column, such as GET /zones, failed with "permission denied for table spatial_ref_sys".
-- The smoke test missed it because it selected only non-geometry columns.
--
-- The fix is not to reopen the table but to expose exactly the row serialisation needs. Row-level
-- security shows the public roles the WGS84 (4326) definition and nothing else. The owner and the
-- service role are unaffected (the owner bypasses RLS, service_role has BYPASSRLS).
create or replace function restrict_postgis_functions() returns integer
language plpgsql as $$
declare
  f regprocedure;
  n integer := 0;
  allowed text[] := array['st_asgeojson', 'st_simplify', 'st_x', 'st_y'];
begin
  for f in
    select p.oid::regprocedure
    from pg_proc p
    join pg_depend d on d.objid = p.oid and d.classid = 'pg_proc'::regclass and d.deptype = 'e'
    join pg_extension e on e.oid = d.refobjid and e.extname = 'postgis'
    where p.pronamespace = 'public'::regnamespace
  loop
    execute format('revoke execute on function %s from public, anon, authenticated', f);
    n := n + 1;
  end loop;

  for f in
    select p.oid::regprocedure
    from pg_proc p
    join pg_depend d on d.objid = p.oid and d.classid = 'pg_proc'::regclass and d.deptype = 'e'
    join pg_extension e on e.oid = d.refobjid and e.extname = 'postgis'
    where p.pronamespace = 'public'::regnamespace and p.proname = any (allowed)
  loop
    execute format('grant execute on function %s to anon, authenticated', f);
  end loop;

  -- PostGIS grants its reference tables to PUBLIC, so PUBLIC must be revoked. Public roles then
  -- get back only the single row that geometry-to-JSON conversion reads.
  -- Only where the table is in `public`: that is the schema the REST API publishes. On Supabase
  -- PostGIS lives in `extensions` (see biodiv.workers.migrate), which is not published, and the
  -- table belongs to a role we cannot alter.
  if to_regclass('public.spatial_ref_sys') is not null then
    revoke all on public.spatial_ref_sys from public, anon, authenticated;
    grant select on public.spatial_ref_sys to anon, authenticated, service_role;
    alter table public.spatial_ref_sys enable row level security;
    drop policy if exists public_wgs84_only on public.spatial_ref_sys;
    create policy public_wgs84_only on public.spatial_ref_sys
      for select to anon, authenticated using (srid = 4326);
  end if;

  if to_regclass('public.geometry_columns') is not null then
    revoke all on geometry_columns, geography_columns from public, anon, authenticated;
  end if;
  return n;
end
$$;

select restrict_postgis_functions();
