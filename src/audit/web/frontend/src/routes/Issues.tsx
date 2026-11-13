import { Fragment, memo, useMemo, useRef, type ReactNode, type Ref } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, withReturnTrail } from "../components/ui";
// The same helper the topbar trail uses.
import { siteLabel } from "../components/ReportCrumb";
import ConformanceBadge from "../components/ConformanceBadge";
import ExportMenu from "../components/ExportMenu";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import {
  Cell,
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
import {
  ActiveFilters,
  FilterMenu,
  activeFilterItems,
  splitFilter,
  type FilterGroup,
} from "../components/table/FilterMenu";
import {
  compareText,
  sortWords,
  type Sort,
  type SortDirection,
  type SortKind,
} from "../components/table/sort";
import ReportHeader from "../components/ReportHeader";
import HowSureTag from "../components/HowSureTag";
import ReportDangerZone from "../components/ReportDangerZone";
import {
  GlossaryList,
  ReportCoverageNote,
  ReportNote,
  ReportNotes,
  ReportSummary,
} from "../components/ReportSummary";
import { cn } from "../lib/cn";
import { liveSearchParams } from "../lib/liveSearchParams";
import { HIDDEN_ISSUE_FIELDS } from "../lib/hiddenIssueFields";
import {
  FINDING_TYPES,
  FINDING_TYPE_HELP,
  FINDING_TYPE_LABELS,
  ISSUE_COLUMN_HELP,
  PRIORITY_HELP,
  REVIEW_LANES,
  REVIEW_LANE_HELP,
  isFindingType,
} from "../lib/labels";
import { CHECK_LABEL, REVIEW_TYPE_LABEL } from "../lib/terms";
import { useScanQuery } from "../hooks/useScanQuery";
import type {
  ConformanceLabel,
  FindingType,
  IssueRow,
  ReviewLane,
} from "../api/types";

/**
 * The primary report: every issue type as one row of a flat table.
 *
 * This is where a report opens. The numbers that used to be an Overview tab
 * sit above the table (``ReportSummary``); what was checked, what the labels
 * mean and the expert tools sit closed below it, so the table follows the
 * numbers directly.
 *
 * Each column is one of the facts the old right-hand evidence pane listed
 * for the selected issue (type, criterion, priority, spread, difficulty,
 * owner), so the whole report can be compared at a glance instead of one
 * issue at a time. What does not fit in a cell is one link away: the title
 * opens the issue type's full record, which leads with every affected page
 * in columns, then what it is, why it matters, and the fix. The page count
 * was a second link, to a page listing the same pages
 * (``/scans/:id/issues/:key/pages``), until 2026-11-02: one job, two
 * links in one row, so the developer made the count a plain number (W3C
 * COGA, "Making Content Usable": one way to do one thing; paraphrased).
 * The topbar trail is the way back,
 * which the desktop app needs because it has no browser back button, and
 * every link out of here carries the origin it needs to draw that trail.
 *
 * The DOM-engine and image-evidence views used to be two buttons under the
 * table. Their rows were already here; what was missing was a way to tell
 * them apart, so the table has a Finding type column (WCAG, Click-Through,
 * Alt Text) and a filter for it, and each of those detailed views is linked
 * from the filter it belongs to.
 */
export default function IssuesRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  // Each filter is a comma-separated list of the values checked ("A,AA"),
  // kept to the values the group offers, in its order; "" is every row.
  const conformance = parseList(params.get("conformance"), CONFORMANCE_LEVELS);
  const lane = parseList(params.get("type"), REVIEW_LANES);
  const findingType = parseList(params.get("finding_type"), FINDING_TYPES);
  const q = params.get("q") ?? "";
  const rawSort = params.get("sort");
  // The same object until ``?sort=`` changes, so the rows below are sorted
  // once per sort, not once per render.
  const sort = useMemo(() => parseSort(rawSort), [rawSort]);
  const hasFilter = Boolean(conformance || lane || findingType || q);
  const location = useLocation();
  // Where links out of the table return to, filters included.
  const here = `${location.pathname}${location.search}`;

  const scanQuery = useScanQuery(id);
  const issuesQuery = useQuery({
    // Ordering is done here, not by the server: every row is already in
    // hand, and the column headers can then sort by any column in either
    // direction instead of the four orders the API offers.
    queryKey: ["issues", id, conformance, lane, findingType, q],
    queryFn: () =>
      api.listIssues(id, {
        conformance,
        review_lane: lane,
        finding_type: findingType,
        q,
        sort: "priority_desc",
      }),
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
  // a filter. React Router's `previous` is the last render's query string,
  // not the live one, so the address itself is read (liveSearchParams).
  const setParam = (key: string, value: string) => {
    setParams(
      () => {
        const next = liveSearchParams();
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
  };
  // The Filter menu's "Clear all": every group back to "All" in one update.
  // One ``setParam`` per group would not do: react-router starts each call
  // in an event from the same query string, so the second call would put
  // back what the first removed. The search and the sort stay.
  const resetFilters = () => {
    setParams(
      () => {
        const next = liveSearchParams();
        for (const key of ["conformance", "type", "finding_type", "page"]) next.delete(key);
        return next;
      },
      { replace: true },
    );
  };

  const rows = useMemo(
    () => sortRows(issuesQuery.data?.rows ?? [], sort),
    [issuesQuery.data, sort],
  );
  // The pager sits in the bar over the table, so the rows are paged here,
  // before the table is drawn, and the bar shows even when no row matches.
  // A new filter, search or sort starts over at page 1; the key is built
  // from those, not from every row's key.
  const paged = usePagedRows(rows, {
    resetKey: [conformance, lane, findingType, q, rawSort ?? ""].join("|"),
  });
  const region = useRef<HTMLDivElement>(null);

  const error = scanQuery.error ?? issuesQuery.error;
  if (error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        The Issues table could not load. Nothing in the saved report has changed.
        Reload the page to try again.
      </Card>
    );
  }
  if (!scanQuery.data || !issuesQuery.data) {
    return <p className="text-sm text-fg-muted" role="status">Loading issues…</p>;
  }

  const scan = scanQuery.data;
  const data = issuesQuery.data;
  const isComplete = scan.status === "completed";
  const summaryRows = hasFilter ? summaryQuery.data?.rows : data.rows;
  const onSort = (next: SortState) => setParam("sort", serializeSort(next));
  const exportMenu = (
    <ExportMenu
      scanId={scan.id}
      site={siteLabel(scan.seed_url)}
      pageCount={scan.page_count}
      issueGroups={data.total_unfiltered}
      shownIssueGroups={hasFilter ? rows.length : undefined}
    />
  );
  // The button that was pressed goes away with the column sort, so focus
  // moves to the table it just reordered rather than falling to the page.
  const recommend = () => {
    onSort(null);
    region.current?.focus();
  };

  return (
    <>
      <ReportHeader
        tabs
        scanId={scan.id}
        previousScanId={scan.previous_scan_id}
        title="Issues"
        // The heading and Export report only (2026-10-30, the developer's
        // request). "Based on the report generated…" under the heading and
        // "Scan again" beside Export were removed, to give the space to the
        // report: the date is on Reports ("Scanned"), and "Scan again" is in
        // the site's row there, beside "Open latest scan". Export report
        // was tried at the end of the summary numbers' row, centred on it,
        // and moved back here: centred against numbers of different heights
        // it looked out of line; top right, level with the heading, it does
        // not (the developer's call). It stays the header's last action, the
        // edge its panel hangs from (see ExportMenu).
        actions={exportMenu}
      />

      {isComplete && (
        <ReportSummary
          scan={scan}
          issueGroups={data.total_unfiltered}
          occurrences={data.occurrence_counts.all_evidence}
        />
      )}

      {/* Filtering changed the table silently: the visible count updated,
          but nothing announced it, so a screen-reader user typing in the
          search box got no confirmation that anything had happened (SC
          4.1.3). Visually hidden because the status line under the bar
          already shows the filtered count — this is the same fact, routed
          to the people the visual update skips. */}
      <p role="status" className="sr-only">
        {issuesQuery.isFetching
          ? "Updating issues…"
          : `${rows.length} of ${data.total_unfiltered} ${data.total_unfiltered === 1 ? "issue type" : "issue types"} shown` +
            (hasFilter ? ", filtered" : "") +
            // By "How sure" value too, so a reader hears how many are Mostly
            // sure without walking the How sure column.
            (rows.length > 0 ? `: ${laneSummary(rows)}` : "")}
      </p>

      {/* No ``overflow-hidden``: it would clip the Filter menu's panel on a
          short, filtered table. The table scrolls in its own region. */}
      <Card>
        <IssueToolbar
          conformanceCounts={data.conformance_counts}
          laneCounts={data.review_lane_counts}
          findingTypeCounts={data.finding_type_counts}
          q={q}
          conformance={conformance}
          lane={lane}
          findingType={findingType}
          onParam={setParam}
          onResetFilters={resetFilters}
          onClearFilters={() => setParams(new URLSearchParams(), { replace: true })}
          pager={<TablePagination label="Issues" noun="issue types" {...paged} />}
        />
        {/* Only for exactly one finding type: the link names one view. */}
        {isFindingType(findingType) && (
          <FindingTypeViewLink scanId={scan.id} findingType={findingType} imageCount={scan.finding_count} />
        )}
        {/* WAI-ARIA sortable table: the line over it says what the order is,
            with the filtered count and the way back to the recommended order
            beside it.

            Shown only when the table is sorted by a column or filtered
            (2026-11-02), and never with the sentence "Recommended order:
            Mostly sure, then Not sure, then For information.", which the
            developer asked to remove: the How sure column already shows
            that grouping, top to bottom. Removing
            the line in every state was the request, and was set aside here
            because the line then holds the only way back to the recommended
            order (a sorted header only flips between its two directions),
            and the count of what a filter left (W3C COGA, "Making Content
            Usable": do not take away the way back).

            The order is still said to a screen reader on every change, by
            the live region under this comment, which stays on the page
            whether or not the line shows; the line itself is not a live
            region (`announce={false}`), so nothing is read twice (SC 4.1.3
            Status Messages, Level AA). The table's caption says the order
            too. */}
        <p role="status" className="sr-only">
          {describeSort(sort)}.
        </p>
        {(sort || hasFilter) && (
          <TableStatus
            announce={false}
            actions={
              <>
                {hasFilter && (
                  <span className="tabular-nums">
                    {rows.length.toLocaleString()} of {data.total_unfiltered.toLocaleString()} shown
                  </span>
                )}
                {sort && (
                  // eslint-disable-next-line react/forbid-elements -- Convert: a text-link styled button; needs a link variant on Button
                  <button
                    type="button"
                    onClick={recommend}
                    className="min-h-target rounded-xs px-1 font-semibold text-umich-blue underline underline-offset-2 hover:text-umich-blue-600 focus-visible:outline-none focus-visible:shadow-focus"
                  >
                    Back to recommended order
                  </button>
                )}
              </>
            }
          >
            {/* The sentence "Recommended order: …" is never shown, only
                spoken (see above): with a filter on and the default order,
                the line holds the count alone. */}
            {sort && `${describeSort(sort)}.`}
          </TableStatus>
        )}
        {rows.length === 0 ? (
          <TableEmpty>
            {hasFilter
              ? "No issues match these filters. Clear a filter to see more results."
              : "Axcess found no issues. That does not mean the site meets WCAG, because some checks may not have run. See “What was checked”, below this table."}
          </TableEmpty>
        ) : (
          <IssueTable
            scanId={scan.id}
            paged={paged}
            here={here}
            sort={sort}
            onSort={onSort}
            busy={issuesQuery.isFetching}
            regionRef={region}
          />
        )}
        <TablePagination label="Issues" noun="issue types" place="end" {...paged} />
      </Card>

      {/* Under the table since user testing (2026-10-28): the table follows
          the numbers with nothing to step over. Why, and what keeps the
          limit in view, is on ReportCoverageNote. */}
      <ReportNotes className="mt-8">
        {isComplete && <ReportCoverageNote scan={scan} rows={summaryRows} />}
        <IssueGlossary />
      </ReportNotes>

      <ReportDangerZone scan={scan} />
    </>
  );
}

/**
 * The bar over the issue table: the search and one Filter menu on the
 * left, the pager on the right, and what narrows the table written out
 * under both. Each filter group keeps its URL parameter (``?conformance=``,
 * ``?type=``, ``?finding_type=``), so a shared or reloaded link opens the
 * same rows.
 */
function IssueToolbar({
  conformanceCounts,
  laneCounts,
  findingTypeCounts,
  q,
  conformance,
  lane,
  findingType,
  onParam,
  onResetFilters,
  onClearFilters,
  pager,
}: {
  conformanceCounts: Record<ConformanceLabel, number>;
  laneCounts: Record<ReviewLane, number>;
  /** Absent from responses cached before the field existed. */
  findingTypeCounts: Record<FindingType, number> | undefined;
  q: string;
  /** Each a comma-separated list of the checked values; "" is all. */
  conformance: string;
  lane: string;
  findingType: string;
  onParam: (key: string, value: string) => void;
  /** Every filter group back to "All" at once; the search stays. */
  onResetFilters: () => void;
  /** Everything back to the report as it opens: filters, search and sort. */
  onClearFilters: () => void;
  pager: ReactNode;
}) {
  // Checkboxes: several of a group can be on at once, and none on is all.
  const groups: FilterGroup[] = [
    {
      key: "conformance",
      label: "Level",
      value: conformance,
      multiple: true,
      options: [
        { value: "A", label: "Level A", count: conformanceCounts.A ?? 0 },
        { value: "AA", label: "Level AA", count: conformanceCounts.AA ?? 0 },
        { value: "AAA", label: "Level AAA", count: conformanceCounts.AAA ?? 0 },
        { value: "BP", label: "Best practice", count: conformanceCounts.BP ?? 0 },
      ],
    },
    // The filter takes the column's own name ("How sure"), so the filter
    // and the column read as one thing and its options read as the cells do.
    {
      key: "type",
      label: COLUMN_LABEL.Type,
      value: lane,
      multiple: true,
      options: [
        ...REVIEW_LANES.map((key) => ({
          value: key,
          label: REVIEW_TYPE_LABEL[key],
          count: laneCounts[key] ?? 0,
        })),
      ],
    },
    // An issue type found both at page load and after clicking is listed under
    // both, so these counts can add up to more than the whole table. Named
    // as its column is ("Where it shows"): "finding" is not an interface word.
    {
      key: "finding_type",
      label: COLUMN_LABEL["Finding type"],
      value: findingType,
      multiple: true,
      options: [
        ...FINDING_TYPES.map((key) => ({
          value: key,
          label: FINDING_TYPE_LABELS[key],
          count: findingTypeCounts?.[key] ?? 0,
        })),
      ],
    },
  ];
  const active = activeFilterItems(groups);
  if (q) active.push(`Search: “${q}”`);
  return (
    <TableBar pager={pager} footer={<ActiveFilters items={active} onClear={onClearFilters} />}>
      <TableSearch
        label="Search issues"
        placeholder="Issue type or WCAG number (1.4.3)"
        value={q}
        onChange={(value) => onParam("q", value)}
      />
      <FilterMenu
          label="Filter issues" groups={groups} onChange={onParam} onReset={onResetFilters} />
    </TableBar>
  );
}

const CONFORMANCE_LEVELS = ["A", "AA", "AAA", "BP"] as const satisfies readonly ConformanceLabel[];

/**
 * A filter parameter as the checked values: "AA,A,nope" → "A,AA". Unknown
 * values are dropped and the rest put in the group's order, so a hand-edited
 * or stale link narrows by what it can and the server sees one spelling.
 */
function parseList(raw: string | null, allowed: readonly string[]): string {
  const on = new Set(splitFilter(raw ?? ""));
  return allowed.filter((value) => on.has(value)).join(",");
}

const COLUMNS = [
  "Issue",
  // How sure, then Priority and Issue occurrences, right after the issue
  // type's name (the developer's order, 2026-11-02). How sure comes first
  // because it says whether to trust the Priority beside it: a High on a
  // Not sure row is a lead to confirm, not a found problem, and the
  // product keeps facts apart from leads (AGENTS.md). It is also the
  // recommended order's first key, with priority ordering the rows inside
  // each How sure group, so the columns read left to right in the order the
  // rows are sorted. Priority and Issue occurrences followed WCAG criterion
  // until that day, and were briefly second and third, ahead of How sure.
  "Type",
  "Priority",
  "Occurrences",
  // Affected pages right after Issue occurrences (2026-11-02), as Reports
  // orders its counts: issue occurrences, then pages. It was the last column.
  "Pages",
  "Finding type",
  "Check",
  "WCAG",
  "Difficulty",
  "Responsibility",
] as const;
type SortColumn = (typeof COLUMNS)[number];
/**
 * What each column header says. The column keys above stay as they are:
 * they are the ``?sort=`` vocabulary and ``HIDDEN_ISSUE_FIELDS``' names.
 * "Finding type" reads "Where it shows", because "finding" is not an
 * interface word (docs/plain-language.md) and every value answers that
 * question (see FINDING_TYPE_LABELS in lib/labels.ts).
 *
 * "Issue" reads "Issue type": a row gathers every place one check found
 * for one reason. "Occurrences" counts those places: an occurrence is one
 * place a problem shows up, and the column's hint says so (ISSUE_COLUMN_HELP,
 * lib/labels.ts). Until 2026-10-26 the row was "an issue"; that day the
 * developer made the row "an issue type" and each place "an issue",
 * because people called each place an issue and "occurrence" is an
 * advanced word. On 2026-10-28 user testing with Siteimprove users, who
 * know Siteimprove's "issues" and "occurrences", led the developer to bring
 * back "Occurrences" for the places; the row stays "Issue type". The
 * research and the reason are in docs/plain-language.md, "Why "occurrence"
 * and "issue type"" (W3C COGA, "Making Content Usable",
 * https://www.w3.org/TR/coga-usable/: the same word for the same thing).
 */
const COLUMN_LABEL: Record<SortColumn, string> = {
  Issue: "Issue type",
  // "How sure", not "Type": the column says how sure Axcess is that a
  // issue type is a real problem, and "Type" named no question (see
  // REVIEW_TYPE_LABEL in lib/terms.ts).
  Type: "How sure",
  "Finding type": "Where it shows",
  // Which check found the row, by its interface name (CHECK_LABEL), after
  // where it shows: both say where the evidence came from. Testers who use
  // Siteimprove asked whether an issue came from axe or from Siteimprove
  // (user testing, 2026-10-28); the header's hint names who makes each
  // rule check. Each row comes from one check (IssueRow.pipeline), so the
  // cell is one name, never a list.
  Check: "Check",
  // "WCAG criterion" (2026-10-30, the developer's choice): the cell holds a
  // success criterion's number and its level badge, and sorts by the number.
  // "WCAG level" was proposed and set aside, since the header would then not
  // name the number; "WCAG criterion and level" was longer than it needed to
  // be, the badge saying its level by itself.
  WCAG: "WCAG criterion",
  Priority: "Priority",
  // "Affected pages" (2026-11-02), the words the trail already uses for an
  // issue type's pages ("131 affected pages"). Not "Impacted pages": impact
  // names the Critical/Serious/Moderate/Minor rating, so it could be read as
  // pages with serious problems.
  Pages: "Affected pages",
  Occurrences: "Issue occurrences",
  Difficulty: "Difficulty",
  Responsibility: "Who fixes it",
};
/** The columns drawn: every one not hidden for now (see ``HIDDEN_ISSUE_FIELDS``). */
const VISIBLE_COLUMNS = COLUMNS.filter((column) => !HIDDEN_ISSUE_FIELDS.has(column));
const shows = (column: SortColumn) => !HIDDEN_ISSUE_FIELDS.has(column);
/**
 * The table's order: one column in one direction, or ``null`` for the
 * recommended order (grouped by type, barriers first, then by priority).
 *
 * The recommended order used to be what the Priority header meant, so that
 * one header grouped by type while every other header sorted flat. It is its
 * own order now, the default, drawn with a header row per type so the
 * grouping shows. Every header sorts flat, the same way.
 */
type SortState = Sort<SortColumn> | null;

/**
 * ``?sort=`` keys, one per column and direction. The API's ``pages_desc``,
 * ``occurrences_desc`` and ``conformance`` keep their old spellings so saved
 * links still open the same order. The API's ``priority_desc`` is lane-first,
 * so a saved link with it opens the recommended order (see ``parseSort``);
 * the flat Priority sort has keys of its own.
 */
const SORT_KEYS: Record<SortColumn, string> = {
  Issue: "title",
  Type: "type",
  "Finding type": "finding_type",
  Check: "check",
  WCAG: "wcag",
  Priority: "score",
  Pages: "pages",
  Occurrences: "occurrences",
  Difficulty: "difficulty",
  Responsibility: "responsibility",
};
const SORT_COLUMNS = Object.keys(SORT_KEYS) as SortColumn[];
/**
 * What each column sorts as (./table/sort): numbers open with the biggest
 * first and read "high → low"; words open alphabetically and read "A → Z".
 */
const SORT_KINDS: Record<SortColumn, SortKind> = {
  Issue: "text",
  Type: "text",
  "Finding type": "text",
  Check: "text",
  WCAG: "text",
  Priority: "number",
  Pages: "number",
  Occurrences: "number",
  Difficulty: "text",
  Responsibility: "text",
};
/** The recommended order has no ``?sort=``: it is what a report opens with. */
function serializeSort(sort: SortState): string {
  if (!sort) return "";
  if (sort.column === "WCAG" && sort.direction === "asc") return "conformance";
  return `${SORT_KEYS[sort.column]}_${sort.direction}`;
}

function parseSort(raw: string | null): SortState {
  if (!raw || raw === "priority_desc") return null;
  if (raw === "conformance") return { column: "WCAG", direction: "asc" };
  const match = raw.match(/^(.+)_(asc|desc)$/);
  if (!match) return null;
  // A hidden column has no header to show its order, so a saved link
  // sorted by one opens the recommended order instead.
  const column = SORT_COLUMNS.find((c) => SORT_KEYS[c] === match[1] && shows(c));
  return column ? { column, direction: match[2] as SortDirection } : null;
}

/** What the order means in words, for the status line and the caption. */
function describeSort(sort: SortState): string {
  if (!sort) {
    return `Recommended order: ${REVIEW_LANES.map((lane) => REVIEW_TYPE_LABEL[lane]).join(", then ")}`;
  }
  return `Sorted by ${COLUMN_LABEL[sort.column]}, ${sortWords(SORT_KINDS[sort.column], sort.direction)}`;
}

const LANE_RANK: Record<ReviewLane, number> = { likely_barrier: 0, expert_review: 1, informational: 2 };

/**
 * Finding types in table order, the first type leading: a WCAG row, then a
 * row that is WCAG and Click-Through, then Click-Through only, then Alt Text.
 */
function findingTypeRank(row: IssueRow): number[] {
  const types = row.finding_types ?? [];
  return [FINDING_TYPES.indexOf(types[0] ?? "wcag"), types.length > 1 ? 0 : 1];
}
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
      return compareText(a.title, b.title);
    case "Type":
      return LANE_RANK[a.review_lane] - LANE_RANK[b.review_lane];
    case "Finding type":
      return compareLists(findingTypeRank(a), findingTypeRank(b));
    case "Check":
      return compareText(CHECK_LABEL[a.pipeline], CHECK_LABEL[b.pipeline]);
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
      return compareText(a.responsibility, b.responsibility);
  }
}

/** Whether the cell reads "Does not apply" (see ``IssueTableRow``), so it has no value to sort by. */
function notApplicable(row: IssueRow, column: SortColumn): boolean {
  const informational = row.review_lane === "informational";
  switch (column) {
    case "Priority":
    case "Responsibility":
      return informational;
    case "Difficulty":
      return informational || row.difficulty === "Unknown";
    default:
      return false;
  }
}

/**
 * A stable sort: ties keep the server's order.
 *
 * The recommended order is lane-first: a barrier outranks a "needs review"
 * lead outranks an informational record, whatever their scores, and the
 * score only orders rows *within* a lane. That is the order a reviewer should
 * work in, which is why it is the default.
 *
 * A column sort is flat. A cell that reads "Does not apply" sorts after every
 * value in both directions, as an empty cell does in a spreadsheet: it is not a
 * low priority, so it must not open the "low → high" order.
 */
function sortRows(rows: IssueRow[], sort: SortState): IssueRow[] {
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      if (!sort) {
        const lane = LANE_RANK[a.row.review_lane] - LANE_RANK[b.row.review_lane];
        if (lane !== 0) return lane;
        const score = b.row.priority - a.row.priority;
        if (score !== 0) return score;
        return a.index - b.index;
      }
      const missing = Number(notApplicable(a.row, sort.column)) - Number(notApplicable(b.row, sort.column));
      if (missing !== 0) return missing;
      const sign = sort.direction === "asc" ? 1 : -1;
      const primary = compareRows(a.row, b.row, sort.column) * sign;
      if (primary !== 0) return primary;
      return a.index - b.index;
    })
    .map(({ row }) => row);
}

