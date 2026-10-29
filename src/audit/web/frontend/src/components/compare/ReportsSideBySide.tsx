import type { ReactNode } from "react";
import type { ComparisonReport } from "../../api/types";
import { Card } from "../ui";
import { cn } from "../../lib/cn";
import { Cell, ColumnHeader, Row, RowHeader, Table, TableHead, TableRegion } from "../table/Table";
import { dateText, laterText, signed } from "./format";

/** A change in a count, in text: "+4", "−4" (a true minus), or "No change". */
export function changeText(before: number, after: number): string {
  const diff = after - before;
  return diff === 0 ? "No change" : signed(diff);
}

/**
 * The two whole reports side by side: when each was scanned, its pages,
 * occurrences and kinds of issues, and the change. Before the New / Still
 * found / No longer found cards, so the reader sees the totals first and
 * then what makes them up.
 *
 * Why a table, not the two reports in two panes (research 2026-10-28,
 * asked for by testers who photographed two reports to compare them):
 *
 * - One table with Before and After columns ties each number to its pair
 *   in code, through the column and row headers (`th scope`, techniques
 *   H63 and H39 for the caption; SC 1.3.1 Info and Relationships, Level
 *   A). A screen reader reads two panes one after the other, with nothing
 *   linking a number in one to the same number in the other.
 * - Two panes cannot stay side by side at 320 pixels (SC 1.4.10 Reflow,
 *   Level AA). This table is four short columns with tighter padding on a
 *   narrow screen (`TIGHT`), so it fits at 320 pixels; if it ever does not,
 *   its region scrolls sideways, which Reflow allows for data tables.
 * - Options as columns and attributes as rows is the usual comparison
 *   table layout (NN/g, "Comparison Tables",
 *   https://www.nngroup.com/articles/comparison-tables/, paraphrased).
 * - The caption shows: it names the two reports, so a screenshot of the
 *   table says what it compares.
 * - Change is in text only: a sign and a number ("+4", "−4"), as the
 *   "Change in occurrences" column of the table below writes it, or "No
 *   change" for none, never a bare 0. No colour marks up or down, so
 *   nothing depends on seeing it (SC 1.4.1 Use of Color, Level A), and a
 *   rise in pages is not painted as good or bad when it is neither.
 * - The Scanned row gives dates, not "27 days ago", and its Change is the
 *   time between the two scans.
 * - Occurrences and Kinds of issues are the comparison's own totals
 *   (`before_totals`, `after_totals`), counted as the Issues table counts
 *   them, so they match each report's Issues page and the trend. Pages is
 *   each scan's stored page total. The words and order are the Reports
 *   list's and the Issues page summary's (SC 3.2.4 Consistent
 *   Identification, Level AA). A line under the table says what an
 *   occurrence is (docs/plain-language.md, Terms).
 */
/**
 * Half the usual cell padding below the `sm` breakpoint, so the four columns
 * fit at 320 pixels without the table scrolling sideways or cutting off its
 * caption (SC 1.4.10 Reflow, Level AA). The usual padding from `sm` up.
 */
const TIGHT = "px-2 sm:px-4";

export default function ReportsSideBySide({ data }: { data: ComparisonReport }) {
  const before = data.baseline!;
  const after = data.current;
  const beforeTotals = data.before_totals ?? { groups: 0, occurrences: 0 };
  const afterTotals = data.after_totals;
  const caption = `Report #${before.id} and report #${after.id} side by side`;
  const rows: Array<{ name: string; before: ReactNode; after: ReactNode; change: string; numeric: boolean }> = [
    {
      name: "Scanned",
      before: <time dateTime={before.started_at}>{dateText(before.started_at, true)}</time>,
      after: <time dateTime={after.started_at}>{dateText(after.started_at, true)}</time>,
      change: laterText(before.started_at, after.started_at),
      numeric: false,
    },
    {
      name: "Pages",
      before: before.page_count.toLocaleString(),
      after: after.page_count.toLocaleString(),
      change: changeText(before.page_count, after.page_count),
      numeric: true,
    },
    {
      name: "Occurrences",
      before: beforeTotals.occurrences.toLocaleString(),
      after: afterTotals.occurrences.toLocaleString(),
      change: changeText(beforeTotals.occurrences, afterTotals.occurrences),
      numeric: true,
    },
    {
      name: "Kinds of issues",
      before: beforeTotals.groups.toLocaleString(),
      after: afterTotals.groups.toLocaleString(),
      change: changeText(beforeTotals.groups, afterTotals.groups),
      numeric: true,
    },
  ];
  return (
    <Card className="mb-4">
      <TableRegion label={caption}>
        <Table
          caption={caption}
          captionClassName="px-4 pb-2 pt-3 text-left text-base font-semibold text-fg"
          ruled
        >
          <TableHead>
            <tr>
              <ColumnHeader className={TIGHT}><span className="sr-only">Detail</span></ColumnHeader>
              <ColumnHeader className={TIGHT}>Before (report #{before.id})</ColumnHeader>
              <ColumnHeader className={TIGHT}>After (report #{after.id})</ColumnHeader>
              <ColumnHeader className={TIGHT}>Change</ColumnHeader>
            </tr>
          </TableHead>
          <tbody>
            {rows.map((row, index) => (
              <Row key={row.name} index={index}>
                <RowHeader className={TIGHT}>{row.name}</RowHeader>
                {[row.before, row.after, row.change].map((value, column) => (
                  // A change in words ("No change") may wrap; numbers do not.
                  <Cell key={column} numeric={row.numeric} className={cn(TIGHT, "text-center", column === 2 && "whitespace-normal")}>
                    {value}
                  </Cell>
                ))}
              </Row>
            ))}
          </tbody>
        </Table>
      </TableRegion>
      <p className="border-t border-border px-4 py-2 text-xs text-fg-muted">
        An occurrence is one place a problem appears: one element on one page, or in one page state.
      </p>
    </Card>
  );
}
