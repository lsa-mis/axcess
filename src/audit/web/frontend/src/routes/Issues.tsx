import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Info,
  Search,
} from "lucide-react";
import { api } from "../api/client";
import { Card, Select, withReturnTrail, type SelectOption } from "../components/ui";
// The same helper the topbar trail and the overview use.
import { siteLabel } from "../components/ReportCrumb";
import ConformanceBadge from "../components/ConformanceBadge";
import ExportMenu from "../components/ExportMenu";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
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
 * Each column is one of the facts the old right-hand evidence pane listed
 * for the selected issue (type, criterion, priority, spread, difficulty,
 * owner), so the whole report can be compared at a glance instead of one
 * issue at a time. The two things that do not fit in a cell open from the
 * row without leaving it: "About" expands an inline panel with the issue's
 * description, and the page count links to a page of its own
 * (``/scans/:id/issues/:key/pages``) listing every affected page in
 * columns. Both stay in the reading order and in the current tab, which is
 * the behaviour the desktop app needs because it has no browser back
 * button; the topbar trail is the way back, and every link out of here
 * carries the origin it needs to draw that trail.
 *
 * The per-issue route (``/scans/:id/issues/:key``) still exists for deep
 * links and for the full evidence record.
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
  const hasFilter = Boolean(conformance || lane || q);
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
                {/* The site leads, as on the overview. This tab is reachable
                    by its own URL, and like every other view it loses the
                    topbar trail the moment it becomes a screenshot or a
                    print -- which is most of how a finding gets quoted to
                    the team that has to fix it. */}
                {siteLabel(scan.seed_url)}
                {" · "}
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

      {/* Filtering changed the table silently: the count line under the title
          updated, but nothing announced it, so a screen-reader user typing in
          the search box got no confirmation that anything had happened (SC
          4.1.3). Visually hidden because the same sentence is already on
          screen in the header — this is the same fact, routed to the people
          the visual update skips. */}
      <p role="status" className="sr-only">
        {issuesQuery.isFetching
          ? "Updating issues…"
          : `${rows.length} of ${data.total_unfiltered} issue groups shown` +
            (hasFilter ? ", filtered" : "")}
      </p>

      <Card className="overflow-hidden">
        <IssueToolbar
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
    </>
  );
}

