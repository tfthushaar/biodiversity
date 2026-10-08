import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useReports } from "../api/hooks";
import type { LayerResult, ReportFinding, ZoneReport } from "../api/types";
import { Empty, ErrorState, Loading, Meter } from "../components/basics";
import { FindingCard } from "../components/cards";
import { fmtAgo, fmtInt } from "../lib/format";
import { linear } from "../lib/scale";

const num = (d: Record<string, unknown>, k: string): number => (typeof d[k] === "number" ? (d[k] as number) : 0);

export function Impact() {
  const reports = useReports();
  const [slug, setSlug] = useState<string | null>(null);

  const rows = reports.data;
  const first = useMemo(() => {
    if (!rows?.length) return null;
    // Default to the zone with the most to say.
    return [...rows].sort((a, b) => b.report.invasive_species.length - a.report.invasive_species.length)[0] ?? null;
  }, [rows]);
  useEffect(() => {
    if (!slug && first) setSlug(first.zones.slug);
  }, [slug, first]);

  const current = rows?.find((r) => r.zones.slug === slug) ?? null;

  return (
    <>
      <h1>Impact on native ecosystems</h1>
      <p className="lede">
        Three questions, from the most certain to the least. The first reports what cited sources say. The
        other two are statistics that give an answer only once there is enough data to support one.
      </p>

      {reports.isError && !rows ? (
        <ErrorState error={reports.error} onRetry={() => void reports.refetch()} />
      ) : !rows ? (
        <Loading what="the analysis" />
      ) : rows.length === 0 ? (
        <Empty>No analysis has been computed yet. It is refreshed by a scheduled job after each data update.</Empty>
      ) : (
        <>
          <div className="filters" role="group" aria-label="Impact filters">
            <label>
              Zone
              <select value={slug ?? ""} onChange={(e) => setSlug(e.target.value)}>
                {rows.map((r) => (
                  <option key={r.zones.slug} value={r.zones.slug}>
                    {r.zones.name}
                  </option>
                ))}
              </select>
            </label>
            {current && <span className="hint">Analysis computed {fmtAgo(current.computed_at)}</span>}
          </div>
          {current && <ZoneLayers report={current.report} name={current.zones.name} />}
        </>
      )}
    </>
  );
}

function ZoneLayers({ report, name }: { report: ZoneReport; name: string }) {
  const { documented, cooccurrence, trend } = report.layers;
  const here = documented.findings.filter((f) => f.recorded_in_zone);
  const reported = documented.findings.filter((f) => !f.recorded_in_zone);

  return (
    <>
      <p>
        <strong>{name}</strong>: {fmtInt(report.observations)} observations of {fmtInt(report.species)} species;{" "}
        {report.invasive_species.length === 0
          ? "no invasive species recorded."
          : `${report.invasive_species.length} invasive ${report.invasive_species.length === 1 ? "species" : "species"} recorded: ${report.invasive_species
              .map((s) => s.species)
              .join(", ")}.`}
      </p>

      <Layer n={1} title="Documented findings" question="What do cited sources report about these species here?">
        {documented.findings.length === 0 ? (
          <Empty>Nothing cited yet for the species recorded in this zone.</Empty>
        ) : (
          <>
            {here.length > 0 && <FindingGroup title="About species recorded in this zone" items={here} />}
            {reported.length > 0 && (
              <FindingGroup
                title="Reported for this reserve, but not recorded in our data"
                note="The literature reports these species for this park, and none has been recorded in our data. They are listed because they matter and kept apart from sightings."
                items={reported}
              />
            )}
          </>
        )}
        <p className="hint">{documented.note}</p>
      </Layer>

      <div className="cols">
      <Layer n={2} title="Co-occurrence" question="Where invasive records are denser, is native richness lower?">
        <LayerResultView result={cooccurrence} kind="co" />
      </Layer>

      <Layer n={3} title="Trend over time" question="Is the invasive share of records rising while native records fall?">
        <LayerResultView result={trend} kind="trend" />
      </Layer>
      </div>
    </>
  );
}

function Layer({ n, title, question, children }: { n: number; title: string; question: string; children: ReactNode }) {
  return (
    <section className="card" aria-labelledby={`layer-${n}`} style={{ marginTop: 16 }}>
      <h2 id={`layer-${n}`} style={{ marginTop: 0 }}>
        {n} · {title}
      </h2>
      <p className="muted" style={{ marginTop: -4 }}>{question}</p>
      {children}
    </section>
  );
}

