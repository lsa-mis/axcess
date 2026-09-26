import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import { Card, EmptyState, PageHeader } from "../components/ui";
import {
  Cell,
  ColumnHeader,
  Row,
  RowHeader,
  SortHeader,
  Table,
  TableBar,
  TableHead,
  TableRegion,
  TableStatus,
} from "../components/table/Table";
import {
  ActiveFilters,
  FilterMenu,
  activeFilterItems,
  splitFilter,
  type FilterGroup,
} from "../components/table/FilterMenu";
import { sortWords, type Sort, type SortDirection, type SortKind } from "../components/table/sort";
import type {
  CoverageMethod,
  RoadmapItem,
  TrackingData,
  TrackingStatus,
} from "../api/types";

/**
 * Product roadmap: what the tool detects today versus what's planned,
 * across every pipeline, in one table. Reads from /api/tracking, which is
 * backed by the same source of truth as docs/coverage-tracker.md
 * (coverage_status.py) so the page can't claim coverage the code lacks.
 *
 * Three lists used to sit behind three tabs — current coverage, criteria
 * not covered yet, and the AI roadmap — which meant a reader asking "where
 * does 1.4.5 stand?" had to know which tab to open. They are one table now,
 * with a section filter (Current / Future / AI) and, where a section has
 * its own vocabulary, a second group in the same Filter menu: coverage
 * method for Current, and shipped / in progress / planned for AI.
 */
