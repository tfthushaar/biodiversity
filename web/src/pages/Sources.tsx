import { useSources, useStorage } from "../api/hooks";
import { ErrorState, Loading, Meter } from "../components/basics";
import { safeUrl } from "../components/evidence";
import { fmtAgo, fmtInt, humanise, pluralise } from "../lib/format";

const DOCS = "https://github.com/tfthushaar/biodiversity/blob/main/docs/data-quality.md";

export function Sources() {
  const sources = useSources();
  const storage = useStorage();
  const MB = 1024 * 1024;
  return (
    <>
      <h1>Data sources and what they can support</h1>
      <p className="lede">
        Every record keeps its source, licence and original date. Archived camera-trap images are labelled as
        replays.
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

      <h2>How much room is left</h2>
      <div className="card">
        {storage.data ? (
          <>
            <Meter
              label="Free-tier database"
              value={Math.round(storage.data.db_bytes / MB)}
              target={Math.round(storage.data.budget_bytes / MB)}
              unit="MB"
              limit
            />
            <p className="hint" style={{ marginBottom: 0 }}>
              Data collection pauses at 90% full, because a full free database becomes read-only. Old run
              logs are trimmed automatically, and records are kept.
            </p>
          </>
        ) : storage.isError ? (
          <p className="muted" style={{ margin: 0 }}>The storage figure is unavailable right now.</p>
        ) : (
          <Loading what="storage" />
        )}
      </div>

      <h2>Limits of this data</h2>
      <div className="card">
        <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 10 }}>
          <li>
            <strong>Dominant invasive plants are under-recorded.</strong> People photograph animals and flowers
            more than common weeds. <em>Lantana</em>, widely reported across these reserves, has a single record
            here. A count shows where a species was recorded and says little about how much ground it covers.
          </li>
          <li>
            <strong>Threatened species are probably under-represented.</strong> Observations with deliberately
            obscured locations are discarded, and iNaturalist hides the position of species it considers sensitive.
          </li>
          <li>
            <strong>Invasive status comes from a country-level list.</strong> A species can be native in part of a
            country and introduced elsewhere in it: the chital is native on the Indian mainland and introduced to
            the Andaman Islands. Species of mixed or uncertain origin are excluded from the invasive counts.
          </li>
          <li>
            <strong>Parks with few observers show few records.</strong> An empty park on the map reflects
            recording effort, and the species may still be present.
          </li>
          <li>
            <strong>USGS records cover non-native aquatic species in the United States.</strong> They add
            fishes, reptiles, amphibians, molluscs and aquatic plants, each with a source type and a coordinate
            accuracy class. Approximate and centroid positions, failed introductions and records without a full
            date are set aside.
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
