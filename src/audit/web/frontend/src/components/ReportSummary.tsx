import type { ReactNode } from "react";
import { Link } from "react-router";
import { AlertOctagon } from "lucide-react";
import type { IssueRow, ScanDetail } from "../api/types";
import MethodCoverageLedger, { methodsRan } from "./MethodCoverageLedger";
import { Card, Disclosure } from "./ui";
import { cn } from "../lib/cn";
import { CLICK_THROUGH_STATES_LABEL } from "../lib/labels";
import { SCAN_END_LABEL } from "../lib/terms";
import { NUMBERS } from "./newScan/copy";

const pages = (n: number) => `${n.toLocaleString()} ${n === 1 ? "page" : "pages"}`;

/**
 * How the scan ended, with the page limit's number when it stopped there:
 * "Stopped at its page limit of 10 pages". The number is what makes the
 * line useful; without it the reader has to look the setting up.
 */
function endText(coverage: ScanDetail["coverage"]): string {
  const words = SCAN_END_LABEL[coverage.ended];
  return coverage.ended === "page_limit" && coverage.page_limit != null
    ? `${words} of ${pages(coverage.page_limit)}`
    : words;
}

/**
 * One number in the summary strip: the value large and what it counts under
 * it. The label is the ``dt`` and the value its ``dd``, so a screen reader
 * reads "Pages visited, 7 of 60 found"; CSS order puts the number first on
 * screen.
 *
 * ``outOf`` says what the number is out of, smaller and beside it in the same
 * ``dd`` ("7 of 60 found"), so the two numbers read as one fact and nobody
 * adds them. The same "X of Y" shape as "6 of 7 checks ran" in "What was
 * checked" and "7 of 60 pages found so far" while a scan runs (SC 3.2.4
 * Consistent Identification, Level AA; W3C COGA, "Making Content Usable":
 * the same pattern for the same kind of thing).
 *
 * Exported for the other report views' numbers (Images, Documents), so a
 * report's numbers look the same on every tab (SC 3.2.4 Consistent
 * Identification, Level AA). Put it in a ``dl`` (``SummaryNumbers``).
 *
 * ``note`` finishes a label that is not a whole idea alone, on a smaller
 * line under it, inside the same ``dt``: "Mostly sure" / "it has
 * accessibility problems". On the Documents tab the bare value left the
 * reader asking "mostly sure of what?" (the developer's report,
 * 2026-11-14). In the ``dt``, so a screen reader hears it as part of the
 * name, before the number. Rejected: a longer label, which put the value's
 * own words (the ones the table's tags show) out of view; and one heading
 * over the three counts, which the grid would place over "Documents" too.
 * Not for facts about the number (those are ``outOf``).
 *
 * ``labelBeside`` puts the label on the number's line, after ``outOf``, so
 * the three read as one phrase: "47 of 47 Pages visited" (the developer's
 * layout, 2026-11-27). ``after`` is a second ``dd`` under that line, for a
 * link or warning that belongs to the number ("List the pages visited"); it
 * sits where the other numbers' labels sit, so the row's lines still align.
 * A ``dd``, not a loose element, because a ``dl``'s group may hold only
 * ``dt`` and ``dd`` (HTML, the dl element's content model).
 */
export function SummaryStat({
  label,
  value,
  outOf,
  note,
  help,
  labelBeside = false,
  after,
  className,
}: {
  label: string;
  value: number;
  outOf?: string;
  /** The rest of the label's sentence, on its own line under it. */
  note?: string;
  /** A ``HelpTip`` after the label, for a counting term that needs explaining. */
  help?: ReactNode;
  /** The label after the number on its line, not under it. */
  labelBeside?: boolean;
  /** What belongs to the number, under it (a link to its list). */
  after?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex",
        labelBeside ? "flex-wrap items-baseline gap-x-2 gap-y-1" : "flex-col gap-1",
        className,
      )}
    >
      <dt className="order-2 text-sm font-semibold text-fg">
        {/* The label and its "?" on one line; a note, when there is one,
            on its own line under them. */}
        <span className="flex items-center gap-0.5">
          {label}
          {help}
        </span>
        {note && <span className="block font-normal text-fg-muted">{note}</span>}
      </dt>
      <dd className="order-1 mb-1 text-3xl font-semibold leading-none tabular-nums text-umich-blue">
        {value.toLocaleString()}
        {outOf && <span className="text-base font-semibold leading-none text-fg-muted"> {outOf}</span>}
      </dd>
      {after && <dd className="order-3 basis-full text-sm">{after}</dd>}
    </div>
  );
}

