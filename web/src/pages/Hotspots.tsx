import { useEffect, useMemo, useState } from "react";
import {
  useFindings,
  useHotspots,
  useInvasiveByYear,
  usePlaybooks,
  useSources,
  useSpeciesPhotos,
  useZones,
} from "../api/hooks";
import type { HotspotCell } from "../api/types";
import { Empty, ErrorState, Loading } from "../components/basics";
import { ColumnChart, TableTwin } from "../components/charts";
import { HotspotMap } from "../components/HotspotMap";
import { SpeciesList, type SpeciesLookup } from "../components/SpeciesCard";
import { fmtInt, pluralise, shortPark } from "../lib/format";
import {
  HEAT_OPACITY,
  SIZES_KM,
  bboxOf,
  cellKey,
  cellsInView,
  chooseSizeKm,
  describeCell,
  extentKm,
  fmtKm,
  rankSpecies,
  yearSpan,
  yearTotals,
  type Bounds,
} from "../lib/hotspots";

const COUNTRY: Record<string, string> = { IN: "India", TZ: "Tanzania", US: "United States" };
const GROUPS = [
  { value: "", label: "Plants and animals" },
  { value: "Plantae", label: "Plants" },
  { value: "Animalia", label: "Animals" },
];

export function Hotspots({ zone: zoneParam }: { zone: string | null }) {
  const zones = useZones();
  const findings = useFindings();
  const playbooks = usePlaybooks();
  const photos = useSpeciesPhotos();
  const sources = useSources();

  const features = zones.data?.features ?? [];
  const busiest = useMemo(
    () => [...features].sort((a, b) => b.properties.invasive_records - a.properties.invasive_records)[0],
    [features],
  );
  const feature = features.find((f) => f.properties.slug === zoneParam) ?? busiest ?? null;
  const slug = feature?.properties.slug ?? null;

  const extent = useMemo(() => (feature ? extentKm(bboxOf(feature.geometry)) : 50), [feature]);
  const autoKm = chooseSizeKm(extent, feature?.properties.invasive_records ?? 0);

  // What narrows the map. The species choice is applied here in the browser, so the species list
  // keeps every species of the park while one is chosen.
  const [species, setSpecies] = useState<string | null>(null);
  const [group, setGroup] = useState("");
  const [source, setSource] = useState("");
  const [yearFrom, setYearFrom] = useState<number | null>(null);
  const [yearTo, setYearTo] = useState<number | null>(null);
  const [size, setSize] = useState<number | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<Bounds | null>(null);
  const [fit, setFit] = useState(0);

  const km = size ?? autoKm;
  const narrowing = { sources: source ? [source] : [], yearFrom, yearTo, kingdom: group || null };
  // Every species of the park, with the other filters applied: the list and the species menu.
  const hot = useHotspots(slug, km, narrowing);
  // The squares for one chosen species, counted exactly by the database.
  const one = useHotspots(slug, km, { ...narrowing, species }, species != null);
  const years = useInvasiveByYear(slug);

  const reset = () => {
    setSpecies(null);
    setGroup("");
    setSource("");
    setYearFrom(null);
    setYearTo(null);
    setSize(null);
    setSelected(null);
  };
  // A new park starts with nothing chosen.
  useEffect(() => {
    reset();
    setView(null);
  }, [slug]);

  const all = hot.data?.cells ?? [];
  const ranking = useMemo(() => rankSpecies(all), [all]);
  const cells = useMemo(() => (species ? (one.data?.cells ?? []) : all), [species, one.data, all]);
  const current = cells.find((c) => cellKey(c) === selected) ?? null;

  // The region the panel describes: the chosen square, else what the map shows, else the park.
  const inView = useMemo(() => (view ? cellsInView(cells, view) : cells), [cells, view]);
  const scopeCells = current ? [current] : inView;
  const scopeLabel = current ? "This square" : inView.length < cells.length ? "In the map view" : "Whole park";
  const scopeRecords = scopeCells.reduce((a, c) => a + c.records, 0);
  const scopeSpecies = useMemo(() => rankSpecies(scopeCells), [scopeCells]);
  const total = cells.reduce((a, c) => a + c.records, 0);
  const filtered = species != null || group !== "" || source !== "" || yearFrom != null || yearTo != null;

  const photoMap = useMemo(() => new Map((photos.data ?? []).map((p) => [p.scientific_name, p])), [photos.data]);
  const lookup: SpeciesLookup = useMemo(
    () => ({
      photoOf: (name) => photoMap.get(name),
      findingsOf: (name) => (findings.data ?? []).filter((f) => f.species.scientific_name === name),
      playbooksOf: (name) => (playbooks.data ?? []).filter((p) => p.species.scientific_name === name).length,
    }),
    [photoMap, findings.data, playbooks.data],
  );

  const groups = useMemo(() => {
    const by = new Map<string, typeof features>();
    for (const f of features) by.set(f.properties.country, [...(by.get(f.properties.country) ?? []), f]);
    return [...by.entries()].sort((a, b) => (COUNTRY[a[0]] ?? a[0]).localeCompare(COUNTRY[b[0]] ?? b[0]));
  }, [features]);
  const sourceNames = (sources.data ?? []).filter((s) => s.kind === "api" && s.items > 0).map((s) => s.name);
  const yearList = useMemo(() => {
    const ys = (years.data ?? []).map((y) => y.year);
    if (ys.length === 0) return [];
    const lo = Math.min(...ys);
    const hi = Math.max(...ys);
    return Array.from({ length: hi - lo + 1 }, (_, i) => hi - i);
  }, [years.data]);

  const pickPark = (value: string) => {
    window.location.hash = `#/hotspots/${encodeURIComponent(value)}`;
  };
  const narrow = (apply: () => void) => {
    apply();
    setSelected(null);
  };

  return (
    <>
      <h1>Hotspots</h1>
      <p className="lede">
        Darker squares hold more invasive-species records. The list follows the square you choose, or the part
        of the park you are looking at, and shows what peer-reviewed papers report about each species.
      </p>

      {zones.isError && !zones.data ? (
        <ErrorState error={zones.error} onRetry={() => void zones.refetch()} />
      ) : !zones.data ? (
        <Loading what="parks" />
      ) : (
        <>
          <div className="toolbar" role="group" aria-label="Hotspot filters">
            <label>
              Park
              <select value={slug ?? ""} onChange={(e) => pickPark(e.target.value)}>
                {groups.map(([country, list]) => (
                  <optgroup key={country} label={COUNTRY[country] ?? country}>
                    {list.map((f) => (
                      <option key={f.properties.slug} value={f.properties.slug}>
                        {shortPark(f.properties.name)}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            <label>
              Species
              <select value={species ?? ""} onChange={(e) => narrow(() => setSpecies(e.target.value || null))}>
                <option value="">All invasive species</option>
                {ranking.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.common_name ?? s.name} · {fmtInt(s.records)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Group
              <select value={group} onChange={(e) => narrow(() => setGroup(e.target.value))}>
                {GROUPS.map((g) => (
                  <option key={g.value} value={g.value}>
                    {g.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Source
              <select value={source} onChange={(e) => narrow(() => setSource(e.target.value))}>
                <option value="">All sources</option>
                {sourceNames.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <label>
              From
              <select
                value={yearFrom ?? ""}
                onChange={(e) =>
                  narrow(() => {
                    const v = e.target.value ? Number(e.target.value) : null;
                    setYearFrom(v);
                    if (v != null && yearTo != null && yearTo < v) setYearTo(v);
                  })
                }
              >
                <option value="">Earliest</option>
                {yearList.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </label>
            <label>
              To
              <select
                value={yearTo ?? ""}
                onChange={(e) =>
                  narrow(() => {
                    const v = e.target.value ? Number(e.target.value) : null;
                    setYearTo(v);
                    if (v != null && yearFrom != null && yearFrom > v) setYearFrom(v);
                  })
                }
              >
                <option value="">Latest</option>
                {yearList.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Square size
              <select value={size ?? ""} onChange={(e) => narrow(() => setSize(e.target.value ? Number(e.target.value) : null))}>
                <option value="">Automatic ({fmtKm(autoKm)})</option>
                {SIZES_KM.map((s) => (
                  <option key={s} value={s}>
                    {fmtKm(s)}
                  </option>
                ))}
              </select>
            </label>
            {filtered && (
              <button type="button" className="btn" onClick={reset}>
                Reset filters
              </button>
            )}
          </div>

          {hot.isError && !hot.data ? (
            <ErrorState error={hot.error} onRetry={() => void hot.refetch()} />
          ) : !hot.data || (species != null && !one.data && !one.isError) ? (
            <Loading what="hotspots" />
          ) : all.length === 0 ? (
            <Empty>
              {filtered
                ? "No invasive-species records match these filters."
                : `No invasive-species records in ${feature?.properties.name ?? "this park"} yet. Records show where people looked, so a park with few observers has few records.`}
              {filtered && (
                <>
                  {" "}
                  <button type="button" className="btn" onClick={reset} style={{ marginLeft: 8 }}>
                    Reset filters
                  </button>
                </>
              )}
            </Empty>
          ) : (
            <div className={`split${hot.isFetching ? " refetching" : ""}`}>
              <div className="stage">
                <HotspotMap
                  zone={feature}
                  cells={cells}
                  selected={selected}
                  onSelect={setSelected}
                  onView={setView}
                  fitKey={fit}
                  label={`Map of invasive-species hotspots in ${feature?.properties.name}. A ranked list of the same hotspots is below it.`}
                />
                <div className="scale">
                  <span>Fewer records</span>
                  <span className="scale-bar" aria-hidden="true">
                    {HEAT_OPACITY.map((a) => (
                      <span key={a} style={{ background: `rgba(var(--hot), ${a})` }} />
                    ))}
                  </span>
                  <span>More records</span>
                  <span className="grow" />
                  <button type="button" className="link-btn" onClick={() => { setSelected(null); setFit((n) => n + 1); }}>
                    Show the whole park
                  </button>
                </div>
                <p className="hint" style={{ marginTop: 8 }}>
                  {pluralise(total, "record")} in {pluralise(cells.length, "square")}, each {fmtKm(hot.data.km ?? km)} on a
                  side.
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
                <Scope
                  label={scopeLabel}
                  cell={current}
                  records={scopeRecords}
                  speciesCount={scopeSpecies.length}
                  onClear={() => {
                    setSelected(null);
                  }}
                />
                {scopeCells.length === 0 ? (
                  <Empty>No squares in this view. Move or zoom the map, or choose Show the whole park.</Empty>
                ) : (
                  <>
                    {!current && (
                      <>
                        <h3>Busiest squares</h3>
                        <ol className="rank">
                          {scopeCells.slice(0, 5).map((c, i) => (
                            <li key={cellKey(c)}>
                              <button type="button" onClick={() => setSelected(cellKey(c))}>
                                <span className="n">{i + 1}</span>
                                <span>
                                  {pluralise(c.records, "record")}
                                  <span className="what">
                                    {c.species.slice(0, 2).map((s) => s.common_name ?? s.name).join(", ")}
                                    {c.species.length > 2 ? ` and ${c.species.length - 2} more` : ""}
                                  </span>
                                </span>
                                <span className="hint">{describeCell(c)}</span>
                              </button>
                            </li>
                          ))}
                        </ol>
                      </>
                    )}
                    <h3>Records by year</h3>
                    <ColumnChart
                      data={yearTotals(scopeCells)}
                      caption={`Invasive records by year, ${scopeLabel.toLowerCase()}`}
                    />
                    <h3>Species here, most recorded first</h3>
                    <SpeciesList
                      scope={`${slug}|${scopeLabel}|${current ? cellKey(current) : ""}|${species ?? ""}`}
                      species={scopeSpecies}
                      lookup={lookup}
                      where={current ? "in this square" : "here"}
                    />
                  </>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

function Scope({
  label,
  cell,
  records,
  speciesCount,
  onClear,
}: {
  label: string;
  cell: HotspotCell | null;
  records: number;
  speciesCount: number;
  onClear: () => void;
}) {
  return (
    <header className="scope">
      <div>
        <div className="eyebrow">{label}</div>
        <h2>{cell ? describeCell(cell) : `${pluralise(records, "record")}`}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {cell && <>{pluralise(records, "record")} of </>}
          {pluralise(speciesCount, "invasive species", "invasive species")}
          {cell?.by_year?.length ? `, ${yearSpan(cell.by_year[0]![0], cell.by_year[cell.by_year.length - 1]![0])}` : ""}.
        </p>
      </div>
      {cell && (
        <button type="button" className="btn" onClick={onClear}>
          Back to all squares
        </button>
      )}
    </header>
  );
}
