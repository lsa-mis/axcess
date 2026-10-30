import { Link, useParams, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowLeft, Layers } from "lucide-react";
import { api, blobUrl } from "../api/client";
import { TablePagination } from "../components/TablePagination";
import { TableBar, TableSearch, TableStatus } from "../components/table/Table";
import { ActiveFilters, FilterMenu, activeFilterItems, type FilterGroup } from "../components/table/FilterMenu";
import {
  AltTag,
  Card,
  EmptyState,
  LinkButton,
  PageHeader,
  SeverityChip,
  StatusChip,
} from "../components/ui";
import type {
  Classification,
  FindingListItem,
  FindingsFilter,
  FindingStatus,
  Severity,
} from "../api/types";
import { STATUS_OPTION_LABEL } from "../lib/terms";

const SEVERITIES: Severity[] = ["critical", "major", "minor", "info"];
const STATUSES: FindingStatus[] = [
  "new",
  "reviewing",
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
];
const CLASSES: Classification[] = [
  "essential",
  "informational",
  "logo",
  "decorative",
  "no_meaningful_text",
];

const PAGE_SIZE = 200;
const FINDINGS_PAGER_ID = "pager-findings";

/** A stored value as sentence-case words: "no_meaningful_text" -> "No meaningful text". */
function sentenceCase(value: string): string {
  const words = value.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export default function FindingsRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();

  const filter: FindingsFilter = {
    page: Number(params.get("page") ?? 1),
    page_size: PAGE_SIZE,
    severity: (params.get("severity") ?? "") as Severity | "",
    status: (params.get("status") ?? "") as FindingStatus | "",
    classification: (params.get("classification") ?? "") as Classification | "",
    q: params.get("q") ?? "",
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["findings", id, filter],
    queryFn: () => api.listFindings(id, filter),
    enabled: Number.isFinite(id),
  });

  const rows = data?.findings ?? [];
  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.set("page", "1");
    setParams(next);
  };
  const option = (value: string) => ({ value, label: sentenceCase(value) });
  const filters: FilterGroup[] = [
    {
      key: "severity",
      label: "Severity",
      value: filter.severity ?? "",
      options: [{ value: "", label: "All" }, ...SEVERITIES.map(option)],
    },
    {
      key: "status",
      label: "Status",
      value: filter.status ?? "",
      options: [
        { value: "", label: "All" },
        ...STATUSES.map((value) => ({ value, label: STATUS_OPTION_LABEL[value] })),
      ],
    },
    {
      key: "classification",
      label: "Image type",
      value: filter.classification ?? "",
      options: [{ value: "", label: "All" }, ...CLASSES.map(option)],
    },
  ];
  // Every group back to "All" in one URL update; the search is its own control.
  const resetFilters = () => {
    const next = new URLSearchParams(params);
    for (const group of filters) next.delete(group.key);
    next.set("page", "1");
    setParams(next);
  };
  const empty = !isLoading && rows.length === 0;

  return (
    <>
      <PageHeader
        title="Images"
        subtitle={
          data
            ? `${data.total.toLocaleString()} images · showing ${rows.length}`
            : "Loading…"
        }
        actions={
          <>
            {/* Promote the grouped view as the *primary* action from
                this flat-table page, most of the time the user wants
                to act on *kinds of issues*, not on individual rows. The
                flat table stays the dwell page for one-off lookups
                and bulk power-user work. */}
            <LinkButton
              to={`/scans/${id}/findings/grouped`}
              variant="primary"
            >
              <Layers className="h-4 w-4" aria-hidden />
              Group by kind of issue
            </LinkButton>
            <LinkButton to={`/scans/${id}`} variant="secondary">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              Back to Report #{id}
            </LinkButton>
          </>
        }
      />

      {error && (
        <Card className="mb-4 border-sev-critical/30 bg-sev-critical-bg p-4 text-sm text-sev-critical">
          {error instanceof Error ? error.message : String(error)}
        </Card>
      )}

      {/* The search, the Filter menu and the pager in one bar over the
          list. The card stays up when nothing matches, so the filter that
          emptied the list is still there to undo. */}
      <Card className={empty ? "mb-4" : undefined}>
        <TableBar
          pager={
            data && (
              <TablePagination
                label="Images"
                noun="images"
                page={filter.page}
                pages={data.total_pages}
                total={data.total}
                pageSize={PAGE_SIZE}
                pagerId={FINDINGS_PAGER_ID}
                setPage={(page) => {
                  const next = new URLSearchParams(params);
                  next.set("page", String(page));
                  setParams(next);
                }}
              />
            )
          }
          footer={<ActiveFilters items={activeFilterItems(filters)} onClear={resetFilters} />}
        >
          <TableSearch
            label="Search"
            placeholder="Page, alt text, or image text"
            value={filter.q ?? ""}
            onChange={(v) => setParam("q", v)}
          />
          <FilterMenu
          label="Filter images" groups={filters} onChange={setParam} onReset={resetFilters} />
        </TableBar>
        <TableStatus className={empty ? "border-b-0" : undefined}>
          {data
            ? `${data.total.toLocaleString()} ${data.total === 1 ? "image" : "images"}.`
            : "Loading…"}
        </TableStatus>
        {!empty && <FindingsTable rows={rows} isLoading={isLoading} />}
      </Card>

      {empty && (
        <EmptyState
          title="No images match"
          message="Clear a filter or shorten your search."
        />
      )}
    </>
  );
}

