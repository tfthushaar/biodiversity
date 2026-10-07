-- Records of invasive species, and one summary row per zone and species.
--
-- "Invasive" means purely alien in the zone's country, flagged invasive by GRIIS. Species that
-- are native in part of the country, or of uncertain origin, are excluded (see migration 0008).
--
-- security_invoker makes each view obey the row-level security of whoever queries it, instead
-- of running with its owner's rights.
create view invasive_records with (security_invoker = true) as
select d.id        as detection_id,
       d.zone_id,
       d.species_id,
       d.captured_at,
       d.origin,
       m.source_id,
       m.geom
from detections d
join media_items m on m.id = d.media_item_id
join zones z on z.id = d.zone_id
join invasive_status i
  on i.species_id = d.species_id and i.country = z.country
 and i.is_invasive and i.origin_class = 'alien';

create view zone_invasive_summary with (security_invoker = true) as
select zone_id,
       species_id,
       count(*)                   as records,
       min(captured_at)           as first_record,
       max(captured_at)           as last_record,
       count(distinct source_id)  as sources
from invasive_records
group by zone_id, species_id;

revoke all on invasive_records, zone_invasive_summary from anon, authenticated;
grant select on invasive_records, zone_invasive_summary to anon, authenticated;

-- One 'first record' alert per zone and species, refreshed in place rather than duplicated.
create unique index alerts_edrr_uq on alerts (zone_id, species_id) where kind = 'edrr';
