-- No paper, no row.
--
-- Every finding and every management option on the dashboard must rest on a peer-reviewed journal
-- article, identified by DOI, published in or after 2016, with verbatim quotes from it. Earlier
-- rows cited species profiles, news stories and fact sheets. They cannot be shown under this rule,
-- so they are removed here, and `python -m biodiv.workers.seed_knowledge --prune` adds back every
-- row in db/seeds/knowledge.json (each of which names a paper).
--
-- The rule is enforced by the schema, so a row entered by hand or by another tool cannot break it.
-- The public roles also see only rows whose quotes were checked against the paper
-- (scripts/verify_citations.py stamps verified_on), so an unchecked row stays out of view.

delete from mitigation_playbooks;
delete from impact_findings;

-- A study's design is part of its claim: a controlled experiment, a field comparison, a review of
-- other work, or a model projection. The dashboard shows it beside every claim.
alter table mitigation_playbooks
  add column citation_doi     text    not null,
  add column citation_year    integer not null,
  add column citation_journal text    not null,
  add column study_design     text    not null;

alter table impact_findings
  add column citation_doi     text    not null,
  add column citation_year    integer not null,
  add column citation_journal text    not null;

alter table mitigation_playbooks alter column citation_url set not null;

alter table mitigation_playbooks
  add constraint playbook_doi_shape check (citation_doi ~ '^10\.[0-9]{4,9}/\S+$'),
  add constraint playbook_recent    check (citation_year >= 2016),
  add constraint playbook_journal   check (length(trim(citation_journal)) > 0),
  add constraint playbook_design    check (study_design in
                                    ('experimental', 'observational', 'review', 'modelled'));

alter table impact_findings
  add constraint finding_doi_shape check (citation_doi ~ '^10\.[0-9]{4,9}/\S+$'),
  add constraint finding_recent    check (citation_year >= 2016),
  add constraint finding_journal   check (length(trim(citation_journal)) > 0);

-- 'detection' (finding the species, as in surveillance and early detection) joins the methods.
alter table mitigation_playbooks drop constraint mitigation_playbooks_method_check;
alter table mitigation_playbooks add constraint mitigation_playbooks_method_check
  check (method in ('mechanical', 'chemical', 'biological', 'cultural', 'fire', 'grazing',
                    'integrated', 'detection'));

-- The labels for certainty were 'preliminary' and 'unverified_concern' as well. A claim that is
-- not at least a published study design has no place here.
alter table impact_findings drop constraint impact_findings_certainty_check;
alter table impact_findings add constraint impact_findings_certainty_check
  check (certainty in ('experimental', 'observational', 'review', 'modelled'));

-- What the public sees: only rows whose quotes have been checked against the paper.
drop policy if exists public_read on mitigation_playbooks;
create policy public_read on mitigation_playbooks
  for select to anon, authenticated using (verified_on is not null);

drop policy if exists public_read on impact_findings;
create policy public_read on impact_findings
  for select to anon, authenticated using (verified_on is not null);
