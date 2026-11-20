import { memo, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useParams } from "react-router";
import { ExternalLink, ScanEye } from "lucide-react";
import { ApiError, api } from "../api/client";
import type { DocumentPage, LinkedFileRow } from "../api/types";
import {
  DocumentPreview,
  Found,
  HOSTED_COLUMN,
  HowItAppears,
  PAGES_COLUMN,
  RESULT_COLUMN,
  ResultTag,
  SiteCell,
  checkedAsNote,
  documentPath,
} from "../components/DocumentParts";
import { FactTile } from "../components/IssueEvidence";
import ReportHeader from "../components/ReportHeader";
import { PagedTable, usePagedRows } from "../components/TablePagination";
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
} from "../components/table/Table";
import { compareText, sortWords, type Sort, type SortKind } from "../components/table/sort";
import { Card, EmptyState, ExternalLinkButton, LinkButton } from "../components/ui";
import { useScanQuery } from "../hooks/useScanQuery";
import {
  LINKED_FILE_CHECK_NAME,
  LINKED_FILE_CHECK_WHY,
  LINKED_FILE_STATUS_HELP,
  LINKED_FILE_STATUS_NOTE,
  LINKED_FILE_TYPE_LABEL,
  OPENS_NEW_WINDOW,
} from "../lib/terms";

type SortColumn = "Page title" | "Page URL";
type PagesSort = Sort<SortColumn>;
const SORT_KINDS: Record<SortColumn, SortKind> = { "Page title": "text", "Page URL": "text" };
/** The server's order: by address, A to Z. */
const DEFAULT_SORT: PagesSort = { column: "Page URL", direction: "asc" };

/**
 * One document of a report (``/scans/:id/documents/:fileId``): its facts, a
 * link that opens the file, and every page of the report it appears on.
 *
 * The document's counterpart of an issue type's record (routes/IssueDetail
 * and components/IssueEvidence): the Documents table lists the files, a
 * file's name opens this page, and this page lists its pages, as Issues
 * lists issue types and an issue type's record lists its pages. The same
 * header, fact tiles (FactTile), card with a titled bar, and table parts,
 * search, sort and pager as the issue type's page table
 * (components/IssuePagesTable), so one kind of list looks and works the same
 * on both tabs (SC 3.2.4 Consistent Identification, Level AA). The developer
 * chose this on 2026-11-14 over rows that expand, a "Show more" list in the
 * cell and a side panel; why is on DocumentsRoute.
 *
 * "Open the file" is the header's action, top right, where the page
 * inspector keeps "Open live page": the one action that leaves the app, in
 * the same place on both. Its words name the file in screen-reader text and
 * say it opens a new tab (SC 2.4.9 Link Purpose (Link Only), Level AAA; SC
 * 3.2.5 Change on Request, Level AAA). No ``aria-label``: the visible words
 * plus hidden text are the name (WCAG technique C7; AGENTS.md rule 8).
 *
 * A PDF the scan could draw shows its first page beside the facts
 * (DocumentPreview), as the Images tab shows the image itself.
 *
 * The facts are the Documents row's, as tiles: the "Accessibility problems?"
 * value with its sentence ("Mostly sure" / "it has accessibility
 * problems"), type (with "Has a form to fill in" under it), where it is
 * hosted and how many pages; then what the checks found, as a table of the
 * checks (ChecksTable), in a card with a titled bar like the pages
 * table's.
 *
 * The pages table: one row per page, however many ways it reaches the file
 * (a link and a frame on one page are one row with two lines in "How it
 * appears"). The page title opens the page inspector with the file's links
 * marked, as an issue type's page title opens it with the issue marked. The
 * address has its own column, as on the issue type's pages, so it no longer
 * sits under each title. The link's own words are in "How it appears"; they
 * left the Documents table on 2026-11-13 and come back here, where there is
 * room. Searched, sorted and paged in the browser, as the issue type's page
 * table is: the server sends at most 2,000 pages, and says so when there
 * are more.
 */
