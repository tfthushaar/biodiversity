import {
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { labelIndices, labelIndicesAt, median, textPx } from "../lib/layout";
import { binYears, coverTicks, linear, nearestIndex, niceTicks, yearTicks } from "../lib/scale";
import { useTooltip } from "./useTooltip";

// ----------------------------------------------------------------------- table twin

/** Every chart has a table twin: the accessible equivalent, and where hover-only values live. */
export function TableTwin({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: { label: string; numeric?: boolean }[];
  rows: ReactNode[][];
}) {
  return (
    <details className="table-twin">
      <summary>View as table</summary>
      <div className="table-wrap">
        <table>
          <caption>{caption}</caption>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.label} className={c.numeric ? "num" : undefined} scope="col">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {r.map((cell, j) => (
                  <td key={j} className={columns[j]?.numeric ? "num" : undefined}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

// ------------------------------------------------------------------------ bar list

export interface BarItem {
  key: string;
  label: string;
  value: number;
  /** What to print at the bar's tip, if not just the number. */
  display?: string;
  /** Extra line for the tooltip and table. */
  note?: string;
}

/**
 * Horizontal bars for comparing magnitudes. One series, so one colour for every bar (a value
 * ramp on nominal categories would only repeat what the length already says). Bars are capped at
 * 18px, round only at the data end, and carry the value at the tip, so no value is ever clipped
 * by its own mark.
 */
export function BarList({
  items,
  color = "var(--series-1)",
  caption,
  valueLabel = "Value",
  max,
}: {
  items: BarItem[];
  color?: string;
  caption: string;
  valueLabel?: string;
  max?: number;
}) {
  const { boxRef, show, hide, node } = useTooltip();
  const top = max ?? Math.max(1, ...items.map((i) => i.value));
  const place = (e: { clientX: number; clientY: number }, item: BarItem) => {
    const box = boxRef.current?.getBoundingClientRect();
    if (!box) return;
    show(
      e.clientX - box.left,
      e.clientY - box.top,
      <>
        <div className="t-head">{item.label}</div>
        <div className="t-row">
          <span>{valueLabel}</span>
          <strong>{item.display ?? item.value.toLocaleString("en-US")}</strong>
        </div>
        {item.note && <div className="t-head" style={{ marginTop: 4 }}>{item.note}</div>}
      </>,
    );
  };
  return (
    <div className="chart-box" ref={boxRef} onPointerLeave={hide}>
      <ul className="bars" aria-label={caption} style={{ ["--bar" as string]: color }}>
        {items.map((item) => (
          <li
            key={item.key}
            className="bar-row"
            tabIndex={0}
            onPointerMove={(e) => place(e, item)}
            onFocus={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              const box = boxRef.current?.getBoundingClientRect();
              if (box) place({ clientX: r.left + r.width * 0.4, clientY: r.top + r.height / 2 }, item);
            }}
            onBlur={hide}
          >
            <span className="bar-label">{item.label}</span>
            <span className="bar-track">
              {item.value > 0 && (
                <span className="bar-fill" style={{ width: `${(item.value / top) * 100}%`, maxWidth: "calc(100% - 64px)" }} />
              )}
              <span className="bar-value">{item.display ?? item.value.toLocaleString("en-US")}</span>
            </span>
          </li>
        ))}
      </ul>
      {node}
      <TableTwin
        caption={caption}
        columns={[{ label: "Category" }, { label: valueLabel, numeric: true }, { label: "Note" }]}
        rows={items.map((i) => [i.label, i.display ?? i.value.toLocaleString("en-US"), i.note ?? ""])}
      />
    </div>
  );
}

// ------------------------------------------------------------------ measuring a chart

/**
 * The width of a chart's box in pixels, kept current as the window changes. Charts are laid out
 * in real pixels, so a label is 12px at every size and the labels along an axis are spaced by the
 * room there is. A chart drawn at a fixed size and then scaled down shrinks its text with it,
 * which is how labels end up too small to read or on top of one another. Where nothing can be
 * measured (a test, a page not yet laid out) the fallback is used.
 */
function useWidth(ref: RefObject<HTMLElement | null>, fallback = 640): number {
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const next = Math.floor(el.getBoundingClientRect().width);
      if (next >= 160) setWidth((old) => (old === next ? old : next));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const watcher = new ResizeObserver(measure);
    watcher.observe(el);
    return () => watcher.disconnect();
  }, [ref]);
  return width;
}

/** Arrow keys, Home and End move along a chart's positions. */
function stepIndex(e: KeyboardEvent, active: number | null, count: number): number | null {
  const last = count - 1;
  const cur = active ?? (e.key === "ArrowLeft" ? last + 1 : -1);
  return e.key === "ArrowRight" ? Math.min(last, cur + 1)
    : e.key === "ArrowLeft" ? Math.max(0, cur - 1)
    : e.key === "Home" ? 0
    : e.key === "End" ? last
    : null;
}

/** An id safe to use inside url(#...) as well as in aria attributes. */
const safeId = (id: string) => id.replace(/[^a-zA-Z0-9_-]/g, "");

// ---------------------------------------------------------------------- line chart

export interface LineSeries {
  id: string;
  label: string;
  /** A shorter name for the end-of-line label; the legend and tooltip keep the full label. */
  short?: string;
  /** A CSS colour (a design token such as var(--series-2)). */
  color: string;
  /** SVG dash pattern. Series are told apart by line style as well as shade, so the chart
   *  reads the same in greyscale, in print and for readers who cannot separate shades. */
  dash?: string;
  points: { x: number; y: number | null }[];
}

/** The sample of a series' line shown in the legend and the tooltip. */
function LineKey({ s }: { s: Pick<LineSeries, "color" | "dash"> }) {
  return (
    <svg className="legend-key" viewBox="0 0 28 8" aria-hidden="true" focusable="false">
      <line x1="1" y1="4" x2="27" y2="4" stroke={s.color} strokeDasharray={s.dash} />
    </svg>
  );
}

const LINE_H = 260;

/**
 * A multi-series line chart on ONE y axis (never two). The crosshair snaps to the nearest x, one
 * tooltip lists every series at that x, the legend is always present, and direct end-labels are
 * added only when they fit without colliding. Keyboard: arrow keys move the crosshair.
 */
export function LineChart({
  series,
  xFormat,
  yFormat,
  xLabel,
  caption,
  yDomain = [0, 1],
  marker,
}: {
  series: LineSeries[];
  xFormat: (x: number) => string;
  yFormat: (y: number) => string;
  xLabel: string;
  caption: string;
  yDomain?: [number, number];
  /** A vertical line at one x, such as the setting in use, named in the legend. */
  marker?: { x: number; label: string };
}) {
  const id = useId();
  const { boxRef, show, hide, node } = useTooltip();
  const w = useWidth(boxRef);
  const [active, setActive] = useState<number | null>(null);

  const xs = useMemo(
    () => [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort((a, b) => a - b),
    [series],
  );
  const [xMin, xMax] = [xs[0] ?? 0, xs[xs.length - 1] ?? 1];
  const yTicks = niceTicks(yDomain[0], yDomain[1], 5);
  const yLabels = yTicks.map(yFormat);
  // End labels need a column to themselves; below this width the legend carries identity.
  const room = w >= 560;
  const M = { top: 14, right: room ? 104 : 16, bottom: 48, left: Math.max(40, Math.max(...yLabels.map(textPx)) + 18) };
  const base = LINE_H - M.bottom;
  const sx = linear([xMin, xMax], [M.left, w - M.right]);
  const sy = linear(yDomain, [base, M.top]);
  const shown = labelIndicesAt(xs.map(sx), Math.max(0, ...xs.map((x) => textPx(xFormat(x)))));

  const valueAt = (s: LineSeries, x: number) => s.points.find((p) => p.x === x)?.y ?? null;

  // Direct labels sit at each line's right end. If two would overlap, none are drawn: nudging
  // them apart would detach them from their lines, and the legend and tooltip carry identity.
  const ends = series
    .map((s) => ({ s, y: [...s.points].reverse().find((p) => p.y != null)?.y ?? null }))
    .filter((e): e is { s: LineSeries; y: number } => e.y != null)
    .map((e) => ({ ...e, py: sy(e.y) }))
    .sort((a, b) => a.py - b.py);
  const labelsFit = room && ends.every((e, i) => i === 0 || e.py - (ends[i - 1]?.py ?? 0) >= 15);

  const reveal = (i: number, clientX?: number, clientY?: number) => {
    setActive(i);
    const x = xs[i];
    if (x == null) return;
    const box = boxRef.current?.getBoundingClientRect();
    const svgBox = boxRef.current?.querySelector("svg.chart")?.getBoundingClientRect();
    if (!box || !svgBox) return;
    const px = clientX != null ? clientX - box.left : svgBox.left - box.left + (sx(x) / w) * svgBox.width;
    const py = clientY != null ? clientY - box.top : 24;
    show(
      px,
      py,
      <>
        <div className="t-head">
          {xLabel}: <strong>{xFormat(x)}</strong>
        </div>
        {series.map((s) => {
          const v = valueAt(s, x);
          return (
            <div className="t-row" key={s.id}>
              <span>
                <LineKey s={s} />
                {s.label}
              </span>
              <strong>{v == null ? "–" : yFormat(v)}</strong>
            </div>
          );
        })}
      </>,
    );
  };

  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const xView = ((e.clientX - r.left) / r.width) * w;
    const data = xMin + ((xView - M.left) / (w - M.right - M.left)) * (xMax - xMin);
    reveal(nearestIndex(xs, data), e.clientX, e.clientY);
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const next = stepIndex(e, active, xs.length);
    if (next == null) return;
    e.preventDefault();
    reveal(next);
  };
  const leave = () => {
    setActive(null);
    hide();
  };

  const activeX = active != null ? xs[active] : undefined;

  return (
    <div className="chart-box" ref={boxRef}>
      {(series.length > 1 || marker) && (
        <ul className="legend" aria-label="Legend">
          {series.length > 1 &&
            series.map((s) => (
              <li key={s.id}>
                <LineKey s={s} />
                {s.label}
              </li>
            ))}
          {marker && (
            <li>
              <svg className="legend-key" viewBox="0 0 28 8" aria-hidden="true" focusable="false">
                <line x1="14" y1="-2" x2="14" y2="10" className="marker-line" />
              </svg>
              {marker.label}
            </li>
          )}
        </ul>
      )}
      <svg
        className="chart"
        viewBox={`0 0 ${w} ${LINE_H}`}
        role="img"
        aria-labelledby={`${id}-t`}
        tabIndex={0}
        onPointerMove={onPointerMove}
        onPointerLeave={leave}
        onKeyDown={onKey}
        onBlur={leave}
      >
        <title id={`${id}-t`}>{caption}. Use the arrow keys to move along the chart.</title>
        {yTicks.map((t, i) => (
          <g key={t}>
            <line className="grid-line" x1={M.left} x2={w - M.right} y1={sy(t)} y2={sy(t)} />
            <text x={M.left - 8} y={sy(t)} dominantBaseline="central" textAnchor="end">
              {yLabels[i]}
            </text>
          </g>
        ))}
        <line className="axis-line" x1={M.left} x2={w - M.right} y1={base} y2={base} />
        {xs.map((x, i) =>
          shown.has(i) ? (
            <text key={x} x={sx(x)} y={base + 20} textAnchor="middle">
              {xFormat(x)}
            </text>
          ) : null,
        )}
        <text x={(M.left + w - M.right) / 2} y={LINE_H - 6} textAnchor="middle">
          {xLabel}
        </text>

        {marker && marker.x >= xMin && marker.x <= xMax && (
          <line className="marker-line" x1={sx(marker.x)} x2={sx(marker.x)} y1={M.top} y2={base} />
        )}
        {activeX != null && <line className="axis-line" x1={sx(activeX)} x2={sx(activeX)} y1={M.top} y2={base} />}

        {series.map((s) => {
          const pts = s.points.filter((p): p is { x: number; y: number } => p.y != null);
          return (
            <g key={s.id}>
              <polyline
                className="line"
                stroke={s.color}
                strokeDasharray={s.dash}
                points={pts.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ")}
              />
              {pts.length > 0 && (
                <circle
                  className="ring"
                  fill={s.color}
                  r={4}
                  cx={sx(pts[pts.length - 1]!.x)}
                  cy={sy(pts[pts.length - 1]!.y)}
                />
              )}
              {activeX != null &&
                (() => {
                  const v = valueAt(s, activeX);
                  return v == null ? null : <circle className="ring" fill={s.color} r={5} cx={sx(activeX)} cy={sy(v)} />;
                })()}
            </g>
          );
        })}

        {labelsFit &&
          ends.map(({ s, py }) => (
            <text key={s.id} x={w - M.right + 10} y={py} dominantBaseline="central">
              {s.short ?? s.label}
            </text>
          ))}
      </svg>
      {node}
      <TableTwin
        caption={caption}
        columns={[{ label: xLabel }, ...series.map((s) => ({ label: s.label, numeric: true }))]}
        rows={xs.map((x) => [xFormat(x), ...series.map((s) => {
          const v = valueAt(s, x);
          return v == null ? "–" : yFormat(v);
        })])}
      />
    </div>
  );
}

// -------------------------------------------------------------------- column chart

const COL_H = 220;

/**
 * Records per year as columns. One series on one axis, thin columns with a gap between them,
 * rounded at the top only. Long records are binned (see `binYears`). The pointer or the arrow
 * keys read out a column; the same values are in the table view.
 */
export function ColumnChart({
  data,
  caption,
  valueLabel = "Records",
}: {
  data: { year: number; records: number }[];
  caption: string;
  valueLabel?: string;
}) {
  const id = useId();
  const { boxRef, show, hide, node } = useTooltip();
  const w = useWidth(boxRef);
  const [active, setActive] = useState<number | null>(null);
  const bins = useMemo(() => binYears(data), [data]);
  if (bins.length === 0) return null;

  const max = Math.max(1, ...bins.map((b) => b.records));
  const ticks = coverTicks(max, 4);
  const top = ticks[ticks.length - 1] ?? max;
  const tickLabels = ticks.map((t) => t.toLocaleString("en-US"));
  const M = { top: 12, right: 16, bottom: 34, left: Math.max(34, Math.max(...tickLabels.map(textPx)) + 18) };
  const base = COL_H - M.bottom;
  const sy = linear([0, top], [base, M.top]);
  const slot = (w - M.left - M.right) / bins.length;
  const barW = Math.max(2, slot - Math.min(3, slot * 0.25));
  const label = (b: (typeof bins)[number]) => (b.start === b.end ? String(b.start) : `${b.start} to ${b.end}`);
  const axisLabel = (b: (typeof bins)[number]) => (b.end - b.start >= 9 ? `${b.start}s` : String(b.start));
  const shown = labelIndices(bins.length, slot, Math.max(...bins.map((b) => textPx(axisLabel(b)))));

  const reveal = (i: number, clientX?: number, clientY?: number) => {
    setActive(i);
    const b = bins[i];
    const box = boxRef.current?.getBoundingClientRect();
    const svg = boxRef.current?.querySelector("svg.chart")?.getBoundingClientRect();
    if (!b || !box || !svg) return;
    const px = clientX != null ? clientX - box.left : svg.left - box.left + ((M.left + slot * (i + 0.5)) / w) * svg.width;
    const py = clientY != null ? clientY - box.top : 24;
    show(
      px,
      py,
      <>
        <div className="t-head">{label(b)}</div>
        <div className="t-row">
          <span>{valueLabel}</span>
          <strong>{b.records.toLocaleString("en-US")}</strong>
        </div>
      </>,
    );
  };
  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * w - M.left;
    reveal(Math.min(bins.length - 1, Math.max(0, Math.floor(x / slot))), e.clientX, e.clientY);
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const next = stepIndex(e, active, bins.length);
    if (next == null) return;
    e.preventDefault();
    reveal(next);
  };
  const leave = () => {
    setActive(null);
    hide();
  };

  return (
    <div className="chart-box" ref={boxRef}>
      <svg
        className="chart"
        viewBox={`0 0 ${w} ${COL_H}`}
        role="img"
        aria-labelledby={`${id}-t`}
        tabIndex={0}
        onPointerMove={onMove}
        onPointerLeave={leave}
        onKeyDown={onKey}
        onBlur={leave}
      >
        <title id={`${id}-t`}>{caption}. Use the arrow keys to move along the chart.</title>
        {ticks.map((t, i) => (
          <g key={t}>
            <line className="grid-line" x1={M.left} x2={w - M.right} y1={sy(t)} y2={sy(t)} />
            <text x={M.left - 8} y={sy(t)} dominantBaseline="central" textAnchor="end">
              {tickLabels[i]}
            </text>
          </g>
        ))}
        <line className="axis-line" x1={M.left} x2={w - M.right} y1={base} y2={base} />
        {bins.map((b, i) => {
          const x = M.left + slot * i + (slot - barW) / 2;
          const h = b.records > 0 ? Math.max(2, base - sy(b.records)) : 0;
          const r = Math.min(3, barW / 2, h);
          const y = base - h;
          return (
            <g key={b.start}>
              {h > 0 && (
                <path
                  className={`col${active === i ? " on" : ""}`}
                  d={`M${x},${base} V${y + r} Q${x},${y} ${x + r},${y} H${x + barW - r} Q${x + barW},${y} ${x + barW},${y + r} V${base} Z`}
                />
              )}
              {shown.has(i) && (
                <text x={x + barW / 2} y={base + 18} textAnchor="middle">
                  {axisLabel(b)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {node}
      <TableTwin
        caption={caption}
        columns={[{ label: "Year" }, { label: valueLabel, numeric: true }]}
        rows={bins.map((b) => [label(b), b.records.toLocaleString("en-US")])}
      />
    </div>
  );
}

// ---------------------------------------------------------------- yearly dots with a trend

/** One year (or one of anything along x): its value, how much it rests on, and what to say of it. */
export interface DotRow {
  x: number;
  y: number;
  /** How much the point rests on, such as the observations in a year. It sets the dot's area. */
  weight: number;
  detail: { label: string; value: string }[];
}

const DOTS_H = 300;

/**
 * A value over time where each year rests on a different amount of data. The area of a dot shows
 * how much that year rests on, so a reader sees which years to trust, and a line shows the
 * trend. Hover or the arrow keys read out a year; the table view lists every one.
 */
export function TrendDots({
  rows,
  line,
  xLabel,
  yLabel,
  xFormat = String,
  yFormat,
  caption,
  lineLabel = "Trend",
  weightLabel = "Observations",
}: {
  rows: DotRow[];
  /** y = slope * x + intercept, drawn across the data. */
  line?: { slope: number; intercept: number } | null;
  xLabel: string;
  yLabel: string;
  xFormat?: (x: number) => string;
  yFormat: (y: number) => string;
  caption: string;
  lineLabel?: string;
  weightLabel?: string;
}) {
  const id = useId();
  const clip = `${safeId(id)}-clip`;
  const { boxRef, show, hide, node } = useTooltip();
  const w = useWidth(boxRef);
  const [active, setActive] = useState<number | null>(null);
  if (rows.length === 0) return null;

  const sorted = [...rows].sort((a, b) => a.x - b.x);
  const [x0, x1] = [sorted[0]!.x, sorted[sorted.length - 1]!.x];
  const lineAt = (x: number) => (line ? line.slope * x + line.intercept : null);
  const yMax = Math.max(0.01, ...sorted.map((r) => r.y), ...(line ? [lineAt(x0)!, lineAt(x1)!] : []));
  const ticks = coverTicks(yMax, 5);
  const top = ticks[ticks.length - 1] ?? yMax;
  const tickLabels = ticks.map(yFormat);
  const M = { top: 14, right: 16, bottom: 50, left: Math.max(40, Math.max(...tickLabels.map(textPx)) + 18) };
  const base = DOTS_H - M.bottom;
  const sx = linear([x0, x1], [M.left + 8, w - M.right - 8]);
  const sy = linear([0, top], [base, M.top]);
  const maxWeight = Math.max(1, ...sorted.map((r) => r.weight));
  const radius = (r: DotRow) => 3 + 6 * Math.sqrt(Math.max(0, r.weight) / maxWeight);
  const xTicks = yearTicks(x0, x1, w < 480 ? 3 : 6);

  const reveal = (i: number, clientX?: number, clientY?: number) => {
    setActive(i);
    const r = sorted[i];
    const box = boxRef.current?.getBoundingClientRect();
    const svg = boxRef.current?.querySelector("svg.chart")?.getBoundingClientRect();
    if (!r || !box || !svg) return;
    const px = clientX != null ? clientX - box.left : svg.left - box.left + (sx(r.x) / w) * svg.width;
    const py = clientY != null ? clientY - box.top : 24;
    show(
      px,
      py,
      <>
        <div className="t-head">
          {xLabel}: <strong>{xFormat(r.x)}</strong>
        </div>
        <div className="t-row">
          <span>{yLabel}</span>
          <strong>{yFormat(r.y)}</strong>
        </div>
        {r.detail.map((d) => (
          <div className="t-row" key={d.label}>
            <span>{d.label}</span>
            <strong>{d.value}</strong>
          </div>
        ))}
      </>,
    );
  };
  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const xView = ((e.clientX - rect.left) / rect.width) * w;
    const data = x0 + ((xView - M.left - 8) / (w - M.right - M.left - 16)) * (x1 - x0);
    reveal(nearestIndex(sorted.map((r) => r.x), data), e.clientX, e.clientY);
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const next = stepIndex(e, active, sorted.length);
    if (next == null) return;
    e.preventDefault();
    reveal(next);
  };
  const leave = () => {
    setActive(null);
    hide();
  };

  return (
    <div className="chart-box" ref={boxRef}>
      <ul className="legend" aria-label="Legend">
        <li>
          <svg className="legend-key" viewBox="0 0 28 8" aria-hidden="true" focusable="false">
            <circle cx="14" cy="4" r="3.5" fill="var(--series-1)" fillOpacity="0.6" />
          </svg>
          One year. Larger dots rest on more {weightLabel.toLowerCase()}.
        </li>
        {line && (
          <li>
            <svg className="legend-key" viewBox="0 0 28 8" aria-hidden="true" focusable="false">
              <line x1="1" y1="4" x2="27" y2="4" stroke="var(--ink)" />
            </svg>
            {lineLabel}
          </li>
        )}
      </ul>
      <svg
        className="chart"
        viewBox={`0 0 ${w} ${DOTS_H}`}
        role="img"
        aria-labelledby={`${id}-t`}
        tabIndex={0}
        onPointerMove={onMove}
        onPointerLeave={leave}
        onKeyDown={onKey}
        onBlur={leave}
      >
        <title id={`${id}-t`}>{caption}. Use the arrow keys to move along the chart.</title>
        <clipPath id={clip}>
          <rect x={M.left} y={M.top} width={w - M.left - M.right} height={base - M.top} />
        </clipPath>
        {ticks.map((t, i) => (
          <g key={t}>
            <line className="grid-line" x1={M.left} x2={w - M.right} y1={sy(t)} y2={sy(t)} />
            <text x={M.left - 8} y={sy(t)} dominantBaseline="central" textAnchor="end">
              {tickLabels[i]}
            </text>
          </g>
        ))}
        <line className="axis-line" x1={M.left} x2={w - M.right} y1={base} y2={base} />
        {xTicks.map((t) => (
          <g key={t}>
            <line className="axis-line" x1={sx(t)} x2={sx(t)} y1={base} y2={base + 4} />
            <text x={sx(t)} y={base + 20} textAnchor="middle">
              {xFormat(t)}
            </text>
          </g>
        ))}
        <text x={(M.left + w - M.right) / 2} y={DOTS_H - 6} textAnchor="middle">
          {xLabel}
        </text>
        {line && (
          <line
            className="trend-line"
            clipPath={`url(#${clip})`}
            x1={sx(x0)}
            y1={sy(lineAt(x0)!)}
            x2={sx(x1)}
            y2={sy(lineAt(x1)!)}
          />
        )}
        {active != null && <line className="axis-line" x1={sx(sorted[active]!.x)} x2={sx(sorted[active]!.x)} y1={M.top} y2={base} />}
        {sorted.map((r, i) => (
          <circle
            key={r.x}
            className={`dot-point${active === i ? " on" : ""}`}
            cx={sx(r.x)}
            cy={sy(r.y)}
            r={radius(r)}
          />
        ))}
      </svg>
      {node}
      <TableTwin
        caption={caption}
        columns={[
          { label: xLabel },
          { label: yLabel, numeric: true },
          ...sorted[0]!.detail.map((d) => ({ label: d.label, numeric: true })),
        ]}
        rows={sorted.map((r) => [xFormat(r.x), yFormat(r.y), ...r.detail.map((d) => d.value)])}
      />
    </div>
  );
}

// ------------------------------------------------------------------ dots grouped by class

export interface DotGroup {
  key: string;
  label: string;
  values: { y: number; note?: string }[];
}

const GROUP_PLOT = 214;

/** The same position every time for the same dot, so a chart does not shuffle when it redraws. */
const jitter = (i: number): number => (((i * 2654435761) >>> 0) % 1000) / 1000 - 0.5;

/**
 * Dots in columns, one column for each class, with the median of each marked. It shows many
 * squares at the same place side by side, which a scatter plot piles on top of each other, and
 * puts the question a correlation answers (does the middle fall from one class to the next?)
 * where the eye can read it. The table view gives each class's count, median and range.
 */
export function GroupedDots({
  groups,
  xLabel,
  yLabel,
  caption,
}: {
  groups: DotGroup[];
  xLabel: string;
  yLabel: string;
  caption: string;
}) {
  const id = useId();
  const { boxRef, show, hide, node } = useTooltip();
  const w = useWidth(boxRef);
  const shown = groups.filter((g) => g.values.length > 0);
  if (shown.length === 0) return null;

  const yMax = Math.max(1, ...shown.flatMap((g) => g.values.map((v) => v.y)));
  const ticks = coverTicks(yMax, 5);
  const top = ticks[ticks.length - 1] ?? yMax;
  const left = Math.max(44, Math.max(...ticks.map((t) => textPx(String(t)))) + 34);
  const band = (w - left - 12) / shown.length;
  const spread = Math.min(band * 0.7, 120);
  const medians = shown.map((g) => median(g.values.map((v) => v.y)));
  const roomForMedian = band >= 92;
  // A class named "1% to 4%" breaks into two lines when its column is too narrow for one.
  const wrap = shown.some((g) => textPx(g.label) + 10 > band);
  const nameLines = (label: string) =>
    wrap && label.includes(" to ") ? label.split(" to ").map((part, i) => (i ? `to ${part}` : part)) : [label];
  const rows = Math.max(...shown.map((g) => nameLines(g.label).length)) + 1 + (roomForMedian ? 1 : 0);
  const lastRow = 20 + 16 * (rows - 1);
  const M = { top: 12, right: 12, bottom: lastRow + 26, left };
  const H = M.top + GROUP_PLOT + M.bottom;
  const base = M.top + GROUP_PLOT;
  const sy = linear([0, top], [base, M.top]);

  const at = (e: { clientX: number; clientY: number }, content: ReactNode) => {
    const box = boxRef.current?.getBoundingClientRect();
    if (box) show(e.clientX - box.left, e.clientY - box.top, content);
  };

  return (
    <div className="chart-box" ref={boxRef} onPointerLeave={hide}>
      <svg className="chart" viewBox={`0 0 ${w} ${H}`} role="img" aria-labelledby={`${id}-t`}>
        <title id={`${id}-t`}>{caption}</title>
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid-line" x1={M.left} x2={w - M.right} y1={sy(t)} y2={sy(t)} />
            <text x={M.left - 8} y={sy(t)} dominantBaseline="central" textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        <line className="axis-line" x1={M.left} x2={w - M.right} y1={base} y2={base} />
        <text transform={`translate(13 ${(M.top + base) / 2}) rotate(-90)`} textAnchor="middle">
          {yLabel}
        </text>
        {shown.map((g, gi) => {
          const cx = M.left + band * (gi + 0.5);
          const med = medians[gi] as number;
          return (
            <g key={g.key}>
              {g.values.map((v, i) => (
                <circle
                  key={i}
                  className="dot-point"
                  cx={cx + jitter(i + gi * 97) * spread}
                  cy={sy(v.y)}
                  r={4.5}
                  onPointerMove={(e) =>
                    at(
                      e,
                      <>
                        <div className="t-head">{g.label}</div>
                        <div className="t-row">
                          <span>{yLabel}</span>
                          <strong>{v.y.toFixed(1)}</strong>
                        </div>
                        {v.note && <div className="t-head" style={{ marginTop: 4 }}>{v.note}</div>}
                      </>,
                    )
                  }
                />
              ))}
              <line
                className="median-line"
                x1={cx - spread / 2 - 6}
                x2={cx + spread / 2 + 6}
                y1={sy(med)}
                y2={sy(med)}
                onPointerMove={(e) =>
                  at(
                    e,
                    <>
                      <div className="t-head">{g.label}</div>
                      <div className="t-row">
                        <span>Median</span>
                        <strong>{med.toFixed(1)}</strong>
                      </div>
                    </>,
                  )
                }
              />
              {nameLines(g.label).map((line, k) => (
                <text key={k} x={cx} y={base + 20 + 16 * k} textAnchor="middle" className="group-label">
                  {line}
                </text>
              ))}
              <text x={cx} y={base + 20 + 16 * (rows - (roomForMedian ? 2 : 1))} textAnchor="middle">
                {`n = ${g.values.length}`}
              </text>
              {roomForMedian && (
                <text x={cx} y={base + lastRow} textAnchor="middle">
                  {`median ${med.toFixed(1)}`}
                </text>
              )}
            </g>
          );
        })}
        <text x={(M.left + w - M.right) / 2} y={H - 6} textAnchor="middle">
          {xLabel}
        </text>
      </svg>
      {node}
      <TableTwin
        caption={caption}
        columns={[
          { label: "Invasive share" },
          { label: "Squares", numeric: true },
          { label: "Median", numeric: true },
          { label: "Lowest", numeric: true },
          { label: "Highest", numeric: true },
        ]}
        rows={shown.map((g, gi) => [
          g.label,
          String(g.values.length),
          (medians[gi] as number).toFixed(1),
          Math.min(...g.values.map((v) => v.y)).toFixed(1),
          Math.max(...g.values.map((v) => v.y)).toFixed(1),
        ])}
      />
    </div>
  );
}

// ------------------------------------------------------------------- an estimate and its range

/**
 * One estimate on a fixed scale with its interval, for a correlation from -1 to 1. The ends of the
 * scale say what each direction means, so the picture can be read without the sentence beside it.
 */
export function IntervalPlot({
  value,
  low,
  high,
  min = -1,
  max = 1,
  minNote,
  maxNote,
  caption,
}: {
  value: number;
  low?: number | null;
  high?: number | null;
  min?: number;
  max?: number;
  minNote: string;
  maxNote: string;
  caption: string;
}) {
  const id = useId();
  const boxRef = useRef<HTMLDivElement>(null);
  const w = useWidth(boxRef, 520);
  const pad = 30;
  const x = linear([min, max], [pad, w - pad]);
  const axis = 30;
  const ticks = [min, (min + max) / 2, max];
  // Side by side when both notes fit on one line, one above the other when they do not.
  const stacked = textPx(minNote) + textPx(maxNote) + 24 > w - 2 * pad;
  const height = stacked ? 106 : 88;
  return (
    <div className="chart-box" ref={boxRef}>
      <svg className="chart" viewBox={`0 0 ${w} ${height}`} role="img" aria-labelledby={`${id}-t`}>
        <title id={`${id}-t`}>{caption}</title>
        <line className="axis-line" x1={x(min)} x2={x(max)} y1={axis} y2={axis} />
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid-line" x1={x(t)} x2={x(t)} y1={axis - 9} y2={axis + 9} />
            <text x={x(t)} y={axis + 26} textAnchor="middle">
              {t > 0 ? `+${t}` : t}
            </text>
          </g>
        ))}
        {low != null && high != null && (
          <line className="interval" x1={x(low)} x2={x(high)} y1={axis} y2={axis} />
        )}
        <circle className="ring" fill="var(--series-1)" r={6} cx={x(value)} cy={axis} />
        <text x={x(min)} y={80} textAnchor="start">
          {minNote}
        </text>
        <text x={stacked ? x(min) : x(max)} y={stacked ? 98 : 80} textAnchor={stacked ? "start" : "end"}>
          {maxNote}
        </text>
      </svg>
    </div>
  );
}

// ------------------------------------------------------------ shares of a whole, side by side

export type Tone = "good" | "bad" | "other";

export interface ShareSegment {
  key: string;
  label: string;
  /** A fraction of the whole, 0 to 1. */
  share: number;
  tone: Tone;
}

export interface ShareRow {
  key: string;
  label: string;
  segments: ShareSegment[];
}

const sharePct = (s: number) => `${(s * 100).toFixed(1)}%`;
const TONE_WORD: Record<Tone, string> = { good: "solid", bad: "hatched", other: "pale" };

/**
 * One bar for each question, split into what happened to the whole: of 100 photos, how many were
 * named correctly, named wrongly or left as "unknown". Each segment is told apart by its fill
 * (solid, hatched, pale) as well as by the words beside it, and each bar lists its figures in
 * text, so nothing depends on seeing the colours.
 */
export function ShareBars({ rows, caption }: { rows: ShareRow[]; caption: string }) {
  return (
    <div className="chart-box">
      <ul className="share-list" aria-label={caption}>
        {rows.map((row) => (
          <li key={row.key} className="share-row">
            <div className="share-label">{row.label}</div>
            <div
              className="share-bar"
              role="img"
              aria-label={row.segments.map((s) => `${s.label} ${sharePct(s.share)}`).join(", ")}
            >
              {row.segments
                .filter((s) => s.share > 0)
                .map((s) => (
                  <span
                    key={s.key}
                    className={`seg tone-${s.tone}`}
                    style={{ flexBasis: `${Number((s.share * 100).toFixed(2))}%`, minWidth: 3 }}
                    title={`${s.label}: ${sharePct(s.share)}`}
                  >
                    {s.share >= 0.16 && <span className="seg-text">{sharePct(s.share)}</span>}
                  </span>
                ))}
            </div>
            <ul className="share-key">
              {row.segments.map((s) => (
                <li key={s.key}>
                  <span className={`swatch tone-${s.tone}`} aria-hidden="true" />
                  <strong>{sharePct(s.share)}</strong> {s.label}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      <TableTwin
        caption={caption}
        columns={[{ label: "Group" }, { label: "Outcome" }, { label: "Share", numeric: true }, { label: "Fill" }]}
        rows={rows.flatMap((r) => r.segments.map((s) => [r.label, s.label, sharePct(s.share), TONE_WORD[s.tone]]))}
      />
    </div>
  );
}

// ------------------------------------------------------------------ rates and their ranges

export interface RateRow {
  key: string;
  label: string;
  /** What the rate is out of, such as "225 of 265 invasive-plant photos". */
  note: string;
  rate: number;
  low: number;
  high: number;
  /** Which way is good, so a reader knows whether a high or a low value is the result they want. */
  goal: "higher" | "lower";
}

/**
 * Several rates on one 0 to 100% scale, each with the range the true value could lie in. A rate
 * from few trials has a wide range, so the picture shows how much each figure can be trusted, not
 * only its value. Each row says whether higher or lower is better.
 */
export function RateRanges({ rows, caption }: { rows: RateRow[]; caption: string }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const w = useWidth(boxRef);
  const pad = 10;
  const x = linear([0, 1], [pad, w - pad]);
  const quarters = [0, 0.25, 0.5, 0.75, 1];
  return (
    <div className="chart-box" ref={boxRef}>
      <ul className="rate-list" aria-label={caption}>
        {rows.map((r) => (
          <li key={r.key} className="rate-row">
            <div className="rate-head">
              <span>{r.label}</span>
              <strong>{sharePct(r.rate)}</strong>
            </div>
            <svg className="chart" viewBox={`0 0 ${w} 24`} aria-hidden="true" focusable="false">
              {quarters.map((q) => (
                <line key={q} className="grid-line" x1={x(q)} x2={x(q)} y1={2} y2={22} />
              ))}
              <line className="axis-line" x1={x(0)} x2={x(1)} y1={12} y2={12} />
              <line className="interval" x1={x(r.low)} x2={x(r.high)} y1={12} y2={12} />
              <circle className="ring" fill="var(--series-1)" r={6} cx={x(r.rate)} cy={12} />
            </svg>
            <div className="rate-note">
              {r.note}. True value likely between {sharePct(r.low)} and {sharePct(r.high)}. {r.goal === "higher" ? "Higher" : "Lower"} is better.
            </div>
          </li>
        ))}
      </ul>
      <svg className="chart" viewBox={`0 0 ${w} 22`} aria-hidden="true" focusable="false">
        {quarters.map((q) => (
          <text key={q} x={x(q)} y={14} textAnchor={q === 0 ? "start" : q === 1 ? "end" : "middle"}>
            {`${q * 100}%`}
          </text>
        ))}
      </svg>
      <TableTwin
        caption={caption}
        columns={[{ label: "Measure" }, { label: "Rate", numeric: true }, { label: "Lowest likely", numeric: true }, { label: "Highest likely", numeric: true }, { label: "Better" }]}
        rows={rows.map((r) => [r.label, sharePct(r.rate), sharePct(r.low), sharePct(r.high), r.goal])}
      />
    </div>
  );
}
