import { Link, useLocation, useSearchParams } from "react-router";
import { useQueries } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { api } from "../api/client";
import { cn } from "../lib/cn";
import { useScanQuery } from "../hooks/useScanQuery";

/**
 * The topbar's orientation line for everything under a report, and the only
 * breadcrumb trail on any page.
 *
 * ``Reports › app.codegra.de #40 › Contrast (Minimum) › Pages › Page
 * inspector``: where you are in the app, which report you are reading (one
 * site can have several, so the number is part of the name), and the path
 * from the report down to this page. On the report's own views, Issues and
 * Verify changes, the trail ends at the report: the lit tab already says
 * which view, and "Issues" as a crumb, a tab and a heading was the same word
 * three times on one screen.
 *
 * Everything here is derived from the URL, so the trail is complete on the
 * first paint of a route rather than appearing once data lands. The scan
 * query only upgrades the report crumb from "Report #46" to the site itself,
 * and it shares ``["scan", id]`` with the routes below, a cache hit, not a
 * second request.
 */
const VIEWS: Array<[RegExp, string]> = [
  [/^\/scans\/\d+\/issues\/[^/]+\/pages\/\d+\/screenshots\/?$/, "Issue screenshots"],
  [/^\/scans\/\d+\/issues\/[^/]+\/pages\/?$/, "Pages"],
  [/^\/scans\/\d+\/issues\/[^/]+\/?$/, "Issue evidence"],
  [/^\/scans\/\d+\/issues\/?$/, "Issues"],
  [/^\/scans\/\d+\/diff\/?$/, "Verify changes"],
  [/^\/scans\/\d+\/pages\/\d+\/inspect\/?$/, "Page inspector"],
  [/^\/scans\/\d+\/pages\/\d+\/?$/, "Page evidence"],
  [/^\/scans\/\d+\/findings\/grouped\/?$/, "Grouped image evidence"],
  [/^\/scans\/\d+\/findings\/?$/, "Image evidence"],
  [/^\/scans\/\d+\/a11y\/by-rule\/?$/, "DOM-engine rules"],
  [/^\/scans\/\d+\/a11y\/?$/, "DOM-engine evidence"],
  [/^\/scans\/\d+\/?$/, "Report"],
];

