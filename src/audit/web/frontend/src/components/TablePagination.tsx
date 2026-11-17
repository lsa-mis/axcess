import { useEffect, useId, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./ui";
import { TableBar, TableFoot } from "./table/Table";
import { useTablePageSize } from "../hooks/usePreferences";

/*
 * Every table in the app shows at most Settings > Rows per page rows at a
 * time (10 by default). A long table was one long scroll: "Pages with this
 * issue type" alone could list 1,200 pages, and the reader lost the column
 * headers and their place in it.
 */

/**
 * The rows of `rows` on the current page, and the page state for
 * `TablePagination`.
 *
 * The page lives in the URL (`?page=`, or `param` when a view has more than
 * one table), so back, reload and a trail link that returns to the list all
 * land on the same page. `local` keeps it in component state instead, for a
 * view that draws one table per group (a URL parameter per group would pile
 * up in the address). It returns to page 1 when `resetKey` changes (the
 * table's filters or sort), and a page past the end shows the last page.
 */
export function usePagedRows<T>(
  rows: readonly T[],
  {
    param = "page",
    resetKey = "",
    local = false,
  }: { param?: string; resetKey?: string; local?: boolean } = {},
): {
  pageRows: T[];
  page: number;
  pages: number;
  total: number;
  setPage: (page: number) => void;
  /** Rows per page, from Settings; row `i` on this page is number `(page - 1) * pageSize + i + 1`. */
  pageSize: number;
  /** DOM id of this table's pager, unique even when a view draws the same table twice. */
  pagerId: string;
} {
  const [params, setParams] = useSearchParams();
  const pageSize = useTablePageSize();
  const pagerId = `pager-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const [localPage, setLocalPage] = useState(1);
  // The row set the current page belongs to. When the rows change because a
  // filter or the sort did, the table is on page 1 in that same render, not
  // one render later with the new rows briefly shown on the old page. Rows
  // arriving for the first time are not a change: a link or reload that
  // names a page keeps it while the table loads.
  const [pageFor, setPageFor] = useState(resetKey);
  const [restart, setRestart] = useState(false);
  if (pageFor !== resetKey) {
    setPageFor(resetKey);
    if (pageFor !== "") {
      setRestart(true);
      if (local) setLocalPage(1);
    }
  }
  // Clears the URL's page once the render above has already shown page 1.
  useEffect(() => {
    if (!restart) return;
    setRestart(false);
    if (local || !params.get(param)) return;
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        updated.delete(param);
        return updated;
      },
      { replace: true },
    );
  }, [restart, local, param, params, setParams]);

  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const requested = restart ? 1 : local ? localPage : Number(params.get(param) ?? "1");
  const page = Math.min(Math.max(1, Number.isFinite(requested) ? Math.floor(requested) : 1), pages);

  const setPage = (next: number) => {
    if (local) {
      setLocalPage(next);
      return;
    }
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        if (next <= 1) updated.delete(param);
        else updated.set(param, String(next));
        return updated;
      },
      { replace: true },
    );
  };

  // A short last page leaves the table short. From 2026-09-23 to 2026-10-30
  // the table kept the height of its tallest page, so turning to a short last
  // page would not pull the pager up the screen. The pager has since moved
  // into the bar above the table (TableBar), where the table's height cannot
  // move it, so all the hold still did was leave a block of empty rows under
  // the last one, which read as a page that had failed to load (developer
  // report, Reports page 2 of 2). What sits under a table moving up after a
  // page turn is ordinary, and the reader asked for the change.

  const start = (page - 1) * pageSize;
  return {
    pageRows: rows.slice(start, start + pageSize),
    page,
    pages,
    total,
    setPage,
    pageSize,
    pagerId,
  };
}

/**
 * The page buttons to show: every page when there are few, otherwise the
 * first, the last, and the current page with its neighbours, with a gap
 * (`null`) wherever pages are skipped.
 */
export function pageItems(page: number, pages: number): (number | null)[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1);
  const start = Math.max(2, Math.min(page - 1, pages - 4));
  const end = Math.min(pages - 1, Math.max(page + 1, 5));
  const items: (number | null)[] = [1];
  if (start > 2) items.push(null);
  for (let n = start; n <= end; n += 1) items.push(n);
  if (end < pages - 1) items.push(null);
  items.push(pages);
  return items;
}

/**
 * Previous and Next are arrows only; their names say what they do ("Previous
 * page of issues"). At either end the arrow is ``aria-disabled`` rather than
 * ``disabled``: a native disabled button drops keyboard focus to the page
 * the moment the reader reaches page 1, while this keeps focus where it was
 * and still tells assistive technology the control does nothing. It has to
 * *look* unavailable too, which the shared Button does not do for
 * ``aria-disabled``, so the pager adds that here.
 */
const ARROW =
  "min-w-target justify-center px-0 aria-disabled:cursor-not-allowed aria-disabled:border-border aria-disabled:bg-surface-muted aria-disabled:text-fg-subtle aria-disabled:opacity-60 aria-disabled:shadow-none aria-disabled:hover:border-border aria-disabled:hover:bg-surface-muted aria-disabled:active:translate-y-0";

/** The props of `TablePagination`, below; `PagedTable` takes them less `place`. */
export type TablePaginationProps = {
  /** The table's name, for the controls' accessible names ("Issues"). */
  label: string;
  /** What a row is, plural ("issue types", "pages"). */
  noun: string;
  page: number;
  pages: number;
  total: number;
  setPage: (page: number) => void;
  pageSize: number;
  pagerId: string;
  /** Hold every control while a server page is loading. */
  disabled?: boolean;
  /**
   * `"top"` in the table's top bar (`TableBar`); `"end"` under its last
   * row, in a `TableFoot` this draws. The top pager must be on the page
   * too: the end pager sends focus to it after a page turn.
   */
  place?: "top" | "end";
};

/**
 * The pager in a table's top bar (`TableBar` in ./table/Table), and again
 * under its last row (`place="end"`, below): a previous
 * arrow, a button per page (with gaps once there are many), a next arrow,
 * and where you are in words. It sits above the rows, so a reader learns
 * the list continues before reading it, and the arrows stay in place as
 * pages of different heights come and go. Rendered only when there is more
 * than one page. The numbered buttons show at a glance that
 * the list continues and how far; the current one is filled and carries
 * `aria-current`. The status line is announced politely, so a screen
 * reader hears the new range after a page turn.
 *
 * `place="end"` draws the same pager again under the last row, in its own
 * bar (`TableFoot`). A page of ten rows with long web addresses is several
 * screens tall, and a reader who had read to row ten had to scroll back up
 * to turn the page, just when they wanted to (developer report, Pages
 * visited, 2026-11-13). It is the same control, in the same order and with
 * the same words as the top one, so it reads as one pager shown twice, not
 * a second way to do something (SC 3.2.4 Consistent Identification, Level
 * AA). What keeps two copies from getting in each other's way:
 *
 * - Only the top pager announces the range. The end pager shows the same
 *   words but is not a live region, so a page turn is read once, not twice
 *   (SC 4.1.3 Status Messages, Level AA).
 * - Each is a navigation landmark, so their names differ ("Issues: page
 *   controls" and "Issues: page controls under the table"); two landmarks
 *   of one kind need different names to be told apart in a screen
 *   reader's list of landmarks (WAI-ARIA Authoring Practices, "Landmark
 *   Regions", paraphrased: https://www.w3.org/WAI/ARIA/apg/practices/landmark-regions/).
 * - A page turn from the end pager moves focus to the top pager. The new
 *   rows start at the top; leaving focus at the bottom would leave the
 *   reader past them, on a page they have not read. Focus on the top
 *   pager scrolls it into view under the sticky top bar (the page's
 *   scroll-padding-top, styles.css), so the new range and the first rows
 *   are what a reader sees next, and a screen reader hears the range from
 *   there (SC 2.4.3 Focus Order, Level A; SC 2.4.11 Focus Not Obscured
 *   (Minimum), Level AA).
 *
 * Rejected: a pager that sticks to the screen while the table scrolls. A
 * second sticky bar would cover focused rows under the 72 px top bar (SC
 * 2.4.11), and at 320 px or 400% zoom the bar wraps to several lines and
 * would fill most of the screen (SC 1.4.10 Reflow, Level AA). The app
 * already dropped a second sticky bar on narrow screens (styles.css).
 *
 * Screens do not draw this themselves: `PagedTable`, below, draws the top
 * pager and the end pager as one pair.
 */
export function TablePagination({
  label,
  noun,
  page,
  pages,
  total,
  setPage,
  pageSize,
  pagerId,
  disabled = false,
  place = "top",
}: TablePaginationProps) {
  if (pages <= 1) return null;
  const end = place === "end";
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const name = label.toLowerCase();
  const go = (next: number) => {
    if (disabled || next < 1 || next > pages || next === page) return;
    setPage(next);
    // The top pager stays mounted across a page turn, so it can take focus
    // now; why it does is in the comment above this component.
    if (end) document.getElementById(pagerId)?.focus();
  };
  const where = (
    <>
      Showing {first.toLocaleString()}–{last.toLocaleString()} of {total.toLocaleString()} {noun} · Page{" "}
      {page} of {pages}
    </>
  );
  const pager = (
    <nav
      id={end ? undefined : pagerId}
      // Names the pager this one repeats, for the one-control-per-job check
      // (tests/ui/test_one_control_per_job.py), which allows the repeat only
      // while it matches that pager control for control.
      data-repeat-of={end ? pagerId : undefined}
      tabIndex={end ? undefined : -1}
      aria-label={end ? `${label}: page controls under the table` : `${label}: page controls`}
      className="ml-auto flex flex-wrap items-center justify-end gap-x-3 gap-y-2 rounded-xs focus:outline-none focus-visible:shadow-focus"
    >
      {end ? (
        <p className="text-sm text-fg-muted">{where}</p>
      ) : (
        <p role="status" aria-live="polite" aria-atomic="true" className="text-sm text-fg-muted">
          {where}
        </p>
      )}
      <ul className="flex flex-wrap items-center gap-2">
        <li>
          <Button
            variant="secondary"
            className={ARROW}
            aria-label={`Previous page of ${name}`}
            aria-disabled={disabled || page === 1}
            onClick={() => go(page - 1)}
          >
            <ChevronLeft className="h-5 w-5" aria-hidden />
          </Button>
        </li>
        {pageItems(page, pages).map((item, index) =>
          item === null ? (
            <li key={`gap-${index}`} className="px-1 text-fg-muted" aria-hidden>
              …
            </li>
          ) : (
            <li key={item}>
              <Button
                variant={item === page ? "primary" : "secondary"}
                className="min-w-target justify-center px-3 tabular-nums"
                aria-label={`Page ${item} of ${name}`}
                aria-current={item === page ? "page" : undefined}
                aria-disabled={disabled || undefined}
                onClick={() => go(item)}
              >
                {item}
              </Button>
            </li>
          ),
        )}
        <li>
          <Button
            variant="secondary"
            className={ARROW}
            aria-label={`Next page of ${name}`}
            aria-disabled={disabled || page === pages}
            onClick={() => go(page + 1)}
          >
            <ChevronRight className="h-5 w-5" aria-hidden />
          </Button>
        </li>
      </ul>
    </nav>
  );
  return end ? <TableFoot>{pager}</TableFoot> : pager;
}

/**
 * A paged table's pager, drawn twice as one pair: in the bar over the table
 * (`top`) and again under its last row (`TablePagination` with
 * `place="end"`), with the table itself (`children`) between them. Every
 * paged table uses it, and only this module draws `TablePagination`.
 *
 * Why one component: until 2026-11-14 each screen drew the two pagers by
 * hand, one in its `TableBar` and one under its table, and a screen added
 * later drew only the top one, so its readers had to scroll back up to
 * turn the page. With the pair in one component, a screen cannot draw one
 * without the other. Rejected: keeping the hand-drawn pair and adding a
 * source check that every top pager has an end pager. A check that reads
 * the source can be fooled by a pager that is conditional, spread or
 * renamed, and it still leaves each screen to wire the pair by hand; here
 * it is wired once (tests/unit/test_table_pagers.py now checks only that no
 * screen draws `TablePagination` itself).
 *
 * The same pager, with the same words, in the same two places on every
 * table is what makes it read as one control shown twice (SC 3.2.4
 * Consistent Identification, Level AA). What keeps the two from getting in
 * each other's way (only the top one is a live region, the landmarks have
 * different names, a page turn from the end pager moves focus to the top
 * one) is in the comment on `TablePagination`, above, and is unchanged.
 *
 * `top` draws the bar over the table and is given the top pager, or null
 * when there is one page or no `pagination`. A screen with search or
 * filters passes its own `top`, which draws its `TableBar` (or a toolbar
 * that wraps one) whether or not there is a pager, so the filter that
 * emptied a table stays there to undo. It must put the pager it is given on
 * the page: the end pager sends focus to it after a page turn. Without
 * `top`, a table with no search or filters gets a plain `TableBar` holding
 * the pager, and no bar at all when there is one page.
 */
export function PagedTable({
  pagination,
  top,
  children,
}: {
  /** TablePagination's props except `place`; null or undefined draws no pager at all. */
  pagination: Omit<TablePaginationProps, "place"> | null | undefined;
  /**
   * Draws the bar over the table, given the top pager element (null when
   * there is one page or no pagination). Default: a plain
   * `<TableBar pager={pager} />`, drawn only when `pager` is not null.
   */
  top?: (pager: ReactNode) => ReactNode;
  /** Everything between the bar and the end pager: TableStatus, TableEmpty, TableRegion… */
  children: ReactNode;
}) {
  const pager = pagination && pagination.pages > 1 ? <TablePagination {...pagination} /> : null;
  return (
    <>
      {top ? top(pager) : pager && <TableBar pager={pager} />}
      {children}
      {pagination && <TablePagination {...pagination} place="end" />}
    </>
  );
}
