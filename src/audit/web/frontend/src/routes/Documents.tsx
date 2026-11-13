import { useEffect } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useLocation, useParams, useSearchParams } from "react-router";
import { ApiError, api } from "../api/client";
import type { LinkedFileRef, LinkedFileRow, LinkedFileStatus } from "../api/types";
import BreakableUrl from "../components/BreakableUrl";
import HowSureTag from "../components/HowSureTag";
import ReportHeader from "../components/ReportHeader";
import { SummaryNumbers, SummaryStat } from "../components/ReportSummary";
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
  TableStatus,
} from "../components/table/Table";
import { Card, EmptyState, LinkButton, PageLink } from "../components/ui";
import { useTablePageSize } from "../hooks/usePreferences";
import { useScanQuery } from "../hooks/useScanQuery";
import {
  LINKED_FILE_CHECK_TEXT,
  LINKED_FILE_REF_LABEL,
  LINKED_FILE_STATUS_HELP,
  LINKED_FILE_STATUS_LABEL,
  LINKED_FILE_TYPE_LABEL,
  OPENS_NEW_WINDOW,
  linkedFileReasonText,
} from "../lib/terms";

/** The trail label for this view; ReportCrumb and the document title use the same words. */
export const DOCUMENTS_VIEW = "Documents";

const STATUSES: readonly LinkedFileStatus[] = ["mostly_sure", "not_sure", "could_not_check"];

/** The fixed order, in words, for the line above the table and its caption. */
const ORDER_WORDS = "Mostly sure first, then Not sure, then Could not check";

