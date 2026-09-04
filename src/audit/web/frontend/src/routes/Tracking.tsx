import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowDownUp, ArrowUp } from "lucide-react";
import { api } from "../api/client";
import { cn } from "../lib/cn";
import { Button, Card, EmptyState, PageHeader } from "../components/ui";
import type {
  CoverageCriterion,
  CoverageData,
  CoverageMethod,
  RoadmapItem,
  TrackingStatus,
} from "../api/types";

/**
 * Coverage & feature tracker — what the tool detects today versus what's
 * planned, across every pipeline. Reads from /api/tracking, which is
 * backed by the same source of truth as docs/coverage-tracker.md
 * (coverage_status.py) so the page can't claim coverage the code lacks.
 */
export default function TrackingRoute() {
  const [params, setParams] = useSearchParams();
  const requestedView = params.get("view");
  const view = requestedView === "roadmap" || requestedView === "pipelines" || requestedView === "uncovered" ? requestedView : "coverage";
  const status = params.get("status");
  const roadmapStatus = status === "shipped" || status === "in_progress" || status === "planned" ? status : "";
  const select = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };
  const { data, isLoading, error } = useQuery({
    queryKey: ["tracking"],
    queryFn: api.getTracking,
  });

  const counts = data?.counts;
  const deterministicCount =
    data?.shipped.filter((p) => !p.needs_ai).length ?? 0;
  const aiCount = (data?.shipped.length ?? 0) - deterministicCount;

  return (
    <>
      <PageHeader
        title="Coverage & Feature Tracker"
        subtitle="What the tool detects today versus what's planned. Status is reconciled against the actual code."
      />

      {error && (
        <Card className="mb-4 border-sev-critical-bg p-4">
          <p className="text-sm text-sev-critical" role="alert">
            {error instanceof Error ? error.message : String(error)}
          </p>
        </Card>
      )}

      <div role="group" aria-label="Tracker sections" className="mb-5 flex flex-wrap gap-2 rounded-lg border border-border bg-surface-muted p-2">
        {([
          ["coverage", "Current coverage"],
          ["uncovered", "Not covered yet"],
          ["roadmap", "AI roadmap"],
          ["pipelines", "Shipped pipelines"],
        ] as const).map(([key, label]) => (
          <Button key={key} variant={view === key ? "primary" : "ghost"} aria-pressed={view === key} aria-controls="tracker-content" onClick={() => select("view", key)} className="rounded-lg transition-none">
            {label}
          </Button>
        ))}
      </div>
      <p role="status" className="sr-only">Showing {view === "coverage" ? "current coverage" : view === "roadmap" ? "AI roadmap" : view === "uncovered" ? "criteria not covered yet" : "shipped pipelines"}</p>
      {isLoading && <p role="status">Loading tracker…</p>}
      <div id="tracker-content">
      {(view === "coverage" || view === "uncovered") && data?.coverage && <CoverageSection coverage={data.coverage} notCovered={view === "uncovered"} />}

      {view === "roadmap" && <section aria-labelledby="roadmap-h" className="mb-8">
        <h2 id="roadmap-h" className="mb-1 text-base font-semibold text-fg">
          AI Roadmap
        </h2>
        <p className="mb-3 text-sm text-fg-muted">
          The queue to close the AI coverage gap. A criterion listed in the
          orchestrator&apos;s default criteria but with no analyzer class is
          skipped at runtime — those read “planned,” not “shipped.”
        </p>
        {counts && (
          <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Filter roadmap by status">
            <Button className="transition-none" variant={roadmapStatus ? "ghost" : "primary"} aria-pressed={!roadmapStatus} onClick={() => select("status", "")}>All</Button>
            {(["shipped", "in_progress", "planned"] as const).map((key) => (
              <Button className="transition-none" key={key} variant={roadmapStatus === key ? "primary" : "ghost"} aria-pressed={roadmapStatus === key} onClick={() => select("status", key)}>
                {STATUS_LABEL[key]} ({counts[key]})
              </Button>
            ))}
          </div>
        )}
        <p role="status" className="mb-2 text-xs text-fg-muted">Showing {data?.roadmap.filter((item) => !roadmapStatus || item.status === roadmapStatus).length ?? 0} roadmap items{roadmapStatus ? ` · ${STATUS_LABEL[roadmapStatus]}` : ""}</p>
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Planned AI analyzers by WCAG criterion
            </caption>
            <thead className="bg-surface-muted text-xs uppercase tracking-wide text-fg-muted">
              <tr>
                <Th>SC</Th>
                <Th>Criterion</Th>
                <Th>Status</Th>
                <Th>Model class</Th>
                <Th>What the AI step does</Th>
                <Th>Reuses</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border align-top">
              {data?.roadmap.filter((item) => !roadmapStatus || item.status === roadmapStatus).map((r) => (
                <RoadmapRow key={r.wcag} item={r} />
              ))}
            </tbody>
          </table>
        </Card>
      </section>}

      {view === "pipelines" && <section aria-labelledby="shipped-h" className="mb-8">
        <h2 id="shipped-h" className="mb-1 text-base font-semibold text-fg">
          Shipped Pipelines — What Runs Today
        </h2>
        {/* Counted from the data, not written down: the previous sentence
        said "three deterministic, two AI" and had been wrong since two
        pipelines shipped. */}
        <p className="mb-3 text-sm text-fg-muted">
          The {deterministicCount} deterministic pipelines need only chromium
          (no Ollama); the {aiCount} AI pipelines need a local Ollama daemon.
        </p>
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Detection pipelines that run on a default crawl
            </caption>
            <thead className="bg-surface-muted text-xs uppercase tracking-wide text-fg-muted">
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
              {data?.shipped.map((p) => (
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
        </Card>
      </section>}
      </div>

      <p className="mt-4 text-xs text-fg-subtle">
        Long-form version with the verification map:{" "}
        <code>docs/coverage-tracker.md</code>.
      </p>
    </>
  );
}

/** Human labels for the roadmap status enum (never the raw key). */
const STATUS_LABEL: Record<TrackingStatus, string> = {
  shipped: "Shipped",
  in_progress: "In progress",
  planned: "Planned",
};

function RoadmapRow({ item }: { item: RoadmapItem }) {
  return (
    <tr className="hover:bg-surface-muted/60">
      <th scope="row" className="whitespace-nowrap px-4 py-3 text-left font-mono text-xs text-fg">
        {item.wcag}
      </th>
      <td className="px-4 py-3 text-fg">{item.issue}</td>
      <td className="px-4 py-3">
        <StatusBadge status={item.status}>
          {STATUS_LABEL[item.status]}
        </StatusBadge>
      </td>
      <td className="px-4 py-3 text-xs text-fg-muted">{item.model_class}</td>
      <td className="px-4 py-3 text-fg-muted">
        {item.what}
        {item.note && (
          <span className="mt-1 block text-2xs text-fg-subtle">{item.note}</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-fg-subtle">{item.reuse}</td>
    </tr>
  );
}

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
      {/* The uppercase treatment stays on the label span, per the house
      rule that interactive controls reset the header's text styling. */}
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className="inline-flex min-h-target items-center gap-1 font-semibold normal-case tracking-normal text-fg-subtle hover:text-fg"
      >
        <span className="uppercase tracking-wide">{label}</span>
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
      </button>
    </th>
  );
}

/** A count tile that also filters the table below it. */
function FilterTile({
  active,
  onClick,
  count,
  blurb,
  label,
  badge,
}: {
  active: boolean;
  onClick: () => void;
  count: number;
  blurb: string;
  label?: string;
  badge?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "min-h-target rounded-xs border p-3 text-left",
        active
          ? "border-umich-blue bg-umich-blue text-fg-inverse"
          : "border-border bg-surface text-fg hover:bg-surface-muted",
      )}
    >
      <span className="flex items-baseline justify-between gap-2">
        {badge ?? <span className="text-2xs font-bold uppercase">{label}</span>}
        <span className="text-lg font-bold tabular-nums">{count}</span>
      </span>
      <span
        className={cn(
          "mt-1.5 block text-2xs leading-snug",
          active ? "text-fg-inverse" : "text-fg-subtle",
        )}
      >
        {blurb}
      </span>
    </button>
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
function StatusBadge({
  status,
  children,
}: {
  status: TrackingStatus;
  children: React.ReactNode;
}) {
  const tone: Record<TrackingStatus, string> = {
    shipped: "bg-[#0f5132]",
    in_progress: "bg-[#6b3a00]",
    planned: "bg-[#374151]",
  };
  return (
    <span
      className={`inline-block whitespace-nowrap rounded px-2 py-0.5 text-2xs font-bold text-white ${tone[status]}`}
    >
      {children}
    </span>
  );
}

// Method fills: dark tones paired with white for AAA contrast (≥7:1).
const METHOD_TONE: Record<CoverageMethod, string> = {
  automated: "bg-[#0f5132]",
  partial: "bg-[#0b4f6c]",
  "ai-assisted": "bg-[#6b3a00]",
  manual: "bg-[#374151]",
};

function CoverageMethodBadge({
  method,
  label,
}: {
  method: CoverageMethod;
  label: string;
}) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded px-2 py-0.5 text-2xs font-bold text-white ${METHOD_TONE[method]}`}
    >
      {label}
    </span>
  );
}

/**
 * The honest WCAG 2.2 A/AA coverage breakdown — what Axcess checks
 * automatically, what it AI-assists, and (the long tail) what still needs
 * manual testing. Rendered straight from the coverage matrix so it can't
 * over-claim. The "What you must still test" column is the whole point.
 */
function CoverageSection({ coverage: fullCoverage, notCovered = false }: { coverage: CoverageData; notCovered?: boolean }) {
  const coverage = useMemo(() => {
    const criteria = fullCoverage.criteria.filter((criterion) => (criterion.method === "manual") === notCovered);
    return {
      ...fullCoverage,
      criteria,
      total: criteria.length,
      methods: fullCoverage.methods.filter((method) => (method === "manual") === notCovered),
    };
  }, [fullCoverage, notCovered]);
  const label = (m: CoverageMethod) => coverage.method_labels[m];
  const [params, setParams] = useSearchParams();

  // Filter and sort live in the URL, matching the Issues and Findings
  // pages, so a filtered view can be bookmarked or pasted into a ticket.
  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const rawMethod = params.get("method") ?? "";
  const method = (
    coverage.methods.includes(rawMethod as CoverageMethod) ? rawMethod : ""
  ) as CoverageMethod | "";
  const rawSort = params.get("sort") ?? "";
  const sort: SortKey = SORT_KEYS.includes(rawSort as SortKey)
    ? (rawSort as SortKey)
    : "sc";
  const dir: SortDir = params.get("dir") === "desc" ? "desc" : "asc";

  const onSort = (key: SortKey) => {
    const next = new URLSearchParams(params);
    next.set("sort", key);
    // Re-clicking the active column reverses it; a new column starts
    // ascending, which is what "first click" means everywhere else.
    next.set("dir", key === sort && dir === "asc" ? "desc" : "asc");
    setParams(next, { replace: true });
  };

  const rows = useMemo(() => {
    const filtered = method
      ? coverage.criteria.filter((c) => c.method === method)
      : [...coverage.criteria];
    const rank = (m: CoverageMethod) => coverage.methods.indexOf(m);
    filtered.sort((a, b) => {
      const by =
        sort === "sc"
          ? compareSc(a.sc, b.sc)
          : sort === "name"
            ? a.name.localeCompare(b.name)
            : sort === "level"
              ? a.level.localeCompare(b.level) || compareSc(a.sc, b.sc)
              : rank(a.method) - rank(b.method) || compareSc(a.sc, b.sc);
      return dir === "asc" ? by : -by;
    });
    return filtered;
  }, [coverage.criteria, coverage.methods, method, sort, dir]);

  return (
    <section aria-labelledby="cov-h" className="mb-8">
      <h2 id="cov-h" className="mb-3 text-base font-semibold text-fg">
        {notCovered ? "Not covered yet" : "Current Coverage"}
      </h2>
      <p className="mb-3 text-sm text-fg-muted">
        {notCovered
          ? "Axcess has no automated detection for these WCAG 2.2 A/AA criteria yet. They require manual testing; this list does not imply an implementation is planned."
          : "WCAG 2.2 A/AA criteria with an implemented automated, partial, or AI-assisted check. Coverage does not mean every requirement is tested; review the manual checks below."}
      </p>

      {/* The method tiles double as the table's filter. They already
      carried the counts, so making them the control removes a separate
      filter row and keeps the number and the thing it filters together. */}
      {!notCovered && <div
        role="group"
        aria-label="Filter coverage by method"
        className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4"
      >
        <FilterTile
          active={!method}
          onClick={() => setParam("method", "")}
          count={coverage.total}
          blurb="Criteria with an implemented Axcess check."
          label="All"
        />
        {coverage.methods.map((m) => (
          <FilterTile
            key={m}
            active={method === m}
            onClick={() => setParam("method", m)}
            count={coverage.by_method[m] ?? 0}
            blurb={coverage.method_blurb[m]}
            badge={<CoverageMethodBadge method={m} label={label(m)} />}
          />
        ))}
      </div>}

      <p role="status" className="mb-2 text-xs text-fg-muted">
        Showing {rows.length} of {coverage.total} criteria
        {method ? ` · ${label(method)}` : ""}
      </p>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">
            {notCovered ? "WCAG 2.2 A/AA criteria not covered by Axcess yet" : "WCAG 2.2 A/AA criteria with current Axcess coverage"}
          </caption>
          <thead className="bg-surface-muted text-xs uppercase tracking-wide text-fg-muted">
            <tr>
              <SortableTh sortKey="sc" label="SC" sort={sort} dir={dir} onSort={onSort} />
              <SortableTh
                sortKey="name"
                label="Criterion"
                sort={sort}
                dir={dir}
                onSort={onSort}
              />
              <SortableTh sortKey="level" label="Lvl" sort={sort} dir={dir} onSort={onSort} />
              <SortableTh
                sortKey="method"
                label="Coverage"
                sort={sort}
                dir={dir}
                onSort={onSort}
              />
              <Th>What Axcess does</Th>
              <Th>What you must still test</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border align-top">
            {rows.map((c: CoverageCriterion) => (
              <tr key={c.sc} className="hover:bg-surface-muted/60">
                <th
                  scope="row"
                  className="whitespace-nowrap px-4 py-3 text-left font-mono text-xs text-fg"
                >
                  {c.sc}
                </th>
                <td className="px-4 py-3 text-fg">{c.name}</td>
                <td className="px-4 py-3 text-xs text-fg-muted">{c.level}</td>
                <td className="px-4 py-3">
                  <CoverageMethodBadge method={c.method} label={notCovered ? "Not covered yet" : label(c.method)} />
                </td>
                <td className="px-4 py-3 text-xs text-fg-muted">
                  {c.automated_check || <span className="text-fg-subtle">—</span>}
                </td>
                <td className="px-4 py-3 text-xs text-fg-muted">
                  {c.manual_check}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {rows.length === 0 && (
        <EmptyState
          title="No criteria match"
          message="Choose All to see every criterion in this section."
        />
      )}
    </section>
  );
}
