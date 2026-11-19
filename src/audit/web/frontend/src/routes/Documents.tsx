import { useMemo, useRef, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { ApiError, api } from "../api/client";
import type { LinkedFileRow, LinkedFileStatus } from "../api/types";
import {
  DocumentThumbnail,
  Found,
  HOSTED_COLUMN,
  PAGES_COLUMN,
  RESULT_COLUMN,
  ResultTag,
  SiteCell,
  StatusColumnHelp,
  TypeCell,
  documentPath,
  hostOf,
} from "../components/DocumentParts";
import HowSureTag from "../components/HowSureTag";
import ReportHeader from "../components/ReportHeader";
import {
  GlossaryList,
  ReportNote,
  ReportNotes,
  SummaryNumbers,
  SummaryStat,
} from "../components/ReportSummary";
import { PagedTable, usePagedRows } from "../components/TablePagination";
import {
  ActiveFilters,
  FilterMenu,
  activeFilterItems,
  splitFilter,
  type FilterGroup,
} from "../components/table/FilterMenu";
import {
  Cell,
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
import {
  compareText,
  parseSortParam,
  sortParam,
  sortWords,
  type Sort,
  type SortKind,
} from "../components/table/sort";
import { Card, EmptyState, LinkButton, withReturnTrail } from "../components/ui";
import { useScanQuery } from "../hooks/useScanQuery";
import { liveSearchParams } from "../lib/liveSearchParams";
import {
  LINKED_FILE_KIND_LABEL,
  LINKED_FILE_STATUS_HELP,
  LINKED_FILE_STATUS_LABEL,
  LINKED_FILE_STATUS_NOTE,
  LINKED_FILE_TYPE_LABEL,
  type LinkedFileKind,
} from "../lib/terms";

/** The trail label for this view; ReportCrumb and the document title use the same words. */
export const DOCUMENTS_VIEW = "Documents";

const STATUSES: readonly LinkedFileStatus[] = ["mostly_sure", "not_sure", "could_not_check"];

/** Files asked for at once: the server's MAX_LIMIT (linked_files_queries.py). */
const MAX_DOCUMENTS = 5000;

/** The Type filter's groups, in the order the menu lists them. */
const KIND_GROUPS: readonly LinkedFileKind[] = [
  "pdf",
  "word",
  "excel",
  "powerpoint",
  "opendocument",
  "rtf",
  "google",
];

/** Which Type group a file is in: Word for .docx and .doc, and so on. */
function kindOf(row: LinkedFileRow): LinkedFileKind {
  switch (row.file_type) {
    case "docx":
    case "doc":
      return "word";
    case "xlsx":
    case "xls":
      return "excel";
    case "pptx":
    case "ppt":
      return "powerpoint";
    case "odt":
    case "odp":
    case "ods":
      return "opendocument";
    case "google_doc":
    case "google_sheet":
    case "google_slides":
    case "google_drive":
      return "google";
    default:
      return row.file_type;
  }
}

/** The Hosted on filter's values: the words the column shows under the host. */
const HOSTED = ["this", "other"] as const;
type Hosted = (typeof HOSTED)[number];
const HOSTED_LABEL: Record<Hosted, string> = { this: "This site", other: "Another site" };
const hostedOf = (row: LinkedFileRow): Hosted => (row.off_site ? "other" : "this");

/** A filter's checked values, kept to the ones its group offers, in its order (as Issues). */
function parseList(raw: string | null, allowed: readonly string[]): string {
  const on = new Set(splitFilter(raw ?? ""));
  return allowed.filter((value) => on.has(value)).join(",");
}

function filterFiles(
  files: readonly LinkedFileRow[],
  { status, kind, hosted }: { status: string; kind: string; hosted: string },
): LinkedFileRow[] {
  const statuses = new Set(splitFilter(status));
  const kinds = new Set(splitFilter(kind));
  const hosts = new Set(splitFilter(hosted));
  return files.filter(
    (row) =>
      (!statuses.size || statuses.has(row.status)) &&
      (!kinds.size || kinds.has(kindOf(row))) &&
      (!hosts.size || hosts.has(hostedOf(row))),
  );
}

/**
 * The columns, each sortable, in the table's order. The keys are what
 * ``?sort=`` keeps ("pages_desc"); the labels are what the headers say.
 */
const SORT_COLUMNS = ["name", "type", "host", "status", "found", "pages"] as const;
type DocumentsColumn = (typeof SORT_COLUMNS)[number];
type DocumentsSort = Sort<DocumentsColumn>;
const COLUMN_LABEL: Record<DocumentsColumn, string> = {
  name: "Document",
  type: "Type",
  host: HOSTED_COLUMN,
  status: RESULT_COLUMN,
  found: "What Axcess found",
  pages: PAGES_COLUMN,
};
/**
 * Words open A to Z, counts open biggest first (./table/sort).
 * "Accessibility problems?" sorts Mostly sure, Not sure, Could not check
 * (A to Z reads as that order, as Issues' How sure column does). "What
 * Axcess found" sorts by how many problems the checks found.
 */
const SORT_KINDS: Record<DocumentsColumn, SortKind> = {
  name: "text",
  type: "text",
  host: "text",
  status: "text",
  found: "number",
  pages: "number",
};
const STATUS_RANK: Record<LinkedFileStatus, number> = { mostly_sure: 0, not_sure: 1, could_not_check: 2 };

function compareFiles(a: LinkedFileRow, b: LinkedFileRow, column: DocumentsColumn): number {
  switch (column) {
    case "name":
      return compareText(a.name, b.name);
    case "type":
      return compareText(LINKED_FILE_TYPE_LABEL[a.file_type], LINKED_FILE_TYPE_LABEL[b.file_type]);
    case "host":
      return compareText(hostOf(a.url) ?? "", hostOf(b.url) ?? "");
    case "status":
      return STATUS_RANK[a.status] - STATUS_RANK[b.status];
    case "found":
      return a.failed_checks.length - b.failed_checks.length;
    case "pages":
      return a.referring_page_count - b.referring_page_count;
  }
}

/** A stable sort: ties keep the recommended order the server sent. */
function sortFiles(files: LinkedFileRow[], sort: DocumentsSort | null): LinkedFileRow[] {
  if (!sort) return files;
  const sign = sort.direction === "asc" ? 1 : -1;
  return files
    .map((row, index) => ({ row, index }))
    .sort((a, b) => compareFiles(a.row, b.row, sort.column) * sign || a.index - b.index)
    .map(({ row }) => row);
}

/** What the order is, in words, for the status line and the caption. */
function describeSort(sort: DocumentsSort | null): string {
  if (!sort) return `Recommended order: ${ORDER_WORDS}`;
  return `Sorted by ${COLUMN_LABEL[sort.column]}, ${sortWords(SORT_KINDS[sort.column], sort.direction)}`;
}

/** The fixed order, in words, for the table's caption and the labels note's order section. */
const ORDER_WORDS = "Mostly sure first, then Not sure, then Could not check";


/**
 * The files a report's pages link to (``/scans/:id/documents``), the report's
 * third tab: PDF, Word, Excel, PowerPoint, OpenDocument, RTF and Google files,
 * where each is linked from, and what the checks found (PDF, Word and
 * PowerPoint files, Google Docs and Slides since 2026-11-17). A web editor
 * opens it to decide which file to fix first.
 *
 * Laid out as Issues (routes/Issues.tsx), the tab beside it, so a reader who
 * knows Issues finds each thing in the same place and form here: the header
 * with nothing under the heading, the row of summary numbers, the table, then
 * under it the closed notes, "What was checked" and "What … the other labels
 * mean". Nothing to read stands between the numbers and the table. The same
 * table parts, paging and page links as every report list. Rejected: the
 * layout of Pages visited, which this tab first copied, with the caveat and
 * several always-open paragraphs and a key before the table; beside Issues it
 * put the same kinds of fact in other places and other forms. One pattern for
 * one kind of thing (SC 3.2.4 Consistent Identification, Level AA; W3C COGA,
 * "Making Content Usable", https://www.w3.org/TR/coga-usable/, paraphrased:
 * the same pattern and the same words for the same thing).
 *
 * The caveat (results for an expert to review, not proof that the files meet
 * accessibility standards) is where Issues says it: in the empty table's
 * message, and here also as the first paragraph of "What was checked". Issues
 * dropped the caveat from under its heading on 2026-09-26 and has shown
 * nothing there since 2026-10-30 (the developer's request); Documents
 * follows it, the developer's choice on 2026-11-13.
 *
 * One file per row, laid out as Issues lays out issue types: the name
 * names the row (its row header, `th scope="row"`, technique H63) and
 * opens the document's own page (routes/DocumentDetail.tsx), as an issue
 * type's title opens its record, with screen-reader text ", full details"
 * as there. That page leads with "Open the file" and lists every page the
 * file appears on. The name opened the file itself until 2026-11-14; it
 * moved to the document's page when the pages left this table (below), so
 * Documents and Issues work the same way: list, then one thing, then its
 * pages (SC 3.2.4 Consistent Identification, Level AA). The row header
 * holds the name only: a screen reader reads it again with every cell, so
 * anything else there (the full address, "On another site") was heard five
 * times. Then its type, its site (SiteCell), the "Accessibility problems?"
 * value (RESULT_COLUMN), what the checks found, and how many pages it
 * appears on.
 *
 * The value uses the Issues table's tag (components/HowSureTag.tsx) and its
 * words for the same meaning, under a column name that says the question. What each value means is said in text in
 * the labels note under the table, as on Issues, because the tag's hover hint
 * is not available to everyone (SC 1.4.13 Content on Hover or Focus, Level
 * AA, and SC 3.3.2 Labels or Instructions, Level A, in spirit). A Not sure
 * row says in its own words what a person must still check, as the
 * developer asked, so it can never be read as a pass.
 *
 * The table opens in the recommended order, the answer to "what do I fix
 * first", worked out on the server (audit/web/linked_files_queries.py) from
 * the status, how many pages link to the file, whether it is a form, and how
 * serious its problem is. Each of those is shown in the row, so a reader can
 * see why a file sits where it does; there is no hidden score (a single 0 to
 * 100 score was ruled out by the developer). The order is explained in the
 * labels note, as its own section, the way Issues explains Priority.
 *
 * Every column sorts, and a Filter menu narrows the list by
 * "Accessibility problems?", Type and "Hosted on" (the developer's request,
 * 2026-11-14). Both are Issues', part for part: SortHeader on each column,
 * the order kept in ``?sort=`` and the filters in the URL so Back and a
 * shared link bring them back, FilterMenu and ActiveFilters in the bar over
 * the table, and the line over the table that, only while the table is
 * sorted or filtered, says the order and the count shown and offers "Back to
 * recommended order" (SC 3.2.4 Consistent Identification, Level AA). That
 * line is the way back a sorted header alone does not give, which is why the
 * sort buttons were left out until now; with Issues' line it is there. The
 * rows are all loaded at once (up to 5,000) and sorted, filtered and paged
 * here, as Issues does, so every column sorts the whole list, not one page.
 * The caption says the order to a screen reader, and a status line says it
 * again on every change.
 *
 * "Pages it appears on" is a plain number, as Issues' "Affected pages" is,
 * and the pages are listed on the document's page. Until 2026-11-14 the
 * cell listed up to 20 pages, each with its title and often its address,
 * which made rows taller than a screen (the developer's report). The
 * developer chose this after a review of other tools (Monsido / Acquia Web
 * Governance, Pope Tech and Screaming Frog all show a document's pages one
 * step away from the list, as a count or a per-document report) and of
 * Adrian Roselli's rows that expand in place
 * (https://adrianroselli.com/2019/09/table-with-expando-rows.html).
 * Rejected: rows that expand, which put page rows under document columns
 * that do not apply to them; the first 3 pages with "Show 11 more", which
 * kept the tall rows once opened (and GOV.UK found some people avoid a
 * "show more" link, https://design-system.service.gov.uk/components/details/);
 * and a side panel, the pattern Issues removed. Not a link either: one
 * link per row, as Issues' count stopped being one on 2026-11-02 (one way
 * to do one thing; W3C COGA, "Making Content Usable", paraphrased). A
 * document on one page works the same way, so the name always leads to the
 * same kind of place.
 *
 * Paged here (Settings > Rows per page, usePagedRows), with the page in
 * the URL so Back and reload return to the same rows. The pager is over the table
 * and again under its last row, as on every paged table (PagedTable draws
 * the pair); the copy under the table was missing here until 2026-11-14. A table wider than the screen
 * scrolls sideways in its own named region, never the page (TableRegion; SC
 * 1.4.10 Reflow, Level AA, allows this for a data table).
 */
export default function DocumentsRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const here = `${location.pathname}${location.search}`;
  // Each filter is a comma-separated list of the values checked, kept to
  // the values its group offers, in its order; "" is every row (as Issues).
  const status = parseList(params.get("status"), STATUSES);
  const kind = parseList(params.get("kind"), KIND_GROUPS);
  const hosted = parseList(params.get("hosted"), HOSTED);
  const rawSort = params.get("sort");
  const sort = useMemo(() => parseSortParam(rawSort, SORT_COLUMNS), [rawSort]);
  const hasFilter = Boolean(status || kind || hosted);

  const scanQuery = useScanQuery(id);
  // Every file at once (up to MAX_LIMIT on the server), sorted, filtered
  // and paged here, as the Issues table does with its rows: the headers can
  // then sort by any column, and the Filter menu counts every value.
  const filesQuery = useQuery({
    queryKey: ["scan-documents", id, "all"],
    queryFn: () => api.listScanDocuments(id, { limit: MAX_DOCUMENTS, offset: 0 }),
    enabled: Number.isFinite(id),
  });

  const setParam = (key: string, value: string) => {
    setParams(
      () => {
        const next = liveSearchParams();
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
  };
  // Every group back to "All" in one update, as on Issues (FilterMenu's
  // onReset): one setParam per group would put back what the first removed.
  const resetFilters = () => {
    setParams(
      () => {
        const next = liveSearchParams();
        for (const key of ["status", "kind", "hosted", "page"]) next.delete(key);
        return next;
      },
      { replace: true },
    );
  };
  const onSort = (next: DocumentsSort | null) => setParam("sort", next ? sortParam(next) : "");
  const region = useRef<HTMLDivElement>(null);

  const files = filesQuery.data?.files;
  const rows = useMemo(
    () => sortFiles(filterFiles(files ?? [], { status, kind, hosted }), sort),
    [files, status, kind, hosted, sort],
  );
  const paged = usePagedRows(rows, { resetKey: [status, kind, hosted, rawSort ?? ""].join("|") });

  const error = scanQuery.error ?? filesQuery.error;
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
        The list of documents could not load. Nothing in the saved report has changed. Reload the
        page to try again.
      </Card>
    );
  }
  if (!scanQuery.data || !filesQuery.data) {
    return (
      <p className="text-sm text-fg-muted" role="status">
        Loading documents…
      </p>
    );
  }

  const scan = scanQuery.data;
  const data = filesQuery.data;
  const all = data.files;
  const offset = (paged.page - 1) * paged.pageSize;
  const cut = data.total > all.length;
  // The button that was pressed goes away with the column sort, so focus
  // moves to the table it just reordered (as on Issues).
  const recommend = () => {
    onSort(null);
    region.current?.focus();
  };

  return (
    <>
      {/* The heading and the tabs only, as on Issues: no line under the
          heading. The counts are the numbers row below it. */}
      <ReportHeader scanId={scan.id} previousScanId={scan.previous_scan_id} title={DOCUMENTS_VIEW} tabs />

      {/* The counts as Issues shows its own: the shared row of summary
          numbers over the table (SummaryNumbers, SummaryStat), how many
          documents and then how many of each "Accessibility problems?" value, in the
          table's order. Four numbers, so four across from 640px and two by
          two below that, where nothing is squeezed at 320px (SC 1.4.10
          Reflow, Level AA). Every value is shown, zero included, as Issues
          shows a zero: "0 Mostly sure" is a result the reader needs.
          Rejected: the counts in the header's meta line ("7 documents · 2
          Mostly sure"), which Issues does not have, so the two tabs put the
          same kind of fact in two places (SC 3.2.4 Consistent
          Identification, Level AA). Shown only when the report looked for
          documents: with nothing looked for, there is nothing to count, as
          Issues shows its numbers only for a completed report. They count
          the whole report, whatever the filters, as Issues' do.

          Each value has a short line under it that finishes it as a
          sentence ("Mostly sure" / "it has accessibility problems",
          LINKED_FILE_STATUS_NOTE): alone, the value did not say what Axcess
          is sure of. See SummaryStat's ``note``. */}
      {data.recorded && (
        <SummaryNumbers className="sm:grid-cols-4">
          <SummaryStat label={data.total === 1 ? "Document" : "Documents"} value={data.total} />
          {STATUSES.map((value) => (
            <SummaryStat
              key={value}
              label={LINKED_FILE_STATUS_LABEL[value]}
              note={LINKED_FILE_STATUS_NOTE[value]}
              value={data.counts[value]}
            />
          ))}
        </SummaryNumbers>
      )}

      {/* The order, said to a screen reader on every change, as on Issues. */}
      <p role="status" className="sr-only">
        {describeSort(sort)}.
      </p>

      {/* No overflow-hidden: it would clip the Filter menu's panel, as on Issues. */}
      <Card>
        {/* PagedTable draws the pager over the table (in the toolbar) and
            again under its last row, as on every paged table. */}
        <PagedTable
          pagination={{ label: DOCUMENTS_VIEW, noun: "documents", ...paged }}
          top={(pager) =>
            data.recorded &&
            data.total > 0 && (
              <DocumentsToolbar
                files={all}
                status={status}
                kind={kind}
                hosted={hosted}
                onParam={setParam}
                onResetFilters={resetFilters}
                onClearFilters={() =>
                  setParams(
                    () => {
                      const next = liveSearchParams();
                      for (const key of ["status", "kind", "hosted", "page"]) next.delete(key);
                      return next;
                    },
                    { replace: true },
                  )
                }
                pager={pager}
              />
            )
          }
        >
          {/* What the order is, the filtered count and the way back to the
              recommended order: Issues' line over its table, shown, as there,
              only while the table is sorted by a column or filtered. Not a
              live region (the line above the card says the order). */}
          {(sort || hasFilter || cut) && (
            <TableStatus
              announce={false}
              actions={
                <>
                  {hasFilter && (
                    <span className="tabular-nums">
                      {rows.length.toLocaleString()} of {all.length.toLocaleString()} shown
                    </span>
                  )}
                  {sort && (
                    // eslint-disable-next-line react/forbid-elements -- Convert: a text-link styled button; needs a link variant on Button (as on Issues)
                    <button
                      type="button"
                      onClick={recommend}
                      className="min-h-target rounded-xs px-1 font-semibold text-umich-blue underline underline-offset-2 hover:text-umich-blue-600 focus-visible:outline-none focus-visible:shadow-focus"
                    >
                      Back to recommended order
                    </button>
                  )}
                </>
              }
            >
              {cut && `Showing the first ${all.length.toLocaleString()} of ${data.total.toLocaleString()} documents. `}
              {sort && `${describeSort(sort)}.`}
            </TableStatus>
          )}
          {/* An empty table says what it means and points down to the note
              that says why, as Issues' does ("That does not mean the site
              meets WCAG… See “What was checked”, below this table."): an empty
              list must never read as a clean result. */}
          {!data.recorded ? (
            <TableEmpty>
              This report did not look for documents. See why in “What was checked”, below this
              table.
            </TableEmpty>
          ) : data.total === 0 ? (
            <TableEmpty>
              The scan found no links to documents on the pages it visited. That does not mean the
              site has none, because the list can miss files. See “What was checked”, below this
              table.
            </TableEmpty>
          ) : rows.length === 0 ? (
            <TableEmpty>No documents match these filters. Clear a filter to see more results.</TableEmpty>
          ) : (
            <TableRegion label="Documents table" regionRef={region}>
              <Table caption={`Documents linked from report #${scan.id}, ${describeSort(sort)}`}>
                <TableHead>
                  <tr>
                    {SORT_COLUMNS.map((column) => (
                      <SortHeader
                        key={column}
                        column={column}
                        wrap="words"
                        kind={SORT_KINDS[column]}
                        sort={sort}
                        onSort={onSort}
                        help={column === "status" ? <StatusColumnHelp /> : undefined}
                        // Sorted by how many problems, shown in words: its
                        // heading sits on the left with its cells
                        // (SortHeader ``align``; the table's side rule).
                        align={column === "found" ? "left" : undefined}
                      >
                        {COLUMN_LABEL[column]}
                      </SortHeader>
                    ))}
                  </tr>
                </TableHead>
                <tbody>
                  {paged.pageRows.map((row, index) => (
                    <DocumentRow
                      key={row.file_id}
                      row={row}
                      index={offset + index}
                      scanId={scan.id}
                      backTo={here}
                    />
                  ))}
                </tbody>
              </Table>
            </TableRegion>
          )}
        </PagedTable>
      </Card>

      {/* Under the table, as on Issues: the table follows the numbers with
          nothing to step over, and what explains it waits in closed rows
          (ReportNotes; see ReportCoverageNote for why Issues moved them
          there). The same two rows, in the same order, with the same
          titles. */}
      <ReportNotes className="mt-8">
        <DocumentsCoverageNote recorded={data.recorded} />
        <DocumentsGlossary />
      </ReportNotes>
    </>
  );
}

/**
 * The bar over the table, as Issues' (IssueToolbar): the Filter menu on the
 * left, the pager on the right, and what is filtered written out under both
 * (ActiveFilters). One Filter control for every way the list narrows, each
 * group named as its column is ("Accessibility problems?", "Type", "Hosted
 * on") so the filter and the column read as one thing, with how many files
 * each value has (FilterMenu, the Issues table's own; SC 3.2.4 Consistent
 * Identification, Level AA). No search box: the developer asked for the
 * filter; Issues' search is for long titles and WCAG numbers, and a file
 * name is easy to find on a sorted Document column.
 */
function DocumentsToolbar({
  files,
  status,
  kind,
  hosted,
  onParam,
  onResetFilters,
  onClearFilters,
  pager,
}: {
  files: LinkedFileRow[];
  status: string;
  kind: string;
  hosted: string;
  onParam: (key: string, value: string) => void;
  onResetFilters: () => void;
  onClearFilters: () => void;
  pager: ReactNode;
}) {
  const count = (test: (row: LinkedFileRow) => boolean) => files.filter(test).length;
  const groups: FilterGroup[] = [
    {
      key: "status",
      label: RESULT_COLUMN,
      value: status,
      multiple: true,
      options: STATUSES.map((value) => ({
        value,
        label: LINKED_FILE_STATUS_LABEL[value],
        count: count((row) => row.status === value),
      })),
    },
    {
      key: "kind",
      label: "Type",
      value: kind,
      multiple: true,
      options: KIND_GROUPS.map((value) => ({
        value,
        label: LINKED_FILE_KIND_LABEL[value],
        count: count((row) => kindOf(row) === value),
      })),
    },
    {
      key: "hosted",
      label: HOSTED_COLUMN,
      value: hosted,
      multiple: true,
      options: HOSTED.map((value) => ({
        value,
        label: HOSTED_LABEL[value],
        count: count((row) => hostedOf(row) === value),
      })),
    },
  ];
  return (
    <TableBar pager={pager} footer={<ActiveFilters items={activeFilterItems(groups)} onClear={onClearFilters} />}>
      <FilterMenu label="Filter documents" groups={groups} onChange={onParam} onReset={onResetFilters} />
    </TableBar>
  );
}

/**
 * "What was checked" for the Documents tab: the same row, title and place as
 * Issues' (ReportCoverageNote), holding what this list covers and what it
 * cannot show. Issues' row holds the table of checks; Documents has one check,
 * so its row holds short paragraphs, one idea each, about 72 characters wide
 * (52ch; SC 1.4.8 Visual Presentation, Level AAA; W3C COGA, "Making Content
 * Usable": one idea per chunk).
 *
 * In this order: the caveat, first, because a list with "Not sure" beside a
 * file could be read as a pass; which files are listed and which types are
 * checked; what the Word and PowerPoint checks look at, and that possible
 * problems need a person; what Axcess downloaded and kept (a privacy fact);
 * what the list can miss; and why a report may not have looked for
 * documents. Never
 * drop the privacy or limitation facts to make the row shorter (AGENTS.md,
 * Interface language rule 4).
 *
 * The closed row shows one fact on its right, as Issues' shows "6 of 7
 * checks ran": "3 types checked" (PDF, Word and PowerPoint; "Only PDFs
 * checked" until 2026-11-17), the limit a reader most needs beside the
 * numbers, with the types named in the paragraph inside; or, for a report
 * that did not look, "Not looked for", under the empty table that says so
 * in full. No longer than Issues' 17 characters: "Only PDF files are
 * checked" squeezed the title to one word a line at 320px, and a list of
 * the three types would too.
 */
function DocumentsCoverageNote({ recorded }: { recorded: boolean }) {
  return (
    <ReportNote
      id="report-coverage"
      title="What was checked"
      meta={recorded ? "3 types checked" : "Not looked for"}
    >
      <div className="max-w-[52ch] space-y-2 text-sm leading-6 text-fg-muted">
        <p>
          Results for an expert to review. They do not prove that the files meet accessibility
          standards.
        </p>
        <p>
          This list shows the files that the scanned pages link to or show inside the page: PDF,
          Word, Excel, PowerPoint, OpenDocument, Rich Text Format (RTF) and Google files. Axcess
          checks the PDF, Word (.docx) and PowerPoint (.pptx) files. It checks a Google Doc or
          Google Slides file as the Word or PowerPoint file that Google exports. It does not check
          Excel files, Google Sheets, old Office files (.doc, .ppt) or the other types.
        </p>
        {/* What the Word and PowerPoint checks look at, so a reader knows
            what "No problem found" covers, and that a possible problem is
            for a person to judge. True to office_check.py: change them
            together. */}
        <p>
          In a Word or PowerPoint file, Axcess checks the alt text for images, table header rows,
          headings, slide titles and the language. It also lists possible problems, such as link
          text, for a person to judge. They do not make a file &ldquo;Mostly sure&rdquo;.
        </p>
        <p>
          To check a file, Axcess downloaded it to this computer once. It kept the results, not
          the file. For a file on another site, Axcess opened that one file and did not scan the
          site.
        </p>
        <p>
          The list can miss files. A link that appears only after pressing a button is found only
          if the scan pressed it, and the scan does not press buttons that may download, buy or
          delete something.
        </p>
        <p>
          Some reports do not look for documents: reports made before Axcess could find them,
          reports from a sign-in scan made before 16 November 2026, and scans with the document
          check turned off. A new scan with the document check on lists the site’s documents.
        </p>
        {/* Sign-in scans check documents since 2026-11-16, through the
            person's sign-in and only on the signed-in site (the developer's
            decision). Said here because a file on another site then reads
            "could not check" with the scan's-settings reason, which alone
            would not tell the reader why. */}
        <p>
          A scan that signs in to a site downloads files only from that site, with the sign-in. It
          lists files on other sites but does not download them.
        </p>
      </div>
    </ReportNote>
  );
}

/**
 * What the counts, the "Accessibility problems?" values and the order mean, closed until
 * asked for: Issues' labels note (IssueGlossary in routes/Issues.tsx), with
 * the same title pattern, place, grid and parts (ReportNote, GlossaryList),
 * so the two tabs explain their labels the same way (SC 3.2.4 Consistent
 * Identification, Level AA).
 *
 * The sections follow Issues': what is counted first, then the "Accessibility problems?"
 * values, each the same tag the table draws, then the order, as its own
 * section, the way Issues explains Priority ("which issue types to look at
 * first"). The tags carry the same sentences as hover hints, but a hint
 * reaches only a mouse: this list is how keyboard and touch users, and anyone
 * who turned hints off, read them (SC 1.4.13 Content on Hover or Focus, Level
 * AA). The order's steps are the server's (audit/web/linked_files_queries.py);
 * change them together.
 */
function DocumentsGlossary() {
  return (
    <ReportNote
      id="report-labels"
      title={`What "${LINKED_FILE_STATUS_LABEL.mostly_sure}", "${LINKED_FILE_STATUS_LABEL.not_sure}" and the other labels mean`}
    >
      <div className="grid max-w-5xl gap-x-10 gap-y-4 text-sm leading-relaxed text-fg-muted md:grid-cols-2 xl:grid-cols-3">
        <GlossaryList
          heading="The numbers: what is counted"
          items={[
            {
              key: "document",
              term: <span className="font-semibold text-fg">Document</span>,
              help: "One file that a scanned page links to or shows inside the page. A file linked from many pages counts once. Each is one row in the Documents table.",
            },
          ]}
        />
        <GlossaryList
          heading={`${RESULT_COLUMN} How sure Axcess is that a file has them`}
          items={STATUSES.map((status) => ({
            key: status,
            term: <HowSureTag label={LINKED_FILE_STATUS_LABEL[status]} quiet={status === "could_not_check"} />,
            help: LINKED_FILE_STATUS_HELP[status],
          }))}
        />
        <GlossaryList
          heading="The order: which files to look at first"
          items={[
            {
              key: "status",
              term: <span className="font-semibold text-fg">1. {RESULT_COLUMN}</span>,
              help: `${ORDER_WORDS}.`,
            },
            {
              key: "pages",
              term: <span className="font-semibold text-fg">2. {PAGES_COLUMN}</span>,
              help: "Within each answer, files that appear on more pages come first.",
            },
            {
              key: "form",
              term: <span className="font-semibold text-fg">3. A form to fill in</span>,
              help: "Then files with a form to fill in.",
            },
            {
              key: "serious",
              term: <span className="font-semibold text-fg">4. How serious the problem is</span>,
              help: "Then files with more serious problems. A file that is not tagged, has no text a screen reader can read, or stops screen readers in its security settings comes before one with only no title or no language set.",
            },
          ]}
        />
      </div>
    </ReportNote>
  );
}

/**
 * One linked file.
 *
 * The widest columns' minimums (Document 11rem, What Axcess found 12rem)
 * leave room, at 1280px with the sidebar open, for the sort tag a sorted
 * header adds under its name ("high → low" under "Pages it appears on"), so
 * a sorted table still fits without sideways scrolling. At 14rem the table
 * was 30px too wide once sorted by that column. Narrower screens scroll the
 * table in its own region (TableRegion; SC 1.4.10 Reflow, Level AA, allows
 * it for a data table).
 */
function DocumentRow({
  row,
  index,
  scanId,
  backTo,
}: {
  row: LinkedFileRow;
  index: number;
  scanId: number;
  backTo: string;
}) {
  return (
    <Row index={index} className="align-top">
      <RowHeader className="min-w-[11rem] max-w-xs align-top">
        {/* The name opens the document's own page, as an issue type's title
            opens its record on Issues; see DocumentsRoute. */}
        <Link
          to={withReturnTrail(documentPath(scanId, row.file_id), DOCUMENTS_VIEW, backTo)}
          className="flex min-h-target flex-col items-start gap-1 text-umich-blue underline underline-offset-2 hover:text-umich-blue-600"
        >
          {/* The first page above the name, as on the Images tab; see
              DocumentThumbnail for why it sits inside this one link. */}
          <DocumentThumbnail scanId={scanId} row={row} />
          <span className="[overflow-wrap:anywhere]" data-scanned-content>
            {row.name}
          </span>
          <span className="sr-only">, full details</span>
        </Link>
      </RowHeader>
      <Cell className="min-w-[8rem] align-top">
        <TypeCell row={row} />
      </Cell>
      <Cell className="min-w-[9rem] align-top">
        <SiteCell url={row.url} offSite={row.off_site} />
      </Cell>
      <Cell className="whitespace-nowrap align-top">
        <ResultTag status={row.status} />
      </Cell>
      <Cell className="min-w-[12rem] max-w-sm align-top text-sm">
        <Found row={row} />
      </Cell>
      <Cell numeric className="align-top">
        {row.referring_page_count.toLocaleString()}
      </Cell>
    </Row>
  );
}
