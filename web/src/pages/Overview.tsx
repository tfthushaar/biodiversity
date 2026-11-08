import { useFindings, useInvasiveByYear, usePlaybooks, useReports, useZones } from "../api/hooks";
import type { ZoneReportRow } from "../api/types";
import { BarList, ColumnChart, type BarItem } from "../components/charts";
import { ErrorState, Loading, StatTile } from "../components/basics";
import { fmtInt, pluralise } from "../lib/format";

/** Distinct invasive species recorded across the parks. */
export function summarise(reports: ZoneReportRow[]) {
  const names = new Set<string>();
  for (const r of reports) for (const s of r.report.invasive_species) names.add(s.species);
  return { invasiveSpecies: names.size, zones: reports.length };
}

/** Records per species summed over every park, most recorded first. */
export function topSpecies(reports: ZoneReportRow[], n = 10): BarItem[] {
  const by = new Map<string, { common: string | null; records: number }>();
  for (const r of reports) {
    for (const s of r.report.invasive_species) {
      const have = by.get(s.species);
      by.set(s.species, { common: s.common_name ?? have?.common ?? null, records: (have?.records ?? 0) + s.records });
    }
  }
  return [...by.entries()]
    .sort((a, b) => b[1].records - a[1].records || a[0].localeCompare(b[0]))
    .slice(0, n)
    .map(([name, v]) => ({ key: name, label: v.common ?? name, value: v.records, note: v.common ? name : undefined }));
}

export function Overview() {
  const zones = useZones();
  const reports = useReports();
  const findings = useFindings();
  const playbooks = usePlaybooks();
  const years = useInvasiveByYear(null);

  const papers =
    findings.data && playbooks.data
      ? new Set([...findings.data, ...playbooks.data].map((x) => x.citation_doi)).size
      : null;

  return (
    <>
      <h1>Invasive species in protected landscapes</h1>
      <p className="lede">
        Where invasive species have been recorded in six national parks, and what peer-reviewed papers report
        about their effect on native species and how they are managed. A species appears only when a paper
        reports on it. Counts show where people recorded species as well as where a species lives. See{" "}
        <a href="#/sources">Sources</a> for the limits.
      </p>

      {zones.isError && !zones.data ? (
        <ErrorState error={zones.error} onRetry={() => void zones.refetch()} />
      ) : !zones.data ? (
        <Loading what="parks" />
      ) : (
        <ZoneOverview
          zones={zones.data.features.map((f) => f.properties)}
          reports={reports.data}
          papers={papers}
          byYear={years.data}
        />
      )}
    </>
  );
}

function ZoneOverview({
  zones,
  reports,
  papers,
  byYear,
}: {
  zones: { slug: string; name: string; observations: number; species: number; invasive_records: number; invasive_species: number }[];
  reports: ZoneReportRow[] | undefined;
  papers: number | null;
  byYear: { year: number; records: number }[] | undefined;
}) {
  const inv = zones.reduce((a, z) => a + z.invasive_records, 0);
  const sum = reports ? summarise(reports) : null;

  const items: BarItem[] = zones
    .map((z) => ({
      key: z.slug,
      label: z.name,
      value: z.invasive_records,
      note: pluralise(z.invasive_species, "invasive species", "invasive species"),
    }))
    .sort((a, b) => b.value - a.value);

  return (
    <>
      <div className="grid" aria-label="Headline numbers">
        <StatTile label="Invasive-species records" value={fmtInt(inv)} sub={`across ${zones.length} parks`} />
        <StatTile label="Invasive species" value={sum ? fmtInt(sum.invasiveSpecies) : "–"} sub="each backed by a paper" />
        <StatTile label="Peer-reviewed papers" value={papers == null ? "–" : fmtInt(papers)} sub="behind every finding shown" />
      </div>

      <div className="grid charts">
        <section className="card" aria-label="Invasive records by park">
          <h2>By park</h2>
          <BarList
            items={items}
            color="var(--invasive)"
            caption="Invasive-species records by park"
            valueLabel="Invasive records"
            max={Math.max(1, ...items.map((i) => i.value))}
          />
        </section>
        <section className="card" aria-label="Invasive records by year">
          <h2>By year</h2>
          {byYear ? <ColumnChart data={byYear} caption="Invasive-species records by year, all parks" /> : <Loading what="years" />}
        </section>
        <section className="card" aria-label="Most recorded invasive species">
          <h2>Most recorded species</h2>
          {reports ? (
            <BarList items={topSpecies(reports)} color="var(--invasive)" caption="Most recorded invasive species, all parks" valueLabel="Records" />
          ) : (
            <Loading what="species" />
          )}
        </section>
      </div>
    </>
  );
}
