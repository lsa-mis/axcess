import { memo, useMemo } from "react";
import { Link } from "react-router";
import type { ComparisonChange, ComparisonRow } from "../../api/types";
import ConformanceBadge from "../ConformanceBadge";
import { TablePagination, usePagedRows } from "../TablePagination";
import { withReturnTrail } from "../ui";
import { cn } from "../../lib/cn";
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
} from "../table/Table";
import { ActiveFilters, FilterMenu, activeFilterItems, splitFilter, type FilterGroup } from "../table/FilterMenu";
import { compareText, sortWords, type Sort, type SortDirection, type SortKind } from "../table/sort";
import ChangeTag, { CHANGES, CHANGE_LABEL } from "./ChangeTag";
import { signed } from "./format";

export const COLUMNS = ["Change", "Issue", "WCAG", "Before", "After", "Difference"] as const;
export type SortColumn = (typeof COLUMNS)[number];
export type SortState = Sort<SortColumn>;

/** New issues first, then what is still there, then what went away. */
const CHANGE_RANK: Record<ComparisonChange, number> = { new: 0, remaining: 1, resolved: 2 };
/**
 * Which way each column sorts first, and the words for its order. Change
 * and WCAG are "text" for their first direction (new first, 1.1.1 first);
 * the Change header names its order itself.
 */
const SORT_KINDS: Record<SortColumn, SortKind> = {
  Change: "text",
  Issue: "text",
  WCAG: "text",
  Before: "number",
  After: "number",
  Difference: "number",
};
export const DEFAULT_SORT: SortState = { column: "Change", direction: "asc" };

export function parseSort(raw: string | null): SortState {
  const match = raw?.match(/^(\w+)_(asc|desc)$/);
  const column = COLUMNS.find((c) => c.toLowerCase() === match?.[1]);
  return column && match ? { column, direction: match[2] as SortDirection } : DEFAULT_SORT;
}

/** The default order has no ``?sort=``. */
export function serializeSort(sort: SortState): string {
  if (sort.column === DEFAULT_SORT.column && sort.direction === DEFAULT_SORT.direction) return "";
  return `${sort.column.toLowerCase()}_${sort.direction}`;
}

export const before = (row: ComparisonRow) => row.before?.issue_occurrences ?? 0;
export const after = (row: ComparisonRow) => row.after?.issue_occurrences ?? 0;
const difference = (row: ComparisonRow) => after(row) - before(row);

