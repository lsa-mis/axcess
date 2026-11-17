import { useLocation } from "react-router";
import Tabs from "./Tabs";
import { FRAMED } from "../lib/framed";

/**
 * Report navigation: the issue table; the Images tab (every image and its
 * alt text); Documents, the files the report's pages link to; and Compare
 * reports, which shows this report and another of the site side by side.
 * (What changed between two reports, the older comparison page, opens from
 * Compare reports and keeps that tab lit: it is part of that view.)
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
 * active tab is read from the path alone. In a panel of Compare reports the
 * row is the same, without Compare reports (below).
 *
 * The views are data (``REPORT_VIEWS``), not markup: a further view of the
 * report's findings, such as findings by page or by component, is one entry
 * there, and its tab, its active state and its order come with it.
 */
export interface ReportView {
  key: string;
  label: string;
  /** Where the tab goes. */
  path: (scanId: number) => string;
  /** The path segment under ``/scans/:id/`` that makes this tab current. */
  segment: string;
  /** Whether the report has this view, given whether another report of its
   *  site exists. Omitted, it always does. */
  available?: (canCompare: boolean) => boolean;
}

/**
 * In tab order. The first is the report's landing view.
 *
 * Compare reports opens with this report alone and its second panel empty,
 * listing the site's other reports to choose from (routes/CompareReports.tsx,
 * EmptyPane). It used to open with the report before this one; the developer
 * asked for the reader to choose instead (2026-10-29).
 */
/** Views a Compare reports panel does not offer (see ReportWorkspaceNav). */
const PANEL_LEAVES_OUT: ReadonlySet<string> = new Set(["compare"]);

export const REPORT_VIEWS: readonly ReportView[] = [
  {
    key: "issues",
    label: "Issues",
    segment: "issues",
    path: (scanId) => `/scans/${scanId}/issues`,
  },
  // Images (2026-11-13): every image with a verdict on its alt text. After
  // Issues, so the report still opens on its issues, and before Compare
  // reports, which looks across two reports rather than into this one.
  {
    key: "images",
    label: "Images",
    segment: "images",
    path: (scanId) => `/scans/${scanId}/images`,
  },
  // The files the report's pages link to (PDF, Word, Excel, Google), with
  // what the PDF checks found (routes/Documents.tsx). After Images and
  // before Compare reports (the developer's decision, 2026-11-16): like
  // Images it looks into this report, and Compare reports looks across two,
  // so the views of this report come first. It also keeps the tab in the
  // same place on every report: Compare reports appears only when the site
  // has another report, and Documents after it was the 3rd tab on a site's
  // only report and the 4th otherwise (SC 3.2.3 Consistent
  // Navigation, Level AA). A reader still looks at the page issues first. Always shown, even for a report
  // that did not look for documents: the tab then says why there is no
  // list, which a missing tab could not.
  {
    key: "documents",
    label: "Documents",
    segment: "documents",
    path: (scanId) => `/scans/${scanId}/documents`,
  },
  {
    key: "compare",
    label: "Compare reports",
    segment: "compare",
    // Shown on every report of a site that has two or more, earlier or
    // later: the page pairs this report with any other one of its site, so
    // the oldest report can be compared too. Hidden only on a site's one
    // report, where the page would offer nothing to choose. Until
    // 2026-11-17 it needed an *earlier* report, so a site's first report
    // had no tab while its later ones did: the same pair could be opened
    // from one side only, and the tab came and went between two reports of
    // one site (SC 3.2.3 Consistent Navigation, Level AA).
    available: (canCompare) => canCompare,
    path: (scanId) => `/scans/${scanId}/compare`,
  },
];

/** The view a report path belongs to; the landing view when none matches. */
export function activeReportView(pathname: string): ReportView {
  const segment = /\/scans\/\d+\/([^/?#]+)/.exec(pathname)?.[1];
  return REPORT_VIEWS.find((view) => view.segment === segment) ?? REPORT_VIEWS[0];
}

export default function ReportWorkspaceNav({
  scanId,
  canCompare,
}: {
  scanId: number;
  /** Another report of the same site exists, earlier or later. */
  canCompare: boolean;
}) {
  const { pathname } = useLocation();
  const active = activeReportView(pathname);
  // The current view stays, so a saved link to it still has its tab. As a
  // panel of Compare reports (lib/framed.ts) a panel offers every view of
  // its report but Compare reports, Issues, Images and Documents, and
  // switches between them like the whole window does (the developer's
  // decision, 2026-11-16), so the two panels can show one report's issues
  // beside the other's, or both reports' images or documents. Compare
  // reports stays out of a panel: it would open the comparison inside one of
  // its own panels. From 2026-11-13 to 2026-11-16 a panel kept only its
  // current view, so it had no tab row.
  const views = REPORT_VIEWS.filter(
    (view) =>
      view === active ||
      (!(FRAMED && PANEL_LEAVES_OUT.has(view.key)) && (view.available?.(canCompare) ?? true)),
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
        to: view.path(scanId),
      }))}
    />
  );
}
