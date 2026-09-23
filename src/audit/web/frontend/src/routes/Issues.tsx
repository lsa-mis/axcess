import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown, Info, Search } from "lucide-react";
import { api } from "../api/client";
import { Card, Select, withReturnTrail, type SelectOption } from "../components/ui";
// The same helper the topbar trail uses.
import { siteLabel } from "../components/ReportCrumb";
import ConformanceBadge from "../components/ConformanceBadge";
import ExportMenu from "../components/ExportMenu";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
import { ReportExpertTools, ReportSummary } from "../components/ReportSummary";
import { cn } from "../lib/cn";
import { useScanQuery } from "../hooks/useScanQuery";
import type {
  ConformanceLabel,
  IssueRow,
  ReviewLane,
} from "../api/types";

/**
 * The primary report: every issue group as one row of a flat table.
 *
 * This is where a report opens. The numbers and scan coverage that used to
 * be an Overview tab sit above the table (``ReportSummary``), and the expert
 * tools sit closed below it, so the first thing on screen is the table.
 *
 * Each column is one of the facts the old right-hand evidence pane listed
 * for the selected issue (type, criterion, priority, spread, difficulty,
 * owner), so the whole report can be compared at a glance instead of one
 * issue at a time. What does not fit in a cell is one link away: the title
 * opens the issue's full record (what it is, why it matters, the fix), and
 * the page count opens a page of its own (``/scans/:id/issues/:key/pages``)
 * listing every affected page in columns. The topbar trail is the way back,
 * which the desktop app needs because it has no browser back button, and
 * every link out of here carries the origin it needs to draw that trail.
 */
export default function IssuesRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const conformance = (params.get("conformance") as ConformanceLabel | null) ?? "";
  const rawLane = params.get("type") ?? "";
  const lane: ReviewLane | "" = isReviewLane(rawLane) ? rawLane : "";
  const q = params.get("q") ?? "";
  const sort = parseSort(params.get("sort"));
  const hasFilter = Boolean(conformance || lane || q);

  const scanQuery = useScanQuery(id);
  const issuesQuery = useQuery({
    // Ordering is done here, not by the server: every row is already in
    // hand, and the column headers can then sort by any column in either
    // direction instead of the four orders the API offers.
    queryKey: ["issues", id, conformance, lane, q],
    queryFn: () => api.listIssues(id, { conformance, review_lane: lane, q, sort: "priority_desc" }),
    placeholderData: (previous, query) => query?.queryKey[1] === id ? keepPreviousData(previous) : undefined,
    enabled: Number.isFinite(id),
  });
  // The summary above the table describes the whole report, so it needs the
  // unfiltered rows. Unfiltered, the table's own response is exactly that;
  // only a filtered table needs the second request.
  const summaryQuery = useQuery({
    queryKey: ["issues", id, "workspace-summary"],
    queryFn: () => api.listIssues(id),
    enabled: Number.isFinite(id) && hasFilter,
  });

  // Update against the live query string, not the one captured at render.
  // The search publishes on a 200ms debounce, so a filter changed while a
  // keystroke is still pending would otherwise write a snapshot taken before
  // that keystroke — and the search term the reader just typed disappears
  // from the URL (and from a shared or reloaded link) the moment they touch
  // a dropdown.
  const setParam = (key: string, value: string) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
  };

  const rows = useMemo(
    () => sortRows(issuesQuery.data?.rows ?? [], sort),
    [issuesQuery.data, sort],
  );

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
  const isComplete = scan.status === "completed";
  const summaryRows = hasFilter ? summaryQuery.data?.rows : data.rows;
  const alfaCount = rows.filter((row) => row.pipeline === "alfa").length;

  return (
    <>
      <ReportHeader
        tabs
        scanId={scan.id}
        previousScanId={scan.previous_scan_id}
        title="Issues"
        meta={
          <ReportMeta
            // No counts: the stat cards below carry them, and the same
            // numbers twice in one screenful read as two different facts.
            // The site leads because the topbar trail is gone the moment
            // this becomes a screenshot or a print -- which is most of how
            // a finding gets quoted to the team that has to fix it.
            counts={[
              siteLabel(scan.seed_url),
              isComplete && scan.finished_at ? `Completed ${formatCompleted(scan.finished_at)}` : "",
            ]
              .filter(Boolean)
              .join(" · ")}
          />
        }
        actions={<ExportMenu scanId={scan.id} />}
      />

      {isComplete && (
        <ReportSummary
          scan={scan}
          issueGroups={data.total_unfiltered}
          occurrences={data.occurrence_counts.all_evidence}
          rows={summaryRows}
        />
      )}

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

      {/* Filtering changed the table silently: the visible count updated,
          but nothing announced it, so a screen-reader user typing in the
          search box got no confirmation that anything had happened (SC
          4.1.3). Visually hidden because the toolbar already shows the
          filtered count — this is the same fact, routed to the people the
          visual update skips. */}
      <p role="status" className="sr-only">
        {issuesQuery.isFetching
          ? "Updating issues…"
          : `${rows.length} of ${data.total_unfiltered} issue groups shown` +
            (hasFilter ? ", filtered" : "")}
      </p>

      <Card className="overflow-hidden">
        <IssueToolbar
          shown={rows.length}
          totalUnfiltered={data.total_unfiltered}
          conformanceCounts={data.conformance_counts}
          laneCounts={data.review_lane_counts}
          q={q}
          conformance={conformance}
          lane={lane}
          hasFilter={hasFilter}
          onParam={setParam}
          onClearFilters={() => setParams(new URLSearchParams(), { replace: true })}
        />
        {rows.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-fg-muted">
            {hasFilter
              ? "No issues match these filters. Clear a filter to see more results."
              : "No issue groups were detected. Check scan coverage before drawing a conformance conclusion."}
          </p>
        ) : (
          <IssueTable
            scanId={scan.id}
            rows={rows}
            sort={sort}
            onSort={(next) => setParam("sort", serializeSort(next))}
            busy={issuesQuery.isFetching}
          />
        )}
      </Card>

      {isComplete && <ReportExpertTools scan={scan} rows={summaryRows} />}
    </>
  );
}

