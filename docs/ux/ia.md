# Axcess UX refresh: information architecture (single page)

Status: Phase 2 output, 2026-09-23. Built on [research.md](research.md). Assumptions A1 to A10 and the principles live in research.md sections 8 and 9.
FigJam diagrams (IA tree, focus order, 3 task flows): https://www.figma.com/board/jIIaA4IsZe4LfSrdZlHR2p (also linked from Figma page "01 IA and Flows").

The page is the **report page**. The URL `/app/` with query state is the only reporting route. Every job in research.md section 4 finishes here.

---

## 1. Changes to the starting hypothesis

| # | Hypothesis item | Change | Reason (research ref) |
|---|---|---|---|
| C1 | App scope: one app or all apps | Kept. "App" means the normalized seed URL. | No app entity exists (§6, A3) |
| C2 | Views as presets | Moved from the list toolbar into the report header. Presets set page-wide defaults (what is expanded, filters, columns). They never hide a zone. | Presets change zones above the list (progress, health). A control placed below those zones would change content before it, breaking predictable order (3.2). |
| C3 | Status strip first under the header | Added a plain-language **summary sentence** above the strip | The leader's 10-second test needs a text equivalent (§4.3). It also serves as the text alternative for the strip. |
| C4 | Strip: Fixed, Regressed, Needs review | "Regressed" becomes **Came back**. **Fixed** counts only fixes a person confirmed; unconfirmed "gone" instances are shown separately. | Plain language. "No longer detected" is not "fixed" (§2.3), so principle 3 applies. |
| C5 | Status list (7 values) | Added **Accepted risk** | The status exists in the data (`accepted_risk`), and ITS needs a way to record known exceptions (A2) |
| C6 | Group by rule plus component or pattern | The row is one **root cause merged across engines** (axe, Alfa, AI, browser tests). Component or pattern is shown as **Fix reach** inside the row and the panel. It is not a grouping key. | axe and Alfa agree on 143 of 143 elements, so per-engine rows double count (§5, rank 5). Template detection is a heuristic (A7); splitting on it would scatter triage decisions. |
| C7 | No home for trend | Added a **Progress** zone (the Done ledger and the trend). It is expanded in Overview and one line elsewhere. | The leader's trend job (§4.3) and principle 4 |
| C8 | Detail panel on the same page | At widths below 1024 px (which includes 400% zoom), the panel **replaces the list in place**. It is not an overlay. | An overlay at high zoom hides focus (2.4.11) and leaves no room |
| C9 | Header bar | The header is **not sticky**. Only the detail panel is sticky, at 1280 px and wider. The bulk bar reserves scroll padding. Nothing is sticky below 1024 px. | 2.4.11 and 2.4.12 at every zoom level. Today's sticky 72 px bar has no scroll padding (T10). |
| C10 | Scan health collapsed, auto-expanded on failure | Kept. Also: counts that health could skew get a **count caveat** marker linked to the health note. | The http/https duplicates inflate counts (§7) |
| C11 | (implicit) the app shell | The sidebar is removed from the report page. The Reports list becomes the App and Run pickers, and the Product roadmap moves into Help. | One page. The 256 px sidebar breaks the split view at 1280 px and wastes space at 400% zoom. |
| C12 | (not in hypothesis) login screen | Added an **Access** screen for hosted mode | 3.3.8. Today the gate is a plain-text 401 (T18). |
| C13 | Dismiss with reason | One inline **Decide** form with three outcomes: Confirm, Dismiss as false positive, Accept the risk. The reason is required for the last two, and the last reason is offered again. | Replaces `window.prompt` (T15); 3.3.7 Redundant Entry |

## 2. IA tree

