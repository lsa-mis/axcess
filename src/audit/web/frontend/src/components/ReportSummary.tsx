import type { ReactNode } from "react";
import { Link } from "react-router";
import { AlertOctagon } from "lucide-react";
import type { IssueRow, ScanDetail } from "../api/types";
import MethodCoverageLedger, { methodsRan } from "./MethodCoverageLedger";
import { Card, Disclosure } from "./ui";
import { cn } from "../lib/cn";
import { CLICK_THROUGH_STATES, clickThroughStates } from "../lib/labels";

/**
 * One number in the summary strip: the value large, what it counts under it,
 * and one or two short lines of explanation. The label is the ``dt`` and the
 * value and each line its ``dd``s, so a screen reader reads "Pages visited,
 * 46, Plus 120 page states opened by clicking"; CSS order puts the number
 * first on screen. A line with ``flag`` set is coloured
 * because it needs attention (pages that could not be loaded); its words say
 * so too, so the colour is never the only signal (SC 1.4.1 Use of Color,
 * Level A).
 */
function SummaryStat({
  label,
  value,
  details,
  className,
}: {
  label: string;
  value: number;
  details: { text: string; flag?: boolean }[];
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <dt className="order-2 text-sm font-semibold text-fg">{label}</dt>
      <dd className="order-1 mb-1 text-3xl font-semibold leading-none tabular-nums text-umich-blue">
        {value.toLocaleString()}
      </dd>
      {details.map(({ text, flag = false }) => (
        <dd key={text} className={cn("order-3 text-xs", flag ? "text-sev-major" : "text-fg-muted")}>
          {text}
        </dd>
      ))}
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
      {/* Three numbers, main point first: how many issues (every place a
          problem shows up), how many kinds of issue they fall into, then how
          much of the site was scanned to find them. The first version read
          left to right as the scan ran (pages, then occurrences, then
          issues), and a coworker testing it misread it in three ways:
          "errors" as accessibility errors, "Occurrences found" as the issue
          count, and "Issues found" as a part of that count. Leading with
          what the reader came for is the first rule of the U.S. Federal
          Plain Language Guidelines.

          The labels carry the difference between the two numbers, not the
          lines under them, because a reader scanning the numbers reads the
          label and skips the rest: "Issues found" for every place a problem
          shows up, "Kinds of issue" for the rows of the table below. Each
          label is the same word as the table's matching column ("Issues")
          or its row name ("Kind of issue"), so one thing keeps one name
          (W3C COGA, "Making Content Usable",
          https://www.w3.org/TR/coga-usable/: the same word for the same
          thing; SC 3.2.4 Consistent Identification, Level AA).

          Until 2026-10-26 the pair was "Kinds of issue found" (the rows,
          shown first) and "Places issues appear (occurrences)" (the
          places). The coworker had asked to call the places "Issues
          found", and the developer had suggested "Issues appear"; both
          were rejected then, because the old terms made an issue one row.
          The coworker's misreadings showed that people call each place an
          issue, as most accessibility tools do, and "occurrence" is an
          advanced word. On 2026-10-26 the developer reversed the earlier
          choice: an issue is now one place, a kind of issue is one row,
          and the places count leads, as the number people already called
          "issues". The research is in docs/plain-language.md, "Why "issue"
          and "kind of issue"". "Kinds of issue", not "Types of issues": the
          "How sure" values were once called the three types of issue, and
          "issue type" is a field in the Jira export.

          The page states opened by clicking are a line under the pages, not a
          fourth number: they say how much was scanned, like the pages, not
          what was found, and a big number of their own read as a result. The
          line stays, because pages alone understate a site whose content
          mostly appears only after a control is used, and a limitation is
          never dropped to save space (Interface language rule 4).

          A line shows only when it tells the reader something: "3 pages
          could not be loaded" when pages failed, and nothing when none did.
          The developer's rule: hide what the reader does not need. An
          "Every page loaded" line was dropped for that reason. The page
          states line stays even at zero ("No page states opened by
          clicking"), because zero is a limitation the reader does need.

          "Pages visited", not "Pages checked": the count is every page the
          scan recorded, including pages that could not be loaded or answered
          with an error (docs/reading-your-report.md), so "checked" claimed
          more than the scan did. The failures are said in words, "3 pages
          could not be loaded", not "3 errors while scanning", which the
          coworker read as accessibility errors (glossary: "Pages not
          reached").

          No panel, border, fill or dividers, the same rule as StatCard
          (ui.tsx): a frame around a number competes with the number, and a
          tinted, rounded tile, suggested again with the reorder, looks like a
          card that can be clicked when these cannot (W3C COGA: make controls
          look like controls, and what is not a control not look like one).
          The cells were once a white panel cut by 1px dividers, which made a
          second card above the issues table. The space between the cells does
          the grouping instead. Every colour here is at least 7:1 on the page
          background, in light and dark and every colour-vision setting (WCAG
          2.2 SC 1.4.6 Contrast (Enhanced), Level AAA); a fill would have to
          be checked again for all of them.

          Without a panel, space alone has to say what belongs together
          (proximity), so the space outside the group is clearly larger than
          the space inside it: 32px above (with the header's margin) and
          below it, 48px between columns on a wide screen (32px on a narrow
          one) and 32px between rows, against 8px from a number to its name
          and 4px between the lines under it, which read as one unit. Three
          across from 640px; below that the two issue numbers (Issues found
          and Kinds of issue) share a row, as the pair they are, and the
          pages take the row under them, so nothing is squeezed at 320px (SC
          1.4.10 Reflow, Level AA). */}
      <dl className="mt-10 mb-5 grid grid-cols-2 gap-x-8 gap-y-8 sm:grid-cols-3 lg:gap-x-12">
        <SummaryStat
          label={occurrences === 1 ? "Issue found" : "Issues found"}
          value={occurrences}
          details={[{ text: "Each one is an element on a page" }]}
        />
        <SummaryStat
          label={issueGroups === 1 ? "Kind of issue" : "Kinds of issue"}
          value={issueGroups}
          details={[{ text: "One per row in the table below" }]}
        />
        <SummaryStat
          label="Pages visited"
          value={scan.page_count}
          className="col-span-2 sm:col-span-1"
          details={[
            {
              text:
                (scan.dom_state_count ?? 0) > 0
                  ? `Plus ${clickThroughStates(scan.dom_state_count)}`
                  : `No ${CLICK_THROUGH_STATES}`,
            },
            ...(scan.error_count > 0
              ? [
                  {
                    text: `${scan.error_count.toLocaleString()} ${
                      scan.error_count === 1 ? "page" : "pages"
                    } could not be loaded`,
                    flag: true,
                  },
                ]
              : []),
          ]}
        />
      </dl>

      {/* What was checked leads the notes: whether the scan checked
          something comes before what its labels mean. The count stays on
          the closed row, so the fact is on screen without opening anything.

          The notes come after the numbers, not before them. Putting them
          first was considered and rejected: the numbers are what the report
          found, and leading with the main point is the first rule of the
          U.S. Federal Plain Language Guidelines; two closed rows above them
          would start every visit with things to open. Each note sits by
          what it explains instead: "What was checked" (how many checks ran)
          qualifies the numbers just above it, and what the labels mean
          explains the table just below it. The count of checks that ran
          stays visible on the closed row, so nobody reads the numbers
          without the limitation beside them. Reading order for a screen
          reader is the same: heading, numbers, notes, table. */}
      <ReportNotes className="mt-8">
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
  return <Card className={cn("mb-6 divide-y divide-border", className)}>{children}</Card>;
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
    // Square between rows; the first and last round their outer corners to
    // the card's (8px less its 1px border), so their fill does not paint
    // square corners over it.
    <Disclosure
      id={id}
      title={title}
      meta={meta}
      headingLevel={2}
      className="rounded-none border-0 first:rounded-t-[7px] last:rounded-b-[7px]"
    >
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
          not get past the start page, so report {scanId} is incomplete. Try
          again on a different network: <Link to="/scans/new">start a new scan</Link>.
          If the site needs you to sign in, and you have permission, use a
          sign-in scan.
        </div>
      </div>
    </Card>
  );
}