/**
 * How many shown rows are of each type, for the live status line: "Mostly
 * sure 3, Not sure 7, For information 2". Every type is named, zeros included,
 * so the sentence reads the same way each time the filters change.
 */
function laneSummary(rows: IssueRow[]): string {
  const counts: Partial<Record<ReviewLane, number>> = {};
  for (const row of rows) counts[row.review_lane] = (counts[row.review_lane] ?? 0) + 1;
  return REVIEW_LANES.map((lane) => `${REVIEW_TYPE_LABEL[lane]} ${counts[lane] ?? 0}`).join(", ");
}

/**
 * The flat table itself.
 *
 * Nine columns do not fit at phone width, so the table sits in a scroll
 * region of its own rather than forcing the page sideways (the shell keeps
 * ``overflow-x: hidden`` on the document). At desktop width they do fit:
 * there is no minimum table width, the issue title is the one column that
 * wraps, and the cells are padded just enough to keep all eight in view
 * beside the expanded sidebar at 1280 px. The region is focusable so a
 * keyboard user can scroll it, and it is named so that focus lands on
 * something with a name. The issue column is sticky, so the row keeps its
 * label while the rest scrolls under it.
 *
 * The rows arrive paged (the pager is in the bar over the table). A short
 * last page leaves the table short (see usePagedRows).
 */
