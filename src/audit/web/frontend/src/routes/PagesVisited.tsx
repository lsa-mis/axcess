import { useEffect } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useLocation, useParams, useSearchParams } from "react-router";
import { ApiError, api } from "../api/client";
import type { ScanPageRow, ScanPagesSort } from "../api/types";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
import { TablePagination } from "../components/TablePagination";
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
  TableStatus,
} from "../components/table/Table";
import { parseSortParam, sortParam, sortWords, type Sort, type SortKind } from "../components/table/sort";
import { Card, EmptyState, LinkButton, PageActionLinks, PageLink } from "../components/ui";
import { useTablePageSize } from "../hooks/usePreferences";
import { useScanQuery } from "../hooks/useScanQuery";
import { CLICK_THROUGH_STATES_LABEL } from "../lib/labels";
import { pageLoadLabel } from "../lib/pageLabels";

/** The trail label for this view; ReportCrumb and the document title use the same words. */
export const PAGES_VISITED_VIEW = "Pages visited";

/**
 * The columns that sort. Each key is also the API's sort prefix, so
 * ``sortParam`` gives the server's sort value as it is ("load_desc").
 *
 * The Page column does not sort, as on Image details' list of pages. A
 * sort button there would be named "Page" alone, which says nothing about
 * what pressing it does (docs/plain-language.md rule 8;
 * tests/ui/test_control_text_purpose.py), and the column shows a title over
 * an address, so either order would match only half of what it shows.
 * Rows that tie in any sort are in address order, A to Z, which the server
 * applies as the last key.
 */
type SortColumn = "load" | "occurrences" | "images" | "states";
const COLUMNS: readonly SortColumn[] = ["load", "occurrences", "images", "states"];

const SORT_KINDS: Record<SortColumn, SortKind> = {
  load: "number",
  occurrences: "number",
  images: "number",
  states: "number",
};

const COLUMN_LABEL: Record<SortColumn, string> = {
  // The same words as the "Page load result" line on Page details.
  load: "Page load result",
  occurrences: "Issue occurrences",
  // The same words Page details uses for the same count ("4 images checked").
  images: "Images checked",
  states: CLICK_THROUGH_STATES_LABEL,
};

/**
 * Problems first by default: pages that could not be loaded, then pages
 * that answered with an error, then the rest by address. See the route's
 * comment for why.
 */
const DEFAULT_SORT: Sort<SortColumn> = { column: "load", direction: "desc" };

/** The load result's direction in words: it is an order of problems, not a number. */
function loadWords(direction: Sort<SortColumn>["direction"]): string {
  return direction === "desc" ? "problems first" : "problems last";
}

function describeSort(sort: Sort<SortColumn>): string {
  const words = sort.column === "load" ? loadWords(sort.direction) : sortWords(SORT_KINDS[sort.column], sort.direction);
  return `${COLUMN_LABEL[sort.column]}, ${words}`;
}

