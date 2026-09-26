import { Link } from "react-router";
import { Check, Minus } from "lucide-react";
import { cn } from "../lib/cn";
import { Card } from "./ui";
import { Cell, ColumnHeader, Row, RowHeader, Table, TableHead, TableRegion } from "./table/Table";
import type {
  IssueRow,
  ScanMethodCoverage,
  ScanMethodState,
} from "../api/types";

/**
 * What was checked, as a table: one row per check, with what it ran on,
 * what it found, and what it can and cannot show, all in view.
 *
 * It used to be a list of closed rows, each opened to read that check's
 * description and caveat, so reading the whole ledger took a click per
 * check. The caveats are the point of it (what a clean result does not
 * prove), so they now sit in a column of their own. Row headers and column
 * headers let a screen reader name the check and the column for every cell.
 */
const METHOD_STATE_LABEL: Record<ScanMethodState, string> = {
  not_selected: "Not selected",
  waiting: "Waiting",
  running: "Checking",
  checked: "Ran",
  partial: "Partly ran",
  not_run: "Did not run",
  coverage_unknown: "Not recorded",
};

/**
 * Which detector's findings belong to which method, so a row can answer "and
 * what did it find?" rather than only "did it run?". ``rendered`` and
 * ``interaction`` are not detectors, they are how a page is reached, and
 * whatever they expose is then checked by axe and Alfa, so they are counted
 * differently below.
 */
const METHOD_PIPELINE: Partial<Record<ScanMethodCoverage["key"], IssueRow["pipeline"][]>> = {
  axe: ["axe"],
  alfa: ["alfa"],
  keyboard: ["keyboard"],
  responsive: ["responsive"],
  image: ["image", "protected_image"],
  semantic: ["semantic"],
};

/** The methods that actually ran, fully or in part. The report's one-line
 *  coverage summary and this ledger count the same set. */
export function methodsRan(methods: ScanMethodCoverage[]): ScanMethodCoverage[] {
  return methods.filter((method) => method.state === "checked" || method.state === "partial");
}

const CAPTION = "What each check ran on, what it found, and what it can and cannot show.";

export default function MethodCoverageLedger({
  scanId,
  methods,
  rows,
  embedded = false,
  className = "",
}: {
  scanId: number;
  methods: ScanMethodCoverage[];
  rows: IssueRow[] | undefined;
  /**
   * Inside a disclosure that already names the ledger and shows the count
   * (the report's notes accordion): drop the card and its heading, which
   * would only repeat the disclosure's own, and keep the table.
   */
  embedded?: boolean;
  className?: string;
}) {
  const table = <LedgerTable scanId={scanId} methods={methods} rows={rows} />;

  if (embedded) {
    return <div className={className}>{table}</div>;
  }

  const ran = methodsRan(methods);
  return (
    <Card className={cn("overflow-hidden", className)}>
      <div className="px-4 pb-3 pt-4">
        <h2 className="text-base font-semibold tracking-[-0.015em] text-fg">
          What was checked
        </h2>
        <p className="mt-1 text-sm text-fg-muted">
          {ran.length} of {methods.length} checks ran.
        </p>
      </div>
      {table}
    </Card>
  );
}

/**
 * The ledger itself. Its caption is visible, and is the table's name. At
 * narrow widths the table scrolls inside its own named region rather than
 * pushing the page sideways.
 */
function LedgerTable({
  scanId,
  methods,
  rows,
}: {
  scanId: number;
  methods: ScanMethodCoverage[];
  rows: IssueRow[] | undefined;
}) {
  // What ran leads, so the checks behind this report's evidence are the
  // first rows read; the rest keep the server's order after them.
  const ranKeys = new Set(methodsRan(methods).map((method) => method.key));
  const ordered = [
    ...methods.filter((method) => ranKeys.has(method.key)),
    ...methods.filter((method) => !ranKeys.has(method.key)),
  ];
  return (
    <TableRegion label="Checks in this scan">
      <Table
        caption={CAPTION}
        captionClassName="px-2 pb-2 text-left text-sm text-fg-muted"
        className="min-w-[40rem] rounded-xs border border-border"
      >
        <TableHead>
          <tr>
            <ColumnHeader>Check</ColumnHeader>
            <ColumnHeader>Status</ColumnHeader>
            <ColumnHeader>Result</ColumnHeader>
            <ColumnHeader>What it can and cannot show</ColumnHeader>
          </tr>
        </TableHead>
        <tbody>
          {ordered.map((method, index) => (
            <MethodRow key={method.key} index={index} scanId={scanId} method={method} rows={rows} />
          ))}
        </tbody>
      </Table>
    </TableRegion>
  );
}

