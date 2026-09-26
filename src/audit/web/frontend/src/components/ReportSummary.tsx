import { Link, useNavigate } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Accessibility, AlertOctagon, ChevronDown, Trash2 } from "lucide-react";
import { api } from "../api/client";
import type { IssueRow, ScanDetail } from "../api/types";
import MethodCoverageLedger, { methodsRan } from "./MethodCoverageLedger";
import { Button, Card, LinkButton, StatCard } from "./ui";
import { STATUS_LABEL } from "../lib/terms";

/**
 * What the old Overview tab said about a completed report, above its table.
 *
 * The report opens on Issues now, so the numbers and the coverage disclosure
 * that used to take a page of their own sit over the table instead: one row
 * of stat cards, then one line saying how many checks ran. The full ledger is
 * behind that line, because what a scan did and did not check is something a
 * reader goes to on purpose, not something every visit should scroll past.
 *
 * ``rows`` is the unfiltered issue list (the per-method "Found" lines count
 * it); undefined while it loads, which the ledger already handles.
 */
export function ReportSummary({
  scan,
  issueGroups,
  occurrences,
  rows,
}: {
  scan: ScanDetail;
  issueGroups: number;
  occurrences: number;
  rows: IssueRow[] | undefined;
}) {
  const ran = methodsRan(scan.methods_used).length;
  return (
    <>
      {scan.blocked && <BlockedScanNotice scanId={scan.id} blocked={scan.blocked} />}
      {/* Read left to right as the scan itself ran: how much was tested,
          what that turned up, how those findings group, and how much of
          the site only existed after a control was used. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Pages checked"
          value={scan.page_count.toLocaleString()}
          hint={`${scan.error_count.toLocaleString()} error${scan.error_count === 1 ? "" : "s"} while scanning`}
          tone={scan.error_count ? "major" : "default"}
        />
        <StatCard
          label="Occurrences found"
          value={occurrences.toLocaleString()}
          hint="Each place an issue appears"
        />
        <StatCard
          label="Issues found"
          value={issueGroups.toLocaleString()}
          hint="Kinds of problem, one per row below"
        />
        {/* Pages alone understate an application whose content mostly does
            not exist until a control is used. */}
        <StatCard
          label="Page states found"
          value={(scan.dom_state_count ?? 0).toLocaleString()}
          hint="Reached by using controls, such as menus"
        />
      </div>

      {/* Same shape as the ACT-rule disclosure below it: the summary is the
          sentence, and the word styled as a link is where to press. The
          chevron points down while closed and up while open, following the
          element's own open state. */}
      <details className="group mb-3 mt-3 text-sm">
        <summary className="inline-flex min-h-target cursor-pointer list-none items-center gap-1.5 rounded-xs text-fg-muted">
          <span className="tabular-nums">
            {ran} of {scan.methods_used.length} checks ran
          </span>
          <span aria-hidden className="text-border-strong">·</span>
          <span className="inline-flex items-center gap-0.5 font-semibold text-umich-blue">
            <span className="underline underline-offset-2">See what was checked</span>
            <ChevronDown
              className="h-4 w-4 shrink-0 transition-transform duration-150 group-open:rotate-180"
              aria-hidden
            />
          </span>
        </summary>
        <MethodCoverageLedger scanId={scan.id} methods={scan.methods_used} rows={rows} className="mt-2" />
      </details>
    </>
  );
}

/**
 * The report's expert tools and lifecycle controls, kept closed under the
 * table: the DOM-engine and image-evidence views, the observed rejection
 * rate, and deleting the report.
 *
 * Delete removes the cache entry rather than invalidating it: there is no
 * record left to refetch, and an invalidation would send this screen to the
 * server for a report that is gone.
 */
