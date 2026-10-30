import { Link, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, PlusCircle, Trash2 } from "lucide-react";
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
import { RULE_CHECK_HELP } from "../lib/labels";
import { ruleChecksText } from "../lib/terms";
import { liveSearchParams } from "../lib/liveSearchParams";
import { useRememberedParams } from "../hooks/useRememberedParams";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import type { ProtectedScanStatus, ProtectedScanSummary, ScanSummary, SiteGroup } from "../api/types";
import { confirmDestructive } from "../hooks/usePreferences";
import BreakableUrl from "../components/BreakableUrl";
import LastScannedSite from "../components/LastScannedSite";
import ScanAgainLink from "../components/ScanAgainLink";
import LinkMenu from "../components/LinkMenu";
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
} from "../components/table/Table";
import { parseSortParam, sortParam, sortWords, type Sort, type SortKind } from "../components/table/sort";

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
 * Expanding a site lists all of its scans, each a link to its report, with
 * the per-report actions (Compare with, Delete) the flat list used to carry.
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
 * - The caption (technique H39, the table's accessible name) says where a
 *   site row's numbers come from. A sentence over the table said it too,
 *   and was removed after user testing (2026-10-28): testers read it as
 *   noise, and "2 scans, 1 completed" under each site name already shows
 *   that a row is one scan of several. A visible caption was not the
 *   answer either: it scrolls sideways with the table and was cut off at
 *   320 pixels (WCAG 2.2 SC 1.4.10 Reflow, Level AA).
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
 *   in the row header, which adds one row per scan under it, not a
 *   `treegrid` and not columns that open and close. Hidden columns change a
 *   table's shape under a screen reader, and `treegrid` needs grid keyboard
 *   handling that screen readers support unevenly. See Adrian Roselli,
 *   "Table with Expando Rows"
 *   (https://adrianroselli.com/2019/09/table-with-expando-rows.html).
 * - A site's scans are rows of this table, under its own column headers,
 *   not a second table nested in one wide cell. The nested table had its
 *   own header row and columns that did not line up with the ones above
 *   it, so testers (2026-10-28) could not read a scan's Pages under the
 *   site's Pages; they asked for the columns aligned and the second header
 *   row gone. Shared headers give both: each scan cell is announced with
 *   the column header above it (technique H63; SC 1.3.1 Info and
 *   Relationships, Level A), with no headers to repeat. That is why the
 *   date column is "Scanned", not "Completed": it now heads a stopped or
 *   running scan too. The scan rows still look like the separate box they
 *   were (`scanCardCell`): framed, raised on the open site's shade and
 *   indented under the site's name, so they read as belonging to it.
 * - Thin lines between columns (Table's `ruled`), asked for in the same
 *   test, so a number can be followed up to its header across a site and
 *   its scans.
 * - A scan's status shows only when it is not Complete ("Stopped",
 *   "Failed", "Scanning"), beside its report number. A Status column that
 *   read "Complete" on nearly every row was noise to testers; the
 *   exception is what needs the eye (W3C COGA, "Making Content Usable":
 *   only what helps the task).
 * - Columns: the site that names the row, when its latest completed scan
 *   finished, its Pages, Occurrences and Kinds of issues, the Rule check
 *   it ran, then Actions. Occurrences counts every place a problem
 *   appears; Kinds of issues counts the rows of that report's Issues
 *   table. They are the words and the order the Issues page summary uses
 *   (ReportSummary), so the list and the report name the same numbers the
 *   same way (SC 3.2.4 Consistent Identification, Level AA). The places
 *   lead: they are the number people mean when they ask how much was
 *   found. History: these columns were "Issues" (the rows) and
 *   "Occurrences" (the places) until 2026-10-26, then "Issues" (the
 *   places) and "Kinds of issues" (the rows). On 2026-10-28 user testing
 *   with Siteimprove users, who know Siteimprove's "issues" and
 *   "occurrences", led the developer to bring back "Occurrences" for the
 *   places and keep "Kinds of issues" for the rows. See
 *   docs/plain-language.md, "Why "occurrence" and "kind of issue"".
 * - Rule check says which rule checks tested pages in that scan: "axe",
 *   "Alfa", "axe and Alfa" or "None". Testers who use Siteimprove asked
 *   (2026-10-28) whether a report came from axe or from Siteimprove, so
 *   the header's hint names who makes each tool (RULE_CHECK_HELP). It
 *   counts what ran, not what was chosen: a check that never reached a
 *   page is not listed. Just before Actions, after the numbers it
 *   qualifies; the Issues table names the check for each kind of issue.
 * - The Occurrences and Kinds of issues counts are plain numbers, in the
 *   site row as in its scan rows. The Occurrences count was a link into
 *   the report, "476 occurrences", until the developer removed it
 *   (2026-10-30): it opened the same report as "Open latest scan" in the
 *   same row, two controls for one job (W3C COGA, "Making Content Usable",
 *   https://www.w3.org/TR/coga-usable/: one way to do one thing,
 *   paraphrased); its word repeated the column header in every cell; and
 *   it made the site row's numbers look unlike its scan rows' (SC 3.2.4
 *   Consistent Identification, Level AA). The header names the number.
 * - "Images with text" and "Page states opened by clicking" were columns
 *   here and were removed (Oct 2026): the first counted every image with
 *   text, fine alt text or not, and read like a second count of problems;
 *   the second measured how far the scan reached, where a 0 cannot say
 *   whether clicking was off or there was nothing to click. Both are about
 *   how the scan ran, not how the site is doing, and the report itself
 *   still shows them (Issues page summary, ReportSummary). Fewer columns
 *   also means less sideways scrolling on a narrow screen (W3C COGA,
 *   "Making Content Usable", https://www.w3.org/TR/coga-usable/: only what
 *   helps the task).
 * - A site's scan rows fill the same Occurrences and Kinds of issues columns,
 *   so a site's past scans can be compared by the same numbers. They are
 *   fetched when the scans are shown (one request per
 *   completed scan, `/api/scans/{id}/issue-counts`), not with the site
 *   list, because counting builds the issue list and the site list is
 *   fetched every few seconds while a scan runs. A scan that did not
 *   finish says "Not counted": its counts would be partial, and the site
 *   row uses only completed scans for the same reason.
 * - Column order: Actions stays last, the usual place for a row's
 *   actions: the row is read (by eye or, cell by cell, by a screen reader)
 *   as "this site, as of then, with these results", and only then offers
 *   what to do with it. Opening the report was considered as the second
 *   column; that split the site from its date and numbers. The Site
 *   column is sticky, so the row keeps its name when a narrow screen
 *   scrolls the table sideways to Actions.
 * - Actions shows both of a site's actions as links, side by side: "Open
 *   latest scan", then "Scan again". Both are always visible and one click
 *   away, laid out side by side as the scan rows' actions are, so the
 *   site rows and scan rows share one pattern (W3C COGA: the same
 *   pattern for the same kind of thing). Stacking them was built and set
 *   aside for this.
 * - Side by side costs width. The dropped columns once left room for two
 *   links, but the Rule check column and the longer word "Occurrences"
 *   took it back: at 1280 pixels with the sidebar open the table scrolls
 *   sideways (the developer measured about 113 pixels), which the
 *   developer accepted (2026-10-28). Sideways scrolling is allowed here:
 *   SC 1.4.10 Reflow (Level AA) excepts content that needs
 *   two-dimensional layout, and its Understanding document names data
 *   tables as such content (paraphrased). The Site column is sticky, so a
 *   row keeps its name while the table scrolls.
 * - Comparing starts from a scan row: each completed scan row of an open
 *   site has "Compare with", beside "Delete" (ScanRow).
 *   The developer chose this place (2026-10-29), so any report can be
 *   compared with any other of its site in one step, without opening a
 *   report first; a "Compare reports" link on the site row was built the
 *   day before and dropped. "Compare with" opens a short list of the
 *   site's other completed reports, "Report #20" and so on; each opens
 *   Compare reports for the pair, side by side (routes/CompareReports.tsx):
 *   the newer report in the address, so in the first panel, and the older
 *   as `compare_to`, in the second. Always that order, so the same pair has
 *   one address whichever row it was chosen from, and it is the order What
 *   changed requires too (the baseline must be the earlier report,
 *   src/audit/web/comparison.py). It is a
 *   button that shows links, not a select that goes somewhere when a value
 *   is chosen (SC 3.2.2 On Input, Level A); LinkMenu says how it opens and
 *   closes. It shows only on a completed scan with at least one other
 *   completed scan in the site: a disabled control would be one that does
 *   nothing. The site's completed scans are its public ones (sites.py),
 *   the ones the comparison accepts.
 *   A row "Actions" dropdown holding the two links was built first and
 *   removed (Oct 2026): it put opening a report, this screen's main task,
 *   one click further away and hid "Scan again" until opened (W3C COGA:
 *   make the main task easy to find); its button, "Actions", named no verb
 *   or object (docs/plain-language.md rule 8); and it closed on scroll,
 *   which caught screen-magnifier users who pan by scrolling. "Compare
 *   with" is a dropdown again, but it holds one task and names it, the
 *   main links stay outside it, and it never closes on scroll. Leaving
 *   "Scan again" to the Issues page alone was also tried; the request was
 *   to rescan from this list, and the same link with the same name on both
 *   screens is consistent (SC 3.2.4). The "Actions" column header is a
 *   label, not a control.
 * - Both are links, styled as links, because they go to a page; a button
 *   acts on this one. Quiet links rather than an outlined button in every
 *   row, which outweighed the numbers. Each accessible name starts with
 *   its visible words (WCAG 2.2 SC 2.5.3 Label in Name, Level A: "the name
 *   contains the text that is presented visually"), then screen-reader-only
 *   text that names the site (technique C7), not an `aria-label`, so the
 *   words are real text (AGENTS.md, Interface language rule 8).
 * - A site with no completed scan has nothing to open, so it shows only
 *   "Scan again", from its latest scan.
 */
type SortKey = "site" | "completed" | "pages" | "issues" | "kinds" | "checks";

const SORT_COLUMNS = ["site", "completed", "pages", "issues", "kinds", "checks"] as const satisfies readonly SortKey[];
const DEFAULT_SORT: Sort<SortKey> = { column: "completed", direction: "desc" };

const SORT_KINDS: Record<SortKey, SortKind> = {
  site: "text",
  pages: "number",
  issues: "number",
  kinds: "number",
  checks: "text",
  completed: "date",
};

const SORT_LABELS: Record<SortKey, string> = {
  site: "Site",
  pages: "Pages",
  // The key stays "issues" for saved `?sort=issues_desc` links; the column
  // it sorts counts occurrences (see "Columns" above).
  issues: "Occurrences",
  kinds: "Kinds of issues",
  checks: "Rule check",
  completed: "Scanned",
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
      return site.most_recent_completed_occurrence_count;
    case "kinds":
      return site.most_recent_completed_issue_count;
    case "checks":
      return completed?.rule_checks ? ruleChecksText(completed.rule_checks).toLowerCase() : null;
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

/** The view parameters Reports keeps for the tab (see ScansRoute). */
const REMEMBERED_VIEW = ["open", "sort"] as const;

/** How often Reports refreshes while a scan is running. */
const RUNNING_REFRESH_MS = 5_000;

export default function ScansRoute() {
  // The view lives in the URL, not in component state: the order
  // (`?sort=`), the search (`?q=`), the sites opened (`?open=`, one per
  // site) and the page (`?page=`, usePagedRows). Going to a report and
  // pressing Back used to bring the table back sorted by date, unsearched
  // and with every site closed, so the reader had to find their place
  // again: a cost that falls hardest on keyboard and screen reader users,
  // who find it by moving through the rows (W3C COGA, "Making Content
  // Usable", https://www.w3.org/TR/coga-usable/: do not make people redo
  // steps). Every change replaces the history entry rather than adding
  // one, so Back leaves the page instead of undoing a sort or a click; and
  // a copied link opens the same view. The Issues table keeps its view the
  // same way.
  //
  // The sites opened and the order are also remembered for the tab, so
  // coming back by the navigation's "Reports", which carries no view,
  // finds them as they were (useRememberedParams says why). Not the search:
  // arriving at Reports from the navigation, the reader expects every site,
  // and a remembered search would hide some without being asked. Not the
  // page either: which sites are on it depends on the search.
  useRememberedParams("axcess-reports-view", REMEMBERED_VIEW);
  const [params, setParams] = useSearchParams();
  const rawSort = params.get("sort");
  const sort = useMemo(() => parseSortParam(rawSort, SORT_COLUMNS) ?? DEFAULT_SORT, [rawSort]);
  const search = params.get("q") ?? "";
  const openKey = params.getAll("open").join("\n");
  const expanded = useMemo<ReadonlySet<string>>(() => new Set(openKey ? openKey.split("\n") : []), [openKey]);
  // Against the live query string, as on Issues: the search publishes on a
  // debounce, so a snapshot taken at render could drop a pending keystroke
  // or a site just opened (liveSearchParams says why `previous` cannot).
  const updateParams = useCallback(
    (change: (next: URLSearchParams) => void) =>
      setParams(
        () => {
          const next = liveSearchParams();
          change(next);
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );
  const setSort = (next: Sort<SortKey>) =>
    updateParams((p) => {
      if (next.column === DEFAULT_SORT.column && next.direction === DEFAULT_SORT.direction) p.delete("sort");
      else p.set("sort", sortParam(next));
    });
  const setSearch = (next: string) =>
    updateParams((p) => {
      if (next) p.set("q", next);
      else p.delete("q");
    });
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
  const toggleSite = useCallback(
    (siteUrl: string) =>
      updateParams((p) => {
        const open = p.getAll("open");
        p.delete("open");
        const next = open.includes(siteUrl) ? open.filter((url) => url !== siteUrl) : [...open, siteUrl];
        for (const url of next) p.append("open", url);
      }),
    [updateParams],
  );
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
          <TableRegion label="Public reports table">
            <Table
              ruled
              className="min-w-[48rem]"
              caption="Public reports by site. A site’s row shows its most recent completed scan. Open a site to list each of its scans under it."
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
                  {(["completed", "pages", "issues", "kinds", "checks"] as const).map((column) => (
                    <SortHeader
                      key={column}
                      column={column}
                      kind={SORT_KINDS[column]}
                      wrap="words"
                      className="align-bottom"
                      hint={column === "checks" ? RULE_CHECK_HELP : undefined}
                      {...sortProps}
                    >
                      {SORT_LABELS[column]}
                    </SortHeader>
                  ))}
                  <ColumnHeader className="whitespace-nowrap px-3 py-1.5 align-bottom">
                    {/* The height of a sort button, words at its foot like theirs,
                        so its label lines up with them. */}
                    <span className="inline-flex min-h-target items-end px-1 pb-1.5">Actions</span>
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
              <TableRegion label="Sign-in scans table">
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
 * One site's summary row, plus a row per scan when expanded. The scan rows
 * sit under the table's own column headers (see "A site's scans are rows of
 * this table" in the comment on this route). Memoized: expanding one site
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
  const scanRowId = (scan: ScanSummary) => `${rowId}-scan-${scan.id}`;
  // Newest first, as the scan rows are: what "Compare with" offers.
  const completedScans = site.scans.filter((scan) => scan.status === "completed");
  return (
    <>
      {/* An open site takes the shaded stripe whatever its place, so its
          scan rows' white box stands out from it on every row. */}
      <Row index={index} className={cn(expanded && OPEN_SITE_SHADE)}>
        <RowHeader id={rowId} sticky className="min-w-52 max-w-xs py-1 font-normal">
          {/* The site's name toggles its scans too, not only the chevron:
              the whole block is one button. Its name starts with what it
              does and then reads the visible text, so a voice-control user
              can say what they see (SC 2.5.3). */}
          {/* eslint-disable-next-line react/forbid-elements -- Keep: the whole row header is the disclosure button (site name and chevron) */}
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={expanded ? site.scans.map(scanRowId).join(" ") : undefined}
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
            <Cell numeric className="text-fg">
              {(site.most_recent_completed_occurrence_count ?? 0).toLocaleString()}
            </Cell>
            <Cell numeric className="text-fg">
              {(site.most_recent_completed_issue_count ?? 0).toLocaleString()}
            </Cell>
            <RuleChecksCell scan={completed} />
            <Cell className="whitespace-nowrap">
              {/* Both actions shown side by side, as in the scan rows: see
                  "Actions" in the comment above. */}
              <div className="flex items-center justify-center gap-2">
                <Link
                  to={`/scans/${completed.id}`}
                  className="report-link inline-flex min-h-target items-center px-1 font-semibold"
                >
                  Open latest scan
                  <span className="sr-only"> of {label}, the most recent completed scan</span>
                </Link>
                <ScanAgainLink scanId={completed.id} site={label} look="link" />
              </div>
            </Cell>
          </>
        ) : (
          <>
            <Cell colSpan={5} className="text-fg-muted">
              No completed scan yet. Expand the site to open its other scans.
            </Cell>
            <Cell className="whitespace-nowrap">
              <ScanAgainLink scanId={site.most_recent.id} site={label} look="link" />
            </Cell>
          </>
        )}
      </Row>
      {expanded &&
        site.scans.map((scan, position) => (
          <ScanRow
            key={scan.id}
            id={scanRowId(scan)}
            scan={scan}
            completedScans={completedScans}
            first={position === 0}
            last={position === site.scans.length - 1}
          />
        ))}
    </>
  );
});

/** The stripe an open site and its scan rows share. */
const OPEN_SITE_SHADE = "bg-surface-subtle";

/**
 * One cell's share of the box drawn around a site's scan rows, so the rows
 * keep the look of the separate, framed list they were (see "A site's scans
 * are rows of this table" in the comment on this route) while their cells
 * stay in the table's columns.
 *
 * A box cannot wrap table rows, so each cell paints its piece in a
 * `::before` layer behind its content: white, with the frame's edge on the
 * sides it touches, rounded at the box's four corners, and inset from the
 * table's edges so the open site's shade shows round it: 60px on the left,
 * so the box starts under the site's name like a nested list; 16px on the
 * right and at the foot; 8px at the top. The left inset was 16px, the same
 * as the right, until user testing (2026-10-29) asked for the box to sit
 * further in, so it reads as the site's own (W3C COGA, "Making Content
 * Usable": group related content). Only the box moves: its cells stay in
 * the table's columns, so the numbers still line up under the site's. A line on the right of each piece is
 * the column line inside the box (Table's `ruled` draws it outside); a line
 * on top of each later row parts one scan from the next. The first and last
 * rows take the inset in extra padding, so their content stays centred in
 * the white part.
 *
 * The cell becomes a stacking context (`isolate`, or the sticky header's own
 * `z-index`) so the layer's `-z-10` puts it over the cell's background and
 * under its content.
 */
function scanCardCell({ first, last, edge }: { first: boolean; last: boolean; edge?: "start" | "end" }): string {
  return cn(
    "before:absolute before:-z-10 before:border-border before:bg-surface before:content-['']",
    edge === "start" ? "before:left-[3.75rem] before:border-l" : "before:left-0",
    edge === "end" ? "before:right-4" : "before:right-0",
    "before:border-r",
    first ? "before:top-2 pt-[1.375rem]" : "before:top-0",
    "before:border-t",
    last ? "before:bottom-4 before:border-b before:shadow-sm pb-[1.875rem]" : "before:bottom-0",
    first && edge === "start" && "before:rounded-tl-xs",
    first && edge === "end" && "before:rounded-tr-xs",
    last && edge === "start" && "before:rounded-bl-xs",
    last && edge === "end" && "before:rounded-br-xs",
    edge !== "start" && "relative isolate",
  );
}

/**
 * One scan of an open site, as a row of the reports table. Pulled out so the
 * delete mutation's loading state is local to the row that owns it.
 */
function ScanRow({
  id,
  scan,
  completedScans,
  first,
  last,
}: {
  id: string;
  scan: ScanSummary;
  /** The site's completed scans, newest first. */
  completedScans: readonly ScanSummary[];
  first: boolean;
  last: boolean;
}) {
  const piece = (edge?: "start" | "end") => scanCardCell({ first, last, edge });
  // "Compare with" on a completed scan, with every other completed scan of
  // the site: see "Comparing starts from a scan row" in the comment on this
  // route.
  const others =
    scan.status === "completed" ? completedScans.filter((other) => other.id !== scan.id) : [];
  return (
    // The open site's shade, and no rule above: it reads as part of the site row.
    <tr id={id} className={OPEN_SITE_SHADE}>
      {/* Indented into the box, which starts under the site's name (see
          scanCardCell). "Report #" keeps the 44px it had inside the box's
          left edge before the box moved in, so the whole block shifts
          right rather than the padding shrinking (the developer's
          correction, 2026-10-29). The rows read as the site's own (W3C
          COGA, "Making Content Usable": group related content).

          "Report #N" is the one way into a scan's report. A completed scan
          goes straight to its Issues page; any other goes to its scan page,
          which says why it did not finish and offers "Review what the scan
          found" when pages were saved (ScanDetail). An "All issues" link
          sat in Actions until user testing (2026-10-29): for a completed
          scan it opened the same page as this link, two controls for one
          job (W3C COGA, "Making Content Usable": one way to do one thing).
          The visible words stay "Report #N", the place it goes, as an
          image is "Image #12" (docs/plain-language.md rule 8); "Open" is
          screen-reader-only. Shown, "Open" would be repeated down the
          column and read with every cell of the row, since this is the
          row's header. */}
      <RowHeader
        sticky
        className={cn("whitespace-nowrap py-1 pl-[6.25rem] text-xs font-normal tabular-nums text-fg-muted", piece("start"))}
      >
        <Link
          to={scan.status === "completed" ? `/scans/${scan.id}/issues` : `/scans/${scan.id}`}
          className="report-link inline-flex min-h-target items-center px-1 font-semibold"
          title={withoutUserinfo(scan.seed_url)}
        >
          <span className="sr-only">Open </span>Report #{scan.id}
        </Link>
        {/* Only a scan that did not complete says so: see "A scan's status"
            in the comment on this route. A word, not a colour (SC 1.4.1). */}
        {scan.status !== "completed" && (
          <span className="ml-2 font-sans">
            <ScanStatusBadge value={scan.status} />
          </span>
        )}
      </RowHeader>
      <Cell
        className={cn("whitespace-nowrap text-center text-xs text-fg-muted", piece())}
        title={scan.finished_at ?? scan.started_at ?? undefined}
      >
        {relativeTime(scan.finished_at ?? scan.started_at)}
      </Cell>
      <Cell numeric className={cn("text-fg", piece())}>
        {scan.page_count.toLocaleString()}
      </Cell>
      <ScanCountCells scan={scan} className={piece()} />
      <RuleChecksCell scan={scan} className={piece()} />
      {/* While "Compare with" is open, its cell rises over the rows after
          it: each cell here is its own layer (`isolate`, for the box drawn
          behind it), so a later row would otherwise paint over the list.
          Still under the top bar (z-20). */}
      <Cell className={cn("whitespace-nowrap py-1 has-[[data-menu-open]]:z-10", piece("end"))}>
        {/* Default `md` size (44px tall): destructive controls in
            particular must be a real target (SC 2.5.5). In reading order:
            compare this report, then delete it. */}
        <div className="flex items-center justify-center gap-2">
          {others.length > 0 && (
            <LinkMenu
              label="Compare with"
              labelContext={` another report, for Report #${scan.id}`}
              intro={`Compare Report #${scan.id} with:`}
              items={others.map((other) => {
                // Report ids increase with creation, so the higher id is the
                // newer report: it goes in the address (the first panel),
                // the older one is `compare_to` (the second).
                const [newer, older] = other.id > scan.id ? [other.id, scan.id] : [scan.id, other.id];
                return {
                  key: String(other.id),
                  to: `/scans/${newer}/compare?compare_to=${older}`,
                  label: `Report #${other.id}`,
                  context: ` (compare with Report #${scan.id})`,
                };
              })}
            />
          )}
          <DeleteScanButton scan={scan} />
        </div>
      </Cell>
    </tr>
  );
}

/**
 * Which rule checks tested pages in a scan: "axe", "Alfa", "axe and Alfa",
 * or "None"; "Not recorded" when the scan did not record it. See "Rule
 * check" in the comment on this route.
 */
function RuleChecksCell({ scan, className }: { scan: ScanSummary; className?: string }) {
  const checks = scan.rule_checks;
  return (
    <Cell className={cn("whitespace-nowrap text-center", checks?.length ? "text-fg" : "text-fg-muted", className)}>
      {checks ? ruleChecksText(checks) : "Not recorded"}
    </Cell>
  );
}

/**
 * Occurrences and Kinds of issues for one scan row of an open site, fetched
 * when the rows are shown (see "A site's scan rows" in the comment on this
 * route). Only a completed scan is counted; the others say "Not counted",
 * since the status beside their report number already says why. While a count loads,
 * the cells say "Counting" rather than showing an empty cell or a 0, which
 * would read as a result.
 */
function ScanCountCells({ scan, className }: { scan: ScanSummary; className?: string }) {
  const completed = scan.status === "completed";
  const counts = useQuery({
    queryKey: ["scans", "issue-counts", scan.id],
    queryFn: () => api.getScanIssueCounts(scan.id),
    enabled: completed,
    // A completed report's counts change only if its evidence is rebuilt.
    staleTime: 5 * 60 * 1000,
  });
  if (!completed || counts.isError) {
    return (
      <>
        <Cell className={cn("whitespace-nowrap text-center text-fg-muted", className)}>Not counted</Cell>
        <Cell className={cn("whitespace-nowrap text-center text-fg-muted", className)}>Not counted</Cell>
      </>
    );
  }
  if (!counts.data) {
    return (
      <>
        <Cell className={cn("whitespace-nowrap text-center text-fg-muted", className)}>Counting</Cell>
        <Cell className={cn("whitespace-nowrap text-center text-fg-muted", className)}>Counting</Cell>
      </>
    );
  }
  return (
    <>
      <Cell numeric className={cn("text-fg", className)}>
        {counts.data.occurrence_count.toLocaleString()}
      </Cell>
      <Cell numeric className={cn("text-fg", className)}>
        {counts.data.issue_count.toLocaleString()}
      </Cell>
    </>
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
