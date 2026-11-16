import { memo, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router";
import { ExternalLink, Maximize2, ScanEye } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, blobUrl } from "../api/client";
import type { ImagePage, ReportImage, ReportImageDetail } from "../api/types";
import {
  CurrentAlt,
  IMAGE_PAGES_COLUMN,
  ImageViewer,
  SuggestionBox,
  VerdictSummary,
  imageAddress,
  imageName,
} from "../components/ImageParts";
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
import { AltTag, Button, Card, EmptyState, ExternalLinkButton, LinkButton } from "../components/ui";
import { useScanQuery } from "../hooks/useScanQuery";
import { ALT_VERDICT_LABEL, OPENS_NEW_WINDOW } from "../lib/terms";

type SortColumn = "Page title" | "Page URL";
type PagesSort = Sort<SortColumn>;
const SORT_KINDS: Record<SortColumn, SortKind> = { "Page title": "text", "Page URL": "text" };
/** The server's order: by address, A to Z. */
const DEFAULT_SORT: PagesSort = { column: "Page URL", direction: "asc" };

/**
 * One image of a report (``/scans/:id/images/:imageId``): the picture, what
 * Axcess knows about its alt text, and every page of the report it appears
 * on, each opening the page inspector with the image outlined.
 *
 * The developer asked for it on 2026-11-16, following the Documents tab's
 * document page (routes/DocumentDetail.tsx on the documents branch): the
 * Images table's "Where it appears" cell named one page as a link and the
 * rest only as "and on 5 other pages", so the other pages could not be
 * reached. Now the Images table's thumbnail and name open this page, the
 * table counts the pages ("Pages it appears on"), and this page lists them,
 * as Documents lists a file's pages and Issues an issue type's (SC 3.2.4
 * Consistent Identification, Level AA). The same header, card with a titled
 * bar, and table parts, search, sort and pager as the document's page.
 *
 * The facts are a description list beside the picture, not the document
 * page's fact tiles: an image's facts are sentences (the text read in it,
 * its alt text, a suggestion with a copy button), and the tiles' large
 * single values would set them in a heading-sized font. Reading order: the
 * picture and its viewer button, then text in the image, current alt text,
 * the verdict, and the suggestion, the Images table's own column order, so
 * the two read the same (SC 1.3.2 Meaningful Sequence, Level A). Below
 * 1024px the picture is above the list, not beside it (SC 1.4.10 Reflow,
 * Level AA).
 *
 * "Open the image" is the header's action, top right, where the document's
 * page keeps "Open the file" and the page inspector "Open live page": the
 * one action that leaves the app, in the same place. "View larger image"
 * opens the image viewer the Images table used to open from its thumbnail.
 *
 * Asking the local model works as it does in the table: a press, never on
 * load; progress and the answer in a polite live region (SC 4.1.3 Status
 * Messages, Level AA); focus moves to the answer when it comes (SC 2.4.3
 * Focus Order, Level A); a failure is visible text and is announced.
 */