```text
Report page (/app/?app&run&compare&view&filters&issue)
├── Skip links: "Skip to issue list", "Skip to issue details" (when open)
├── Top bar [banner]
│   ├── Axcess home
│   ├── App picker (one app | All apps)
│   ├── Help menu (How to read this report, Keyboard shortcuts, Contact the accessibility team, Product roadmap)
│   ├── Settings (theme, shortcuts on/off and remap, "after I decide, go to next issue")
│   └── Run scan (dialog, prefilled with the last settings)
├── Main [main]
│   ├── Report header
│   │   ├── h1 "Accessibility report: <app>"
│   │   ├── Run picker, Compare picker, scanned time and duration
│   │   ├── Scan health chip (opens zone 4)
│   │   └── View presets: Triage | Fix | Overview
│   ├── Zone 3 "At a glance" [region, h2]
│   │   ├── Summary sentence
│   │   ├── Severity tiles: Blocker, Critical, Major, Minor, Best practice (count + change since compare run)
│   │   └── Work tiles: Needs review, Came back, Fixed
│   ├── Zone 4 "Scan health and coverage" [region, h2, disclosure]
│   │   ├── Pages: checked, skipped, duplicated, redirected
│   │   ├── Sign-in: used or not, session outcome
│   │   ├── Checks that ran: per method, pages covered
│   │   ├── Excluded routes and blocked patterns
│   │   └── What no tool can check (manual criteria)
│   ├── Zone 5 "Progress" [region, h2, disclosure]
│   │   ├── Done ledger (fixed, dismissed with reason, accepted risk per run)
│   │   ├── Open issues by severity over the last runs (chart)
│   │   └── "Show as table" (data table equivalent) and a text summary
│   ├── Zone 6 "Issues" [region, h2]
│   │   ├── Toolbar: Find an issue, filter chips, Add filter, Clear all, Group by, Sort
│   │   ├── Issue table (root causes), grouped
│   │   ├── Pagination
│   │   └── Bulk bar (only when rows are selected)
│   └── Zone 7 "Issue details" [region, h2 = issue title]
│       ├── Header: severity, status, WCAG, trust (Witness marks), Previous, Next, Close
│       ├── Decide: Confirm | Dismiss or accept risk… | Create Jira ticket | Copy selector
│       ├── h3 What is wrong
│       ├── h3 Who it affects
│       ├── h3 Checks that found it (Witness marks, expanded)
│       ├── h3 Since Run N (the change, with the came-back history)
│       ├── h3 Where it happens (Fix reach, numbered instances table, evidence for the selected instance)
│       ├── h3 Suggested fixes (options, trade-offs, disclaimer)
│       ├── h3 Done when (acceptance criteria)
│       ├── h3 Jira ticket (draft in the ITS format)
│       └── h3 History (decisions, with reasons and who)
└── Footer [contentinfo]: "Results are evidence to review, not proof of compliance." Help and contact, version
Dialogs: Run scan, Keyboard shortcuts, Settings
Separate screen: Access (hosted mode only), before the report page
```

## 3. Content priority per zone (highest first)

| Zone | Priority order |
|---|---|
| Top bar | 1 App in view; 2 Run scan; 3 Help (fixed position); 4 Settings; 5 Home |
| Report header | 1 h1 (app); 2 which run and when; 3 health chip if not OK; 4 compare target; 5 view preset |
| At a glance | 1 summary sentence; 2 Blocker and Critical counts with change; 3 Came back; 4 Needs review; 5 Fixed; 6 Major, Minor, Best practice |
| Scan health | 1 anything that failed (auth, scan, a check that did not run); 2 notes that change counts (duplicates, redirects); 3 pages checked vs found; 4 checks and coverage; 5 exclusions; 6 manual-only criteria |
| Progress | 1 a text summary of the work done since the compare run; 2 Done ledger; 3 open-by-severity trend; 4 the table toggle |
| Issue row | 1 severity; 2 plain title; 3 status; 4 trust (Witness marks); 5 change since the compare run; 6 instances and pages; 7 WCAG SC and level; 8 Fix reach |
| Issue details | 1 title, severity, status, trust; 2 decision actions; 3 what is wrong; 4 who it affects; 5 where (instances, evidence); 6 suggested fixes; 7 done when; 8 ticket; 9 history |

## 4. View presets

Presets set defaults. The user can change anything after that, and the URL records the result. "Reset view" returns to the preset.

| | Triage (analyst) | Fix (developer) | Overview (leader) |
|---|---|---|---|
| Filter | Status: Came back, Needs review, New | Status: Came back, Confirmed, Ticketed | None |
| Group by | Status (Came back first) | Severity | Severity |
| Sort in group | Severity, then instances | Fix reach (fewest templates, most pages), then severity | Severity, then change |
| Columns | Select, Severity, Issue, Checks, Since Run N, Instances, Status | Select, Severity, Issue, Fix reach, Pages, Ticket, Status | Severity, Issue, Since Run N, Status |
| Progress zone | One line | One line | Expanded |
| Detail panel | Opens on Enter | Opens on Enter; deep links open it directly | Closed until asked |

## 5. Page landmarks and heading outline

