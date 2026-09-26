import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./ui";
import { useTablePageSize } from "../hooks/usePreferences";

/*
 * Every table in the app shows at most Settings > Rows per page rows at a
 * time (10 by default). A long table was one long scroll: "Pages with this
 * issue" alone could list 1,200 pages, and the reader lost the column
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
  /** Spread on the element around the table: keeps its height from page to page. */
  hold: { ref: (node: HTMLElement | null) => void; style: { minHeight?: number } };
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

  // The table keeps the height of its tallest page so far, so turning to a
  // short last page does not pull the pager, and everything under it, up
  // the screen. Rows vary in height (titles wrap), so the height is measured
  // rather than padded with blank rows. A new filter or sort starts over.
  const holder = useRef<HTMLElement | null>(null);
  const [held, setHeld] = useState(0);
  if (restart && held !== 0) setHeld(0);
  const ref = useCallback((node: HTMLElement | null) => {
    holder.current = node;
  }, []);
  useLayoutEffect(() => {
    const node = holder.current;
    if (!node || pages <= 1) return;
    const height = Math.ceil(node.getBoundingClientRect().height);
    if (height > held) setHeld(height);
  }, [page, pages, rows, held]);

  const start = (page - 1) * pageSize;
  return {
    pageRows: rows.slice(start, start + pageSize),
    page,
    pages,
    total,
    setPage,
    pageSize,
    hold: { ref, style: pages > 1 && held ? { minHeight: held } : {} },
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

/**
 * The pager in a table's top bar (`TableBar` in ./table/Table): a previous
 * arrow, a button per page (with gaps once there are many), a next arrow,
 * and where you are in words. It sits above the rows, so a reader learns
 * the list continues before reading it, and the arrows stay in place as
 * pages of different heights come and go. Rendered only when there is more
 * than one page. The numbered buttons show at a glance that
 * the list continues and how far; the current one is filled and carries
 * `aria-current`. The status line is announced politely, so a screen
 * reader hears the new range after a page turn.
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
}: {
  hold?: unknown;
  /** The table's name, for the controls' accessible names ("Issues"). */
  label: string;
  /** What a row is, plural ("issue groups", "pages"). */
  noun: string;
  page: number;
  pages: number;
  total: number;
  setPage: (page: number) => void;
  pageSize: number;
  pagerId: string;
  /** Hold every control while a server page is loading. */
  disabled?: boolean;
}) {
  if (pages <= 1) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const name = label.toLowerCase();
  const go = (next: number) => {
    if (!disabled && next >= 1 && next <= pages && next !== page) setPage(next);
  };
  return (
    <nav
      id={pagerId}
      tabIndex={-1}
      aria-label={`${label} pagination`}
      className="ml-auto flex flex-wrap items-center justify-end gap-x-3 gap-y-2 rounded-xs focus:outline-none focus-visible:shadow-focus"
    >
      <p role="status" aria-live="polite" aria-atomic="true" className="text-sm text-fg-muted">
        Showing {first.toLocaleString()}–{last.toLocaleString()} of {total.toLocaleString()} {noun} · Page{" "}
        {page} of {pages}
      </p>
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
}
