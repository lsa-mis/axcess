# Reading your Axcess report

A report is one completed scan: the pages Axcess tested, what each check
found, and the [evidence](glossary.md#evidence) behind each result. This guide
explains every screen, column, and export, and what to do next. Terms link to
the [Axcess glossary](glossary.md). A report is evidence for people to review;
it never proves [WCAG](glossary.md#wcag) conformance or legal compliance.

## On this page

- [The three report groups at a glance](#the-three-report-groups-at-a-glance)
- [Find a problem and fix it (for developers)](#find-a-problem-and-fix-it-for-developers)
- [The report summary](#the-report-summary)
- [The Issues tab](#the-issues-tab)
- [The full evidence record](#the-full-evidence-record)
- [The note that shows which button revealed a problem](#the-note-that-shows-which-button-revealed-a-problem)
- [Recording decisions](#recording-decisions)
- [Exports](#exports)
- [Compare reports after a fix](#compare-reports-after-a-fix)
- [Acting on findings](#acting-on-findings)
- [Delete a report](#delete-a-report)
- [What the report cannot tell you](#what-the-report-cannot-tell-you)

## The three report groups at a glance

![Diagram of the three report groups. Barrier holds rule-engine failures from axe-core and Siteimprove Alfa, including problems found after clicking or after a configured search; confirm them on the page, fix, and rescan. Needs review holds browser checks, the keyboard trap check, motion checks, text in images whose alt text is missing or does not match, AI checks, and Alfa "cannot tell" results; a person tests and records a decision. Informational holds images whose alt text already matches and older records kept for history; no action is needed.](images/diagrams/report-groups.png)

Each [issue](glossary.md#issue) lands in one report group, based on the check
that found it and its result. Only rule-engine failures become Barriers;
anything a person has to judge waits in Needs review. The app calls the report
group an issue's **Type**.

| Report group | What to do |
| --- | --- |
| [Barrier](glossary.md#barrier) | Start here. Confirm it on the page, fix it, and rescan. |
| [Needs review](glossary.md#needs-review) | Test it on the page and record a decision before anyone calls it a barrier. |
| [Informational](glossary.md#informational) | Nothing to fix. It shows you what was checked. |

## Find a problem and fix it (for developers)

On the **Issues** tab, select an issue's name to open its
[issue page](#the-full-evidence-record). From there:

| You need | Where it is |
| --- | --- |
| The page URL | **Pages with this issue** lists each page's title and URL. In the inspector, **Open live page** opens the page on the real site. |
| The element locator and code | In the inspector, **Evidence from the scan**, under the page, lists the first three occurrences with their element locator (CSS selector) and element code (HTML). A page's **Page details**, linked from its screenshots view, lists every occurrence on that page, with **Element locator (CSS selector), for developers**. |
| An image with text in it | For an [image of text](glossary.md#image-of-text), the page's **Page details** lists the image under **Images on this page**, with **Open the image** (the image's address), any alt text, and the text read from it. Search your code or content system for that image address. |
| A screenshot | The **Screenshots** column in **Pages with this issue** links to a screenshot of each occurrence, when the scan took one. An outline marks where the occurrence was found. Rule check (Alfa) results have no screenshots, because Alfa runs in a separate browser. |
| The page inspector | Select a page title in **Pages with this issue**. The inspector opens the page's **Saved copy** (or the **Live page**, if the scan saved no copy) with scripts off, and red outlines mark the flagged elements. The arrow buttons beside the count, such as "Flagged element 2 of 5", step to the previous or next flagged element; the one you are on has a thicker blue outline on yellow. The **Page code (DOM)** tab shows the page code, with the same buttons. |

**Issue guidance**, at the top right of the issue page, opens the issue's
guidance in one dialog, with every section open: **What it is**, **How to fix
it** with **Done when**, and **Why it matters, and how to test the fix** with
**How to test the fix**. For Needs review, **How to confirm it** comes second,
and the fix is under **How it should work** in **Why it matters, and how to
fix it if it is confirmed**.

**About this rule** sits in **What it is**, beside the confidence, and
appears only when the rule has its own documentation. Start there when the
issue has no written guidance.

To reproduce a problem that appears only after a click:

1. Open the page's **Page details**, which groups occurrences under headings
   such as After clicking “Menu”. The heading names only the last control
   used.
2. Select the page title in **Pages with this issue** to open the inspector.
   It opens on the page state where the issue appears. The **Page state**
   list offers At page load and each state where the issue appears. An entry
   such as After clicking “Menu” → “Settings”: 2 occurrences lists every
   control in order and shows the page code the scan saved.
3. On the live page, use each control in that order, then find the element by
   its element locator (CSS selector).

### If you have a ticket or a workbook row, not the app

Reports stay where Axcess ran the scan, so you may get only an export.

- **Jira ticket**: **Page** is the page address. **Target selector** and
  **Failing HTML** locate the element, **To reproduce** names any control to
  use first, and **Rule docs**, when present, links to the rule's
  documentation. These tickets have no fix steps, so ask for the issue's
  **Issue guidance** from the app, or use the workbook. A ticket for an image
  of text instead lists **Image URL**, **OCR text**, any **Suggested fix**,
  and each page under **Occurrences**.
- **The "Review locally" link** in a ticket opens only where the Axcess app
  that made the export is running, usually the analyst's computer.
- **Workbook issue tab**: **Where** names the page, **Element** gives the
  element locator (or the image address), and **User action** says what to
  open first. **What to fix** and **How to reproduce** are described under
  [Exports](#exports). The **Page References** sheet links every affected
  page.

For a nested state, **To reproduce** and **User action** name only the last
control, like the note in the app. Ask the analyst for the full chain, which
the inspector's **Page state** list shows.

## The report summary

A finished report opens on **Issues**. Under the title, "Based on the report
generated" gives the date and time the scan finished, and the **Export
report** menu sits at the top right. Four numbers above the table count:

| Number | What it counts |
| --- | --- |
| Pages checked | Every page the scan recorded, including pages that answered with an error and most pages that failed to load. Beside it, in parentheses, is the number of [errors while scanning](glossary.md#pages-not-reached), and most of those pages are already in this number. |
| Occurrences found | [Occurrences](glossary.md#occurrence) in every issue, including Needs review and Informational, so it is not a count of confirmed problems. |
| Issues found | Rows in the Issues table, across all three report groups. |
| Page states opened by clicking | [Page states](glossary.md#page-state) the scan reached by using menus, tabs, dialogs, and other controls. |

Below the numbers, two closed rows open more detail. **What was checked**
shows how many checks ran, such as "7 of 9 checks ran". It opens a table with
one row per check, such as Rule check (axe) and Click-Through, and the checks
that ran come first. **Status** is one of Not selected, Waiting, Checking, Ran,
Partly ran, Did not run, or Not recorded, with a check mark for Ran and Partly
ran. **Result** says what the check ran on and what it found. **About this
check** says in one line each what the check does and its limit, and **More
about this check** opens its card on the Axcess website. The focus and visual
checks have no row here. The second row, **What Barrier, Needs review
and the other labels mean**, explains the words in the **Type** and **Found
by** columns.

The error count says how many pages failed, not which ones. See
[pages not reached](glossary.md#pages-not-reached) for what the report does and
does not list.

## The Issues tab

The summary line counts issues and occurrences. The table's columns, in
order:

| Column | What it shows |
| --- | --- |
| Issue | The issue's name. Select it to open the issue page. |
| Type | The report group: Barrier, Needs review, or Informational. |
| Found by | Which kind of check found it: WCAG, Click-Through, or Alt Text (see [Found by](glossary.md#found-by)). One issue can show both WCAG and Click-Through. |
| WCAG | The [success criterion](glossary.md#success-criterion) number with its [level](glossary.md#conformance-level) badge, or "Best practice" (see [best practice](glossary.md#best-practice)). |
| Priority | High, Medium, or Low (see [priority](glossary.md#priority)); "Does not apply" for Informational rows. |
| Pages | How many pages have it, linked to the list of those pages. |
| Occurrences | How many places it appears. |

Search with the **Search issues** box (an issue name or a WCAG number, such as
1.4.3). The **Filter** menu narrows the table by **Level** (Level A, AA, AAA,
or Best practice), **Type** (a report group), and **Found by**. When you choose
one **Found by** value, a link to its detailed view appears above the table:
**Rule check issues by WCAG criterion**, or **Images** for Alt Text.

The table opens in the recommended order: Barriers, then Needs review, then
Informational, each by priority. Select a column header to sort by that
column, and **Back to recommended order** to return. As the filters change, a
screen reader hears how many issues show and how many of each type, such as
"12 of 40 issues shown, filtered: Barrier 3, Needs review 7, Informational 2".

Each issue's title opens its [issue page](#the-full-evidence-record).
**Delete report**, at the end of the Issues page, is described under
[Delete a report](#delete-a-report).

## The full evidence record

The issue page is the full evidence record for one issue. It leads with
**Pages with this issue**: page title (opens the inspector), Page URL,
Occurrences, Screenshots, and Status. Its header names the WCAG criterion and
the issue's type, in the same words as the Issues table's **Type** column.

**Issue guidance**, at the top right, opens a dialog with every section open:

1. **What it is** (**What Axcess found** for Informational): the type and
   what it means, the confidence (high, medium, or low), and **About this
   rule**, then "Why it was flagged", a one-line summary such as
   "Deterministic axe-core rule failure; verify after remediation." Then the
   facts (WCAG level, Priority, Occurrences across its pages, and who it
   affects) and the rule's description.
2. **How to fix it**, with **Done when** (for Needs review, **How to confirm
   it**).
3. **Why it matters, and how to test the fix**, with **How to test the fix**
   (for Needs review, **Why it matters, and how to fix it if it is
   confirmed**, with **How it should work** and **Done when**).

Escape or the close button returns you to the page.

## The note that shows which button revealed a problem

By default, Axcess opens menus, tabs, dialogs, and other controls (the
[Click-Through](glossary.md#click-through) check), then runs axe-core on each
new [page state](glossary.md#page-state). When a problem was first flagged
after a control was used, the report names that control (here, "Menu"). A
problem visible at page load never gets this note.

| Where | What it says |
| --- | --- |
| A page's **Page details** | Groups `At page load (N occurrences)`, then `After clicking “Menu” (N occurrences)` |
| Page inspector, **Page state** list | `At page load: N occurrences` and `After clicking “Menu” → “Settings”: N occurrences`, with the note `The scan saved this page state after clicking the control.` When every occurrence came after a click, At page load shows `Issue not here`. |
| Workbook, **User action** column | `Open "Menu" on this page.` or `Load the page.` |
| Written report | `Seen after: activating "Menu" on this page.` |
| Jira CSV | `To reproduce: Load the page, then activate "Menu".` or `Load the page.` |
| Occurrence list (CSV) | `revealed_by`, empty for page-load results |
| All report data (JSON) | `a11y_findings[].revealed_by`, `null` for page-load results |

Image text check results and the Markdown evidence inventory never show it.
Results from a [configured search](spa-search-scans.md) name “Configured
search”, and a control with no readable name shows its tag, such as
`<button>`.

## Recording decisions

Every occurrence starts with the [status](glossary.md#status) New. Then use:

- **Reviewing** while you check it.
- **In progress** once you confirm a real barrier and plan a fix.
- **Fixed** when it is fixed.
- **Accepted risk** when your team decides to accept it.
- **Not a problem (false positive)** when it is not a real problem.

The last four need a reason, which the app saves in the occurrence's history
but does not show again.

You cannot change status in the Issues table or on the issue page. Instead:

1. On the report's **Issues** tab, open the **Filter** menu and choose one
   **Found by** value.
2. For page results, select **Rule check issues by WCAG criterion** (use
   **Group by rule** to change a whole rule). For image results, select
   **Images** (use **Group by issue** to change a whole issue).

Fixed, Accepted risk, and Not a problem results move to the written report's
Appendix A and leave the Jira CSV; a Needs review issue marked In progress
becomes an issue card. Status never changes a result's report group.

## Exports

The **Export report** menu, at the top right of the Issues tab, offers the
first four formats. The last two need the API (`/api/scans/{id}/export/jira`
or `.../export/markdown`) or the command line (`audit export -f jira` or
`-f markdown`).

| Format | Best for | Main sheets or columns |
| --- | --- | --- |
| Issue list with fixes (Excel, `.xlsx`) | Assigning and tracking fixes | A summary, an issue index, a tab per issue, and supporting sheets (listed below the table) |
| Written report (Markdown, `.audit.md`) | A narrative report for stakeholders | Sections from an executive summary to the appendices (listed below the table) |
| Occurrence list (CSV, `.csv`) | Filtering in a spreadsheet | One row per occurrence (per page for an image), 24 columns such as `severity`, `status`, `wcag_criterion`, `page_url`, `target_selector`, and `revealed_by` |
| All report data (JSON, `.json`) | Scripts and other tools | `scan`, `findings` (image results), and `a11y_findings` (everything else) |
| Jira CSV (`.jira.csv`) | Importing tickets | Summary, Description, Priority, Issue Type, Labels, Component; one row per occurrence not marked Fixed, Accepted risk, or Not a problem |
| Markdown evidence inventory (`.md`) | A raw list of every result | Every result with its status, including Needs review results |

Sheets in the issue list with fixes (Excel):

- Summary
- Issues Overview: ID, Issue, Severity, Conformance Level, Remediation
  Ownership, Status, Instances, Pages, and Details
- A tab per issue for the first 40 issues: #, Where, User action, Element,
  What to fix, and How to reproduce
- More Issues, which holds the rest when there are more than 40
- Page Hotspots
- Page References
- Click-Through
- Who's Affected
- Coverage & Method
- Test Tracking
- Manual Review Evidence

Written report sections:

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
  steps (**How to fix it** in the app, or **How it should work** for Needs
  review) onto the row for every occurrence. It is general advice, not advice
  for that one occurrence, and it is blank when the rule has none. **How to
  reproduce** holds the steps to test the fix, not steps to reproduce.
- Written report issue cards cover open Barrier issues tied to a WCAG
  criterion and Needs review issues marked In progress; other open results,
  including other Needs review results, go to Appendix B. The workbook
  Summary's "Likely-barrier" counts follow these cards, so they can differ
  from the Issues table.
- The workbook's Issues Overview, the CSV, the JSON, and the Jira CSV have no
  report group column. The Jira CSV also includes Needs review and
  Informational results, so check it before you import. Edits to a downloaded
  file never flow back to Axcess.

### Draft labels

Export menu downloads are labeled a [draft](glossary.md#draft-export) until
the report's expert review is complete and every Barrier and Needs review
occurrence has a status other than New or Reviewing. A draft has `_DRAFT` in
its file name and a notice inside, such as a "DRAFT NOTICE" sheet or an
"Axcess export state" CSV column. The app has no screen for completing the
review yet, so for now every download from the **Export report** menu is a
draft. The command-line `audit export` adds no draft label.

## Compare reports after a fix

After you publish fixes, scan the same site again with the same checks.
**Compare reports** compares this report with the latest earlier completed
report for the same start address, counting issues, not occurrences.

| Change | What it means |
| --- | --- |
| New | Found in this report but not in the earlier one. Check whether it is a new barrier. |
| No longer found | Found in the earlier report but not found again in this one. That is not proof of a fix. Check the page yourself before you mark the issue Fixed. |
| Still found | Found in both reports. Its number of occurrences can still go up or down. |

The page opens with **Trend over time**, which plots every completed scan of
the site. Select a point in the trend, or use **Show as data table**, to open
that scan's issues or compare it with this report. Below it are the three
numbers; each is also a filter for the table of issues under them, which
shows the occurrences before and after and the change between them. **What do
these terms mean?**, at the top right, explains each word.

When the checks, settings, or pages scanned differ between the two reports,
the page says so above the numbers: an issue can look new or no longer found
only because of what was scanned. Read **What was checked in each report**, at
the end of the page, before you trust a result. See
[rescan comparison](glossary.md#rescan-comparison).

## Acting on findings

A long list is normal for a first scan, and nobody clears it in one sitting.
Progress Over Perfection: each barrier you fix helps someone use the site today.

1. **Barriers first.** They top the Issues table; confirm each one, then fix
   it. [Priority](glossary.md#priority) favors spread, so also check the
   workbook's Severity column for a severe problem on a single page.
2. **Then Needs review.** Check each one on the page and record a decision.
3. **Batch shared fixes.** Axcess groups by check, not by
   [root cause](glossary.md#root-cause), so look for one template or component
   behind an issue on many pages, and route the fix to whoever owns it.
4. **Rescan** and check your work in **Compare reports**.

## Delete a report

**Delete report**, at the end of the Issues page, deletes the report. It asks
you first, unless **Ask before deleting** is off in Settings. It removes the
report and everything the scan saved for it; image files that other reports
also use may stay in storage. You cannot undo this. You cannot delete a
running scan: cancel it first.

## What the report cannot tell you

- **Whether the site conforms.** The written report calls a clean run
  "necessary, not sufficient" for conformance.
- **What only a person can judge.** Many WCAG 2.2 Level A and AA success
  criteria have no automated check at all. See
  [What you still need to test by hand](https://lsa-mis.github.io/axcess/coverage/#by-hand)
  and [manual testing](glossary.md#manual-testing).
- **Pages and states it never reached** (see
  [pages not reached](glossary.md#pages-not-reached)). A check marked Not
  selected did not run, with one exception: the image row reads Not selected
  whenever the vision model is off, although OCR image results can still
  appear. Click-Through cannot reach hover-only content, gestures,
  operating-system menus, closed shadow DOM, cross-origin embeds, or page
  states with no change to the page code (DOM).
- **What axe-core could not decide.** Axcess keeps only axe-core's
  violations, not the results it marks as incomplete.
