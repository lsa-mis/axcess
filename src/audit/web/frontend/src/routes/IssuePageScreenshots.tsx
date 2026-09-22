import { Link, useLocation, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, blobUrl } from "../api/client";
import ConformanceBadge from "../components/ConformanceBadge";
import ReportHeader from "../components/ReportHeader";
import { Card, EmptyState, LinkButton, pageEvidencePath } from "../components/ui";
import { issueInspectorPath } from "./IssuePages";

/** The trail label for this view; ReportCrumb shows the same words. */
export const ISSUE_SCREENSHOTS_VIEW = "Issue screenshots";

/**
 * The captured instance screenshots of one issue on one page
 * (``/scans/:id/issues/:key/pages/:pageId/screenshots``).
 *
 * The pages table links here from its screenshots column. This is a page
 * of its own in the current tab rather than a side panel: a panel needs
 * focus management and an escape route to be usable from the keyboard,
 * while a page is a plain navigation whose way back is the topbar trail,
 * which the link that opened it fed with ``?origin=&back=``.
 */
export default function IssuePageScreenshotsRoute() {
  const { scanId, issueKey, pageId } = useParams<{
    scanId: string;
    issueKey: string;
    pageId: string;
  }>();
  const id = Number(scanId);
  const key = decodeURIComponent(issueKey ?? "");
  const page = Number(pageId);
  const location = useLocation();

  const scanQuery = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
  });
  const detailQuery = useQuery({
    queryKey: ["issue-detail", id, key, "occurrences_desc"],
    queryFn: () => api.getIssueDetail(id, key, "occurrences_desc"),
    enabled: Number.isFinite(id) && !!key,
  });

  if (scanQuery.error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        Couldn&rsquo;t load this report. The stored scan evidence is unchanged.
      </Card>
    );
  }
  const pagesPath = `/scans/${id}/issues/${encodeURIComponent(key)}/pages`;
  const found = detailQuery.data?.pages.find((candidate) => candidate.page_id === page);
  if (detailQuery.error || (detailQuery.data && !found)) {
    return (
      <EmptyState
        title="Screenshots not found"
        message={
          "This page is not part of the evidence group in the current report. It may have been " +
          "resolved or the URL may be stale."
        }
        action={
          <LinkButton to={pagesPath} variant="primary">
            Back to pages with this issue
          </LinkButton>
        }
      />
    );
  }
  if (!scanQuery.data || !detailQuery.data || !found) {
    return <p className="text-sm text-fg-muted" role="status">Loading screenshots…</p>;
  }

  const scan = scanQuery.data;
  const { row } = detailQuery.data;
  const isInformational = row.review_lane === "informational";
  const label = found.page_title?.trim() || found.page_url;
  const missing = Math.max(0, found.occurrence_count - found.screenshot_hashes.length);
  const here = `${location.pathname}${location.search}`;

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
            <span className="font-semibold text-fg">{label}</span>
            {found.page_title?.trim() && (
              <>
                {" "}
                <span className="break-all">{found.page_url}</span>
              </>
            )}
            {" · "}
            {found.occurrence_count} occurrence{found.occurrence_count === 1 ? "" : "s"}
            {", "}
            {found.screenshot_hashes.length} with a screenshot
            {" · "}
            <a
              href={found.page_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-umich-blue underline underline-offset-2"
            >
              Open live page
              <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
              <span className="sr-only">, opens in a new tab</span>
            </a>
            {" · "}
            <Link
              to={pageEvidencePath({
                scanId: scan.id,
                pageId: found.page_id,
                origin: ISSUE_SCREENSHOTS_VIEW,
                backTo: here,
              })}
              className="text-umich-blue underline underline-offset-2"
            >
              Stored evidence
            </Link>
            {" · "}
            <Link
              to={issueInspectorPath({
                scanId: scan.id,
                pageId: found.page_id,
                issueKey: key,
                origin: ISSUE_SCREENSHOTS_VIEW,
                backTo: here,
              })}
              className="text-umich-blue underline underline-offset-2"
            >
              Inspect page
            </Link>
          </>
        }
      />

      <Card className="p-4">
        <h2 className="text-base font-semibold">Instance screenshots</h2>
        {found.screenshot_hashes.length === 0 ? (
          <p className="mt-2 text-sm text-fg-muted">
            No instance on this page had a locatable screenshot.
          </p>
        ) : (
          <ul className="mt-3 grid list-none gap-3 p-0 md:grid-cols-2 xl:grid-cols-3">
            {found.screenshot_hashes.map((hash, index) => (
              <li key={`${hash}-${index}`}>
                <figure className="rounded-xs border border-border bg-surface p-2">
                  <img
                    src={blobUrl(hash)}
                    alt={`Issue instance ${index + 1} on ${label}. A circular marker identifies the detected location.`}
                    className="max-h-80 w-full rounded-xs object-contain"
                    loading="lazy"
                  />
                  <figcaption className="mt-2 text-xs text-fg-muted">
                    Instance {index + 1} of {found.occurrence_count}. The circle marks the detected location.
                  </figcaption>
                </figure>
              </li>
            ))}
          </ul>
        )}
        {missing > 0 && (
          <p className="mt-3 text-xs text-fg-muted">
            {missing} additional instance{missing === 1 ? "" : "s"} had no locatable screenshot or exceeded the per-page safety limit.
          </p>
        )}
      </Card>
    </>
  );
}
