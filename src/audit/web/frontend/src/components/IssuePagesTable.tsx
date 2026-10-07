import { memo, useMemo, useState } from "react";
import { Link } from "react-router";
import { ScanEye } from "lucide-react";
import { TablePagination, usePagedRows } from "./TablePagination";
import {
  Cell,
  ColumnHeader,
  Row,
  RowHeader,
  SortHeader,
  Table,
  TableBar,
  TableEmpty,
  TableHead,
  TableRegion,
  TableSearch,
  TableStatus,
} from "./table/Table";
import { compareText, sortWords, type Sort, type SortKind } from "./table/sort";
import { withReturnTrail } from "./ui";
import type { IssuePage, IssueRow } from "../api/types";
import { STATUS_LABEL } from "../lib/terms";

/** The trail label for the pages view; ReportCrumb shows the same words. */
// "Pages" and not "Pages with this issue": the trail already names the
// issue right before it, so the longer label said the same thing twice.
export const ISSUE_PAGES_VIEW = "Pages";

/**
 * The in-app inspector for one page, pointed at this issue.
 *
 * ``issue`` is what makes the inspector highlight anything: without it the
 * Rendered page and DOM tabs show the page with nothing outlined. The rest is
 * the orientation the inspector's own trail and context chip read.
 */
export function issueInspectorPath({
  scanId,
  pageId,
  issueKey,
  origin,
  backTo,
}: {
  scanId: number;
  pageId: number;
  issueKey: string;
  origin: string;
  backTo: string;
}): string {
  const params = new URLSearchParams();
  params.set("issue", issueKey);
  params.set("origin", origin);
  params.set("context", issueKey);
  params.set("contextTo", `/scans/${scanId}/issues/${encodeURIComponent(issueKey)}`);
  params.set("back", backTo);
  return `/scans/${scanId}/pages/${pageId}/inspect?${params.toString()}`;
}

const STATUS_LABELS_ORDER = [
  "new",
  "reviewing",
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
] as const;

type SortColumn = "Page title" | "Page URL" | "Occurrences" | "Issue screenshots" | "Status";
export type PagesSort = Sort<SortColumn>;

/**
 * What each column sorts as (./table/sort): words open A to Z, counts open
 * with the biggest first. Status counts a page's open occurrences.
 */
const SORT_KINDS: Record<SortColumn, SortKind> = {
  "Page title": "text",
  "Page URL": "text",
  Occurrences: "number",
  "Issue screenshots": "number",
  Status: "number",
};
export const DEFAULT_PAGES_SORT: PagesSort = { column: "Occurrences", direction: "desc" };

/** What each column header says. The column keys above stay as they are. */
const COLUMN_LABEL: Record<SortColumn, string> = {
  "Page title": "Page title",
  "Page URL": "Page URL",
  Occurrences: "Occurrences",
  "Issue screenshots": "Screenshots",
  Status: "Status",
};

function describeSort(sort: PagesSort): string {
  return `${COLUMN_LABEL[sort.column]}, ${sortWords(SORT_KINDS[sort.column], sort.direction)}`;
}

/** Open work first: how many of a page's occurrences are not yet closed. */
function openCount(page: IssuePage): number {
  return (page.status_summary.new ?? 0)
    + (page.status_summary.reviewing ?? 0)
    + (page.status_summary.in_progress ?? 0);
}

function comparePages(a: IssuePage, b: IssuePage, column: SortColumn): number {
  switch (column) {
    case "Page title":
      return compareText(a.page_title ?? "", b.page_title ?? "");
    case "Page URL":
      return compareText(a.page_url, b.page_url);
    case "Occurrences":
      return a.occurrence_count - b.occurrence_count;
    case "Issue screenshots":
      return a.screenshot_hashes.length - b.screenshot_hashes.length;
    case "Status":
      return openCount(a) - openCount(b);
  }
}

/** A stable sort: ties keep the server's order. */
function sortPages(pages: IssuePage[], sort: PagesSort): IssuePage[] {
  const sign = sort.direction === "asc" ? 1 : -1;
  return pages
    .map((page, index) => ({ page, index }))
    .sort((a, b) => {
      const primary = comparePages(a.page, b.page, sort.column) * sign;
      if (primary !== 0) return primary;
      return a.index - b.index;
    })
    .map(({ page }) => page);
}

/** Whether the page's title or address contains `needle`, already trimmed and lower case. */
function matches(page: IssuePage, needle: string): boolean {
  return (page.page_title ?? "").toLowerCase().includes(needle)
    || page.page_url.toLowerCase().includes(needle);
}

/**
 * Every page an issue appears on, one page per row, with a search box
 * over title and URL and a sortable header on each fact column. It is the
 * same table whether it is read inline under the issue's evidence or on the
 * pages route the Issues table links to from its page count, so the two
 * never drift apart. Search and sort happen in the browser: the whole page
 * list is already loaded, and a keystroke should not round-trip to the
 * server.
 *
 * Like the Issues table it scrolls inside a named, focusable region at
 * narrow widths instead of pushing the document sideways.
 */