function FindingGroup({ title, note, items }: { title: string; note?: string; items: ReportFinding[] }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <h3>{title}</h3>
      {note && <p className="hint" style={{ marginTop: 0 }}>{note}</p>}
      {items.map((f, i) => (
        <FindingCard
          key={`${f.species}-${f.zone}-${f.affected}-${i}`}
          f={{
            species: f.species,
            commonName: f.common_name,
            certainty: f.certainty,
            findingType: f.finding_type,
            summary: f.summary,
            affected: f.affected,
            regionNote: f.region_note,
            quotes: f.quotes,
            citation: f.citation,
            url: f.url,
            verifiedOn: f.verified_on,
            recordsHere: f.records_in_zone,
          }}
        />
      ))}
    </div>
  );
}

function LayerResultView({ result, kind }: { result: LayerResult; kind: "co" | "trend" }) {
  const d = result.detail;
  if (result.status === "insufficient") {
    return (
      <>
        <div className="callout">
          <strong>Not enough data to say anything yet.</strong> {result.reason && <>{capitalise(result.reason)}.</>}
        </div>
        {kind === "co" ? (
          <>
            <Meter label="Grid cells with enough native records" value={num(d, "cells_usable")} target={num(d, "required_cells")} unit="cells" />
            <Meter label="…of which also hold invasive records" value={num(d, "cells_with_invasives")} target={num(d, "required_invasive_cells")} unit="cells" />
          </>
        ) : (
          <>
            <Meter label="Years with enough observations" value={num(d, "usable_years")} target={num(d, "required_years")} unit="years" />
            <Meter label="Invasive records in the zone" value={num(d, "invasive_records")} target={num(d, "required_invasive_records")} unit="records" />
          </>
        )}
        {result.needs && <p className="hint">Needs: {result.needs}.</p>}
        <p className="hint">
          A number computed from this little data would suggest more certainty than the records support, so none is shown.
        </p>
      </>
    );
  }
  return (
    <>
      {kind === "co" ? <CoResult detail={d} /> : <TrendResult detail={d} />}
      {result.caution && <div className="callout fail"><strong>Read with care.</strong> {result.caution}</div>}
    </>
  );
}

const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function CoResult({ detail }: { detail: Record<string, unknown> }) {
  const rho = num(detail, "spearman_rho");
  const ci = (detail.ci95 as [number, number] | null) ?? null;
  const W = 520;
  const x = linear([-1, 1], [24, W - 24]);
  return (
    <>
      <p>
        Rank correlation between the invasive share of records and native species richness across{" "}
        <strong>{fmtInt(num(detail, "cells_usable"))}</strong> grid cells:{" "}
        <strong>ρ = {rho.toFixed(2)}</strong>
        {ci && <> (95% interval {ci[0].toFixed(2)} to {ci[1].toFixed(2)})</>}.
      </p>
      <svg className="chart" viewBox={`0 0 ${W} 64`} role="img" aria-label={`Correlation ${rho.toFixed(2)}, interval ${ci ? `${ci[0].toFixed(2)} to ${ci[1].toFixed(2)}` : "unavailable"}`}>
        <line className="axis-line" x1={x(-1)} x2={x(1)} y1={34} y2={34} />
        {[-1, 0, 1].map((t) => (
          <g key={t}>
            <line className="grid-line" x1={x(t)} x2={x(t)} y1={26} y2={42} />
            <text x={x(t)} y={58} textAnchor="middle">{t}</text>
          </g>
        ))}
        {ci && <line stroke="var(--series-1)" strokeWidth={4} strokeLinecap="round" x1={x(ci[0])} x2={x(ci[1])} y1={34} y2={34} />}
        <circle className="ring" fill="var(--series-1)" r={5} cx={x(rho)} cy={34} />
        <text x={x(-1)} y={18} textAnchor="start">fewer native species where invaded</text>
        <text x={x(1)} y={18} textAnchor="end">more</text>
      </svg>
    </>
  );
}

function TrendResult({ detail }: { detail: Record<string, unknown> }) {
  const inv = detail.invasive_per_observation as { tau: number; p_value: number; slope: number } | null;
  const nat = detail.native_per_observation as { tau: number; p_value: number; slope: number } | null;
  const row = (label: string, r: typeof inv) =>
    r && (
      <tr>
        <td>{label}</td>
        <td className="num">{r.tau.toFixed(2)}</td>
        <td className="num">{r.p_value < 0.001 ? "<0.001" : r.p_value.toFixed(3)}</td>
        <td className="num">{r.slope >= 0 ? "+" : ""}{r.slope.toFixed(4)} per year</td>
      </tr>
    );
  return (
    <div className="table-wrap">
      <table>
        <caption>Mann-Kendall trend of records per observation, {(detail.years as number[] | undefined)?.join(" to ")}</caption>
        <thead>
          <tr><th>Measure</th><th className="num">Kendall τ</th><th className="num">p</th><th className="num">Theil-Sen slope</th></tr>
        </thead>
        <tbody>{row("Invasive records per observation", inv)}{row("Native records per observation", nat)}</tbody>
      </table>
    </div>
  );
}
