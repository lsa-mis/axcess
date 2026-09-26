import { useLayoutEffect, useRef, useState } from "react";
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
 * ``Reports › app.codegra.de #40 › Contrast (Minimum) › 12 affected pages ›
 * Dashboard | Sage Campus``: where you are in the app, which report you are reading (one
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

/**
 * What a crumb names, when it names one thing rather than a view.
 *
 * Every crumb says *which* thing it leads to: an issue by its title, a page
 * by its title, an issue's page list by how many pages it has. A view name
 * ("Page inspector", "Pages") says what kind of screen is behind the link,
 * which the reader could already see; it does not say which one, and two
 * different pages read the same. The label is resolved from data the routes
 * already load, and until it lands the crumb holds a placeholder.
 */
export type CrumbSubject =
  | { kind: "issue"; scanId: number; key: string }
  | { kind: "issuePages"; scanId: number; key: string }
  | { kind: "issuePageScreenshots"; scanId: number; key: string; pageId: number }
  | { kind: "page"; scanId: number; pageId: number; view: "inspect" | "evidence" };

/** One link in the trail. `subject` is set when the label should name that thing. */
export type Crumb = { label: string; to: string; subject?: CrumbSubject };

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

/** The thing a route itself names, from its path alone. */
function subjectFor(pathname: string): CrumbSubject | undefined {
  const page = pathname.match(/^\/scans\/(\d+)\/pages\/(\d+)(\/inspect)?\/?$/);
  if (page) {
    return {
      kind: "page",
      scanId: Number(page[1]),
      pageId: Number(page[2]),
      view: page[3] ? "inspect" : "evidence",
    };
  }
  const issue = pathname.match(
    /^\/scans\/(\d+)\/issues\/([^/]+)(?:\/(pages)(?:\/(\d+)\/screenshots)?)?\/?$/,
  );
  if (!issue) return undefined;
  const scanId = Number(issue[1]);
  const key = decodeURIComponent(issue[2]);
  if (issue[4]) return { kind: "issuePageScreenshots", scanId, key, pageId: Number(issue[4]) };
  if (issue[3]) return { kind: "issuePages", scanId, key };
  return { kind: "issue", scanId, key };
}

/** What a subject reads as before its data has loaded. */
function placeholderFor(subject: CrumbSubject): string {
  switch (subject.kind) {
    case "issue":
      return subject.key;
    case "issuePages":
      return "Affected pages";
    case "issuePageScreenshots":
      return `Screenshots on page ${subject.pageId}`;
    case "page":
      return subject.view === "inspect"
        ? `Page ${subject.pageId}`
        : `Stored evidence for page ${subject.pageId}`;
  }
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
      // generic view name, but a crumb with a subject still resolves to it.
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
        subject: { kind: "issue", scanId, key: issueKey },
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
        ? {
            label: contextKey,
            to: contextTo,
            subject: { kind: "issue", scanId: contextScan, key: contextKey },
          }
        : { label: contextLabel, to: contextTo },
    );
  }

  // 4. This location itself, named by what it shows when it shows one thing.
  if (match) {
    const query = params.toString();
    const subject = subjectFor(pathname);
    add({
      label: subject ? placeholderFor(subject) : match.view,
      to: `${pathname}${query ? `?${query}` : ""}`,
      subject,
    });
  }
  return chain;
}

/** A page's title, or its address when it has none. */
function pageName(title: string | null | undefined, url: string | null | undefined): string | null {
  const trimmed = title?.trim();
  if (trimmed) return trimmed;
  return url ? siteLabel(url) : null;
}

/**
 * The trail for the current location, with every crumb that names one thing
 * carrying that thing's name once it has loaded.
 */