export default function DocumentDetailRoute() {
  const { scanId, fileId } = useParams<{ scanId: string; fileId: string }>();
  const id = Number(scanId);
  const file = Number(fileId);
  const location = useLocation();
  const here = `${location.pathname}${location.search}`;

  const scanQuery = useScanQuery(id);
  const documentQuery = useQuery({
    queryKey: ["scan-document", id, file],
    queryFn: () => api.getScanDocument(id, file),
    enabled: Number.isFinite(id) && Number.isFinite(file),
    retry: false,
  });

  const error = scanQuery.error ?? documentQuery.error;
  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <EmptyState
          level={1}
          title="Document not found"
          message="This document is not part of this report. The link may be out of date."
          action={
            <LinkButton to={`/scans/${id}/documents`} variant="primary">
              Go to Documents
            </LinkButton>
          }
        />
      );
    }
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        This document could not load. Nothing in the saved report has changed. Reload the page to
        try again.
      </Card>
    );
  }
  if (!scanQuery.data || !documentQuery.data) {
    return (
      <p className="text-sm text-fg-muted" role="status">
        Loading this document…
      </p>
    );
  }

  const scan = scanQuery.data;
  const { file: row, pages } = documentQuery.data;
  // Only an http(s) address is ever stored; checked again here so a stored
  // value can never become a script link.
  const openable = /^https?:\/\//i.test(row.url);

  return (
    <>
      <ReportHeader
        scanId={scan.id}
        previousScanId={scan.previous_scan_id}
        title={
          <span className="[overflow-wrap:anywhere]" data-scanned-content>
            {row.name}
          </span>
        }
        actions={
          openable && (
            <ExternalLinkButton href={row.url} variant="secondary">
              <ExternalLink className="h-4 w-4" aria-hidden />
              Open the file
              <span className="sr-only">
                {" "}
                {row.name} ({OPENS_NEW_WINDOW})
              </span>
            </ExternalLinkButton>
          )
        }
      />

      {/* The facts, then the first page when the scan drew one
          (DocumentPreview): on its right on a wide screen, under it on a
          narrow one. The same order on screen and in the page code, so a
          screen reader and the keyboard meet the facts first (SC 2.4.3
          Focus Order, Level A), and nothing scrolls sideways at 320px (SC
          1.4.10 Reflow, Level AA). */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <dl className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <FactTile
            label={RESULT_COLUMN}
            value={<ResultTag status={row.status} />}
            note={LINKED_FILE_STATUS_NOTE[row.status]}
          />
          <FactTile
            label="Type"
            value={LINKED_FILE_TYPE_LABEL[row.file_type]}
            note={row.is_form ? "Has a form to fill in" : undefined}
          />
          <FactTile label={HOSTED_COLUMN} value={<SiteCell url={row.url} offSite={row.off_site} />} />
          <FactTile label={PAGES_COLUMN} value={row.referring_page_count.toLocaleString()} />
        </dl>
        <DocumentPreview scanId={scan.id} row={row} />
      </div>

      <Card className="mt-8">
        <div className="flex flex-wrap items-baseline justify-between gap-3 rounded-t-[7px] border-b border-border bg-surface-muted px-4 py-3">
          <h2 className="text-base font-semibold">What Axcess found</h2>
        </div>
        <ChecksTable row={row} scanId={scan.id} />
      </Card>

      <Card className="mt-8">
        <div className="flex flex-wrap items-baseline justify-between gap-3 rounded-t-[7px] border-b border-border bg-surface-muted px-4 py-3">
          <h2 className="text-base font-semibold">
            {PAGES_COLUMN}
            <span className="ml-2 text-sm font-normal text-fg-muted">
              {row.referring_page_count.toLocaleString()} page{row.referring_page_count === 1 ? "" : "s"}
            </span>
          </h2>
        </div>
        <DocumentPagesTable
          scanId={scan.id}
          fileId={row.file_id}
          name={row.name}
          pages={pages}
          total={row.referring_page_count}
          backTo={here}
        />
      </Card>
    </>
  );
}

/**
 * What Axcess found, as a table of the machine checks that ran on this file:
 * what each looks at, its result, and why it matters. The checks are the
 * row's ``checks_run``: for a Word or PowerPoint file the server's list for
 * its type (seven for a Word file, six for a PowerPoint file;
 * office_check.checks_for), for a PDF the checks it was given (the five
 * every PDF gets, and those of the seven structure checks that applied;
 * pdf_check.py). So the table shows the checks that apply to this file and
 * no others (the developer's request, 2026-11-17). A check that did not
 * apply is left out rather than shown as "No problem found": a PDF with no
 * form fields was not checked for field names, and saying it had no problem
 * there would claim a check that never ran (plain-language rule 5, keep
 * text accurate to the code); the rejected option, a "Did not apply" row
 * for each, would add rows of nothing to every file. Every check that ran
 * is listed, the ones with no problem too, so a reader sees what was looked
 * at, not only what failed, and a Not sure file shows that its checks
 * passed and what a person must still check (said over the table). The
 * developer chose this on 2026-11-14 over a bullet list of sentences: the
 * table's own cell keeps a short name per problem (Found, DocumentParts.tsx)
 * and the reasons live here, where there is room.
 *
 * Row header the check (technique H63), so the result is heard with the
 * check it belongs to. The result is in words, never colour alone (SC 1.4.1
 * Use of Color, Level A): "Problem found" in bold for a check that proves a
 * barrier; "Possible problem" for a Word or PowerPoint check that does not
 * prove one on its own and never makes the file Mostly sure (table header
 * rows, headings, heading levels, link text, the document title;
 * office_check.COUNTED, the developer's two tiers of 2026-11-20), so the two are
 * told apart by their words, not their weight; "No problem found" muted.
 * Never "Passed": a machine check cannot prove a file is accessible
 * (AGENTS.md, Interface language rule 4). A file Axcess could not check has
 * no table, only why. The same table parts as every table here, so it looks
 * and reads the same.
 */