function MethodRow({
  index,
  scanId,
  method,
  rows,
}: {
  index: number;
  scanId: number;
  method: ScanMethodCoverage;
  rows: IssueRow[] | undefined;
}) {
  const ran = method.state === "checked" || method.state === "partial";
  const found = findingsFor(method, rows);
  // Top-aligned: the last column holds a paragraph, and every other cell
  // should start on its first line rather than float in the middle of it.
  const top = "align-top";

  return (
    <Row index={index}>
      <RowHeader className={cn(top, "w-[12rem]")}>
        <span className={ran ? "text-fg" : "text-fg-muted"}>{method.label}</span>
      </RowHeader>
      <Cell className={cn(top, "whitespace-nowrap text-center")}>
        <StateChip state={method.state} />
      </Cell>
      {/* What it ran on, then what it found: one column, since a check
          that did not run has neither. */}
      <Cell className={cn(top, "w-[14rem] text-sm")}>
        {!ran ? (
          <span className="text-fg-muted">No result</span>
        ) : (
          <>
            <span className="block text-fg-muted">{method.result}</span>
            {found && (
              <span className="mt-1 block text-fg">
                {found.text}
                {found.count > 0 && (
                  <>
                    {" "}
                    <Link
                      to={`/scans/${scanId}/issues`}
                      className="font-semibold text-umich-blue underline underline-offset-2"
                    >
                      See them in the Issues table
                    </Link>
                  </>
                )}
              </span>
            )}
          </>
        )}
      </Cell>
      <Cell className={cn(top, "min-w-[18rem]")}>
        <p className="max-w-[70ch] text-sm leading-relaxed text-fg-muted">{method.description}</p>
        <p className="mt-1.5 max-w-[70ch] text-xs leading-relaxed text-fg-muted">
          <span className="font-semibold text-fg">Limits: </span>
          {method.caveat}
        </p>
      </Cell>
    </Row>
  );
}

/**
 * What one method found, under its result in the Result column.
 *
 * Detector methods answer with their own issues. ``interaction`` is the
 * exception worth spelling out: Click-Through does not detect
 * anything itself, it just reaches markup that would otherwise be invisible to
 * the scan, so what it "found" is the evidence that only exists after a
 * control was used. Saying "none" there is a real result, not a gap, it means
 * nothing in this report is hiding behind a menu.
 */
function findingsFor(
  method: ScanMethodCoverage,
  rows: IssueRow[] | undefined,
): { text: string; count: number } | null {
  if (!rows || (method.state !== "checked" && method.state !== "partial")) return null;

  if (method.key === "interaction") {
    const revealed = rows.filter((row) =>
      row.locations.some((location) => location.revealed_by),
    );
    return revealed.length === 0
      ? {
          text: "Found: no occurrence in this report appears only after a click.",
          count: 0,
        }
      : {
          text: `Found: ${revealed.length} issue${revealed.length === 1 ? "" : "s"} with at least one occurrence that appears only after you use a control, such as a menu.`,
          count: revealed.length,
        };
  }

  const pipelines = METHOD_PIPELINE[method.key];
  if (!pipelines) return null;
  const count = rows.filter((row) => pipelines.includes(row.pipeline)).length;
  return count === 0
    ? { text: "Found: no issues.", count: 0 }
    : {
        text: `Found: ${count} issue${count === 1 ? "" : "s"}.`,
        count,
      };
}

/**
 * A check's state in words, with an icon as a second signal: a check mark
 * on green for a check that ran, a dash for one that did not. Colour is the
 * third signal, never the only one.
 */
function StateChip({ state }: { state: ScanMethodState }) {
  const ran = state === "checked" || state === "partial";
  const Icon = ran ? Check : Minus;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-2xs font-semibold",
        ran
          ? "border-ok/30 bg-ok-bg text-ok"
          : state === "running"
            ? "border-umich-maize/60 bg-umich-maize/15 text-fg"
            : state === "not_run"
              ? "border-sev-major/30 bg-sev-major-bg text-sev-major"
              : "border-border bg-surface text-fg-muted",
      )}
    >
      <Icon className="h-3 w-3 shrink-0" strokeWidth={3} aria-hidden />
      {METHOD_STATE_LABEL[state]}
    </span>
  );
}
