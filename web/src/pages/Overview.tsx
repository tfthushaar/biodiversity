import { useAlerts, useReports, useZones } from "../api/hooks";
import type { ZoneReportRow } from "../api/types";
import { BarList, type BarItem } from "../components/charts";
import { Empty, ErrorState, Loading, StatTile } from "../components/basics";
import { Icon } from "../components/icons";
import { fmtInt, fmtPct, pluralise } from "../lib/format";

export function summarise(reports: ZoneReportRow[]) {
  const names = new Set<string>();
  let findings = 0;
  let insufficientCo = 0;
  let insufficientTrend = 0;
  for (const r of reports) {
    for (const s of r.report.invasive_species) names.add(s.species);
    findings += r.report.layers.documented.findings.length;
    insufficientCo += r.report.layers.cooccurrence.status === "insufficient" ? 1 : 0;
    insufficientTrend += r.report.layers.trend.status === "insufficient" ? 1 : 0;
  }
  return { invasiveSpecies: names.size, findings, insufficientCo, insufficientTrend, zones: reports.length };
}

const START = [
  {
    href: "#/hotspots",
    title: "Explore hotspots",
    text: "See where records concentrate in each park, and what the species there do to the local environment.",
  },
  {
    href: "#/species",
    title: "Look up a species",
    text: "Photos, cited research on effects, and the management options that have been tried.",
  },
  {
    href: "#/impact",
    title: "See what the data supports",
    text: "Which questions the records can answer today, and how much more data the others need.",
  },
];

export function Overview() {
  const zones = useZones();
  const reports = useReports();
  const alerts = useAlerts();

  return (
    <>
      <h1>Invasive species in protected landscapes</h1>
      <p className="lede">
        Where invasive plants and animals have been recorded in national parks in India, Tanzania and the
        United States, what published research reports about their effect on native species, and how they are
        managed. Every claim links to its evidence.
      </p>

      <nav className="start" aria-label="Where to start">
        {START.map((s) => (
          <a key={s.href} className="card" href={s.href}>
            <strong>{s.title}</strong>
            <span>{s.text}</span>
            <span className="go">
              Open <Icon name="arrow" />
            </span>
          </a>
        ))}
      </nav>

      <h2>The numbers</h2>
      <div className="banner" role="note">
        <Icon name="info" />
        <div>
          Counts reflect where people recorded species as well as where the species lives. Citizen-science
          photos under-record the plants that dominate these reserves: across the three Indian parks there are
          only a handful of <em>Lantana</em> and <em>Senna</em> records, though both are widely reported to be
          widespread. A low count can mean few observers. Statistics appear only when there is enough data, and
          otherwise the page shows how much more is needed. Details are on the <a href="#/sources">Sources</a> page.
        </div>
      </div>

      {zones.isError && !zones.data ? (
        <ErrorState error={zones.error} onRetry={() => void zones.refetch()} />
      ) : !zones.data ? (
        <Loading what="parks" />
      ) : (
        <ZoneOverview zones={zones.data.features.map((f) => f.properties)} reports={reports.data} alerts={alerts.data?.length} />
      )}
    </>
  );
}

function ZoneOverview({
  zones,
  reports,
  alerts,
}: {
  zones: { slug: string; name: string; observations: number; species: number; invasive_records: number; invasive_species: number }[];
  reports: ZoneReportRow[] | undefined;
  alerts: number | undefined;
}) {
  const obs = zones.reduce((a, z) => a + z.observations, 0);
  const inv = zones.reduce((a, z) => a + z.invasive_records, 0);
  const sum = reports ? summarise(reports) : null;

  const items: BarItem[] = zones
    .map((z) => ({
      key: z.slug,
      label: z.name,
      value: z.invasive_records,
      display: `${fmtInt(z.invasive_records)} of ${fmtInt(z.observations)}`,
      note: `${fmtPct(z.observations ? z.invasive_records / z.observations : 0)} of observations, ${pluralise(z.invasive_species, "invasive species", "invasive species")}`,
    }))
    .sort((a, b) => b.value - a.value);

  return (
    <>
      <div className="grid" aria-label="Headline numbers">
        <StatTile label="Observations" value={fmtInt(obs)} sub={`across ${zones.length} parks`} />
        <StatTile label="Invasive-species records" value={fmtInt(inv)} sub={obs ? `${fmtPct(inv / obs)} of observations` : undefined} />
        <StatTile
          label="Invasive species recorded"
          value={sum ? fmtInt(sum.invasiveSpecies) : "–"}
          sub="distinct, across all parks"
        />
        <StatTile
          label="Early-detection alerts"
          value={alerts == null ? "–" : fmtInt(alerts)}
          sub={alerts === 0 ? "none raised yet" : "see Alerts"}
        />
      </div>

      <h2>Invasive records by park</h2>
      <div className="card">
        <p className="hint" style={{ marginTop: 0 }}>
          Records of species that GRIIS lists as alien and invasive in the park's country, compared with all
          observations in the park. Serengeti has none because wildlife photos there rarely include
          introduced plants.
        </p>
        <BarList
          items={items}
          color="var(--invasive)"
          caption="Invasive-species records by park"
          valueLabel="Invasive records"
          max={Math.max(1, ...items.map((i) => i.value))}
        />
      </div>

      <h2>What the data supports</h2>
      {!sum ? (
        <Loading what="analysis" />
      ) : (
        <div className="grid">
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Reported findings</h3>
            <p className="muted small" style={{ margin: "0 0 8px" }}>
              What published sources report, quoted and cited.
            </p>
            <strong>{pluralise(sum.findings, "finding")}</strong> across the parks.
          </div>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Fewer native species where invaders are dense?</h3>
            <p className="muted small" style={{ margin: "0 0 8px" }}>
              Compares native species richness across map squares with different invasive densities.
            </p>
            <strong>
              {sum.insufficientCo === sum.zones ? "Not enough data" : `${sum.zones - sum.insufficientCo} of ${sum.zones} parks`}
            </strong>
            {sum.insufficientCo === sum.zones ? " in any park yet." : " have enough data."}
          </div>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Is the invasive share changing?</h3>
            <p className="muted small" style={{ margin: "0 0 8px" }}>
              Follows the invasive share of records, and the native share, year by year.
            </p>
            <strong>
              {sum.insufficientTrend === sum.zones ? "Not enough data" : `${sum.zones - sum.insufficientTrend} of ${sum.zones} parks`}
            </strong>
            {sum.insufficientTrend === sum.zones ? " in any park yet." : " have enough data."}
          </div>
        </div>
      )}
      <p style={{ marginTop: 14 }}>
        <a href="#/impact">See what each question needs</a>
      </p>

      {alerts === 0 && (
        <Empty>
          No early-detection alerts. An alert is raised when an invasive species is recorded in a park for the
          first time in the past year, after enough observation that its earlier absence means something.
        </Empty>
      )}
    </>
  );
}