function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString()} ${count === 1 ? one : many}`;
}

/**
 * Every page a report visited, one page per row (``/scans/:id/pages``).
 *
 * The report summary's "Pages visited" number links here. A number alone
 * could not tell a clean result from missing coverage: "0 issue
 * occurrences" reads the same whether every page loaded and passed or half
 * of them never loaded. So each row says how its page loaded, in words, and
 * what the checks stored against it.
 *
 * Columns, laid out as the closest existing list of pages, "Pages with this
 * image" on Image details (routes/FindingDetail.tsx): the page names the row
 * (its title, its address under it; the row header, `th scope="row"`,
 * technique H63), then the facts about it, then Actions last, with "Open
 * live page" and "Page details" side by side (PageActionLinks). The title
 * opens the page inspector, as everywhere a page is named (PageLink). One
 * pattern for one kind of table (SC 3.2.4 Consistent Identification, Level
 * AA; W3C COGA, "Making Content Usable", https://www.w3.org/TR/coga-usable/,
 * paraphrased: the same pattern for the same kind of thing). Rejected: the
 * address alone as a link to Page details, which would have been the one
 * place in the app where a page's name does not open the inspector.
 *
 * Problems first, by default. A reader opens this list to check coverage,
 * and the pages that could not be loaded are the gaps; with hundreds of
 * pages in address order they would be scattered across many pages of
 * rows. Ties fall back to the address, A to Z, so the order is predictable
 * (SC 3.2.3 Consistent Navigation, Level AA, in spirit). The counts at the
 * top say how many failed before any row is read.
 *
 * A failed page says so in words, "Could not be loaded" or the server's
 * answer ("Page not found (HTTP 404)"), in bold, with a warning icon beside
 * it that is hidden from screen readers. The words carry the meaning, so
 * neither the icon nor a colour is the only signal (SC 1.4.1 Use of Color,
 * Level A). The words stay in the body text colour: a warning colour on a
 * striped row would need its 7:1 contrast checked again in every theme (SC
 * 1.4.6 Contrast (Enhanced), Level AAA). Its counts read "Not checked", not
 * "0": no check ran on a page that did not load, and "0" would read as a
 * clean result, the very confusion this list exists to remove.
 *
 * A page's address does not break inside a word, so a site with long
 * addresses makes the table wider than the screen. It then scrolls sideways
 * inside its own named region, never the page (TableRegion; SC 1.4.10
 * Reflow, Level AA, allows this for a data table). The count headers wrap
 * by word, so the Actions column fits at 1280px for short addresses.
 *
 * The rows are paged by the server (at most Settings > Rows per page, the
 * same as every table), because a scan can visit thousands of pages. The
 * page and the sort live in the URL, so Back, reload and the trail from a
 * row's Page details return to the same rows. There is no search box: the
 * server does not search pages yet, and searching only the rows on screen
 * would miss pages on the other pages of rows.
 */
export default function PagesVisitedRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const pageSize = useTablePageSize();
  const sort = parseSortParam(params.get("sort"), COLUMNS) ?? DEFAULT_SORT;
  const rawPage = Number(params.get("page") ?? "1");
  const page = Number.isFinite(rawPage) && rawPage >= 1 ? Math.floor(rawPage) : 1;
  const offset = (page - 1) * pageSize;
  // Links out of the table return here, page and sort included.
  const here = `${location.pathname}${location.search}`;

  const scanQuery = useScanQuery(id);
  const pagesQuery = useQuery({
    queryKey: ["scan-pages", id, sortParam(sort), pageSize, offset],
    queryFn: () =>
      api.listScanPages(id, { limit: pageSize, offset, sort: sortParam(sort) as ScanPagesSort }),
    // The old rows stay on screen while the next page loads, so the table
    // does not collapse and jump on every page turn.
    placeholderData: (previous, query) => (query?.queryKey[1] === id ? keepPreviousData(previous) : undefined),
    enabled: Number.isFinite(id),
  });

  const total = pagesQuery.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  // A page past the end (a smaller Rows per page setting, an old link) shows
  // the last page, as usePagedRows does for the tables paged in the browser.
  useEffect(() => {
    if (!pagesQuery.data || pagesQuery.isPlaceholderData || page <= pages) return;
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (pages <= 1) next.delete("page");
        else next.set("page", String(pages));
        return next;
      },
      { replace: true },
    );
  }, [pagesQuery.data, pagesQuery.isPlaceholderData, page, pages, setParams]);

  const error = scanQuery.error ?? pagesQuery.error;
  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <EmptyState
          level={1}
          title="Report not found"
          message="This report is not in Axcess. It may have been deleted, or the link may be out of date."
          action={
            <LinkButton to="/scans" variant="primary">
              Go to Reports
            </LinkButton>
          }
        />
      );
    }
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        The list of pages visited could not load. Nothing in the saved report has changed. Reload
        the page to try again.
      </Card>
    );
  }
  if (!scanQuery.data || !pagesQuery.data) {
    return (
      <p className="text-sm text-fg-muted" role="status">
        Loading pages visited…
      </p>
    );
  }

  const scan = scanQuery.data;
  const data = pagesQuery.data;
  const setSort = (next: Sort<SortColumn>) =>
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        updated.set("sort", sortParam(next));
        // A new order starts the list over at its first page.
        updated.delete("page");
        return updated;
      },
      { replace: true },
    );
  const setPage = (next: number) =>
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        if (next <= 1) updated.delete("page");
        else updated.set("page", String(next));
        return updated;
      },
      { replace: true },
    );
  const sortProps = { sort, onSort: setSort };
  const shownPage = Math.min(page, pages);

  const counts = [
    plural(data.total, "page", "pages"),
    data.not_loaded_count > 0 ? `${data.not_loaded_count.toLocaleString()} could not be loaded` : null,
    data.error_status_count > 0
      ? `${data.error_status_count.toLocaleString()} answered with an error`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <>
      <ReportHeader
        scanId={scan.id}
        previousScanId={scan.previous_scan_id}
        title={PAGES_VISITED_VIEW}
        // The counts only, without ReportMeta's standing caveat beside them:
        // the header's line runs to 4xl, and the two-sentence caveat made it
        // over 80 characters a line (SC 1.4.8 Visual Presentation, Level
        // AAA; tests/ui/test_wcag_aaa.py). The caveat is not dropped (AGENTS.md,
        // Interface language rule 4): it is the first paragraph below, in
        // the same words, where the line length is held under 80 characters.
        meta={<ReportMeta counts={counts} note="" />}
      />

      {/* What the counts mean and what the list leaves out, before the
          table, in short paragraphs, one idea each (W3C COGA, "Making
          Content Usable": one idea per chunk). Plain text, not a card: it
          is not a control and should not look like one. About 72
          characters wide (52ch: this font sets about 1.4 characters per ch),
          so no line runs past 80 (SC 1.4.8
          Visual Presentation, Level AAA).

          The caveat comes first: a list of pages with counts beside them
          could be read as a pass mark for the pages with zeros.

          The next line says what an occurrence is, as every screen that
          first counts them does (SC 3.1.3 Unusual Words, Level AAA;
          docs/plain-language.md, "Why "occurrence" and "issue type""), and
          why the column can add up to more than the report's own count: the
          Issues table counts an element that repeats across pages once. A
          reader adding up the column would otherwise think one of the two
          numbers was wrong.

          The next says which pages are not here. The skipped pages are a
          limit of the report, and a limit is never dropped to save space
          (AGENTS.md, Interface language rule 4).

          The last shows only when the summary's "could not be loaded"
          number differs from this list's. The summary counts every failure
          while a page was scanned, including ones after the page was saved
          and ones before it was, so the two can differ, and the reader is
          told why rather than left to doubt both. */}
      <div className="mb-5 max-w-[52ch] space-y-2 text-sm leading-6 text-fg-muted">
        <p>
          Results for an expert to review. They do not prove that the site meets accessibility
          standards.
        </p>
        <p>
          An occurrence is one place a problem appears. Each count here matches that page&rsquo;s
          Page details. An element that repeats on many pages, such as a menu, counts on each page
          here, but only once in the Issues table.
        </p>
        <p>
          This list does not include pages the scan skipped: pages outside the scope of the scan,
          and pages the site asked scanners to stay out of (in its robots.txt file).
        </p>
        {scan.error_count > 0 && scan.error_count !== data.not_loaded_count && (
          <p>
            The report summary counts {plural(scan.error_count, "page", "pages")} that could not be
            loaded. That number also counts other failures while Axcess scanned a page, so it can
            differ from this list.
          </p>
        )}
      </div>

      <Card>
        {pages > 1 && (
          <TableBar
            pager={
              <TablePagination
                label={PAGES_VISITED_VIEW}
                noun="pages"
                page={shownPage}
                pages={pages}
                total={total}
                setPage={setPage}
                pageSize={pageSize}
                pagerId="pager-pages-visited"
                disabled={pagesQuery.isPlaceholderData}
              />
            }
          />
        )}
        <TableStatus>Sorted by {describeSort(sort)}.</TableStatus>
        {data.total === 0 ? (
          <TableEmpty>This report has no saved pages.</TableEmpty>
        ) : (
          <TableRegion label="Pages visited table" busy={pagesQuery.isPlaceholderData}>
            <Table caption={`Pages visited by report #${scan.id}, sorted by ${describeSort(sort)}`}>
              <TableHead>
                <tr>
                  <ColumnHeader>Page</ColumnHeader>
                  <SortHeader
                    column="load"
                    kind="number"
                    chip={(current) => loadWords(current.direction)}
                    {...sortProps}
                  >
                    {COLUMN_LABEL.load}
                  </SortHeader>
                  <SortHeader column="occurrences" kind="number" wrap="words" {...sortProps}>
                    {COLUMN_LABEL.occurrences}
                  </SortHeader>
                  <SortHeader column="images" kind="number" wrap="words" {...sortProps}>
                    {COLUMN_LABEL.images}
                  </SortHeader>
                  <SortHeader column="states" kind="number" wrap="words" {...sortProps}>
                    {COLUMN_LABEL.states}
                  </SortHeader>
                  <ColumnHeader className="whitespace-nowrap">Actions</ColumnHeader>
                </tr>
              </TableHead>
              <tbody>
                {data.pages.map((row, index) => (
                  <PageRow
                    key={row.page_id}
                    row={row}
                    index={(shownPage - 1) * pageSize + index}
                    scanId={scan.id}
                    backTo={here}
                  />
                ))}
              </tbody>
            </Table>
          </TableRegion>
        )}
        <TablePagination
          label={PAGES_VISITED_VIEW}
          noun="pages"
          page={shownPage}
          pages={pages}
          total={total}
          setPage={setPage}
          pageSize={pageSize}
          pagerId="pager-pages-visited"
          disabled={pagesQuery.isPlaceholderData}
          place="end"
        />
      </Card>
    </>
  );
}

