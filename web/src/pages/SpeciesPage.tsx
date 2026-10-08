import { useMemo, useState } from "react";
import { useFindings, usePlaybooks, useReports } from "../api/hooks";
import type { Finding, InvasiveSpecies, Playbook, ZoneReportRow } from "../api/types";
import { Empty, ErrorState, Loading } from "../components/basics";
import { BarList } from "../components/charts";
import { FindingCard, PlaybookCard } from "../components/cards";
import { fmtInt, pluralise } from "../lib/format";

interface Entry {
  name: string;
  common: string | null;
  playbooks: number;
  findings: number;
  records: number;
}

export function buildEntries(
  invasives: InvasiveSpecies[],
  playbooks: Playbook[],
  findings: Finding[],
  reports: ZoneReportRow[],
): Entry[] {
  const pb = new Map<string, number>();
  for (const p of playbooks) pb.set(p.species.scientific_name, (pb.get(p.species.scientific_name) ?? 0) + 1);
  const fd = new Map<string, number>();
  for (const f of findings) fd.set(f.species.scientific_name, (fd.get(f.species.scientific_name) ?? 0) + 1);
  const rec = new Map<string, number>();
  for (const r of reports) for (const s of r.report.invasive_species) rec.set(s.species, (rec.get(s.species) ?? 0) + s.records);

  const out = new Map<string, Entry>();
  const add = (name: string, common: string | null) => {
    if (!out.has(name))
      out.set(name, { name, common, playbooks: pb.get(name) ?? 0, findings: fd.get(name) ?? 0, records: rec.get(name) ?? 0 });
  };
  for (const s of invasives) add(s.species.scientific_name, s.species.common_name);
  for (const p of playbooks) add(p.species.scientific_name, p.species.common_name);
  // Most evidence first, then most recorded, then alphabetical: the useful ones surface.
  return [...out.values()].sort(
    (a, b) =>
      b.playbooks + b.findings - (a.playbooks + a.findings) ||
      b.records - a.records ||
      a.name.localeCompare(b.name),
  );
}

/** Species recorded in any park, in the shape the list expects. */
function recordedSpecies(reports: ZoneReportRow[]): InvasiveSpecies[] {
  const seen = new Map<string, InvasiveSpecies>();
  for (const r of reports) {
    for (const s of r.report.invasive_species) {
      if (!seen.has(s.species)) {
        seen.set(s.species, {
          species_id: 0,
          establishment_means: null,
          species: { scientific_name: s.species, common_name: s.common_name, kingdom: null },
        });
      }
    }
  }
  return [...seen.values()];
}

