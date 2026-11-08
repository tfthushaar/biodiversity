-- Remove data that nothing on the platform shows or may show.
--
-- threat_links held 4,362 links between invasive and threatened native species from the IUCN Red
-- List. IUCN's terms forbid redistributing its data without written permission, so migration 0017
-- hid every row from the public API, and no page, report or analysis read them. Data we store and
-- cannot show has no use here, so the table goes, and the importer with it.
--
-- species.iucn_category was part of the same design and was never filled.
--
-- Run with a lock timeout (PGOPTIONS="-c lock_timeout=4000") while no ingest is running: dropping
-- a column takes a lock on species.

drop table threat_links;
alter table species drop column iucn_category;
