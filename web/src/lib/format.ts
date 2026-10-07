/** 1284 -> "1,284". Missing values read as an em dash, never as 0. */
export function fmtInt(n: number | null | undefined): string {
  return n == null || Number.isNaN(n) ? "–" : Math.round(n).toLocaleString("en-US");
}

/** Compact for tiles: 1284 -> "1,284", 12900 -> "12.9K", 4_200_000 -> "4.2M". */
export function fmtCompact(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "–";
  const abs = Math.abs(n);
  if (abs < 10_000) return fmtInt(n);
  if (abs < 1_000_000) return `${trim(n / 1_000)}K`;
  return `${trim(n / 1_000_000)}M`;
}
const trim = (x: number) => x.toFixed(1).replace(/\.0$/, "");

/** 0.8494 -> "84.9%". Pass `digits` for coarser figures. */
export function fmtPct(x: number | null | undefined, digits = 1): string {
  return x == null || Number.isNaN(x) ? "–" : `${(x * 100).toFixed(digits)}%`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-08-05T10:00:00+00:00" -> "5 Aug 2026". Always UTC, so every viewer sees the same date. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "–";
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function fmtYear(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "–" : String(d.getUTCFullYear());
}

/** "5 hours ago" style, for "last updated". */
export function fmtAgo(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "never";
  const secs = (now.getTime() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(secs)) return "–";
  if (secs < 90) return "just now";
  const unit = (n: number, name: string) => {
    const k = Math.max(1, Math.round(n));
    return `${k} ${name}${k === 1 ? "" : "s"} ago`;
  };
  const minutes = secs / 60;
  if (minutes < 60) return unit(minutes, "minute");
  const hours = minutes / 60;
  if (hours < 24) return unit(hours, "hour");
  const days = hours / 24;
  if (days < 30) return unit(days, "day");
  if (days < 365) return unit(days / 30, "month");
  return unit(days / 365, "year");
}

/** "native_lookalike" -> "native look-alike"; "unverified_concern" -> "unverified concern". */
export function humanise(token: string): string {
  return token.replace(/_/g, " ").replace("lookalike", "look-alike");
}

export function pluralise(n: number, one: string, many = `${one}s`): string {
  return `${fmtInt(n)} ${n === 1 ? one : many}`;
}
