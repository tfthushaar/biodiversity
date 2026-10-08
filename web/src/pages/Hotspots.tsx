import { useEffect, useMemo, useState } from "react";
import { useFindings, useHotspots, usePlaybooks, useRecords, useSpeciesPhotos, useZones } from "../api/hooks";
import type { HotspotCell } from "../api/types";
import { Empty, ErrorState, Loading } from "../components/basics";
import { BarList, TableTwin } from "../components/charts";
import { HotspotMap } from "../components/HotspotMap";
import { SpeciesCard } from "../components/SpeciesCard";
import { fmtInt, pluralise } from "../lib/format";
import {
  HEAT_OPACITY,
  bboxOf,
  cellKey,
  chooseCellSize,
  describeCell,
  filterCells,
  rankSpecies,
  yearSpan,
} from "../lib/hotspots";

const COUNTRY: Record<string, string> = { IN: "India", TZ: "Tanzania", US: "United States" };

export function Hotspots({ zone: zoneParam }: { zone: string | null }) {
  const zones = useZones();
  const findings = useFindings();
  const playbooks = usePlaybooks();
  const photos = useSpeciesPhotos();

  const features = zones.data?.features ?? [];
  const busiest = useMemo(
    () => [...features].sort((a, b) => b.properties.invasive_records - a.properties.invasive_records)[0],
    [features],
  );
  const feature = features.find((f) => f.properties.slug === zoneParam) ?? busiest ?? null;
  const slug = feature?.properties.slug ?? null;

  const extent = useMemo(() => {
    if (!feature) return 0.5;
    const [w, s, e, n] = bboxOf(feature.geometry);
    return Math.max(e - w, n - s);
  }, [feature]);
  const cellSize = chooseCellSize(extent);
  const hot = useHotspots(slug, cellSize);

  const [species, setSpecies] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [showPoints, setShowPoints] = useState(false);
  const points = useRecords(slug, showPoints);

  // A new park starts with nothing chosen.
  useEffect(() => {
    setSpecies(null);
    setSelected(null);
    setShowPoints(false);
  }, [slug]);

  const all = hot.data?.cells ?? [];
  const ranking = useMemo(() => rankSpecies(all), [all]);
  const cells = useMemo(() => filterCells(all, species), [all, species]);
  const current = cells.find((c) => cellKey(c) === selected) ?? null;
  const total = cells.reduce((a, c) => a + c.records, 0);

  const photoOf = useMemo(() => new Map((photos.data ?? []).map((p) => [p.scientific_name, p])), [photos.data]);
  const findingsOf = (name: string) => (findings.data ?? []).filter((f) => f.species.scientific_name === name);
  const playbooksOf = (name: string) => (playbooks.data ?? []).filter((p) => p.species.scientific_name === name).length;

  const groups = useMemo(() => {
    const by = new Map<string, typeof features>();
    for (const f of features) by.set(f.properties.country, [...(by.get(f.properties.country) ?? []), f]);
    return [...by.entries()].sort((a, b) => (COUNTRY[a[0]] ?? a[0]).localeCompare(COUNTRY[b[0]] ?? b[0]));
  }, [features]);

  const pickPark = (value: string) => {
    window.location.hash = `#/hotspots/${encodeURIComponent(value)}`;
  };

  return (
    <>
      <h1>Hotspots</h1>
      <p className="lede">
        Choose a park to see where invasive species have been recorded most often. Darker squares hold more
        records. Select a square to see which species are there, what published research says they do to
        the local environment, and how they are managed.
      </p>

      {zones.isError && !zones.data ? (
        <ErrorState error={zones.error} onRetry={() => void zones.refetch()} />
      ) : !zones.data ? (
        <Loading what="parks" />
      ) : (
        <>
          <div className="filters" role="group" aria-label="Hotspot filters">
            <label>
              Park
              <select value={slug ?? ""} onChange={(e) => pickPark(e.target.value)}>
                {groups.map(([country, list]) => (
                  <optgroup key={country} label={COUNTRY[country] ?? country}>
                    {list.map((f) => (
                      <option key={f.properties.slug} value={f.properties.slug}>
                        {f.properties.name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            <label>
              Species
              <select
                value={species ?? ""}
                onChange={(e) => {
                  setSpecies(e.target.value || null);
                  setSelected(null);
                }}
              >
                <option value="">All invasive species</option>
                {ranking.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.common_name ? `${s.common_name} (${s.name})` : s.name} · {fmtInt(s.records)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <input type="checkbox" checked={showPoints} onChange={(e) => setShowPoints(e.target.checked)} />
              Show individual records
            </label>
          </div>

          {hot.isError && !hot.data ? (
            <ErrorState error={hot.error} onRetry={() => void hot.refetch()} />
          ) : !hot.data ? (
            <Loading what="hotspots" />
          ) : all.length === 0 ? (
            <Empty>
              No invasive-species records in {feature?.properties.name ?? "this park"} yet. Records depend on what
              people photograph, so a park with few observers shows few records whatever grows there.
            </Empty>
          ) : (
            <div className={`split${hot.isFetching ? " refetching" : ""}`}>
              <div>
                <HotspotMap
                  zone={feature}
                  cells={cells}
                  selected={selected}
                  onSelect={setSelected}
                  points={showPoints ? (points.data ?? null) : null}
                  label={`Map of invasive-species hotspots in ${feature?.properties.name}. A ranked list of the same hotspots is beside it.`}
                />
                <div className="scale">
                  <span>Fewer records</span>
                  <span className="scale-bar" aria-hidden="true">
                    {HEAT_OPACITY.map((a) => (
                      <span key={a} style={{ background: `rgba(var(--heat), ${a})` }} />
                    ))}
                  </span>
                  <span>More records</span>
                </div>
                <p className="hint" style={{ marginTop: 10 }}>
                  {pluralise(total, "record")} in {pluralise(cells.length, "square")} of about{" "}
                  {Math.round(cellSize * 111)} km. {showPoints && points.data && points.data.features.length >= 5000
                    ? "Individual records show the 5,000 most recent. "
                    : ""}
                  Counts reflect where people recorded species as well as where the species lives.
                </p>
                <TableTwin
                  caption="Hotspots ranked by number of invasive records"
                  columns={[{ label: "Rank" }, { label: "Location" }, { label: "Records", numeric: true }, { label: "Species" }]}
                  rows={cells.slice(0, 50).map((c, i) => [
                    i + 1,
                    describeCell(c),
                    fmtInt(c.records),
                    c.species.map((s) => s.common_name ?? s.name).join(", "),
                  ])}
                />
              </div>

              <div className="panel" aria-live="polite">
                {current ? (
                  <CellDetail
                    cell={current}
                    onBack={() => setSelected(null)}
                    photoOf={photoOf}
                    findingsOf={findingsOf}
                    playbooksOf={playbooksOf}
                  />
                ) : (
                  <Overview
                    cells={cells}
                    ranking={species ? rankSpecies(cells) : ranking}
                    onPick={(c) => setSelected(cellKey(c))}
                  />
                )}
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

function Overview({
  cells,
  ranking,
  onPick,
}: {
  cells: HotspotCell[];
  ranking: ReturnType<typeof rankSpecies>;
  onPick: (c: HotspotCell) => void;
}) {
  return (
    <>
      <h2 style={{ marginTop: 0 }}>Busiest squares</h2>
      <p className="hint" style={{ marginTop: -8 }}>
        Select a square on the map, or one below, to see its species.
      </p>
      <ol className="rank">
        {cells.slice(0, 8).map((c, i) => (
          <li key={cellKey(c)}>
            <button type="button" aria-pressed="false" onClick={() => onPick(c)}>
              <span className="n">{i + 1}</span>
              <span>
                {pluralise(c.records, "record")}{" "}
                <span className="what">
                  {c.species
                    .slice(0, 2)
                    .map((s) => s.common_name ?? s.name)
                    .join(", ")}
                  {c.species.length > 2 ? ` and ${c.species.length - 2} more` : ""}
                </span>
              </span>
              {" "}
              <span className="hint">{describeCell(c)}</span>
            </button>
          </li>
        ))}
      </ol>

      <h2 style={{ fontSize: 18 }}>Most recorded species</h2>
      <BarList
        caption="Most recorded invasive species in this park"
        valueLabel="Records"
        items={ranking.slice(0, 8).map((s) => ({
          key: s.name,
          label: s.common_name ?? s.name,
          value: s.records,
          note: `${s.name}, ${yearSpan(s.first_year, s.last_year)}`,
        }))}
      />
    </>
  );
}

function CellDetail({
  cell,
  onBack,
  photoOf,
  findingsOf,
  playbooksOf,
}: {
  cell: HotspotCell;
  onBack: () => void;
  photoOf: Map<string, import("../api/types").SpeciesPhoto>;
  findingsOf: (name: string) => import("../api/types").Finding[];
  playbooksOf: (name: string) => number;
}) {
  return (
    <>
      <button type="button" className="btn" onClick={onBack} style={{ marginBottom: 16 }}>
        Back to all squares
      </button>
      <h2 style={{ marginTop: 0 }}>{describeCell(cell)}</h2>
      <p className="muted" style={{ marginTop: -8 }}>
        {pluralise(cell.records, "record")} of {pluralise(cell.species_count, "invasive species", "invasive species")} in
        this square.
      </p>
      {cell.species.map((s) => (
        <SpeciesCard
          key={s.name}
          species={s}
          photo={photoOf.get(s.name)}
          findings={findingsOf(s.name)}
          playbooks={playbooksOf(s.name)}
          where="here"
        />
      ))}
    </>
  );
}
