import { useState } from "react";
import { useNavigate } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api } from "../api/client";
import { confirmDestructive } from "../hooks/usePreferences";
import type { ScanDetail } from "../api/types";
import { siteLabel } from "./ReportCrumb";
import { Button, Card } from "./ui";

/**
 * Delete this report, at the very end of it: the one action on the page
 * that cannot be undone, so it sits apart, after everything a reviewer
 * reads, and asks before it acts (the "Ask before deleting" preference in
 * Settings governs the prompt, as it does on Reports).
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
    <Card className="mt-8 border-sev-critical/40 p-4" role="region" aria-labelledby="delete-report-heading">
      <h2 id="delete-report-heading" className="text-base font-semibold text-sev-critical">
        Delete this report
      </h2>
      <p className="mt-1 max-w-[70ch] text-sm text-fg-muted">
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
    </Card>
  );
}
