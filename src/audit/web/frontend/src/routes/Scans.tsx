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
import { cn } from "../lib/cn";
import { CLICK_THROUGH_STATES_LABEL } from "../lib/labels";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import type { ProtectedScanSummary, ScanSummary, SiteGroup } from "../api/types";
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
  TableStatus,
  TableBar,
  rowBand,
} from "../components/table/Table";
import { sortWords, type Sort, type SortKind } from "../components/table/sort";

/**
 * Reports list, one row per site. A site is a normalized seed scope, the
 * same key "compare to previous report" uses, and the server does the
 * grouping so the two can never disagree.
 *
 * A row shows one scan: the site's most recent *completed* run, the only
 * one whose numbers stand for the site. Interrupted, failed and running
 * scans never reach the row; they are listed, with every other scan, when
 * the site is expanded. Which scan the numbers come from is carried three
 * ways so no one depends on the shading: a spanning header over the group,
 * `headers` on each grouped cell so a screen reader reads the group name
 * with the value, and the help text above the table.
 *
 * Expanding a site lists all of its scans with the per-report actions
 * (All issues, Delete) the flat list used to carry.
 */
type SortKey = "site" | "scans" | "pages" | "issues" | "images" | "states" | "completed";

const SORT_KINDS: Record<SortKey, SortKind> = {
  site: "text",
  scans: "number",
  pages: "number",
  issues: "number",
  images: "number",
  states: "number",
  completed: "date",
};

const SORT_LABELS: Record<SortKey, string> = {
  site: "Site",
  scans: "Scans",
  pages: "Pages",
  issues: "Issues",
  images: "Images with text",
  states: CLICK_THROUGH_STATES_LABEL,
  completed: "Completed",
};

// Ids for the two-level header. Grouped cells name both through `headers`.
const GROUP_HEADER_ID = "reports-completed-group";
const COLUMN_HEADER_IDS = {
  pages: "reports-col-pages",
  issues: "reports-col-issues",
  images: "reports-col-images",
  states: "reports-col-states",
  completed: "reports-col-completed",
  report: "reports-col-report",
} as const;
const TOTAL_COLUMNS = 8;