/**
 * The table's columns, shared by its header row and its rows: Image, Preview,
 * Text read from the image, Alt text, Image type, Severity, Status, Page.
 *
 * Severity has a column of its own (2026-10-30, the developer's suggestion):
 * stacked under "Image #12" in the first cell, the two were taller than the
 * fixed row height (64 pixels) and the chip ran into the next row's link.
 * Severity and Status sit side by side, in the order the grouped images table
 * uses (Severity, Status, Pages), so the two views of the same images read
 * the same way (W3C COGA, "Making Content Usable": the same pattern for the
 * same kind of thing). Page, the widest, comes last. Image type and Status
 * are 7rem: their words fit, and the room goes to the three text columns.
 */
const COLUMNS = "grid-cols-[6rem_5.5rem_minmax(0,1fr)_minmax(0,1fr)_7rem_5.5rem_7rem_minmax(0,1fr)]";

/**
 * Virtualized findings table. Only the visible rows are rendered to the
 * DOM, a 1000-finding scan still scrolls at 60fps. Thumbnails are a
 * fixed 72×48 and never expand; clicking a row opens the detail page.
 *
 * The header row is inside the same scrolling box as the rows, so a sideways
 * scroll moves both and each header stays over its column. Until 2026-10-30
 * the header sat outside the box: scrolled sideways, the rows moved and the
 * headers did not, so every value sat under the wrong header (developer
 * report). Up and down, the header stays pinned at the top of the box
 * (`sticky`), as it did. The box keeps focus clear of the pinned header
 * (`scroll-pt-16`): a link reached by Tab is scrolled to below it, not under
 * it (SC 2.4.11 Focus Not Obscured (Minimum), Level AA).
 *
 * The table is at least 56rem wide. Narrower, its three text columns would
 * shrink to nothing; it scrolls sideways instead, which SC 1.4.10 Reflow
 * (Level AA) allows for a data table. At 1280 pixels with the sidebar open it
 * fits.
 *
 * The rows' positions count from the top of their own block, under the
 * header. The virtualizer measures from the top of the box, so the rows it
 * draws are offset by the header's height; `overscan` (8 rows, over 500
 * pixels) covers that, and no row is missing at either edge.
 */