function IssueTable({
  scanId,
  paged,
  here,
  sort,
  onSort,
  busy,
  regionRef,
}: {
  scanId: number;
  paged: Pick<ReturnType<typeof usePagedRows<IssueRow>>, "pageRows" | "page" | "pageSize">;
  /** Where links out of the table return to. */
  here: string;
  sort: SortState;
  onSort: (next: SortState) => void;
  busy: boolean;
  regionRef: Ref<HTMLDivElement>;
}) {
  const offset = (paged.page - 1) * paged.pageSize;
  return (
    <TableRegion label="Issues table" busy={busy} regionRef={regionRef}>
      <Table caption={`Accessibility issue types, one per row. ${describeSort(sort)}.`}>
        <TableHead>
          <tr>
            {/* No ``whitespace-nowrap`` on a header: when nine columns are
                tight, the sorted header's chip drops under its label
                instead of widening the table past the region. The labels'
                words wrap too (`wrap="words"`, as on Reports): "Issue
                occurrences" (2026-10-30) on one line pushed the table 21
                pixels past its region at 1280 with Pages sorted. Every
                header wraps the same way, so their last lines stay level,
                and is padded 1.5 at the sides as the body cells are (see
                IssueTableRow): the shared 3 left the headers, not the data,
                setting the columns' widths. */}
            {VISIBLE_COLUMNS.map((column) => (
              <SortHeader
                key={column}
                column={column}
                wrap="words"
                kind={SORT_KINDS[column]}
                sort={sort}
                onSort={onSort}
                className={cn("px-1.5", column === "Issue" && "sticky left-0 z-[1] bg-surface-muted")}
                hint={columnHint(column)}
              >
                {column === "WCAG" ? (
                  <>
                    <abbr title="Web Content Accessibility Guidelines">WCAG</abbr> criterion
                  </>
                ) : (
                  COLUMN_LABEL[column]
                )}
              </SortHeader>
            ))}
          </tr>
        </TableHead>
        {/* One flat body in every order. The recommended order used to break
            into one row group per type, each opened by a header row; the Type
            cell already names every row's type, so those rows only split the
            table. The per-type counts they carried are announced instead, by
            the visually hidden status line above the table. */}
        <tbody>
          {paged.pageRows.map((row, index) => (
            <IssueTableRow key={row.issue_key} scanId={scanId} row={row} index={offset + index} here={here} />
          ))}
        </tbody>
      </Table>
    </TableRegion>
  );
}

