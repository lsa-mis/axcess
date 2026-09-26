import type { ReactNode } from "react";
import { Link } from "react-router";
import { AlertOctagon } from "lucide-react";
import type { IssueRow, ScanDetail } from "../api/types";
import MethodCoverageLedger, { methodsRan } from "./MethodCoverageLedger";
import { Card, Disclosure } from "./ui";
import { cn } from "../lib/cn";
import { CLICK_THROUGH_STATES_LABEL } from "../lib/labels";

/**
 * One number in the summary line: the value first, then what it counts.
 * The label is the ``dt`` and the value the ``dd``, so a screen reader reads
 * "Pages checked, 8"; CSS order puts the number first on screen. ``detail``
 * is a short aside in parentheses, and ``flag`` colors the number when it
 * needs attention (crawl errors), which the detail text also says.
 */
function SummaryStat({
  label,
  value,
  detail,
  flag = false,
}: {
  label: string;
  value: number;
  detail?: string;
  flag?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="order-2 text-fg-muted">
        {label}
        {detail && <span className="text-xs"> ({detail})</span>}
      </dt>
      <dd className={cn("order-1 text-xl font-semibold tabular-nums", flag ? "text-sev-major" : "text-umich-blue")}>
        {value.toLocaleString()}
      </dd>
    </div>
  );
}

/**
 * What the old Overview tab said about a completed report, above its table.
 *
 * The report opens on Issues now, so the numbers and the coverage disclosure
 * that used to take a page of their own sit over the table instead: one row
 * of stat cards, then an accordion whose first row says how many checks ran.
 * The full ledger is behind that row, because what a scan did and did not check is something a
 * reader goes to on purpose, not something every visit should scroll past.
 *
 * ``rows`` is the unfiltered issue list (the per-method "Found" lines count
 * it); undefined while it loads, which the ledger already handles.
 *
 * ``notes`` are the page's other closed explanations (what the table's
 * labels mean), as ``ReportNote`` rows. They join the
 * coverage row in one accordion, so the report's context reads as one short
 * list of things to open rather than loose sentences between the numbers
 * and the table.
 */
export function ReportSummary({
  scan,
  issueGroups,
  occurrences,
  rows,
  notes,
}: {
  scan: ScanDetail;
  issueGroups: number;
  occurrences: number;
  rows: IssueRow[] | undefined;
  notes?: ReactNode;
}) {
  const ran = methodsRan(scan.methods_used).length;
  return (
    <>
      {scan.blocked && <BlockedScanNotice scanId={scan.id} blocked={scan.blocked} />}
      {/* Read left to right as the scan itself ran: how much was tested,
          what that turned up, how those findings group, and how much of
          the site only existed after a control was used. One compact line
          rather than four cards, so the table starts higher on the screen.
          Each term keeps its short explanation in parentheses. */}
      <dl className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-sm">
        <SummaryStat
          label="Pages checked"
          value={scan.page_count}
          detail={`${scan.error_count.toLocaleString()} error${scan.error_count === 1 ? "" : "s"} while scanning`}
          flag={scan.error_count > 0}
        />
        <SummaryStat label="Occurrences found" value={occurrences} detail="each place an issue appears" />
        <SummaryStat label="Issues found" value={issueGroups} detail="kinds of problem, one per row below" />
        {/* Pages alone understate an application whose content mostly does
            not exist until a control is used. */}
        <SummaryStat
          label={CLICK_THROUGH_STATES_LABEL}
          value={scan.dom_state_count ?? 0}
          detail="reached by using controls, such as menus"
        />
      </dl>

      {/* What was checked leads the notes: whether the scan checked
          something comes before what its labels mean. The count stays on
          the closed row, so the fact is on screen without opening anything. */}
      <ReportNotes className="mt-6">
        <ReportNote
          id="report-coverage"
          title="What was checked"
          meta={
            <span className="tabular-nums">
              {ran} of {scan.methods_used.length} checks ran
            </span>
          }
        >
          <MethodCoverageLedger scanId={scan.id} methods={scan.methods_used} rows={rows} embedded />
        </ReportNote>
        {notes}
      </ReportNotes>
    </>
  );
}

/**
 * The report's closed explanations under the header, as one accordion: a
 * framed list of ``ReportNote`` rows, one per line, all closed on arrival.
 *
 * These used to be link-styled ``<details>`` summaries wrapped side by side,
 * which read as loose sentences and put the table's context in a different
 * shape from the issue page's own disclosures. Stacked rows each say what
 * they open, keep their one key fact visible on the right, and leave the
 * space around the table to the table. A new explanation for a future view
 * is one more row here, not one more line on the page.
 */
export function ReportNotes({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "mb-6 divide-y divide-border rounded-xs border border-border bg-surface shadow-card",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * One row of ``ReportNotes``: the issue page's ``Disclosure`` without its own
 * frame, so the rows share the group's border and read as one list.
 */
export function ReportNote({
  id,
  title,
  meta,
  children,
}: {
  id: string;
  title: string;
  /** The row's one fact, shown on the right while it is closed. */
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Disclosure id={id} title={title} meta={meta} headingLevel={2} className="rounded-none border-0">
      {children}
    </Disclosure>
  );
}

export function BlockedScanNotice({
  scanId,
  blocked,
}: {
  scanId: number;
  blocked: NonNullable<ScanDetail["blocked"]>;
}) {
  return (
    <Card className="mb-4 border-sev-critical/40 bg-sev-critical-bg p-4">
      <div className="flex items-start gap-3">
        <AlertOctagon
          className="mt-0.5 h-5 w-5 text-sev-critical"
          aria-hidden
        />
        <div className="text-sm">
          <strong className="text-sev-critical">
            The website returned an error (HTTP {blocked.status_code})
          </strong>
          {blocked.title && <>, &ldquo;{blocked.title}&rdquo;</>}. Axcess could
          not get past the start page, so report {scanId} is incomplete.{" "}
          <Link to="/scans/new">Start a new scan</Link>. If the site needs you
          to sign in, and you have permission, use a sign-in scan.
        </div>
      </div>
    </Card>
  );
}