```text
[banner] Top bar (no heading; the brand link is not a heading)
[main]
  h1  Accessibility report: museumcollab.anthro.lsa.umich.edu
    h2  At a glance                        [region]
    h2  Scan health and coverage           [region]
    h2  Progress                           [region]
    h2  Issues                             [region]
      (group headers in the table are row headers, not headings)
    h2  <Issue title>                      [region "Issue details"]
      h3  What is wrong
      h3  Who it affects
      h3  Checks that found it
      h3  Since Run 3
      h3  Where it happens
      h3  Suggested fixes
      h3  Done when
      h3  Jira ticket
      h3  History
[contentinfo] Footer
Dialogs have their own h2: "Run a new scan", "Keyboard shortcuts", "Settings"
```

There is exactly one h1. No heading level is skipped. The table groups use `<tbody>` with a `<th scope="rowgroup">` row, so they do not add headings to the outline.

## 6. Focus order

Tab order follows DOM order, which matches visual order at every width. At 1280 px and wider, the panel sits to the right of the list and follows it in the DOM.

1. Skip to issue list; Skip to issue details (only when the panel is open)
2. Top bar: Axcess home, App picker, Help, Settings, Run scan
3. Report header: Run picker, Compare picker, Scan health chip, View presets (one tab stop; arrow keys move between the presets)
4. At a glance: 8 tiles, left to right (toggle buttons)
5. Scan health: disclosure button, then its links when open
6. Progress: disclosure button, then "Show as table" and the table
7. Issues toolbar, in visual order: Find an issue, Group by, Sort, then each chip's remove button, Add filter, Clear all
8. Bulk actions bar (only while issues are selected; it sits between the filter chips and the table)
9. Issue table: Select all, each sortable header, then per row: Select checkbox, then the issue title button. Every row's checkbox and title are in the Tab order (native order, no roving).
10. Pagination
11. Issue details, in visual order: Previous issue, Next issue, Close details, then Confirm, Dismiss or accept risk…, Create Jira ticket, Copy selector, then in-section controls in reading order
12. Footer links

Rules:
- **Open details.** Enter on a row title opens the panel and moves focus to the panel's h2 (`tabindex="-1"`).
- **Close details.** Escape or Close returns focus to the same row title.
- **Next or previous issue.** Moves focus to the new h2, so the screen reader reads the new title.
- **A decision.** Focus stays on the action button, which now shows the new state, with an Undo button right after it. Focus never jumps on its own. The setting "After I decide, go to the next issue" is off by default.
- **Decided rows stay put.** In any filtered view, a row that no longer matches the filter after a decision stays in place, marked "Confirmed just now" (or Dismissed, Accepted risk), until the user chooses "Refresh list". So Escape and Close always return focus to an existing row, and J moves to the next undecided issue. If a row was removed another way (for example, another tab), focus goes to the next row, else to the Issues h2.
- **Triage progress.** In the Triage view the Issues header shows "Decided in this view: 3 of 13" as text plus a thin bar; it is not live, and decisions announce the new count in their own message.
- **Decision done.** After a decision the button reads "Confirmed" (or "Dismissed", "Risk accepted") and is `aria-disabled="true"`: it keeps focus but does nothing. A second Enter, Space or C says "Already confirmed. Use Undo to change it." Only the Undo button right after it reverses a decision.
- **Create Jira ticket (T).** Opens the Jira ticket section and moves focus to its h3. The first control after the h3 is "Copy ticket", then "Download for Jira (CSV)" and "Mark as ticketed"; the draft text follows them.
- **Bulk actions.** When one or more issues are selected, the bulk actions bar appears between the filter chips and the table (not at the bottom), so Tab reaches it right after the toolbar, and B jumps to it. It is a plain `section` of buttons, reached with Tab. Escape in the bar returns focus to the last focused row and never clears the selection; "Clear selection" is a button, and its message offers Undo. Escape inside the bulk Dismiss form closes only that form and keeps the selection.
- **Decide form.** Escape inside the form closes only the form, keeps the typed reason as a draft for next time, and returns focus to "Dismiss or accept risk". It never closes the panel.
- **Newer run.** When the URL pins an older run and a newer run exists, a notice sits under the report header: "A newer run exists: Run 5, Sep 25. Show Run 5." It is plain text with a link, not live.
- **Filter or view changes.** Focus stays on the control. The polite status region reports the new count.
- **Dialogs.** Focus moves to the dialog's h2, is trapped while the dialog is open, and returns to the opener on close.

## 7. Keyboard model

