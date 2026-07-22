import { Link, useLocation } from "react-router-dom";
import { cn } from "../lib/cn";

/**
 * The expert's report lifecycle. This is local navigation, not a claim that
 * a scan alone determines conformance: the Manual checks step stays visible
 * beside machine evidence and exports.
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
    { label: "Overview", to: `/scans/${scanId}`, active: pathname === `/scans/${scanId}` },
    { label: "Review queue", to: `/scans/${scanId}/review`, active: pathname.includes("/review") || pathname.includes("/issues") },
    { label: "Manual checks", to: `/scans/${scanId}/manual-checks`, active: pathname.includes("/manual-checks") },
    { label: "Handoff", to: `/scans/${scanId}/handoff`, active: pathname.includes("/handoff") },
  ];
  if (previousScanId != null) {
    items.push({
      label: "Verify changes",
      to: `/scans/${scanId}/diff?compare_to=${previousScanId}`,
      active: pathname.includes("/diff"),
    });
  }

  return (
    <nav aria-label="Report workspace" className="mb-5 border-b border-border">
      <ul className="flex flex-wrap gap-x-1">
        {items.map((item) => (
          <li key={item.to}>
            <Link
              to={item.to}
              aria-current={item.active ? "page" : undefined}
              className={cn(
                "inline-flex min-h-target items-center border-b-2 px-3 text-sm font-semibold no-underline",
                item.active
                  ? "border-umich-blue text-umich-blue"
                  : "border-transparent text-fg-muted hover:border-border hover:text-fg",
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
