import type { ReactNode } from "react";
import { useLocation } from "react-router";
import { activeView } from "./ReportCrumb";
import ReportWorkspaceNav from "./ReportWorkspaceNav";

/**
 * The one header every view of a report wears.
 *
 * Overview, Issues and Verify changes are three views of the same evidence,
 * so they get the same chrome in the same order: the tabs (and, inside a
 * drill-down, the trail under them), then the title, a single meta line and
 * the view's actions. Before this each route invented its own
 * arrangement, different crumbs, different subtitle shapes, tabs on some
 * pages and not others, and the report stopped feeling like one place.
 *
 * The breadcrumb is deliberately absent: it lives in the topbar
 * (see ``ReportCrumb``) where it stays put while this content scrolls.
 *
 * Drill-downs below those three views pass ``tabs={false}``. The tabs mark a
 * current view, and on a page that is none of them the marker has to land
 * somewhere — it fell on "Overview", so the inspector claimed to be the
 * overview while showing a single page. Their trail crumb carries the
 * orientation on those routes instead.
 */
export default function ReportHeader({
  scanId,
  previousScanId,
  title,
  meta,
  actions,
  tabs = true,
}: {
  scanId: number;
  previousScanId: number | null;
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  /** Show the report's view tabs. Off on drill-downs (see above). */
  tabs?: boolean;
}) {
  const { pathname, search } = useLocation();
  // Under Issues and Verify changes the trail beneath the tabs names where
  // you are (``↳ Issues › <issue> › Page inspector: “<page>”``) and its last
  // step is the page's h1 (see ReportSubTrail), so no second heading is drawn
  // here. Overview has no trail and keeps its own title.
  const view = tabs ? activeView(pathname, search) : "";
  const titleInTrail = view === "issues" || view === "diff";
  return (
    <header className="mb-5">
      {/* Tabs first, title second. The tabs are the report's own navigation
          and belong at the top of its area, right under the topbar trail
          that ends in the same word; the title then reads as the heading of
          the view you chose, not as something the tabs sit beneath. */}
      {tabs && (
        <ReportWorkspaceNav scanId={scanId} previousScanId={previousScanId} />
      )}
      <div className={`${titleInTrail ? "mt-0.5 items-center" : "mt-5 items-start"} flex flex-wrap justify-between gap-3`}>
        <div className="min-w-0">
          {!titleInTrail && (
            <h1 className="text-2xl font-semibold leading-tight tracking-[-0.025em] text-fg sm:text-[1.75rem]">
              {title}
            </h1>
          )}
          {meta && (
            <p className={`${titleInTrail ? "" : "mt-1"} max-w-4xl text-sm leading-6 text-fg-muted`}>{meta}</p>
          )}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

/**
 * The shared shape of every report meta line: the counts that identify this
 * view, then the standing caveat. Keeping it in one component is what stops
 * the three views from drifting into three different sentences.
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
