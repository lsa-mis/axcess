import { Fragment } from "react";
import { ChevronRight, CornerDownRight, FileText } from "lucide-react";
import { Link } from "react-router";
import { useReportTrail } from "./ReportCrumb";

/**
 * Where you are inside the current report view, one quiet line under its tab.
 *
 * ``↳ Issues › Contrast (Minimum)… › Pages › Page inspector``. It starts at
 * the view itself: the lit tab also leads back to the list, but the step back
 * belongs where the eye is already reading the path, as the first link in it.
 * That crumb carries the link the list was opened from, so it returns to the
 * list as it was left, filters and sort included. The corner glyph hangs the
 * line off the tab row like a branch, which is the relationship: a place
 * inside Issues, not a page of its own.
 *
 * Deliberately plain: small text, hairline chevrons, no pills, no background.
 * The topbar trail owns the chip. Every earlier step is a real link and looks
 * like one at rest — the app's blue underline — because a trail whose steps
 * only reveal themselves on hover is a trail nobody clicks; the current step
 * is the one thing that is not a link, in plain text colour. Links have a
 * 44 px hit area; long titles truncate with the full text on hover and in
 * the DOM. On the view's own list page the line is just ``↳ Issues``: every
 * page under a tab carries the same line, and it is the page's visible title
 * (see ReportHeader), so the list gets one too.
 */
export default function ReportSubTrail({ scanId, view }: { scanId: number; view: "issues" | "diff" }) {
  const { trail } = useReportTrail();
  const root = `/scans/${scanId}/${view}`;
  const start = trail.findIndex((crumb) => crumb.to.split("?")[0] === root);
  if (start < 0) return null;
  const crumbs = trail.slice(start);
  const last = crumbs.length - 1;
  const context = crumbs
    .slice(0, last)
    .map((crumb) => crumb.label)
    .join(", ");

  return (
    <nav
      aria-label={`Where you are in ${view === "issues" ? "Issues" : "Verify changes"}`}
      className="animate-drop-in mt-3 text-sm"
    >
      <ol className="flex min-w-0 flex-wrap items-center gap-x-0.5">
        <li aria-hidden className="flex items-center pr-1.5 text-border-strong">
          <CornerDownRight className="h-4 w-4" />
        </li>
        {crumbs.map((crumb, index) => (
          <Fragment key={`${crumb.to}-${index}`}>
            {/* No chevron before a title on its own line: the path ends at
                the last link, and a trailing chevron points at nothing. */}
            {index > 0 && !(index === last && last > 0) && (
              <li aria-hidden className="flex items-center text-border-strong">
                <ChevronRight className="h-4 w-4" />
              </li>
            )}
            {/* With steps above it, the title takes a line of its own, under
                the path, level with the content below, so it never wraps at an
                arbitrary point in the middle of the path. */}
            <li className={index === last && last > 0 ? "min-w-0 basis-full" : "min-w-0"}>
              {index === last ? (
                // The last step is the page's heading (the header draws no
                // other, see ReportHeader), and names the page it shows when
                // there is one: ``Page inspector: “Find a Room”``. A screen
                // reader's heading list gets just this step, then the steps
                // above it as context in words ("…, in Issues, <issue>"),
                // rather than the whole trail with its chevrons.
                <h1
                  aria-current="page"
                  title={crumb.detail ? `${crumb.label}: ${crumb.detail}` : crumb.label}
                  className={`flex max-w-[48rem] min-w-0 items-center gap-1.5 py-1 text-lg ${index === last && last > 0 ? "" : "px-1.5"} font-semibold leading-tight tracking-[-0.015em] text-fg sm:text-xl`}
                >
                  <span className={crumb.detail ? "shrink-0 font-medium text-fg-muted" : "truncate"}>
                    {crumb.label}
                    {crumb.detail ? ": " : ""}
                  </span>
                  {crumb.detail && (
                    <>
                      <FileText className="h-5 w-5 shrink-0 text-fg-muted" aria-hidden />
                      <span className="truncate">“{crumb.detail}”</span>
                    </>
                  )}
                  {context && <span className="sr-only">, in {context}</span>}
                </h1>
              ) : (
                <Link
                  to={crumb.to}
                  title={crumb.label}
                  // `report-link`: the app's one link style, underlined and
                  // blue at rest, so a step reads as somewhere you can go
                  // before you hover it. Subtle is in the size and spacing,
                  // never in hiding the affordance (the visible-links rule).
                  className="report-link block max-w-[28rem] min-h-target content-center truncate px-1.5 py-2 font-medium"
                >
                  {crumb.label}
                </Link>
              )}
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}
