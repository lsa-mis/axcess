import { useState } from "react";
import { useParams } from "react-router";
import { BookOpenText } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import ReportHeader from "../components/ReportHeader";
import IssueEvidence, { IssueGuidanceDialog, issuePageLaneLabel } from "../components/IssueEvidence";
import { Button, Card, EmptyState, LinkButton } from "../components/ui";
import ConformanceBadge from "../components/ConformanceBadge";
import { useScanQuery } from "../hooks/useScanQuery";
import { REVIEW_LANE_HELP } from "../lib/labels";

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

  const { data: scan, error: scanError } = useScanQuery(id);
  const [guidanceOpen, setGuidanceOpen] = useState(false);
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
        title="Issue not found"
        message={
          "This issue is not part of this report. It may have been fixed, " +
          "or the link may be out of date. Go back to the Issues table to find it."
        }
        action={
          <LinkButton to={`/scans/${id}/issues`} variant="primary">
            Back to the Issues table
          </LinkButton>
        }
      />
    );
  }
  if (!scan) {
    return <div className="text-fg-muted">Loading issue…</div>;
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
        // The type rides with the criterion, so a "Needs review" issue reads
        // as one even with the guidance closed. The word is the Issues
        // table's (REVIEW_TYPE_LABEL), the same one the guidance dialog uses.
        meta={
          row ? (
            <>
              {row.wcag_sc && (
                <>
                  <abbr title="Web Content Accessibility Guidelines">WCAG</abbr> {row.wcag_sc}
                  {row.wcag_name ? ` ${row.wcag_name}` : ""}
                  {" · "}
                </>
              )}
              <span title={REVIEW_LANE_HELP[row.review_lane]}>{issuePageLaneLabel(row.review_lane)}</span>
            </>
          ) : undefined
        }
        // Top right, where Compare reports keeps its terms: one place on
        // every report page for "explain this". A book, not Compare's
        // question mark, so the two are not mistaken for each other.
        actions={
          detail && (
            <Button type="button" onClick={() => setGuidanceOpen(true)} className="rounded-full">
              <BookOpenText className="h-4 w-4" aria-hidden />
              Issue guidance
            </Button>
          )
        }
      />
      {detail && (
        <IssueGuidanceDialog open={guidanceOpen} onClose={() => setGuidanceOpen(false)} detail={detail} />
      )}
      {/* The trail names the issue, not the kind of page it is, so evidence
          opened from here returns under the issue's own title. */}
      <IssueEvidence
        scanId={scan.id}
        issueKey={key}
        origin={row?.title ?? key}
        backTo={`/scans/${scan.id}/issues/${encodeURIComponent(key)}`}
      />
    </>
  );
}
