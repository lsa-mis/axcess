import { useState } from "react";
import { useLocation, useParams } from "react-router";
import { BookOpenText } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import ReportHeader from "../components/ReportHeader";
import IssueEvidence, { IssueGuidanceDialog, issuePageLaneLabel } from "../components/IssueEvidence";
import { Button, Card, EmptyState, LinkButton } from "../components/ui";
import ConformanceBadge from "../components/ConformanceBadge";
import { useScanQuery } from "../hooks/useScanQuery";
import { REVIEW_LANE_HELP, alsoWcagText } from "../lib/labels";

/**
 * Per-issue evidence at a stable URL (``/scans/:id/issues/:key``).
 *
 * This is a thin shell: the evidence content lives in ``<IssueEvidence>``.
 * The route exists for deep links, bookmarks, and the breadcrumb trail.
 */
export default function IssueDetailRoute() {
  const { scanId, issueKey } = useParams<{ scanId: string; issueKey: string }>();
  const id = Number(scanId);
  const key = decodeURIComponent(issueKey ?? "");
  // This page's own address with its query: the query carries the trail it
  // was opened with (the filtered Issues list), so evidence opened from here
  // returns through it, as from an issue type's pages (IssuePages `here`).
  const location = useLocation();
  const here = `${location.pathname}${location.search}`;

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
        title="Issue type not found"
        message={
          "This issue type is not part of this report. It may have been fixed, " +
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
    return <div className="text-fg-muted">Loading this issue type…</div>;
  }

  const row = detail?.row;
  const isInformational = row?.review_lane === "informational";

  return (
    <>
      <ReportHeader
        scanId={scan.id}
        canCompare={scan.has_other_reports}
        // The heading is the issue type's name alone. Its level (A, AA, AAA,
        // Best practice) moved to the start of the WCAG line under it
        // (the developer's layout, 2026-11-27): the level belongs to the
        // criterion, so the badge sits beside the criterion it grades, and
        // a screen reader's list of headings hears the name without "Level
        // A" in front of it. At the start of the line, not the end, so it
        // reads "Level A, WCAG 4.1.2 Name, Role, Value", the order the
        // Issues table's Level filter and badge column use.
        title={row?.title ?? key}
        // Three lines under the heading, left-aligned with it (the
        // developer's layout, 2026-11-27): the level and criterion, then
        // How sure on its own line, then "Issue guidance".
        //
        // How sure has its own line so it is not read as part of the
        // criterion's name. The word is the Issues table's
        // (REVIEW_TYPE_LABEL), the same one the guidance dialog uses.
        meta={
          row ? (
            <>
              {(!isInformational || row.wcag_sc) && (
                <span className="flex flex-wrap items-center gap-x-2">
                  {!isInformational && <ConformanceBadge level={row.conformance} />}
                  {row.wcag_sc && (
                    <span>
                      <abbr title="Web Content Accessibility Guidelines">WCAG</abbr> {row.wcag_sc}
                      {row.wcag_name ? ` ${row.wcag_name}` : ""}
                      {row.also_wcag.length > 0 ? `, ${alsoWcagText(row.also_wcag, true)}` : ""}
                    </span>
                  )}
                </span>
              )}
              <span className="block" title={REVIEW_LANE_HELP[row.review_lane]}>
                {issuePageLaneLabel(row.review_lane)}
              </span>
            </>
          ) : undefined
        }
        // "Issue guidance" under the facts, on the left, not at the top
        // right where it was until 2026-11-27. The developer moved it
        // because buttons at the far right get lost. Readers of a page in a
        // left-to-right language look most at its left side and least at
        // its right (NN/g, "F-Shaped Pattern of Reading on the Web",
        // https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content/,
        // paraphrased), and a control is found where it sits near what it
        // acts on (NN/g, "Proximity Principle in Visual Design",
        // https://www.nngroup.com/articles/gestalt-proximity/, paraphrased).
        // Here it is next to the issue type it explains, and next in
        // keyboard order after the heading (SC 2.4.3 Focus Order, Level A).
        // A book, not Compare's question mark, so the two are not mistaken
        // for each other.
        below={
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
      {/* The trail names the issue type, not the kind of page it is, so
          evidence opened from here returns under its own title. It returns
          to this page as it was opened (`here`), so the report crumb still
          leads to the Issues list the reader filtered. That was lost on this
          path until 2026-11-02, when the Issues table's page count, the
          other way to an issue type's pages, stopped being a link. */}
      <IssueEvidence scanId={scan.id} issueKey={key} origin={row?.title ?? key} backTo={here} />
    </>
  );
}