/**
 * What sits under "Pages visited": the pages that could not be loaded, when
 * any failed, then the link to the list of pages.
 *
 * Until 2026-11-27 a line of facts ran under all three numbers: how the scan
 * ended, its page limit, the page states it opened, the failed pages, then
 * this link. The developer removed that line (2026-11-27) and moved the link
 * under the number it lists. The facts it held are not dropped (Interface
 * language rule 4): how the scan ended, the page limit, the page states and
 * the failed pages are in "How this scan ran" in "About this report", and
 * how it ended is on that group's closed row.
 *
 * "3 pages could not be loaded" stays here, in view, because it needs
 * attention and the reader should not have to open anything to learn that
 * the count above includes failures. It is coloured and says so in words too
 * (SC 1.4.1 Use of Color, Level A). It shows only when pages failed.
 *
 * The link follows the fact it is about, in reading and keyboard order (SC
 * 2.4.3 Focus Order, Level A). It is a text link with a 44px target (SC
 * 2.5.5 Target Size (Enhanced), Level AAA); a negative margin as tall as the
 * extra height keeps it on the same line as the other numbers' labels.
 */
function PagesVisitedAfter({ scan }: { scan: ScanDetail }) {
  return (
    <>
      {scan.error_count > 0 && (
        <span className="block text-sev-major">{pages(scan.error_count)} could not be loaded</span>
      )}
      {scan.page_count > 0 && (
        <Link
          to={`/scans/${scan.id}/pages`}
          // The margin is half of (target height - line height), whatever
          // Settings > Target size makes the target.
          className="-my-[calc((var(--target,44px)_-_1.25rem)/2)] inline-flex min-h-target items-center font-semibold text-umich-blue underline underline-offset-2"
        >
          List the pages visited
        </Link>
      )}
    </>
  );
}

