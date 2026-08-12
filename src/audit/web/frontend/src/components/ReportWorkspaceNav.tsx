import { Link, useLocation } from "react-router";
import { cn } from "../lib/cn";

/** Minimal report navigation: summary, one issue table, and optional comparison. */
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
  if (previousScanId != null) {
    items.push({
      label: "Verify changes",
      to: `/scans/${scanId}/diff?compare_to=${previousScanId}`,
      active: pathname.includes("/diff"),
    });
  }

  return (
    <nav
      aria-label="Report workspace"
      className="mb-6 overflow-x-auto rounded-xs border border-border bg-surface p-1.5 shadow-card"
    >
      <ul className="flex w-max min-w-full flex-nowrap gap-x-1">
        {items.map((item, index) => (
          <li key={item.to}>
            <Link
              to={item.to}
              aria-current={item.active ? "page" : undefined}
              className={cn(
                "inline-flex min-h-target items-center rounded-[6px] border px-3 text-sm font-semibold no-underline transition-colors",
                item.active
                  ? "border-umich-blue bg-umich-blue text-white shadow-sm"
                  : "border-transparent text-fg-muted hover:bg-surface-muted hover:text-fg",
              )}
            >
              <span
                className="mr-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full border border-current text-2xs"
                aria-hidden
              >
                {index + 1}
              </span>
              <span className="whitespace-nowrap">{item.label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
