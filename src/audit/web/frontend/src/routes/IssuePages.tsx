import { Link, useLocation, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import ConformanceBadge from "../components/ConformanceBadge";
import IssuePagesTable from "../components/IssuePagesTable";
import ReportHeader from "../components/ReportHeader";
import { Card, EmptyState, LinkButton } from "../components/ui";
import { useScanQuery } from "../hooks/useScanQuery";

export { ISSUE_PAGES_VIEW, issueInspectorPath } from "../components/IssuePagesTable";

/**
 * Every page an issue group appears on, one page per row
 * (``/scans/:id/issues/:key/pages``).
 *
 * The Issues table links here from its page count. Each fact about a page
 * has a column of its own: title, URL, the live page, its stored evidence,
 * how many times the issue occurs on it, and the captured instance
 * screenshots. The screenshots open on a page of their own rather than in a
 * side panel, in the current tab, with the trail carrying the way back; the
 * desktop app has no browser back button, so the topbar trail is the only
 * return path and every drill-down here feeds it.
 */
export default function IssuePagesRoute() {
  const { scanId, issueKey } = useParams<{ scanId: string; issueKey: string }>();
  const id = Number(scanId);
  const key = decodeURIComponent(issueKey ?? "");
  const location = useLocation();

  const scanQuery = useScanQuery(id);
  const detailQuery = useQuery({
    queryKey: ["issue-detail", id, key],
    queryFn: () => api.getIssueDetail(id, key),
    enabled: Number.isFinite(id) && !!key,
  });

  if (scanQuery.error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        Couldn&rsquo;t load this report. The stored scan evidence is unchanged.
      </Card>
    );
  }
  if (detailQuery.error) {
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
  if (!scanQuery.data || !detailQuery.data) {
    return <p className="text-sm text-fg-muted" role="status">Loading pages…</p>;
  }

  const scan = scanQuery.data;
  const { row, pages } = detailQuery.data;
  const isInformational = row.review_lane === "informational";
  const occurrences = pages.reduce((total, page) => total + page.occurrence_count, 0);
  // Links out of this table return here, trail included.
  const here = `${location.pathname}${location.search}`;
  const issuePath = `/scans/${scan.id}/issues/${encodeURIComponent(key)}`;

  return (
    <>
      <ReportHeader
        scanId={scan.id}
        previousScanId={scan.previous_scan_id}
        title={
          <span className="flex flex-wrap items-center gap-2">
            {!isInformational && <ConformanceBadge level={row.conformance} />}
            <span>{row.title}</span>
          </span>
        }
        meta={
          <>
            {row.wcag_sc && (
              <>
                WCAG SC {row.wcag_sc}
                {row.wcag_name ? `: ${row.wcag_name}` : ""}
                {" · "}
              </>
            )}
            {pages.length} page{pages.length === 1 ? "" : "s"}
            {" · "}
            {occurrences} occurrence{occurrences === 1 ? "" : "s"}
            {" · "}
            <Link to={issuePath} className="text-umich-blue underline underline-offset-2">
              Full evidence record
            </Link>
          </>
        }
      />

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-border bg-surface-muted px-4 py-3">
          <h2 className="text-base font-semibold">
            Pages with this issue
            <span className="ml-2 text-sm font-normal text-fg-muted">
              {pages.length} page{pages.length !== 1 ? "s" : ""}
            </span>
          </h2>
        </div>
        <IssuePagesTable scanId={scan.id} issueKey={key} row={row} pages={pages} backTo={here} />
      </Card>
    </>
  );
}
