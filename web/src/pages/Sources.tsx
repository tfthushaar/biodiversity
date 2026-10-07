import { useSources } from "../api/hooks";
import { ErrorState, Loading } from "../components/basics";
import { safeUrl } from "../components/evidence";
import { fmtAgo, fmtInt, humanise, pluralise } from "../lib/format";

const DOCS = "https://github.com/tfthushaar/biodiversity/blob/main/docs/data-quality.md";

export function Sources() {
  const sources = useSources();
  return (
    <>
      <h1>Data sources and what they can support</h1>
      <p className="lede">
        Every record keeps its source, licence and original date. Archived camera-trap images are labelled as
        replays and are never passed off as live.
      </p>

      {sources.isError && !sources.data ? (
        <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />
      ) : !sources.data ? (
        <Loading what="sources" />
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <caption>Sources, their licences, and how the latest run went</caption>
              <thead>
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Licence</th>
                  <th className="num" scope="col">Records</th>
                  <th scope="col">Last run</th>
                  <th scope="col">Why records were refused</th>
                </tr>
              </thead>
              <tbody>
                {sources.data.map((s) => {
                  const rejected = Object.entries(s.rejected ?? {}).sort((a, b) => b[1] - a[1]);
                  const href = safeUrl(s.base_url);
                  return (
                    <tr key={s.id}>
                      <th scope="row" style={{ whiteSpace: "normal", color: "var(--ink)" }}>
                        {href ? <a href={href} target="_blank" rel="noopener noreferrer">{s.name}</a> : s.name}
                        {s.attribution && <div className="hint" style={{ fontWeight: 400 }}>{s.attribution}</div>}
                      </th>
                      <td>{s.kind === "replay" ? "replay (archive)" : s.kind}</td>
                      <td>{s.license ?? "–"}</td>
                      <td className="num" title={s.kind === "dataset" ? "A checklist of species, not a stream of sightings" : undefined}>
                        {s.kind === "dataset" ? "checklist" : fmtInt(s.items)}
                      </td>
                      <td>
                        {s.last_run ? fmtAgo(s.last_run) : "–"}
                        {s.fetched != null && (
                          <div className="hint">
                            fetched {fmtInt(s.fetched)}, {pluralise(s.skipped_dupe ?? 0, "duplicate")}
                          </div>
                        )}
                      </td>
                      <td>
                        {rejected.length === 0 ? (
                          "–"
                        ) : (
                          <ul style={{ margin: 0, paddingLeft: 16 }}>
                            {rejected.map(([reason, n]) => (
                              <li key={reason}>{humanise(reason)}: {fmtInt(n)}</li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <h2>What this data cannot tell you</h2>
      <div className="card">
        <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 10 }}>
          <li>
            <strong>It under-records the dominant invasive plants.</strong> People photograph animals and flowers,
            not ubiquitous weeds. <em>Lantana</em>, widely reported to have invaded large areas of these reserves,
            has a single record here. Treat any count as <em>recorded presence</em>, never abundance or cover.
          </li>
          <li>
            <strong>Threatened species are probably under-represented.</strong> Observations with deliberately
            obscured locations are discarded, and iNaturalist hides the position of species it considers sensitive.
          </li>
          <li>
            <strong>Invasive status comes from a country-level list.</strong> A species can be native in part of a
            country and introduced elsewhere in it (the chital is native on the mainland but introduced to the
            Andaman Islands). Species of mixed or uncertain origin are therefore excluded from the invasive counts.
          </li>
          <li>
            <strong>“Empty” is not “absent”.</strong> A zone with no invasive records may simply have few observers.
          </li>
        </ul>
        <p className="hint" style={{ marginBottom: 0 }}>
          Full measurements, including how many records were refused and why:{" "}
          <a href={DOCS} target="_blank" rel="noopener noreferrer">data-quality notes</a>.
        </p>
      </div>
    </>
  );
}