/**
 * One issue type.
 *
 * There used to be an "About" column whose button opened the issue's
 * description in a second row under this one. It repeated what the title
 * link opens, and it was the column that got cut off, so it is gone: the
 * title is the one way to what an issue is.
 */
const IssueTableRow = memo(function IssueTableRow({
  scanId,
  row,
  index,
  here,
}: {
  scanId: number;
  row: IssueRow;
  /** Position for the row stripe. */
  index: number;
  /** This list's own address, filters included: the way back from the links. */
  here: string;
}) {
  const isInformational = row.review_lane === "informational";
  const detailPath = `/scans/${scanId}/issues/${encodeURIComponent(row.issue_key)}`;
  // Body cells are padded 1.5 rather than the shared 2, which is what keeps
  // all nine columns in view beside the expanded sidebar at 1280 px. Every
  // cell but the title is short, so it centres under its centred heading.
  const cell = "px-1.5 text-center";

  return (
    <Row index={index}>
      <RowHeader sticky className="min-w-[11rem] max-w-[18rem]">
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
          <span className="sr-only">, full details</span>
        </Link>
      </RowHeader>
      <Cell className={cn(cell, "whitespace-nowrap")}>
        <LaneTag lane={row.review_lane} />
      </Cell>
      <Cell className={cn(cell, "whitespace-nowrap")}>
        {isInformational ? (
          <span className="whitespace-normal text-fg-muted">Does not apply</span>
        ) : (
          // The band, not the score: "11.28" means nothing to a reader,
          // and two decimals invited comparing issues by hundredths. The
          // score still orders the column; the word is what shows.
          <span title={PRIORITY_HELP[priorityTier(row.priority)]}>{priorityTier(row.priority)}</span>
        )}
      </Cell>
      <Cell numeric className={cell}>
        {row.occurrence_count}
      </Cell>
      <Cell numeric className={cell}>
        {row.page_count}
      </Cell>
      <Cell className={cell}>
        <FindingTypeCell row={row} />
      </Cell>
      <Cell className={cell}>{CHECK_LABEL[row.pipeline] ?? row.pipeline}</Cell>
      <Cell className={cn(cell, "whitespace-nowrap")}>
        {row.wcag_sc ? (
          <>
            <span className="inline-flex items-center gap-1.5">
              <span className="tabular-nums">{row.wcag_sc}</span>
              <ConformanceBadge level={row.conformance} />
              {row.wcag_name && <span className="sr-only">{row.wcag_name}</span>}
            </span>
            {/* The rule's other criteria under the first, numbers on screen
                and names for a screen reader, as the first criterion's
                name is. Why "also": alsoWcagText in lib/labels.ts. */}
            {row.also_wcag.length > 0 && (
              <span className="mt-0.5 block text-xs tabular-nums text-fg-muted">
                also{" "}
                {row.also_wcag.map((ref, index) => (
                  <Fragment key={ref.sc}>
                    {index > 0 && ", "}
                    {ref.sc}
                    {ref.name && <span className="sr-only"> {ref.name}</span>}
                  </Fragment>
                ))}
              </span>
            )}
          </>
        ) : (
          <span className="text-fg-muted">Best practice</span>
        )}
      </Cell>
      {shows("Difficulty") && (
        <Cell className={cn(cell, "whitespace-nowrap")}>
          {isInformational || row.difficulty === "Unknown" ? (
            <span className="whitespace-normal text-fg-muted">Does not apply</span>
          ) : (
            row.difficulty
          )}
        </Cell>
      )}
      {shows("Responsibility") && (
        <Cell className={cn(cell, "whitespace-nowrap")}>
          {isInformational ? (
            <span className="whitespace-normal text-fg-muted">Does not apply</span>
          ) : (
            capitalize(row.responsibility)
          )}
        </Cell>
      )}
    </Row>
  );
});

