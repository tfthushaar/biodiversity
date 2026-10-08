-- How full the free-tier database is. The Sources page shows it, and the workers refuse to add data
-- when it is nearly full, because Supabase's free plan puts a project into read-only mode at its
-- 500 MB limit and that would stop every later run.
--
-- security definer, because pg_database_size needs privileges the public role does not have.
-- It returns two numbers and nothing else.
create function storage_status() returns jsonb
language sql stable security definer set search_path = pg_catalog as $$
  select jsonb_build_object(
    'db_bytes', pg_database_size(current_database()),
    'budget_bytes', 500 * 1024 * 1024
  )
$$;
revoke all on function storage_status() from public;
grant execute on function storage_status() to anon, authenticated, service_role;