export default function TrackingRoute() {
  const [params, setParams] = useSearchParams();
  const { data, isLoading, error } = useQuery({
    queryKey: ["tracking"],
    queryFn: api.getTracking,
  });

  // Filter and sort live in the URL, matching the Issues and Findings
  // pages, so a filtered view can be bookmarked or pasted into a ticket.
  const setParam = (updates: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(updates)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
  };

  const rawView = params.get("view") ?? "";
  const view: Group | "" = isGroup(rawView) ? rawView : "";
  // Status and method are checkbox groups: each a comma-separated list of
  // the checked values ("shipped,planned"), "" for all. The section stays a
  // single choice, because it decides which of the two is offered.
  const status = view === "ai" ? keepListed(params.get("status"), STATUSES) : "";
  const method =
    view === "current" && data ? keepListed(params.get("method"), listedMethods(data.coverage.methods)) : "";
  const rawSort = params.get("sort") ?? "";
  const sort: SortKey = SORT_KEYS.includes(rawSort as SortKey) ? (rawSort as SortKey) : "sc";
  const dir: SortDirection = params.get("dir") === "desc" ? "desc" : "asc";

  // Re-clicking the active column reverses it; a new column starts in its
  // kind's first direction (./components/table/sort).
  const sortProps = {
    sort: { column: sort, direction: dir } satisfies Sort<SortKey>,
    onSort: (next: Sort<SortKey>) => setParam({ sort: next.column, dir: next.direction }),
  };

  const allRows = useMemo(() => (data ? buildRows(data) : []), [data]);
  const groupCounts = useMemo(() => {
    const counts: Record<Group, number> = { current: 0, future: 0, ai: 0 };
    for (const row of allRows) counts[row.group] += 1;
    return counts;
  }, [allRows]);

  const rows = useMemo(() => {
    const statuses = new Set<string>(splitFilter(status));
    const methods = new Set<string>(splitFilter(method));
    const filtered = allRows.filter(
      (row) =>
        (!view || row.group === view) &&
        (!statuses.size || (row.status !== undefined && statuses.has(row.status))) &&
        (!methods.size || (row.method !== undefined && methods.has(row.method))),
    );
    filtered.sort((a, b) => {
      const by =
        sort === "sc"
          ? compareSc(a.sc, b.sc)
          : sort === "name"
            ? a.name.localeCompare(b.name)
            : sort === "level"
              ? a.level.localeCompare(b.level) || compareSc(a.sc, b.sc)
              : GROUPS.indexOf(a.group) - GROUPS.indexOf(b.group) ||
                a.badge.localeCompare(b.badge) ||
                compareSc(a.sc, b.sc);
      return dir === "asc" ? by : -by;
    });
    return filtered;
  }, [allRows, view, status, method, sort, dir]);

  const coverage = data?.coverage;
  const counts = data?.counts;
  const methodLabel = (m: CoverageMethod) => coverage?.method_labels[m] ?? m;
  const deterministicCount = data?.shipped.filter((p) => !p.needs_ai).length ?? 0;
  const aiCount = (data?.shipped.length ?? 0) - deterministicCount;

  const filterSummary = [
    view ? GROUP_LABEL[view] : "",
    splitFilter(status)
      .map((key) => STATUS_LABEL[key as TrackingStatus])
      .join(", "),
    splitFilter(method)
      .map((key) => methodLabel(key as CoverageMethod))
      .join(", "),
  ]
    .filter(Boolean)
    .join(" · ");
  // One Filter menu for the table. The section's own vocabulary (method
  // for Current, status for AI) only appears inside that section.
  const filterGroups: FilterGroup[] = [
    {
      key: "view",
      label: "Section",
      value: view,
      options: [
        { value: "", label: "All", count: allRows.length },
        ...GROUPS.map((g) => ({ value: g, label: GROUP_LABEL[g], count: groupCounts[g] })),
      ],
    },
  ];
  if (view === "ai" && counts) {
    filterGroups.push({
      key: "status",
      label: "Status",
      value: status,
      multiple: true,
      options: STATUSES.map((key) => ({ value: key, label: STATUS_LABEL[key], count: counts[key] })),
    });
  }
  if (view === "current" && coverage) {
    filterGroups.push({
      key: "method",
      label: "Coverage method",
      value: method,
      multiple: true,
      options: listedMethods(coverage.methods).map((m) => ({
        value: m,
        label: methodLabel(m),
        count: coverage.by_method[m] ?? 0,
      })),
    });
  }
  // Switching section clears the sub-filter, since a method or status from
  // another section would match nothing.
  const onFilter = (key: string, value: string) =>
    setParam(key === "view" ? { view: value, status: "", method: "" } : { [key]: value });
  const clearFilters = () => setParam({ view: "", status: "", method: "" });

  const criteria = usePagedRows(rows, { resetKey: `${view}|${status}|${method}|${sort}|${dir}` });
  const shipped = useMemo(() => data?.shipped ?? [], [data]);
  const shippedKey = useMemo(() => shipped.map((p) => p.pipeline).join(","), [shipped]);
  const pipelines = usePagedRows(shipped, { param: "pipelinesPage", resetKey: shippedKey });

  return (
    <>
      <PageHeader
        title="Product Roadmap"
        subtitle="What the tool detects today versus what's planned. Status is reconciled against the actual code."
      />

      {error && (
        <Card className="mb-4 border-sev-critical-bg p-4">
          <p className="text-sm text-sev-critical" role="alert">
            {error instanceof Error ? error.message : String(error)}
          </p>
        </Card>
      )}

      <section aria-labelledby="roadmap-h" className="mb-8">
        <h2 id="roadmap-h" className="mb-1 text-base font-semibold text-fg">
          Coverage and roadmap
        </h2>
        <p className="mb-3 text-sm text-fg-muted">
          Every WCAG 2.2 A/AA criterion, with what Axcess checks today, what
          still needs manual testing, and the AI analyzers queued to close the
          gap. Coverage does not mean every requirement is tested; the last
          column is what you must still check yourself.
        </p>

        <Card>
          <TableBar
            pager={<TablePagination label="Criteria" noun="criteria" {...criteria} />}
            footer={<ActiveFilters items={activeFilterItems(filterGroups)} onClear={clearFilters} />}
          >
            <FilterMenu groups={filterGroups} onChange={onFilter} onReset={clearFilters} />
          </TableBar>
          <TableStatus
            actions={
              <p role="status">
                {isLoading
                  ? "Loading tracker…"
                  : `Showing ${rows.length} of ${allRows.length} rows${filterSummary ? ` · ${filterSummary}` : ""}`}
              </p>
            }
          >
            Sorted by {SORT_LABELS[sort]}, {sortWords(SORT_KINDS[sort], dir)}.
          </TableStatus>
          <TableRegion label="Coverage and roadmap table" paged={criteria}>
            <Table caption="WCAG 2.2 A/AA coverage and AI roadmap">
              <TableHead>
                <tr>
                  <SortHeader column="sc" kind={SORT_KINDS.sc} {...sortProps}>
                    SC
                  </SortHeader>
                  <SortHeader column="name" kind={SORT_KINDS.name} {...sortProps}>
                    Criterion
                  </SortHeader>
                  <SortHeader column="level" kind={SORT_KINDS.level} {...sortProps}>
                    Lvl
                  </SortHeader>
                  <SortHeader column="method" kind={SORT_KINDS.method} {...sortProps}>
                    Coverage
                  </SortHeader>
                  <ColumnHeader>Status</ColumnHeader>
                  <ColumnHeader>What Axcess does</ColumnHeader>
                  <ColumnHeader>What remains</ColumnHeader>
                </tr>
              </TableHead>
              <tbody>
                {criteria.pageRows.map((row, index) => (
                  <Row key={row.key} index={(criteria.page - 1) * criteria.pageSize + index}>
                    <RowHeader className="whitespace-nowrap font-mono text-xs text-fg">{row.sc}</RowHeader>
                    <Cell className="text-fg">{row.name}</Cell>
                    <Cell className="text-xs text-fg-muted">{row.level}</Cell>
                    <Cell className="text-xs text-fg-muted">{GROUP_LABEL[row.group]}</Cell>
                    <Cell>
                      <Badge tone={row.tone}>{row.badge}</Badge>
                    </Cell>
                    <Cell className="text-xs text-fg-muted">
                      {row.detail || "n/a"}
                      {row.note && <span className="mt-1 block text-2xs">{row.note}</span>}
                    </Cell>
                    <Cell className="text-xs text-fg-muted">{row.remaining}</Cell>
                  </Row>
                ))}
              </tbody>
            </Table>
          </TableRegion>
        </Card>
        {!isLoading && rows.length === 0 && (
          <EmptyState
            title="No rows match"
            message="Choose All to see every criterion and roadmap item."
          />
        )}
      </section>

      <section aria-labelledby="shipped-h" className="mb-8">
        <h2 id="shipped-h" className="mb-1 text-base font-semibold text-fg">
          Shipped Pipelines, What Runs Today
        </h2>
        {/* Counted from the data, not written down: the previous sentence
        said "three deterministic, two AI" and had been wrong since two
        pipelines shipped. */}
        <p className="mb-3 text-sm text-fg-muted">
          The {deterministicCount} deterministic pipelines need only chromium
          (no Ollama); the {aiCount} AI pipelines need a local Ollama daemon.
        </p>
        <Card>
          {pipelines.pages > 1 && (
            <TableBar pager={<TablePagination label="Detection pipelines" noun="pipelines" {...pipelines} />} />
          )}
          <TableRegion label="Detection pipelines table" paged={pipelines}>
            <Table caption="Detection pipelines that run on a default crawl">
              <TableHead>
                <tr>
                  <ColumnHeader>Pipeline</ColumnHeader>
                  <ColumnHeader>Engine</ColumnHeader>
                  <ColumnHeader>WCAG coverage</ColumnHeader>
                  <ColumnHeader>AI?</ColumnHeader>
                </tr>
              </TableHead>
              <tbody>
                {isLoading && (
                  <tr className="border-t border-border">
                    <td className="px-2 py-2.5 text-fg-muted" colSpan={4}>
                      Loading…
                    </td>
                  </tr>
                )}
                {pipelines.pageRows.map((p, index) => (
                  <Row key={p.pipeline} index={(pipelines.page - 1) * pipelines.pageSize + index}>
                    <RowHeader className="font-medium text-fg">
                      {p.name}{" "}
                      <code className="rounded bg-surface-muted px-1 text-2xs text-fg-muted">
                        {p.pipeline}
                      </code>
                      {p.note && (
                        <span className="mt-1 block text-2xs font-normal text-fg-muted">
                          {p.note}
                        </span>
                      )}
                    </RowHeader>
                    <Cell className="text-fg-muted">{p.engine}</Cell>
                    <Cell className="text-fg-muted">{p.scs}</Cell>
                    <Cell>
                      {p.needs_ai ? (
                        <span className="rounded bg-umich-blue px-2 py-0.5 text-2xs font-bold text-fg-inverse">
                          AI
                        </span>
                      ) : (
                        <span className="rounded bg-surface-muted px-2 py-0.5 text-2xs font-semibold text-fg-muted">
                          rule
                        </span>
                      )}
                    </Cell>
                  </Row>
                ))}
              </tbody>
            </Table>
          </TableRegion>
        </Card>
      </section>

      <p className="mt-4 text-xs text-fg-subtle">
        Long-form version with the verification map:{" "}
        <code>docs/coverage-tracker.md</code>.
      </p>
    </>
  );
}

