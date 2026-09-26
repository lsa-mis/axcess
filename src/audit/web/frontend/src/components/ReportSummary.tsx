import type { ReactNode } from "react";
import { Link } from "react-router";
import { AlertOctagon } from "lucide-react";
import type { IssueRow, ScanDetail } from "../api/types";
import MethodCoverageLedger, { methodsRan } from "./MethodCoverageLedger";
import { Card, Disclosure, StatCard } from "./ui";
import { cn } from "../lib/cn";
import { CLICK_THROUGH_STATES_LABEL } from "../lib/labels";

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
 * labels mean, what an ACT rule is), as ``ReportNote`` rows. They join the
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
          the site only existed after a control was used. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Pages Tested"
          value={scan.page_count.toLocaleString()}
          hint={`${scan.error_count.toLocaleString()} crawl errors`}
          tone={scan.error_count ? "major" : "default"}
        />
        <StatCard label="Issues Found" value={occurrences.toLocaleString()} />
        <StatCard label="Issue Groups" value={issueGroups.toLocaleString()} />
        {/* Pages alone understate an application whose content mostly does
            not exist until a control is used. */}
        <StatCard
          label={CLICK_THROUGH_STATES_LABEL}
          value={(scan.dom_state_count ?? 0).toLocaleString()}
          hint="Menus, tabs and dialogs the scan opened"
        />
      </div>

      {/* Coverage leads the notes: whether the scan checked something comes
          before what its labels mean. The count stays on the closed row, so
          the fact is on screen without opening anything. */}
      <ReportNotes className="mt-6">
        <ReportNote
          id="report-coverage"
          title="What this scan checked"
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
            Site URL returned HTTP {blocked.status_code}
          </strong>
          {blocked.title && <>, &ldquo;{blocked.title}&rdquo;</>}. The crawler
          could not read past the entry page. Try a{" "}
          <Link to="/scans/new">new scan</Link>, or use an authorized
          sign-in scan when the site requires authentication.
          <span className="sr-only"> Report {scanId} is incomplete.</span>
        </div>
      </div>
    </Card>
  );
}