function ChecksTable({ row, scanId }: { row: LinkedFileRow; scanId: number }) {
  if (row.status === "could_not_check") {
    return (
      <div className="max-w-prose px-4 py-3 text-sm leading-6">
        <Found row={row} />
      </div>
    );
  }
  const possible = row.possible_problems ?? [];
  const checkedAs = checkedAsNote(row);
  return (
    <>
      {/* A copy: the same bytes as an earlier file in the list, at another
          address. Axcess did not read it again; the checks below are that
          file's, so the line says so and links to it (the link's words are
          the place it goes, the file's name; plain-language rule 8). */}
      {row.same_as && (
        <p className="max-w-prose px-4 pt-3 text-sm leading-6">
          Same file as{" "}
          <Link
            to={documentPath(scanId, row.same_as.file_id)}
            className="font-semibold text-umich-blue underline underline-offset-2"
          >
            <span data-scanned-content>{row.same_as.name}</span>
          </Link>
          , at another address. The results below are that file&rsquo;s.
        </p>
      )}
      {/* A Google file has no original: the checks below read the Word or
          PowerPoint file Google exports, and the reader needs that to know
          what the results are about and what to fix. */}
      {checkedAs && <p className="max-w-prose px-4 py-3 text-sm leading-6">{checkedAs}.</p>}
      {row.status === "not_sure" && (
        <p className="max-w-prose px-4 py-3 text-sm leading-6">{LINKED_FILE_STATUS_HELP.not_sure}</p>
      )}
      <TableRegion label="Checks table">
        <Table caption={`Machine checks on ${row.name}`}>
          <TableHead>
            <tr>
              <ColumnHeader>Check</ColumnHeader>
              <ColumnHeader>Result</ColumnHeader>
              <ColumnHeader>Why it matters</ColumnHeader>
            </tr>
          </TableHead>
          <tbody>
            {(row.checks_run ?? []).map((check, index) => (
              <Row key={check} index={index} className="align-top">
                <RowHeader className="min-w-[10rem] align-top">{LINKED_FILE_CHECK_NAME[check]}</RowHeader>
                <Cell className="whitespace-nowrap align-top">
                  {row.failed_checks.includes(check) ? (
                    <span className="font-semibold text-fg">Problem found</span>
                  ) : possible.includes(check) ? (
                    <span className="text-fg">Possible problem</span>
                  ) : (
                    <span className="text-fg-muted">No problem found</span>
                  )}
                </Cell>
                <Cell className="min-w-[16rem] align-top text-sm">{LINKED_FILE_CHECK_WHY[check]}</Cell>
              </Row>
            ))}
          </tbody>
        </Table>
      </TableRegion>
    </>
  );
}

function comparePages(a: DocumentPage, b: DocumentPage, column: SortColumn): number {
  return column === "Page title"
    ? compareText(a.page_title ?? "", b.page_title ?? "")
    : compareText(a.page_url, b.page_url);
}

/** A stable sort: ties keep the server's order. */
function sortPages(pages: DocumentPage[], sort: PagesSort): DocumentPage[] {
  const sign = sort.direction === "asc" ? 1 : -1;
  return pages
    .map((page, index) => ({ page, index }))
    .sort((a, b) => comparePages(a.page, b.page, sort.column) * sign || a.index - b.index)
    .map(({ page }) => page);
}

/**
 * Every page the document appears on: the issue type's page table
 * (components/IssuePagesTable) with this list's own columns. Search, sort
 * and paging work as they do there.
 */
