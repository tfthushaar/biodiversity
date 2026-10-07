-- Local development only: the roles Supabase provides, so the same migrations and the same
-- PostgREST behaviour apply here as in production.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create role authenticator login password 'dev' noinherit;
grant anon, authenticated, service_role to authenticator;
