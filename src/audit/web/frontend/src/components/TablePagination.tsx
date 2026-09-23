import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Button } from "./ui";

/**
 * Every table in the app shows at most this many rows at a time. A long
 * table was one long scroll: "Pages with this issue" alone could list 1,200
 * pages, and the reader lost the column headers and their place in it.
 */
export const TABLE_PAGE_SIZE = 10;

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
} {
  const [params, setParams] = useSearchParams();
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
  const pages = Math.max(1, Math.ceil(total / TABLE_PAGE_SIZE));
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

  const start = (page - 1) * TABLE_PAGE_SIZE;
  return { pageRows: rows.slice(start, start + TABLE_PAGE_SIZE), page, pages, total, setPage };
}

/**
 * Previous/Next under a table, with where you are in words. Rendered only
 * when there is more than one page. The status line is announced politely,
 * so a screen reader hears the new range after a page turn.
 */
export function TablePagination({
  label,
  noun,
  page,
  pages,
  total,
  setPage,
}: {
  /** The table's name, for the controls' accessible names ("Issues"). */
  label: string;
  /** What a row is, plural ("issue groups", "pages"). */
  noun: string;
  page: number;
  pages: number;
  total: number;
  setPage: (page: number) => void;
}) {
  if (pages <= 1) return null;
  const first = (page - 1) * TABLE_PAGE_SIZE + 1;
  const last = Math.min(page * TABLE_PAGE_SIZE, total);
  return (
    <nav
      aria-label={`${label} pagination`}
      className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3"
    >
      <p role="status" aria-live="polite" aria-atomic="true" className="text-sm text-fg-muted">
        Showing {first.toLocaleString()}–{last.toLocaleString()} of {total.toLocaleString()} {noun} · Page{" "}
        {page} of {pages}
      </p>
      <div className="flex gap-2">
        <Button
          variant="secondary"
          aria-label={`Previous page of ${label.toLowerCase()}`}
          aria-disabled={page === 1}
          onClick={() => {
            if (page > 1) setPage(page - 1);
          }}
        >
          Previous
        </Button>
        <Button
          variant="secondary"
          aria-label={`Next page of ${label.toLowerCase()}`}
          aria-disabled={page === pages}
          onClick={() => {
            if (page < pages) setPage(page + 1);
          }}
        >
          Next
        </Button>
      </div>
    </nav>
  );
}
