import { useEffect, useId, useMemo, useRef } from "react";
import { useParams, useSearchParams, Link, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Info, Search } from "lucide-react";
import { api } from "../api/client";
import { Card } from "../components/ui";
import ExportMenu from "../components/ExportMenu";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
import { cn } from "../lib/cn";
import type { ConformanceLabel, IssueLocation, IssueRow } from "../api/types";

/**
 * The primary report: an issue list beside the evidence for the selected one.
 *
 * The four-column table this replaces put what, why, fix and where on screen
 * for every issue at once — six issues carrying roughly fifteen facts each, in
 * columns so wide they needed their own horizontal scrollbar. Reviewers work
 * one issue at a time, so the list stays permanently visible for scanning and
 * comparing while the pane beside it answers the four questions for whichever
 * issue is selected.
 *
 * **Below `lg` the two panes cannot coexist**, so the list becomes the whole
 * page and picking an issue navigates to ``/scans/:id/issues/:key`` — the
 * detail route that already exists. That is the same content at a URL of its
 * own, not a second implementation of it.
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
    enabled: Number.isFinite(id),
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    // Changing a filter can strip the selected issue out of the results;
    // the selection effect below re-picks rather than leaving a stale pane.
    setParams(next, { replace: true });
  };

  const rows = useMemo(() => issuesQuery.data?.rows ?? [], [issuesQuery.data]);
  const selected =
    rows.find((row) => row.issue_key === selectedKey) ?? rows[0] ?? null;

  useEffect(() => {
    // Keep ?issue= honest without ever inventing it: the pane falls back to the
    // first row on its own, so an untouched /issues URL stays clean. Only a
    // param that no longer names a visible row gets dropped — which is what
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
            or cannot tell. A failed rule is evidence about that condition—not
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
        {/* The pane is the desktop half of the pattern. On small screens the
            list rows are links to the detail route instead, so nothing here
            needs a second, stacked rendering of the same evidence. */}
        <div className="hidden lg:block">
          {selected ? <IssuePane row={selected} /> : null}
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
          <input
            type="search"
            aria-label="Search issues"
            value={q}
            placeholder="Search issue name or WCAG criterion"
            onChange={(event) => onParam("q", event.target.value)}
            className="min-h-target w-full rounded-xs border border-border-strong bg-surface py-2 pl-10 pr-3 text-sm text-fg focus:border-umich-blue focus:outline-none"
          />
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
          {rows.map((row) => (
            <IssueListRow
              key={row.issue_key}
              row={row}
              selected={row.issue_key === selectedKey}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

function IssueListRow({
  row,
  selected,
}: {
  row: IssueRow;
  selected: boolean;
}) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const lane = laneLabel(row.review_lane);

  const select = () => {
    const next = new URLSearchParams(params);
    next.set("issue", row.issue_key);
    setParams(next, { replace: true });
  };

  return (
    <li>
      {/*
        One control, two behaviors by width. It is a real <a> so it can be
        opened in a new tab and read as a link, and at lg and up the click is
        intercepted to select the pane instead of navigating — which is the
        same destination's content without losing the list.
      */}
      <a
        href={`${row.detail_url}`}
        aria-current={selected ? "true" : undefined}
        onClick={(event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
          event.preventDefault();
          if (window.matchMedia("(min-width: 1024px)").matches) select();
          else navigate(row.detail_url);
        }}
        className={cn(
          // `hover:no-underline` is load-bearing: the base layer's `a:hover`
          // rule out-specifies a plain `no-underline`, so without it the whole
          // row — title, chips and count — underlines on hover.
          "block px-3.5 py-3 no-underline transition-colors hover:no-underline",
          selected
            ? "bg-surface-muted shadow-[inset_3px_0_0_theme(colors.umich.blue)]"
            : "hover:bg-surface-muted/60",
        )}
      >
        <span
          className={cn(
            "block text-sm leading-snug",
            selected ? "font-semibold text-umich-blue" : "font-semibold text-fg",
          )}
        >
          {row.title}
        </span>
        <span className="mt-1.5 flex flex-wrap gap-1.5">
          <Tag tone={row.review_lane === "informational" ? "neutral" : "flag"}>{lane}</Tag>
          {row.wcag_sc && <Tag>WCAG {row.wcag_sc} {row.conformance}</Tag>}
        </span>
        <span className="mt-1.5 block text-xs tabular-nums text-fg-muted">
          {occurrenceSummary(row)}
        </span>
        {/* Small screens leave this list for the detail route, so say so. */}
        <span className="sr-only lg:hidden"> — opens the full issue evidence</span>
      </a>
    </li>
  );
}

/**
 * The evidence pane: what, why, the fix, and exactly where.
 *
 * It is a labelled region rather than a live region — the selection is a
 * deliberate act by the reader, so announcing the whole pane on every arrow
 * press would talk over them. Focus is moved to the heading instead.
 */
function IssuePane({ row }: { row: IssueRow }) {
  const headingId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    headingRef.current?.focus({ preventScroll: true });
  }, [row.issue_key]);

  const remaining = Math.max(0, row.occurrence_count - row.locations.length);

  return (
    <Card aria-labelledby={headingId} className="p-5" role="region">
      <h2
        id={headingId}
        ref={headingRef}
        tabIndex={-1}
        className="text-lg font-semibold leading-snug tracking-[-0.01em] text-fg"
      >
        {row.title}
      </h2>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Tag tone={row.review_lane === "informational" ? "neutral" : "flag"}>
          {laneLabel(row.review_lane)}
        </Tag>
        {row.wcag_sc && <Tag>WCAG {row.wcag_sc} {row.conformance}</Tag>}
        <Tag>{sourceLabel(row.pipeline)}</Tag>
        {/* Evidence that only exists after a control is used was reached by the
            click-through pass, not by loading the URL. Saying so here is what
            connects the overview's "26 DOM states reached" to a real issue. */}
        {row.locations.some((location) => location.revealed_by) && (
          <Tag>Found in a clicked-open state</Tag>
        )}
        <span className="text-xs tabular-nums text-fg-muted">{occurrenceSummary(row)}</span>
      </div>

      <div className="mt-5 grid gap-x-9 gap-y-5 xl:grid-cols-2">
        <div>
          <h3 className="text-2xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
            Why it matters
          </h3>
          <p className="mt-1.5 max-w-[58ch] text-sm leading-relaxed text-fg">
            {row.why_matters || row.description || row.evidence_summary}
          </p>
          {row.abilities_affected.length > 0 && (
            <p className="mt-2.5 text-xs text-fg-muted">
              <strong className="font-semibold">Affects</strong> · {row.abilities_affected.join(", ")}
            </p>
          )}
        </div>
        <div>
          <h3 className="text-2xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
            Expected fix
          </h3>
          {row.fix_steps.length > 0 ? (
            <ol className="mt-1.5 list-decimal space-y-1.5 pl-5 text-sm leading-relaxed text-fg">
              {row.fix_steps.map((step, index) => (
                <li key={index} dangerouslySetInnerHTML={{ __html: step }} />
              ))}
            </ol>
          ) : (
            <p className="mt-1.5 text-sm leading-relaxed text-fg">
              Confirm the stored evidence in page context, then correct the component or content that produced the result.
            </p>
          )}
          {row.acceptance && (
            <p className="mt-2.5 max-w-[58ch] text-xs text-fg-muted">
              <strong className="font-semibold">Done when</strong> · {row.acceptance}
            </p>
          )}
        </div>
      </div>

      <h3 className="mt-6 text-2xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
        Where exactly
        {row.locations.length > 0 && (
          <span className="ml-1.5 font-medium normal-case tracking-normal text-fg-muted">
            · {row.locations.length} of {row.occurrence_count} shown
          </span>
        )}
      </h3>
      {row.locations.length > 0 ? (
        <ul className="mt-2 grid gap-2.5 xl:grid-cols-2">
          {row.locations.map((location) => (
            <Location key={`${location.page_id}:${location.target}`} location={location} />
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-fg-muted">
          No bounded location sample is available for this historical evidence.
        </p>
      )}

      <p className="mt-4">
        <Link
          to={row.detail_url}
          className="inline-flex min-h-target items-center text-sm font-semibold text-umich-blue underline underline-offset-2"
        >
          {remaining > 0
            ? `Open full evidence — ${remaining} more occurrence${remaining === 1 ? "" : "s"}`
            : "Open full evidence"}
        </Link>
      </p>
    </Card>
  );
}

function Location({ location }: { location: IssueLocation }) {
  return (
    <li className="rounded-xs border border-border bg-surface-subtle px-3.5 py-3">
      <a
        href={location.page_url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 text-sm font-semibold text-umich-blue underline underline-offset-2"
      >
        {location.page_title || location.page_url}
        <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
        <span className="sr-only"> opens the scanned page in a new tab</span>
      </a>
      {location.page_title && (
        <p className="mt-0.5 break-all text-xs text-fg-subtle">{location.page_url}</p>
      )}
      {/* A finding that only exists after a control is used cannot be
          reproduced from the URL alone. Naming the control is the
          difference between evidence and an assertion. */}
      {location.revealed_by && (
        <p className="mt-1 text-xs font-medium text-fg">
          After clicking &ldquo;{location.revealed_by}&rdquo;
        </p>
      )}
      <code className="mt-2 block overflow-x-auto rounded-2xs border border-border bg-surface-muted px-2 py-1 text-xs text-fg">
        {location.target}
      </code>
      {location.context && (
        <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-fg-muted">{location.context}</p>
      )}
      <Link
        to={location.evidence_url}
        className="mt-2 inline-block text-xs font-semibold text-umich-blue underline underline-offset-2"
      >
        Open stored page evidence
      </Link>
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

function sourceLabel(pipeline: IssueRow["pipeline"]): string {
  return {
    axe: "axe-core",
    alfa: "ACT rule · Siteimprove Alfa",
    semantic: "Local AI",
    keyboard: "Keyboard probe",
    responsive: "Responsive probe",
    focus: "Focus probe",
    visual: "Visual probe",
    image: "OCR + vision",
    protected_image: "Protected image",
  }[pipeline] ?? pipeline;
}

/**
 * A filter control that shows one short word and announces a fuller one.
 *
 * The visible caption is a substring of the accessible name (SC 2.5.3), so
 * speech-input users can say either "Level" or "WCAG level" and hit the same
 * control — while the toolbar stays compact enough for the list column.
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
