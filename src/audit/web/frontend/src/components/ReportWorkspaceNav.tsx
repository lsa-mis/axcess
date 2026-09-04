import { Link, useLocation } from "react-router";
import { cn } from "../lib/cn";

/**
 * Report navigation: overview, the issue table, and change verification.
 *
 * These are three *views of the same report*, not three steps of a task, so
 * they render as underline tabs. The earlier numbered-pill treatment read as
 * a wizard ("1 Overview → 2 Issues → 3 Verify changes") and implied both an
 * order and a completion state that the report does not have — users asked
 * what they were supposed to have finished in step 1.
 */
export default function ReportWorkspaceNav({
  scanId,
  previousScanId,
}: {
  scanId: number;
  previousScanId: number | null;
}) {
  const { pathname } = useLocation();
  const items = [
    {
      label: "Overview",
      to: `/scans/${scanId}`,
      active: pathname === `/scans/${scanId}`,
    },
    {
      label: "Issues",
      to: `/scans/${scanId}/issues`,
      active: pathname.includes("/issues"),
    },
  ];
  items.push({
    label: "Verify changes",
    to: `/scans/${scanId}/diff${previousScanId != null ? `?compare_to=${previousScanId}` : ""}`,
    active: pathname.includes("/diff"),
  });

  return (
    <nav
      aria-label="Report workspace"
      className="mt-4 overflow-x-auto border-b border-border"
    >
      {/* -mb-px pulls the active tab's 2px underline over the nav's own
          hairline so the two read as a single rule, not a double border. */}
      <ul className="-mb-px flex w-max min-w-full flex-nowrap gap-6">
        {items.map((item) => (
          <li key={item.to}>
            <Link
              to={item.to}
              aria-current={item.active ? "page" : undefined}
              // The active tab is marked three ways — weight, color, and the
              // underline bar — so the current view is never color-only.
              className={cn(
                "inline-flex min-h-target items-center whitespace-nowrap border-b-2 px-0.5 text-sm font-semibold no-underline transition-colors",
                item.active
                  ? "border-umich-blue text-umich-blue"
                  : "border-transparent text-fg-subtle hover:border-border-strong hover:text-fg",
              )}
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
