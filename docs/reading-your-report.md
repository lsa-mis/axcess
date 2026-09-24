# Reading your Axcess report

A report is one completed scan: the pages Axcess tested, what each check
found, and the [evidence](glossary.md#evidence) behind each result. This guide
explains every screen, column, and export, and what to do next. Terms link to
the [Axcess glossary](glossary.md). A report is evidence for people to review;
it never proves [WCAG](glossary.md#wcag) conformance or legal compliance.

## On this page

- [The three report groups at a glance](#the-three-report-groups-at-a-glance)
- [Find a problem and fix it (for developers)](#find-a-problem-and-fix-it-for-developers)
- [The Overview tab](#the-overview-tab)
- [The Issues tab](#the-issues-tab)
- [The full evidence record](#the-full-evidence-record)
- [The note that shows which button revealed a problem](#the-note-that-shows-which-button-revealed-a-problem)
- [Recording decisions](#recording-decisions)
- [Exports](#exports)
- [Verify changes after a fix](#verify-changes-after-a-fix)
- [Acting on findings](#acting-on-findings)
- [What the report cannot tell you](#what-the-report-cannot-tell-you)

## The three report groups at a glance

![Diagram of the three report groups. Barrier holds rule-engine failures from axe-core and Siteimprove Alfa, including problems found after clicking or after a configured search; confirm them on the page, fix, and rescan. Needs review holds browser checks, the keyboard trap check, motion checks, text in images whose alt text is missing or does not match, AI checks, and Alfa "cannot tell" results; a person tests and records a decision. Informational holds images whose alt text already matches and older records kept for history; no action is needed.](images/diagrams/report-groups.png)

Each [issue group](glossary.md#issue-group) lands in one report group, based
on the check that found it and its result. Only rule-engine failures become
Barriers; anything a person has to judge waits in Needs review.

| Report group | What to do |
| --- | --- |
| [Barrier](glossary.md#barrier) | Start here. Confirm it on the page, fix it, and rescan. |
| [Needs review](glossary.md#needs-review) | Test it on the page and record a decision before anyone calls it a barrier. |
| [Informational](glossary.md#informational) | Nothing to fix. It shows you what was checked. |

## Find a problem and fix it (for developers)

On the **Issues** tab, select an issue's name to open its
[full evidence record](#the-full-evidence-record). From there:

| You need | Where it is |
| --- | --- |
| The page URL | **Pages with this issue** lists each page's title and URL, with **Open live page**. |
| The selector and code | **Flagged element** shows up to three sample locations, each with its selector and highlighted HTML. A page's **Stored evidence** lists every result on that page, with **Selector for developers**. |
| An image with text in it | For an [image of text](glossary.md#image-of-text), **Flagged element** names the image by its position on the page, such as Image occurrence 2 (above the fold), with its alt text if it has any. It has no selector or HTML. The page's **Stored evidence** lists the image under **Images on this page**, with **Open the image** (the image's address), any alt text, and the text read from it. Search your code or content system for that image address. |
| A screenshot | **Issue screenshots** links to circled screenshots when the scan captured them. Siteimprove Alfa results have none, because Alfa runs in a separate browser session. |
| The page inspector | Select a page title in **Pages with this issue**. The inspector opens the stored page (or a fresh render if none was stored) with scripts off and the flagged elements highlighted, and **DOM source** shows the markup. |

Open **Why it matters, and how to fix it**, which starts collapsed. For
Needs review it is called **Why it matters, and what to check**. Make the
changes in **Expected behavior**, check them against **Done when**, and confirm
them with **How to verify** (**What to check to confirm** for Needs review).

**Rule docs** sits at the top of the record, beside the evidence confidence
chip, and appears only when the rule has its own documentation. Start there
when the record has no written guidance.

To reproduce a problem that appears only after a click:

1. Find the control's name under the page name in **Flagged element**, such
   as After clicking “Menu”. The note names only the last control used. For a
   page not among those samples, look in that page's **Stored evidence**,
   which groups results under headings such as After clicking “Menu”.
2. Select the page title in **Pages with this issue** to open the inspector,
   then open **Page state**. The entry with a count, such as
   After clicking “Menu” → “Settings” (2), lists every control in order and
   shows the markup the scan captured.
3. On the live page, use each control in that order, then find the element by
   its selector.

### If you have a ticket or a workbook row, not the app

Reports stay where Axcess ran the scan, so you may get only an export.

- **Jira ticket**: **Page** is the page address. **Target selector** and
  **Failing HTML** locate the element, **To reproduce** names any control to
  use first, and **Rule docs**, when present, links to the rule's
  documentation. These tickets have no fix steps, so ask for the issue's
  **Expected behavior** or use the workbook. A ticket for an image of text
  instead lists **Image URL**, **OCR text**, any **Suggested fix**, and each
  page under **Occurrences**.
- **The "Review locally" link** in a ticket opens only where the Axcess app
  that made the export is running, usually the analyst's computer.
- **Workbook issue tab**: **Where** names the page, **Element** gives the
  selector (or the image address), and **User action** says what to open
  first. **What to fix** and **How to reproduce** are described under
  [Exports](#exports). The **Page References** sheet links every affected page.

For a nested state, **To reproduce** and **User action** name only the last
control, like the note in the app. Ask the analyst for the full chain, which
the inspector's **Page state** picker shows.

## The Overview tab

A finished report opens on **Overview**, beside the **Issues** and **Verify
changes** tabs. Its header holds the **Export** menu and **Open Issue Groups**.

| Tile | What it counts |
| --- | --- |
| Pages Tested | Every page the scan recorded, including pages that answered with an error and pages that failed to load. Its hint counts crawl errors (pages that failed to load or could not be processed). Most of those are already counted in this number, not extra pages. |
| Issues Found | [Occurrences](glossary.md#occurrence) in every issue group, including Needs review and Informational, so it is not a count of confirmed problems. |
| Issue Groups | Rows in the Issues table, across all three report groups. |
| DOM States Found | [DOM states](glossary.md#dom-state) the scan reached by operating controls. |

**What this scan actually checked** lists each method, such as axe-core and
Click Through DOM States. Each row shows a result and one of these states: Not
selected, Waiting, Checking, Ran, Partly ran, Did not run, or Not recorded.
Open a row for what it found and what it cannot prove. The focus and visual
checks have no row here.

The crawl error count says how many pages failed, not which ones. See
[pages not reached](glossary.md#pages-not-reached) for what the report does and
does not list.

## The Issues tab

The header counts issue groups and occurrences and adds "Evidence for expert
review, not a conformance verdict." The columns, in order:

| Column | What it shows |
| --- | --- |
| Issue | The issue's name. Select it for the full evidence record. |
| Type | The report group: Barrier, Needs review, or Informational. |
| WCAG | The [success criterion](glossary.md#success-criterion) with its [level](glossary.md#conformance-level) badge, or "Best practice" (see [best practice](glossary.md#best-practice)). |
| Priority | High, Medium, or Low (see [priority](glossary.md#priority)); "n/a" for Informational rows. |
| Pages | How many pages have it, linked to the list of those pages. |
| Occurrences | How many places it appears. |
| Difficulty | Beginner, Intermediate, or Advanced when the rule has an estimate; "n/a" otherwise and for Informational rows. |
| Responsibility | Who usually makes the fix, such as Dev, Editor, or Designer; "n/a" for Informational rows. |
| About | A short summary, described below. |

Filter with the **Search issues** box (an issue name or WCAG criterion number), **Level** (A,
AA, AAA, or Best practice), and **Type** (a report group).

The table opens "Sorted by Priority, barriers first, then highest first":
Barriers, then Needs review, then Informational, each by priority. Select
another column header (not About) to re-sort; 10 issue groups show per page.

**About** opens What it is, Why it matters, Expected behavior, Done when, and
Abilities affected, plus links to the **Full evidence record** and **Rule
docs**. Needs review rows add "Do not describe this as a confirmed barrier
until the expert decision is documented."

## The full evidence record

1. **Report group card**: the group, an evidence confidence chip (high,
   medium, or low), and **Rule docs**. A one-line evidence summary follows,
   such as "Deterministic axe-core rule failure; verify after remediation." It calls
   Needs review "Needs confirmation" (the dashboard says "Review leads").
2. **Facts**: Criterion level, Priority, Pages affected, Occurrences,
   Difficulty, Responsibility, and Abilities affected.
3. **Pages with this issue**: page title (opens the inspector), Page URL,
   Open live page, Stored evidence, Occurrences, Issue screenshots, and status.
4. **What it is**, then **Why it matters, and how to fix it** (for Needs
   review, **Why it matters, and what to check**).
5. **Flagged element**: up to three sample locations, each with the page, any
   After clicking note, the selector, highlighted HTML, and context.

## The note that shows which button revealed a problem

By default, Axcess opens menus, tabs, dialogs, and other controls, then runs
axe-core on each new [DOM state](glossary.md#dom-state). When a problem was
first flagged after a control was used, the report names that control (here,
"Menu"). A problem visible at page load never gets this note.

| Where | What it says |
| --- | --- |
| Issue page, **Flagged element** | `After clicking “Menu”` under the page name |
| A page's **Stored evidence** | Groups `At page load (N findings)`, then `After clicking “Menu” (N findings)` |
| Page inspector, **Page state** picker | `At page load (N)` and `After clicking “Menu” → “Settings” (N)`, with the note `Captured during the scan, after the control was operated.` |
| Workbook, **User action** column | `Open "Menu" on this page.` or `Load the page.` |
| Audit report | `Seen after: activating "Menu" on this page.` |
| Jira CSV | `To reproduce: Load the page, then activate "Menu".` or `Load the page.` |
| Issue table CSV | `revealed_by`, empty for page-load results |
| Raw findings JSON | `a11y_findings[].revealed_by`, `null` for page-load results |

Image findings and the Markdown evidence inventory never show it. Results from
a [configured search](spa-search-scans.md) name “Configured search”, and a
control with no readable name shows its tag, such as `<button>`.

## Recording decisions

Every finding starts with the [status](glossary.md#status) new. Then use:

- **Reviewing** while you check it.
- **In progress** once you confirm a real barrier and plan a fix.
- **Remediated** when it is fixed.
- **Accepted risk** when your team decides to accept it.
- **False positive** when it is not a real problem.

The last four need a reason, which the app saves in the finding's history but
does not show again.

You cannot change status in the Issues table or the evidence record. Instead:

1. Open **Overview**.
2. Expand **Expert tools and scan details**.
3. For page results, choose **DOM engines** (use **Group by rule** to change a
   whole rule). For image results, choose **Image evidence** (use **Group by
   issue** for a whole group).

Remediated, accepted risk, and false positive results move to the audit
report's Appendix A and leave the Jira CSV; a Needs review group marked in
progress becomes an issue card. Status never changes a result's report group.

## Exports

The **Export** menu on the Overview and Issues tabs offers the first four
formats. The last two need the API (`/api/scans/{id}/export/jira` or
`.../export/markdown`) or the command line (`audit export -f jira` or `-f markdown`).

| Format | Best for | Main sheets or columns |
| --- | --- | --- |
| Remediation workbook (`.xlsx`) | Assigning and tracking fixes | A summary, an issue index, a tab per issue, and supporting sheets (listed below the table) |
| Audit report (`.audit.md`) | A narrative report for stakeholders | Sections from an executive summary to the appendices (listed below the table) |
| Issue table (`.csv`) | Filtering in a spreadsheet | One row per finding (per page for an image finding), 24 columns such as `severity`, `status`, `wcag_criterion`, `page_url`, `target_selector`, and `revealed_by` |
| Raw findings (`.json`) | Scripts and other tools | `scan`, `findings` (image results), and `a11y_findings` (everything else) |
| Jira CSV (`.jira.csv`) | Importing tickets | Summary, Description, Priority, Issue Type, Labels, Component; one row per finding not marked remediated, accepted risk, or false positive |
| Markdown evidence inventory (`.md`) | A raw list of every result | Every result with its status, including review leads |

Remediation workbook sheets:

- Summary
- Issues Overview: ID, Issue, Severity, Conformance Level, Remediation
  Ownership, Status, Instances, Pages, and Details
- A tab per issue for the first 40 issues: #, Where, User action, Element,
  What to fix, and How to reproduce
- More Issues, which holds the rest when there are more than 40
- Page Hotspots
- Page References
- DOM States
- Who's Affected
- Coverage & Method
- Test Tracking
- Manual Review Evidence

Audit report sections:

- Executive summary
- Open barrier summary
- Who is affected
- Coverage and method
- WCAG 2.2 A/AA coverage
- Page hotspots
- Remediation worklist by owner
- Issue cards
- Appendix A and B

Notes on the exports:

- **What to fix** exists only in the workbook. It copies the issue's fix
  steps (**Expected behavior** in the app) onto every instance row. It is
  general advice, not advice for that one instance, and it is blank when the
  rule has none. **How to reproduce** holds verification steps, not steps to
  reproduce.
- Audit report issue cards cover open Barrier groups tied to a WCAG criterion
  and Needs review groups marked in progress; other open results, including
  review leads, go to Appendix B. The workbook Summary's "Likely-barrier"
  counts follow these cards, so they can differ from the Issues table.
- The workbook's Issues Overview, the CSV, the JSON, and the Jira CSV have no
  report group column. The Jira CSV also includes Needs review leads and
  Informational records, so check it before you import. Edits to a
  downloaded file never flow back to Axcess.

### Draft labels

Export menu downloads are labeled a [draft](glossary.md#draft-export) until
the report's expert evaluation is complete and every Barrier and Needs review
finding has a status other than new or reviewing. A draft has `_DRAFT` in its
file name and a notice inside, such as a "DRAFT NOTICE" sheet or an "Axcess
export state" CSV column. The app has no screen for completing the evaluation
yet, so for now every Export menu download is a draft. The command-line
`audit export` adds no draft label.

## Verify changes after a fix

After you publish fixes, scan the same site again with the same checks.
**Verify changes** compares this report with the latest earlier completed
report for the same start address, counting issue groups, not findings.

| Category | What the app tells you |
| --- | --- |
| New | Found only in the later report. Check whether it is a new barrier. |
| Still detected | The same findings were recorded in both reports. Check the issue's review status for next steps. |
| Changed | Locations, counts, results, or review statuses differ. This does not always mean improvement. |
| No longer detected | Not found again with comparable checks. Confirm the fix on the page before marking it remediated. |
| Cannot compare reliably | Missing evidence or different coverage prevents a reliable conclusion. Recheck the affected pages. |

Read the **Comparison coverage** notes before you trust a result. See
[rescan comparison](glossary.md#rescan-comparison).

## Acting on findings

A long list is normal for a first scan, and nobody clears it in one sitting.
Progress Over Perfection: each barrier you fix helps someone use the site today.

1. **Barriers first.** They top the Issues table; confirm each one, then fix
   it. [Priority](glossary.md#priority) favors spread, so also check the
   workbook's Severity column for a severe problem on a single page.
2. **Then Needs review.** Test each lead and record a decision.
3. **Batch shared fixes.** Axcess groups by check, not by
   [root cause](glossary.md#root-cause), so look for one template or component
   behind an issue on many pages, and route work by Responsibility.
4. **Rescan** and check your work in **Verify changes**.

## What the report cannot tell you

- **Whether the site conforms.** The audit report calls a clean run
  "necessary, not sufficient" for conformance.
- **What only a person can judge.** Many WCAG 2.2 Level A and AA success
  criteria have no automated check at all. See
  [What you still need to test by hand](https://lsa-mis.github.io/axcess/coverage/#by-hand)
  and [manual testing](glossary.md#manual-testing).
- **Pages and states it never reached** (see
  [pages not reached](glossary.md#pages-not-reached)). A method marked Not
  selected did not run, with one exception: the image row reads Not selected
  whenever the vision model is off, although OCR image results can still
  appear. The click-through cannot reach hover-only content, gestures,
  operating-system menus, closed shadow DOM, cross-origin embeds, or states
  with no observable DOM change.
- **What axe-core could not decide.** Axcess keeps only axe-core's
  violations, not the results it marks as incomplete.
