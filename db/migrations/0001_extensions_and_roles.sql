-- PostGIS for spatial queries ("all sightings inside this reserve boundary").
create extension if not exists postgis;

-- Supabase already provides these roles. Create them only on plain Postgres
-- (local Docker, CI) so the access-control migration behaves the same everywhere.
do $$
begin
  if not exists (select from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end
$$;
