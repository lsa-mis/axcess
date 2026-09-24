import { Link, useNavigate } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Accessibility, AlertOctagon, ChevronDown, Trash2 } from "lucide-react";
import { api } from "../api/client";
import type { IssueRow, ScanDetail } from "../api/types";
import MethodCoverageLedger, { methodsRan } from "./MethodCoverageLedger";
import { Button, Card, LinkButton, StatCard } from "./ui";

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
          label="Pages Tested"
          value={scan.page_count.toLocaleString()}
          hint={`${scan.error_count.toLocaleString()} crawl errors`}
          tone={scan.error_count ? "major" : "default"}
        />
        <StatCard label="Issues Found" value={occurrences.toLocaleString()} />
        <StatCard label="Issue Groups" value={issueGroups.toLocaleString()} />
        {/* Pages alone understate an application whose content mostly does
            not exist until a control is used. */}
        <StatCard
          label="DOM States Found"
          value={(scan.dom_state_count ?? 0).toLocaleString()}
          hint="Reached by operating controls"
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
            <span className="underline underline-offset-2">Details</span>
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
        Expert tools and scan details
      </summary>
      <div className="border-t border-border pt-4">
        <div className="flex flex-wrap gap-2">
          <LinkButton to={`/scans/${scan.id}/a11y`} variant="secondary">
            <Accessibility className="h-4 w-4" aria-hidden /> DOM engines
          </LinkButton>
          <LinkButton to={`/scans/${scan.id}/findings`} variant="secondary">
            Image evidence ({scan.finding_count})
          </LinkButton>
        </div>
        <p className="mt-4 text-sm text-fg-muted">
          Observed reviewer rejection rate:{" "}
          <strong>
            {rows == null
              ? "loading…"
              : observedRejectionRate == null
                ? "not measured yet"
                : `${observedRejectionRate.toFixed(1)}%`}
          </strong>
          {observedRejectionRate != null &&
            ` (${rejectedBackingFindings} of ${reviewedBackingFindings} reviewed findings marked false positive)`}
          . This is a result from this report, not a general
          detector-accuracy claim.
        </p>
        <details className="mt-4 border-t border-border pt-3">
          <summary className="min-h-target cursor-pointer py-2 text-sm font-semibold text-sev-critical">
            Danger zone
          </summary>
          <p className="text-sm text-fg-muted">
            Deleting removes this scan and its report evidence. Shared
            image blobs may remain.
          </p>
          {deleteScan.error && (
            <p className="mt-2 text-sm text-sev-critical" role="alert">
              Couldn&rsquo;t delete scan:{" "}
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
                `Delete scan #${scan.id} (${scan.seed_url})?\n\nThis permanently removes the scan, its pages, findings, and history. This cannot be undone.`,
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
            Site URL returned HTTP {blocked.status_code}
          </strong>
          {blocked.title && <>, &ldquo;{blocked.title}&rdquo;</>}. The crawler
          could not read past the entry page. Try a{" "}
          <Link to="/scans/new">new scan</Link>, or use an authorized
          sign-in scan when the site requires authentication.
          <span className="sr-only"> Report {scanId} is incomplete.</span>
        </div>
      </div>
    </Card>
  );
}