/**
 * What the old Overview tab said about a report, above its table. Every
 * report gets it, however its scan ended: a stopped scan used to have none.
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
}: {
  scan: ScanDetail;
  /** Issue types and occurrences the Issues table shows when it opens. */
  issueGroups: number;
  occurrences: number;
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
          Unusual Words, Level AAA). How the scan ran is said in facts
          (page states reached, pages that failed, how it ended) in "How
          this scan ran", not definitions.

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

          The page states opened by clicking are a fact in "How this scan
          ran", not a fourth number: they say how much was scanned, like the
          pages, not what was found, and a big number of their own read as a
          result. The fact stays, even at zero, because pages alone
          understate a site whose content mostly appears only after a
          control is used, and a limitation is never dropped to save space
          (Interface language rule 4). Until 2026-11-27 it was on a line of
          facts under these numbers, which the developer removed.

          "3 pages could not be loaded" shows under "Pages visited" when
          pages failed, and nothing when none did. The developer's rule:
          hide what the reader does not need. An "Every page loaded" line was
          dropped for that reason.

          "Pages visited" says what it is out of: "7 of 60" (2026-11-14; the
          word "found" went when the label moved beside it, 2026-11-27).
          A stopped scan used to be a "Partial report" while one that
          completed at a 10-page limit read as whole; the developer asked for
          coverage as facts instead. The found count is left out when it was
          not recorded (a scan stopped before migration 0040).

          "Pages visited", not "Pages checked": the count is every page the
          scan recorded, including pages that could not be loaded or answered
          with an error (docs/reading-your-report.md), so "checked" claimed
          more than the scan did. The failures are said in words, "3 pages
          could not be loaded", not "3 errors while scanning", which the
          coworker read as accessibility errors (glossary: "Pages not
          reached").

          "List the pages visited" is under "Pages visited" (since
          2026-11-27; first added 2026-11-06, backlog: readers could not tell a clean result from
          missing coverage, because the number did not say which pages it
          counted or which of them failed). It opens the list of every page
          (routes/PagesVisited.tsx), with the ones that could not be loaded
          first. A link under the number rather than the number itself as a
          link: a big link in a row of plain numbers would look like the one
          number that can be clicked, and it would be read as "46, link"
          with no verb (docs/plain-language.md rule 8: a verb and an object;
          SC 2.4.4 Link Purpose (In Context), Level A). It shows only when
          there is at least one page to list. Keyboard order is the reading
          order: the link comes after the number it is about (SC 2.4.3 Focus
          Order, Level A).

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
          one) and 32px between rows, against 8px from a number to its name.
          Three
          across from 640px; below that the two problem numbers (Issue types
          and Issue occurrences) share a row, as the pair they are, and the
          pages take the row under them, so nothing is squeezed at 320px (SC
          1.4.10 Reflow, Level AA).

          The two problem numbers count what the Issues table shows when it
          opens, so the number over the table is the number of rows under it
          (SC 3.2.4 Consistent Identification, Level AA). Since 2026-11-13
          that is every issue type, so they are the whole report. (From
          2026-11-10 it opened on Mostly sure and Measured only, and a "Plus
          12 hidden" line counted the rest; if the default ever leaves rows
          out again, say so here, because a limitation is never dropped to
          make a number look smaller, Interface language rule 4.) The
          Reports list counts the same way (routes/Scans.tsx). */}
      {/* mb-8: the facts line that used to sit under the numbers is gone
          (2026-11-27), so the numbers keep the 32px to the table it had. */}
      <SummaryNumbers className="mb-8">
        {/* No "?" after the two counts' names since 2026-11-27 (the
            developer removed them; they had been added 2026-11-16). What an
            issue type and an occurrence are is still in words everyone can
            reach: "What the labels mean" in "About this report" under the
            table, and the Issue occurrences column's hint (SC 3.1.3 Unusual
            Words, Level AAA). */}
        <SummaryStat label={issueGroups === 1 ? "Issue type" : "Issue types"} value={issueGroups} />
        <SummaryStat
          label={occurrences === 1 ? "Issue occurrence" : "Issue occurrences"}
          value={occurrences}
        />
        {/* "47 of 47 Pages visited" on one line, with "List the pages
            visited" under it where the other numbers' labels are (the
            developer's layout, 2026-11-27). "of 47" no longer says "found":
            the label beside it would have made "47 of 47 found Pages
            visited". Pages found is named in "How this scan ran". */}
        <SummaryStat
          label="Pages visited"
          value={scan.page_count}
          outOf={
            scan.coverage.pages_found != null ? `of ${scan.coverage.pages_found.toLocaleString()}` : undefined
          }
          labelBeside
          after={scan.page_count > 0 || scan.error_count > 0 ? <PagesVisitedAfter scan={scan} /> : undefined}
          className="col-span-2 sm:col-span-1"
        />
      </SummaryNumbers>
    </>
  );
}

/**
 * The row of summary numbers over a report view's table: a ``dl`` of
 * ``SummaryStat``s, with no panel, border or fill. The spacing, the columns
 * and why there is no frame are explained on the Issues numbers above
 * (ReportSummary); this is the same row, so every report view that counts
 * its table's rows shows them in the same place and the same form (SC 3.2.4
 * Consistent Identification, Level AA). ``className`` may change the column
 * count for a view with more or fewer numbers; nothing else should differ.
 */
