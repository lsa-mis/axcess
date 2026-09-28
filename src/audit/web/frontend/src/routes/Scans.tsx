import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, ListChecks, PlusCircle, Trash2 } from "lucide-react";
import { memo, useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import {
  protectedQueryKey,
  useProtectedIdentityContext,
} from "../hooks/useProtectedIdentityContext";
import {
  Button,
  Card,
  EmptyState,
  LinkButton,
  PageHeader,
  ScanStatusBadge,
  ScanTag,
  relativeTime,
} from "../components/ui";
import { withoutUserinfo } from "../components/ReportCrumb";
import { cn } from "../lib/cn";
import { CLICK_THROUGH_STATES_LABEL } from "../lib/labels";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import type { ProtectedScanStatus, ProtectedScanSummary, ScanSummary, SiteGroup } from "../api/types";
import { confirmDestructive } from "../hooks/usePreferences";
import BreakableUrl from "../components/BreakableUrl";
import LastScannedSite from "../components/LastScannedSite";
import {
  Cell,
  ColumnHeader,
  Row,
  RowHeader,
  SortHeader,
  Table,
  TableHead,
  TableRegion,
  TableSearch,
  TableBar,
  rowBand,
} from "../components/table/Table";
import { sortWords, type Sort, type SortKind } from "../components/table/sort";

/** A sign-in scan's progress, in the same words as the public scan badges. */
const PROTECTED_STATUS_LABEL: Record<ProtectedScanStatus, string> = {
  awaiting_authentication: "Waiting for sign-in",
  authentication_required: "Sign-in needed",
  running: "Scanning",
  completed: "Complete",
  failed: "Failed",
  interrupted: "Stopped",
};

/**
 * Reports list, one row per site. A site is a normalized seed scope, the
 * same key "compare to previous report" uses, and the server does the
 * grouping so the two can never disagree.
 *
 * A row shows one scan: the site's most recent *completed* run, the only
 * one whose numbers stand for the site. Interrupted, failed and running
 * scans never reach the row; they are listed, with every other scan, when
 * the site is expanded.
 *
 * Expanding a site lists all of its scans with the per-report actions
 * (All issues, Delete) the flat list used to carry.
 *
 * Why the table looks the way it does (keep these when you change it):
 *
 * - One header row. The table used to have a second row, "Most recent
 *   completed scan", over six of its columns. The W3C WAI Tables Tutorial
 *   (https://www.w3.org/WAI/tutorials/tables/) calls that a table with
 *   multi-level headers, which needs `scope="colgroup"` or `headers` and
 *   `id` on every cell (WCAG technique H43); a table with one header row
 *   needs only `scope="col"` (technique H63). Screen readers support the
 *   simple form best, and it is the one sighted readers scan fastest. The
 *   group existed only because one column (Scans) was not about the latest
 *   scan. Scans now sits under the site's name, so every column is about the
 *   same scan, and the caption says so once, in words.
 * - A sentence over the table says where the numbers come from, and the
 *   caption (technique H39, the table's accessible name) says it too. WCAG
 *   2.2 SC 1.3.1 Info and Relationships (Level A): "Information, structure,
 *   and relationships conveyed through presentation can be programmatically
 *   determined or are available in text." The sentence sits outside the
 *   scrolling region, not in a visible caption: WCAG 2.2 SC 1.4.10 Reflow
 *   (Level AA) asks that content be usable at 320 CSS pixels "without
 *   requiring scrolling in two dimensions", and excepts only content that
 *   needs a two-dimensional layout, such as the table's data. A caption
 *   scrolls sideways with the table and was cut off at 320 pixels.
 * - No visible "Sorted by" line. The sorted header already shows the order
 *   in words (the chip), and `aria-sort` gives it to a screen reader, as in
 *   the WAI-ARIA Authoring Practices sortable table
 *   (https://www.w3.org/WAI/ARIA/apg/patterns/table/examples/sortable-table/).
 *   A change of `aria-sort` is not announced reliably, so the new order is
 *   still said in a live region that is visually hidden. WCAG 2.2 SC 4.1.3
 *   Status Messages (Level AA): "In content implemented using markup
 *   languages, status messages can be programmatically determined through
 *   role or properties such that they can be presented to the user by
 *   assistive technologies without receiving focus." It asks for status
 *   messages to be announced, not shown. Other tables keep the visible
 *   line because it carries more there (filters, "Back to recommended
 *   order"); here it only repeated the chip.
 * - The search count sits beside the search box, visibly and in its own
 *   live region, shown only while there is a search: the result of an
 *   action next to the action (W3C COGA, "Making Content Usable",
 *   https://www.w3.org/TR/coga-usable/: one idea per chunk, and help people
 *   see what just happened).
 * - Rows expand with a disclosure button (`aria-expanded`, `aria-controls`)
 *   in the row header and a detail row under it, not a `treegrid` and not
 *   columns that open and close. Hidden columns change a table's shape
 *   under a screen reader, and `treegrid` needs grid keyboard handling
 *   that screen readers support unevenly. See Adrian Roselli, "Table with
 *   Expando Rows" (https://adrianroselli.com/2019/09/table-with-expando-rows.html).
 * - Column order: the site that names the row, when its latest completed
 *   scan finished, that scan's numbers, then the link to open it. The link
 *   stays last, the usual place for a row's action: the row is read (by eye
 *   or, cell by cell, by a screen reader) as "this site, as of then, with
 *   these results", and only then offers to open it. It was considered as
 *   the second column; that split the site from its date and numbers, and
 *   the Issues count is already a link into the same report earlier in the
 *   row. The Site column is sticky, so the row keeps its name when a narrow
 *   screen scrolls the table sideways to reach the link.
 * - "Open latest scan" is a link, styled as one, because it goes to a
 *   page; a button acts on this one. One quiet link per row rather than an
 *   outlined button in every row, which outweighed the numbers. Its
 *   accessible name starts with its visible words (WCAG 2.2 SC 2.5.3 Label
 *   in Name, Level A: "the name contains the text that is presented
 *   visually").
 */
type SortKey = "site" | "completed" | "pages" | "issues" | "images" | "states";

const SORT_KINDS: Record<SortKey, SortKind> = {
  site: "text",
  pages: "number",
  issues: "number",
  images: "number",
  states: "number",
  completed: "date",
};

const SORT_LABELS: Record<SortKey, string> = {
  site: "Site",
  pages: "Pages",
  issues: "Issues",
  images: "Images with text",
  states: CLICK_THROUGH_STATES_LABEL,
  completed: "Completed",
};

const TOTAL_COLUMNS = 7;

/**
 * `https://a.example/docs/` reads as `a.example/docs`; other schemes stay
 * visible. Any `user:password@` is dropped, as everywhere an address shows.
 */
export function siteLabel(siteUrl: string): string {
  return withoutUserinfo(siteUrl).replace(/^https:\/\//, "").replace(/\/$/, "");
}

/** The sortable value; null sorts last in either direction. */
function sortValue(site: SiteGroup, key: SortKey): number | string | null {
  const completed = site.most_recent_completed;
  switch (key) {
    case "site":
      return siteLabel(site.site_url).toLowerCase();
    case "pages":
      return completed ? completed.page_count : null;
    case "issues":
      return site.most_recent_completed_issue_count;
    case "images":
      return completed ? completed.finding_count : null;
    case "states":
      return completed ? completed.dom_state_count ?? 0 : null;
    case "completed":
      // Report ids increase with creation, so they order runs without a
      // start time too.
      return completed ? completed.id : null;
  }
}

/** A site matches when its address, or any of its scans' start address,
 *  contains the query. Case-insensitive; `query` is already lower case. */
function matchesSearch(site: SiteGroup, query: string): boolean {
  if (site.site_url.toLowerCase().includes(query)) return true;
  return site.scans.some((scan) => scan.seed_url.toLowerCase().includes(query));
}

function sortSites(sites: SiteGroup[], { column, direction }: Sort<SortKey>): SiteGroup[] {
  return [...sites].sort((a, b) => {
    const left = sortValue(a, column);
    const right = sortValue(b, column);
    if (left === null || right === null) {
      if (left === right) return b.most_recent.id - a.most_recent.id;
      return left === null ? 1 : -1;
    }
    const diff = left < right ? -1 : left > right ? 1 : 0;
    if (diff !== 0) return direction === "asc" ? diff : -diff;
    return b.most_recent.id - a.most_recent.id;
  });
}

// One empty list, so the memoized views below do not recompute while loading.
const NO_SITES: SiteGroup[] = [];

/** How often Reports refreshes while a scan is running. */
const RUNNING_REFRESH_MS = 5_000;

export default function ScansRoute() {
  const [sort, setSort] = useState<Sort<SortKey>>({ column: "completed", direction: "desc" });
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [search, setSearch] = useState("");
  // Under the "scans" prefix so every existing invalidation of the scan
  // list (create, cancel, delete) refreshes the grouped view as well.
  const { data: sites = NO_SITES, isLoading, isError } = useQuery({
    queryKey: ["scans", "sites"],
    queryFn: api.listSites,
    // While a scan runs, refresh so the list and the Last scanned card move on
    // by themselves when it finishes; the desktop app gets no focus event to
    // refetch on. Nothing running, nothing polled.
    refetchInterval: (query) =>
      query.state.data?.some((site) => site.scans.some((scan) => scan.status === "running"))
        ? RUNNING_REFRESH_MS
        : false,
  });
  const protectedIdentity = useProtectedIdentityContext();
  const protectedReports = useQuery({
    queryKey: protectedQueryKey("reports", protectedIdentity.fingerprint),
    queryFn: api.listProtectedScans,
    enabled: protectedIdentity.isReady,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    // A 403/404 simply means this browser is not in a protected deployment;
    // public report browsing remains fully usable and does not surface a
    // misleading error card.
    retry: false,
  });
  const protectedList = protectedReports.data?.reports;
  const protectedShown = protectedIdentity.isReady && !protectedReports.isFetching;
  // The same array until the data changes, so the pager does not re-measure
  // its table on every render.
  const protectedScans = useMemo(
    () => (protectedShown ? protectedList ?? [] : []),
    [protectedShown, protectedList],
  );

  const query = search.trim().toLowerCase();
  // Filtered and sorted only when the sites, the search or the sort change,
  // not on every render (expanding a site, a refetch that changed nothing).
  const matchingSites = useMemo(
    () => (query ? sites.filter((site) => matchesSearch(site, query)) : sites),
    [sites, query],
  );
  const sortedSites = useMemo(() => sortSites(matchingSites, sort), [matchingSites, sort]);
  const scanTotal = sites.reduce((total, site) => total + site.scan_count, 0);

  // A new search or sort starts the table over at page 1.
  const sitePages = usePagedRows(sortedSites, { resetKey: `${query}|${sort.column}|${sort.direction}` });
  const protectedPages = usePagedRows(protectedScans, { param: "protectedPage" });

  // Stable, so a site row that did not change skips re-rendering.
  const toggleSite = useCallback((siteUrl: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(siteUrl)) next.delete(siteUrl);
      else next.add(siteUrl);
      return next;
    });
  }, []);
  const sortProps = { sort, onSort: setSort };

  return (
    <>
      {/* No header "New scan" action, the topbar carries the single
          global CTA. The empty state below keeps its contextual one. */}
      <PageHeader
        title="Reports"
        subtitle={
          isLoading
            ? "Loading…"
            : isError
              ? "Reports could not be loaded"
              : `${sites.length} ${sites.length === 1 ? "site" : "sites"} · ${scanTotal} ${scanTotal === 1 ? "scan" : "scans"}`
        }
      />

      {/* No help paragraph above the table. It restated the "Most recent
          completed scan" band and glossed each column, and as the table's
          description a screen reader read all of it on every entry. The band,
          the caption and each cell's `headers` say which scan the numbers
          come from. */}
      {!isLoading && !isError && <LastScannedSite sites={sites} />}

      {isError ? (
        <p role="alert" className="mb-4 text-sm text-sev-critical">
          Could not load reports. Refresh the page to try again.
        </p>
      ) : isLoading ? (
        <p role="status">Loading reports…</p>
      ) : sites.length === 0 && protectedScans.length === 0 ? (
        <EmptyState
          title="No reports yet"
          message="Start a scan to check a website. Axcess makes a report when the scan finishes."
          action={
            <LinkButton to="/scans/new" variant="primary">
              <PlusCircle className="h-4 w-4" aria-hidden /> Start a new scan
            </LinkButton>
          }
        />
      ) : (
        <Card>
          {/* One small search, in the table's own bar: it filters the rows
              below by site address. The ⌘K palette still finds anything
              anywhere; this is for narrowing a long list in place. */}
          <TableBar pager={<TablePagination label="Public reports" noun="sites" {...sitePages} />}>
            <TableSearch label="Search sites" id="site-search" value={search} onChange={setSearch} />
            {/* Always mounted, so the count is announced when it changes;
                empty, and so invisible, while there is no search. */}
            <p role="status" className="text-xs text-fg-muted">
              {query &&
                `${matchingSites.length} of ${sites.length} ${sites.length === 1 ? "site matches" : "sites match"} “${search.trim()}”.`}
            </p>
          </TableBar>
          {/* The order, for screen readers only: the sorted header's chip
              shows it (SC 4.1.3, see the comment on this route). */}
          <p role="status" className="sr-only">
            Sorted by {SORT_LABELS[sort.column]}, {sortWords(SORT_KINDS[sort.column], sort.direction)}.
          </p>
          {/* Outside the region, so it wraps at 320 pixels rather than
              scrolling sideways with the table (SC 1.4.10). */}
          <p className="px-4 pb-2 pt-3 text-sm text-fg-muted">
            Each row shows the report from the site’s most recent completed scan.
          </p>
          <TableRegion label="Public reports table" paged={sitePages}>
            <Table
              className="min-w-[48rem]"
              caption="Public reports by site. Each row shows the report from the site’s most recent completed scan."
            >
              <TableHead>
                {/* One header row (H63): see the comment on this route. */}
                <tr>
                  <SortHeader
                    column="site"
                    kind="text"
                    wrap="words"
                    className="sticky left-0 z-[2] bg-surface-muted align-bottom"
                    {...sortProps}
                  >
                    {SORT_LABELS.site}
                  </SortHeader>
                  {(["completed", "pages", "issues", "images", "states"] as const).map((column) => (
                    <SortHeader
                      key={column}
                      column={column}
                      kind={SORT_KINDS[column]}
                      wrap="words"
                      className="align-bottom"
                      {...sortProps}
                    >
                      {SORT_LABELS[column]}
                    </SortHeader>
                  ))}
                  <ColumnHeader className="whitespace-nowrap px-3 py-1.5 align-bottom">
                    {/* The height of a sort button, words at its foot like theirs,
                        so its label lines up with them. */}
                    <span className="inline-flex min-h-target items-end px-1 pb-1.5">Report</span>
                  </ColumnHeader>
                </tr>
              </TableHead>
              <tbody>
                {sortedSites.length === 0 && (
                  <tr className="border-t border-border">
                    <td colSpan={TOTAL_COLUMNS} className="p-6 text-center text-fg-muted">
                      {query ? `No sites match “${search.trim()}”.` : "No public reports yet."}
                    </td>
                  </tr>
                )}
                {sitePages.pageRows.map((site, index) => {
                  const position = (sitePages.page - 1) * sitePages.pageSize + index;
                  return (
                    <SiteRows
                      key={site.site_url}
                      site={site}
                      index={position}
                      rowId={`site-row-${position}`}
                      expanded={expanded.has(site.site_url)}
                      onToggle={toggleSite}
                    />
                  );
                })}
              </tbody>
            </Table>
          </TableRegion>
        </Card>
      )}

      {protectedIdentity.isChecking && (
        <p className="mt-4 text-sm text-fg-muted" aria-live="polite">
          Checking access to sign-in scans…
        </p>
      )}

      {protectedIdentity.isReady && (
        <section className="mt-6" aria-labelledby="protected-reports-heading">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h2 id="protected-reports-heading" className="text-lg font-semibold text-fg">
                Sign-in scans
              </h2>
              <p className="mt-1 text-sm text-fg-muted">
                This list shows only the reports you are allowed to see. It does not show site addresses or detailed evidence.
              </p>
            </div>
            <LinkButton to="/scans/new?mode=login" variant="secondary">
              <PlusCircle className="h-4 w-4" aria-hidden /> New sign-in scan
            </LinkButton>
          </div>
          {protectedReports.isFetching ? (
            <p className="text-sm text-fg-muted" aria-live="polite">
              Loading your sign-in scans…
            </p>
          ) : protectedScans.length === 0 ? (
            <Card className="p-5 text-sm text-fg-muted">
              No sign-in scans yet. Before you start one, the site owner must approve which
              pages you scan. You also need a test account with only the access the scan
              needs (least privilege).
            </Card>
          ) : (
            <Card>
              {protectedPages.pages > 1 && (
                <TableBar pager={<TablePagination label="Sign-in scans" noun="sign-in scans" {...protectedPages} />} />
              )}
              <TableRegion label="Sign-in scans table" paged={protectedPages}>
                <Table className="min-w-[58rem]" caption="Your sign-in scans, most recently updated first">
                  <TableHead>
                    <tr>
                      <ColumnHeader>Report</ColumnHeader>
                      <ColumnHeader>Status</ColumnHeader>
                      <ColumnHeader>Environment and data classification</ColumnHeader>
                      <ColumnHeader>Pages</ColumnHeader>
                      <ColumnHeader>Occurrences</ColumnHeader>
                      <ColumnHeader>Updated</ColumnHeader>
                      <ColumnHeader>Open</ColumnHeader>
                    </tr>
                  </TableHead>
                  <tbody>
                    {protectedPages.pageRows.map((report, index) => (
                      <ProtectedReportRow
                        key={report.scan_id}
                        report={report}
                        index={(protectedPages.page - 1) * protectedPages.pageSize + index}
                      />
                    ))}
                  </tbody>
                </Table>
              </TableRegion>
            </Card>
          )}
        </section>
      )}
    </>
  );
}

