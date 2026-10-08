import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { errorMessage } from "../api/rest";
import type { Certainty } from "../api/types";
import { humanise } from "../lib/format";
import { Icon } from "./icons";

// ---------------------------------------------------------------------------- states

export function Loading({ what = "data" }: { what?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      Loading {what}…
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="state error" role="alert">
      <Icon name="warning" />
      <div>
        <strong>Couldn’t load this.</strong>
        <div>{errorMessage(error)}</div>
        {onRetry && (
          <button className="btn" onClick={onRetry} style={{ marginTop: 8 }}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state">{children}</div>;
}

/**
 * Renders a query's states. On refetch the previous result stays on screen, dimmed, so the page
 * never flashes a skeleton or jumps.
 */
export function QueryView<T>({
  query,
  what,
  children,
}: {
  query: UseQueryResult<T>;
  what?: string;
  children: (data: T) => ReactNode;
}) {
  if (query.isError && !query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (query.data === undefined) return <Loading what={what} />;
  return <div className={query.isFetching && !query.isPending ? "refetching" : undefined}>{children(query.data)}</div>;
}

// ----------------------------------------------------------------------------- tiles

export function StatTile({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="card tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

/** How far a count is from the amount a method needs. Reads in words and as a meter. */
export function Meter({
  label,
  value,
  target,
  unit,
  limit = false,
}: {
  label: string;
  value: number;
  target: number;
  unit: string;
  /** The target is a ceiling to stay under, not a requirement to reach. */
  limit?: boolean;
}) {
  const pct = target > 0 ? Math.min(1, value / target) : 0;
  const met = !limit && value >= target;
  return (
    <div className="meter">
      <div className="meter-head">
        <span>{label}</span>
        <span>
          {met ? (
            <>
              <strong>{value.toLocaleString("en-US")}</strong> {unit} · {target.toLocaleString("en-US")} needed, met
            </>
          ) : (
            <>
              <strong>{value.toLocaleString("en-US")}</strong> of {target.toLocaleString("en-US")} {unit}
            </>
          )}
        </span>
      </div>
      <div
        className="meter-track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={target}
        aria-valuenow={Math.min(value, target)}
        aria-valuetext={`${value} of ${target} ${unit}`}
      >
        <div className="meter-fill" style={{ width: `${pct * 100}%` }} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------- badges

/** A record's kind. The colour is a mark beside a word: never colour alone. */
export function KindBadge({ kind }: { kind: "invasive" | "native" | "introduced" }) {
  return (
    <span className={`badge ${kind}`}>
      <span className="dot" aria-hidden="true" />
      {kind}
    </span>
  );
}

const CERTAINTY_COPY: Record<Certainty, string> = {
  experimental: "Controlled experiment",
  observational: "Field observation",
  review: "Reported in a review",
  preliminary: "Preliminary",
  unverified_concern: "Unverified concern",
};

export function CertaintyBadge({ certainty }: { certainty: Certainty }) {
  return (
    <span className="badge" title="How firmly the source supports this">
      {CERTAINTY_COPY[certainty] ?? humanise(certainty)}
    </span>
  );
}

export function EvidenceBadge({ label, level }: { label: string; level: string | null }) {
  if (!level) return null;
  return (
    <span className="badge">
      {label}: <strong>{level}</strong>
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: "low" | "medium" | "high" }) {
  const level = severity === "high" ? 3 : severity === "medium" ? 2 : 1;
  return (
    <span className="badge strong">
      <span className="severity" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <i key={i} className={i <= level ? "on" : undefined} />
        ))}
      </span>
      {severity}
    </span>
  );
}
