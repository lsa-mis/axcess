import type { ReactNode } from "react";
import ReportWorkspaceNav from "./ReportWorkspaceNav";

/**
 * The one header every page inside a report wears.
 *
 * Every page of a report gets the same chrome in the same order: the tabs
 * where there are tabs, then the title, a single meta line and the page's
 * actions. Before this each route invented its own arrangement, different
 * crumbs, different subtitle shapes, and the report stopped feeling like one
 * place.
 *
 * The breadcrumb is deliberately absent: it lives in the topbar
 * (see ``ReportCrumb``) where it stays put while this content scrolls, and
 * it is the only trail -- a page inside a report is one location, and two
 * trails for it disagreed about where it sat.
 *
 * Only the report's two views, Issues and Verify changes, pass ``tabs``.
 * An issue, its pages and the inspector sit *inside* the report rather than
 * beside those views, so a tab row there claimed a sibling relationship
 * they do not have; the breadcrumb carries the way back instead.
 */
export default function ReportHeader({
  scanId,
  previousScanId,
  title,
  meta,
  actions,
  tabs = false,
}: {
  scanId: number;
  previousScanId: number | null;
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  /** Show the report's view tabs. Only the report's own views (see above). */
  tabs?: boolean;
}) {
  return (
    <header className="mb-5">
      {/* Tabs first, title second. The tabs are the report's own navigation
          and belong at the top of its area, right under the topbar trail
          that ends at the report; the title then reads as the heading of
          the view you chose, not as something the tabs sit beneath. */}
      {tabs && (
        <ReportWorkspaceNav scanId={scanId} previousScanId={previousScanId} />
      )}
      <div className="mt-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold leading-tight tracking-[-0.025em] text-fg sm:text-[1.75rem]">
            {title}
          </h1>
          {meta && (
            <p className="mt-1 max-w-4xl text-sm leading-6 text-fg-muted">{meta}</p>
          )}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

/**
 * The shared shape of every report meta line: what identifies this page,
 * then the standing caveat. Keeping it in one component is what stops the
 * pages from drifting into different sentences.
 */
export function ReportMeta({
  counts,
  note = "Evidence for expert review, not a conformance verdict.",
}: {
  counts: ReactNode;
  note?: string;
}) {
  return (
    <>
      <span className="font-semibold tabular-nums text-fg">{counts}</span>
      {note && (<>
        <span aria-hidden className="px-1.5 text-border-strong">|</span>
        <span className="text-fg-subtle">{note}</span>
      </>)}
    </>
  );
}
