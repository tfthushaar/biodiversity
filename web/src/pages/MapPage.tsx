import { useEffect, useMemo, useState } from "react";
import { useRecords, useZones } from "../api/hooks";
import type { RecordClass } from "../api/types";
import { ErrorState, KindBadge, Loading } from "../components/basics";
import { TableTwin } from "../components/charts";
import { safeUrl } from "../components/evidence";
import { MapView } from "../components/MapView";
import { fmtDate, fmtInt } from "../lib/format";

const KINDS: { id: RecordClass; label: string }[] = [
  { id: "invasive", label: "Invasive" },
  { id: "introduced", label: "Introduced (not invasive)" },
  { id: "native", label: "Native / unlisted" },
];

export function MapPage() {
  const [zone, setZone] = useState<string | null>(null);
  const [chosen, setChosen] = useState(false);
  const [show, setShow] = useState<Record<RecordClass, boolean>>({ invasive: true, introduced: true, native: true });
  const zones = useZones();
  const records = useRecords(zone);

  // "All zones" spans two continents and shrinks every point to a speck, so start on the zone
  // with the most invasive records. "All zones" stays one click away.
  useEffect(() => {
    if (zone !== null || !zones.data || chosen) return;
    const best = [...zones.data.features].sort((a, b) => b.properties.invasive_records - a.properties.invasive_records)[0];
    if (best) setZone(best.properties.slug);
    setChosen(true);
  }, [zone, zones.data, chosen]);

  const invasive = useMemo(
    () => (records.data?.features ?? []).filter((f) => f.properties.class === "invasive"),
    [records.data],
  );
  const counts = useMemo(() => {
    const c: Record<RecordClass, number> = { invasive: 0, introduced: 0, native: 0 };
    for (const f of records.data?.features ?? []) c[f.properties.class] += 1;
    return c;
  }, [records.data]);

  return (
    <>
      <h1>Map of recorded sightings</h1>
      <p className="lede">
        Every sighting in the data, in context. Invasive records are the large orange points; everything else is
        drawn small and quiet beneath them. An empty patch of map means <em>no records</em>, not <em>no plants</em>.
      </p>

      <div className="filters" role="group" aria-label="Map filters">
        <label>
          Zone
          <select value={zone ?? ""} onChange={(e) => {
              setChosen(true);
              setZone(e.target.value || null);
            }}>
            <option value="">All zones (two continents)</option>
            {zones.data?.features.map((f) => (
              <option key={f.properties.slug} value={f.properties.slug}>
                {f.properties.name}
              </option>
            ))}
          </select>
        </label>
        {KINDS.map((k) => (
          <label key={k.id}>
            <input
              type="checkbox"
              checked={show[k.id]}
              onChange={(e) => setShow({ ...show, [k.id]: e.target.checked })}
            />
            <span
              aria-hidden="true"
              className="swatch"
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: `var(--${k.id === "invasive" ? "invasive" : k.id === "native" ? "native" : "introduced"})`,
              }}
            />
            {k.label} <span className="hint">({fmtInt(counts[k.id])})</span>
          </label>
        ))}
      </div>

      {zones.isError && !zones.data ? (
        <ErrorState error={zones.error} onRetry={() => void zones.refetch()} />
      ) : records.isError && !records.data ? (
        <ErrorState error={records.error} onRetry={() => void records.refetch()} />
      ) : !zones.data || !records.data ? (
        <Loading what="the map" />
      ) : (
        <div className={records.isFetching ? "refetching" : undefined}>
          <MapView zones={zones.data} records={records.data} selected={zone} show={show} />
          {records.data.features.length >= 5000 && (
            <p className="hint">Showing the 5,000 most recent records; narrow by zone to see them all.</p>
          )}
          <h2>Invasive records</h2>
          {invasive.length === 0 ? (
            <p className="muted">No invasive-species records in {zone ? "this zone" : "the data"}.</p>
          ) : (
            <TableTwin
              caption="Invasive-species records shown on the map"
              columns={[{ label: "Species" }, { label: "Zone" }, { label: "Recorded" }, { label: "Identified by" }, { label: "Record" }]}
              rows={invasive.map((f) => {
                const href = safeUrl(f.properties.url);
                return [
                  <>
                    <em>{f.properties.species}</em> <KindBadge kind="invasive" />
                  </>,
                  f.properties.zone,
                  fmtDate(f.properties.captured_at),
                  f.properties.origin === "observer" ? "a person" : "the model",
                  href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer">
                      open
                    </a>
                  ) : (
                    "–"
                  ),
                ];
              })}
            />
          )}
        </div>
      )}
    </>
  );
}
