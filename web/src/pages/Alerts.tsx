import { useAlerts } from "../api/hooks";
import { Empty, ErrorState, Loading, SeverityBadge } from "../components/basics";
import { fmtDate, fmtInt } from "../lib/format";

export function Alerts() {
  const alerts = useAlerts();
  return (
    <>
      <h1>Early-detection alerts</h1>
      <p className="lede">
        An alert means one specific thing: an invasive species was <strong>recorded in a zone for the first
        time in the past year</strong>, after enough observation there that not having seen it earlier means
        something. It is a prompt to go and look, never a finding.
      </p>

      {alerts.isError && !alerts.data ? (
        <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />
      ) : !alerts.data ? (
        <Loading what="alerts" />
      ) : alerts.data.length === 0 ? (
        <Empty>
          <strong>No alerts.</strong> No invasive species has been recorded in any zone for the first time in the
          past year. That is a statement about the records we hold, not a clean bill of health: the dominant
          invasive plants are rarely photographed (see Sources).
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