function wcagRank(row: ComparisonRow): number[] {
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

function compareBy(a: ComparisonRow, b: ComparisonRow, column: SortColumn): number {
  switch (column) {
    case "Change":
      return CHANGE_RANK[a.change] - CHANGE_RANK[b.change];
    case "Issue":
      return compareText(a.title, b.title);
    case "WCAG":
      return compareLists(wcagRank(a), wcagRank(b));
    case "Before":
      return before(a) - before(b);
    case "After":
      return after(a) - after(b);
    case "Difference":
      return difference(a) - difference(b);
  }
}

/**
 * Sorted by the chosen column, then by the size of the change (largest
 * first) and the title, so rows that tie on a column still land in a useful
 * and stable order.
 */
export function sortRows(rows: ComparisonRow[], sort: SortState): ComparisonRow[] {
  const sign = sort.direction === "asc" ? 1 : -1;
  return [...rows].sort(
    (a, b) =>
      compareBy(a, b, sort.column) * sign ||
      Math.abs(difference(b)) - Math.abs(difference(a)) ||
      compareText(a.title, b.title),
  );
}

/** The Change header's chip: its order is by kind of change, not A to Z. */
const changeChip = (sort: SortState): string => (sort.direction === "asc" ? "new first" : "new last");

function describeSort(sort: SortState): string {
  if (sort.column === "Change") {
    return sort.direction === "asc"
      ? "Sorted by change: new, then still found, then no longer found, largest change first in each"
      : "Sorted by change: no longer found, then still found, then new";
  }
  const name = headerText(sort.column);
  // "WCAG" stays in capitals mid-sentence.
  const spoken = name.startsWith("WCAG") ? name : name.toLowerCase();
  return `Sorted by ${spoken}, ${sortWords(SORT_KINDS[sort.column], sort.direction)}`;
}

/**
 * `?change=` as the checked changes: a comma-separated list kept to the known
 * changes, in their order ("resolved,new" → "new,resolved"); "" is every row.
 */
export function parseChanges(raw: string | null): string {
  const on = new Set(splitFilter(raw ?? ""));
  return CHANGES.filter((change) => on.has(change)).join(",");
}

function headerText(column: SortColumn, baselineId?: number, currentId?: number): string {
  if (column === "Before") return baselineId ? `Before (report #${baselineId})` : "Before";
  if (column === "After") return currentId ? `After (report #${currentId})` : "After";
  if (column === "Difference") return "Change in occurrences";
  if (column === "WCAG") return "WCAG criterion";
  return column;
}

/**
 * Every compared issue group, in the one table design: search and a Filter
 * menu (its Change group is the same `?change=` the stat cards above set)
 * with the pager beside them, a status line, and sortable columns, laid out
 * like the Issues table so the two read the same way.
 */
export default function ComparedIssuesTable({
  rows,
  counts,
  change,
  onChange,
  q,
  onQuery,
  onClearFilters,
  sort,
  onSort,
  baselineId,
  currentId,
  backTo,
  rowCaveats,
}: {
  /** Already filtered and sorted. */
  rows: ComparisonRow[];
  /** Flag each unsure new or resolved row; off when the page says it once for all of them. */
  rowCaveats: boolean;
  counts: Record<ComparisonChange, number> & { all: number };
  /** The checked changes, comma-separated (`parseChanges`); "" is all. */
  change: string;
  onChange: (next: string) => void;
  q: string;
  onQuery: (next: string) => void;
  /**
   * Clears the change and the search in one update. Calling `onChange` and
   * then `onQuery` would not: each rewrites the query string it was
   * rendered with, so the second write would put the first one back.
   */
  onClearFilters: () => void;
  sort: SortState;
  onSort: (next: SortState) => void;
  baselineId: number;
  currentId: number;
  backTo: string;
}) {
  const term = q.trim();
  // From what decides the rows rather than the rows themselves, so a new
  // filter, search or sort returns to page 1 without joining every row's key
  // on every render.
  const paged = usePagedRows(rows, {
    resetKey: `${change}\n${term.toLowerCase()}\n${sort.column}\n${sort.direction}`,
  });
  // One scale for every row, so bar lengths compare down the column. A loop,
  // not `Math.max(...rows)`: spreading a long list into arguments can
  // overflow the stack.
  const scale = useMemo(() => {
    let largest = 1;
    for (const row of rows) largest = Math.max(largest, before(row), after(row));
    return largest;
  }, [rows]);

  const groups: FilterGroup[] = [
    {
      key: "change",
      label: "Change",
      value: change,
      // Checkboxes: New and No longer found can be shown together; none is all.
      multiple: true,
      options: CHANGES.map((key) => ({ value: key, label: CHANGE_LABEL[key], count: counts[key] })),
    },
  ];
  const filtered = [...activeFilterItems(groups), ...(term ? [`Search: “${term}”`] : [])];
  const sortProps = { sort, onSort };

  return (
    <>
      <TableBar
        pager={<TablePagination label="Compared issues" noun="issues" {...paged} />}
        footer={<ActiveFilters items={filtered} onClear={onClearFilters} />}
      >
        <TableSearch label="Search issues" value={q} onChange={onQuery} />
        <FilterMenu
          groups={groups}
          onChange={(key, value) => {
            if (key === "change") onChange(parseChanges(value));
          }}
          onReset={() => onChange("")}
        />
      </TableBar>
      <TableStatus>
        {describeSort(sort)}. {rows.length} of {counts.all} issues shown.
      </TableStatus>
      {rows.length === 0 ? (
        <TableEmpty>
          {counts.all === 0
            ? "Neither scan found any issues."
            : "No issues match. Clear the filters to see them all."}
        </TableEmpty>
      ) : (
        <TableRegion label="Compared issues" paged={paged}>
          <Table caption={`Issues in report #${baselineId} and report #${currentId}. ${describeSort(sort)}.`}>
            <TableHead>
              <tr>
                {COLUMNS.map((column) => (
                  <SortHeader
                    key={column}
                    column={column}
                    kind={SORT_KINDS[column]}
                    chip={column === "Change" ? changeChip : undefined}
                    {...sortProps}
                  >
                    {headerText(column, baselineId, currentId)}
                  </SortHeader>
                ))}
              </tr>
            </TableHead>
            <tbody>
              {paged.pageRows.map((row, index) => (
                <ComparedRow
                  key={row.key}
                  row={row}
                  index={(paged.page - 1) * paged.pageSize + index}
                  scale={scale}
                  backTo={backTo}
                  caveat={rowCaveats}
                />
              ))}
            </tbody>
          </Table>
        </TableRegion>
      )}
    </>
  );
}

/**
 * A group that appeared or went away while the checks or pages differed
 * between the two scans may only look that way because of the coverage.
 */
export function unsureChange(row: ComparisonRow): boolean {
  return row.category === "cannot_compare" && row.change !== "remaining";
}

/**
 * One compared group. Memoized: a page turn, a sort or a search re-renders
 * only the rows whose props changed, not every row on the page.
 */
const ComparedRow = memo(function ComparedRow({
  row,
  index,
  scale,
  backTo,
  caveat,
}: {
  row: ComparisonRow;
  /** Position across pages, for the row stripe. */
  index: number;
  scale: number;
  backTo: string;
  caveat: boolean;
}) {
  // A resolved group exists only in the earlier report, so its evidence is there.
  const link = (row.after ?? row.before)?.issues[0];
  const scan = row.change === "resolved" ? "earlier" : "later";
  const diff = difference(row);
  const unsure = caveat && unsureChange(row);
  return (
    <Row index={index}>
      <Cell className="whitespace-nowrap">
        <ChangeTag change={row.change} />
      </Cell>
      <RowHeader className="min-w-[14rem] max-w-[28rem]">
        {link ? (
          <Link
            to={withReturnTrail(link.url.replace(/^\/app(?=\/)/, ""), "Compare reports", backTo)}
            className="inline-flex min-h-target items-center text-umich-blue underline underline-offset-2 hover:text-umich-blue-600"
          >
            {row.title}
            <span className="sr-only">, evidence in the {scan} scan</span>
          </Link>
        ) : (
          row.title
        )}
        {unsure && (
          <p className="mt-0.5 text-xs font-normal text-fg-muted">
            Checks differed between the scans. Confirm on the page.
          </p>
        )}
      </RowHeader>
      <Cell className="whitespace-nowrap">
        {row.wcag_sc ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="font-mono tabular-nums">{row.wcag_sc}</span>
            <ConformanceBadge level={row.conformance} />
            {row.wcag_name && <span className="sr-only">{row.wcag_name}</span>}
          </span>
        ) : (
          <span className="text-fg-muted">Best practice</span>
        )}
      </Cell>
      <Cell numeric className="font-mono text-fg-muted">
        {before(row).toLocaleString()}
      </Cell>
      <Cell numeric className="font-mono font-semibold">
        {after(row).toLocaleString()}
      </Cell>
      <Cell>
        <span className="flex min-w-[11rem] items-center gap-3">
          <span aria-hidden className="flex w-28 flex-col gap-1">
            <Bar value={before(row)} scale={scale} className="bg-border-strong" />
            <Bar value={after(row)} scale={scale} className={row.change === "new" ? "bg-sev-critical" : "bg-umich-blue"} />
          </span>
          <span
            className={cn(
              "ml-auto font-mono font-semibold tabular-nums",
              diff > 0 ? "text-sev-critical" : diff < 0 ? "text-fg" : "text-fg-muted",
            )}
          >
            {signed(diff)}
          </span>
        </span>
      </Cell>
    </Row>
  );
});

function Bar({ value, scale, className }: { value: number; scale: number; className: string }) {
  if (value <= 0) return <span className="h-1.5" />;
  return <span className={cn("block h-1.5 min-w-[2px] rounded-full", className)} style={{ width: `${(value / scale) * 100}%` }} />;
}
