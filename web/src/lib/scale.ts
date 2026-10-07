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
