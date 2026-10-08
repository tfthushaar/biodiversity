import { describe, expect, it } from "vitest";
import type { HotspotCell } from "../api/types";
import { cellKey, chooseCellSize, describeCell, filterCells, heatLevel, rankSpecies, yearSpan } from "./hotspots";

const sp = (name: string, records: number, first = 2020, last = 2020) => ({
  name,
  common_name: null,
  records,
  first_year: first,
  last_year: last,
});
const cell = (west: number, south: number, species: ReturnType<typeof sp>[]): HotspotCell => ({
  west,
  south,
  east: west + 0.02,
  north: south + 0.02,
  records: species.reduce((a, s) => a + s.records, 0),
  species_count: species.length,
  species,
});

const CELLS = [
  cell(76.5, 11.7, [sp("Lantana camara", 3, 2018, 2022), sp("Senna spectabilis", 1)]),
  cell(76.6, 11.8, [sp("Lantana camara", 1, 2015, 2015)]),
  cell(76.7, 11.9, [sp("Senna spectabilis", 2, 2021, 2023)]),
];

describe("chooseCellSize", () => {
  it("gives a small park finer squares than a large one", () => {
    expect(chooseCellSize(0.25)).toBeLessThan(chooseCellSize(1.2));
  });
  it("lands on one of the offered sizes", () => {
    for (const extent of [0.05, 0.3, 0.9, 3, 40]) {
      expect([0.005, 0.01, 0.02, 0.05, 0.1]).toContain(chooseCellSize(extent));
    }
  });
  it("aims for a few dozen squares across when there is plenty of data", () => {
    expect(chooseCellSize(0.56)).toBe(0.02);
    expect(chooseCellSize(1.4)).toBe(0.05);
  });
  it("uses coarser squares where records are few", () => {
    expect(chooseCellSize(0.5, 6)).toBeGreaterThan(chooseCellSize(0.5, 5000));
  });
  it("copes with no records at all", () => {
    expect([0.005, 0.01, 0.02, 0.05, 0.1]).toContain(chooseCellSize(0.5, 0));
  });
});

describe("filterCells", () => {
  it("returns everything when no species is chosen", () => {
    expect(filterCells(CELLS, null)).toBe(CELLS);
  });
  it("keeps only the chosen species and recounts each cell", () => {
    const got = filterCells(CELLS, "Senna spectabilis");
    expect(got.map((c) => c.records)).toEqual([2, 1]); // busiest first
    expect(got.every((c) => c.species.length === 1 && c.species_count === 1)).toBe(true);
  });
  it("drops cells where the species was never recorded", () => {
    expect(filterCells(CELLS, "Lantana camara")).toHaveLength(2);
    expect(filterCells(CELLS, "Nothing")).toEqual([]);
  });
  it("does not change the cells it was given", () => {
    const before = JSON.stringify(CELLS);
    filterCells(CELLS, "Lantana camara");
    expect(JSON.stringify(CELLS)).toBe(before);
  });
});

describe("rankSpecies", () => {
  it("adds up each species across cells and orders by records", () => {
    const got = rankSpecies(CELLS);
    expect(got.map((s) => [s.name, s.records])).toEqual([
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
    expect(heatLevel(10, 1000)).toBeGreaterThanOrEqual(0);
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