/** One visited page. */
function PageRow({
  row,
  index,
  scanId,
  backTo,
}: {
  row: ScanPageRow;
  /** Position across all pages of rows: the row stripe. */
  index: number;
  scanId: number;
  backTo: string;
}) {
  const failed = row.load_result !== "loaded";
  const checked = row.load_result !== "not_loaded";
  const display = row.title?.trim() || row.url;
  const count = (value: number) => (checked ? value.toLocaleString() : <span className="text-fg-muted">Not checked</span>);
  return (
    <Row index={index}>
      <RowHeader className="min-w-[12rem] max-w-md font-normal">
        <PageLink
          pageId={row.page_id}
          scanId={scanId}
          pageUrl={row.url}
          pageTitle={row.title}
          origin={PAGES_VISITED_VIEW}
          backTo={backTo}
          actions={false}
        />
      </RowHeader>
      <Cell className="min-w-[9rem]">
        {failed ? (
          <span className="inline-flex items-start gap-1.5 font-semibold text-fg">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-sev-major" aria-hidden />
            {pageLoadLabel(row.load_result, row.status_code)}
          </span>
        ) : (
          <span className="text-fg-muted">{pageLoadLabel(row.load_result, row.status_code)}</span>
        )}
      </Cell>
      <Cell numeric>{count(row.occurrence_count)}</Cell>
      <Cell numeric>{count(row.image_count)}</Cell>
      <Cell numeric>{count(row.page_state_count)}</Cell>
      <Cell className="whitespace-nowrap">
        <PageActionLinks
          look="actions"
          className="justify-center"
          pageId={row.page_id}
          scanId={scanId}
          pageUrl={row.url}
          display={display}
          origin={PAGES_VISITED_VIEW}
          backTo={backTo}
        />
      </Cell>
    </Row>
  );
}
