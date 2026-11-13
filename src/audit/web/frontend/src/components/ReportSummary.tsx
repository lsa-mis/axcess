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
 *
 * ``link`` adds one link as the last ``dd``, after the lines, to the list
 * the number counts ("List the pages visited"). It is a text link, not a
 * button or a tile: the stat itself stays plain text and only the words
 * that go somewhere look like a link (W3C COGA: make controls look like
 * controls). Its target is 44px tall (SC 2.5.5 Target Size (Enhanced),
 * Level AAA; a link alone on its line is not inside a sentence, so the
 * inline exception does not cover it), and a negative margin as tall as
 * the extra height takes it back out of the layout, so the line keeps the
 * 4px spacing of the lines above it and the group stays one unit (see the
 * spacing rule in ReportSummary).
 */
function SummaryStat({
  label,
  value,
  details = [],
  link,
  className,
}: {
  label: string;
  value: number;
  details?: { text: string; flag?: boolean }[];
  link?: { to: string; text: string };
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
      {link && (
        <dd className="order-4 text-xs">
          <Link
            to={link.to}
            // The margin is half of (target height - line height), whatever
            // Settings > Target size makes the target.
            className="-my-[calc((var(--target,44px)_-_1.3125rem)/2)] inline-flex min-h-target items-center font-semibold text-umich-blue underline underline-offset-2"
          >
            {link.text}
          </Link>
        </dd>
      )}
    </div>
  );
}

/**
 * What the old Overview tab said about a completed report, above its table.
 *
 * The report opens on Issues now, so the numbers that used to take a page of
 * their own sit over the table instead, as one row of stat cards.
 *
 * The notes that explain the report ("What was checked", what the labels
 * mean) are not here: they sit under the table (see ReportCoverageNote).
 */