function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString()} ${count === 1 ? one : many}`;
}

/**
 * The files a report's pages link to (``/scans/:id/documents``), the report's
 * third tab: PDF, Word, Excel, PowerPoint, OpenDocument, RTF and Google files,
 * where each is linked from, and what the PDF checks found. A web editor
 * opens it to decide which file to fix first.
 *
 * The header and the numbers over the table are Issues' (routes/Issues.tsx),
 * the tab beside it. The rest is laid out as Pages visited
 * (routes/PagesVisited.tsx): the same short paragraphs before the table, the
 * same table parts, paging and page links. One pattern for one kind of list (SC
 * 3.2.4 Consistent Identification, Level AA; W3C COGA, "Making Content
 * Usable", https://www.w3.org/TR/coga-usable/, paraphrased: the same pattern
 * for the same kind of thing).
 *
 * One file per row. The file names the row (its row header, `th
 * scope="row"`, technique H63) and opens the file itself in a new tab, as
 * "Open live page" opens a page: the file is the place the link goes, so its
 * name is the link's words (docs/plain-language.md rule 8), and the new tab
 * is said in screen-reader text (SC 3.2.5 Change on Request, Level AAA).
 * Then its type, the "How sure" value, what the checks found, and the pages
 * that link to it.
 *
 * "How sure" uses the Issues table's tag (components/HowSureTag.tsx) and the
 * same words for the same meaning; the key above the table says what each
 * value means in text, because the tag's hover hint is not available to
 * everyone (SC 1.4.13 Content on Hover or Focus, Level AA, and SC 3.3.2
 * Labels or Instructions, Level A, in spirit). A Not sure row says in its own
 * words what a person must still check, as the developer asked, so it can
 * never be read as a pass.
 *
 * The order is fixed and there are no sort buttons: the order is the answer
 * to "what do I fix first", worked out on the server
 * (audit/web/linked_files_queries.py) from the status, how many pages link to
 * the file, whether it is a form, and how serious its problem is. Each of
 * those is shown in the row, so a reader can see why a file sits where it
 * does; there is no hidden score. Rejected: sort buttons per column, which
 * would let the list lose its recommended order with nothing on screen to
 * get it back; and a single 0 to 100 score, which the developer ruled out.
 *
 * Each referring page is a page link that opens the page inspector, as
 * everywhere a page is named (PageLink, actions off as in Pages visited),
 * with the link's own text under it and, for a file shown inside the page or
 * reached only after a click, how. Up to 20 pages per file; the row says how
 * many there are in all.
 *
 * Paged by the server (Settings > Rows per page), with the page in the URL
 * so Back and reload return to the same rows. A table wider than the screen
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

  return (
    <>
      {/* The heading and the tabs only, as on Issues: no line under the
          heading. The counts are the numbers row below it. */}
      <ReportHeader scanId={scan.id} previousScanId={scan.previous_scan_id} title={DOCUMENTS_VIEW} tabs />

      {/* The counts as Issues shows its own: the shared row of summary
          numbers over the table (SummaryNumbers, SummaryStat), how many
          documents and then how many of each "How sure" value, in the
          table's order. Four numbers, so four across from 640px and two by
          two below that, where nothing is squeezed at 320px (SC 1.4.10
          Reflow, Level AA). Every value is shown, zero included, as Issues
          shows a zero: "0 Mostly sure" is a result the reader needs.
          Rejected: the counts in the header's meta line ("7 documents · 2
          Mostly sure"), which Issues does not have, so the two tabs put the
          same kind of fact in two places (SC 3.2.4 Consistent
          Identification, Level AA). Shown only when the report looked for
          documents: with nothing looked for, there is nothing to count, as
          Issues shows its numbers only for a completed report. */}
      {data.recorded && (
        <SummaryNumbers className="sm:grid-cols-4">
          <SummaryStat label={data.total === 1 ? "Document" : "Documents"} value={data.total} />
          {STATUSES.map((status) => (
            <SummaryStat key={status} label={LINKED_FILE_STATUS_LABEL[status]} value={data.counts[status]} />
          ))}
        </SummaryNumbers>
      )}

      {/* What the list is and what it leaves out, before the table, in short
          paragraphs, one idea each (W3C COGA, "Making Content Usable": one
          idea per chunk), about 72 characters wide (52ch), as on Pages
          visited. The caveat comes first: a list with "Not sure" beside a
          file could be read as a pass. Then what is listed and what is
          checked, the key to the three values, the order, what Axcess
          downloaded (a privacy fact, never dropped: AGENTS.md, Interface
          language rule 4), and what the list can miss. */}
      <div className="mb-5 max-w-[52ch] space-y-2 text-sm leading-6 text-fg-muted">
        <p>
          Results for an expert to review. They do not prove that the files meet accessibility
          standards.
        </p>
        {!data.recorded && (
          <p>
            This report did not look for documents. Reports made before Axcess could find
            documents, and scans that sign in to a site, do not look for them. A new scan of
            the site that does not sign in lists its documents.
          </p>
        )}
        <p>
          This list shows the files that the scanned pages link to or show inside the page: PDF,
          Word, Excel, PowerPoint, OpenDocument, Rich Text Format (RTF) and Google files. Axcess
          checks only the PDF files.
        </p>
        <dl className="space-y-2">
          {STATUSES.map((status) => (
            <div key={status}>
              <dt className="inline">
                <HowSureTag label={LINKED_FILE_STATUS_LABEL[status]} quiet={status === "could_not_check"} />
              </dt>{" "}
              <dd className="inline">{LINKED_FILE_STATUS_HELP[status]}</dd>
            </div>
          ))}
        </dl>
        <p>
          Files come in this order: {ORDER_WORDS}. Within each, files linked from more pages come
          first, then files with a form to fill in, then files with more serious problems.
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
      </div>

      <Card>
        {pages > 1 && (
          <TableBar
            pager={
              <TablePagination
                label={DOCUMENTS_VIEW}
                noun="documents"
                page={shownPage}
                pages={pages}
                total={total}
                setPage={setPage}
                pageSize={pageSize}
                pagerId="pager-documents"
                disabled={filesQuery.isPlaceholderData}
              />
            }
          />
        )}
        {!data.recorded ? (
          // One sentence: the empty line runs the card's full width, so a
          // longer message ran past 80 characters a line (SC 1.4.8 Visual
          // Presentation, Level AAA). Why, and what to do, is the paragraph
          // above, in the narrow column.
          <TableEmpty>This report did not look for documents.</TableEmpty>
        ) : data.total === 0 ? (
          <TableEmpty>The scan found no links to documents on the pages it visited.</TableEmpty>
        ) : (
          <>
            <TableStatus>In recommended order: {ORDER_WORDS}.</TableStatus>
            <TableRegion label="Documents table" busy={filesQuery.isPlaceholderData}>
              <Table caption={`Documents linked from report #${scan.id}, ${ORDER_WORDS}`}>
                <TableHead>
                  <tr>
                    <ColumnHeader>Document</ColumnHeader>
                    <ColumnHeader>Type</ColumnHeader>
                    <ColumnHeader>How sure</ColumnHeader>
                    <ColumnHeader>What Axcess found</ColumnHeader>
                    <ColumnHeader>Linked from</ColumnHeader>
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
          </>
        )}
      </Card>
    </>
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
  // Only an http(s) address is ever stored; checked again here so a stored
  // value can never become a script link.
  const openable = /^https?:\/\//i.test(row.url);
  return (
    <Row index={index} className="align-top">
      <RowHeader className="min-w-[12rem] max-w-xs align-top font-normal">
        {openable ? (
          <a
            href={row.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-target items-center gap-1 break-words font-semibold text-umich-blue underline underline-offset-2"
          >
            <span className="break-all" data-scanned-content>
              {row.name}
            </span>
            <span aria-hidden className="text-2xs">
              ↗
            </span>
            <span className="sr-only">, opens the file ({OPENS_NEW_WINDOW})</span>
          </a>
        ) : (
          <span className="font-semibold">{row.name}</span>
        )}
        <div className="break-all text-2xs text-fg-subtle">
          <BreakableUrl text={row.url} />
        </div>
        {(row.off_site || row.is_form) && (
          <ul className="mt-1 space-y-0.5 text-2xs text-fg-muted">
            {row.off_site && <li>On another site</li>}
            {row.is_form && <li>Has a form to fill in</li>}
          </ul>
        )}
      </RowHeader>
      <Cell className="min-w-[8rem] align-top">{LINKED_FILE_TYPE_LABEL[row.file_type]}</Cell>
      <Cell className="whitespace-nowrap align-top">
        <HowSureTag
          label={LINKED_FILE_STATUS_LABEL[row.status]}
          help={LINKED_FILE_STATUS_HELP[row.status]}
          quiet={row.status === "could_not_check"}
        />
      </Cell>
      <Cell className="min-w-[14rem] max-w-sm align-top text-sm">
        <Found row={row} />
      </Cell>
      <Cell className="min-w-[16rem] align-top">
        <LinkedFrom row={row} scanId={scanId} backTo={backTo} />
      </Cell>
    </Row>
  );
}