/**
 * A row's type as the table shows it; the glossary reuses it so the two match.
 * On hover it says what the type means (the glossary's words), except in the
 * glossary, where the meaning is printed beside it.
 */
function LaneTag({ lane, hint = true }: { lane: ReviewLane; hint?: boolean }) {
  // The shared tag (components/HowSureTag.tsx), so Documents shows its "How
  // sure" values the same way.
  return (
    <HowSureTag
      label={REVIEW_TYPE_LABEL[lane]}
      help={hint ? REVIEW_LANE_HELP[lane] : undefined}
      quiet={lane === "informational"}
    />
  );
}

/**
 * The row's finding types as outlined pills, a different shape from the
 * filled review-lane tag beside them so the two columns do not read as one.
 * "After clicking" appears only when at least one of the group's errors was
 * found after clicking; a group seen both at page load and after clicking
 * shows "At page load" and "After clicking" together.
 *
 * Two pills always stack, one per line, at one width, so their edges line up
 * and the pair stays centred under the heading. They used to wrap only when
 * the table was tight, and two pills of different widths then centred one by
 * one, edges out of line (seen once the labels grew from "WCAG" and
 * "Click-Through"). Side by side on one line was rejected: it widens the
 * column and pushes the table past nine columns in view at 1280 px (see
 * `cell` in IssueTableRow). Stacking also keeps one row looking the same at every
 * width.
 */