/**
 * One site's summary row, plus its scan list when expanded. The expanded
 * list is its own captioned table: a nested table keeps each scan's
 * columns labelled, where extra rows in the outer table would sit under
 * headers that describe a different scan. Memoized: expanding one site
 * re-renders that site's rows, not every row on the page.
 */
const SiteRows = memo(function SiteRows({ site, index, rowId, expanded, onToggle }: {
  site: SiteGroup;
  /** Position across pages, for the row stripe. */
  index: number;
  rowId: string;
  expanded: boolean;
  onToggle: (siteUrl: string) => void;
}) {
  const label = siteLabel(site.site_url);
  const completed = site.most_recent_completed;
  const detailId = `${rowId}-scans`;
  return (
    <>
      <Row index={index}>
        <RowHeader id={rowId} sticky className="min-w-52 max-w-xs py-1 font-normal">
          {/* The site's name toggles its scans too, not only the chevron:
              the whole block is one button. Its name starts with what it
              does and then reads the visible text, so a voice-control user
              can say what they see (SC 2.5.3). */}
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={expanded ? detailId : undefined}
            onClick={() => onToggle(site.site_url)}
            className="group flex w-full items-start gap-1 rounded-xs text-left hover:bg-surface-muted focus-visible:outline-none focus-visible:shadow-focus"
          >
            <span className="inline-flex min-h-target min-w-target shrink-0 items-center justify-center text-fg-muted group-hover:text-fg">
              <ChevronRight
                className={cn("h-4 w-4 transition-transform motion-reduce:transition-none", expanded && "rotate-90")}
                aria-hidden
              />
            </span>
            <span className="min-w-0 py-2">
              <span className="sr-only">
                {`${expanded ? "Hide" : "Show"} all ${site.scan_count} ${site.scan_count === 1 ? "scan" : "scans"} for `}
              </span>
              <span className="block break-words font-semibold text-fg underline-offset-2 group-hover:underline" title={withoutUserinfo(site.site_url)}>
                <BreakableUrl text={label} />
              </span>
              {/* All the site's scans, here rather than in a column: every
                  column is about the latest completed scan (one header row). */}
              <span className="block text-xs text-fg-muted">
                {`${site.scan_count.toLocaleString()} ${site.scan_count === 1 ? "scan" : "scans"}, ${site.completed_count.toLocaleString()} completed`}
              </span>
            </span>
          </button>
        </RowHeader>
        {completed ? (
          <>
            <Cell
              className="whitespace-nowrap text-center text-fg"
              title={completed.finished_at ?? completed.started_at ?? undefined}
            >
              {relativeTime(completed.finished_at ?? completed.started_at)}
            </Cell>
            <Cell numeric className="text-fg">
              {completed.page_count.toLocaleString()}
            </Cell>
            <Cell numeric>
              <Link
                to={`/scans/${completed.id}/issues`}
                className="report-link inline-flex min-h-target items-center px-1 font-semibold"
                aria-label={`${(site.most_recent_completed_issue_count ?? 0).toLocaleString()} issues in Report #${completed.id}`}
              >
                {(site.most_recent_completed_issue_count ?? 0).toLocaleString()}
              </Link>
            </Cell>
            <Cell numeric className="text-fg">
              {completed.finding_count.toLocaleString()}
            </Cell>
            <Cell numeric className="text-fg">
              {(completed.dom_state_count ?? 0).toLocaleString()}
            </Cell>
            <Cell className="whitespace-nowrap text-center">
              {/* A link styled as a link: it goes to a page (SC 2.5.3 for its name). */}
              <Link
                to={`/scans/${completed.id}`}
                className="report-link inline-flex min-h-target items-center px-1 font-semibold"
                aria-label={`Open latest scan of ${label}, the most recent completed scan`}
              >
                Open latest scan
              </Link>
            </Cell>
          </>
        ) : (
          <Cell colSpan={6} className="text-fg-muted">
            No completed scan yet. Expand the site to open its other scans.
          </Cell>
        )}
      </Row>
      {expanded && (
        // The site's stripe, and no rule above: it reads as part of the site row.
        <tr id={detailId} className={rowBand(index)}>
          <td colSpan={TOTAL_COLUMNS} className="px-4 pb-4 pt-2">
            <SiteScansTable site={site} label={label} />
          </td>
        </tr>
      )}
    </>
  );
});

