/** Rough width in pixels of a 12px label, used to keep axis labels from touching. */
export const textPx = (s: string): number => Math.ceil(s.length * 6.6);

/**
 * Which axis labels to draw so that no two are closer than `gap` pixels, given where each
 * position sits on the axis. The first label is always drawn. So is the last, which replaces its
 * neighbour when the two would touch, unless that neighbour is the first.
 */
export function labelIndicesAt(positions: number[], labelPx: number, gap = 28): Set<number> {
  const out = new Set<number>();
  if (positions.length === 0) return out;
  const need = labelPx + gap;
  let kept = 0;
  out.add(0);
  positions.forEach((p, i) => {
    if (i > 0 && p - (positions[kept] as number) >= need) {
      out.add(i);
      kept = i;
    }
  });
  const last = positions.length - 1;
  if (!out.has(last)) {
    const touches = (positions[last] as number) - (positions[kept] as number) < need;
    // The first label stays. Any other neighbour gives way to the last.
    if (!touches) out.add(last);
    else if (kept !== 0) {
      out.delete(kept);
      out.add(last);
    }
  }
  return out;
}

/** The same for positions an equal `slot` apart, such as years or the bars of a column chart. */
export function labelIndices(count: number, slot: number, labelPx: number, gap = 28): Set<number> {
  return labelIndicesAt(Array.from({ length: count }, (_, i) => i * slot), labelPx, gap);
}

export const median = (values: number[]): number => {
  if (values.length === 0) return NaN;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? (s[mid] as number) : ((s[mid - 1] as number) + (s[mid] as number)) / 2;
};

/** The intercept that goes with a Theil-Sen slope: the median of y - slope * x. */
export const theilSenIntercept = (xs: number[], ys: number[], slope: number): number =>
  median(xs.map((x, i) => (ys[i] as number) - slope * x));

/** "0.4%", "3%", "58%": a share as a person would write it. */
export const shareLabel = (v: number): string =>
  v === 0 ? "0%" : v < 0.01 ? `${(v * 100).toFixed(1)}%` : `${Math.round(v * 100)}%`;

export interface SquareGroup {
  key: string;
  /** What the group is, in words a reader can follow. */
  label: string;
  /** Native richness of each square in the group. */
  richness: number[];
  /** The number of invasive records in each square, for the tooltip. */
  invasive: number[];
}

/**
 * Sorts map squares into groups by how much of their records are invasive: those with none, then
 * up to three groups of equal size among those with some. Squares with the same share stay
 * together. With too few squares that hold invasive records to split, they form one group. The
 * edges come from the data, so a group is never empty and never a stretch of the axis nobody sits
 * on. Each point is [invasive share, native richness, invasive records].
 */
export function groupSquares(points: [number, number, number][]): SquareGroup[] {
  const none = points.filter((p) => p[2] === 0);
  const some = points.filter((p) => p[2] > 0).sort((a, b) => a[0] - b[0]);
  const groups: SquareGroup[] = [];
  if (none.length > 0) {
    groups.push({ key: "none", label: "None", richness: none.map((p) => p[1]), invasive: none.map(() => 0) });
  }
  const parts = some.length >= 12 ? 3 : some.length >= 6 ? 2 : some.length > 0 ? 1 : 0;
  let start = 0;
  for (let k = 1; k <= parts; k++) {
    let end = k === parts ? some.length : Math.floor((some.length * k) / parts);
    // Do not split squares that share a value across two groups.
    while (end < some.length && end > start && (some[end] as number[])[0] === (some[end - 1] as number[])[0]) end++;
    const chunk = some.slice(start, end);
    start = end;
    if (chunk.length === 0) continue;
    const lo = (chunk[0] as number[])[0] as number;
    const hi = (chunk[chunk.length - 1] as number[])[0] as number;
    groups.push({
      key: `some-${k}`,
      label: parts === 1 ? "Some" : lo === hi ? shareLabel(lo) : `${shareLabel(lo)} to ${shareLabel(hi)}`,
      richness: chunk.map((p) => p[1]),
      invasive: chunk.map((p) => p[2]),
    });
  }
  return groups;
}