function FindingTypeCell({ row }: { row: IssueRow }) {
  const types = row.finding_types ?? ["wcag"];
  return (
    <span className="inline-flex flex-col items-stretch gap-1">
      {types.map((type) => (
        <FindingTypePill key={type} type={type} />
      ))}
    </span>
  );
}

/** One finding type as the table shows it; the glossary reuses it, without the hover hint. */
function FindingTypePill({ type, hint = true }: { type: FindingType; hint?: boolean }) {
  return (
    <span
      title={hint ? FINDING_TYPE_HELP[type] : undefined}
      className="inline-flex items-center justify-center whitespace-nowrap rounded-full border border-border-strong px-1.5 py-px text-2xs font-semibold text-fg"
    >
      {FINDING_TYPE_LABELS[type]}
    </span>
  );
}

/**
 * What the counts and the Type and Finding type words mean, closed until
 * asked for.
 *
 * The counts lead: what an occurrence and an issue type are. The summary
 * numbers lost the lines that said so (user testing, 2026-10-28), and
 * "occurrence" is an advanced word, so its meaning must stay in words
 * everyone can reach, not only in the column's hover hint (SC 3.1.3 Unusual
 * Words, Level AAA).
 *
 * The tags in the table carry the same sentences as hover hints, but a hint
 * on a tag reaches only a mouse: this list is how keyboard and touch users,
 * and anyone who turned hints off, read them.
 */
