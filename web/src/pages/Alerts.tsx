import { useAlerts } from "../api/hooks";
import { Empty, ErrorState, Loading, SeverityBadge } from "../components/basics";
import { fmtDate, fmtInt } from "../lib/format";

export function Alerts() {
  const alerts = useAlerts();
  return (
    <>
      <h1>Early-detection alerts</h1>
      <p className="lede">
        An alert is raised when an invasive species is <strong>recorded in a park for the first time in
        the past year</strong>, after enough observation there that not having seen it earlier means something.
        Each alert is a prompt to go and look.
      </p>

      {alerts.isError && !alerts.data ? (
        <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />
      ) : !alerts.data ? (
        <Loading what="alerts" />
      ) : alerts.data.length === 0 ? (
        <Empty>
          <div>
            <strong>No alerts.</strong> No invasive species has been recorded in any park for the first time in
            the past year. This describes the records held here. The dominant invasive plants are rarely
            photographed, so the absence of an alert is limited evidence (see Sources).
          </div>
        </Empty>
      ) : (
        <div className="card">
          {alerts.data.map((a) => (
            <article className="evidence" key={a.id}>
              <div className="head">
                <SeverityBadge severity={a.severity} />
                <strong>
                  <em>{a.species?.scientific_name ?? "Unknown species"}</em>
                </strong>
                {a.zones && <span className="badge">{a.zones.name}</span>}
                <span className="hint">first recorded {fmtDate(a.window_start)}</span>
              </div>
              <p style={{ margin: "4px 0" }}>
                {fmtInt(a.evidence.records)} {a.evidence.records === 1 ? "record" : "records"} so far.
              </p>
              {a.evidence.caveat && <p className="where"><strong>Caveat:</strong> {a.evidence.caveat}</p>}
            </article>
          ))}
        </div>
      )}
    </>
  );
}
