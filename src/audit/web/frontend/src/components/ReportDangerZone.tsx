import { useState } from "react";
import { useNavigate } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api } from "../api/client";
import { confirmDestructive } from "../hooks/usePreferences";
import type { ScanDetail } from "../api/types";
import { siteLabel } from "./ReportCrumb";
import { Button } from "./ui";
import { ReportNote } from "./ReportSummary";

/**
 * Delete this report, at the very end of it: the one action on the page
 * that cannot be undone, so it comes after everything a reviewer reads, and
 * asks before it acts (the "Ask before deleting" preference in Settings
 * governs the prompt, as it does on Reports).
 *
 * A closed row of the report's notes (``ReportNote``), the last one, since
 * 2026-11-27 (the developer's request). It was a red-bordered card of its
 * own under them. As a row it takes one more press to reach the button,
 * which suits a rare action that cannot be undone, and the page ends in one
 * list rather than a list and a card. Reports offers the same delete, so
 * nothing depends on this one being in view. It is the same disclosure
 * pattern as the rows above it (https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/),
 * so keyboard and screen-reader use do not change. The trade, told to the
 * developer: an action among explanations. The title starts with the verb,
 * "Delete", and a trash icon marks it, so the row reads as an action by its
 * words and its shape, not by colour alone (SC 1.4.1 Use of Color, Level
 * A). The panel keeps the name "Delete this report" (its region is named by
 * the row's button).
 *
 * A running scan cannot be deleted: the crawl would keep writing rows after
 * the delete. The button says so rather than failing.
 */
export default function ReportDangerZone({ scan }: { scan: ScanDetail }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const running = scan.status === "running";

  const mutation = useMutation({
    mutationFn: () => api.deleteScan(scan.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["scans"] });
      // The report is gone; Reports is where the reader goes next.
      navigate("/scans", { replace: true });
    },
    onError: (err: unknown) => setError(err instanceof Error ? err.message : String(err)),
  });

  return (
    <ReportNote
      id="report-delete"
      title="Delete this report"
      icon={<Trash2 className="h-4 w-4 shrink-0 text-sev-critical" aria-hidden />}
    >
      <p className="max-w-measure text-sm text-fg-muted">
        Deleting removes this report and everything the scan saved for it. Image files that other
        reports also use may stay in storage.
      </p>
      {running && (
        <p className="mt-1 text-sm text-fg-muted">Stop the scan before you delete this report.</p>
      )}
      <Button
        type="button"
        variant="ghost"
        disabled={running || mutation.isPending}
        className="mt-3 border border-sev-critical/40 text-sev-critical hover:bg-sev-critical-bg"
        onClick={() => {
          setError(null);
          const ok = confirmDestructive(
            `Delete report #${scan.id} (${siteLabel(scan.seed_url)})?\n\n` +
              "This removes the report for good, with its pages, issues, and history. " +
              "Image files that other reports also use may stay in storage. You cannot undo this.",
          );
          if (ok) mutation.mutate();
        }}
      >
        <Trash2 className="h-4 w-4" aria-hidden />
        {mutation.isPending ? "Deleting…" : "Delete report"}
      </Button>
      {error && (
        <p className="mt-2 text-sm text-sev-critical" role="alert">
          The report was not deleted. Try again. Details: {error}
        </p>
      )}
    </ReportNote>
  );
}