export function useReportTrail(): {
  match: ReturnType<typeof reportRouteMatch>;
  trail: Crumb[];
} {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const match = reportRouteMatch(pathname);
  const trail = trailFor(pathname, params);
  const subjects = trail.flatMap((crumb) => (crumb.subject ? [crumb.subject] : []));
  // Every issue the trail passes through, for its title, page count, and the
  // titles of its pages. Same key and sort the issue routes use, so this is a
  // cache hit rather than a second request. Usually one issue.
  const issueKeys = [
    ...new Map(
      subjects
        .filter((subject) => subject.kind !== "page")
        .map((subject) => [`${subject.scanId}:${subject.key}`, subject] as const),
    ).values(),
  ];
  const issueQueries = useQueries({
    queries: issueKeys.map((subject) => ({
      queryKey: ["issue-detail", subject.scanId, subject.key, "occurrences_desc"],
      queryFn: () => api.getIssueDetail(subject.scanId, subject.key, "occurrences_desc"),
      enabled: match != null,
    })),
  });
  // Pages the trail names directly. The same key the page evidence and
  // inspector routes load, so on those routes this is read from cache.
  const pageKeys = [
    ...new Map(
      subjects
        .filter((subject) => subject.kind === "page")
        .map((subject) => [`${subject.scanId}:${subject.pageId}`, subject] as const),
    ).values(),
  ];
  const pageQueries = useQueries({
    queries: pageKeys.map((subject) => ({
      queryKey: ["page-evidence", subject.scanId, subject.pageId],
      queryFn: () => api.getPageEvidence(subject.scanId, subject.pageId),
      enabled: match != null,
    })),
  });
  const issueDetail = (scanId: number, key: string) =>
    issueQueries[issueKeys.findIndex((s) => s.scanId === scanId && s.key === key)]?.data;
  const pageEvidence = (scanId: number, pageId: number) =>
    pageQueries[pageKeys.findIndex((s) => s.scanId === scanId && s.pageId === pageId)]?.data;

  const nameOf = (subject: CrumbSubject): string | null => {
    switch (subject.kind) {
      case "issue":
        return issueDetail(subject.scanId, subject.key)?.row.title ?? null;
      case "issuePages": {
        const count = issueDetail(subject.scanId, subject.key)?.row.page_count;
        return count == null ? null : `${count} affected page${count === 1 ? "" : "s"}`;
      }
      case "issuePageScreenshots": {
        const page = issueDetail(subject.scanId, subject.key)?.pages.find(
          (candidate) => candidate.page_id === subject.pageId,
        );
        const name = pageName(page?.page_title, page?.page_url);
        return name ? `Screenshots on ${name}` : null;
      }
      case "page": {
        const page = pageEvidence(subject.scanId, subject.pageId)?.page;
        const name = pageName(page?.title, page?.url_normalized);
        if (!name) return null;
        return subject.view === "inspect" ? name : `Stored evidence for ${name}`;
      }
    }
  };
  // Until a name lands the placeholder (or the link's own label) holds the
  // place, so the trail is never empty and never jumps in length twice.
  const labelled = trail.map((crumb) => {
    if (!crumb.subject) return crumb;
    const name = nameOf(crumb.subject);
    return name ? { ...crumb, label: name } : crumb;
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
  const listRef = useRef<HTMLOListElement | null>(null);
  const [cap, setCap] = useState<number | null>(null);
  const trailText = trail.map((crumb) => crumb.label).join("\n") + (scanQuery.data?.seed_url ?? "");
  useLongestFirstCap(listRef, trailText, setCap);
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
      <ol ref={listRef} className="flex min-w-0 items-center gap-x-1 overflow-hidden">
        <Crumb to="/scans" first>
          {/* The root is never cut: it is short, and it is not measured. */}
          <span className="whitespace-nowrap">Reports</span>
        </Crumb>
        {report &&
          (current ? (
            <Crumb to={report.reportTo} title={`${report.site} #${report.id}`}>
              <ReportName site={report.site} id={report.id} cap={cap} />
            </Crumb>
          ) : (
            <Current title={`${report.site} #${report.id}`}>
              <ReportName site={report.site} id={report.id} cap={cap} />
            </Current>
          ))}
        {ancestors.map((ancestor) => (
          <Crumb key={`${ancestor.label}-${ancestor.to}`} to={ancestor.to} title={ancestor.label}>
            <CrumbText cap={cap}>{ancestor.label}</CrumbText>
          </Crumb>
        ))}
        {current && (
          <Current title={current.label}>
            <CrumbText cap={cap}>{current.label}</CrumbText>
          </Current>
        )}
      </ol>
    </nav>
  );
}

/** ``app.codegra.de #40``. The site can be cut like any long crumb; the
 *  number never is, since it is what tells two reports of one site apart. */
function ReportName({ site, id, cap }: { site: string; id: number; cap: number | null }) {
  return (
    <>
      <CrumbText cap={cap}>{site}</CrumbText>
      <span className="shrink-0 whitespace-pre tabular-nums"> #{id}</span>
    </>
  );
}

/**
 * One line, and when it is full, the longest crumbs are cut first.
 *
 * The trail never wraps or scrolls. When it fits, nothing is cut. When it
 * does not, one shared width cap is found (by water-filling) that makes the
 * line fit exactly: every crumb shorter than the cap is left whole, and only
 * crumbs longer than it are cut to it, with an ellipsis. So a short crumb
 * such as the report name keeps every character while a long title gives
 * up the width, and two long titles are cut to the same length.
 *
 * Cutting a short crumb to save a few pixels removes most of what it says;
 * cutting the longest one removes the least. "Reports" is never cut. A cut
 * crumb keeps its whole name in the DOM, so a screen reader reads it in
 * full, and in ``title`` for a pointer hover.
 */
function useLongestFirstCap(
  listRef: React.RefObject<HTMLOListElement | null>,
  trailText: string,
  setCap: (cap: number | null) => void,
): void {
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const fit = () => {
      const items = [...list.children] as HTMLElement[];
      const texts = [...list.querySelectorAll<HTMLElement>("[data-crumb-text]")];
      if (items.length === 0 || texts.length === 0) return;
      // scrollWidth is a text's full width even while the cap cuts it.
      const natural = texts.map((text) => text.scrollWidth);
      const shown = texts.reduce((sum, text) => sum + text.getBoundingClientRect().width, 0);
      const first = items[0].getBoundingClientRect();
      const last = items[items.length - 1].getBoundingClientRect();
      // Everything that is not measured text: "Reports", separators,
      // padding, gaps, and the report number. It does not change with the cap.
      const fixed = last.right - first.left - shown;
      const budget = list.clientWidth - fixed - 1;
      if (natural.reduce((sum, width) => sum + width, 0) <= budget) {
        setCap(null);
        return;
      }
      const sorted = [...natural].sort((a, b) => a - b);
      let remaining = budget;
      let cap = 0;
      for (let index = 0; index < sorted.length; index += 1) {
        const share = remaining / (sorted.length - index);
        if (sorted[index] > share) {
          cap = share;
          break;
        }
        remaining -= sorted[index];
      }
      setCap(Math.max(MIN_CAP_PX, Math.floor(cap)));
    };
    fit();
    // The line's width changes with the window, zoom, and text spacing, and a
    // late web font changes every text's width.
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
    observer?.observe(list);
    void document.fonts?.ready.then(fit);
    return () => observer?.disconnect();
  }, [listRef, trailText, setCap]);
}