export function SummaryNumbers({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <dl className={cn("mt-10 mb-5 grid grid-cols-2 gap-x-8 gap-y-8 sm:grid-cols-3 lg:gap-x-12", className)}>
      {children}
    </dl>
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
 * "How this scan ran": how much of the site the scan covered and the
 * settings that decided it, as one more closed row of ``ReportNotes``.
 * Always shown: every report has an ending and limits worth knowing. The
 * row's right side says how the scan ended, so it is seen without opening
 * anything (AGENTS.md, Interface language rule 4: never drop a limitation
 * to make the page shorter).
 *
 * It replaces the "Partial report" card a stopped scan used to get instead
 * of its report (the developer's decision, 2026-11-14): pages found, pages
 * visited, the limits chosen and how the scan ended say how complete a
 * report is better than a label did. A failed scan's reason is here too,
 * since its report now opens like any other. Axcess's own note
 * (``scan_note``, migration 0039), such as a sign-in scan that went back
 * from several tabs to one, follows them.
 *
 * The labels are the New scan form's ("Maximum pages", "Maximum link
 * depth"), so a setting has one name on both screens (SC 3.2.4 Consistent
 * Identification, Level AA). An inline ``dl``, the pattern Compare's legend
 * uses. Titled "How this scan ran", not "notes": "Issue notes" are what a
 * person writes (docs/plain-language.md).
 */
export function ReportScanNote({ scan }: { scan: ScanDetail }) {
  const { coverage } = scan;
  const facts: [string, string][] = [
    ["How it ended", endText(coverage)],
    ["Pages found", coverage.pages_found != null ? coverage.pages_found.toLocaleString() : "Not recorded"],
    ["Pages visited", coverage.pages_visited.toLocaleString()],
    // Both were on a line under the report's numbers until 2026-11-27,
    // when the developer removed it; here so no limitation is dropped
    // (Interface language rule 4). Page states stay at zero, because zero
    // is a limitation the reader needs.
    ["Pages that could not be loaded", scan.error_count.toLocaleString()],
    [CLICK_THROUGH_STATES_LABEL, (scan.dom_state_count ?? 0).toLocaleString()],
    [NUMBERS.max_pages.label, coverage.page_limit != null ? coverage.page_limit.toLocaleString() : "No limit"],
    [NUMBERS.max_depth.label, coverage.depth_limit != null ? coverage.depth_limit.toLocaleString() : "Not recorded"],
    ...(scan.failure_reason ? [["Why it failed", scan.failure_reason] as [string, string]] : []),
    ...(scan.scan_note ? [["Note from Axcess", scan.scan_note] as [string, string]] : []),
  ];
  return (
    <ReportNote id="report-scan-note" title="How this scan ran" meta={<span>{endText(coverage)}</span>}>
      <dl className="max-w-prose space-y-1 text-sm text-fg">
        {facts.map(([term, value]) => (
          <div key={term}>
            <dt className="inline font-semibold">{term}</dt>
            <dd className="inline">: {value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 max-w-prose text-sm text-fg-muted">
        A page is found when the scan finds a link to it. The scan stops looking for new pages when it reaches its
        maximum pages, when it is stopped, or when it fails, and it does not follow links deeper than its maximum
        link depth. The site may have more pages than it found. &ldquo;Stopped before the scan finished&rdquo; means
        someone pressed Stop or Axcess closed while the scan ran.
      </p>
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

/**
 * One glossary list under a real heading (an h3 under the note's h2), so a
 * screen-reader user can jump between the lists. Each term is the same chip
 * the table draws, above its definition rather than run into one line, so
 * an entry reads on its own and reflows cleanly when zoomed.
 *
 * The part every report view's "What … labels mean" note is built from
 * (Issues, Documents), so the notes look and read the same on each tab (SC
 * 3.2.4 Consistent Identification, Level AA). It was local to the Issues
 * route until Documents needed the same note; moved here unchanged rather
 * than copied, so the two cannot drift.
 */
export function GlossaryList({
  heading,
  items,
}: {
  heading: string;
  items: { key: string; term: ReactNode; help: string }[];
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-fg">{heading}</h3>
      <dl className="mt-2 space-y-3">
        {items.map(({ key, term, help }) => (
          <div key={key}>
            <dt>{term}</dt>
            <dd className="mt-1">{help}</dd>
          </div>
        ))}
      </dl>
    </div>
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