function IssueGlossary() {
  return (
    <ReportNote
      id="report-labels"
      title={`What "${REVIEW_TYPE_LABEL.likely_barrier}", "${REVIEW_TYPE_LABEL.expert_review}" and the other labels mean`}
    >
      <div className="grid max-w-5xl gap-x-10 gap-y-4 text-sm leading-relaxed text-fg-muted md:grid-cols-2 xl:grid-cols-3">
        <GlossaryList
          heading="The numbers: what is counted"
          items={[
            {
              key: "occurrence",
              term: <span className="font-semibold text-fg">Occurrence</span>,
              help: "One place a problem appears: one element on one page, or in one page state. \"Issue occurrences\" counts them all.",
            },
            {
              key: "kind",
              term: <span className="font-semibold text-fg">Issue type</span>,
              help: "All the occurrences one check found for the same reason. Each is one row in the Issues table.",
            },
          ]}
        />
        <GlossaryList
          heading={`${COLUMN_LABEL.Type}: how sure Axcess is that an issue type is a real problem`}
          items={REVIEW_LANES.map((key) => ({ key, term: <LaneTag lane={key} hint={false} />, help: REVIEW_LANE_HELP[key] }))}
        />
        <GlossaryList
          heading={`${COLUMN_LABEL["Finding type"]}: where the problem shows up`}
          items={FINDING_TYPES.map((key) => ({
            key,
            term: <FindingTypePill type={key} hint={false} />,
            help: FINDING_TYPE_HELP[key],
          }))}
        />
        {/* The bands' meaning, such as Not sure never being High, in words
            everyone can reach, not only in a hover hint. */}
        <GlossaryList
          heading={`${COLUMN_LABEL.Priority}: which issue types to look at first`}
          items={(["High", "Medium", "Low"] as const).map((key) => ({
            key,
            term: <span className="font-semibold text-fg">{key}</span>,
            help: PRIORITY_HELP[key],
          }))}
        />
      </div>
    </ReportNote>
  );
}

