-- GRIIS is a COUNTRY-level checklist. Some species are native in part of a country and
-- introduced elsewhere in it. Chital (Axis axis) is "Native|Alien" in India: native on the
-- mainland, introduced to the Andaman Islands and flagged invasive THERE. Counting a Western
-- Ghats chital as an invasive-species detection would be plainly wrong, and a country list
-- cannot say where. So classify each record, and let only purely alien species drive the
-- invasion statistics.
--
--   alien     purely introduced in this country           -> counts as invasive if flagged
--   native    native here, or native in part of it        -> counts as native
--   uncertain cryptogenic / origin unknown                -> counts as neither
alter table invasive_status add column origin_class text generated always as (
  case
    when establishment_means ilike '%native%'      then 'native'
    when establishment_means ilike '%cryptogenic%'
      or establishment_means ilike '%uncertain%'   then 'uncertain'
    else 'alien'
  end
) stored;

-- Rebuild the rollups with the stricter definitions. Dropping a view drops its grants, so
-- they are restated at the end.
drop materialized view invasion_index_monthly;
drop materialized view native_trend_monthly;

create materialized view invasion_index_monthly as
select d.zone_id,
       d.species_id,
       (date_trunc('month', d.captured_at at time zone 'UTC'))::date as month,
       count(*)                                                     as detections,
       e.effort,
       count(*)::double precision / nullif(e.effort, 0)             as normalised_index
from detections d
join zones z on z.id = d.zone_id
join invasive_status i
  on i.species_id = d.species_id and i.country = z.country
 and i.is_invasive and i.origin_class = 'alien'
join (
  select zone_id,
         (date_trunc('month', captured_at at time zone 'UTC'))::date as month,
         count(*) as effort
  from media_items
  where zone_id is not null and captured_at is not null
  group by 1, 2
) e on e.zone_id = d.zone_id
   and e.month = (date_trunc('month', d.captured_at at time zone 'UTC'))::date
group by d.zone_id, d.species_id, 3, e.effort;
create unique index invasion_index_monthly_uq on invasion_index_monthly (zone_id, species_id, month);

-- Native = no GRIIS record, or a record that says it is also native here.
create materialized view native_trend_monthly as
select d.zone_id,
       d.species_id,
       (date_trunc('month', d.captured_at at time zone 'UTC'))::date as month,
       count(*)                                                     as detections,
       e.effort,
       count(*)::double precision / nullif(e.effort, 0)             as normalised_index
from detections d
join zones z on z.id = d.zone_id
join (
  select zone_id,
         (date_trunc('month', captured_at at time zone 'UTC'))::date as month,
         count(*) as effort
  from media_items
  where zone_id is not null and captured_at is not null
  group by 1, 2
) e on e.zone_id = d.zone_id
   and e.month = (date_trunc('month', d.captured_at at time zone 'UTC'))::date
where d.species_id is not null
  and not exists (
    select 1 from invasive_status i
    where i.species_id = d.species_id and i.country = z.country
      and i.origin_class in ('alien', 'uncertain')
  )
group by d.zone_id, d.species_id, 3, e.effort;
create unique index native_trend_monthly_uq on native_trend_monthly (zone_id, species_id, month);

revoke all on invasion_index_monthly, native_trend_monthly from anon, authenticated;
grant select on invasion_index_monthly, native_trend_monthly to anon, authenticated;
