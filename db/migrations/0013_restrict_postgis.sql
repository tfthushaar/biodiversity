-- PostGIS installs about a thousand functions into the public schema, and Postgres makes new
-- functions executable by everyone. Supabase's REST API publishes public-schema functions as
-- endpoints, so an anonymous visitor could call any of them: confirmed, an unauthenticated
-- request to /rpc/postgis_full_version returned the server's library versions, and heavy
-- geometry functions (buffers, unions) would run on attacker-chosen input.
--
-- Default deny: remove every PostGIS function from the public-facing roles, then allow back the
-- handful that the public views and functions in this schema genuinely use.
--
-- A PostGIS upgrade (ALTER EXTENSION postgis UPDATE) can add new functions with default
-- privileges, so this is a function: run `select restrict_postgis_functions()` again afterwards.
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

  -- Reference tables PostGIS adds to public; nothing the dashboard needs. PostGIS grants them to
  -- PUBLIC, so revoking from anon alone would change nothing: they must be revoked from PUBLIC.
  -- Our own workers connect as the owner, which keeps access.
  -- Only where they are in `public`, the schema the REST API publishes (on Supabase PostGIS is in
  -- `extensions`, see biodiv.workers.migrate).
  if to_regclass('public.spatial_ref_sys') is not null then
    revoke all on public.spatial_ref_sys from public, anon, authenticated;
  end if;
  if to_regclass('public.geometry_columns') is not null then
    revoke all on geometry_columns, geography_columns from public, anon, authenticated;
  end if;
  if to_regclass('public.spatial_ref_sys') is not null then
    grant select on public.spatial_ref_sys to service_role;
  end if;
  return n;
end
$$;

revoke execute on function restrict_postgis_functions() from public, anon, authenticated;
select restrict_postgis_functions();