function IssueToolbar({
  shown,
  totalUnfiltered,
  conformanceCounts,
  laneCounts,
  q,
  conformance,
  lane,
  hasFilter,
  onParam,
  onClearFilters,
}: {
  shown: number;
  totalUnfiltered: number;
  conformanceCounts: Record<ConformanceLabel, number>;
  laneCounts: Record<ReviewLane, number>;
  q: string;
  conformance: string;
  lane: ReviewLane | "";
  hasFilter: boolean;
  onParam: (key: string, value: string) => void;
  onClearFilters: () => void;
}) {
  // One row, search first, so the table starts as high as it can. It wraps
  // rather than clipping: the search keeps a usable minimum width and the
  // filters drop under it on a narrow screen.
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border bg-surface-subtle p-3">
      <div className="relative min-w-[min(100%,16rem)] max-w-xl flex-1 basis-80">
        <Search
          className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle"
          aria-hidden
        />
        <IssueSearch value={q} onChange={(value) => onParam("q", value)} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <FilterSelect
          caption="Level"
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
        {/* "Type" is the column's name for the review lane, so the filter
            is named the same way and its options read as the cells do. */}
        <FilterSelect
          caption="Type"
          value={lane}
          options={[
            { value: "", label: `All (${totalUnfiltered})` },
            ...REVIEW_LANES.map((key) => ({
              value: key,
              label: `${laneLabel(key)} (${laneCounts[key] ?? 0})`,
            })),
          ]}
          onChange={(value) => onParam("type", value)}
        />
        {hasFilter && (
          <>
            <button
              type="button"
              onClick={onClearFilters}
              className="min-h-target rounded-xs border border-border-strong bg-surface px-3 text-sm font-semibold text-fg hover:bg-surface-muted"
            >
              Clear filters
            </button>
            {/* The subtitle used to carry this; it now carries no counts. */}
            <span className="text-sm tabular-nums text-fg-muted">
              {shown} of {totalUnfiltered} shown
            </span>
          </>
        )}
      </div>
    </div>
  );
}