function SiteScansTable({ site, label }: { site: SiteGroup; label: string }) {
  // Framed by its own scroll region (see TableRegion's className): rounded
  // corners the rows are clipped to, and a wide list scrolls here rather
  // than widening the whole reports table.
  return (
    <TableRegion label={`All scans for ${label}`} className="rounded-xs border border-border bg-surface">
      <Table
        captionClassName="px-3 py-2 text-left text-sm font-semibold text-fg"
        caption={`All scans for ${label}, most recent first`}
      >
        <TableHead>
          <tr>
            <ColumnHeader>Report</ColumnHeader>
            <ColumnHeader>Status</ColumnHeader>
            <ColumnHeader>Started</ColumnHeader>
            <ColumnHeader>Pages</ColumnHeader>
            <ColumnHeader>Images with text</ColumnHeader>
            <ColumnHeader>{CLICK_THROUGH_STATES_LABEL}</ColumnHeader>
            <ColumnHeader>Actions</ColumnHeader>
          </tr>
        </TableHead>
        <tbody>
          {site.scans.map((scan, index) => (
            <ScanRow key={scan.id} scan={scan} index={index} isHeadline={scan.id === site.most_recent_completed?.id} />
          ))}
        </tbody>
      </Table>
    </TableRegion>
  );
}