function IssueToolbar({
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
  return (
    <div className="border-b border-border bg-surface-subtle p-3">
      <div className="relative max-w-xl">
        <Search
          className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle"
          aria-hidden
        />
        <IssueSearch value={q} onChange={(value) => onParam("q", value)} />
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
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
  "About",
] as const;
type Column = (typeof COLUMNS)[number];
type SortColumn = Exclude<Column, "About">;
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
 * Nine columns do not fit at phone width, so the table sits in a scroll
 * region of its own rather than forcing the page sideways (the shell keeps
 * ``overflow-x: hidden`` on the document). The region is focusable so a
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
      <table className="w-full min-w-[64rem] text-sm">
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
              if (column === "About") {
                return (
                  <th key={column} scope="col" className={cn(cell, "px-3 py-2")}>
                    {column}
                  </th>
                );
              }
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
                      "group inline-flex min-h-target items-center gap-1.5 rounded-xs px-2 text-2xs font-semibold hover:bg-border/50 focus-visible:outline-none focus-visible:shadow-focus",
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
 * One issue group and, under it, its "About" panel.
 *
 * The panel is a second ``<tr>`` that is always mounted and toggled with
 * ``hidden``, so the button's ``aria-controls`` always names a real element
 * and the description reads in place, straight after the row, for anyone
 * moving through the table linearly. Both rows share one band so they read
 * as one record; ``odd:``/``even:`` on the ``<tr>`` would stripe halfway
 * through it.
 */
function IssueTableRow({ scanId, row, index }: { scanId: number; row: IssueRow; index: number }) {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const isInformational = row.review_lane === "informational";
  const slug = row.issue_key.replace(/[^A-Za-z0-9_-]/g, "-");
  const titleId = `issue-${slug}-title`;
  const buttonId = `issue-about-${slug}-button`;
  const panelId = `issue-about-${slug}-panel`;
  const band = index % 2 === 1 ? "bg-surface-subtle" : "bg-surface";
  const Caret = open ? ChevronDown : ChevronRight;
  const detailPath = `/scans/${scanId}/issues/${encodeURIComponent(row.issue_key)}`;
  // The pages table needs the way back to this list, filters included.
  const here = `${location.pathname}${location.search}`;
  const pagesPath = withReturnTrail(`${detailPath}/pages`, "Issues", here);

  return (
    <Fragment>
      <tr className={cn(band, "border-t border-border")}>
        <th
          scope="row"
          className={cn(
            band,
            "sticky left-0 z-[1] max-w-[18rem] min-w-[14rem] px-3 py-2.5 text-left align-top font-semibold shadow-[inset_-1px_0_0_theme(colors.border.DEFAULT)]",
          )}
        >
          {/* The title is the row's main link and opens the issue's full
              evidence record: what it is, why it matters, the fix, and its
              pages. The page count beside it is the shortcut straight to
              the pages. It is styled
              like every other link so nobody has to guess it is one. The
              other links in this row point at this id for their context
              instead of repeating the title in their own names: a name is
              what gets read on every stop, a description only on request. */}
          {/* min-h-target goes on the link, not as padding on the cell: SC
              2.5.5 measures the target itself, and a 38px-high link inside a
              taller cell is still a 38px target. */}
          <Link
            id={titleId}
            to={withReturnTrail(detailPath, "Issues", here)}
            data-issue-link="true"
            className="flex min-h-target items-center text-umich-blue underline underline-offset-2 hover:text-umich-blue-600"
          >
            {row.title}
            <span className="sr-only">, full evidence</span>
          </Link>
        </th>
        <td className="whitespace-nowrap px-3 py-2.5 align-top">
          <Tag tone={isInformational ? "neutral" : "flag"}>{laneLabel(row.review_lane)}</Tag>
        </td>
        <td className="whitespace-nowrap px-3 py-2.5 align-top">
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
        <td className="whitespace-nowrap px-3 py-2.5 align-top">
          {isInformational ? (
            <span className="text-fg-muted">n/a</span>
          ) : (
            // The band, not the score: "11.28" means nothing to a reader,
            // and two decimals invited comparing issues by hundredths. The
            // score still orders the column; the word is what shows.
            priorityTier(row.priority)
          )}
        </td>
        <td className="whitespace-nowrap px-3 py-2.5 text-right align-top tabular-nums">
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
        <td className="whitespace-nowrap px-3 py-2.5 text-right align-top tabular-nums">
          {row.occurrence_count}
        </td>
        <td className="whitespace-nowrap px-3 py-2.5 align-top">
          {isInformational || row.difficulty === "Unknown" ? (
            <span className="text-fg-muted">n/a</span>
          ) : (
            row.difficulty
          )}
        </td>
        <td className="whitespace-nowrap px-3 py-2.5 align-top">
          {isInformational ? (
            <span className="text-fg-muted">n/a</span>
          ) : (
            capitalize(row.responsibility)
          )}
        </td>
        <td className="whitespace-nowrap px-3 py-1 align-top">
          <button
            type="button"
            id={buttonId}
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((value) => !value)}
            className="inline-flex min-h-target items-center gap-1 rounded-xs px-2 text-sm font-semibold text-umich-blue hover:bg-surface-muted focus-visible:outline-none focus-visible:shadow-focus"
          >
            <Caret className="h-4 w-4 shrink-0" aria-hidden />
            <span>About</span>
            <span className="sr-only"> this issue: {row.title}</span>
          </button>
        </td>
      </tr>
      <tr id={panelId} hidden={!open} className={band}>
        <td colSpan={COLUMNS.length} className="px-3 pb-4 pt-1">
          <div
            role="region"
            aria-labelledby={buttonId}
            className="max-w-3xl rounded-xs border border-border bg-surface p-4"
          >
            <AboutIssue row={row} detailPath={detailPath} titleId={titleId} />
          </div>
        </td>
      </tr>
    </Fragment>
  );
}

/** The issue's description, why it matters, the fix, and where the full record lives. */
function AboutIssue({
  row,
  detailPath,
  titleId,
}: {
  row: IssueRow;
  detailPath: string;
  titleId: string;
}) {
  const isInformational = row.review_lane === "informational";
  return (
    <>
      <h2 className="text-2xs font-semibold text-fg-subtle">What it is</h2>
      <p className="mt-1 text-sm text-fg">
        {row.description ||
          row.evidence_summary ||
          "This is an automated evidence record. Open the affected pages for the captured detail."}
      </p>
      {row.review_lane === "expert_review" && (
        <p className="mt-2 text-sm font-semibold">
          Do not describe this as a confirmed barrier until the expert decision is documented.
        </p>
      )}
      {isInformational && (
        <p className="mt-2 text-sm font-semibold">
          No barrier was detected by this check. This record is read-only evidence retained for transparency.
        </p>
      )}
      {!isInformational && row.why_matters && (
        <p className="mt-2 text-sm text-fg-muted">
          <span className="font-semibold text-fg">Why it matters:</span> {row.why_matters}
        </p>
      )}
      {!isInformational && row.fix_steps.length > 0 && (
        <>
          <h2 className="mt-4 text-2xs font-semibold text-fg-subtle">Expected behavior</h2>
          <ol className="mt-1 list-decimal space-y-1.5 pl-5 text-sm text-fg">
            {row.fix_steps.map((step, i) => (
              <li
                key={i}
                // Steps include inline <code> / <em> from the YAML.
                // We trust YAML authors (it's our own rule book).
                dangerouslySetInnerHTML={{ __html: step }}
              />
            ))}
          </ol>
        </>
      )}
      {!isInformational && row.acceptance && (
        <p className="mt-2 text-sm text-fg-muted">
          <span className="font-semibold text-fg">Done when:</span> {row.acceptance}
        </p>
      )}
      {!isInformational && row.abilities_affected.length > 0 && (
        <p className="mt-3 text-sm">
          <span className="font-semibold text-fg">Abilities affected:</span>{" "}
          {row.abilities_affected.map((a) => capitalize(a)).join(", ")}
        </p>
      )}
      <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <Link
          to={detailPath}
          aria-describedby={titleId}
          className="font-semibold text-umich-blue underline underline-offset-2"
        >
          Full evidence record
        </Link>
        {row.help_url && (
          <a
            href={row.help_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-semibold text-umich-blue underline underline-offset-2"
          >
            Rule docs
            <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
            <span className="sr-only">, opens in a new tab</span>
          </a>
        )}
      </p>
    </>
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