const COLUMNS = [
  "Issue",
  "Type",
  "WCAG",
  "Priority",
  "Pages",
  "Occurrences",
  "Difficulty",
  "Responsibility",
] as const;
type SortColumn = (typeof COLUMNS)[number];
type Direction = "asc" | "desc";
type SortState = { column: SortColumn; direction: Direction };

/**
 * ``?sort=`` keys, one per column and direction. The four the API accepts
 * (``priority_desc``, ``pages_desc``, ``occurrences_desc``, ``conformance``)
 * keep their old spellings so saved links still open the same order.
 */
const SORT_KEYS: Record<SortColumn, string> = {
  Issue: "title",
  Type: "type",
  WCAG: "wcag",
  Priority: "priority",
  Pages: "pages",
  Occurrences: "occurrences",
  Difficulty: "difficulty",
  Responsibility: "responsibility",
};
const SORT_COLUMNS = Object.keys(SORT_KEYS) as SortColumn[];
/** Numbers open with the biggest first; words open alphabetically. */
const DEFAULT_DIRECTION: Record<SortColumn, Direction> = {
  Issue: "asc",
  Type: "asc",
  WCAG: "asc",
  Priority: "desc",
  Pages: "desc",
  Occurrences: "desc",
  Difficulty: "asc",
  Responsibility: "asc",
};
const DEFAULT_SORT: SortState = { column: "Priority", direction: "desc" };

function serializeSort(sort: SortState): string {
  if (sort.column === "WCAG" && sort.direction === "asc") return "conformance";
  return `${SORT_KEYS[sort.column]}_${sort.direction}`;
}

function parseSort(raw: string | null): SortState {
  if (!raw) return DEFAULT_SORT;
  if (raw === "conformance") return { column: "WCAG", direction: "asc" };
  const match = raw.match(/^(.+)_(asc|desc)$/);
  if (!match) return DEFAULT_SORT;
  const column = SORT_COLUMNS.find((c) => SORT_KEYS[c] === match[1]);
  return column ? { column, direction: match[2] as Direction } : DEFAULT_SORT;
}

/** The direction as a two-word chip: "high → low" for numbers, "A → Z" for words. */
function sortChip(sort: SortState): string {
  const numeric = DEFAULT_DIRECTION[sort.column] === "desc";
  if (numeric) return sort.direction === "desc" ? "high → low" : "low → high";
  return sort.direction === "asc" ? "A → Z" : "Z → A";
}

/** What the sort means in words, for the status line and the header names. */
function describeSort(sort: SortState): string {
  const numeric = DEFAULT_DIRECTION[sort.column] === "desc";
  const how = numeric
    ? sort.direction === "desc" ? "highest first" : "lowest first"
    : sort.direction === "asc" ? "A to Z" : "Z to A";
  // Priority is lane-first (see sortRows), and the status line says so: a
  // reader who sees a low score above a higher one should not think the
  // sort is broken.
  if (sort.column === "Priority") return `Priority, barriers first, then ${how}`;
  return `${sort.column}, ${how}`;
}

const LANE_RANK: Record<ReviewLane, number> = { likely_barrier: 0, expert_review: 1, informational: 2 };
const DIFFICULTY_RANK: Record<string, number> = { Beginner: 0, Intermediate: 1, Advanced: 2 };

/** A WCAG SC like "2.4.4" as comparable numbers; no SC sorts after every SC. */
function wcagRank(row: IssueRow): number[] {
  if (!row.wcag_sc) return [Number.POSITIVE_INFINITY];
  return row.wcag_sc.split(".").map((part) => Number(part) || 0);
}

