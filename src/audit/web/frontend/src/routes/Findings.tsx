import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Search } from "lucide-react";
import { api, blobUrl } from "../api/client";
import { AltTag, Card, EmptyState, PageHeader, SeverityChip, StatusChip } from "../components/ui";
import type {
  Classification,
  FindingListItem,
  FindingsFilter,
  FindingStatus,
  Severity,
} from "../api/types";

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

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Scans", to: "/scans" },
          { label: `Scan #${id}`, to: `/scans/${id}` },
          { label: "Findings" },
        ]}
        title="Findings"
        subtitle={
          data
            ? `${data.total.toLocaleString()} total · showing ${rows.length}`
            : "Loading…"
        }
      />

      <Card className="mb-4 p-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <FilterSelect
            label="Severity"
            value={filter.severity ?? ""}
            options={SEVERITIES}
            onChange={(v) => setParam("severity", v)}
          />
          <FilterSelect
            label="Status"
            value={filter.status ?? ""}
            options={STATUSES}
            onChange={(v) => setParam("status", v)}
          />
          <FilterSelect
            label="Classification"
            value={filter.classification ?? ""}
            options={CLASSES}
            onChange={(v) => setParam("classification", v)}
          />
          <label className="flex flex-col text-xs font-semibold uppercase tracking-wide text-fg-subtle">
            Search
            <div className="relative mt-1">
              <Search
                className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-subtle"
                aria-hidden
              />
              <input
                type="search"
                value={filter.q ?? ""}
                onChange={(e) => setParam("q", e.target.value)}
                placeholder="URL, alt, OCR…"
                className="w-full rounded-xs border border-border bg-surface py-1.5 pl-7 pr-2 text-sm font-normal normal-case tracking-normal text-fg placeholder:text-fg-subtle focus:border-umich-blue focus:outline-none"
              />
            </div>
          </label>
        </div>
      </Card>

      {error && (
        <Card className="border-sev-critical/30 bg-sev-critical-bg p-4 text-sm text-sev-critical">
          {error instanceof Error ? error.message : String(error)}
        </Card>
      )}

      {!isLoading && rows.length === 0 ? (
        <EmptyState
          title="No findings match"
          message="Try clearing a filter or widening the search."
        />
      ) : (
        <FindingsTable rows={rows} isLoading={isLoading} />
      )}

      {data && data.total_pages > 1 && (
        <nav className="mt-4 flex items-center gap-2 text-sm" aria-label="Pagination">
          <button
            className="rounded-xs border border-border bg-surface px-3 py-1 font-semibold disabled:opacity-40"
            disabled={filter.page <= 1}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set("page", String(Math.max(1, filter.page - 1)));
              setParams(next);
            }}
          >
            ← Prev
          </button>
          <span aria-current="page">
            Page {filter.page} of {data.total_pages}
          </span>
          <button
            className="rounded-xs border border-border bg-surface px-3 py-1 font-semibold disabled:opacity-40"
            disabled={filter.page >= data.total_pages}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set("page", String(filter.page + 1));
              setParams(next);
            }}
          >
            Next →
          </button>
        </nav>
      )}
    </>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col text-xs font-semibold uppercase tracking-wide text-fg-subtle">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 rounded-xs border border-border bg-surface px-2 py-1.5 text-sm font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
      >
        <option value="">any</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o.replace(/_/g, " ")}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Virtualized findings table. Only the visible rows are rendered to the
 * DOM — a 1000-finding scan still scrolls at 60fps. Thumbnails are a
 * fixed 72×48 and never expand; clicking a row opens the detail page.
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

  // Call directly each render — react-virtual's hook subscribes to scroll +
  // resize internally and triggers re-renders, so this stays in sync. A
  // useMemo([rowVirtualizer]) would *cache* the first (empty) result
  // forever because the virtualizer reference is stable across renders.
  const items = rowVirtualizer.getVirtualItems();

  return (
    <Card className="overflow-hidden">
      <div
        role="table"
        aria-label="Findings"
        aria-busy={isLoading}
        className="flex flex-col"
      >
        <div
          role="row"
          className="grid grid-cols-[6rem_5.5rem_minmax(0,1fr)_minmax(0,1fr)_8rem_minmax(0,1fr)_8rem] items-center gap-3 border-b border-border bg-surface-muted px-4 py-2 text-2xs font-semibold uppercase tracking-wide text-fg-subtle"
        >
          <span role="columnheader">Severity</span>
          <span role="columnheader">Image</span>
          <span role="columnheader">OCR text</span>
          <span role="columnheader">Alt</span>
          <span role="columnheader">Classification</span>
          <span role="columnheader">Page</span>
          <span role="columnheader">Status</span>
        </div>
        <div ref={scrollRef} className="max-h-[70vh] overflow-auto">
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
                  className="absolute inset-x-0 grid grid-cols-[6rem_5.5rem_minmax(0,1fr)_minmax(0,1fr)_8rem_minmax(0,1fr)_8rem] items-center gap-3 border-b border-border px-4 py-1.5 transition-colors hover:bg-surface-muted/60"
                >
                  <div role="cell">
                    <Link
                      to={`/findings/${f.id}`}
                      className="inline-block no-underline"
                    >
                      <SeverityChip value={f.severity} />
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
                        —
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
                      <span className="text-xs text-fg-subtle">—</span>
                    )}
                  </div>
                  <div role="cell" className="min-w-0">
                    <AltTag value={f.sample_alt} />
                  </div>
                  <div role="cell" className="text-xs text-fg-muted">
                    {f.vlm_classification ?? "—"}
                  </div>
                  <div role="cell" className="min-w-0">
                    {f.sample_page ? (
                      <Link
                        to={`/findings/${f.id}`}
                        className="block truncate text-xs text-umich-blue no-underline hover:underline"
                        title={f.sample_page}
                      >
                        {f.sample_page}
                      </Link>
                    ) : (
                      <span className="text-xs text-fg-subtle">—</span>
                    )}
                  </div>
                  <div role="cell">
                    <StatusChip value={f.status} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Card>
  );
}
