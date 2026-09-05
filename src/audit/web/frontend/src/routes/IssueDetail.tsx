import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import ReportHeader from "../components/ReportHeader";
import IssueEvidence from "../components/IssueEvidence";
import { Card, EmptyState, LinkButton } from "../components/ui";
import ConformanceBadge from "../components/ConformanceBadge";

/**
 * Per-issue evidence at a stable URL (``/scans/:id/issues/:key``).
 *
 * This is now a thin shell: the full evidence content lives in
 * ``<IssueEvidence>``, which is also expanded inline on the Issues list, so
 * the detail route and the inline expansion can never drift apart. The route
 * exists for deep links, bookmarks, and the breadcrumb trail.
 */
export default function IssueDetailRoute() {
  const { scanId, issueKey } = useParams<{ scanId: string; issueKey: string }>();
  const id = Number(scanId);
  const key = decodeURIComponent(issueKey ?? "");

  const { data: scan, error: scanError } = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
  });
  // Fetched once for the header title/meta; the same query key is reused by
  // <IssueEvidence>, so React Query serves both from one request.
  const { data: detail, error: detailError } = useQuery({
    queryKey: ["issue-detail", id, key, "occurrences_desc"],
    queryFn: () => api.getIssueDetail(id, key, "occurrences_desc"),
    enabled: Number.isFinite(id) && !!key,
  });

  if (scanError) {
    return (
      <Card className="p-4 text-sm text-sev-critical">
        {scanError instanceof Error ? scanError.message : String(scanError)}
      </Card>
    );
  }
  if (detailError) {
    return (
      <EmptyState
        title="Evidence group not found"
        message={
          "This evidence group isn't part of the current report. It may have been " +
          "resolved or the URL may be stale. Return to the issue table."
        }
        action={
          <LinkButton to={`/scans/${id}/issues`} variant="primary">
            Back to issue table
          </LinkButton>
        }
      />
    );
  }
  if (!scan) {
    return <div className="text-fg-muted">Loading…</div>;
  }

  const row = detail?.row;
  const isInformational = row?.review_lane === "informational";

  return (
    <>
      <ReportHeader
        scanId={scan.id}
        previousScanId={scan.previous_scan_id}
        title={
          <span className="flex flex-wrap items-center gap-2">
            {row && !isInformational && <ConformanceBadge level={row.conformance} />}
            <span>{row?.title ?? key}</span>
          </span>
        }
        meta={
          row?.wcag_sc
            ? `WCAG SC ${row.wcag_sc}${row.wcag_name ? `: ${row.wcag_name}` : ""}`
            : undefined
        }
      />
      <IssueEvidence scanId={scan.id} issueKey={key} />
    </>
  );
}
