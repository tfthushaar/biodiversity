import type { Geometry } from "geojson";
import type { HotspotCell, HotspotSpecies, YearCount } from "../api/types";

/** Square sizes on offer, in kilometres. The server builds the grid in kilometres, so a square
 *  is square wherever the park lies and its width is the width this list states. */
export const SIZES_KM = [0.5, 1, 2, 5, 10, 20];

/** Kilometres in one degree of latitude, and in one degree of longitude at the equator. */
const KM_PER_DEG_LAT = 110.574;
const KM_PER_DEG_LON_EQ = 111.32;

/**
 * A square size that suits the park and its data: up to about 28 squares across for a park with
 * thousands of records, and coarser squares where records are few, so a handful of records does
 * not become a scatter of tiny marks. `extentKm` is the larger side of the park's bounding box.
 */
export function chooseSizeKm(extentKm: number, records = Number.POSITIVE_INFINITY): number {
  const across = Math.min(28, Math.max(6, Math.round(Math.sqrt(Math.max(records, 0)) * 2.5)));
  const target = extentKm / across;
  return SIZES_KM.reduce((best, s) => (Math.abs(s - target) < Math.abs(best - target) ? s : best), SIZES_KM[0]!);
}

/** Width and height of a bounding box in kilometres: [west, south, east, north] in degrees. */
export function extentKm([w, s, e, n]: [number, number, number, number]): number {
  const mid = (((s + n) / 2) * Math.PI) / 180;
  return Math.max((e - w) * KM_PER_DEG_LON_EQ * Math.cos(mid), (n - s) * KM_PER_DEG_LAT);
}

/** Species across all cells, most recorded first. */
export function rankSpecies(cells: HotspotCell[]): HotspotSpecies[] {
  const by = new Map<string, HotspotSpecies>();
  for (const c of cells) {
    for (const s of c.species) {
      const have = by.get(s.name);
      by.set(
        s.name,
        have
          ? {
              ...have,
              records: have.records + s.records,
              first_year: Math.min(have.first_year, s.first_year),
              last_year: Math.max(have.last_year, s.last_year),
            }
          : { ...s },
      );
    }
  }
  return [...by.values()].sort((a, b) => b.records - a.records || a.name.localeCompare(b.name));
}

/** Records per year across cells, oldest first. */
export function yearTotals(cells: HotspotCell[]): YearCount[] {
  const by = new Map<number, number>();
  for (const c of cells) for (const [y, n] of c.by_year ?? []) by.set(y, (by.get(y) ?? 0) + n);
  return [...by.entries()].sort((a, b) => a[0] - b[0]).map(([year, records]) => ({ year, records }));
}

/** Records per source across cells, most first. */
export function sourceTotals(cells: HotspotCell[]): { source: string; records: number }[] {
  const by = new Map<string, number>();
  for (const c of cells) for (const [k, n] of Object.entries(c.by_source ?? {})) by.set(k, (by.get(k) ?? 0) + n);
  return [...by.entries()].sort((a, b) => b[1] - a[1]).map(([source, records]) => ({ source, records }));
}

/** [west, south, east, north] of a map view. */
export type Bounds = [number, number, number, number];

/** The cells whose middle lies inside a view. A cell on the edge belongs to the view it is mostly in. */
export function cellsInView(cells: HotspotCell[], view: Bounds): HotspotCell[] {
  const [w, s, e, n] = view;
  return cells.filter((c) => {
    const lon = (c.west + c.east) / 2;
    const lat = (c.south + c.north) / 2;
    return lon >= w && lon <= e && lat >= s && lat <= n;
  });
}

/** Shading levels, 0 (lightest) to 4. Square-root scaling keeps one very busy cell from
 *  flattening every other cell into the lightest shade. */
export function heatLevel(records: number, max: number): number {
  if (max <= 0 || records <= 0) return 0;
  return Math.min(4, Math.floor(Math.sqrt(records / max) * 5));
}

/** Fill opacity for each level. */
export const HEAT_OPACITY = [0.16, 0.3, 0.46, 0.64, 0.85];

export const cellKey = (c: Pick<HotspotCell, "west" | "south">) => `${c.west.toFixed(4)},${c.south.toFixed(4)}`;

/** "25.39° N, 80.59° W" for the middle of a cell. */
export function describeCell(c: HotspotCell): string {
  const lat = (c.south + c.north) / 2;
  const lon = (c.west + c.east) / 2;
  return `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}° ${lon >= 0 ? "E" : "W"}`;
}

export function yearSpan(first: number, last: number): string {
  return first === last ? String(first) : `${first} to ${last}`;
}

/** "0.5 km", "2 km". */
export const fmtKm = (km: number) => `${km} km`;

/** [west, south, east, north] of any polygon geometry. */
export function bboxOf(geometry: Geometry): [number, number, number, number] {
  let w = Infinity;
  let s = Infinity;
  let e = -Infinity;
  let n = -Infinity;
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") {
      const [x, y] = c as [number, number];
      w = Math.min(w, x);
      e = Math.max(e, x);
      s = Math.min(s, y);
      n = Math.max(n, y);
    } else if (Array.isArray(c)) {
      c.forEach(walk);
    }
  };
  if ("coordinates" in geometry) walk(geometry.coordinates);
  return Number.isFinite(w) ? [w, s, e, n] : [0, 0, 0, 0];
}
