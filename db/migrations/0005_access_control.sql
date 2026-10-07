-- The dashboard talks to Supabase's REST/GraphQL APIs with the public "anon" key, so anyone
-- can use it. It must be able to READ and nothing else. Writes come from workers using the
-- service role (which bypasses RLS). Supabase grants new objects to anon by default, so we
-- revoke explicitly rather than trust defaults.
do $$
declare t text;
begin
  foreach t in array array[
    'sources','zones','species','invasive_status','threat_links','model_versions',
    'media_items','ingestion_runs','mitigation_playbooks','alerts','detections'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
    execute format('grant select on public.%I to anon, authenticated', t);
    execute format('drop policy if exists public_read on public.%I', t);
    execute format(
      'create policy public_read on public.%I for select to anon, authenticated using (true)', t);
  end loop;
end
$$;

-- The default partition is not covered by the parent's grants when queried directly. Lock it.
alter table detections_default enable row level security;
revoke all on detections_default from anon, authenticated;

-- Materialized views do not support RLS; they hold only aggregates, so read-only is fine.
revoke all on invasion_index_monthly, native_trend_monthly from anon, authenticated;
grant select on invasion_index_monthly, native_trend_monthly to anon, authenticated;

-- Functions are executable by PUBLIC by default, which would expose them as RPC endpoints.
revoke execute on function refresh_rollups() from public, anon, authenticated;
revoke execute on function ensure_detection_partition(int) from public, anon, authenticated;
grant execute on function refresh_rollups() to service_role;
grant execute on function ensure_detection_partition(int) to service_role;
