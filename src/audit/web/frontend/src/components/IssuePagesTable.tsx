import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink, ScanEye, Search } from "lucide-react";
import { cn } from "../lib/cn";
import { TABLE_PAGE_SIZE, TablePagination, usePagedRows } from "./TablePagination";
import { pageEvidencePath, withReturnTrail } from "./ui";
import type { IssuePage, IssueRow } from "../api/types";

/** The trail label for the pages view; ReportCrumb shows the same words. */
// "Pages" and not "Pages with this issue": the trail already names the
// issue right before it, so the longer label said the same thing twice.
export const ISSUE_PAGES_VIEW = "Pages";

/**
 * The in-app inspector for one page, pointed at this issue.
 *
 * ``issue`` is what makes the inspector highlight anything: without it the
 * Rendered page and DOM tabs show the page with nothing circled. The rest is
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

const SORT_COLUMNS = ["Page title", "Page URL", "Occurrences", "Issue screenshots", "Status"] as const;
type SortColumn = (typeof SORT_COLUMNS)[number];
type Direction = "asc" | "desc";
export type PagesSort = { column: SortColumn; direction: Direction };

const DEFAULT_DIRECTION: Record<SortColumn, Direction> = {
  "Page title": "asc",
  "Page URL": "asc",
  Occurrences: "desc",
  "Issue screenshots": "desc",
  Status: "desc",
};
export const DEFAULT_PAGES_SORT: PagesSort = { column: "Occurrences", direction: "desc" };

type Column = "#" | SortColumn | "Open live page" | "Stored evidence";

function isSortable(column: Column): column is SortColumn {
  return (SORT_COLUMNS as readonly string[]).includes(column);
}

function sortChip(sort: PagesSort): string {
  const numeric = DEFAULT_DIRECTION[sort.column] === "desc";
  if (numeric) return sort.direction === "desc" ? "high → low" : "low → high";
  return sort.direction === "asc" ? "A → Z" : "Z → A";
}

function describeSort(sort: PagesSort): string {
  const numeric = DEFAULT_DIRECTION[sort.column] === "desc";
  const how = numeric
    ? sort.direction === "desc" ? "highest first" : "lowest first"
    : sort.direction === "asc" ? "A to Z" : "Z to A";
  return `${sort.column}, ${how}`;
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
      return (a.page_title ?? "").localeCompare(b.page_title ?? "", undefined, { sensitivity: "base" });
    case "Page URL":
      return a.page_url.localeCompare(b.page_url, undefined, { sensitivity: "base" });
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

function matches(page: IssuePage, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return (page.page_title ?? "").toLowerCase().includes(needle)
    || page.page_url.toLowerCase().includes(needle);
}

/**
 * Every page an issue group appears on, one page per row, with a search box
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
  // Written only after a header is pressed; see IssueTable in Issues.tsx.
  const [announced, setAnnounced] = useState<PagesSort | null>(null);

  const columns: Column[] = [
    "#",
    "Page title",
    "Page URL",
    "Open live page",
    "Stored evidence",
    "Occurrences",
    "Issue screenshots",
    ...(isInformational ? [] : ["Status" as const]),
  ];

  const visible = useMemo(
    () => sortPages(pages.filter((page) => matches(page, query)), sort),
    [pages, query, sort],
  );
  const paged = usePagedRows(visible, { resetKey: visible.map((page) => page.page_id).join(",") });
  const offset = (paged.page - 1) * TABLE_PAGE_SIZE;

  const choose = (column: SortColumn) => {
    const next: PagesSort =
      sort.column === column
        ? { column, direction: sort.direction === "asc" ? "desc" : "asc" }
        : { column, direction: DEFAULT_DIRECTION[column] };
    setAnnounced(next);
    setSort(next);
  };

  return (
    <>
      <div className="border-b border-border bg-surface-subtle p-3">
        <div className="relative max-w-xl">
          <Search
            className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle"
            aria-hidden
          />
          <PageSearch value={query} onChange={setQuery} />
        </div>
      </div>
      <p
        role="status"
        aria-live="polite"
        className="border-b border-border bg-surface-subtle px-3 py-1.5 text-xs text-fg-muted"
      >
        {query.trim()
          ? `${visible.length} of ${pages.length} page${pages.length === 1 ? "" : "s"} match. `
          : ""}
        Sorted by {describeSort(announced ?? sort)}.
      </p>
      {visible.length === 0 ? (
        <p className="p-4 text-sm text-fg-muted">
          {pages.length === 0
            ? "No pages are currently associated with this issue."
            : "No pages match that search."}
        </p>
      ) : (
        <>
        {/* Keyboard users need focus on the overflow region to scroll the table. */}
        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
        <div role="region" aria-label="Pages table" tabIndex={0} className="overflow-x-auto focus:outline-none focus-visible:shadow-focus">
          {/* Holds the tallest page's height, so paging never moves the pager. */}
          <div {...paged.hold}>
          <table className="w-full min-w-[56rem] text-sm">
            <caption className="sr-only">Pages with the issue {row.title}</caption>
            <thead className="bg-surface-muted text-2xs text-fg-subtle">
              <tr>
                {columns.map((column) => {
                  const numeric = column === "Occurrences";
                  const cell = cn(
                    "whitespace-nowrap px-1 py-0.5 text-left font-semibold",
                    column === "#" && "w-10 px-3 py-2 text-right",
                    numeric && "text-right",
                  );
                  if (column === "#") {
                    return (
                      <th key={column} scope="col" className={cell}>
                        <span aria-hidden="true">#</span>
                        <span className="sr-only">Row number</span>
                      </th>
                    );
                  }
                  if (!isSortable(column)) {
                    return (
                      <th key={column} scope="col" className={cn(cell, "px-3 py-2")}>
                        {column}
                      </th>
                    );
                  }
                  const active = sort.column === column;
                  const Arrow = !active ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;
                  return (
                    <th
                      key={column}
                      scope="col"
                      aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                      className={cn(cell, active && "shadow-[inset_0_-3px_0_theme(colors.umich.blue)]")}
                    >
                      <button
                        type="button"
                        onClick={() => choose(column)}
                        className={cn(
                          "group inline-flex min-h-target items-center gap-1.5 rounded-xs px-2 text-2xs font-semibold hover:bg-border/50 focus-visible:outline-none focus-visible:shadow-focus",
                          active ? "text-umich-blue" : "text-fg-subtle",
                        )}
                      >
                        <span>{column}</span>
                        {active ? (
                          <span
                            key={`${sort.column}-${sort.direction}`}
                            className="inline-flex items-center gap-0.5 whitespace-nowrap rounded-full bg-umich-blue px-1.5 py-px text-[0.65rem] font-semibold normal-case tracking-normal text-white motion-safe:animate-sort-pop"
                          >
                            <Arrow className="h-3 w-3 shrink-0" aria-hidden />
                            {sortChip(sort)}
                          </span>
                        ) : (
                          <Arrow
                            className="h-3.5 w-3.5 shrink-0 opacity-40 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
                            aria-hidden
                          />
                        )}
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {paged.pageRows.map((page, rowIndex) => {
                const index = offset + rowIndex;
                const label = page.page_title?.trim() || page.page_url;
                const shots = page.screenshot_hashes.length;
                const screenshotsPath = withReturnTrail(
                  `/scans/${scanId}/issues/${encodeURIComponent(issueKey)}/pages/${page.page_id}/screenshots`,
                  origin,
                  backTo,
                );
                return (
                  <tr
                    key={page.page_id}
                    className={index % 2 === 1 ? "bg-surface-subtle" : "bg-surface"}
                  >
                    <th
                      scope="row"
                      className="px-3 py-2.5 text-right align-top font-normal tabular-nums text-fg-subtle"
                    >
                      {index + 1}
                    </th>
                    <td className="min-w-[12rem] px-3 py-2.5 align-top font-semibold text-fg">
                      {/* The title opens the inspector with this issue circled on the page. */}
                      <Link
                        to={issueInspectorPath({ scanId, pageId: page.page_id, issueKey, origin, backTo })}
                        className="inline-flex items-baseline gap-1 text-umich-blue underline underline-offset-2"
                      >
                        <ScanEye className="h-5 w-5 shrink-0 self-start pt-0.5 text-fg-subtle" aria-hidden />
                        <span>
                          {page.page_title?.trim() || <span className="font-normal">Untitled</span>}
                        </span>
                        <span className="sr-only">, opens the in-app page inspector</span>
                      </Link>
                    </td>
                    <td className="min-w-[14rem] max-w-md break-all px-3 py-2.5 align-top text-xs text-fg-muted">
                      {page.page_url}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 align-top">
                      <a
                        href={page.page_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-umich-blue underline underline-offset-2"
                      >
                        Open live page
                        <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                        <span className="sr-only">, {label}, opens in a new tab</span>
                      </a>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 align-top">
                      <Link
                        to={pageEvidencePath({ scanId, pageId: page.page_id, origin, backTo })}
                        className="text-umich-blue underline underline-offset-2"
                      >
                        Stored evidence
                        <span className="sr-only"> for {label}</span>
                      </Link>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right align-top tabular-nums">
                      {page.occurrence_count}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 align-top">
                      {shots > 0 ? (
                        <Link to={screenshotsPath} className="text-umich-blue underline underline-offset-2">
                          {shots} screenshot{shots === 1 ? "" : "s"}
                          <span className="sr-only"> of this issue on {label}</span>
                        </Link>
                      ) : (
                        <span className="text-fg-muted">None captured</span>
                      )}
                    </td>
                    {!isInformational && (
                      <td className="px-3 py-2.5 align-top">
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
                                    : "inline-block rounded-xs bg-surface-muted px-1.5 py-0.5 text-2xs text-fg-subtle"
                                }
                              >
                                {n} {s.replace(/_/g, " ")}
                              </span>
                            );
                          })}
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        </div>
        <TablePagination label="Pages with this issue" noun="pages" {...paged} />
        </>
      )}
    </>
  );
}

/** Keep keystrokes synchronous; the filter is applied on a short debounce. */
function PageSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [draft, setDraft] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <input
      type="search"
      aria-label="Search pages"
      value={draft}
      placeholder="Search page title or URL"
      onChange={(event) => {
        const next = event.target.value;
        setDraft(next);
        clearTimeout(timer.current);
        timer.current = setTimeout(() => onChange(next), 200);
      }}
      className="min-h-target w-full rounded-xs border border-border-strong bg-surface py-2 pl-10 pr-3 text-base text-fg focus:border-umich-blue focus:outline-none focus-visible:shadow-focus"
    />
  );
}