export function SpeciesPage({ selected }: { selected: string | null }) {
  const playbooks = usePlaybooks();
  const findings = useFindings();
  const reports = useReports();
  const [q, setQ] = useState("");

  const entries = useMemo(
    () =>
      playbooks.data && findings.data && reports.data
        ? buildEntries(recordedSpecies(reports.data), playbooks.data, findings.data, reports.data)
        : null,
    [playbooks.data, findings.data, reports.data],
  );

  const failed = [playbooks, findings, reports].find((x) => x.isError && !x.data);
  if (failed) return <ErrorState error={failed.error} onRetry={() => void failed.refetch()} />;
  if (!entries) return <Loading what="species" />;

  const shown = entries.filter(
    (e) => !q.trim() || `${e.name} ${e.common ?? ""}`.toLowerCase().includes(q.trim().toLowerCase()),
  );
  const current = entries.find((e) => e.name === selected) ?? null;

  return (
    <>
      <h1>Species</h1>
      <p className="lede">
        {fmtInt(entries.length)} invasive species are recorded in the parks or have cited research. Findings and
        management guidance each need a verbatim quote from a source that can be checked, so some species have
        none yet and say so.
      </p>
      <div className="grid two" style={{ alignItems: "start" }}>
        <section className="card" aria-label="Species list" style={{ maxHeight: 640, overflowY: "auto" }}>
          <div className="filters">
            <label style={{ width: "100%" }}>
              Search
              <input
                type="search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Lantana, Senna, Parthenium…"
                style={{ flex: 1, minHeight: 34, padding: "6px 10px", border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)", color: "var(--ink)" }}
              />
            </label>
          </div>
          {shown.length === 0 ? (
            <Empty>No species match “{q}”.</Empty>
          ) : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {shown.map((e) => (
                <li key={e.name}>
                  <a
                    href={`#/species/${encodeURIComponent(e.name)}`}
                    aria-current={e.name === selected ? "true" : undefined}
                    style={{
                      display: "block", padding: "6px 8px", borderRadius: 6, textDecoration: "none", color: "var(--ink)",
                      background: e.name === selected ? "var(--wash)" : undefined,
                    }}
                  >
                    <em>{e.name}</em>
                    {e.common && <span className="muted"> · {e.common}</span>}
                    <span className="hint" style={{ display: "block" }}>
                      {e.playbooks + e.findings > 0 ? `${pluralise(e.findings, "finding")} · ${pluralise(e.playbooks, "management option")}` : "no cited guidance yet"}
                      {e.records > 0 && ` · ${pluralise(e.records, "record")}`}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>

        {current ? (
          <Dossier entry={current} playbooks={playbooks.data ?? []} findings={findings.data ?? []} reports={reports.data ?? []} />
        ) : (
          <div className="card">
            <p className="muted" style={{ margin: 0 }}>
              Choose a species to see where it has been recorded, what research says it does, and what management
              has been tried. <a href={`#/species/${encodeURIComponent("Senna spectabilis")}`}>Start with <em>Senna spectabilis</em></a>, whose
              management history is the most instructive.
            </p>
          </div>
        )}
      </div>
    </>
  );
}

function Dossier({ entry, playbooks, findings, reports }: { entry: Entry; playbooks: Playbook[]; findings: Finding[]; reports: ZoneReportRow[] }) {
  const pbs = playbooks.filter((p) => p.species.scientific_name === entry.name);
  const fds = findings.filter((f) => f.species.scientific_name === entry.name);
  const byZone = reports
    .map((r) => ({ zone: r.zones.name, rec: r.report.invasive_species.find((s) => s.species === entry.name) }))
    .filter((z) => z.rec);

  return (
    <section aria-label={`About ${entry.name}`}>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>
          <em>{entry.name}</em>
        </h2>
        {entry.common && <p className="muted" style={{ marginTop: -4 }}>{entry.common}</p>}
        <span className="badge invasive"><span className="dot" aria-hidden="true" />listed as invasive (GRIIS)</span>
        <h3 style={{ marginTop: 16 }}>Recorded in the parks</h3>
        {byZone.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No records in these parks. The data cannot show whether it is present; see the limits under Sources.
          </p>
        ) : (
          <BarList
            color="var(--invasive)"
            caption={`Records of ${entry.name} by zone`}
            valueLabel="Records"
            items={byZone.map((z) => ({
              key: z.zone,
              label: z.zone,
              value: z.rec!.records,
              note: `${z.rec!.first_record} to ${z.rec!.last_record}`,
            }))}
          />
        )}
      </div>

      <h2>What research reports</h2>
      {fds.length === 0 ? (
        <Empty>No cited findings for this species yet.</Empty>
      ) : (
        <div className="card">
          {fds.map((f) => (
            <FindingCard
              key={f.id}
              f={{
                species: f.species.scientific_name, commonName: f.species.common_name, certainty: f.certainty,
                findingType: f.finding_type, summary: f.summary, affected: f.affected, regionNote: f.region_note,
                quotes: f.source_quotes, citation: f.citation_text, url: f.citation_url, verifiedOn: f.verified_on,
                zone: f.zones?.name ?? null, showSpecies: false,
              }}
            />
          ))}
        </div>
      )}

      <h2>What has been tried</h2>
      {pbs.length === 0 ? (
        <Empty>
          No cited management guidance for this species yet.
        </Empty>
      ) : (
        <>
          <p className="hint">
            This summarises what published sources report, with their caveats. A method that worked in one habitat
            or country may not work in another, and where experts disagree both views are shown.
          </p>
          <div className="card">
            {pbs.map((p) => (
              <PlaybookCard key={p.id} p={p} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
