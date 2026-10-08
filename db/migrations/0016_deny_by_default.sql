-- Public access is deny-by-default, whatever the host's default privileges are.
--
-- On plain Postgres a new table is private. On Supabase, default privileges hand every new table,
-- sequence and function in `public` to the public roles (anon, authenticated) with full rights, so
-- anything we create is world-writable unless something takes it back. Migration 0005 did that for
-- the tables that existed then; this does it for everything, and for everything created later.
-- Found by auditing a live Supabase project: schema_migrations (created by the migration runner,
-- outside 0005's list) was left with insert, update, delete and truncate for anon. Row-level
-- security, which Supabase turns on automatically, hid the rows, but truncate ignores it.
--
-- This only removes rights. What the dashboard reads keeps its explicit grants (0005, 0012, 0015),
-- and the workers connect as the owner, who is unaffected.

-- Nothing public may write, on any table, view or partition that exists now.
revoke insert, update, delete, truncate, references, trigger
  on all tables in schema public from anon, authenticated;

-- Migration bookkeeping is not public at all.
revoke all on schema_migrations from anon, authenticated;

-- The public roles never need to advance a sequence.
revoke all on all sequences in schema public from anon, authenticated;

-- New objects start private: each migration must grant what it means to publish.
alter default privileges in schema public
  revoke all on tables from anon, authenticated;
alter default privileges in schema public
  revoke all on sequences from anon, authenticated;
alter default privileges in schema public
  revoke execute on functions from public, anon, authenticated;