// --- Row model --------------------------------------------------------

const GROUPS = ["current", "future", "ai"] as const;
type Group = (typeof GROUPS)[number];

const GROUP_LABEL: Record<Group, string> = {
  current: "Current Coverage",
  future: "Future Coverage",
  ai: "AI Coverage",
};

const isGroup = (value: string): value is Group => (GROUPS as readonly string[]).includes(value);
const STATUSES = ["shipped", "in_progress", "planned"] as const satisfies readonly TrackingStatus[];

/** The methods the Coverage method filter offers: "manual" rows are Future Coverage. */
const listedMethods = (methods: readonly CoverageMethod[]) => methods.filter((m) => m !== "manual");

/**
 * A checkbox filter's parameter kept to the values it offers, in their order:
 * "planned,shipped,nope" → "shipped,planned". "" is every row.
 */
function keepListed(raw: string | null, allowed: readonly string[]): string {
  const on = new Set(splitFilter(raw ?? ""));
  return allowed.filter((value) => on.has(value)).join(",");
}

/** Human labels for the roadmap status enum (never the raw key). */
const STATUS_LABEL: Record<TrackingStatus, string> = {
  shipped: "Shipped",
  in_progress: "In progress",
  planned: "Planned",
};

/**
 * One line of the merged table. Coverage criteria and roadmap items carry
 * different fields, so each is flattened to the same shape up front and
 * the table never has to branch on where a row came from.
 */