/** Below this a cut crumb no longer says anything; the list clips instead. */
const MIN_CAP_PX = 64;

const CRUMB_TEXT = "min-w-0 px-2 py-2 font-semibold";

function Crumb({
  to,
  children,
  title,
  first = false,
}: {
  to: string;
  children: React.ReactNode;
  title?: string;
  first?: boolean;
}) {
  return (
    <li className="flex shrink-0 items-center">
      {!first && <Separator />}
      <Link
        to={to}
        title={title}
        className={cn("report-link flex min-h-target items-center", CRUMB_TEXT)}
      >
        {children}
      </Link>
    </li>
  );
}

/** Where you are: plain text, not a link and not a chip. */
function Current({ children, title }: { children: React.ReactNode; title: string }) {
  return (
    <li className="flex shrink-0 items-center">
      <Separator />
      <span
        aria-current="page"
        title={title}
        className={cn("flex min-h-target items-center text-fg", CRUMB_TEXT)}
      >
        {children}
      </span>
    </li>
  );
}

/** One measured, cuttable crumb label. */
function CrumbText({ children, cap }: { children: string; cap: number | null }) {
  return (
    <span data-crumb-text className="truncate" style={cap == null ? undefined : { maxWidth: cap }}>
      {children}
    </span>
  );
}

function Separator() {
  return <ChevronRight aria-hidden className="h-3.5 w-3.5 shrink-0 text-border-strong" />;
}
