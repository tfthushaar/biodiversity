import { useSources } from "../api/hooks";
import { ErrorState, Loading } from "../components/basics";
import { safeUrl } from "../components/evidence";
import { BarList } from "../components/charts";
import { fmtAgo, fmtInt, humanise } from "../lib/format";

const KIND: Record<string, string> = { api: "records", dataset: "checklist", replay: "archive" };

/** The licence as a reader should see it, without the name of the database column that holds it. */
const licence = (text: string | null) => (text ? text.replace(/;?\s*see media_items\.license/, "") : "–");

const DOCS = "https://github.com/tfthushaar/biodiversity/blob/main/docs/data-quality.md";

export function Sources() {
  const sources = useSources();
  return (
    <>
      <h1>Data sources and what they can support</h1>
      <p className="lede">
        Every record keeps its source, licence and original date.
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
                </tr>
              </thead>
              <tbody>
                {sources.data.map((s) => {
                  const href = safeUrl(s.base_url);
                  return (
                    <tr key={s.id}>
                      <th scope="row" style={{ whiteSpace: "normal", color: "var(--ink)" }}>
                        {href ? <a href={href} target="_blank" rel="noopener noreferrer">{s.name}</a> : s.name}
                        {s.attribution && <div className="hint" style={{ fontWeight: 400 }}>{s.attribution}</div>}
                      </th>
                      <td>{KIND[s.kind] ?? s.kind}</td>
                      <td>{licence(s.license)}</td>
                      <td className="num" title={s.kind === "dataset" ? "A checklist of species, not a stream of sightings" : undefined}>
                        {s.kind === "dataset" ? "checklist" : fmtInt(s.items)}
                      </td>
                      <td>{s.last_run ? fmtAgo(s.last_run) : "–"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {sources.data && sources.data.some((s) => Object.keys(s.rejected ?? {}).length > 0) && (
        <>
          <h2>Why records were refused</h2>
          <p className="hint" style={{ marginTop: -8 }}>
            Every record must name a species, carry a full date, have a position that is not hidden and is
            accurate to 2 km, and fall inside the park. Each refusal is counted by reason, from the latest run.
          </p>
          <div className="grid three">
            {sources.data
              .filter((s) => Object.keys(s.rejected ?? {}).length > 0)
              .map((s) => (
                <div className="card" key={s.id}>
                  <h3 style={{ marginTop: 0 }}>{s.name}</h3>
                  <BarList
                    caption={`Why ${s.name} records were refused`}
                    valueLabel="Records refused"
                    items={Object.entries(s.rejected ?? {})
                      .sort((a, b) => b[1] - a[1])
                      .map(([reason, n]) => ({ key: reason, label: humanise(reason), value: n }))}
                  />
                </div>
              ))}
          </div>
        </>
      )}

      <h2>Limits of this data</h2>
      <div className="card">
        <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 10 }}>
          <li>
            <strong>A record shows that a species was seen at a place and time.</strong> It says nothing about
            how much ground the species covers, and a species that observers rarely record can be common and
            still have few records.
          </li>
          <li>
            <strong>Records with a hidden location are discarded.</strong> They are counted above as
            obscured locations.
          </li>
          <li>
            <strong>Invasive status comes from a country-level list.</strong> GRIIS cannot say whether a species
            is invasive inside one park. Species that GRIIS lists as both native and alien in a country, such as
            the chital in India, and species of uncertain origin are left out of the invasive counts.
          </li>
          <li>
            <strong>Parks with few observers show few records.</strong> An empty square on the map says nothing
            about whether a species is there.
          </li>
          <li>
            <strong>The three sources differ.</strong> iNaturalist holds community observations with a confirmed
            identification. GBIF supplies preserved museum and herbarium specimens only, because those trace to
            a collection. The USGS Nonindigenous Aquatic Species database holds curated records of non-native
            aquatic species in the two US parks, each with a source type and a coordinate accuracy class.
            Approximate and centroid positions, failed introductions and records without a full date are set aside.
          </li>
          <li>
            <strong>Findings come from peer-reviewed papers.</strong> Each is a journal article published in
            2016 or later, checked against Crossref and OpenAlex, and every quote appears in the paper's
            abstract. A species with no such paper says so.
          </li>
        </ul>
        <p className="hint" style={{ margin: "14px 0 0" }}>
          Full measurements, including how many records were refused and why:{" "}
          <a href={DOCS} target="_blank" rel="noopener noreferrer">data-quality notes</a>.
        </p>
      </div>
    </>
  );
}