export function ReportExpertTools({
  scan,
  rows,
}: {
  scan: ScanDetail;
  rows: IssueRow[] | undefined;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const deleteScan = useMutation({
    mutationFn: () => api.deleteScan(scan.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["scans"] });
      qc.removeQueries({ queryKey: ["scan", scan.id] });
      navigate("/scans", { replace: true });
    },
  });
  const reviewed = rows?.filter((issue) => issue.review_lane !== "informational");
  const reviewedBackingFindings =
    reviewed?.reduce(
      (total, issue) =>
        total +
        (issue.status_summary.in_progress ?? 0) +
        (issue.status_summary.remediated ?? 0) +
        (issue.status_summary.accepted_risk ?? 0) +
        (issue.status_summary.false_positive ?? 0),
      0,
    ) ?? 0;
  const rejectedBackingFindings =
    reviewed?.reduce((total, issue) => total + (issue.status_summary.false_positive ?? 0), 0) ?? 0;
  const observedRejectionRate = reviewedBackingFindings
    ? (rejectedBackingFindings / reviewedBackingFindings) * 100
    : null;

  return (
    <details className="mt-5 rounded-xs border border-border bg-surface p-4 shadow-card">
      <summary className="min-h-target cursor-pointer py-2 font-semibold text-fg">
        Expert tools and report details
      </summary>
      <div className="border-t border-border pt-4">
        <div className="flex flex-wrap gap-2">
          <LinkButton to={`/scans/${scan.id}/a11y`} variant="secondary">
            <Accessibility className="h-4 w-4" aria-hidden /> Rule check issues by WCAG criterion
          </LinkButton>
          <LinkButton to={`/scans/${scan.id}/findings`} variant="secondary">
            Images ({scan.finding_count})
          </LinkButton>
        </div>
        <p className="mt-4 text-sm text-fg-muted">
          Reviewed occurrences marked &ldquo;{STATUS_LABEL.false_positive}&rdquo;:{" "}
          <strong>
            {rows == null
              ? "loading…"
              : observedRejectionRate == null
                ? "none reviewed yet"
                : `${observedRejectionRate.toFixed(1)}%`}
          </strong>
          {observedRejectionRate != null &&
            ` (${rejectedBackingFindings} of ${reviewedBackingFindings})`}
          . This number is for this report only. It does not show how accurate
          the checks are in general.
        </p>
        <details className="mt-4 border-t border-border pt-3">
          <summary className="min-h-target cursor-pointer py-2 text-sm font-semibold text-sev-critical">
            Delete this report
          </summary>
          <p className="text-sm text-fg-muted">
            Deleting removes this report and everything the scan saved for it.
            Image files that other reports also use may stay in storage.
          </p>
          {deleteScan.error && (
            <p className="mt-2 text-sm text-sev-critical" role="alert">
              The report was not deleted. Try again. Details:{" "}
              {deleteScan.error instanceof Error
                ? deleteScan.error.message
                : String(deleteScan.error)}
            </p>
          )}
          <Button
            variant="ghost"
            disabled={deleteScan.isPending}
            className="mt-2 text-sev-critical hover:bg-sev-critical-bg"
            onClick={() => {
              const ok = window.confirm(
                `Delete report #${scan.id} (${scan.seed_url})?\n\nThis removes the report for good, with its pages, issues, images, and history. You cannot undo this.`,
              );
              if (ok) deleteScan.mutate();
            }}
          >
            <Trash2 className="h-4 w-4" aria-hidden />
            {deleteScan.isPending ? "Deleting…" : "Delete report"}
          </Button>
        </details>
      </div>
    </details>
  );
}

export function BlockedScanNotice({
  scanId,
  blocked,
}: {
  scanId: number;
  blocked: NonNullable<ScanDetail["blocked"]>;
}) {
  return (
    <Card className="mb-4 border-sev-critical/40 bg-sev-critical-bg p-4">
      <div className="flex items-start gap-3">
        <AlertOctagon
          className="mt-0.5 h-5 w-5 text-sev-critical"
          aria-hidden
        />
        <div className="text-sm">
          <strong className="text-sev-critical">
            The website returned an error (HTTP {blocked.status_code})
          </strong>
          {blocked.title && <>, &ldquo;{blocked.title}&rdquo;</>}. Axcess could
          not get past the start page, so report {scanId} is incomplete.{" "}
          <Link to="/scans/new">Start a new scan</Link>. If the site needs you
          to sign in, and you have permission, use a sign-in scan.
        </div>
      </div>
    </Card>
  );
}
