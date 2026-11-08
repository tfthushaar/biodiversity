import { describe, expect, it } from "vitest";
import type { HotspotCell } from "../api/types";
import {
  SIZES_KM,
  cellKey,
  cellsInView,
  chooseSizeKm,
  describeCell,
  extentKm,
  heatLevel,
  rankSpecies,
  sourceTotals,
  yearSpan,
  yearTotals,
} from "./hotspots";

const sp = (name: string, records: number, first = 2020, last = 2020) => ({
  name,
  common_name: null,
  records,
  first_year: first,
  last_year: last,
});
const cell = (
  west: number,
  south: number,
  species: ReturnType<typeof sp>[],
  extra: Partial<HotspotCell> = {},
): HotspotCell => ({
  west,
  south,
  east: west + 0.02,
  north: south + 0.02,
  records: species.reduce((a, s) => a + s.records, 0),
  species_count: species.length,
  species,
  ...extra,
});

const CELLS = [
  cell(76.5, 11.7, [sp("Lantana camara", 3, 2018, 2022), sp("Senna spectabilis", 1)], {
    by_year: [[2018, 1], [2022, 3]],
    by_source: { iNaturalist: 3, "GBIF specimens": 1 },
  }),
  cell(76.6, 11.8, [sp("Lantana camara", 1, 2015, 2015)], { by_year: [[2015, 1]], by_source: { iNaturalist: 1 } }),
  cell(76.7, 11.9, [sp("Senna spectabilis", 2, 2021, 2023)], { by_year: [[2021, 1], [2023, 1]], by_source: { "USGS NAS": 2 } }),
];

describe("chooseSizeKm", () => {
  it("gives a small park finer squares than a large one", () => {
    expect(chooseSizeKm(30)).toBeLessThan(chooseSizeKm(150));
  });
  it("lands on one of the offered sizes", () => {
    for (const extent of [3, 30, 100, 330, 4000]) expect(SIZES_KM).toContain(chooseSizeKm(extent));
  });
  it("aims for a few dozen squares across when there is plenty of data", () => {
    expect(chooseSizeKm(62)).toBe(2);
    expect(chooseSizeKm(155)).toBe(5);
  });
  it("uses coarser squares where records are few", () => {
    expect(chooseSizeKm(55, 6)).toBeGreaterThan(chooseSizeKm(55, 5000));
  });
  it("copes with no records at all", () => {
    expect(SIZES_KM).toContain(chooseSizeKm(55, 0));
  });
});

describe("extentKm", () => {
  it("measures the larger side of a box in kilometres, whatever the latitude", () => {
    // One degree of latitude is about 110.6 km everywhere.
    expect(extentKm([0, 0, 0.1, 1])).toBeCloseTo(110.574, 1);
    // One degree of longitude is shorter in the north: 111.32 * cos(60 degrees) = 55.66 km.
    expect(extentKm([10, 59.5, 11, 60.5])).toBeCloseTo(110.574, 1);
    expect(extentKm([10, 59.9, 12, 60.1])).toBeCloseTo(2 * 111.32 * Math.cos((60 * Math.PI) / 180), 0);
  });
});

describe("rankSpecies", () => {
  it("adds up each species across cells and orders by records", () => {
    expect(rankSpecies(CELLS).map((s) => [s.name, s.records])).toEqual([
      ["Lantana camara", 4],
      ["Senna spectabilis", 3],
    ]);
  });
  it("widens the years to cover every cell", () => {
    const lantana = rankSpecies(CELLS)[0]!;
    expect([lantana.first_year, lantana.last_year]).toEqual([2015, 2022]);
  });
  it("breaks ties alphabetically", () => {
    const tie = [cell(0, 0, [sp("B species", 2), sp("A species", 2)])];
    expect(rankSpecies(tie).map((s) => s.name)).toEqual(["A species", "B species"]);
  });
});

describe("totals for the charts", () => {
  it("adds yearly counts across cells, oldest first", () => {
    expect(yearTotals(CELLS)).toEqual([
      { year: 2015, records: 1 },
      { year: 2018, records: 1 },
      { year: 2021, records: 1 },
      { year: 2022, records: 3 },
      { year: 2023, records: 1 },
    ]);
  });
  it("adds source counts across cells, most first", () => {
    expect(sourceTotals(CELLS)).toEqual([
      { source: "iNaturalist", records: 4 },
      { source: "USGS NAS", records: 2 },
      { source: "GBIF specimens", records: 1 },
    ]);
  });
  it("copes with cells that carry no breakdown", () => {
    expect(yearTotals([cell(0, 0, [sp("A", 1)])])).toEqual([]);
    expect(sourceTotals([cell(0, 0, [sp("A", 1)])])).toEqual([]);
  });
});

describe("cellsInView", () => {
  it("keeps the cells whose middle is inside the view", () => {
    const got = cellsInView(CELLS, [76.45, 11.65, 76.65, 11.85]);
    expect(got.map(cellKey)).toEqual(["76.5000,11.7000", "76.6000,11.8000"]);
  });
  it("returns nothing for a view with no cells in it", () => {
    expect(cellsInView(CELLS, [0, 0, 1, 1])).toEqual([]);
  });
});

describe("heatLevel", () => {
  it("is lightest for nothing and darkest for the busiest cell", () => {
    expect(heatLevel(0, 100)).toBe(0);
    expect(heatLevel(100, 100)).toBe(4);
  });
  it("never goes outside 0 to 4", () => {
    expect(heatLevel(500, 100)).toBe(4);
    expect(heatLevel(1, 0)).toBe(0);
  });
  it("lifts quiet cells above the lightest shade when one cell dominates", () => {
    expect(heatLevel(250, 1000)).toBeGreaterThan(heatLevel(10, 1000));
  });
});

describe("labels", () => {
  it("names the middle of a cell with hemispheres", () => {
    expect(describeCell(cell(-80.6, 25.38, []))).toBe("25.39° N, 80.59° W");
    expect(describeCell(cell(34.8, -2.3, []))).toBe("2.29° S, 34.81° E");
  });
  it("keys a cell by its corner so the same cell is found again", () => {
    expect(cellKey(CELLS[0]!)).toBe("76.5000,11.7000");
  });
  it("shows a single year once", () => {
    expect(yearSpan(2020, 2020)).toBe("2020");
    expect(yearSpan(2015, 2022)).toBe("2015 to 2022");
  });
});
