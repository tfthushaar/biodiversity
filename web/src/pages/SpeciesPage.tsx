import { useMemo, useState } from "react";
import { useFindings, usePlaybooks, useReports, useSpeciesPhotos, useSpeciesProfile } from "../api/hooks";
import type { Finding, Playbook, SpeciesPhoto, ZoneReportRow } from "../api/types";
import { Empty, ErrorState, Loading } from "../components/basics";
import { BarList, ColumnChart } from "../components/charts";
import { FindingCard, PlaybookCard } from "../components/cards";
import { safeUrl } from "../components/evidence";
import { fmtInt, pluralise } from "../lib/format";
import { yearSpan } from "../lib/hotspots";

export interface Entry {
  name: string;
  common: string | null;
  /** Findings and management rows on file. Every listed species has at least one. */
  papers: number;
  records: number;
}

/**
 * The species the page lists: those a peer-reviewed paper backs, and no others. A species recorded
 * in a park but without a paper is neither listed nor counted.
 */
export function buildEntries(playbooks: Playbook[], findings: Finding[], reports: ZoneReportRow[]): Entry[] {
  const papers = new Map<string, number>();
  for (const x of [...playbooks, ...findings]) {
    const n = x.species.scientific_name;
    papers.set(n, (papers.get(n) ?? 0) + 1);
  }
  const records = new Map<string, number>();
  const common = new Map<string, string | null>();
  for (const r of reports) {
    for (const s of r.report.invasive_species) {
      records.set(s.species, (records.get(s.species) ?? 0) + s.records);
      common.set(s.species, s.common_name);
    }
  }
  for (const x of [...playbooks, ...findings]) common.set(x.species.scientific_name, common.get(x.species.scientific_name) ?? x.species.common_name);

  return [...papers.keys()].map((name) => ({
    name,
    common: common.get(name) ?? null,
    papers: papers.get(name) ?? 0,
    records: records.get(name) ?? 0,
  }));
}

/** Most recorded first: the species the data says most about. */
export function sortEntries(entries: Entry[]): Entry[] {
  return [...entries].sort((a, b) => b.records - a.records || b.papers - a.papers || a.name.localeCompare(b.name));
}