export default function ImageDetailRoute() {
  const { scanId, imageId } = useParams<{ scanId: string; imageId: string }>();
  const id = Number(scanId);
  const image = Number(imageId);
  const location = useLocation();
  const here = `${location.pathname}${location.search}`;
  const queryClient = useQueryClient();
  const [viewing, setViewing] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [checkError, setCheckError] = useState("");
  const answerRef = useRef<HTMLDivElement>(null);

  const scanQuery = useScanQuery(id);
  const imageQuery = useQuery({
    queryKey: ["report-image", id, image],
    queryFn: () => api.getReportImage(id, image),
    enabled: Number.isFinite(id) && Number.isFinite(image),
    retry: false,
  });

  const check = useMutation({
    mutationFn: () => api.checkImageAlt(id, image),
    onMutate: () => {
      setCheckError("");
      setAnnouncement("Asking the local AI model about this image. This can take a minute.");
    },
    onSuccess: (row: ReportImage) => {
      setAnnouncement(
        `Done. ${ALT_VERDICT_LABEL[row.verdict]}. Suggested alt text: ${row.suggestion ?? "none"}.`,
      );
      queryClient.setQueryData(["report-image", id, image], (old: ReportImageDetail | undefined) =>
        old ? { ...old, image: row } : old,
      );
      void queryClient.invalidateQueries({ queryKey: ["report-images", id] });
      // After the answer is drawn.
      window.setTimeout(() => answerRef.current?.focus(), 0);
    },
    onError: (error) => {
      const message =
        error instanceof ApiError || error instanceof Error ? error.message : "The check did not finish. Try again later.";
      setCheckError(message);
      setAnnouncement(`The check did not finish. ${message}`);
    },
  });

  const error = scanQuery.error ?? imageQuery.error;
  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <EmptyState
          level={1}
          title="Image not found"
          message="This image is not part of this report. The link may be out of date."
          action={
            <LinkButton to={`/scans/${id}/images`} variant="primary">
              Go to Images
            </LinkButton>
          }
        />
      );
    }
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        This image could not load. Nothing in the saved report has changed. Reload the page to try again.
      </Card>
    );
  }
  if (!scanQuery.data || !imageQuery.data) {
    return (
      <p className="text-sm text-fg-muted" role="status">
        Loading this image…
      </p>
    );
  }

  const scan = scanQuery.data;
  const { image: row, pages, check_available: checkAvailable } = imageQuery.data;
  const name = imageName(row);
  const address = imageAddress(row);
  const action = row.verdict === "not_checked" && row.alt_text ? "Check alt text" : "Suggest alt text";
  const busy = check.isPending;

  return (
    <>
      <ReportHeader
        scanId={scan.id}
        previousScanId={scan.previous_scan_id}
        title={
          <span className="[overflow-wrap:anywhere]" data-scanned-content>
            {name}
          </span>
        }
        actions={
          address && (
            <ExternalLinkButton href={address} variant="secondary">
              <ExternalLink className="h-4 w-4" aria-hidden />
              Open the image
              <span className="sr-only">
                {" "}
                {name} ({OPENS_NEW_WINDOW})
              </span>
            </ExternalLinkButton>
          )
        }
      />

      {/* Kept mounted, so its first message is read out. */}
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      <Card className="p-4 sm:p-5">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
          <div className="flex flex-col items-start gap-3">
            {row.has_svg_text || !row.content_hash ? (
              <p className="rounded-xs border border-border bg-surface-muted p-4 text-sm text-fg-muted">
                Text drawn in the page code (SVG). It has no picture of its own: open a page below to see it.
              </p>
            ) : (
              <>
                {/* Decorative here (alt=""): the heading names the image, and
                    its alt text and the text read from it are written out
                    beside it. */}
                <img
                  src={blobUrl(row.content_hash)}
                  alt=""
                  className="max-h-80 w-full rounded-xs border border-border bg-white object-contain"
                />
                <Button type="button" variant="secondary" onClick={() => setViewing(true)}>
                  <Maximize2 className="h-4 w-4" aria-hidden />
                  View larger image
                  <span className="sr-only">: {name}</span>
                </Button>
              </>
            )}
          </div>
          <dl className="min-w-0 space-y-4 text-sm">
            <div>
              <dt className="font-semibold text-fg-muted">Text in the image</dt>
              <dd className="mt-1 break-words" data-scanned-content>
                {row.image_text ?? <span className="text-fg-subtle">None found</span>}
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-fg-muted">Current alt text</dt>
              <dd className="mt-1">
                <CurrentAlt image={row} />
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-fg-muted">Alt text verdict</dt>
              <dd className="mt-1">
                <VerdictSummary image={row} />
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-fg-muted">Suggested alt text</dt>
              <dd className="mt-1 max-w-prose">
                {row.suggestion ? (
                  <div ref={answerRef} tabIndex={-1} className="rounded-xs focus:outline-none focus-visible:shadow-focus">
                    <SuggestionBox text={row.suggestion} name={name} />
                  </div>
                ) : !checkAvailable ? (
                  <span className="text-fg-subtle">
                    The local AI check is off, so no alt text can be suggested here. The person who runs Axcess can
                    turn it on by choosing a local model.
                  </span>
                ) : !row.can_check ? (
                  <span className="text-fg-subtle">
                    Check by hand: the model cannot look at an image drawn in the page code (SVG).
                  </span>
                ) : (
                  <>
                    {/* aria-disabled while a check runs, so focus stays on
                        the button (SC 2.4.3), as in the Images table. */}
                    <Button
                      onClick={() => {
                        if (!busy) check.mutate();
                      }}
                      aria-disabled={busy || undefined}
                      aria-describedby={checkError ? "image-check-error" : undefined}
                    >
                      {busy ? "Checking…" : action}
                      <span className="sr-only"> for {name}</span>
                    </Button>
                    {checkError && (
                      <p id="image-check-error" className="mt-2 text-xs text-sev-critical">
                        {checkError}
                      </p>
                    )}
                  </>
                )}
              </dd>
            </div>
          </dl>
        </div>
      </Card>

      <Card className="mt-8">
        <div className="flex flex-wrap items-baseline justify-between gap-3 rounded-t-[7px] border-b border-border bg-surface-muted px-4 py-3">
          <h2 className="text-base font-semibold">
            {IMAGE_PAGES_COLUMN}
            <span className="ml-2 text-sm font-normal text-fg-muted">
              {row.page_count.toLocaleString()} page{row.page_count === 1 ? "" : "s"}
            </span>
          </h2>
        </div>
        <ImagePagesTable
          scanId={scan.id}
          contentHash={row.content_hash}
          name={name}
          pages={pages}
          total={row.page_count}
          backTo={here}
        />
      </Card>

      <ImageViewer image={viewing ? row : null} onClose={() => setViewing(false)} />
    </>
  );
}

