import { describe, expect, it } from "vitest";
import { fmtAgo, fmtCompact, fmtDate, fmtInt, fmtPct, fmtYear, humanise, pluralise } from "./format";
import { groupSquares, labelIndices, labelIndicesAt, median, shareLabel, theilSenIntercept } from "./layout";
import { binYears, clamp, coverTicks, linear, nearestIndex, niceTicks, yearTicks } from "./scale";

describe("number formatting", () => {
  it("groups thousands and rounds", () => {
    expect(fmtInt(1284)).toBe("1,284");
    expect(fmtInt(1283.6)).toBe("1,284");
  });
  it("shows a missing value as a dash, never as zero", () => {
    expect(fmtInt(null)).toBe("–");
    expect(fmtInt(undefined)).toBe("–");
    expect(fmtPct(null)).toBe("–");
    expect(fmtCompact(Number.NaN)).toBe("–");
    expect(fmtInt(0)).toBe("0"); // a real zero is still a zero
  });
  it("compacts large numbers", () => {
    expect(fmtCompact(1284)).toBe("1,284");
    expect(fmtCompact(12_900)).toBe("12.9K");
    expect(fmtCompact(20_000)).toBe("20K");
    expect(fmtCompact(4_200_000)).toBe("4.2M");
  });
  it("formats proportions as percentages", () => {
    expect(fmtPct(0.8494)).toBe("84.9%");
    expect(fmtPct(0.966, 0)).toBe("97%");
  });
  it("pluralises", () => {
    expect(pluralise(1, "record")).toBe("1 record");
    expect(pluralise(1500, "record")).toBe("1,500 records");
    expect(pluralise(2, "species", "species")).toBe("2 species");
  });
});

describe("dates", () => {
  it("renders in UTC so everyone sees the same day", () => {
    expect(fmtDate("2026-08-05T23:30:00-05:00")).toBe("6 Aug 2026"); // 04:30 UTC next day
    expect(fmtDate("2026-01-01T00:00:00Z")).toBe("1 Jan 2026");
    expect(fmtYear("1984-05-08T00:00:00Z")).toBe("1984");
  });
  it("copes with missing and invalid input", () => {
    expect(fmtDate(null)).toBe("–");
    expect(fmtDate("not a date")).toBe("–");
    expect(fmtAgo(null)).toBe("never");
  });
  it("says how long ago", () => {
    const now = new Date("2026-10-07T12:00:00Z");
    expect(fmtAgo("2026-10-07T11:59:30Z", now)).toBe("just now");
    expect(fmtAgo("2026-10-07T09:00:00Z", now)).toBe("3 hours ago");
    expect(fmtAgo("2026-10-06T11:00:00Z", now)).toBe("1 day ago");
    expect(fmtAgo("2026-07-01T12:00:00Z", now)).toBe("3 months ago");
    expect(fmtAgo("2024-10-07T12:00:00Z", now)).toBe("2 years ago");
    expect(fmtAgo("2026-10-07T11:40:00Z", now)).toBe("20 minutes ago");
  });
  it("makes tokens readable", () => {
    expect(humanise("native_lookalike")).toBe("native look-alike");
    expect(humanise("unverified_concern")).toBe("unverified concern");
  });
});

describe("scales", () => {
  it("maps a domain to a range, including inverted ranges for y axes", () => {
    const x = linear([0, 10], [0, 100]);
    expect(x(0)).toBe(0);
    expect(x(5)).toBe(50);
    const y = linear([0, 1], [200, 0]);
    expect(y(0)).toBe(200);
    expect(y(1)).toBe(0);
  });
  it("does not divide by zero on a flat domain", () => {
    expect(linear([3, 3], [0, 100])(3)).toBe(50);
  });
  it("picks round ticks", () => {
    expect(niceTicks(0, 100, 5)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(niceTicks(0, 1, 5)).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1]);
    expect(niceTicks(0, 1, 4)).toEqual([0, 0.5, 1]);
    expect(niceTicks(0, 7, 5)).toEqual([0, 2, 4, 6]);
    expect(niceTicks(5, 5)).toEqual([5]);
  });
  it("snaps to the nearest position", () => {
    expect(nearestIndex([0.3, 0.5, 0.7, 0.9], 0.64)).toBe(2);
    expect(nearestIndex([0.3, 0.5], -10)).toBe(0);
  });
  it("clamps", () => {
    expect(clamp(5, 0, 3)).toBe(3);
    expect(clamp(-1, 0, 3)).toBe(0);
  });
});

describe("binYears", () => {
  it("keeps one bin for each year when the record is short, with empty years as zero", () => {
    expect(binYears([{ year: 2018, records: 3 }, { year: 2021, records: 4 }])).toEqual([
      { start: 2018, end: 2018, records: 3 },
      { start: 2019, end: 2019, records: 0 },
      { start: 2020, end: 2020, records: 0 },
      { start: 2021, end: 2021, records: 4 },
    ]);
  });
  it("groups a long record into 5-year bins, then 10-year bins, so columns stay readable", () => {
    const years = (n: number) => Array.from({ length: n }, (_, i) => ({ year: 1990 + i, records: 1 }));
    expect(binYears(years(60))[0]).toMatchObject({ start: 1990, end: 1994, records: 5 });
    const bins = binYears(years(200));
    expect(bins[0]).toMatchObject({ start: 1990, end: 1999, records: 10 });
    expect(bins.length).toBeLessThanOrEqual(21);
  });
  it("never loses or invents a record", () => {
    const data = [{ year: 1925, records: 2 }, { year: 1999, records: 7 }, { year: 2026, records: 11 }];
    expect(binYears(data).reduce((a, b) => a + b.records, 0)).toBe(20);
  });
  it("has nothing to draw for no data", () => {
    expect(binYears([])).toEqual([]);
  });
});

