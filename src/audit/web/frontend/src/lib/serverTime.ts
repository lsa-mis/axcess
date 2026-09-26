/**
 * A time the server sent, in milliseconds since the epoch (NaN if unreadable).
 *
 * The database stores UTC with no zone: SQLite's CURRENT_TIMESTAMP writes
 * "2026-09-26 21:53:46". A browser reads that form as local time, which put
 * every time off by the reader's UTC offset: in US Eastern daylight time a
 * scan that had just finished was "in 4 hours", and anything under four
 * hours old read "just now". A value with no zone is UTC; a value that names
 * one ("Z", "+02:00") is read as written.
 */
export function parseServerTime(value: string | null | undefined): number {
  if (!value) return Number.NaN;
  const trimmed = value.trim();
  // A date alone ("2026-09-26") is already UTC to Date.parse.
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return Date.parse(trimmed);
  const iso = trimmed.replace(" ", "T");
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso);
  return Date.parse(hasZone ? iso : `${iso}Z`);
}

/** The same time as a Date, for toLocaleString and friends. */
export function serverDate(value: string | null | undefined): Date {
  return new Date(parseServerTime(value));
}
