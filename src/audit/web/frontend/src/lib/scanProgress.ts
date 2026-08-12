import type { ScanProgress } from "../api/types";

/** Human-readable, deliberately approximate crawl completion range. */
export function formatScanEta(
  eta: ScanProgress["eta"] | null | undefined,
): string {
  if (!eta || eta.state === "estimating") {
    return "Estimating after two pages complete";
  }
  if (eta.state === "finalizing") {
    return "Usually less than 30 seconds";
  }
  if (eta.min_seconds == null || eta.max_seconds == null) {
    return "Calculating from observed page speed";
  }
  return `${formatDuration(eta.min_seconds)}–${formatDuration(eta.max_seconds)} for currently discovered pages`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} sec`;
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes
    ? `${hours} hr ${remainingMinutes} min`
    : `${hours} hr`;
}