export function ReportSummary({
  scan,
  issueGroups,
  occurrences,
  hiddenIssueGroups = 0,
  hiddenOccurrences = 0,
}: {
  scan: ScanDetail;
  /** Issue types and occurrences the Issues table shows when it opens. */
  issueGroups: number;
  occurrences: number;
  /** What that default view holds back (Not sure, For information). */
  hiddenIssueGroups?: number;
  hiddenOccurrences?: number;
}) {
  return (
    <>
      {scan.blocked && <BlockedScanNotice scanId={scan.id} blocked={scan.blocked} />}
      {/* Three numbers: how many issue types (the rows of the table below),
          how many issue occurrences (every place a problem shows up), then
          how much of the site was scanned to find them. The developer set
          this order and these names on 2026-10-30 ("Issue types" first,
          "Issue occurrences" second), the same order as the Reports table's
          columns, so one report reads the same way on both screens (SC 3.2.4
          Consistent Identification, Level AA). The paragraphs below are the
          history before that. On the ITS export branch (2026-10-15) the
          places came first, because an evaluator reviews element by element
          and each occurrence becomes a row of the ITS technical review; the
          2026-10-30 order replaced it on every screen. The first version
          read left to right as the scan ran (pages, then occurrences, then
          issues), and a coworker testing it misread it in three ways:
          "errors" as accessibility errors, "Occurrences found" as the issue
          count, and "Issues found" as a part of that count. Leading with
          what the reader came for is the first rule of the U.S. Federal
          Plain Language Guidelines.

          The labels carry the difference between the two numbers, because a
          reader scanning the numbers reads the label and skips the rest:
          "Issue types" for the rows of the table below, "Issue occurrences"
          for every place a problem shows up. Each label is the same word as
          the table's row name ("Issue type") or its matching column ("Issue
          occurrences"), so one thing
          keeps one name (W3C COGA, "Making Content Usable",
          https://www.w3.org/TR/coga-usable/: the same word for the same
          thing; SC 3.2.4 Consistent Identification, Level AA).

          No line under these two. "Each one is an element on a page" and
          "One per row in the table below" were there, and user testing
          (2026-10-28) found them noise; the developer removed them. What
          each number counts is still said in words everyone can reach:
          "What the labels mean" under the table defines an issue type and an
          occurrence, and the Issue occurrences column's hint does too (SC 3.1.3
          Unusual Words, Level AAA). "Pages visited" keeps its lines: they
          are facts (page states reached, pages that failed), not
          definitions.

          On 2026-10-30 the developer renamed them again, everywhere: "issue
          type" for a row (it was "kind of issue") and "Issue occurrences" for
          the places, with issue types first. See docs/plain-language.md.

          History, short. Until 2026-10-26 the pair was "Kinds of issue
          found" (the rows, first) and "Places issues appear (occurrences)".
          On 2026-10-26 the developer renamed the places "issues" ("Issues
          found", first), because the coworker read each place as an issue
          and "occurrence" is an advanced word. On 2026-10-28 user testing
          with Siteimprove users, who know Siteimprove's pair of "issues" (a
          rule) and "occurrences" (each place), led the developer to bring
          back "occurrence" for the places, and keep "kind of issue" for a
          row, with the places count leading. The research and the reasons
          are in docs/plain-language.md, "Why "occurrence" and "issue type"".
          "Kinds of issues" was chosen over "Types of issues" then, because
          the "How sure" values were once called the three types of issue
          and "Issue Type" is a field in the Jira export. Neither holds the
          reader back now: the How sure values have not been called types
          since, and the Jira export's "Issue Type" is Jira's own field
          (always "Bug"), which a reader sees only inside Jira.

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

          "List the pages visited" is the last line under "Pages visited"
          (2026-11-06, backlog: readers could not tell a clean result from
          missing coverage, because the number did not say which pages it
          counted or which of them failed). It opens the list of every page
          (routes/PagesVisited.tsx), with the ones that could not be loaded
          first. A link under the number rather than the number itself as a
          link: a big link in a row of plain numbers would look like the one
          number that can be clicked, and it would be read as "46, link"
          with no verb (docs/plain-language.md rule 8: a verb and an object;
          SC 2.4.4 Link Purpose (In Context), Level A). It shows only when
          there is at least one page to list, by the same rule as the lines
          above it. Keyboard order is the reading order: the link comes
          after the facts it is about (SC 2.4.3 Focus Order, Level A).

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
          and 4px between the lines under "Pages visited", which read as one
          unit. Three
          across from 640px; below that the two problem numbers (Issue types
          and Issue occurrences) share a row, as the pair they are, and the
          pages take the row under them, so nothing is squeezed at 320px (SC
          1.4.10 Reflow, Level AA).

          The two problem numbers count what the table shows when it opens,
          so the number over the table is the number of rows under it (SC
          3.2.4 Consistent Identification, Level AA). Since 2026-11-13 the
          table opens on every issue type, so these are the whole report and
          nothing is hidden. (From 2026-11-10 it opened on Mostly sure and
          Measured only.) If the default view ever leaves rows out again, a
          line under each number ("Plus 12 hidden") says so, because a
          limitation is never dropped to make a number look smaller
          (Interface language rule 4); it shows only when something is
          hidden. The Reports list counts the same way (routes/Scans.tsx). */}
      <dl className="mt-10 mb-5 grid grid-cols-2 gap-x-8 gap-y-8 sm:grid-cols-3 lg:gap-x-12">
        <SummaryStat
          label={issueGroups === 1 ? "Issue type" : "Issue types"}
          value={issueGroups}
          details={hiddenIssueGroups > 0 ? [{ text: `Plus ${hiddenIssueGroups.toLocaleString()} hidden` }] : []}
        />
        <SummaryStat
          label={occurrences === 1 ? "Issue occurrence" : "Issue occurrences"}
          value={occurrences}
          details={hiddenOccurrences > 0 ? [{ text: `Plus ${hiddenOccurrences.toLocaleString()} hidden` }] : []}
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
          link={
            scan.page_count > 0
              ? { to: `/scans/${scan.id}/pages`, text: "List the pages visited" }
              : undefined
          }
        />
      </dl>
    </>
  );
}

/**
 * "What was checked", as a closed row of ``ReportNotes``, with how many
 * checks ran on the row itself. ``rows`` is the unfiltered issue list (the
 * per-check "Found" lines count it); undefined while it loads, which the
 * ledger already handles.
 *
 * Where it sits (Issues page): under the table, with what the labels mean,
 * since user testing (2026-10-28). Testers wanted the table to follow the
 * numbers with nothing to step over, and asked for both notes to move
 * down; the developer chose to move them all the way, count included.
 *
 * The tradeoff, told to the developer before building it: the notes were
 * above the table so that nobody read the numbers without the limit beside
 * them ("6 of 7 checks ran"). Keeping that count by the numbers was offered
 * and set aside. What still holds: the count stays visible on the closed
 * row, without opening anything; the empty table says that some checks may
 * not have run and points down to this row; and the order for a screen
 * reader is heading, numbers, table, notes, the same as on screen. Never
 * drop the count from the row to make it shorter (AGENTS.md, Interface
 * language rule 4).
 */
export function ReportCoverageNote({ scan, rows }: { scan: ScanDetail; rows: IssueRow[] | undefined }) {
  const ran = methodsRan(scan.methods_used).length;
  return (
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
