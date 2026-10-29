import { parseServerTime } from "../../lib/serverTime";

/** "1 occurrence", "7 occurrences". */
export function count(n: number, noun: string): string {
  return `${n.toLocaleString()} ${plural(n, noun)}`;
}

export function plural(n: number, noun: string): string {
  return n === 1 ? noun : `${noun}s`;
}

/**
 * "1 kind of issue", "6 kinds of issues": both words change with the count, so
 * `count` cannot build it (docs/plain-language.md, Terms).
 */
export function countKinds(n: number): string {
  return `${n.toLocaleString()} ${n === 1 ? "kind of issue" : "kinds of issues"}`;
}

/** A signed change as the table prints it: "+141", "−4" (a true minus), "±0". */
export function signed(n: number): string {
  if (n > 0) return `+${n.toLocaleString()}`;
  if (n < 0) return `−${Math.abs(n).toLocaleString()}`;
  return "±0";
}

/** "27 days ago", in words, for sentences; the axis uses the short "27d ago". */
export function agoLong(iso: string | null): string {
  if (!iso) return "time not recorded";
  const at = parseServerTime(iso);
  if (Number.isNaN(at)) return "time not recorded";
  const hours = Math.max(0, Math.floor((Date.now() - at) / 3_600_000));
  if (hours < 1) return "less than an hour ago";
  if (hours < 24) return `${count(hours, "hour")} ago`;
  const days = Math.floor(hours / 24);
  if (days < 60) return `${count(days, "day")} ago`;
  const months = Math.floor(days / 30);
  if (months < 24) return `${count(months, "month")} ago`;
  return `${count(Math.floor(days / 365), "year")} ago`;
}

/**
 * "Oct 20, 2026" (or "Oct 20, 2026, 2:05 PM" with `withTime`), in the
 * reader's own locale, for the "Reports to compare" choices and the
 * side-by-side Scanned row. A date, not "27 days ago": two reports are told
 * apart by when they ran, and a date stays true in a screenshot.
 */
export function dateText(iso: string | null, withTime = false): string {
  const at = parseServerTime(iso);
  if (Number.isNaN(at)) return "Time not recorded";
  return new Intl.DateTimeFormat(undefined, withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" }).format(at);
}

/** How long after `from` the scan at `to` ran: "34 days later", "Less than an hour later". */
export function laterText(from: string | null, to: string | null): string {
  const start = parseServerTime(from);
  const end = parseServerTime(to);
  if (Number.isNaN(start) || Number.isNaN(end)) return "Time not recorded";
  const hours = Math.max(0, Math.floor((end - start) / 3_600_000));
  if (hours < 1) return "Less than an hour later";
  if (hours < 24) return `${count(hours, "hour")} later`;
  return `${count(Math.floor(hours / 24), "day")} later`;
}