/**
 * One scan in a site's expanded list. Pulled out so the delete mutation's
 * loading state is local to the row that owns it.
 */
function ScanRow({ scan, index, isHeadline }: { scan: ScanSummary; index: number; isHeadline: boolean }) {
  return (
    <Row index={index}>
      <RowHeader className="whitespace-nowrap py-1 text-xs font-normal tabular-nums text-fg-muted">
        <Link
          to={`/scans/${scan.id}`}
          className="report-link inline-flex min-h-target items-center px-1 font-semibold"
          title={withoutUserinfo(scan.seed_url)}
        >
          <span className="sr-only">Open </span>Report #{scan.id}
        </Link>
        {isHeadline && (
          <span className="ml-2 font-sans text-xs font-normal text-fg-muted">
            (shown in the site row)
          </span>
        )}
      </RowHeader>
      <Cell className="text-center">
        <ScanStatusBadge value={scan.status} />
      </Cell>
      <Cell className="whitespace-nowrap text-center text-xs text-fg-muted" title={scan.started_at ?? undefined}>
        {relativeTime(scan.started_at)}
      </Cell>
      <Cell numeric className="text-fg">
        {scan.page_count.toLocaleString()}
      </Cell>
      <Cell numeric className="text-fg">
        {scan.finding_count.toLocaleString()}
      </Cell>
      <Cell numeric className="text-fg">
        {(scan.dom_state_count ?? 0).toLocaleString()}
      </Cell>
      <Cell className="whitespace-nowrap py-1">
        {/* Default `md` size (44px tall): destructive controls in
            particular must be a real target (SC 2.5.5). */}
        <div className="flex items-center justify-center gap-2">
          <LinkButton
            to={`/scans/${scan.id}/issues`}
            variant="ghost"
            className="report-link"
            aria-label={`All issues for Report #${scan.id}`}
          >
            <ListChecks className="h-4 w-4" aria-hidden />
            All issues
          </LinkButton>
          <DeleteScanButton scan={scan} />
        </div>
      </Cell>
    </Row>
  );
}