interface TrackerRow {
  key: string;
  sc: string;
  name: string;
  level: string;
  group: Group;
  method?: CoverageMethod;
  status?: TrackingStatus;
  badge: string;
  tone: string;
  detail: string;
  remaining: string;
  note?: string;
}

// Badge fills: dark tones paired with white for AAA contrast (≥7:1).
const METHOD_TONE: Record<CoverageMethod, string> = {
  automated: "bg-[#0f5132]",
  partial: "bg-[#0b4f6c]",
  "ai-assisted": "bg-[#6b3a00]",
  manual: "bg-[#374151]",
};
const STATUS_TONE: Record<TrackingStatus, string> = {
  shipped: "bg-[#0f5132]",
  in_progress: "bg-[#6b3a00]",
  planned: "bg-[#374151]",
};

function buildRows(data: TrackingData): TrackerRow[] {
  const rows: TrackerRow[] = [];
  const levelBySc = new Map<string, string>();
  for (const c of data.coverage.criteria) {
    levelBySc.set(c.sc, c.level);
    const future = c.method === "manual";
    rows.push({
      key: `cov:${c.sc}`,
      sc: c.sc,
      name: c.name,
      level: c.level,
      group: future ? "future" : "current",
      method: c.method,
      badge: future ? "Not covered yet" : data.coverage.method_labels[c.method],
      tone: METHOD_TONE[c.method],
      detail: c.automated_check,
      remaining: c.manual_check,
    });
  }
  for (const item of data.roadmap) rows.push(roadmapRow(item, levelBySc.get(item.wcag) ?? ""));
  return rows;
}

function roadmapRow(item: RoadmapItem, level: string): TrackerRow {
  return {
    key: `ai:${item.wcag}`,
    sc: item.wcag,
    name: item.issue,
    level,
    group: "ai",
    status: item.status,
    badge: STATUS_LABEL[item.status],
    tone: STATUS_TONE[item.status],
    detail: item.what,
    note: item.note || undefined,
    remaining: [item.model_class && `Model: ${item.model_class}`, item.reuse && `Reuses: ${item.reuse}`]
      .filter(Boolean)
      .join(". "),
  };
}

// --- Sorting ----------------------------------------------------------

const SORT_KEYS = ["sc", "name", "level", "method"] as const;
type SortKey = (typeof SORT_KEYS)[number];

// Criterion numbers order as numbers (compareSc); the rest as text.
const SORT_KINDS: Record<SortKey, SortKind> = {
  sc: "number",
  name: "text",
  level: "text",
  method: "text",
};

/** Column names as the status line says them. */
const SORT_LABELS: Record<SortKey, string> = {
  sc: "SC",
  name: "Criterion",
  level: "Level",
  method: "Coverage",
};

/**
 * Compare success-criterion numbers as numbers, not strings: sorted as
 * text, "1.4.10" lands before "1.4.4", which is the order the matrix
 * itself is careful to avoid.
 */
function compareSc(a: string, b: string): number {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < Math.max(left.length, right.length); i += 1) {
    const diff = (left[i] ?? 0) - (right[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

/**
 * Status pill. Colour is backed by a text label (never colour alone) so
 * the badge clears WCAG 1.4.1; each fill is a dark tone paired with white
 * for AAA contrast (≥7:1).
 */
function Badge({ tone, children }: { tone: string; children: React.ReactNode }) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded px-2 py-0.5 text-2xs font-bold text-white ${tone}`}
    >
      {children}
    </span>
  );
}

