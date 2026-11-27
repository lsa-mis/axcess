/**
 * Calendar days as Axcess shows and compares them: "YYYY-MM-DD" keys and
 * the reader's own words for them. A day is the date as it was written
 * (the first ten characters of an ISO 8601 string), never moved into the
 * reader's time zone, so a file made late on 24 April in its maker's zone
 * shows, sorts and filters as 24 April everywhere.
 */

/** "2018-07-17" from "2018-07-17T09:30:00+00:00"; null when not a real day. */
export function dayKey(iso: string | null | undefined): string | null {
  const match = iso ? /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) : null;
  if (!match) return null;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return null;
  }
  return match[0].slice(0, 10);
}

/** The day in the reader's words ("July 17, 2018"); null when not a real day. */
export function formatDay(iso: string | null | undefined): string | null {
  const key = dayKey(iso);
  if (!key) return null;
  const [year, month, day] = key.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}
