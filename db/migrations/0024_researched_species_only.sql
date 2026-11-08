-- A species is shown as invasive only when a peer-reviewed paper backs a claim about it.
--
-- researched_species lists the species with at least one finding or management row whose quotes
-- were checked against the paper (migration 0020 requires a DOI, a journal and a year from 2016 on
-- for every such row). invasive_records, and with it every count, map, species list, report and
-- alert built on it, now holds only those species. A species GRIIS lists as invasive but that no
-- paper backs is not an invasive-species record here, and the ingest refuses it (see
-- scripts/prune_unresearched.py for the records stored earlier).
create view researched_species with (security_invoker = true) as
select invasive_species_id as species_id from impact_findings where verified_on is not null
union
select species_id from mitigation_playbooks where verified_on is not null;

revoke all on researched_species from anon, authenticated;
grant select on researched_species to anon, authenticated;

create or replace view invasive_records with (security_invoker = true) as
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
 and i.is_invasive and i.origin_class = 'alien'
join researched_species rs on rs.species_id = d.species_id;

-- The public roles see a species, and its invasive status, only when a paper backs it. Before,
-- the API listed every species ever recorded and every species on the GRIIS checklists.
drop policy if exists public_read on species;
create policy public_read on species for select to anon, authenticated
  using (id in (select species_id from researched_species));

drop policy if exists public_read on invasive_status;
create policy public_read on invasive_status for select to anon, authenticated
  using (species_id in (select species_id from researched_species));

-- Alerts about species no paper backs are removed, and the analysis no longer raises them.
delete from alerts
where species_id is not null and species_id not in (select species_id from researched_species);

-- Nothing on the dashboard reads these. They counted invasive records of every species, so the
-- public no longer reads them, and the individual-records function that the map once called is
-- gone with the layer it fed.
revoke select on invasion_index_monthly, native_trend_monthly from anon, authenticated;
drop function records_geojson(text, text, integer);
