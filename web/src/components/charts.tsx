import { useId, useMemo, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";
import { linear, nearestIndex, niceTicks } from "../lib/scale";
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

const W = 640;
const H = 240;
const M = { top: 14, right: 132, bottom: 40, left: 48 };

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
}: {
  series: LineSeries[];
  xFormat: (x: number) => string;
  yFormat: (y: number) => string;
  xLabel: string;
  caption: string;
  yDomain?: [number, number];
}) {
  const id = useId();
  const { boxRef, show, hide, node } = useTooltip();
  const [active, setActive] = useState<number | null>(null);

  const xs = useMemo(
    () => [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort((a, b) => a - b),
    [series],
  );
  const [xMin, xMax] = [xs[0] ?? 0, xs[xs.length - 1] ?? 1];
  const sx = linear([xMin, xMax], [M.left, W - M.right]);
  const sy = linear(yDomain, [H - M.bottom, M.top]);
  const yTicks = niceTicks(yDomain[0], yDomain[1], 5);

  const valueAt = (s: LineSeries, x: number) => s.points.find((p) => p.x === x)?.y ?? null;

  // Direct labels sit at each line's right end. If two would overlap, none are drawn: nudging
  // them apart would detach them from their lines, and the legend and tooltip carry identity.
  const ends = series
    .map((s) => ({ s, y: [...s.points].reverse().find((p) => p.y != null)?.y ?? null }))
    .filter((e): e is { s: LineSeries; y: number } => e.y != null)
    .map((e) => ({ ...e, py: sy(e.y) }))
    .sort((a, b) => a.py - b.py);
  const labelsFit = ends.every((e, i) => i === 0 || e.py - (ends[i - 1]?.py ?? 0) >= 15);

  const reveal = (i: number, clientX?: number, clientY?: number) => {
    setActive(i);
    const x = xs[i];
    if (x == null) return;
    const box = boxRef.current?.getBoundingClientRect();
    const svgBox = boxRef.current?.querySelector("svg")?.getBoundingClientRect();
    if (!box || !svgBox) return;
    const px = clientX != null ? clientX - box.left : (svgBox.left - box.left) + (sx(x) / W) * svgBox.width;
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
    const xView = ((e.clientX - r.left) / r.width) * W;
    const data = xMin + ((xView - M.left) / (W - M.right - M.left)) * (xMax - xMin);
    reveal(nearestIndex(xs, data), e.clientX, e.clientY);
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const last = xs.length - 1;
    const cur = active ?? (e.key === "ArrowLeft" ? last + 1 : -1);
    const next =
      e.key === "ArrowRight" ? Math.min(last, cur + 1) : e.key === "ArrowLeft" ? Math.max(0, cur - 1)
      : e.key === "Home" ? 0 : e.key === "End" ? last : null;
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
      {series.length > 1 && (
        <ul className="legend" aria-label="Legend">
          {series.map((s) => (
            <li key={s.id}>
              <LineKey s={s} />
              {s.label}
            </li>
          ))}
        </ul>
      )}
      <svg
        className="chart"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-labelledby={`${id}-t`}
        tabIndex={0}
        onPointerMove={onPointerMove}
        onPointerLeave={leave}
        onKeyDown={onKey}
        onBlur={leave}
      >
        <title id={`${id}-t`}>{caption}. Use the arrow keys to move along the chart.</title>
        {yTicks.map((t) => (
          <g key={t}>
            <line className="grid-line" x1={M.left} x2={W - M.right} y1={sy(t)} y2={sy(t)} />
            <text x={M.left - 8} y={sy(t) + 4} textAnchor="end">
              {yFormat(t)}
            </text>
          </g>
        ))}
        <line className="axis-line" x1={M.left} x2={W - M.right} y1={H - M.bottom} y2={H - M.bottom} />
        {xs.map((x) => (
          <text key={x} x={sx(x)} y={H - M.bottom + 16} textAnchor="middle">
            {xFormat(x)}
          </text>
        ))}
        <text x={(M.left + W - M.right) / 2} y={H - 6} textAnchor="middle">
          {xLabel}
        </text>

        {activeX != null && <line className="axis-line" x1={sx(activeX)} x2={sx(activeX)} y1={M.top} y2={H - M.bottom} />}

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
            <text key={s.id} x={W - M.right + 10} y={py + 4}>
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
