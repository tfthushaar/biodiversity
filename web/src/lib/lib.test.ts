import { describe, expect, it } from "vitest";
import { fmtAgo, fmtCompact, fmtDate, fmtInt, fmtPct, fmtYear, humanise, pluralise } from "./format";
import { clamp, linear, nearestIndex, niceTicks } from "./scale";

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
