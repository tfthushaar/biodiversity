-- Applied once the dashboard that calls the old functions has been replaced.
--
-- hotspot_cells (squares of a fixed number of degrees) is replaced by hotspot_grid (squares of a
-- fixed number of kilometres, with filters), introduced in migration 0022.
drop function hotspot_cells(text, double precision, text);

-- Our own ratings of a management method (how well it worked, how strong the evidence, what it
-- costs, its risks and failure cases) are claims that no paper states, so the columns that held
-- them are removed. What a paper reports about a method is in the summary and its quotes.
alter table mitigation_playbooks
  drop column effectiveness,
  drop column evidence_strength,
  drop column cost_tier,
  drop column risks,
  drop column failure_cases,
  drop column season;
