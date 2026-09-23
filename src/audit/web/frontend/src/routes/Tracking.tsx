import { useMemo } from "react";
import { useSearchParams } from "react-router";
import Tabs from "../components/Tabs";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowDownUp, ArrowUp } from "lucide-react";
import { api } from "../api/client";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import { Card, EmptyState, PageHeader } from "../components/ui";
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
 * with a group filter (Current / Future / AI) and, where a group has its
 * own vocabulary, a second row of chips: coverage method for Current, and
 * shipped / in progress / planned for AI.
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
  const rawStatus = params.get("status") ?? "";
  const status: TrackingStatus | "" =
    view === "ai" && isStatus(rawStatus) ? rawStatus : "";
  const rawMethod = params.get("method") ?? "";
  const method: CoverageMethod | "" =
    view === "current" && data?.coverage.methods.includes(rawMethod as CoverageMethod)
      ? (rawMethod as CoverageMethod)
      : "";
  const rawSort = params.get("sort") ?? "";
  const sort: SortKey = SORT_KEYS.includes(rawSort as SortKey) ? (rawSort as SortKey) : "sc";
  const dir: SortDir = params.get("dir") === "desc" ? "desc" : "asc";

  const onSort = (key: SortKey) => {
    // Re-clicking the active column reverses it; a new column starts
    // ascending, which is what "first click" means everywhere else.
    setParam({ sort: key, dir: key === sort && dir === "asc" ? "desc" : "asc" });
  };

  const allRows = useMemo(() => (data ? buildRows(data) : []), [data]);
  const groupCounts = useMemo(() => {
    const counts: Record<Group, number> = { current: 0, future: 0, ai: 0 };
    for (const row of allRows) counts[row.group] += 1;
    return counts;
  }, [allRows]);

  const rows = useMemo(() => {
    const filtered = allRows.filter(
      (row) =>
        (!view || row.group === view) &&
        (!status || row.status === status) &&
        (!method || row.method === method),
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
    status ? STATUS_LABEL[status] : "",
    method ? methodLabel(method) : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const criteria = usePagedRows(rows, { resetKey: rows.map((row) => row.key).join(",") });
  const shipped = data?.shipped ?? [];
  const pipelines = usePagedRows(shipped, {
    param: "pipelinesPage",
    resetKey: shipped.map((p) => p.pipeline).join(","),
  });

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

        {/* Group chips first; the second row only appears for a group that
        has its own sub-vocabulary. Switching group clears the sub-filter,
        since a method or status from another group would match nothing. */}
        <Tabs
          mode="filter"
          label="Tracker sections"
          className="mb-2"
          controls="tracker-content"
          value={view || "all"}
          onChange={(key) =>
            setParam({ view: key === "all" ? "" : key, status: "", method: "" })
          }
          items={[
            { key: "all", label: `All (${allRows.length})` },
            ...GROUPS.map((g) => ({
              key: g,
              label: `${GROUP_LABEL[g]} (${groupCounts[g]})`,
            })),
          ]}
        />
        {view === "ai" && counts && (
          <Tabs
            mode="filter"
            label="Filter AI coverage by status"
            className="mb-2"
            controls="tracker-content"
            value={status || "all"}
            onChange={(key) => setParam({ status: key === "all" ? "" : key })}
            items={[
              { key: "all", label: "All" },
              ...(["shipped", "in_progress", "planned"] as const).map((key) => ({
                key,
                label: `${STATUS_LABEL[key]} (${counts[key]})`,
              })),
            ]}
          />
        )}
        {view === "current" && coverage && (
          <Tabs
            mode="filter"
            label="Filter coverage by method"
            className="mb-2"
            controls="tracker-content"
            value={method || "all"}
            onChange={(key) => setParam({ method: key === "all" ? "" : key })}
            items={[
              { key: "all", label: "All" },
              ...coverage.methods
                .filter((m) => m !== "manual")
                .map((m) => ({
                  key: m,
                  label: `${methodLabel(m)} (${coverage.by_method[m] ?? 0})`,
                })),
            ]}
          />
        )}

        <p role="status" className="mb-2 text-xs text-fg-muted">
          {isLoading
            ? "Loading tracker…"
            : `Showing ${rows.length} of ${allRows.length} rows${filterSummary ? ` · ${filterSummary}` : ""}`}
        </p>

        <div id="tracker-content">
          <Card className="overflow-x-auto">
            {/* Holds the tallest page's height, so paging never moves the pager. */}
            <div {...criteria.hold}>
            <table className="w-full text-sm">
              <caption className="sr-only">
                WCAG 2.2 A/AA coverage and AI roadmap
              </caption>
              <thead className="bg-surface-muted text-xs text-fg-muted">
                <tr>
                  <SortableTh sortKey="sc" label="SC" sort={sort} dir={dir} onSort={onSort} />
                  <SortableTh sortKey="name" label="Criterion" sort={sort} dir={dir} onSort={onSort} />
                  <SortableTh sortKey="level" label="Lvl" sort={sort} dir={dir} onSort={onSort} />
                  <SortableTh sortKey="method" label="Coverage" sort={sort} dir={dir} onSort={onSort} />
                  <Th>Status</Th>
                  <Th>What Axcess does</Th>
                  <Th>What remains</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border align-top">
                {criteria.pageRows.map((row) => (
                  <tr key={row.key} className="hover:bg-surface-muted/60">
                    <th
                      scope="row"
                      className="whitespace-nowrap px-4 py-3 text-left font-mono text-xs text-fg"
                    >
                      {row.sc}
                    </th>
                    <td className="px-4 py-3 text-fg">{row.name}</td>
                    <td className="px-4 py-3 text-xs text-fg-muted">{row.level}</td>
                    <td className="px-4 py-3 text-xs text-fg-muted">{GROUP_LABEL[row.group]}</td>
                    <td className="px-4 py-3">
                      <Badge tone={row.tone}>{row.badge}</Badge>
                    </td>
                    <td className="px-4 py-3 text-xs text-fg-muted">
                      {row.detail || <span className="text-fg-subtle">n/a</span>}
                      {row.note && (
                        <span className="mt-1 block text-2xs text-fg-subtle">{row.note}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-fg-muted">{row.remaining}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <TablePagination label="Criteria" noun="criteria" {...criteria} />
          </Card>
          {!isLoading && rows.length === 0 && (
            <EmptyState
              title="No rows match"
              message="Choose All to see every criterion and roadmap item."
            />
          )}
        </div>
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
        <Card className="overflow-x-auto">
          {/* Holds the tallest page's height, so paging never moves the pager. */}
          <div {...pipelines.hold}>
          <table className="w-full text-sm">
            <caption className="sr-only">
              Detection pipelines that run on a default crawl
            </caption>
            <thead className="bg-surface-muted text-xs text-fg-muted">
              <tr>
                <Th>Pipeline</Th>
                <Th>Engine</Th>
                <Th>WCAG coverage</Th>
                <Th>AI?</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border align-top">
              {isLoading && (
                <tr>
                  <td className="px-4 py-3 text-fg-subtle" colSpan={4}>
                    Loading…
                  </td>
                </tr>
              )}
              {pipelines.pageRows.map((p) => (
                <tr key={p.pipeline} className="hover:bg-surface-muted/60">
                  <th scope="row" className="px-4 py-3 text-left font-medium text-fg">
                    {p.name}{" "}
                    <code className="rounded bg-surface-muted px-1 text-2xs text-fg-muted">
                      {p.pipeline}
                    </code>
                    {p.note && (
                      <span className="mt-1 block text-2xs font-normal text-fg-subtle">
                        {p.note}
                      </span>
                    )}
                  </th>
                  <td className="px-4 py-3 text-fg-muted">{p.engine}</td>
                  <td className="px-4 py-3 text-fg-muted">{p.scs}</td>
                  <td className="px-4 py-3">
                    {p.needs_ai ? (
                      <span className="rounded bg-umich-blue px-2 py-0.5 text-2xs font-bold text-fg-inverse">
                        AI
                      </span>
                    ) : (
                      <span className="rounded bg-surface-muted px-2 py-0.5 text-2xs font-semibold text-fg-muted">
                        rule
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <TablePagination label="Detection pipelines" noun="pipelines" {...pipelines} />
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
const isStatus = (value: string): value is TrackingStatus =>
  value === "shipped" || value === "in_progress" || value === "planned";

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
interface Row {
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

function buildRows(data: TrackingData): Row[] {
  const rows: Row[] = [];
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

function roadmapRow(item: RoadmapItem, level: string): Row {
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
type SortDir = "asc" | "desc";

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

/** A column header that sorts, carrying its state in `aria-sort`. */
function SortableTh({
  sortKey,
  label,
  sort,
  dir,
  onSort,
}: {
  sortKey: SortKey;
  label: string;
  sort: SortKey;
  dir: SortDir;
  onSort: (key: SortKey) => void;
}) {
  const active = sort === sortKey;
  const Icon = active ? (dir === "asc" ? ArrowUp : ArrowDown) : ArrowDownUp;
  return (
    <th
      scope="col"
      aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
      className="px-4 py-2 text-left font-semibold"
    >
      {/* The label span carries the type treatment, per the house
      rule that interactive controls reset the header's text styling. */}
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className="inline-flex min-h-target items-center gap-1 font-semibold normal-case tracking-normal text-fg-subtle hover:text-fg"
      >
        <span className="">{label}</span>
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
      </button>
    </th>
  );
}

const Th = ({ children }: { children: React.ReactNode }) => (
  <th scope="col" className="px-4 py-2 text-left font-semibold">
    {children}
  </th>
);

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