function comparePages(a: ImagePage, b: ImagePage, column: SortColumn): number {
  return column === "Page title"
    ? compareText(a.page_title ?? "", b.page_title ?? "")
    : compareText(a.page_url, b.page_url);
}

/** A stable sort: ties keep the server's order. */
function sortPages(pages: ImagePage[], sort: PagesSort): ImagePage[] {
  const sign = sort.direction === "asc" ? 1 : -1;
  return pages
    .map((page, index) => ({ page, index }))
    .sort((a, b) => comparePages(a.page, b.page, sort.column) * sign || a.index - b.index)
    .map(({ page }) => page);
}

/**
 * Every page the image appears on: the document page's table
 * (DocumentPagesTable) with this list's own last column, the alt text the
 * image has on that page, since it can differ from page to page. Search,
 * sort and paging work as they do there and on an issue type's pages.
 */
function ImagePagesTable({
  scanId,
  contentHash,
  name,
  pages,
  total,
  backTo,
}: {
  scanId: number;
  contentHash: string;
  name: string;
  pages: ImagePage[];
  /** Every page the image appears on; more than ``pages`` when the list was cut. */
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
    return <TableEmpty>No scanned page shows this image.</TableEmpty>;
  }
  return (
    <PagedTable
      pagination={{ label: IMAGE_PAGES_COLUMN, noun: "pages", ...paged }}
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
                <ColumnHeader>Alt text on this page</ColumnHeader>
              </tr>
            </TableHead>
            <tbody>
              {paged.pageRows.map((page, rowIndex) => (
                <ImagePageRow
                  key={page.page_id}
                  page={page}
                  index={offset + rowIndex}
                  scanId={scanId}
                  contentHash={contentHash}
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

/** The page inspector for one page, with every place of this image outlined. */
function imageInspectorPath(scanId: number, pageId: number, contentHash: string, name: string, backTo: string): string {
  const params = new URLSearchParams();
  params.set("image", contentHash);
  params.set("origin", name);
  params.set("back", backTo);
  return `/scans/${scanId}/pages/${pageId}/inspect?${params.toString()}`;
}

/** One page the image appears on. */
const ImagePageRow = memo(function ImagePageRow({
  page,
  index,
  scanId,
  contentHash,
  name,
  backTo,
}: {
  page: ImagePage;
  index: number;
  scanId: number;
  contentHash: string;
  name: string;
  backTo: string;
}) {
  return (
    <Row index={index} className="align-top">
      <RowHeader className="text-center font-normal tabular-nums text-fg-muted">{index + 1}</RowHeader>
      <Cell className="min-w-[12rem] font-semibold text-fg">
        {/* Laid out as the document page's title link is: 44 px tall, the
            negative margin using the cell's own padding. */}
        <Link
          to={imageInspectorPath(scanId, page.page_id, contentHash, name, backTo)}
          className="-my-2.5 inline-flex min-h-target items-start gap-1 py-2.5 text-umich-blue underline underline-offset-2"
        >
          <ScanEye className="mt-0.5 h-5 w-5 shrink-0 text-fg-subtle" aria-hidden />
          <span>{page.page_title?.trim() || <span className="font-normal">Untitled</span>}</span>
          <span className="sr-only">, opens the saved copy with {name} marked</span>
        </Link>
      </Cell>
      <Cell className="min-w-[14rem] max-w-md break-all text-xs text-fg-muted">{page.page_url}</Cell>
      <Cell className="min-w-[12rem] max-w-sm text-sm">
        <ul className="space-y-1">
          {page.alt_texts.map((alt, i) => (
            <li key={`${i}-${alt ?? "none"}`}>
              <AltTag value={alt} wrap />
            </li>
          ))}
        </ul>
      </Cell>
    </Row>
  );
});