function FindingsTable({
  rows,
  isLoading,
}: {
  rows: FindingListItem[];
  isLoading: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 64,
    overscan: 8,
  });

  // Call directly each render, react-virtual's hook subscribes to scroll +
  // resize internally and triggers re-renders, so this stays in sync. A
  // useMemo([rowVirtualizer]) would *cache* the first (empty) result
  // forever because the virtualizer reference is stable across renders.
  const items = rowVirtualizer.getVirtualItems();

  return (
    <div
      role="table"
      aria-label="Images"
      aria-busy={isLoading}
      className="flex flex-col"
    >
      <div ref={scrollRef} className="max-h-[70vh] scroll-pt-16 overflow-auto">
        <div className="min-w-[56rem]">
          <div
            role="row"
            className={`sticky top-0 z-10 grid ${COLUMNS} items-center gap-3 border-b border-border bg-surface-muted px-4 py-2 text-2xs font-semibold text-fg-muted`}
          >
            <span role="columnheader">Image</span>
            <span role="columnheader">Preview</span>
            <span role="columnheader">Text read from image (OCR)</span>
            <span role="columnheader">Alt text</span>
            <span role="columnheader">Image type</span>
            <span role="columnheader">Severity</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">Page</span>
          </div>
          <div
            style={{ height: rowVirtualizer.getTotalSize() }}
            className="relative"
          >
            {items.map((v) => {
              const f = rows[v.index];
              return (
                <div
                  key={f.id}
                  role="row"
                  style={{
                    transform: `translateY(${v.start}px)`,
                    height: v.size,
                  }}
                  className={`absolute inset-x-0 grid ${COLUMNS} items-center gap-3 border-b border-border px-4 py-1.5 transition-colors hover:bg-surface-muted/60`}
                >
                  {/* The link names its destination, "Image #12" (the detail page's
                      own title). The severity chip alone used to be the link, so
                      its words were "critical" or "info": a severity, not where
                      the link goes (SC 2.4.4 Link Purpose (In Context), Level AA).
                      The chip then sat under the link, in the same cell, until
                      2026-10-30: the two were taller than the fixed row, so the
                      chip ran into the next row's link. It has its own column
                      now (see COLUMNS). */}
                  <div role="cell">
                    <Link to={`/findings/${f.id}`} className="inline-flex min-h-target items-center text-xs font-semibold">
                      Image #{f.id}
                    </Link>
                  </div>
                  <div role="cell">
                    {f.has_svg_text ? (
                      <span className="flex h-12 w-[72px] items-center justify-center rounded-xs border border-border bg-umich-blue/10 font-mono text-2xs font-semibold text-umich-blue">
                        SVG
                      </span>
                    ) : f.content_hash ? (
                      <img
                        src={blobUrl(f.content_hash)}
                        alt=""
                        loading="lazy"
                        decoding="async"
                        width={72}
                        height={48}
                        className="h-12 w-[72px] rounded-xs border border-border bg-white object-contain"
                      />
                    ) : (
                      <span className="flex h-12 w-[72px] items-center justify-center rounded-xs border border-border text-fg-subtle">
                        No image
                      </span>
                    )}
                  </div>
                  <div role="cell" className="min-w-0">
                    {f.ocr_text ? (
                      <span
                        className="block truncate font-mono text-xs text-fg"
                        title={f.ocr_text}
                      >
                        {f.ocr_text}
                      </span>
                    ) : (
                      <span className="text-xs text-fg-subtle">No text found</span>
                    )}
                  </div>
                  <div role="cell" className="min-w-0">
                    <AltTag value={f.sample_alt} />
                  </div>
                  <div role="cell" className="text-xs text-fg-muted">
                    {f.vlm_classification ? sentenceCase(f.vlm_classification) : "Not classified"}
                  </div>
                  <div role="cell">
                    <SeverityChip value={f.severity} />
                  </div>
                  <div role="cell">
                    <StatusChip value={f.status} />
                  </div>
                  <div role="cell" className="min-w-0">
                    {f.sample_page ? (
                      // Page URL is now a real external link (target=_blank)
                      // so a click here opens the actual page that has the
                      // issue. Previously this rendered the URL as the
                      // link text but pointed at /findings/{id}, which was
                      // misleading. "Image #12" in the first column
                      // links to the image's details.
                      <a
                        href={f.sample_page}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block min-h-target truncate text-xs leading-[2.75rem] text-umich-blue underline underline-offset-2"
                        title={f.sample_page}
                      >
                        {f.sample_page}{" "}
                        <span aria-hidden>↗</span>
                        <span className="sr-only">opens in a new tab</span>
                      </a>
                    ) : (
                      <span className="text-xs text-fg-subtle">Does not apply</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