| Key | Where it works | Action |
|---|---|---|
| Tab, Shift+Tab | Everywhere | Move through controls in the order above |
| Enter, Space | Buttons, rows, sort headers | Activate; a row title opens details; a sort header cycles the sort |
| Arrow keys | View presets, pickers, menus | Move within the widget (radio group, listbox, menu) |
| Up and Down arrows | Issue table, when a row title has focus | Extra: move to the previous or next row title. Tab still visits every checkbox and title; the arrows are a shortcut, not a roving tab stop. |
| Escape | Panel, dialogs, menus | Close and return focus |
| J, K | Issue table and details panel only | Next and previous issue |
| X | Issue table only | Select or unselect the focused row |
| B | Issue table and details panel, when issues are selected | Move focus to the bulk actions bar |
| C, D, T | Details panel only | Confirm; open Dismiss or accept risk; create a Jira ticket draft |
| ? | Issue table and details panel | Open Keyboard shortcuts |

Single-key shortcuts (J, K, X, C, D, T, ?) meet 2.1.4 three ways:
- they work only when focus is inside the Issues region or the details panel, and never in a text field;
- Settings can turn them off;
- Settings can remap each one.

Help, Keyboard shortcuts lists them. The table's description tells screen reader users they exist.

**Screen readers.** In browse mode, NVDA and JAWS keep single letters for their own quick keys (for example C, D, T, X, K), so these shortcuts do not reach Axcess. That is expected and is said in the shortcuts dialog. Every shortcut has a button close by (after the details h2, the next Tab stop is Confirm; Previous, Next and Close sit above the h2, one Shift+Tab away), and Settings offers "Use Alt and Shift with shortcuts" (for example Alt+Shift+C), which passes through browse mode.

## 8. Live regions

| Region | Politeness | What it says | Chatty guard |
|---|---|---|---|
| Page status (`role="status"`) | polite | Result counts after a filter, view or search change ("Showing 6 issues"); decisions ("Confirmed. 3 of 13 decided."); bulk results ("Confirmed 3 issues. Undo is available."); copy ("Selector copied") | Search is debounced 600 ms. Repeat messages are merged. There is one region for the whole page. |
| Scan progress (`role="status"`) | polite | "Scan started", then at 25, 50 and 75 percent, then "Scan finished" or "Scan stopped" | The visible counter updates continuously but is not live. Only milestones are announced. |
| Errors (`role="alert"`) | assertive | Only when an action failed: "Your decision was not saved. Try again." | Never used for success |

## 9. Responsive behavior

| Width | Layout |
|---|---|
| 1440, 1280 | Top bar in one row. Report header in two rows. The strip is 8 tiles in one row at 1440 and two rows of 5 and 3 at 1280. Health and Progress are full width. **Split view:** the list is about 58% and the details panel about 42%; the panel is sticky and scrolls on its own. |
| 1024 to 1279 | Same as 1280, but the panel is 45% and the list drops the Instances column (it stays in the panel). |
| 768 | Single column. The strip is 2 rows of 4. The issue table becomes a list of issue cards (an `ol` of `article`s with the same data as label-value pairs). Details replace the list in place, with a "Back to issues" button at the top. |
| 320 (also 1280 at 400%) | The top bar is Home plus a "Menu" button that reveals the App picker, Help, Settings and Run scan. Pickers stack. Tiles are 2 per row. Chips wrap. Selectors and URLs wrap anywhere. Nothing is sticky. The instances table becomes numbered instance cards. |

Text spacing: no fixed heights and no truncation. Every label wraps. Tested against the 1.4.12 overrides in the annotations.

## 10. Task flows

The diagrams in FigJam show decision points. Keyboard only, no mouse.

### F1 Analyst triages a new scan (target: every issue in the Triage view with no page change; 13 in the sample run, and the same path scales to 20 or more)
1. Open the report. The Triage view is remembered in the URL or bookmark.
2. Use "Skip to issue list". Focus lands on the Issues h2; the table follows.
3. The first group is "Came back (1)". Press Enter on the row title. The panel opens and focus moves to its h2.
4. Read the summary, the Witness marks and "Since Run 3". Then decide:
   - **Real:** press C. The status becomes Confirmed and the page says "Confirmed. 1 of 13 decided."
   - **Not real:** press D. The Decide form opens inline with focus on the first choice, and the last reason is offered. Save, and the page says "Dismissed. Undo is available."
   - **Not sure:** open evidence. The instance screenshot, snippet and "Open the page" (new tab, announced) are all in the panel.