describe("labelIndices", () => {
  it("always labels the first and last position when there is room for both", () => {
    for (const count of [9, 77, 100]) {
      const got = labelIndices(count, 500 / (count - 1), 28);
      expect(got.has(0)).toBe(true);
      expect(got.has(count - 1)).toBe(true);
    }
  });

  it("keeps the first label, and skips the last, when no two labels can fit", () => {
    expect([...labelIndices(2, 5, 28)]).toEqual([0]);
  });

  it("keeps labels at least a label's width and a gap apart", () => {
    const slot = 6;
    const got = [...labelIndices(100, slot, 28)].sort((a, b) => a - b);
    for (let i = 1; i < got.length; i++) expect(((got[i] as number) - (got[i - 1] as number)) * slot).toBeGreaterThanOrEqual(28 + 28);
  });

  it("spaces labels by where they sit, so uneven steps do not make two touch", () => {
    // The fifth position is 20px from the fourth, so the two cannot both be labelled.
    const at = [0, 120, 260, 340, 360, 440];
    const got = [...labelIndicesAt(at, 28)].sort((a, b) => a - b);
    expect(got).toEqual([0, 1, 2, 3, 5]);
    for (let i = 1; i < got.length; i++) expect((at[got[i] as number] as number) - (at[got[i - 1] as number] as number)).toBeGreaterThanOrEqual(56);
  });

  it("labels every position when there is room", () => {
    expect(labelIndices(5, 200, 28).size).toBe(5);
  });

  it("drops the neighbour of the last label when the two would touch", () => {
    const got = [...labelIndices(10, 10, 28)];
    expect(got).toContain(9);
    expect(got).not.toContain(8);
  });
});

describe("median and theilSenIntercept", () => {
  it("takes the middle value, or the mean of the two in the middle", () => {
    expect(median([3, 1, 2])).toBe(2);
    expect(median([4, 1, 3, 2])).toBe(2.5);
    expect(median([])).toBeNaN();
  });

  it("finds the intercept that goes with a slope", () => {
    const xs = [2000, 2001, 2002, 2003];
    expect(theilSenIntercept(xs, xs.map((x) => 0.5 * x + 3), 0.5)).toBeCloseTo(3, 9);
  });
});

describe("shareLabel", () => {
  it("writes a share the way a person would", () => {
    expect([0, 0.004, 0.034, 0.58].map(shareLabel)).toEqual(["0%", "0.4%", "3%", "58%"]);
  });
});

describe("groupSquares", () => {
  const sq = (share: number, richness = 9, invasive = share > 0 ? 3 : 0): [number, number, number] => [share, richness, invasive];

  it("puts squares with no invasive records first, in a group of their own", () => {
    const got = groupSquares([sq(0), sq(0), sq(0.1), sq(0.2)]);
    expect(got[0]).toMatchObject({ key: "none", label: "None" });
    expect(got[0]?.richness).toHaveLength(2);
  });

  it("makes one group of the rest when there are too few to split", () => {
    const got = groupSquares([sq(0), sq(0.1), sq(0.2), sq(0.3)]);
    expect(got.map((g) => g.label)).toEqual(["None", "Some"]);
  });

  it("splits many squares into groups of similar size, labelled by the shares in them", () => {
    const shares = Array.from({ length: 12 }, (_, i) => (i + 1) / 100);
    const got = groupSquares(shares.map((s) => sq(s)));
    expect(got).toHaveLength(3);
    expect(got.map((g) => g.richness.length)).toEqual([4, 4, 4]);
    expect(got[0]?.label).toBe("1% to 4%");
    expect(got[2]?.label).toBe("9% to 12%");
  });

  it("never splits squares that share the same value across two groups", () => {
    const shares = [0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2];
    const got = groupSquares(shares.map((s) => sq(s)));
    expect(got.flatMap((g) => g.richness)).toHaveLength(12);
    for (const g of got) expect(new Set(g.invasive).size).toBeLessThanOrEqual(1);
    expect(got.map((g) => g.label)).not.toContain("5% to 20%");
  });

  it("returns nothing for no squares, and keeps every square otherwise", () => {
    expect(groupSquares([])).toEqual([]);
    const pts = [sq(0), sq(0.01), sq(0.02), sq(0.5), sq(0.6), sq(0.7), sq(0.8)];
    expect(groupSquares(pts).flatMap((g) => g.richness)).toHaveLength(pts.length);
  });
});

describe("axes that cover the data", () => {
  it("coverTicks reaches the tallest value, which niceTicks can stop short of", () => {
    expect(niceTicks(0, 6500, 4).at(-1)).toBeLessThan(6500);
    for (const max of [6500, 0.73, 1, 40, 2429, 0.004]) {
      const ticks = coverTicks(max, 4);
      expect(ticks[0]).toBe(0);
      expect(ticks.at(-1)).toBeGreaterThanOrEqual(max);
    }
  });

  it("coverTicks stays usable with nothing to draw", () => {
    expect(coverTicks(0)).toEqual([0, 1]);
  });

  it("yearTicks sit on round years and never on a fraction of a year", () => {
    expect(yearTicks(1925, 2026, 6)).toEqual([1940, 1960, 1980, 2000, 2020]);
    expect(yearTicks(2018, 2021, 6)).toEqual([2018, 2019, 2020, 2021]);
    for (const t of yearTicks(1881, 2026, 4)) expect(Number.isInteger(t)).toBe(true);
  });
});
