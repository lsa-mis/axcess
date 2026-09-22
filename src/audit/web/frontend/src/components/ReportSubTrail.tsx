import { Fragment } from "react";
import { ChevronRight, CornerDownRight } from "lucide-react";
import { Link } from "react-router";
import { useReportTrail } from "./ReportCrumb";

/**
 * Where you are inside the current report view, one quiet line under its tab.
 *
 * ``↳ Contrast (Minimum)… › Pages › Page inspector``. It starts *after* the
 * tab — the lit tab is already the first crumb and the way back to the list,
 * so repeating "Issues" here would be the third time on one screen. The
 * corner glyph hangs the line off the tab row like a branch, which is the
 * relationship: a place inside Issues, not a page of its own.
 *
 * Deliberately plain: small text, hairline chevrons, no pills, no background.
 * The topbar trail owns the chip. Every earlier step is a real link and looks
 * like one at rest — the app's blue underline — because a trail whose steps
 * only reveal themselves on hover is a trail nobody clicks; the current step
 * is the one thing that is not a link, in plain text colour. Links have a
 * 44 px hit area; long titles truncate with the full text on hover and in
 * the DOM. Nothing renders on the tab's own list page, where the tab is the whole answer.
 */
export default function ReportSubTrail({ scanId, view }: { scanId: number; view: "issues" | "diff" }) {
  const { trail } = useReportTrail();
  const root = `/scans/${scanId}/${view}`;
  const start = trail.findIndex((crumb) => crumb.to.split("?")[0] === root);
  if (start < 0 || start >= trail.length - 1) return null;
  const crumbs = trail.slice(start + 1);
  const last = crumbs.length - 1;

  return (
    <nav
      aria-label={`Where you are in ${view === "issues" ? "Issues" : "Verify changes"}`}
      className="animate-drop-in mt-2 pl-3 text-xs"
    >
      <ol className="flex min-w-0 flex-wrap items-center gap-x-0.5">
        <li aria-hidden className="flex items-center pr-1.5 text-border-strong">
          <CornerDownRight className="h-3.5 w-3.5" />
        </li>
        {crumbs.map((crumb, index) => (
          <Fragment key={`${crumb.to}-${index}`}>
            {index > 0 && (
              <li aria-hidden className="flex items-center text-border-strong">
                <ChevronRight className="h-3 w-3" />
              </li>
            )}
            <li className="min-w-0">
              {index === last ? (
                <span
                  aria-current="page"
                  title={crumb.label}
                  className="block max-w-[28rem] truncate px-1.5 py-2 font-semibold text-fg"
                >
                  {crumb.label}
                </span>
              ) : (
                <Link
                  to={crumb.to}
                  title={crumb.label}
                  // `report-link`: the app's one link style, underlined and
                  // blue at rest, so a step reads as somewhere you can go
                  // before you hover it. Subtle is in the size and spacing,
                  // never in hiding the affordance (the visible-links rule).
                  className="report-link block max-w-[18rem] min-h-target content-center truncate px-1.5 py-2 font-medium"
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