5. Press J for the next issue. Focus moves to the new title. Repeat.
6. For several similar issues, press X on each row, then use the bulk bar to Confirm them or draft tickets.
7. For confirmed issues, press T. The ticket draft opens in the panel, prefilled. Copy it or download CSV, then "Mark as ticketed" and enter the key.
8. The Issues header shows "Decided: 13 of 13". The Needs review tile reads 0.

### F2 Developer fixes one root cause
1. Open the deep link from the Jira ticket: `?app=museumcollab…&run=4&view=fix&issue=image-links-no-name`. The panel opens with focus on its h2.
2. Read What is wrong, then Who it affects.
3. Where it happens: Fix reach says "Likely 1 template: `.item.resource > a`, 19 pages". Select instance 1, then view its screenshot, HTML and steps to reproduce. Use Copy selector.
4. Suggested fixes: compare the 3 options and their trade-offs. The recommended option is marked, and the disclaimer is shown.
5. Done when: copy the acceptance criteria into the pull request.
6. After the deploy, choose Run scan (same settings). The next run shows "Gone in Run 5 on 19 of 19 pages. A person needs to confirm."
7. The analyst confirms, the status becomes Fixed, and the Done ledger credits the work.

### F3 Leader checks status (target: 10 seconds)
1. Open `/app/?view=overview`. The Overview preset expands Progress.
2. Read the h1 and the summary sentence: "2 critical issues are open. 1 issue came back since Run 3. Your team fixed 19 instances since Run 3. 6 issues need a person to review."
3. Scan the tiles for Blocker 0, Critical 2 (+1) and Came back 1.
4. Read Progress: the Done ledger and the trend. "Show as table" gives the numbers.
5. Check the health chip: "2 notes". Open it to see whether the counts can be trusted.
6. Optional: switch the App picker to All apps. The strip and the list then roll up by app, and each row names its app.

## 11. Every job, and its path on this page

| Job (research.md §4) | Path |
|---|---|
| Analyst 1: triage a new run | F1, steps 1 to 5 |
| Analyst 2: tickets in the ITS format | F1, step 7. Panel, then h3 Jira ticket. |
| Analyst 3: check what went away or came back | Came back tile, then the Came back group. Fixed tile, then instances "gone, needs a check". Confirm each one. |
| Developer 1: exact location | Panel, then Where it happens: numbered instances with URL, selector, element, screenshot and reveal steps |
| Developer 2: cause and fix | Panel, then What is wrong, Suggested fixes and Done when |
| Developer 3: did my fix work | Run picker set to the newest run, then the issue's "Since Run N" section (gone, still present, or came back) |
| Leader 1: current risk | Summary sentence, then the Blocker, Critical and Came back tiles |
| Leader 2: trend and credit | Progress zone: Done ledger, trend, table |
| Leader 3: trust the numbers | Health chip, then Scan health and coverage, and the count caveats |

## 12. URL state

`/app/?app=<host>&run=<id>&compare=<id|none>&view=<triage|fix|overview>&sev=<list>&status=<list>&trust=<list>&wcag=<list>&q=<text>&group=<key>&sort=<key>&issue=<root-cause-key>&instance=<n>`

- Back and Forward move between states that the user changed on purpose.
- Typing in search replaces the history entry instead of adding one.
- Opening details pushes one entry, so Back closes the panel.

## 13. Round 2 decisions (2026-09-23)
- **Status name.** The undecided status is shown as **"Not decided"** (stored as `new`). "New" is no longer a status label, because it clashed with "No change" and "First seen in Run 4" in the same row. Status labels: Not decided, Needs review, Confirmed, Ticketed, Fixed, Came back, Accepted risk, Dismissed.
- **One meaning for Confirm.** "Confirm" only means "this issue is real". Marking a gone issue as fixed uses **"Mark as fixed"**.
- **Counts.** The summary sentence repeats the tiles and nothing else: "15 issues are open, with 2,180 instances. 2 are critical, and 1 came back since Run 3. 6 need review by a person. Since Run 3, your team fixed 19 instances on 2 issues." The Issues header progress is scoped: "Decided in this view: 0 of 13". The Fixed tile says "instances fixed since Run 3" and "On 2 issues, all confirmed by a person".
- **Progress line.** One wording everywhere: "Since Run 3, your team fixed 19 instances. Since the first run, your team has resolved 212."