export default function IssuePagesTable({
  scanId,
  issueKey,
  row,
  pages,
  backTo,
  origin = ISSUE_PAGES_VIEW,
}: {
  scanId: number;
  issueKey: string;
  row: IssueRow;
  pages: IssuePage[];
  /** Where links out of the table return to. */
  backTo: string;
  /** The view name those links carry in their trail. */
  origin?: string;
}) {
  const isInformational = row.review_lane === "informational";
  const [sort, setSort] = useState<PagesSort>(DEFAULT_PAGES_SORT);
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();

  const visible = useMemo(
    () => sortPages(needle ? pages.filter((page) => matches(page, needle)) : pages, sort),
    [pages, needle, sort],
  );
  // A new search or sort starts the table over at page 1.
  const paged = usePagedRows(visible, { resetKey: `${needle}|${sort.column}|${sort.direction}` });
  const offset = (paged.page - 1) * paged.pageSize;
  const sortProps = { sort, onSort: setSort };

  return (
    <>
      <TableBar pager={<TablePagination label="Pages with this issue" noun="pages" {...paged} />}>
        <TableSearch label="Search pages" placeholder="Search by page title or URL" value={query} onChange={setQuery} />
      </TableBar>
      <TableStatus>
        {needle ? `${visible.length} of ${pages.length} page${pages.length === 1 ? "" : "s"} match. ` : ""}
        Sorted by {describeSort(sort)}.
      </TableStatus>
      {visible.length === 0 ? (
        <TableEmpty>
          {pages.length === 0
            ? "No pages have this issue."
            : "No pages match that search."}
        </TableEmpty>
      ) : (
        <TableRegion label="Pages table" paged={paged}>
          <Table className="min-w-[44rem]" caption={`Pages with the issue ${row.title}`}>
            <TableHead>
              <tr>
                <ColumnHeader className="w-10 whitespace-nowrap">
                  <span aria-hidden="true">#</span>
                  <span className="sr-only">Row number</span>
                </ColumnHeader>
                <SortHeader column="Page title" kind="text" {...sortProps}>
                  Page title
                </SortHeader>
                <SortHeader column="Page URL" kind="text" {...sortProps}>
                  Page URL
                </SortHeader>
                <SortHeader column="Occurrences" kind="number" {...sortProps}>
                  Occurrences
                </SortHeader>
                <SortHeader column="Issue screenshots" kind="number" {...sortProps}>
                  {COLUMN_LABEL["Issue screenshots"]}
                </SortHeader>
                {!isInformational && (
                  <SortHeader column="Status" kind="number" {...sortProps}>
                    Status
                  </SortHeader>
                )}
              </tr>
            </TableHead>
            <tbody>
              {paged.pageRows.map((page, rowIndex) => (
                <IssuePageRow
                  key={page.page_id}
                  page={page}
                  index={offset + rowIndex}
                  scanId={scanId}
                  issueKey={issueKey}
                  origin={origin}
                  backTo={backTo}
                  isInformational={isInformational}
                />
              ))}
            </tbody>
          </Table>
        </TableRegion>
      )}
    </>
  );
}

/**
 * One page the issue appears on. Memoized: a parent that re-renders for its
 * own reasons (the issue's evidence above, a query refetch) leaves the rows
 * of an unchanged page as they are.
 */
const IssuePageRow = memo(function IssuePageRow({
  page,
  index,
  scanId,
  issueKey,
  origin,
  backTo,
  isInformational,
}: {
  page: IssuePage;
  /** Position across pages: the row number, and the row stripe. */
  index: number;
  scanId: number;
  issueKey: string;
  origin: string;
  backTo: string;
  isInformational: boolean;
}) {
  const label = page.page_title?.trim() || page.page_url;
  const shots = page.screenshot_hashes.length;
  const screenshotsPath = withReturnTrail(
    `/scans/${scanId}/issues/${encodeURIComponent(issueKey)}/pages/${page.page_id}/screenshots`,
    origin,
    backTo,
  );
  return (
    <Row index={index}>
      <RowHeader className="text-center font-normal tabular-nums text-fg-muted">{index + 1}</RowHeader>
      <Cell className="min-w-[12rem] font-semibold text-fg">
        {/* The title opens the inspector with this issue outlined on the page.
            At least 44 px tall, as the shared PageLink is: a link alone in its
            cell is not in a sentence, so the SC 2.5.5 Target Size (Enhanced),
            Level AAA, inline exception does not cover it. */}
        <Link
          to={issueInspectorPath({ scanId, pageId: page.page_id, issueKey, origin, backTo })}
          className="inline-flex min-h-target items-center gap-1 text-umich-blue underline underline-offset-2"
        >
          <ScanEye className="h-5 w-5 shrink-0 self-start pt-0.5 text-fg-subtle" aria-hidden />
          <span>{page.page_title?.trim() || <span className="font-normal">Untitled</span>}</span>
          <span className="sr-only">, opens the saved copy with this issue marked</span>
        </Link>
      </Cell>
      <Cell className="min-w-[14rem] max-w-md break-all text-xs text-fg-muted">{page.page_url}</Cell>
      <Cell numeric>
        {page.occurrence_count}
      </Cell>
      <Cell className="whitespace-nowrap text-center">
        {shots > 0 ? (
          <Link to={screenshotsPath} className="inline-flex min-h-target items-center text-umich-blue underline underline-offset-2">
            {shots} screenshot{shots === 1 ? "" : "s"}
            <span className="sr-only"> of this issue on {label}</span>
          </Link>
        ) : (
          <span className="text-fg-muted">No screenshots</span>
        )}
      </Cell>
      {!isInformational && (
        <Cell className="text-center">
          <div className="flex flex-wrap gap-1">
            {STATUS_LABELS_ORDER.map((s) => {
              const n = page.status_summary[s] ?? 0;
              if (!n) return null;
              const isOpen = s === "new" || s === "reviewing" || s === "in_progress";
              return (
                <span
                  key={s}
                  className={
                    isOpen
                      ? "inline-block rounded-xs bg-sev-major-bg/15 px-1.5 py-0.5 text-2xs text-fg"
                      : // fg-muted, not fg-subtle: AAA contrast on a shaded row.
                        "inline-block rounded-xs bg-surface-muted px-1.5 py-0.5 text-2xs text-fg-muted"
                  }
                >
                  {n} {STATUS_LABEL[s]}
                </span>
              );
            })}
          </div>
        </Cell>
      )}
    </Row>
  );
});
