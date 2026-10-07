import { useCallback, useRef, useState, type ReactNode } from "react";

interface Tip {
  x: number;
  y: number;
  content: ReactNode;
}

/**
 * One tooltip per chart. Position is in pixels relative to the chart box. Tooltips enhance and
 * never gate: every value they show is also in the chart's table view, and keyboard focus
 * shows the same thing as hover.
 */
export function useTooltip() {
  const boxRef = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip | null>(null);

  const show = useCallback((x: number, y: number, content: ReactNode) => setTip({ x, y, content }), []);
  const hide = useCallback(() => setTip(null), []);

  const node = tip && (
    <div
      className="tooltip"
      role="presentation"
      style={{
        top: Math.max(0, tip.y + 12),
        // Flip to the left of the pointer in the right-hand half so it never leaves the box.
        ...(tip.x > (boxRef.current?.clientWidth ?? 0) * 0.55
          ? { right: Math.max(0, (boxRef.current?.clientWidth ?? 0) - tip.x + 12) }
          : { left: tip.x + 12 }),
      }}
    >
      {tip.content}
    </div>
  );
  return { boxRef, show, hide, node };
}
