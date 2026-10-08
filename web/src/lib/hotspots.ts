import type { Geometry } from "geojson";
import type { HotspotCell, HotspotSpecies } from "../api/types";

/** Cell sizes on offer, in degrees: about 0.5, 1, 2, 5 and 10 km. */
const STEPS = [0.005, 0.01, 0.02, 0.05, 0.1];

/**
 * A cell size that gives roughly 20 to 40 cells across a zone, so a small park is not one square
 * and a large one is not a blur. `extentDeg` is the larger side of the zone's bounding box.
 */
export function chooseCellSize(extentDeg: number): number {
  const target = extentDeg / 28;
  return STEPS.reduce((best, s) => (Math.abs(s - target) < Math.abs(best - target) ? s : best), STEPS[0]!);
}

/** Cells with only the chosen species counted; cells it is absent from disappear. */
export function filterCells(cells: HotspotCell[], species: string | null): HotspotCell[] {
  if (!species) return cells;
  return cells
    .map((c) => {
      const only = c.species.filter((s) => s.name === species);
      return { ...c, species: only, species_count: only.length, records: only.reduce((a, s) => a + s.records, 0) };
    })
    .filter((c) => c.records > 0)
    .sort((a, b) => b.records - a.records);
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
