import { Fragment } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import { useQueries, useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { api } from "../api/client";

/**
 * The topbar's orientation line for everything under a report.
 *
 * ``Reports › lsa-mis.github.io/axcess › Issues``, where you are in the app,
 * which site's evidence you are reading, and which view of it. The last
 * segment tracks the tab, so the trail and the tabs never disagree.
 *
 * Everything here is derived from the URL, so the trail is complete on the
 * first paint of a route rather than appearing once data lands. The scan
 * query only upgrades the middle crumb from "Report #46" to the site itself,
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
  [/^\/scans\/\d+\/?$/, "Overview"],
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
 * title once it has loaded. Shared by the topbar trail and the sub-trail
 * under the report tabs, so the two can never disagree about where you are.
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

/**
 * The topbar's share of the trail: up to the report view, never past it.
 *
 * Inside Issues or Verify changes the drill-down crumbs (the issue, its
 * pages, the inspector) are printed under that tab by `ReportSubTrail`, so
 * the topbar stops at the tab — ``Reports › site › Issues`` — instead of
 * saying the same thing twice in two places. A page reached with no tab
 * context keeps its full trail here, because nothing else shows it.
 */
function topbarTrail(trail: Crumb[], pathname: string, search: string): Crumb[] {
  const view = activeView(pathname, search);
  if (view !== "issues" && view !== "diff") return trail;
  const scanId = reportRouteMatch(pathname)?.scanId;
  const root = trail.findIndex((crumb) => crumb.to.split("?")[0] === `/scans/${scanId}/${view}`);
  return root >= 0 ? trail.slice(0, root + 1) : trail;
}

/**
 * Which of the three views a location belongs to, or none.
 *
 * A drill-down is still part of the view it was opened from: an issue's pages
 * and the inspector reached through them belong to Issues, and a page opened
 * from Verify changes belongs there. The tabs therefore stay on every
 * drill-down with the right one lit, instead of disappearing (which lost the
 * way back) or lighting Overview (which was wrong). The view is read from the
 * path first, then from the `?origin=&back=&contextTo=` trail the link
 * carried; a page reached with neither marks nothing.
 */
export function activeView(pathname: string, search: string): "overview" | "issues" | "diff" | "" {
  const params = new URLSearchParams(search);
  const trail = [params.get("back") ?? "", params.get("contextTo") ?? ""].join(" ");
  const origin = params.get("origin") ?? "";
  if (/\/scans\/\d+\/issues(\/|$)/.test(pathname)) return "issues";
  if (/\/scans\/\d+\/diff(\/|$)/.test(pathname)) return "diff";
  if (/^\/scans\/\d+\/?$/.test(pathname)) return "overview";
  if (/\/issues(\/|$|\?)/.test(trail) || origin === "Issues") return "issues";
  if (/\/diff(\/|$|\?)/.test(trail) || origin === "Verify changes") return "diff";
  return "";
}

export default function ReportCrumb() {
  const { pathname, search } = useLocation();
  const { match, trail: full } = useReportTrail();
  const labelled = topbarTrail(full, pathname, search);
  const scanQuery = useQuery({
    queryKey: ["scan", match?.scanId],
    queryFn: () => api.getScan(match!.scanId as number),
    enabled: match != null && match.scanId != null,
  });
  if (!match) return null;

  const ancestors = labelled.slice(0, -1);
  const view = labelled[labelled.length - 1]?.label ?? match.view;
  const seedUrl = scanQuery.data?.seed_url;
  const middle = seedUrl ? siteLabel(seedUrl) : `Report #${match.scanId}`;

  return (
    <nav aria-label="Breadcrumb" className="min-w-0 text-sm">
      <ol className="flex min-w-0 flex-wrap items-center gap-1">
        <Crumb to="/scans">Reports</Crumb>
        <Separator />
        {/* The site is the middle crumb and links to the report's own
            overview: from any view, one click gets back to the whole report.
            A route with no report yet (New scan) skips straight to the chip. */}
        {match.scanId != null && (
          <>
            <Crumb to={`/scans/${match.scanId}`} className="max-w-[18rem] truncate">
              {middle}
            </Crumb>
            <Separator />
          </>
        )}
        {ancestors.map((ancestor) => (
          <Fragment key={`${ancestor.label}-${ancestor.to}`}>
            <Crumb to={ancestor.to} className="max-w-[12rem] truncate" title={ancestor.label}>
              {ancestor.label}
            </Crumb>
            <Separator />
          </Fragment>
        ))}
        <li className="min-w-0">
          {/* The current view is a filled chip, not just bolder text: at a
              glance the trail should show which of the report's views you are
              standing in without being read word by word. */}
          {/* An issue title is a sentence, not a view name, so the chip
              truncates and keeps the whole title in `title` for a hover and
              in the DOM for a screen reader. */}
          <span
            aria-current="page"
            title={view}
            className="inline-block max-w-[26rem] truncate rounded-full bg-umich-blue/10 px-2.5 py-1 text-xs font-semibold text-umich-blue"
          >
            {view}
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
  title,
}: {
  to: string;
  children: React.ReactNode;
  className?: string;
  /** Full text for a crumb the layout truncates (an issue title). */
  title?: string;
}) {
  return (
    <li className="min-w-0">
      <Link
        to={to}
        title={title}
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
