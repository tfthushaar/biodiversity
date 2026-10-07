import { useAlerts, useReports, useZones } from "../api/hooks";
import type { ZoneReportRow } from "../api/types";
import { BarList, type BarItem } from "../components/charts";
import { Empty, ErrorState, Loading, StatTile } from "../components/basics";
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

export function Overview() {
  const zones = useZones();
  const reports = useReports();
  const alerts = useAlerts();

  return (
    <>
      <h1>Invasive species and their effect on native ecosystems</h1>
      <p className="lede">
        Where invasive plants and animals have been recorded in four protected landscapes, what published
        research says they do to the native species there, and what has been tried to manage them, with
        the evidence for every claim.
      </p>

      <div className="banner" role="note">
        <span aria-hidden="true">ⓘ</span>
        <div>
          <strong>Read counts as recorded presence, not abundance.</strong> Most records here come from
          citizen-science photos, which badly under-record the plants that dominate these reserves: across
          three Indian reserves there are only a handful of <em>Lantana</em> and <em>Senna</em> records, though both
          are widely reported to be widespread. Where the data is too thin to support a statistic, this
          dashboard says so instead of showing one. <a href="#/sources">See what the data can and cannot say</a>.
        </div>
      </div>

      {zones.isError && !zones.data ? (
        <ErrorState error={zones.error} onRetry={() => void zones.refetch()} />
      ) : !zones.data ? (
        <Loading what="zones" />
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
      note: `${fmtPct(z.observations ? z.invasive_records / z.observations : 0)} of observations · ${pluralise(z.invasive_species, "invasive species", "invasive species")}`,
    }))
    .sort((a, b) => b.value - a.value);

  return (
    <>
      <div className="grid" aria-label="Headline numbers">
        <StatTile label="Observations" value={fmtInt(obs)} sub={`across ${zones.length} zones`} />
        <StatTile label="Invasive-species records" value={fmtInt(inv)} sub={obs ? `${fmtPct(inv / obs)} of observations` : undefined} />
        <StatTile
          label="Invasive species recorded"
          value={sum ? fmtInt(sum.invasiveSpecies) : "–"}
          sub="distinct, across all zones"
        />
        <StatTile
          label="Early-detection alerts"
          value={alerts == null ? "–" : fmtInt(alerts)}
          sub={alerts === 0 ? "none raised yet" : "see Alerts"}
        />
      </div>

      <h2>Invasive records by zone</h2>
      <div className="card">
        <p className="hint" style={{ marginTop: 0 }}>
          Records of species that are purely alien and flagged invasive, against all observations in the
          zone. Serengeti has none because wildlife photos there rarely include introduced plants, not
          because it is free of them.
        </p>
        <BarList
          items={items}
          color="var(--invasive)"
          caption="Invasive-species records by zone"
          valueLabel="Invasive records"
          max={Math.max(1, ...items.map((i) => i.value))}
        />
      </div>

      <h2>What the data can support</h2>
      {!sum ? (
        <Loading what="analysis" />
      ) : (
        <div className="grid">
          <div className="card">
            <h3>1 · Documented findings</h3>
            <p className="muted small" style={{ margin: "0 0 8px" }}>
              What published sources report, quoted and cited. No inference by us.
            </p>
            <strong>{pluralise(sum.findings, "finding")}</strong> across the zones.
          </div>
          <div className="card">
            <h3>2 · Co-occurrence</h3>
            <p className="muted small" style={{ margin: "0 0 8px" }}>
              Is native richness lower where invasives are denser?
            </p>
            <strong>
              {sum.insufficientCo === sum.zones ? "Not enough data" : `${sum.zones - sum.insufficientCo} of ${sum.zones} zones`}
            </strong>
            {sum.insufficientCo === sum.zones ? " in any zone yet." : " have enough data."}
          </div>
          <div className="card">
            <h3>3 · Trend</h3>
            <p className="muted small" style={{ margin: "0 0 8px" }}>
              Is the invasive share rising while natives fall?
            </p>
            <strong>
              {sum.insufficientTrend === sum.zones ? "Not enough data" : `${sum.zones - sum.insufficientTrend} of ${sum.zones} zones`}
            </strong>
            {sum.insufficientTrend === sum.zones ? " in any zone yet." : " have enough data."}
          </div>
        </div>
      )}
      <p style={{ marginTop: 14 }}>
        <a href="#/impact">See each layer, and exactly how much more data it needs →</a>
      </p>

      {alerts === 0 && (
        <Empty>
          No early-detection alerts. An alert means an invasive species was recorded in a zone for the
          first time, in the past year, after enough observation that its absence earlier means something.
        </Empty>
      )}
    </>
  );
}
