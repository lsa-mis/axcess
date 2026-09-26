import { parseServerTime } from "../../lib/serverTime";

/** "1 issue", "7 issues". */
export function count(n: number, noun: string): string {
  return `${n.toLocaleString()} ${plural(n, noun)}`;
}

export function plural(n: number, noun: string): string {
  return n === 1 ? noun : `${noun}s`;
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
