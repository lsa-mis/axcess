import { useEffect } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { ApiError, api } from "../api/client";
import type { LinkedFileRow, LinkedFileStatus } from "../api/types";
import { Found, PAGES_COLUMN, RESULT_COLUMN, ResultTag, SiteCell } from "../components/DocumentParts";
import HowSureTag from "../components/HowSureTag";
import ReportHeader from "../components/ReportHeader";
import {
  GlossaryList,
  ReportNote,
  ReportNotes,
  SummaryNumbers,
  SummaryStat,
} from "../components/ReportSummary";
import { TablePagination } from "../components/TablePagination";
import {
  Cell,
  ColumnHeader,
  Row,
  RowHeader,
  Table,
  TableBar,
  TableEmpty,
  TableHead,
  TableRegion,
} from "../components/table/Table";
import { Card, EmptyState, LinkButton, withReturnTrail } from "../components/ui";
import { useTablePageSize } from "../hooks/usePreferences";
import { useScanQuery } from "../hooks/useScanQuery";
import {
  LINKED_FILE_STATUS_HELP,
  LINKED_FILE_STATUS_LABEL,
  LINKED_FILE_STATUS_NOTE,
  LINKED_FILE_TYPE_LABEL,
} from "../lib/terms";

/** The trail label for this view; ReportCrumb and the document title use the same words. */
export const DOCUMENTS_VIEW = "Documents";

const STATUSES: readonly LinkedFileStatus[] = ["mostly_sure", "not_sure", "could_not_check"];


/** The fixed order, in words, for the table's caption and the labels note's order section. */
const ORDER_WORDS = "Mostly sure first, then Not sure, then Could not check";

/** One document's own page, where its facts and every page it appears on are listed. */
export function documentPath(scanId: number, fileId: number): string {
  return `/scans/${scanId}/documents/${fileId}`;
}

/**
 * The files a report's pages link to (``/scans/:id/documents``), the report's
 * third tab: PDF, Word, Excel, PowerPoint, OpenDocument, RTF and Google files,
 * where each is linked from, and what the PDF checks found. A web editor
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
 * The order is fixed and there are no sort buttons: the order is the answer
 * to "what do I fix first", worked out on the server
 * (audit/web/linked_files_queries.py) from the status, how many pages link to
 * the file, whether it is a form, and how serious its problem is. Each of
 * those is shown in the row, so a reader can see why a file sits where it
 * does; there is no hidden score. Rejected: sort buttons per column, which
 * would let the list lose its recommended order with nothing on screen to
 * get it back; and a single 0 to 100 score, which the developer ruled out.
 * The order is explained in the labels note, as its own section, the way
 * Issues explains Priority. No line over the table says it: Issues shows
 * that line only while its table is sorted or filtered, and this one never
 * is. The table's caption still says the order to a screen reader.
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
 * Paged by the server (Settings > Rows per page), with the page in the URL
 * so Back and reload return to the same rows. The pager is over the table
 * and again under its last row, as on every paged table (TablePagination,
 * place="end"); the copy under the table was missing here until
 * 2026-11-14. A table wider than the screen
 * scrolls sideways in its own named region, never the page (TableRegion; SC
 * 1.4.10 Reflow, Level AA, allows this for a data table).
 */