/** What the checks found, or why there was nothing to find. */
function Found({ row }: { row: LinkedFileRow }) {
  if (row.status === "mostly_sure") {
    return (
      <ul className="list-disc space-y-1 pl-4">
        {row.failed_checks.map((check) => (
          <li key={check}>{LINKED_FILE_CHECK_TEXT[check]}</li>
        ))}
      </ul>
    );
  }
  if (row.status === "not_sure") return <p>{LINKED_FILE_STATUS_HELP.not_sure}</p>;
  return <p>{row.reason ? linkedFileReasonText(row.reason, row.http_status) : LINKED_FILE_STATUS_HELP.could_not_check}</p>;
}

/** The pages that reach the file, each with its link's words and how. */
function LinkedFrom({ row, scanId, backTo }: { row: LinkedFileRow; scanId: number; backTo: string }) {
  if (row.refs.length === 0) {
    return (
      <p className="text-sm text-fg-muted">
        No scanned page links to it. The scan reached it another way, such as the site map.
      </p>
    );
  }
  const more = row.referring_page_count - new Set(row.refs.map((ref) => ref.page_id)).size;
  return (
    <div className="text-sm">
      <p className="text-fg-muted">{plural(row.referring_page_count, "page links", "pages link")} to it.</p>
      <ul className="mt-1 space-y-2">
        {row.refs.map((ref, position) => (
          <li key={`${ref.page_id}-${ref.how}-${position}`}>
            <PageLink
              pageId={ref.page_id}
              scanId={scanId}
              pageUrl={ref.page_url}
              pageTitle={ref.page_title}
              origin={DOCUMENTS_VIEW}
              backTo={backTo}
              actions={false}
            />
            <RefDetails refItem={ref} />
          </li>
        ))}
      </ul>
      {more > 0 && (
        <p className="mt-2 text-fg-muted">
          {plural(more, "more page links", "more pages link")} to it, not listed here.
        </p>
      )}
    </div>
  );
}

/** The link's own words, and how the page shows the file when it is not a plain link. */
function RefDetails({ refItem }: { refItem: LinkedFileRef }) {
  const isLink = refItem.how === "link" || refItem.how === "revealed_link";
  const how = refItem.how === "link" || refItem.how === "revealed_link" ? null : LINKED_FILE_REF_LABEL[refItem.how];
  return (
    <ul className="space-y-0.5 text-2xs text-fg-muted">
      <li>
        {isLink ? "Link text: " : "Title: "}
        {refItem.link_text ? (
          <span data-scanned-content>&ldquo;{refItem.link_text}&rdquo;</span>
        ) : (
          "none"
        )}
      </li>
      {how && <li>{how}</li>}
      {refItem.how === "revealed_link" && (
        <li>
          Appears only after pressing{" "}
          <span data-scanned-content>&ldquo;{refItem.revealed_by ?? "a control"}&rdquo;</span>
        </li>
      )}
    </ul>
  );
}