/** `https://a.example/docs/` reads as `a.example/docs`; other schemes stay visible. */
export function siteLabel(siteUrl: string): string {
  return siteUrl.replace(/^https:\/\//, "").replace(/\/$/, "");
}

/** The sortable value; null sorts last in either direction. */
function sortValue(site: SiteGroup, key: SortKey): number | string | null {
  const completed = site.most_recent_completed;
  switch (key) {
    case "site":
      return siteLabel(site.site_url).toLowerCase();
    case "scans":
      return site.scan_count;
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

export default function ScansRoute() {
  const [sort, setSort] = useState<Sort<SortKey>>({ column: "completed", direction: "desc" });
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [search, setSearch] = useState("");
  // Under the "scans" prefix so every existing invalidation of the scan
  // list (create, cancel, delete) refreshes the grouped view as well.
  const { data: sites = NO_SITES, isLoading, isError } = useQuery({
    queryKey: ["scans", "sites"],
    queryFn: api.listSites,
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
              ? "Reports unavailable"
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
          title="No scans yet"
          message="Point the crawler at a URL to start auditing."
          action={
            <LinkButton to="/scans/new" variant="primary">
              <PlusCircle className="h-4 w-4" aria-hidden /> Create New Scan
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
          </TableBar>
          <TableStatus
            actions={
              // Always mounted, so the count is announced when it changes.
              <p role="status">
                {query &&
                  `${matchingSites.length} of ${sites.length} ${sites.length === 1 ? "site matches" : "sites match"} “${search.trim()}”.`}
              </p>
            }
          >
            Sorted by {SORT_LABELS[sort.column]}, {sortWords(SORT_KINDS[sort.column], sort.direction)}.
          </TableStatus>
          <TableRegion label="Public reports table" paged={sitePages}>
            <Table
              className="min-w-[56rem]"
              caption="Public reports by site. Grouped columns come from each site’s most recent completed scan."
            >
              <TableHead>
                <tr>
                  <SortHeader
                    column="site"
                    kind="text"
                    rowSpan={2}
                    wrap="words"
                    className="sticky left-0 z-[2] bg-surface-muted align-bottom"
                    {...sortProps}
                  >
                    {SORT_LABELS.site}
                  </SortHeader>
                  <SortHeader column="scans" kind="number" rowSpan={2} wrap="words" className="align-bottom" {...sortProps}>
                    {SORT_LABELS.scans}
                  </SortHeader>
                  <ColumnHeader
                    id={GROUP_HEADER_ID}
                    scope="colgroup"
                    colSpan={6}
                    className="border-l-2 border-umich-blue bg-umich-blue/10 pb-1 pt-2 text-xs text-fg-accent"
                  >
                    Most recent completed scan
                  </ColumnHeader>
                </tr>
                <tr>
                  {(["pages", "issues", "images", "states", "completed"] as const).map((column) => (
                    <SortHeader
                      key={column}
                      column={column}
                      kind={SORT_KINDS[column]}
                      id={COLUMN_HEADER_IDS[column]}
                      wrap="words"
                      className={cn("bg-umich-blue/10", column === "pages" && "border-l-2 border-umich-blue")}
                      {...sortProps}
                    >
                      {SORT_LABELS[column]}
                    </SortHeader>
                  ))}
                  <ColumnHeader id={COLUMN_HEADER_IDS.report} className="whitespace-nowrap bg-umich-blue/10">
                    Report
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
          Checking protected-report access…
        </p>
      )}

      {protectedIdentity.isReady && (
        <section className="mt-6" aria-labelledby="protected-reports-heading">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h2 id="protected-reports-heading" className="text-lg font-semibold text-fg">
                Protected reports
              </h2>
              <p className="mt-1 text-sm text-fg-muted">
                Your authorized reports only. Target locations and detailed evidence are not listed here.
              </p>
            </div>
            <LinkButton to="/scans/new?mode=login" variant="secondary">
              <PlusCircle className="h-4 w-4" aria-hidden /> New login scan
            </LinkButton>
          </div>
          {protectedReports.isFetching ? (
            <p className="text-sm text-fg-muted" aria-live="polite">
              Loading your protected reports…
            </p>
          ) : protectedScans.length === 0 ? (
            <Card className="p-5 text-sm text-fg-muted">
              No protected reports yet. Start one only after the target owner has authorized
              the scope and a least-privilege audit account is ready.
            </Card>
          ) : (
            <Card>
              {protectedPages.pages > 1 && (
                <TableBar pager={<TablePagination label="Protected reports" noun="reports" {...protectedPages} />} />
              )}
              <TableRegion label="Protected reports table" paged={protectedPages}>
                <Table className="min-w-[58rem]" caption="Your protected reports, newest activity first">
                  <TableHead>
                    <tr>
                      <ColumnHeader>Report</ColumnHeader>
                      <ColumnHeader>Status</ColumnHeader>
                      <ColumnHeader>Handling</ColumnHeader>
                      <ColumnHeader>Pages</ColumnHeader>
                      <ColumnHeader>Issue leads</ColumnHeader>
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
  const grouped = (column: keyof typeof COLUMN_HEADER_IDS) =>
    `${rowId} ${GROUP_HEADER_ID} ${COLUMN_HEADER_IDS[column]}`;
  const groupCell = "bg-umich-blue/[0.04]";
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
              <span className="block break-words font-semibold text-fg underline-offset-2 group-hover:underline" title={site.site_url}>
                <BreakableUrl text={label} />
              </span>
              <span className="block text-xs text-fg-muted">
                {site.completed_count} completed
              </span>
            </span>
          </button>
        </RowHeader>
        <Cell numeric className="text-fg">
          {site.scan_count.toLocaleString()}
        </Cell>
        {completed ? (
          <>
            <Cell numeric headers={grouped("pages")} className={cn(groupCell, "border-l-2 border-umich-blue text-fg")}>
              {completed.page_count.toLocaleString()}
            </Cell>
            <Cell numeric headers={grouped("issues")} className={groupCell}>
              <Link
                to={`/scans/${completed.id}/issues`}
                className="report-link inline-flex min-h-target items-center px-1 font-semibold"
                aria-label={`${(site.most_recent_completed_issue_count ?? 0).toLocaleString()} issues in report ${completed.id}`}
              >
                {(site.most_recent_completed_issue_count ?? 0).toLocaleString()}
              </Link>
            </Cell>
            <Cell numeric headers={grouped("images")} className={cn(groupCell, "text-fg")}>
              {completed.finding_count.toLocaleString()}
            </Cell>
            <Cell numeric headers={grouped("states")} className={cn(groupCell, "text-fg")}>
              {(completed.dom_state_count ?? 0).toLocaleString()}
            </Cell>
            <Cell
              headers={grouped("completed")}
              className={cn(groupCell, "whitespace-nowrap text-center text-xs text-fg-muted")}
              title={completed.finished_at ?? completed.started_at ?? undefined}
            >
              {relativeTime(completed.finished_at ?? completed.started_at)}
            </Cell>
            <Cell headers={grouped("report")} className={cn(groupCell, "whitespace-nowrap text-center")}>
              <LinkButton
                to={`/scans/${completed.id}`}
                variant="secondary"
                aria-label={`Open latest scan of ${label}, the most recent completed scan`}
              >
                Open latest scan
              </LinkButton>
            </Cell>
          </>
        ) : (
          <Cell
            colSpan={6}
            headers={`${rowId} ${GROUP_HEADER_ID}`}
            className={cn(groupCell, "border-l-2 border-umich-blue text-fg-muted")}
          >
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
  return (
    <Table
      className="rounded-xs border border-border bg-surface"
      captionClassName="px-2 py-2 text-left text-sm font-semibold text-fg"
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
          title={scan.seed_url}
        >
          <span className="sr-only">Open </span>scan {scan.id}
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
            aria-label={`All issues for report ${scan.id}`}
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
      <Cell><span className="font-medium text-fg">{report.protection_status.replaceAll("_", " ")}</span></Cell>
      <Cell className="text-fg-muted">{report.environment} · {report.data_classification}</Cell>
      <Cell numeric className="text-fg">{report.page_count.toLocaleString()}</Cell>
      <Cell numeric className="text-fg">{report.issue_occurrences.toLocaleString()}</Cell>
      <Cell className="text-center text-xs text-fg-muted" title={report.updated_at}>{relativeTime(report.updated_at)}</Cell>
      <Cell className="py-1 text-center">
        <LinkButton to={`/scans/${report.scan_id}/protected`} variant="ghost" aria-label={`Open protected report ${report.scan_id}`}>
          Open protected report
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
        title="Cancel the running scan before deleting it."
        className="text-fg-subtle"
        aria-label={`Delete scan ${scan.id} (disabled, scan is running)`}
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
        aria-label={`Delete scan ${scan.id}`}
        onClick={() => {
          // confirm() blocks; it's the right primitive for "are you sure".
          // Message includes the scan ID and seed URL so the user knows
          // exactly which scan they're about to remove.
          const ok = confirmDestructive(
            `Delete scan ${scan.id} (${scan.seed_url})?\n\n` +
              "This permanently removes the scan, its pages, findings, and " +
              "history. Image blobs are kept (they may be referenced by " +
              "other scans). This cannot be undone.",
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