function DocumentPagesTable({
  scanId,
  fileId,
  name,
  pages,
  total,
  backTo,
}: {
  scanId: number;
  fileId: number;
  name: string;
  pages: DocumentPage[];
  /** Every page the file appears on; more than ``pages`` when the list was cut. */
  total: number;
  backTo: string;
}) {
  const [sort, setSort] = useState<PagesSort>(DEFAULT_SORT);
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const visible = useMemo(
    () =>
      sortPages(
        needle
          ? pages.filter(
              (page) =>
                (page.page_title ?? "").toLowerCase().includes(needle) ||
                page.page_url.toLowerCase().includes(needle),
            )
          : pages,
        sort,
      ),
    [pages, needle, sort],
  );
  const paged = usePagedRows(visible, { resetKey: `${needle}|${sort.column}|${sort.direction}` });
  const offset = (paged.page - 1) * paged.pageSize;
  const sortProps = { sort, onSort: setSort };
  const cut = total > pages.length;

  if (pages.length === 0) {
    return (
      <TableEmpty>
        No scanned page links to this document. The scan reached it another way, such as the site
        map.
      </TableEmpty>
    );
  }
  return (
    <PagedTable
      pagination={{ label: PAGES_COLUMN, noun: "pages", ...paged }}
      top={(pager) => (
        <TableBar pager={pager}>
          <TableSearch label="Search pages" placeholder="Search by page title or URL" value={query} onChange={setQuery} />
        </TableBar>
      )}
    >
      <TableStatus>
        {cut ? `Showing the first ${pages.length.toLocaleString()} of ${total.toLocaleString()} pages. ` : ""}
        {needle ? `${visible.length} of ${pages.length} page${pages.length === 1 ? "" : "s"} match. ` : ""}
        Sorted by {sort.column}, {sortWords(SORT_KINDS[sort.column], sort.direction)}.
      </TableStatus>
      {visible.length === 0 ? (
        <TableEmpty>No pages match that search.</TableEmpty>
      ) : (
        <TableRegion label="Pages table">
          <Table className="min-w-[44rem]" caption={`Pages ${name} appears on`}>
            <TableHead>
              <tr>
                <ColumnHeader numeric className="w-10 whitespace-nowrap">
                  <span aria-hidden="true">#</span>
                  <span className="sr-only">Row number</span>
                </ColumnHeader>
                <SortHeader column="Page title" kind="text" {...sortProps}>
                  Page title
                </SortHeader>
                <SortHeader column="Page URL" kind="text" {...sortProps}>
                  Page URL
                </SortHeader>
                <ColumnHeader>How it appears</ColumnHeader>
              </tr>
            </TableHead>
            <tbody>
              {paged.pageRows.map((page, rowIndex) => (
                <DocumentPageRow
                  key={page.page_id}
                  page={page}
                  index={offset + rowIndex}
                  scanId={scanId}
                  fileId={fileId}
                  name={name}
                  backTo={backTo}
                />
              ))}
            </tbody>
          </Table>
        </TableRegion>
      )}
    </PagedTable>
  );
}

/** The page inspector for one page, with the links to this file marked. */
function documentInspectorPath(scanId: number, pageId: number, fileId: number, name: string, backTo: string): string {
  const params = new URLSearchParams();
  params.set("file", String(fileId));
  params.set("origin", name);
  params.set("back", backTo);
  return `/scans/${scanId}/pages/${pageId}/inspect?${params.toString()}`;
}

/** One page the document appears on. */
const DocumentPageRow = memo(function DocumentPageRow({
  page,
  index,
  scanId,
  fileId,
  name,
  backTo,
}: {
  page: DocumentPage;
  index: number;
  scanId: number;
  fileId: number;
  name: string;
  backTo: string;
}) {
  return (
    <Row index={index} className="align-top">
      <RowHeader className="text-right font-normal tabular-nums text-fg-muted">{index + 1}</RowHeader>
      <Cell className="min-w-[12rem] font-semibold text-fg">
        {/* Laid out as the issue type's page title link is (IssuePagesTable):
            44 px tall, the negative margin using the cell's own padding. */}
        <Link
          to={documentInspectorPath(scanId, page.page_id, fileId, name, backTo)}
          className="-my-2.5 inline-flex min-h-target items-start gap-1 py-2.5 text-umich-blue underline underline-offset-2"
        >
          <ScanEye className="mt-0.5 h-5 w-5 shrink-0 text-fg-subtle" aria-hidden />
          <span>{page.page_title?.trim() || <span className="font-normal">Untitled</span>}</span>
          <span className="sr-only">, opens the saved copy with the link to {name} marked</span>
        </Link>
      </Cell>
      <Cell className="min-w-[14rem] max-w-md break-all text-xs text-fg-muted">{page.page_url}</Cell>
      <Cell className="min-w-[14rem] max-w-sm text-sm">
        <HowItAppears ways={page.ways} />
      </Cell>
    </Row>
  );
});
