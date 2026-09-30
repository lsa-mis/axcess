import { useLocation } from "react-router";
import Tabs from "./Tabs";

/**
 * Report navigation: the issue table, and the comparison with earlier scans.
 *
 * These are two *views of the same report*, not two steps of a task. An
 * early numbered-pill treatment read as a wizard ("1 Overview → 2 Issues →
 * 3 Verify changes", as Compare reports was then called) and implied an order
 * and a completion state the report does not have. The segmented row below carries no sequence, and it is the
 * same `Tabs` component the inspector and the tracker use, so the same
 * control reads the same way everywhere in the app.
 *
 * There was an Overview tab first. The report opens on Issues now, with the
 * overview's numbers above the table, and ``/scans/:id`` redirects there.
 *
 * Only the views themselves render this (see ``ReportHeader``), so the
 * active tab is read from the path alone.
 *
 * The views are data (``REPORT_VIEWS``), not markup: a further view of the
 * report's findings, such as findings by page or by component, is one entry
 * there, and its tab, its active state and its order come with it.
 */
export interface ReportView {
  key: string;
  label: string;
  /** Where the tab goes. ``previousScanId`` is the comparison target, if any. */
  path: (scanId: number, previousScanId: number | null) => string;
  /** The path segment under ``/scans/:id/`` that makes this tab current. */
  segment: string;
  /** Whether the report has this view. Omitted, it always does. */
  available?: (previousScanId: number | null) => boolean;
}

/** In tab order. The first is the report's landing view. */
export const REPORT_VIEWS: readonly ReportView[] = [
  {
    key: "issues",
    label: "Issues",
    segment: "issues",
    path: (scanId) => `/scans/${scanId}/issues`,
  },
  {
    key: "compare",
    label: "Compare reports",
    segment: "compare",
    // A site's first report has nothing earlier to compare with.
    available: (previousScanId) => previousScanId != null,
    path: (scanId, previousScanId) =>
      `/scans/${scanId}/compare${previousScanId != null ? `?compare_to=${previousScanId}` : ""}`,
  },
];

/** The view a report path belongs to; the landing view when none matches. */
export function activeReportView(pathname: string): ReportView {
  const segment = /\/scans\/\d+\/([^/?#]+)/.exec(pathname)?.[1];
  return REPORT_VIEWS.find((view) => view.segment === segment) ?? REPORT_VIEWS[0];
}

export default function ReportWorkspaceNav({
  scanId,
  previousScanId,
}: {
  scanId: number;
  previousScanId: number | null;
}) {
  const { pathname } = useLocation();
  const active = activeReportView(pathname);
  // The current view stays, so a saved link to it still has its tab.
  const views = REPORT_VIEWS.filter(
    (view) => view === active || (view.available?.(previousScanId) ?? true),
  );
  // One view is not a choice; the heading already names it.
  if (views.length < 2) return null;
  return (
    <Tabs
      mode="nav"
      attached
      label="Report views"
      className="mt-0"
      value={active.key}
      items={views.map((view) => ({
        key: view.key,
        label: view.label,
        to: view.path(scanId, previousScanId),
      }))}
    />
  );
}