export default function DocumentsRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const pageSize = useTablePageSize();
  const rawPage = Number(params.get("page") ?? "1");
  const page = Number.isFinite(rawPage) && rawPage >= 1 ? Math.floor(rawPage) : 1;
  const offset = (page - 1) * pageSize;
  const here = `${location.pathname}${location.search}`;

  const scanQuery = useScanQuery(id);
  const filesQuery = useQuery({
    queryKey: ["scan-documents", id, pageSize, offset],
    queryFn: () => api.listScanDocuments(id, { limit: pageSize, offset }),
    placeholderData: (previous, query) => (query?.queryKey[1] === id ? keepPreviousData(previous) : undefined),
    enabled: Number.isFinite(id),
  });

  const total = filesQuery.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  // A page past the end (a smaller Rows per page setting, an old link) shows
  // the last page, as Pages visited does.
  useEffect(() => {
    if (!filesQuery.data || filesQuery.isPlaceholderData || page <= pages) return;
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (pages <= 1) next.delete("page");
        else next.set("page", String(pages));
        return next;
      },
      { replace: true },
    );
  }, [filesQuery.data, filesQuery.isPlaceholderData, page, pages, setParams]);

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
  const shownPage = Math.min(page, pages);
  const pagerProps = {
    label: DOCUMENTS_VIEW,
    noun: "documents",
    page: shownPage,
    pages,
    total,
    setPage,
    pageSize,
    pagerId: "pager-documents",
    disabled: filesQuery.isPlaceholderData,
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
          Issues shows its numbers only for a completed report.

          Each value has a short line under it that finishes it as a
          sentence ("Mostly sure" / "it has accessibility problems",
          LINKED_FILE_STATUS_NOTE): alone, the value did not say what Axcess
          is sure of. See SummaryStat's ``note``. */}
      {data.recorded && (
        <SummaryNumbers className="sm:grid-cols-4">
          <SummaryStat label={data.total === 1 ? "Document" : "Documents"} value={data.total} />
          {STATUSES.map((status) => (
            <SummaryStat
              key={status}
              label={LINKED_FILE_STATUS_LABEL[status]}
              note={LINKED_FILE_STATUS_NOTE[status]}
              value={data.counts[status]}
            />
          ))}
        </SummaryNumbers>
      )}

      <Card>
        {pages > 1 && <TableBar pager={<TablePagination {...pagerProps} />} />}
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
        ) : (
          <>
            <TableRegion label="Documents table" busy={filesQuery.isPlaceholderData}>
              <Table caption={`Documents linked from report #${scan.id}, ${ORDER_WORDS}`}>
                <TableHead>
                  <tr>
                    <ColumnHeader>Document</ColumnHeader>
                    <ColumnHeader>Type</ColumnHeader>
                    <ColumnHeader>Site</ColumnHeader>
                    <ColumnHeader>{RESULT_COLUMN}</ColumnHeader>
                    <ColumnHeader>What Axcess found</ColumnHeader>
                    <ColumnHeader>{PAGES_COLUMN}</ColumnHeader>
                  </tr>
                </TableHead>
                <tbody>
                  {data.files.map((row, index) => (
                    <DocumentRow
                      key={row.file_id}
                      row={row}
                      index={(shownPage - 1) * pageSize + index}
                      scanId={scan.id}
                      backTo={here}
                    />
                  ))}
                </tbody>
              </Table>
            </TableRegion>
            {/* The same pager again under the last row, as on every paged
                table (TablePagination, place="end"). */}
            <TablePagination {...pagerProps} place="end" />
          </>
        )}
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
 * "What was checked" for the Documents tab: the same row, title and place as
 * Issues' (ReportCoverageNote), holding what this list covers and what it
 * cannot show. Issues' row holds the table of checks; Documents has one check,
 * so its row holds short paragraphs, one idea each, about 72 characters wide
 * (52ch; SC 1.4.8 Visual Presentation, Level AAA; W3C COGA, "Making Content
 * Usable": one idea per chunk).
 *
 * In this order: the caveat, first, because a list with "Not sure" beside a
 * file could be read as a pass; which files are listed and that only PDFs
 * are checked; what Axcess downloaded and kept (a privacy fact); what the
 * list can miss; and why a report may not have looked for documents. Never
 * drop the privacy or limitation facts to make the row shorter (AGENTS.md,
 * Interface language rule 4).
 *
 * The closed row shows one fact on its right, as Issues' shows "6 of 7
 * checks ran": "Only PDFs checked", the limit a reader most needs beside the
 * numbers; or, for a report that did not look, "Not looked for", under the
 * empty table that says so in full. No longer than Issues' 17 characters:
 * "Only PDF files are checked" squeezed the title to one word a line at
 * 320px.
 */
function DocumentsCoverageNote({ recorded }: { recorded: boolean }) {
  return (
    <ReportNote
      id="report-coverage"
      title="What was checked"
      meta={recorded ? "Only PDFs checked" : "Not looked for"}
    >
      <div className="max-w-[52ch] space-y-2 text-sm leading-6 text-fg-muted">
        <p>
          Results for an expert to review. They do not prove that the files meet accessibility
          standards.
        </p>
        <p>
          This list shows the files that the scanned pages link to or show inside the page: PDF,
          Word, Excel, PowerPoint, OpenDocument, Rich Text Format (RTF) and Google files. Axcess
          checks only the PDF files.
        </p>
        <p>
          To check a PDF, Axcess downloaded it to this computer once. It kept the results, not
          the file. For a file on another site, Axcess opened that one file and did not scan the
          site.
        </p>
        <p>
          The list can miss files. A link that appears only after pressing a button is found only
          if the scan pressed it, and the scan does not press buttons that may download, buy or
          delete something.
        </p>
        <p>
          Some reports do not look for documents: reports made before Axcess could find
          documents, and scans that sign in to a site. A new scan of the site that does not sign
          in lists its documents.
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

/** One linked file. */
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
      <RowHeader className="min-w-[12rem] max-w-xs align-top">
        {/* The name opens the document's own page, as an issue type's title
            opens its record on Issues; see DocumentsRoute. */}
        <Link
          to={withReturnTrail(documentPath(scanId, row.file_id), DOCUMENTS_VIEW, backTo)}
          className="flex min-h-target items-center text-umich-blue underline underline-offset-2 hover:text-umich-blue-600"
        >
          <span className="[overflow-wrap:anywhere]" data-scanned-content>
            {row.name}
          </span>
          <span className="sr-only">, full details</span>
        </Link>
      </RowHeader>
      <Cell className="min-w-[8rem] align-top">{LINKED_FILE_TYPE_LABEL[row.file_type]}</Cell>
      <Cell className="min-w-[9rem] align-top">
        <SiteCell url={row.url} offSite={row.off_site} />
      </Cell>
      <Cell className="whitespace-nowrap align-top">
        <ResultTag status={row.status} />
      </Cell>
      <Cell className="min-w-[14rem] max-w-sm align-top text-sm">
        <Found row={row} />
      </Cell>
      <Cell numeric className="align-top">
        {row.referring_page_count.toLocaleString()}
      </Cell>
    </Row>
  );
}