function ProtectedReportRow({ report, index }: { report: ProtectedScanSummary; index: number }) {
  return (
    <Row index={index}>
      <RowHeader className="whitespace-nowrap text-xs font-normal text-fg-muted"><ScanTag id={report.scan_id} /></RowHeader>
      <Cell><span className="font-medium text-fg">{PROTECTED_STATUS_LABEL[report.protection_status] ?? report.protection_status.replaceAll("_", " ")}</span></Cell>
      <Cell className="text-fg-muted">{report.environment} · {report.data_classification}</Cell>
      <Cell numeric className="text-fg">{report.page_count.toLocaleString()}</Cell>
      <Cell numeric className="text-fg">{report.issue_occurrences.toLocaleString()}</Cell>
      <Cell className="text-center text-xs text-fg-muted" title={report.updated_at}>{relativeTime(report.updated_at)}</Cell>
      <Cell className="py-1 text-center">
        <LinkButton to={`/scans/${report.scan_id}/protected`} variant="ghost" aria-label={`Open sign-in scan ${report.scan_id}`}>
          Open sign-in scan
        </LinkButton>
      </Cell>
    </Row>
  );
}

/**
 * Delete button with a window.confirm gate. We use the native confirm()
 * intentionally, it's keyboard-accessible by default, screen-reader
 * friendly, and adds zero UI surface. The cost is a slightly utilitarian
 * dialog, which is appropriate for an internal a11y tool and avoids the
 * trap of building a custom modal that itself fails axe.
 *
 * Running scans show a disabled button with a tooltip explaining why,
 * the user shouldn't have to discover the constraint by clicking.
 */
