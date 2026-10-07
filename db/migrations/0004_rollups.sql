-- Monthly rollups. These replace TimescaleDB continuous aggregates: refreshed by a scheduled
-- worker (refresh_rollups) rather than incrementally, which is fine at this data volume.
--
-- Observation effort = media items captured in the zone that month (empty camera-trap frames
-- count, they are effort too). Raw counts mislead: a zone with more cameras or observers looks
-- both more invaded and more biodiverse. The normalised index divides that out.

create materialized view invasion_index_monthly as
select d.zone_id,
       d.species_id,
       (date_trunc('month', d.captured_at at time zone 'UTC'))::date as month,
       count(*)                                                     as detections,
       e.effort,
       count(*)::double precision / nullif(e.effort, 0)             as normalised_index
from detections d
join zones z on z.id = d.zone_id
join invasive_status i on i.species_id = d.species_id and i.country = z.country and i.is_invasive
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

-- Native = not recorded as introduced in this zone's country.
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
  )
group by d.zone_id, d.species_id, 3, e.effort;
create unique index native_trend_monthly_uq on native_trend_monthly (zone_id, species_id, month);

create function refresh_rollups() returns void
language sql as $$
  refresh materialized view concurrently invasion_index_monthly;
  refresh materialized view concurrently native_trend_monthly;
$$;
