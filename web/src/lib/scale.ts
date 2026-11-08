export type Scale = (v: number) => number;

/** Maps a data range onto a pixel range. A zero-width domain maps to the middle, not NaN. */
export function linear(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  if (d0 === d1) return () => (r0 + r1) / 2;
  return (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
}

/** Round, human tick values covering [min, max]: 0, 5, 10 rather than 0, 3.7, 7.4. */
export function niceTicks(min: number, max: number, target = 5): number[] {
  if (!(max > min)) return [min];
  const rough = (max - min) / Math.max(1, target);
  const mag = 10 ** Math.floor(Math.log10(rough));
  const norm = rough / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) {
    out.push(Number(v.toFixed(10)));
  }
  return out;
}

/** The index of the value in `xs` closest to `x`: what a crosshair snaps to. */
export function nearestIndex(xs: number[], x: number): number {
  let best = 0;
  for (let i = 1; i < xs.length; i++) {
    if (Math.abs((xs[i] ?? 0) - x) < Math.abs((xs[best] ?? 0) - x)) best = i;
  }
  return best;
}

export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/**
 * Groups yearly counts into bins so a long record does not become a hundred hairline bars: one
 * year per bin up to `maxBars` years, then 5 or 10 years per bin. Empty years inside the range
 * count as zero, so gaps in the record show as gaps.
 */
export function binYears(
  data: { year: number; records: number }[],
  maxBars = 36,
): { start: number; end: number; records: number }[] {
  if (data.length === 0) return [];
  const first = Math.min(...data.map((d) => d.year));
  const last = Math.max(...data.map((d) => d.year));
  const span = last - first + 1;
  const width = span <= maxBars ? 1 : span <= maxBars * 5 ? 5 : 10;
  const start = Math.floor(first / width) * width;
  const out: { start: number; end: number; records: number }[] = [];
  for (let b = start; b <= last; b += width) out.push({ start: b, end: b + width - 1, records: 0 });
  for (const d of data) {
    const bin = out[Math.floor((d.year - start) / width)];
    if (bin) bin.records += d.records;
  }
  return out;
}
