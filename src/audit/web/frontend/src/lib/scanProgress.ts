import type { ScanProgress } from "../api/types";

/** Human-readable, deliberately approximate crawl completion range. */
export function formatScanEta(
  eta: ScanProgress["eta"] | null | undefined,
): string {
  if (!eta || eta.state === "estimating") {
    return "Estimate appears after two pages are checked";
  }
  if (eta.state === "finalizing") {
    return "Usually less than 30 seconds";
  }
  if (eta.min_seconds == null || eta.max_seconds == null) {
    return "Working out the time from how fast pages load";
  }
  return `${formatDuration(eta.min_seconds)} to ${formatDuration(eta.max_seconds)} for the pages found so far`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return unit(Math.max(1, Math.round(seconds)), "second");
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return unit(minutes, "minute");
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes
    ? `${unit(hours, "hour")} ${unit(remainingMinutes, "minute")}`
    : unit(hours, "hour");
}

function unit(count: number, name: string): string {
  return `${count} ${name}${count === 1 ? "" : "s"}`;
}

/**
 * How far a running scan has got: pages checked out of the pages it will
 * check, as a whole percent, with the words that say what the total is.
 *
 * The total is the pages found so far, or the page limit when that is
 * smaller: a 5-page scan that has found 76 pages checks 5 of them, so
 * "1 of 76" read as 1% while a fifth of the scan was done (2026-11-25). The
 * scan finds more links as it goes, so without a limit the total can grow
 * and the percent step back; the words then say "found so far".
 *
 * 100 is kept for when only the report is left to prepare: a page skipped
 * as out of scope also counts as done, so the count can reach the limit a
 * moment before the scan does.
 */
export interface CheckedShare {
  percent: number;
  checked: number;
  /** What the percent is out of: the pages found, or the page limit. */
  total: number;
  found: number;
  /** The page limit is the total: it is smaller than the pages found. */
  limited: boolean;
}

export function checkedShare(
  progress: ScanProgress | null | undefined,
  pageLimit: number | null | undefined,
): CheckedShare {
  const found = progress?.discovered ?? 0;
  const limited = pageLimit != null && pageLimit > 0 && pageLimit < found;
  const total = limited ? pageLimit : found;
  const checked = Math.min(progress?.completed ?? 0, total);
  let percent = 0;
  if (progress?.stage === "preparing_report") percent = 100;
  else if (total > 0) percent = Math.min(99, Math.floor((checked / total) * 100));
  return { percent, checked, total, found, limited };
}

/**
 * The counts a percent comes from, in words: "1 of 76 pages found so far",
 * or with a smaller page limit "1 of 5 pages (the page limit), 76 found so
 * far". One wording for the progress card, its announcement and the Reports
 * page's notice (SC 3.2.4 Consistent Identification, Level AA).
 */
export function checkedCountText(share: CheckedShare): string {
  const checked = share.checked.toLocaleString();
  if (share.limited) {
    return `${checked} of ${share.total.toLocaleString()} pages (the page limit), ${share.found.toLocaleString()} found so far`;
  }
  return `${checked} of ${share.found.toLocaleString()} pages found so far`;
}
