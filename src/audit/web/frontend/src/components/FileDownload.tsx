import { useState } from "react";
import { Download } from "lucide-react";
import type { DownloadedFile } from "../api/client";
import { cn } from "../lib/cn";
import { Button } from "./ui";

/**
 * One view's download button, with what it is doing in words: the
 * preparing message while the server builds the file, then the file name
 * and size, or what went wrong. The words are in a polite live region
 * beside the button (SC 4.1.3 Status Messages, Level AA). The button stays
 * enabled and focusable while it works (aria-disabled), so focus is not lost
 * (SC 2.4.3 Focus Order, Level A).
 *
 * Fetched and saved (api/client.ts, downloadFile), not a plain link: a
 * plain link did nothing in some windows (2026-11-13), and a refused or
 * failed download would have been saved as the file with no word on the
 * page.
 *
 * It goes in ReportHeader's action slot, top right, where Issues keeps
 * Export report, so a report's downloads are in one place on every view
 * (SC 3.2.3 Consistent Navigation, Level AA). One component for every
 * per-view download, so they look, behave and are worded the same (SC 3.2.4
 * Consistent Identification, Level AA). It began as the Images tab's ZIP
 * button and was moved here when Pages visited needed the same control,
 * rather than copied. ExportMenu was considered and not extended: its panel
 * is the whole report's files, and a file of one view's list in it would
 * break the panel's promise that its files cover the whole report.
 *
 * The size reads in KB under 0.1 MB, so a small file does not read
 * "0.0 MB", which looks like an empty file.
 */
export default function FileDownload({
  label,
  busyLabel,
  preparing,
  failure,
  download,
}: {
  /** The button's words: a verb and the file, with its type ("Download pages list (CSV)"). */
  label: string;
  /** The button's words while it works ("Preparing pages list (CSV)…"). */
  busyLabel: string;
  /** Said in the live region while it works. */
  preparing: string;
  /** The first sentence when it fails ("The CSV file could not be downloaded."). */
  failure: string;
  download: () => Promise<DownloadedFile>;
}) {
  const [state, setState] = useState<{ busy: boolean; message: string; error: boolean }>({
    busy: false,
    message: "",
    error: false,
  });
  const start = async () => {
    if (state.busy) return;
    setState({ busy: true, message: preparing, error: false });
    try {
      const { filename, sizeBytes } = await download();
      setState({ busy: false, message: `Saved ${filename} (${fileSize(sizeBytes)}) to your downloads.`, error: false });
    } catch (error) {
      const text = error instanceof Error ? error.message : "Try again later.";
      setState({ busy: false, message: `${failure} ${text}`, error: true });
    }
  };
  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={() => void start()} aria-disabled={state.busy || undefined}>
        <Download className="h-4 w-4" aria-hidden />
        {state.busy ? busyLabel : label}
      </Button>
      <p
        role="status"
        aria-live="polite"
        className={cn("max-w-xs text-right text-xs", state.error ? "text-sev-critical" : "text-fg-muted")}
      >
        {state.message}
      </p>
    </div>
  );
}

function fileSize(bytes: number): string {
  if (bytes < 100_000) return `${Math.max(1, Math.round(bytes / 1000))} KB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}
