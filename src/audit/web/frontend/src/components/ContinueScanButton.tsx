import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../api/client";
import { Button } from "./ui";

/**
 * "Continue scan": carries on a report that is not finished, in place of
 * "Scan again" (the developer's decision, 2026-11-20).
 *
 * - What it is for. A scan cut off when Axcess closed keeps the addresses
 *   it had still to visit (audit/web/continuing.py). Until 2026-11-20,
 *   "Scan again" quietly continued such a report instead of making a new
 *   one, so the reader asked for a new report and got an old one back. Now
 *   continuing is its own action with its own name, and "Scan again"
 *   always makes a new report. Where the latest report is not finished,
 *   this replaces "Scan again", so the row offers one way forward that
 *   says what it will do (W3C COGA, "Making Content Usable",
 *   https://www.w3.org/TR/coga-usable/: one way to do one thing, clear
 *   words). A new report of the site is still one step away on New scan.
 * - A button, not a link: it acts here, as Delete does, instead of opening
 *   a form. It continues the report with the settings it started with, so
 *   there is nothing to choose. Starting a crawl of a real site still must
 *   not follow from one stray click (the rule ScanAgainLink records), so
 *   it asks first, naming the report and the site, as Delete does.
 *   window.confirm is used directly rather than confirmDestructive: that
 *   one follows the preference for confirming deletions, which is not this.
 * - Quiet look, like the links beside it: no border, the link colour, and
 *   no underline, which in this table marks a link (a button that looked
 *   like a link would promise to go somewhere). Real text in the name: the
 *   visible words first, then screen-reader-only words naming the report
 *   and site (technique C7; SC 2.5.3 Label in Name, Level A). No
 *   `aria-label`.
 * - An error shows as text beside it, with role="alert", as Delete's does
 *   (SC 3.3.1 Error Identification, Level A).
 */
export default function ContinueScanButton({ scanId, site }: { scanId: number; site: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => api.continueScan(scanId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["scans"] });
      await queryClient.invalidateQueries({ queryKey: ["scan", scanId] });
      navigate(`/scans/${scanId}`);
    },
    onError: (err: unknown) => setError(err instanceof Error ? err.message : String(err)),
  });
  return (
    <>
      <Button
        variant="ghost"
        disabled={mutation.isPending}
        className="whitespace-nowrap px-1 text-umich-blue"
        onClick={() => {
          setError(null);
          const ok = window.confirm(
            `Continue report #${scanId} (${site})?\n\n` +
              "Axcess visits the pages this report had not reached yet, with the " +
              "settings it started with, and adds them to the same report.",
          );
          if (ok) mutation.mutate();
        }}
      >
        <Play className="h-4 w-4 shrink-0" aria-hidden />
        {mutation.isPending ? "Continuing…" : "Continue scan"}
        <span className="sr-only">: report #{scanId}, {site}</span>
      </Button>
      {error && (
        <span className="ml-2 text-xs text-sev-critical" role="alert">
          {error}
        </span>
      )}
    </>
  );
}