function compareLists(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const diff = (a[i] ?? 0) - (b[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function compareRows(a: IssueRow, b: IssueRow, column: SortColumn): number {
  switch (column) {
    case "Issue":
      return a.title.localeCompare(b.title, undefined, { sensitivity: "base" });
    case "Type":
      return LANE_RANK[a.review_lane] - LANE_RANK[b.review_lane];
    case "WCAG":
      return compareLists(wcagRank(a), wcagRank(b));
    case "Priority":
      return a.priority - b.priority;
    case "Pages":
      return a.page_count - b.page_count;
    case "Occurrences":
      return a.occurrence_count - b.occurrence_count;
    case "Difficulty":
      return (DIFFICULTY_RANK[a.difficulty] ?? 9) - (DIFFICULTY_RANK[b.difficulty] ?? 9);
    case "Responsibility":
      return a.responsibility.localeCompare(b.responsibility, undefined, { sensitivity: "base" });
  }
}

/**
 * A stable sort: ties keep the server's order, then the title.
 *
 * Priority is lane-first: a barrier outranks a "needs review" lead outranks
 * an informational record, whatever their scores. The score only orders rows
 * *within* a lane. A high-scoring informational row above a real barrier was
 * the priority column contradicting the type column, and the type is the one
 * a reviewer acts on. The lane order is fixed for both directions; only the
 * score flips.
 */
function sortRows(rows: IssueRow[], sort: SortState): IssueRow[] {
  const sign = sort.direction === "asc" ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      if (sort.column === "Priority") {
        const lane = LANE_RANK[a.row.review_lane] - LANE_RANK[b.row.review_lane];
        if (lane !== 0) return lane;
      }
      const primary = compareRows(a.row, b.row, sort.column) * sign;
      if (primary !== 0) return primary;
      return a.index - b.index;
    })
    .map(({ row }) => row);
}

/**
 * The flat table itself.
 *
 * Eight columns do not fit at phone width, so the table sits in a scroll
 * region of its own rather than forcing the page sideways (the shell keeps
 * ``overflow-x: hidden`` on the document). At desktop width they do fit:
 * there is no minimum table width, the issue title is the one column that
 * wraps, and the cells are padded just enough to keep all eight in view
 * beside the expanded sidebar at 1280 px. The region is focusable so a
 * keyboard user can scroll it, and it is named so that focus lands on
 * something with a name. The issue column is sticky, so the row keeps its
 * label while the rest scrolls under it.
 */
function IssueTable({
  scanId,
  rows,
  sort,
  onSort,
  busy,
}: {
  scanId: number;
  rows: IssueRow[];
  sort: SortState;
  onSort: (next: SortState) => void;
  busy: boolean;
}) {
  // The status line is written only after a header is pressed. Present from
  // the first paint it would be read out as the page loads, before anyone
  // has asked for anything; and the table stays sorted by priority with no
  // announcement, as it always has.
  const [announced, setAnnounced] = useState<SortState | null>(null);
  const choose = (column: SortColumn) => {
    const next: SortState =
      sort.column === column
        ? { column, direction: sort.direction === "asc" ? "desc" : "asc" }
        : { column, direction: DEFAULT_DIRECTION[column] };
    setAnnounced(next);
    onSort(next);
  };
  return (
    <>
      {/* WAI-ARIA sortable table: ``aria-sort`` on the sorted header, a real
          button in each header so the sort is reachable and operable from
          the keyboard, and a polite live region that says what the order is
          now. The region is visible, so sighted readers get the same
          confirmation without hunting for the small arrow. */}
      <p
        role="status"
        aria-live="polite"
        className="border-b border-border bg-surface-subtle px-3 py-1.5 text-xs text-fg-muted"
      >
        {announced ? `Sorted by ${describeSort(announced)}.` : `Sorted by ${describeSort(sort)}.`}
      </p>
      {/* Keyboard users need focus on the overflow region to scroll the table. */}
      <div
        role="region"
        aria-label="Issue table"
        aria-busy={busy}
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        className="overflow-x-auto focus:outline-none focus-visible:shadow-focus"
      >
      <table className="w-full text-sm">
        <caption className="sr-only">Accessibility issue groups</caption>
        <thead className="bg-surface-muted text-2xs text-fg-subtle">
          <tr>
            {COLUMNS.map((column) => {
              const numeric =
                column === "Pages" || column === "Occurrences";
              const cell = cn(
                "whitespace-nowrap px-1 py-0.5 text-left font-semibold",
                column === "Issue" && "sticky left-0 z-[1] bg-surface-muted",
                numeric && "text-right",
              );
              const active = sort.column === column;
              const Arrow = !active ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;
              return (
                <th
                  key={column}
                  scope="col"
                  aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                  // The sorted column is underlined in blue across the whole
                  // header cell, so the eye finds it before reading anything.
                  className={cn(cell, active && "shadow-[inset_0_-3px_0_theme(colors.umich.blue)]")}
                >
                  {/* The sorted header says how it is sorted, in words, right
                      where the reader is looking: a small chip with the arrow
                      and "high → low" or "A → Z". The chip re-keys on every
                      change so it pops in again, a quiet cue that the order
                      just moved. The inactive headers keep a faint two-way
                      arrow, the promise that they can be sorted too. */}
                  <button
                    type="button"
                    onClick={() => choose(column)}
                    className={cn(
                      "group inline-flex min-h-target items-center gap-1.5 rounded-xs px-1 text-2xs font-semibold hover:bg-border/50 focus-visible:outline-none focus-visible:shadow-focus",
                      active ? "text-umich-blue" : "text-fg-subtle",
                    )}
                  >
                    <span>{column}</span>
                    {active ? (
                      <span
                        key={`${sort.column}-${sort.direction}`}
                        className="inline-flex items-center gap-0.5 whitespace-nowrap rounded-full bg-umich-blue px-1.5 py-px text-[0.65rem] font-semibold normal-case tracking-normal text-white motion-safe:animate-sort-pop"
                      >
                        <Arrow className="h-3 w-3 shrink-0" aria-hidden />
                        {sortChip(sort)}
                      </span>
                    ) : (
                      <Arrow
                        className="h-3.5 w-3.5 shrink-0 opacity-40 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
                        aria-hidden
                      />
                    )}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <IssueTableRow key={row.issue_key} scanId={scanId} row={row} index={index} />
          ))}
        </tbody>
      </table>
      </div>
    </>
  );
}

/**
 * One issue group.
 *
 * There used to be an "About" column whose button opened the issue's
 * description in a second row under this one. It repeated what the title
 * link opens, and it was the column that got cut off, so it is gone: the
 * title is the one way to what an issue is.
 */
function IssueTableRow({ scanId, row, index }: { scanId: number; row: IssueRow; index: number }) {
  const location = useLocation();
  const isInformational = row.review_lane === "informational";
  const band = index % 2 === 1 ? "bg-surface-subtle" : "bg-surface";
  const detailPath = `/scans/${scanId}/issues/${encodeURIComponent(row.issue_key)}`;
  // The pages table needs the way back to this list, filters included.
  const here = `${location.pathname}${location.search}`;
  const pagesPath = withReturnTrail(`${detailPath}/pages`, "Issues", here);

  return (
    <tr className={cn(band, "border-t border-border")}>
      <th
        scope="row"
        className={cn(
          band,
          "sticky left-0 z-[1] max-w-[18rem] min-w-[12rem] px-2 py-2.5 text-left align-top font-semibold shadow-[inset_-1px_0_0_theme(colors.border.DEFAULT)]",
        )}
      >
        {/* The title is the row's main link and opens the issue's full
            evidence record: what it is, why it matters, the fix, and its
            pages. The page count beside it is the shortcut straight to
            the pages. It is styled like every other link so nobody has to
            guess it is one. */}
        {/* min-h-target goes on the link, not as padding on the cell: SC
            2.5.5 measures the target itself, and a 38px-high link inside a
            taller cell is still a 38px target. */}
        <Link
          to={withReturnTrail(detailPath, "Issues", here)}
          data-issue-link="true"
          className="flex min-h-target items-center text-umich-blue underline underline-offset-2 hover:text-umich-blue-600"
        >
          {row.title}
          <span className="sr-only">, full evidence</span>
        </Link>
      </th>
      <td className="whitespace-nowrap px-2 py-2.5 align-top">
        <Tag tone={isInformational ? "neutral" : "flag"}>{laneLabel(row.review_lane)}</Tag>
      </td>
      <td className="whitespace-nowrap px-2 py-2.5 align-top">
        {row.wcag_sc ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="tabular-nums">{row.wcag_sc}</span>
            <ConformanceBadge level={row.conformance} />
            {row.wcag_name && <span className="sr-only">{row.wcag_name}</span>}
          </span>
        ) : (
          <span className="text-fg-muted">Best practice</span>
        )}
      </td>
      <td className="whitespace-nowrap px-2 py-2.5 align-top">
        {isInformational ? (
          <span className="text-fg-muted">n/a</span>
        ) : (
          // The band, not the score: "11.28" means nothing to a reader,
          // and two decimals invited comparing issues by hundredths. The
          // score still orders the column; the word is what shows.
          priorityTier(row.priority)
        )}
      </td>
      <td className="whitespace-nowrap px-2 py-2.5 text-right align-top tabular-nums">
        {/* "211 pages" says nothing about which issue on its own, and a
            description is not a name: SC 2.4.9 wants the purpose from the
            link text alone, so the issue rides along inside the name while
            the cell stays a number wide. */}
        <Link
          to={pagesPath}
          className="flex min-h-target items-center justify-end text-umich-blue underline underline-offset-2"
        >
          {row.page_count} page{row.page_count === 1 ? "" : "s"}
          <span className="sr-only"> with {row.title}</span>
        </Link>
      </td>
      <td className="whitespace-nowrap px-2 py-2.5 text-right align-top tabular-nums">
        {row.occurrence_count}
      </td>
      <td className="whitespace-nowrap px-2 py-2.5 align-top">
        {isInformational || row.difficulty === "Unknown" ? (
          <span className="text-fg-muted">n/a</span>
        ) : (
          row.difficulty
        )}
      </td>
      <td className="whitespace-nowrap px-2 py-2.5 align-top">
        {isInformational ? (
          <span className="text-fg-muted">n/a</span>
        ) : (
          capitalize(row.responsibility)
        )}
      </td>
    </tr>
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

const REVIEW_LANES = ["likely_barrier", "expert_review", "informational"] as const;
const isReviewLane = (value: string): value is ReviewLane =>
  (REVIEW_LANES as readonly string[]).includes(value);

function laneLabel(lane: IssueRow["review_lane"]): string {
  return lane === "likely_barrier"
    ? "Barrier"
    : lane === "expert_review"
      ? "Needs review"
      : "Informational";
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

/** A plain-English band for the priority score (severity × log1p(pages)). */
function priorityTier(priority: number): "High" | "Medium" | "Low" {
  if (priority >= 6) return "High";
  if (priority >= 3) return "Medium";
  return "Low";
}

/** A filter in the issue toolbar. The caption is the control's name, so it
 *  carries no second aria-label: a visible label and a different accessible
 *  one are two names for one control (WCAG 2.5.3). */
function FilterSelect({
  caption,
  value,
  options,
  onChange,
}: {
  caption: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
}) {
  return (
    <Select
      label={caption}
      value={value}
      options={options}
      onChange={onChange}
      className="shrink-0"
    />
  );
}

/** Keep keystrokes synchronous while URL navigation is scheduled by the router. */
function IssueSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [draft, setDraft] = useState(value);
  const published = useRef<string | null>(null);
  const latestChange = useRef(onChange);
  useEffect(() => { latestChange.current = onChange; }, [onChange]);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // Only a change to the search term itself resets the box. The effect used
  // to run on every render where `value` was not what we last published,
  // which includes the renders caused by *other* filters: changing Level
  // while a keystroke was still inside the 200ms debounce cancelled that
  // publish, and the typed term vanished from the URL and the results.
  const fromUrl = useRef(value);
  useEffect(() => {
    if (value === fromUrl.current) return;
    fromUrl.current = value;
    if (value === published.current) return;
    clearTimeout(timer.current);
    setDraft(value);
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

/** "4 Sep 2026, 15:16", a scan's own finish time, in the reader's locale. */
function formatCompleted(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return at.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
