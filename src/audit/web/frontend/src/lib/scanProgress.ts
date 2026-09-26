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
