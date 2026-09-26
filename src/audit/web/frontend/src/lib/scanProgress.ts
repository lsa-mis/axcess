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
 * How much of the scan is done, as a whole percent: the pages checked out of
 * the pages found so far, and 100 once only the report is left to prepare.
 * The scan finds more links as it goes, so the total can grow and the
 * percent step back; the words beside it always say "found so far".
 */
export function checkedPercent(progress: ScanProgress | null | undefined): number {
  if (!progress) return 0;
  if (progress.stage === "preparing_report") return 100;
  if (progress.discovered <= 0) return 0;
  return Math.min(100, Math.floor((progress.completed / progress.discovered) * 100));
}
