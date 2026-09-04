import type { ReactNode } from "react";
import ReportWorkspaceNav from "./ReportWorkspaceNav";

/**
 * The one header every view of a report wears.
 *
 * Overview, Issues and Verify changes are three views of the same evidence,
 * so they get the same chrome in the same order: title, a single meta line,
 * the view's actions, then the tabs. Before this each route invented its own
 * arrangement — different crumbs, different subtitle shapes, tabs on some
 * pages and not others — and the report stopped feeling like one place.
 *
 * The breadcrumb is deliberately absent: it lives in the topbar
 * (see ``ReportCrumb``) where it stays put while this content scrolls.
 */
export default function ReportHeader({
  scanId,
  previousScanId,
  title,
  meta,
  actions,
}: {
  scanId: number;
  previousScanId: number | null;
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
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
      <ReportWorkspaceNav scanId={scanId} previousScanId={previousScanId} />
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
