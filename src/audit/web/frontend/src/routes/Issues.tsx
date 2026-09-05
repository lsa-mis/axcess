import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Info, Search } from "lucide-react";
import { api } from "../api/client";
import { Card } from "../components/ui";
import ExportMenu from "../components/ExportMenu";
import IssueEvidence from "../components/IssueEvidence";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
import { cn } from "../lib/cn";
import type { ConformanceLabel, IssueRow } from "../api/types";

/**
 * The primary report: the issue list beside the selected issue's evidence.
 *
 * On wide screens the full issue evidence, description, why it matters, the
 * fix, verification, and every affected page with its occurrences and instance
 * screenshots, sits in the right pane next to the list, so the reviewer can
 * scan the list and read the selected issue in the same view. Below ``lg`` the
 * two cannot coexist, so the list is the whole page and picking an issue
 * navigates to ``/scans/:id/issues/:key`` (the same content at a URL of its
 * own). The per-issue route still exists for deep links and bookmarks.
 */
export default function IssuesRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const conformance = (params.get("conformance") as ConformanceLabel | null) ?? "";
  const q = params.get("q") ?? "";
  const sort = params.get("sort") ?? "priority_desc";
  const selectedKey = params.get("issue") ?? "";

  const scanQuery = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
  });
  const issuesQuery = useQuery({
    queryKey: ["issues", id, conformance, q, sort],
    queryFn: () => api.listIssues(id, { conformance, q, sort }),
    placeholderData: (previous, query) => query?.queryKey[1] === id ? keepPreviousData(previous) : undefined,
    enabled: Number.isFinite(id),
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const rows = useMemo(() => issuesQuery.data?.rows ?? [], [issuesQuery.data]);
  const selected =
    rows.find((row) => row.issue_key === selectedKey) ??
    rows.find((row) => row.review_lane === "likely_barrier") ??
    rows.find((row) => row.review_lane === "expert_review") ?? rows[0] ?? null;

  useEffect(() => {
    // Keep ?issue= honest without ever inventing it: the pane falls back to the
    // first row on its own, so an untouched /issues URL stays clean. Only a
    // param that no longer names a visible row gets dropped, which is what
    // happens when a filter removes the issue that was selected.
    if (!selectedKey || rows.length === 0) return;
    if (rows.some((row) => row.issue_key === selectedKey)) return;
    const next = new URLSearchParams(params);
    next.delete("issue");
    setParams(next, { replace: true });
  }, [rows, selectedKey, params, setParams]);

  const error = scanQuery.error ?? issuesQuery.error;
  if (error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        Couldn&rsquo;t load this issue table. The stored scan evidence is unchanged.
      </Card>
    );
  }
  if (!scanQuery.data || !issuesQuery.data) {
    return <p className="text-sm text-fg-muted" role="status">Loading issue table…</p>;
  }

  const scan = scanQuery.data;
  const data = issuesQuery.data;
  const hasFilter = Boolean(conformance || q);
  const alfaCount = rows.filter((row) => row.pipeline === "alfa").length;
  const occurrences = rows.reduce((total, row) => total + row.occurrence_count, 0);

  return (
    <>
      <ReportHeader
        scanId={scan.id}
        previousScanId={scan.previous_scan_id}
        title="Issues"
        meta={
          <ReportMeta
            counts={
              <>
                {rows.length === data.total_unfiltered
                  ? `${data.total_unfiltered} issue groups`
                  : `${rows.length} of ${data.total_unfiltered} issue groups`}
                {" · "}
                {occurrences} occurrences
              </>
            }
          />
        }
        actions={<ExportMenu scanId={scan.id} />}
      />

      {alfaCount > 0 && (
        <details className="mb-3 text-xs text-fg-muted">
          <summary className="inline-flex min-h-target cursor-pointer list-none items-center gap-2">
            <Info className="h-4 w-4 shrink-0" aria-hidden />
            <span>
              {alfaCount === 1
                ? "One of these comes from a standardized ACT rule."
                : `${alfaCount} of these come from standardized ACT rules.`}{" "}
              <span className="font-semibold text-umich-blue underline underline-offset-2">
                What is an ACT rule?
              </span>
            </span>
          </summary>
          <p className="mt-2 max-w-3xl pl-6 leading-relaxed">
            ACT means Accessibility Conformance Testing. Each standardized rule
            checks one specific accessibility condition and returns pass, fail,
            or cannot tell. A failed rule is evidence about that condition, not
            proof that the whole page or site fails WCAG. “Cannot tell” needs an
            expert decision.
          </p>
        </details>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[23rem_minmax(0,1fr)]">
        <IssueListPane
          rows={rows}
          totalUnfiltered={data.total_unfiltered}
          conformanceCounts={data.conformance_counts}
          selectedKey={selected?.issue_key ?? ""}
          q={q}
          conformance={conformance}
          sort={sort}
          hasFilter={hasFilter}
          onParam={setParam}
          onClearFilters={() => setParams(new URLSearchParams(), { replace: true })}
        />
        {/* The evidence pane is the desktop half of the pattern. On small
            screens the list rows navigate to the detail route instead, so
            nothing here needs a second, stacked rendering of the same data. */}
        <div className="hidden lg:block">
          {selected ? (
            <IssueEvidence
              key={selected.issue_key}
              scanId={scan.id}
              issueKey={selected.issue_key}
            />
          ) : null}
        </div>
      </div>
    </>
  );
}

function IssueListPane({
  rows,
  totalUnfiltered,
  conformanceCounts,
  selectedKey,
  q,
  conformance,
  sort,
  hasFilter,
  onParam,
  onClearFilters,
}: {
  rows: IssueRow[];
  totalUnfiltered: number;
  conformanceCounts: Record<ConformanceLabel, number>;
  selectedKey: string;
  q: string;
  conformance: string;
  sort: string;
  hasFilter: boolean;
  onParam: (key: string, value: string) => void;
  onClearFilters: () => void;
}) {
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border bg-surface-subtle p-3">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle"
            aria-hidden
          />
          <IssueSearch value={q} onChange={(value) => onParam("q", value)} />
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <FilterSelect
            caption="Level"
            label="WCAG level"
            value={conformance}
            options={[
              { value: "", label: `All (${totalUnfiltered})` },
              { value: "A", label: `Level A (${conformanceCounts.A ?? 0})` },
              { value: "AA", label: `Level AA (${conformanceCounts.AA ?? 0})` },
              { value: "AAA", label: `Level AAA (${conformanceCounts.AAA ?? 0})` },
              { value: "BP", label: `Best practice (${conformanceCounts.BP ?? 0})` },
            ]}
            onChange={(value) => onParam("conformance", value)}
          />
          <FilterSelect
            caption="Sort"
            label="Order"
            value={sort}
            options={[
              { value: "priority_desc", label: "Highest priority" },
              { value: "pages_desc", label: "Most pages" },
              { value: "occurrences_desc", label: "Most occurrences" },
              { value: "conformance", label: "WCAG level" },
            ]}
            onChange={(value) => onParam("sort", value)}
          />
          {hasFilter && (
            <button
              type="button"
              onClick={onClearFilters}
              className="min-h-target rounded-xs border border-border-strong bg-surface px-3 text-sm font-semibold text-fg hover:bg-surface-muted"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-fg-muted">
          {hasFilter
            ? "No issues match these filters. Clear a filter to see more results."
            : "No issue groups were detected. Check scan coverage before drawing a conformance conclusion."}
        </p>
      ) : (
        <ul aria-label="Accessibility issue groups" className="divide-y divide-border">
          {([
            ["likely_barrier", "Barriers"],
            ["expert_review", "Needs manual review"],
            ["informational", "Informational"],
          ] as const).map(([lane, label]) => {
            const laneRows = rows.filter((row) => row.review_lane === lane);
            if (laneRows.length === 0) return null;
            return (
              <li key={lane}>
                <details open={true}>
                  <summary className="min-h-target cursor-pointer focus-visible:outline-none focus-visible:shadow-focus bg-surface-subtle px-3.5 py-3 text-sm font-semibold text-fg">
                    {label} <span className="font-normal tabular-nums">({laneRows.length})</span>
                  </summary>
                  <ul aria-label={`${label} issue groups`} className="divide-y divide-border">
                    {laneRows.map((row) => (
                      <IssueListRow
                        key={row.issue_key}
                        row={row}
                        selected={row.issue_key === selectedKey}
                      />
                    ))}
                  </ul>
                </details>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function IssueListRow({ row, selected }: { row: IssueRow; selected: boolean }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const lane = laneLabel(row.review_lane);

  const select = () => {
    // Selection lives in ?issue= so it is shareable and survives a refresh.
    const next = new URLSearchParams(params);
    next.set("issue", row.issue_key);
    setParams(next, { replace: true });
  };

  return (
    <li>
      {/*
        One control, two behaviors by width. It is a real <a> so it can be
        opened in a new tab and read as a link, and at lg and up the click is
        intercepted to select the issue in the pane instead of navigating,
        which is the same destination's content without losing the list.
      */}
      <a
        href={row.detail_url}
        data-issue-selection="true"
        aria-current={selected ? "true" : undefined}
        onClick={(event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
          event.preventDefault();
          if (window.matchMedia("(min-width: 1024px)").matches) select();
          else navigate(row.detail_url);
        }}
        className={cn(
          "block px-3.5 py-3 no-underline transition-colors hover:no-underline",
          selected
            ? "bg-umich-blue/[0.06] shadow-[inset_4px_0_0_theme(colors.umich.blue)]"
            : "hover:bg-surface-muted/60",
        )}
      >
        <span className="flex items-start justify-between gap-2">
          <span
            className={cn(
              "block text-sm leading-snug",
              selected ? "font-semibold text-umich-blue" : "font-semibold text-fg",
            )}
          >
            {row.title}
          </span>
          {selected && (
            <span className="mt-0.5 shrink-0 rounded-full bg-umich-blue px-2 py-0.5 text-2xs font-semibold uppercase tracking-wide text-white">
              Current
            </span>
          )}
        </span>
        <span className="mt-1.5 flex flex-wrap gap-1.5">
          <Tag tone={row.review_lane === "informational" ? "neutral" : "flag"}>{lane}</Tag>
          {row.wcag_sc && <Tag>WCAG {row.wcag_sc} {row.conformance}</Tag>}
        </span>
        <span className="mt-1.5 block text-xs tabular-nums text-fg-muted">
          {occurrenceSummary(row)}
        </span>
      </a>
    </li>
  );
}

function Tag({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "flag" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-2xs px-2 py-0.5 text-2xs font-semibold",
        tone === "flag"
          ? "bg-sev-major-bg text-sev-major"
          : "border border-border bg-surface-muted text-fg-muted",
      )}
    >
      {children}
    </span>
  );
}

function laneLabel(lane: IssueRow["review_lane"]): string {
  return lane === "likely_barrier"
    ? "Automated failure"
    : lane === "expert_review"
      ? "Needs confirmation"
      : "Informational";
}

function occurrenceSummary(row: IssueRow): string {
  return (
    `${row.occurrence_count} occurrence${row.occurrence_count === 1 ? "" : "s"}` +
    ` on ${row.page_count} page${row.page_count === 1 ? "" : "s"}`
  );
}

/**
 * A filter control that shows one short word and announces a fuller one.
 *
 * The visible caption is a substring of the accessible name (SC 2.5.3), so
 * speech-input users can say either "Level" or "WCAG level" and hit the same
 * control, while the toolbar stays compact enough for the list column.
 */
function FilterSelect({
  caption,
  label,
  value,
  options,
  onChange,
}: {
  caption: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="inline-flex min-h-target shrink-0 items-center gap-2 rounded-xs border border-border-strong bg-surface pl-3 pr-1 focus-within:border-umich-blue">
      <span className="text-xs font-medium text-fg-subtle">{caption}</span>
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-target min-w-0 max-w-[9rem] border-0 bg-transparent py-2 pr-1 text-sm font-semibold text-fg focus:outline-none"
      >
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

/** Keep keystrokes synchronous while URL navigation is scheduled by the router. */
function IssueSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [draft, setDraft] = useState(value);
  const published = useRef<string | null>(null);
  const latestChange = useRef(onChange);
  useEffect(() => { latestChange.current = onChange; }, [onChange]);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    if (value !== published.current) {
      clearTimeout(timer.current);
      setDraft(value);
    }
  }, [value]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return <input
    type="search"
    aria-label="Search issues"
    value={draft}
    placeholder="Search issue name or WCAG criterion"
    onChange={(event) => {
      const next = event.target.value;
      setDraft(next);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        published.current = next;
        latestChange.current(next);
      }, 200);
    }}
    className="min-h-target w-full rounded-xs border border-border-strong bg-surface py-2 pl-10 pr-3 text-base text-fg focus:border-umich-blue focus:outline-none focus-visible:shadow-focus"
  />;
}
