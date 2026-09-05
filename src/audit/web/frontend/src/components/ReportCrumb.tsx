import { Link, useLocation } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { api } from "../api/client";

/**
 * The topbar's orientation line for everything under a report.
 *
 * ``Reports › lsa-mis.github.io/axcess › Issues``, where you are in the app,
 * which site's evidence you are reading, and which view of it. The last
 * segment tracks the tab, so the trail and the tabs never disagree.
 *
 * Everything here is derived from the pathname, so the trail is complete on
 * the first paint of a route rather than appearing once data lands. The scan
 * query only upgrades the middle crumb from "Report #46" to the site itself,
 * and it shares ``["scan", id]`` with the routes below, a cache hit, not a
 * second request.
 */
const VIEWS: Array<[RegExp, string]> = [
  [/^\/scans\/\d+\/issues\/[^/]+\/?$/, "Issue evidence"],
  [/^\/scans\/\d+\/issues\/?$/, "Issues"],
  [/^\/scans\/\d+\/diff\/?$/, "Verify changes"],
  [/^\/scans\/\d+\/pages\/\d+\/inspect\/?$/, "Page inspector"],
  [/^\/scans\/\d+\/pages\/\d+\/?$/, "Page evidence"],
  [/^\/scans\/\d+\/findings\/grouped\/?$/, "Grouped image evidence"],
  [/^\/scans\/\d+\/findings\/?$/, "Image evidence"],
  [/^\/scans\/\d+\/a11y\/by-rule\/?$/, "DOM-engine rules"],
  [/^\/scans\/\d+\/a11y\/?$/, "DOM-engine evidence"],
  [/^\/scans\/\d+\/?$/, "Overview"],
];

/** Strip the scheme and trailing slash, the host and path are the identity. */
export function siteLabel(seedUrl: string): string {
  return seedUrl.replace(/^https?:\/\//, "").replace(/\/+$/, "");
}

export function reportRouteMatch(
  pathname: string,
): { scanId: number; view: string } | null {
  const scanId = Number(pathname.match(/^\/scans\/(\d+)(?:\/|$)/)?.[1]);
  if (!Number.isFinite(scanId)) return null;
  const view = VIEWS.find(([pattern]) => pattern.test(pathname))?.[1];
  return view ? { scanId, view } : null;
}

export default function ReportCrumb() {
  const { pathname } = useLocation();
  const match = reportRouteMatch(pathname);
  const scanQuery = useQuery({
    queryKey: ["scan", match?.scanId],
    queryFn: () => api.getScan(match!.scanId),
    enabled: match != null,
  });
  if (!match) return null;

  const seedUrl = scanQuery.data?.seed_url;
  const middle = seedUrl ? siteLabel(seedUrl) : `Report #${match.scanId}`;

  return (
    <nav aria-label="Breadcrumb" className="min-w-0 text-sm">
      <ol className="flex min-w-0 flex-wrap items-center gap-1">
        <Crumb to="/scans">Reports</Crumb>
        <Separator />
        {/* The site is the middle crumb and links to the report's own
            overview: from any view, one click gets back to the whole report. */}
        <Crumb to={`/scans/${match.scanId}`} className="max-w-[18rem] truncate">
          {middle}
        </Crumb>
        <Separator />
        <li className="min-w-0">
          {/* The current view is a filled chip, not just bolder text: at a
              glance the trail should show which of the report's views you are
              standing in without being read word by word. */}
          <span
            aria-current="page"
            className="inline-block whitespace-nowrap rounded-full bg-umich-blue/10 px-2.5 py-1 text-xs font-semibold text-umich-blue"
          >
            {match.view}
          </span>
        </li>
      </ol>
    </nav>
  );
}

function Crumb({
  to,
  children,
  className,
}: {
  to: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <li className="min-w-0">
      <Link
        to={to}
        className={`report-link block min-h-target content-center whitespace-nowrap px-2 py-2 font-semibold ${className ?? ""}`}
      >
        {children}
      </Link>
    </li>
  );
}

function Separator() {
  return (
    <li aria-hidden className="flex shrink-0 items-center">
      <ChevronRight className="h-3.5 w-3.5 text-border-strong" />
    </li>
  );
}