/**
 * The detailed view behind a finding type, shown while the table is
 * filtered to it. These used to be buttons at the bottom of the report;
 * this is where a reader who wants them is already looking.
 */
function FindingTypeViewLink({
  scanId,
  findingType,
  imageCount,
}: {
  scanId: number;
  findingType: FindingType;
  imageCount: number;
}) {
  const view =
    findingType === "alt_text"
      ? {
          to: `/scans/${scanId}/findings`,
          // The Images view's own name, as the image text check calls it.
          label: `Images (${imageCount.toLocaleString()})`,
          note: "One card per image, with the text found in it, its alt text, and its status.",
        }
      : {
          to: `/scans/${scanId}/a11y`,
          label: "Rule check issues by WCAG criterion",
          note: "Every occurrence from the rule checks (axe and Alfa), grouped by WCAG criterion, with its page and element.",
        };
  return (
    <p className="flex flex-wrap items-center gap-x-2 border-b border-border px-3 py-1 text-xs text-fg-muted">
      <Link
        to={view.to}
        className="inline-flex min-h-target items-center font-semibold text-umich-blue underline underline-offset-2"
      >
        {view.label}
      </Link>
      <span>{view.note}</span>
    </p>
  );
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

/** The hover hint on a column's header, where one helps. */
function columnHint(column: SortColumn): string | undefined {
  const label = COLUMN_LABEL[column];
  return label in ISSUE_COLUMN_HELP ? ISSUE_COLUMN_HELP[label as keyof typeof ISSUE_COLUMN_HELP] : undefined;
}

/** A plain-English band for the priority score (``_priority`` in src/audit/web/issues.py). */
function priorityTier(priority: number): "High" | "Medium" | "Low" {
  if (priority >= 6) return "High";
  if (priority >= 3) return "Medium";
  return "Low";
}