/** Strip the scheme and trailing slash, the host and path are the identity. */
export function siteLabel(seedUrl: string): string {
  return seedUrl.replace(/^https?:\/\//, "").replace(/\/+$/, "");
}

/** One link in the trail. `issue` is set when the label should be that issue's title. */
export type Crumb = { label: string; to: string; issue?: { scanId: number; key: string } };

/** An in-app absolute path, or null. `<Link to>` follows a full URL off-site,
 *  which would let a crafted link put an attacker's destination inside the
 *  app's own breadcrumb, so only absolute in-app paths are honoured. */
function inAppPath(to: string | null): string | null {
  if (!to || !to.startsWith("/") || to.startsWith("//")) return null;
  return to;
}

/** Split an in-app path into its pathname and query, dropping any hash. */
function splitPath(to: string): { pathname: string; params: URLSearchParams } {
  const [beforeHash] = to.split("#");
  const [pathname, query = ""] = beforeHash.split("?");
  return { pathname, params: new URLSearchParams(query) };
}

/** The pathname alone, so two links to the same view with different filters count as one crumb. */
function samePath(a: string, b: string): boolean {
  return splitPath(a).pathname.replace(/\/+$/, "") === splitPath(b).pathname.replace(/\/+$/, "");
}

/** Routes that belong in the trail but have no report behind them yet. */
const STANDALONE: Array<[RegExp, string]> = [[/^\/scans\/new\/?$/, "New scan"]];

export function reportRouteMatch(
  pathname: string,
): { scanId: number | null; view: string } | null {
  // New scan sits under /scans but has no report yet, so it carries no middle
  // crumb. It still belongs in the topbar: the trail is where orientation
  // lives in this app, and a page that draws its own breadcrumb above the
  // title puts the same information in two different places depending on which
  // route you are standing in.
  const standalone = STANDALONE.find(([pattern]) => pattern.test(pathname))?.[1];
  if (standalone) return { scanId: null, view: standalone };

  const scanId = Number(pathname.match(/^\/scans\/(\d+)(?:\/|$)/)?.[1]);
  if (!Number.isFinite(scanId)) return null;
  const view = VIEWS.find(([pattern]) => pattern.test(pathname))?.[1];
  return view ? { scanId, view } : null;
}

/**
 * The issue key in any route scoped to one issue, decoded, or null.
 *
 * ``/scans/:id/issues/:key`` and everything under it (its pages, a page's
 * screenshots) all belong to one issue, and the trail says so: the issue is a
 * level of the hierarchy, not a view name. On the issue's own route the chip
 * is its title — the reader can already see they are looking at evidence, what
 * the trail has to tell them is *which* issue.
 */
function issueScopeKey(pathname: string): string | null {
  const key = pathname.match(/^\/scans\/\d+\/issues\/([^/]+)(?:\/|$)/)?.[1];
  return key ? decodeURIComponent(key) : null;
}

/** Deepest chain of `?back=` links the trail will unwind before giving up. */
const MAX_DEPTH = 12;

/**
 * Every crumb between the report and a location, root first, then the
 * location itself as the last entry.
 *
 * The trail used to read a single `?origin=&back=` pair and stop, so any
 * drill-down deeper than one step lost its middle: Issues › issue › its pages
 * › the inspector showed as ``Pages with this issue › Page inspector`` with
 * no way back to the issue or the list. Now the chain is unwound: `back` is
 * itself an in-app path, and if it carries its own `?origin=&back=` that is
 * where *it* was opened from, and so on up to the report. Every step the
 * reader actually took is a crumb, however deep they went.
 *
 * Two more sources fill any gap a link did not carry. A route scoped to one
 * issue proves its parents from the path alone (the issue list, then the
 * issue), so a bookmark or deep link lands with the whole trail. And the
 * inspector's `?contextTo=` names the issue or finding it is circling, so a
 * page opened straight from the issue list still shows the issue between the
 * list and the page. Anything already in the chain is not added twice.
 */
function trailFor(
  pathname: string,
  params: URLSearchParams,
  depth = 0,
  seen: string[] = [],
): Crumb[] {
  const match = reportRouteMatch(pathname);
  const scanId = match?.scanId ?? null;
  const chain: Crumb[] = [];
  const add = (crumb: Crumb) => {
    if (!chain.some((existing) => samePath(existing.to, crumb.to))) chain.push(crumb);
  };

  // 1. The view this one was opened from, and everything it was opened from.
  const originLabel = params.get("origin");
  const back = inAppPath(params.get("back"));
  if (originLabel && back && depth < MAX_DEPTH && !seen.includes(back)) {
    const parent = splitPath(back);
    const parentTrail = trailFor(parent.pathname, parent.params, depth + 1, [...seen, back]);
    if (parentTrail.length > 0) {
      // The link that opened this view named it; that name wins over the
      // generic view name, but an issue route keeps upgrading to its title.
      const last = parentTrail[parentTrail.length - 1];
      parentTrail[parentTrail.length - 1] = { ...last, label: originLabel, to: back };
      parentTrail.forEach(add);
    } else {
      add({ label: originLabel, to: back });
    }
  }

  // 2. What the path proves: an issue-scoped route sits under the list and the issue.
  const issueKey = issueScopeKey(pathname);
  const onIssueItself = match?.view === "Issue evidence";
  if (issueKey && scanId != null) {
    add({ label: "Issues", to: `/scans/${scanId}/issues` });
    if (!onIssueItself) {
      add({
        label: issueKey,
        to: `/scans/${scanId}/issues/${encodeURIComponent(issueKey)}`,
        issue: { scanId, key: issueKey },
      });
    }
  }

  // 3. What the inspector is circling, when the chain did not pass through it.
  const contextTo = inAppPath(params.get("contextTo"));
  const contextLabel = params.get("context");
  if (contextTo && contextLabel && depth < MAX_DEPTH && !seen.includes(contextTo)) {
    const context = splitPath(contextTo);
    const contextKey = issueScopeKey(context.pathname);
    const contextScan = reportRouteMatch(context.pathname)?.scanId ?? null;
    add(
      contextKey && contextScan != null
        ? { label: contextKey, to: contextTo, issue: { scanId: contextScan, key: contextKey } }
        : { label: contextLabel, to: contextTo },
    );
  }

  // 4. This location itself.
  if (match) {
    const query = params.toString();
    const self: Crumb = { label: match.view, to: `${pathname}${query ? `?${query}` : ""}` };
    if (onIssueItself && issueKey && scanId != null) self.issue = { scanId, key: issueKey };
    add(self);
  }
  return chain;
}

/**
 * The trail for the current location, with every issue crumb carrying its
 * title once it has loaded.
 */
export function useReportTrail(): {
  match: ReturnType<typeof reportRouteMatch>;
  trail: Crumb[];
} {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const match = reportRouteMatch(pathname);
  const trail = trailFor(pathname, params);
  // Every issue the trail passes through needs its title. Same key and sort
  // the issue routes use, so this is a cache hit rather than a second
  // request for a title that is already on screen. Usually one issue, at
  // most a handful.
  const issues = trail.flatMap((crumb) => (crumb.issue ? [crumb.issue] : []));
  const distinct = issues.filter(
    (issue, index) => issues.findIndex((other) => other.scanId === issue.scanId && other.key === issue.key) === index,
  );
  const titleQueries = useQueries({
    queries: distinct.map((issue) => ({
      queryKey: ["issue-detail", issue.scanId, issue.key, "occurrences_desc"],
      queryFn: () => api.getIssueDetail(issue.scanId, issue.key, "occurrences_desc"),
      enabled: match != null,
    })),
  });
  const titleOf = (issue: { scanId: number; key: string }): string | null => {
    const index = distinct.findIndex((other) => other.scanId === issue.scanId && other.key === issue.key);
    return titleQueries[index]?.data?.row.title ?? null;
  };
  // Until a title lands the key (or the link's own label) holds the place, so
  // the trail is never empty and never jumps in length twice.
  const labelled = trail.map((crumb) => {
    if (!crumb.issue) return crumb;
    const title = titleOf(crumb.issue);
    return title ? { ...crumb, label: title } : crumb;
  });
  return { match, trail: labelled };
}

/** The report's own views: its URL, the issue table, and Verify changes. */
function isReportView(pathname: string): boolean {
  return /^\/scans\/\d+(?:\/issues|\/diff)?\/?$/.test(pathname);
}

/**
 * Split the trail into the report crumb's target and the crumbs after it.
 *
 * The report and its issue table are one crumb: the report opens on Issues,
 * so a crumb for the list would be the report a second time. Any link that
 * carried the list as its origin (filters and all) becomes where the report
 * crumb points, so the way back still lands on the table the reader left.
 * On the report's own views nothing follows the report crumb at all.
 */
function reportTrail(
  trail: Crumb[],
  pathname: string,
  scanId: number,
): { reportTo: string; crumbs: Crumb[] } {
  const listPath = `/scans/${scanId}/issues`;
  const isReport = (crumb: Crumb) =>
    samePath(crumb.to, listPath) || samePath(crumb.to, `/scans/${scanId}`);
  const list = trail.find((crumb) => samePath(crumb.to, listPath));
  return {
    reportTo: list?.to ?? listPath,
    crumbs: isReportView(pathname) ? [] : trail.filter((crumb) => !isReport(crumb)),
  };
}

export default function ReportCrumb() {
  const { match, trail } = useReportTrail();
  const { pathname } = useLocation();
  // The same shared report-summary query the gate and the route use, so
  // the breadcrumb reads the site name from cache. It previously kept its
  // own `["scan", id]` entry, which meant a second request for the same
  // record on every report page, and one that was not partitioned by
  // proxy identity.
  const scanQuery = useScanQuery(typeof match?.scanId === "number" ? match.scanId : 0);
  if (!match) return null;

  const seedUrl = scanQuery.data?.seed_url;
  // A route with no report yet (New scan) has no report crumb: the trail is
  // Reports and then the page itself.
  const report =
    match.scanId == null
      ? null
      : {
          ...reportTrail(trail, pathname, match.scanId),
          site: seedUrl ? siteLabel(seedUrl) : "Report",
          id: match.scanId,
        };
  const crumbs = report ? report.crumbs : trail;
  const ancestors = crumbs.slice(0, -1);
  const current = crumbs[crumbs.length - 1];

  // WAI-ARIA breadcrumb pattern: a navigation landmark named "Breadcrumb"
  // around an ordered list, one item per crumb, the separators drawn inside
  // the items (and hidden from assistive tech) so the list's length is the
  // trail's, and the last item plain text marked ``aria-current="page"``.
  // It used to be a filled chip, which looked like a button you could press.
  return (
    <nav aria-label="Breadcrumb" className="min-w-0 text-sm">
      <ol className="flex min-w-0 flex-wrap items-center gap-x-1">
        <Crumb to="/scans" first>
          Reports
        </Crumb>
        {report &&
          (current ? (
            <Crumb to={report.reportTo} title={`${report.site} #${report.id}`}>
              <ReportName site={report.site} id={report.id} />
            </Crumb>
          ) : (
            <Current title={`${report.site} #${report.id}`}>
              <ReportName site={report.site} id={report.id} />
            </Current>
          ))}
        {ancestors.map((ancestor) => (
          <Crumb
            key={`${ancestor.label}-${ancestor.to}`}
            to={ancestor.to}
            className="max-w-[12rem]"
            title={ancestor.label}
          >
            <span className="truncate">{ancestor.label}</span>
          </Crumb>
        ))}
        {current && (
          <Current title={current.label}>
            <span className="truncate">{current.label}</span>
          </Current>
        )}
      </ol>
    </nav>
  );
}

/** ``app.codegra.de #40``. The site truncates; the number never does, since
 *  it is what tells two reports of one site apart. */
function ReportName({ site, id }: { site: string; id: number }) {
  return (
    <>
      <span className="truncate">{site}</span>
      <span className="shrink-0 whitespace-pre tabular-nums"> #{id}</span>
    </>
  );
}

function Crumb({
  to,
  children,
  className,
  title,
  first = false,
}: {
  to: string;
  children: React.ReactNode;
  className?: string;
  /** Full text for a crumb the layout truncates (an issue title). */
  title?: string;
  first?: boolean;
}) {
  return (
    <li className="flex min-w-0 items-center">
      {!first && <Separator />}
      <Link
        to={to}
        title={title}
        className={cn(
          "report-link flex min-h-target min-w-0 max-w-[20rem] items-center whitespace-nowrap px-2 py-2 font-semibold",
          className,
        )}
      >
        {children}
      </Link>
    </li>
  );
}

/** Where you are: plain text, not a link and not a chip. An issue title is a
 *  sentence, so it truncates and keeps the whole title in ``title`` for a
 *  hover and in the DOM for a screen reader. */
function Current({ children, title }: { children: React.ReactNode; title: string }) {
  return (
    <li className="flex min-w-0 items-center">
      <Separator />
      <span
        aria-current="page"
        title={title}
        className="flex min-w-0 max-w-[26rem] items-center whitespace-nowrap px-2 py-2 font-semibold text-fg"
      >
        {children}
      </span>
    </li>
  );
}

function Separator() {
  return <ChevronRight aria-hidden className="h-3.5 w-3.5 shrink-0 text-border-strong" />;
}