export function SpeciesPage({ selected }: { selected: string | null }) {
  const playbooks = usePlaybooks();
  const findings = useFindings();
  const reports = useReports();
  const photos = useSpeciesPhotos();
  const [q, setQ] = useState("");

  const entries = useMemo(
    () => (playbooks.data && findings.data && reports.data ? buildEntries(playbooks.data, findings.data, reports.data) : null),
    [playbooks.data, findings.data, reports.data],
  );
  const shown = useMemo(() => {
    if (!entries) return [];
    const needle = q.trim().toLowerCase();
    return sortEntries(
      entries.filter(
        (e) => !needle || `${e.name} ${e.common ?? ""}`.toLowerCase().includes(needle),
      ),
    );
  }, [entries, q]);

  const failed = [playbooks, findings, reports].find((x) => x.isError && !x.data);
  if (failed) return <ErrorState error={failed.error} onRetry={() => void failed.refetch()} />;
  if (!entries) return <Loading what="species" />;

  // The page opens on the most recorded species, so it is never an empty frame.
  const top = sortEntries(entries)[0] ?? null;
  const current = entries.find((e) => e.name === selected) ?? (selected ? null : top);

  return (
    <>
      <h1>Species</h1>
      <p className="lede">
        {fmtInt(entries.length)} invasive species, most recorded first. A species appears here only when a
        peer-reviewed paper reports on it, and every finding and management method below comes from such a
        paper.
      </p>
      <div className="species-layout">
        <section className="card list-pane" aria-label="Species list">
          <div className="list-tools">
            <label className="field">
              <span>Search</span>
              <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or common name" />
            </label>
            <p className="hint" style={{ margin: 0 }}>{pluralise(shown.length, "species", "species")}</p>
          </div>
          {shown.length === 0 ? (
            <Empty>No species match “{q}”.</Empty>
          ) : (
            <ul className="species-index">
              {shown.map((e) => (
                <li key={e.name}>
                  <a href={`#/species/${encodeURIComponent(e.name)}`} aria-current={e.name === current?.name ? "true" : undefined}>
                    <span className="primary">
                      <strong>{e.common ?? <em>{e.name}</em>}</strong>
                      {e.common && <em className="muted"> {e.name}</em>}
                    </span>
                    <span className="hint">
                      {e.records > 0 ? pluralise(e.records, "record") : "not recorded in the parks"}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>

        {current ? (
          <Dossier
            entry={current}
            playbooks={playbooks.data ?? []}
            findings={findings.data ?? []}
            reports={reports.data ?? []}
            photo={(photos.data ?? []).find((p) => p.scientific_name === current.name)}
          />
        ) : (
          <Empty>
            {selected ? `“${selected}” is not listed: no peer-reviewed paper on file reports on it.` : "No species yet."}
          </Empty>
        )}
      </div>
    </>
  );
}

/** Number of distinct papers behind a set of claims. */
export const paperCount = (rows: { citation_doi: string }[]) => new Set(rows.map((r) => r.citation_doi)).size;

function Dossier({
  entry,
  playbooks,
  findings,
  reports,
  photo,
}: {
  entry: Entry;
  playbooks: Playbook[];
  findings: Finding[];
  reports: ZoneReportRow[];
  photo: SpeciesPhoto | undefined;
}) {
  const profile = useSpeciesProfile(entry.name);
  const pbs = playbooks.filter((p) => p.species.scientific_name === entry.name);
  const fds = findings.filter((f) => f.species.scientific_name === entry.name);
  const papers = paperCount([...fds, ...pbs]);
  const image = safeUrl(photo?.photo_url);
  const source = safeUrl(photo?.photo_source_url);
  const p = profile.data;
  const parks = reports.filter((r) => r.report.invasive_species.some((s) => s.species === entry.name));

  return (
    <section className="dossier" aria-label={`About ${entry.name}`}>
      <div className="card hero">
        {image && (
          <figure>
            <img src={image} alt={`Photograph of ${entry.common ?? entry.name}`} loading="lazy" referrerPolicy="no-referrer" />
            {photo?.photo_credit && (
              <figcaption>
                {photo.photo_credit}
                {source && (
                  <>
                    {" "}
                    <a href={source} target="_blank" rel="noopener noreferrer">Photo page</a>
                  </>
                )}
              </figcaption>
            )}
          </figure>
        )}
        <div>
          <h2 style={{ margin: 0 }}>{entry.common ?? <em>{entry.name}</em>}</h2>
          {entry.common && <p className="muted" style={{ margin: "2px 0 8px" }}><em>{entry.name}</em></p>}
          <span className="badge invasive">
            <span className="dot" aria-hidden="true" />
            alien and invasive, per GRIIS
          </span>
          <p className="muted" style={{ margin: "10px 0 0" }}>
            {pluralise(p?.records ?? entry.records, "record")}
            {p?.first_year ? `, ${yearSpan(p.first_year, p.last_year ?? p.first_year)}` : ""}
            {" · "}
            {pluralise(parks.length, "park")}
            {" · "}
            {pluralise(papers, "paper")} on file
          </p>
        </div>
      </div>

      <h2>Where and when it was recorded</h2>
      {profile.isError && !p ? (
        <ErrorState error={profile.error} onRetry={() => void profile.refetch()} />
      ) : !p ? (
        <Loading what="records" />
      ) : p.records === 0 ? (
        <Empty>
          Not recorded in these parks. The records cannot show whether the species is present. See the limits under Sources.
        </Empty>
      ) : (
        <div className="cols">
          <div className="card">
            <h3>By year</h3>
            <ColumnChart data={p.by_year} caption={`Records of ${entry.name} by year`} />
          </div>
          <div className="card">
            <h3>By park</h3>
            <BarList
              caption={`Records of ${entry.name} by park`}
              valueLabel="Records"
              items={p.by_park.map((z) => ({ key: z.slug, label: z.park, value: z.records }))}
            />
          </div>
        </div>
      )}

      <div className="cols">
        {fds.length > 0 && (
        <div>
          <h2>What research reports</h2>
          {(
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
        </div>
        )}
        {pbs.length > 0 && (
        <div>
          <h2>What has been tried</h2>
          {(
            <>
              <p className="hint" style={{ marginTop: 0 }}>
                Each row restates one paper, with the setting of its study. A method that worked in one habitat
                or country may not work in another.
              </p>
              <div className="card">
                {pbs.map((x) => (
                  <PlaybookCard key={x.id} p={x} />
                ))}
              </div>
            </>
          )}
        </div>
        )}
      </div>

    </section>
  );
}