function DeleteScanButton({ scan }: { scan: ScanSummary }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const isRunning = scan.status === "running";

  const mutation = useMutation({
    mutationFn: () => api.deleteScan(scan.id),
    onSuccess: () => {
      // Refresh the scans list. The deleted row vanishes on next render.
      void queryClient.invalidateQueries({ queryKey: ["scans"] });
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
    },
  });

  if (isRunning) {
    return (
      <Button
        variant="ghost"
        disabled
        title="Stop the scan before you delete this report."
        className="text-fg-subtle"
        aria-label={`Delete report ${scan.id} (not available while the scan is running)`}
      >
        <Trash2 className="h-4 w-4" aria-hidden />
        Delete
      </Button>
    );
  }

  return (
    <>
      <Button
        variant="ghost"
        disabled={mutation.isPending}
        className="text-sev-critical hover:bg-sev-critical-bg"
        aria-label={`Delete report ${scan.id}`}
        onClick={() => {
          // confirm() blocks; it's the right primitive for "are you sure".
          // Message includes the scan ID and seed URL so the user knows
          // exactly which scan they're about to remove.
          const ok = confirmDestructive(
            `Delete report #${scan.id} (${siteLabel(scan.seed_url)})?\n\n` +
              "This deletes the report for good, with its pages, issues, and " +
              "history. You cannot undo this. Axcess keeps the saved image " +
              "files, because other reports may use them.",
          );
          if (ok) mutation.mutate();
        }}
      >
        <Trash2 className="h-4 w-4" aria-hidden />
        {mutation.isPending ? "Deleting…" : "Delete"}
      </Button>
      {error && (
        // role="alert" + text-xs (12px). Bumped from text-2xs (10px)
        // because errors are critical to read on first glance, AAA
        // reading-comfort doesn't mandate a font size, but tiny error
        // text fights the user.
        <span className="ml-2 text-xs text-sev-critical" role="alert">
          {error}
        </span>
      )}
    </>
  );
}
