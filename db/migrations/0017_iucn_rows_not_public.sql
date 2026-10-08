-- IUCN Red List data is not ours to republish.
--
-- IUCN's terms of use (https://www.iucnredlist.org/terms/terms-of-use) allow its data to be used
-- for conservation, education, scientific analysis and research, but prohibit "reposting,
-- sub-licensing, reselling, or other forms of redistribution of IUCN Red List Data ... whole or in
-- part, alone or combined with other data, including within Derivative Works" without IUCN's prior
-- written permission, and they require a permission waiver for derivative works.
--
-- This database is readable by anyone through its public REST API, which is redistribution. So
-- rows that come from IUCN are stored (our own analysis can use them) but hidden from the public
-- roles. Rows from cited published literature stay public.
--
-- To publish the IUCN rows once IUCN has given written permission: add a migration that replaces
-- this policy with `using (true)`, and add IUCN's required acknowledgement and Red List version
-- wherever they appear (see docs/iucn.md).
--
-- The owner and the service role are unaffected, so the workers still see every row. Any future
-- API endpoint that reads threat_links as the owner must filter evidence_source itself.
drop policy if exists public_read on threat_links;
create policy public_read on threat_links
  for select to anon, authenticated
  using (evidence_source <> 'iucn');
