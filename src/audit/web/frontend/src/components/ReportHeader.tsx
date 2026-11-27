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
 * Only the report's four views, Issues, Images, Documents and Compare
 * reports, pass ``tabs``, and What changed, which is part of Compare
 * reports and keeps its tab lit.
 * An issue, its pages and the inspector sit *inside* the report rather than
 * beside those views, so a tab row there claimed a sibling relationship
 * they do not have; the breadcrumb carries the way back instead.
 */
export default function ReportHeader({
  scanId,
  canCompare,
  title,
  kicker,
  help,
  meta,
  below,
  actions,
  tabs = false,
}: {
  scanId: number;
  /** Another report of the same site exists, earlier or later, so the tabs
   *  include Compare reports (ScanDetail.has_other_reports). */
  canCompare: boolean;
  title: ReactNode;
  /**
   * A line above the heading that says what the page sits inside, such as
   * the issue type an inspected page is opened for ("Issue type: Some
   * content sits outside any page region"). Above, not in the heading, so
   * a screen reader's list of headings hears the page's own name.
   */
  kicker?: ReactNode;
  /**
   * A ``HelpTip`` ("?") that explains the view, right after the heading
   * (Images). After it, not inside it: inside, its words would join the
   * heading's name in a screen reader's list of headings.
   */
  help?: ReactNode;
  meta?: ReactNode;
  /**
   * Lines under the meta line, in the title's column: more facts about the
   * page, or an action that belongs to the title. Each child is its own
   * line. The issue type page puts "Issue guidance" here, on the left
   * under the facts, rather than in ``actions`` at the far right.
   */
  below?: ReactNode;
  actions?: ReactNode;
  /** Show the report's view tabs. Only the report's own views (see above). */
  tabs?: boolean;
}) {
  const heading = (
    <h1 className="text-2xl font-semibold leading-tight tracking-[-0.025em] text-fg sm:text-[1.75rem]">
      {title}
    </h1>
  );
  return (
    <header className="mb-5">
      {/* Tabs first, title second. The tabs are the report's own navigation
          and belong at the top of its area, right under the topbar trail
          that ends at the report; the title then reads as the heading of
          the view you chose, not as something the tabs sit beneath. */}
      {tabs && (
        <ReportWorkspaceNav scanId={scanId} canCompare={canCompare} />
      )}
      <div className="mt-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {kicker && <p className="mb-1 text-sm leading-6 text-fg-muted">{kicker}</p>}
          {help ? (
            <div className="flex items-center gap-1">
              {heading}
              {help}
            </div>
          ) : (
            heading
          )}
          {meta && (
            <p className="mt-1 max-w-4xl text-sm leading-6 text-fg-muted">{meta}</p>
          )}
          {below && <div className="mt-2 flex flex-col items-start gap-3">{below}</div>}
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
  note = "Results for an expert to review. They do not prove that the site meets accessibility standards.",
}: {
  counts: ReactNode;
  note?: string;
}) {
  return (
    <>
      <span className="font-semibold tabular-nums text-fg">{counts}</span>
      {note && (<>
        {/* A drawn line, not a "|" character: as text in the light border
            colour it was 1.68:1, which contrast checkers report even though
            it is decoration (Alfa sia-r66; October 2026 AAA audit). A shape
            is plainly decoration, so no contrast rule applies to it. */}
        <span aria-hidden className="mx-2 inline-block h-[1em] w-px bg-border-strong align-[-0.15em]" />
        <span className="text-fg-subtle">{note}</span>
      </>)}
    </>
  );
}
