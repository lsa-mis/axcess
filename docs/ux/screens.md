# Axcess UX refresh: screen compositions (04 Dashboard, 05 States)

Status: Phase 3 input, 2026-09-23. It composes components from [design-spec.md](design-spec.md) (§3) using the IA in [ia.md](ia.md) and the sample data in [research.md](research.md) §7.
All copy is plain language with no em dashes. Numbers match research.md §7.

## 1. Shared sample content

### 1.1 The 15 root causes (Run 4 of museumcollab.anthro.lsa.umich.edu, compared with Run 3)

| # | Severity | Title | WCAG | Instances | Checks (Witness) | Since Run 3 | Status | Fix reach |
|---|---|---|---|---|---|---|---|---|
| 1 | Critical | Poster text is only in an image | 1.1.1 A, 1.4.5 AA | 2 on 2 pages | AI only | First seen in Run 4 | Needs review | |
| 2 | Critical | Image links have no name | 2.4.4 A, 4.1.2 A | 143 on 19 pages | Person confirmed (2 rule checks + AI on 27) | 2 fixed | Confirmed | Likely 1 template: .item.resource > a |
| 3 | Major | Item descriptions get cut off when text is bigger or spaced out | 1.4.4 AA, 1.4.12 AA | 42 on 9 pages | One check (browser test) | No change | New | Likely 1 template: div.description |
| 4 | Major | Embedded videos make the page scroll sideways on phones | 1.4.10 AA | 8 on 8 pages | One check (browser test) | Came back | Came back | Likely 1 template: item media iframe |
| 5 | Major | Links are too small to tap easily | 2.5.8 AA | 220 on 58 pages | Checks agree on 100, one check on 120 | 17 fixed | Ticketed A11Y-214 | Likely 2 templates |
| 6 | Major | Banner text is part of an image | 1.4.5 AA | 1 image on 211 pages | AI only | No change | Needs review | |
| 7 | Major | Headings do not describe their section | 2.4.6 AA | 677 on 155 pages | AI only | No change | Needs review | |
| 8 | Major | Link text does not say where it goes | 2.4.4 A | 238 on 158 pages | AI only, Cannot tell on 17 | No change | Needs review | |
| 9 | Major | Search and page fields have vague labels | 3.3.2 A | 107 on 50 pages | AI only | No change | Needs review | Likely 2 templates |
| 10 | Major | Reading order on screen differs from the code | 1.3.2 A | 91 on 91 pages | AI only | No change | Needs review | |
| 11 | Minor | Footer credit text is too faint | 1.4.3 AA | 3 on 3 pages (count caveat: 2 are sign-in pages) | One check (rule) | First seen in Run 4 | New | |
| 12 | Minor | A heading is empty | 1.3.1 A | 1 on 1 page | Checks agree (2 rule) | No change | New | |
| 13 | Best practice | Pages have no main heading | none | 211 on 211 pages (count caveat: 5 pages counted twice) | One check | No change | New | Likely 1 template |
| 14 | Best practice | Heading levels skip | none | 170 on 170 pages | One check | No change | New | |
| 15 | Best practice | Navigation areas share the same name | none | 56 on 56 pages | One check | No change | New | |

### 1.2 Tiles, summary and header
Use the tiles, summary sentence and header text from design-spec §5 exactly, with Major showing "Up 1 since Run 3".

## 2. 04 Dashboard frames

| Frame | Size | Mode |
|---|---|---|
| Dashboard 1440 Light | 1440 wide, hug height | Light |
| Dashboard 1440 Dark | clone of 1440 Light | Dark |
| Dashboard 1280 Light / Dark | 1280 | Light / Dark |
| Dashboard 768 Light / Dark | 768 | Light / Dark |
| Dashboard 320 Light / Dark | 320 | Light / Dark |
| Dashboard 1440 Forced colors | clone of 1440 Light | High contrast (annotate: "Approximation of Windows High Contrast Black. Real forced-colors mode uses system colors.") |

**View:** Triage. **Filter:** Status is Came back, Needs review or New (13 of 15 issues). **Details panel:** open on issue #4 at 1440 and 1280; closed at 768 and 320, where the list shows.

### 2.1 1440 layout, top to bottom (side padding 40, content 1360)
1. **Top bar** (64 high, `bg/surface`, bottom `border/decorative`):
   - left: Axcess mark and wordmark, then the App picker (inline label "App", value "museumcollab.anthro.lsa.umich.edu");
   - right: Help (secondary), Settings (secondary), Run scan (primary, 52 high).
2. **Report header** (padding top 32):
   - h1.
   - Row: Run picker, Compare picker, the meta line, and the Health chip ("Scan health: 2 notes", flag icon).
   - Right-aligned in the same row: "View" plus the View presets (Triage selected).
3. **At a glance:**
   - h2 "At a glance", then the summary sentence (`body-lg`).
   - Tile row: 5 severity tiles, a 1 px divider with the label "Severity" above the first group and "Work" above the second, then 3 work tiles.
   - Tile width 158, gap 12. The Came back tile shows the band. The Critical tile shows "Up 1 since Run 3".
4. **Scan health and coverage:** disclosure, collapsed, state Notes. Summary: "214 pages checked with 9 kinds of checks. 2 notes may change the counts." Button text "Show details".
5. **Progress:** disclosure, collapsed. Summary: "Your team fixed 19 instances since Run 3, and has closed 212 since the first run." Button text "Show progress".
6. **Split row** (gap 24):
   - **Issues, 776 wide:**
     - h2 "Issues" plus a caption "13 of 15 issues shown".
     - Toolbar: the search field "Find an issue" (320), "Group by: Status" picker, "Sort: Severity" picker.
     - Chip row: "Filters" label, the chip "Status: Came back, Needs review, New", "Add filter" (ghost), "Clear all" (link style button).
     - Table header: Select all | Severity | Issue | Checks | Since Run 3 | Status. The Severity header shows "Sorted high to low".
     - Group "Came back (1)": row #4 with the band.
     - Group "Needs review (6)": rows 1, 6, 7, 8, 9, 10.
     - Group "New (6)": rows 3, 11, 12, 13, 14, 15.
     - The Issue cell holds 3 lines: title (label 16), then WCAG badges plus "143 on 19 pages" (body-sm), then the Fix reach or a count caveat when one applies.
     - Row #4 is in the "Open" state ("Showing in details").
     - Pagination text: "Showing all 13".
   - **Issue details, 560 wide:** a region with a card style and `bg/surface`.
     - Top row: "Previous issue", "Next issue", "Close details" (secondary buttons with text).
     - h2 "Embedded videos make the page scroll sideways on phones". Meta row: Major badge, Came back badge, 1.4.10 AA badge, Witness "One check".
     - Came-back band callout: "Fixed in Run 3, and a person confirmed it on Aug 29. Found again in Run 4 on 8 pages."
     - Actions: Confirm (primary), "Dismiss or accept risk…" (secondary), "Create Jira ticket" (secondary), "Copy selector" (ghost).
     - Sections h3:
       - **What is wrong:** "On screens 320 px wide, embedded videos stay 560 px wide. The page then scrolls sideways by 245 px."
       - **Who it affects:** "People who zoom in to 400% and people on small phones must scroll both ways to read each line."
       - **Checks that found it:** Witness expanded: "Browser test, reflow at 320 px: 8 of 8 pages". "Rule checks, axe and Alfa: no rule for this".
       - **Since Run 3:** "Came back on 8 pages. It was gone in Run 3 and a person confirmed the fix."
       - **Where it happens:** "Likely 1 template: the video frame in the item media block, 8 pages." Instances 1 to 3 (/s/Anishinaabe/page/rush, /s/Anishinaabe/page/Corn_basket, /s/Anishinaabe/page/cedar_mat_making; element "Video frame, 560 px wide"; selector `iframe`), then "Show all 8 instances". Instance 1 is selected, showing a screenshot placeholder (a 320 px phone outline with the video box running past the right edge, circled) with the caption "Screenshot of the rush page at 320 px wide. The video frame is circled." Below it: the HTML code block `<iframe allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope" width="560" height="315" …>`, and the steps "1. Open the rush page. 2. Make the window 320 px wide, or zoom to 400%. 3. Scroll to the video. 4. The page now scrolls sideways."
       - **Suggested fixes:** (Recommended) "Make the video frame fluid", How: "Set width to 100% and keep a 16 by 9 shape with aspect-ratio", Watch out: "Check that the player controls still show", Effort: Low. Option 2: "Wrap the frame in a responsive container", Watch out: "Adds markup to the item template", Effort: Low. Then the disclaimer.
       - **Done when:** "At 320 px wide, no item page scrolls sideways." "The video keeps its controls and its 16 by 9 shape." "The reflow check passes on all 8 pages."
       - **Jira ticket:** "Ticket A11Y-188 was closed after Run 3. Copy a note to reopen it, or make a new ticket." Buttons: "Copy reopen note", "Create Jira ticket".
       - **History:** "Aug 29, 2026: Marked fixed by R. Maharjan after Run 3." and "Sep 11, 2026: Came back in Run 4."
7. **Footer:** design-spec §5.

### 2.2 1280
Same content.
- Tiles in 2 rows: 5 severity tiles, then 3 work tiles.
- List 700 wide, panel 492 wide.
- The table drops no columns; the Issue cell wraps.

### 2.3 768
- **Top bar in 2 rows:** row 1 has Axcess on the left and Help, Settings, Run scan on the right; row 2 has the App picker at full width.
- **Header:** h1 wraps. The Run and Compare pickers sit side by side. The Health chip and View presets take one row each.
- **Tiles:** 2 rows of 4.
- **Health and Progress:** collapsed.
- **Issues** are a list of **issue cards**. Each card shows:
  - the severity badge and the status badge on top;
  - the title as a button;
  - WCAG, instances and pages;
  - Checks;
  - the Since line.

  The Came back card has the band.
- The details panel is closed. A note under the first card says "Opening an issue shows its details here, in place of the list."

### 2.4 320 (also represents 1280 at 400% zoom)
- **Top bar:** Axcess plus a "Menu" button with a menu icon and the word "Menu".
- **Header:**
  - The h1 wraps over 3 or more lines.
  - The pickers stack at full width.
  - The meta line wraps.
  - Then the Health chip, then View presets (3 options fit at 96 px each).
- **At a glance:** the summary sentence, then tiles 2 per row, each 138 wide.
- **Scan health and Progress:** collapsed.
- **Issues:**
  - The search field is full width.
  - Chips wrap.
  - Group by and Sort stack.
  - Issue cards follow.
  - Selectors wrap anywhere.
- **Footer** at the end.
- Nothing is sticky, and there is no horizontal scroll.
- Show at least the first 5 cards.

### 2.5 Overview view, 1440 (Light and Dark): the leader's page
Frames "Dashboard 1440 Overview Light" and "Dashboard 1440 Overview Dark".
- Same page as 2.1, but the View preset is Overview. The filter is none; the list is grouped by Severity with the columns Severity, Issue, Since Run 3, Status; the details panel is closed, so the list is full width.
- **Progress** is expanded:
  - Text summary first: "Your team has closed 212 instances since the first run, and 19 since Run 3."
  - **Done ledger** rows, newest first:
    - Run 4 (Sep 11): 19 fixed, 0 dismissed, 0 accepted risk
    - Run 3 (Aug 28): 64 fixed, 12 dismissed, 1 accepted risk
    - Run 2 (Aug 14): 101 fixed, 15 dismissed, 0 accepted risk
    - Run 1 (Jul 31): first run, nothing to credit yet
  - Beside it, a small **trend** chart, "Open issues by severity, last 4 runs". Lines with shape markers and direct labels at the line ends, no legend lookup:
    - Critical 1, 1, 1, 2
    - Major 9, 8, 7, 8
    - Minor 2, 1, 1, 2
    - Best practice 3, 3, 3, 3
    - Blocker 1, 0, 0, 0
  - Under the chart, the text "Open critical issues went from 1 to 2 since Run 3. One blocker was fixed in Run 2." and a "Show as table" button.
  - Also show the table state next to the chart: a table with caption "Open issues by severity, last 4 runs", columns Run 1 to Run 4, and a row per severity.
- **Scan health** stays collapsed, with its summary line and the "2 notes" state.
- Mark "Illustrative numbers" in a small caption on the frame label, not in the UI.

## 3. 05 States frames (each in Light and Dark; the Dark frame is a clone with mode Dark)

Frames 1 to 8 are required by the brief. Frames 9 to 11 support the accessibility bar.

1. **Empty, first scan** (1440):
   - App picker value "app.example.lsa (new app)". Mark this as illustrative. h1 "Accessibility report: app.example.lsa".
   - Empty state card: heading "No scans yet for this app". Text "Run a scan to check up to 2,500 pages. Most scans take 10 minutes to 2 hours. You can keep using Axcess while it runs." Primary "Run first scan"; link "What Axcess checks".
   - Each zone still shows its h2 with one line: "Counts show here after the first scan." "Health shows here after the first scan." "Progress shows here after two scans."
2. **Scanning in progress** (1440):
   - The Run picker shows "Run 5 · Scanning now".
   - A progress card sits under the header: h2 "Scan in progress". "Checking pages: 132 of about 214. Now running: rule checks (axe and Alfa). About 35 minutes left." A determinate bar at 62% with its value in text. Buttons "Stop scan" (secondary) and "Keep working" (ghost).
   - Annotation: "Screen readers hear only: started, 25%, 50%, 75%, finished."
   - Below it, the page keeps showing Run 4, with the note "You are seeing Run 4. Run 5 results will show when the scan finishes."
3. **Scan failed on sign-in** (1440). The app "rooms.example.lsa (sign-in app)" is illustrative.
   - The Health chip reads "Scan health: Sign-in failed" (Blocker-style filled chip with an octagon).
   - Scan health and coverage is **expanded automatically**. A Failed item says: "Sign-in did not reach the app. All 3 pages checked were the sign-in page. Axcess did not try to sign in again, and it never saw your password."
   - Buttons: "Start a new sign-in scan" (primary), "What can cause this" (link).
   - Other items: "Pages: 3 checked, 0 inside the app". "Checks ran, but only on the sign-in page".
   - At a glance: the summary "No results for this run. The scan could not get past sign-in." Tiles show "Not available", never 0.
   - Issues empty state: "No results about the app. The 3 pages checked were sign-in pages, so their results are hidden. Show sign-in page results".
4. **Zero issues** (1440). The app is lsa-mis.github.io/axcess, Run 3 (illustrative).
   - Summary: "No issues found by automated checks in Run 3. Your team closed 64 instances to get here."
   - A calm success card with a check-in-square icon: "Nothing for automated checks to report. 26 of 55 WCAG criteria still need a person to check. Plan the manual checks". No confetti and no animation.
   - Tiles all read 0, with "Down 3 since Run 2" and similar.
   - Progress is expanded with the Done ledger.
5. **Large result set** (1440). Scope: All apps, 512 root causes across 6 apps.
   - Summary: "512 issues across 6 apps. 3 blockers are open, in 2 apps."
   - Tiles with larger counts: Blocker 3, Critical 41, Major 268, Minor 122, Best practice 78, Needs review 190, Came back 7, Fixed 1,204.
   - The table adds an App column. Group by Severity, with the Blocker group expanded, Critical expanded, and the others collapsed with counts.
   - Pagination: "Showing 1 to 50 of 512 issues", Previous, Next, "Issues per page: 50".
   - A tip under the toolbar: "Tip: filter by app or status to narrow the list."
6. **Details panel open, Fix view** (1440):
   - View preset Fix. Filter: Status is Came back, Confirmed or Ticketed. Columns: Severity, Issue, Fix reach, Pages, Ticket, Status.
   - The panel shows issue #2 in full: every section from design-spec §5, including the instances table (3 rows plus "Show all 143"), an expanded screenshot for instance 1, the HTML code block with "Copied" state, the three fix options, Done when, and the Jira ticket draft expanded (Summary, Current Behavior, Steps to Reproduce, Impact, Expected Behavior, Suggested Fix with disclaimer, References, the Instances table), then History.
7. **Bulk selection** (1440):
   - Triage view. Rows 13, 14 and 15 are Selected.
   - The bulk bar sits at the bottom of the Issues region: "3 issues selected" plus Confirm, "Dismiss or accept risk…", "Create Jira tickets", "Clear selection".
   - A status message under the bar: "3 issues selected. Actions apply to all 3."
   - Annotation: "The list keeps 88 px of bottom scroll padding so the bar never covers a focused row."
8. **Keyboard focus on every interactive type** (a 1440 board, not a full page). A grid showing the Focus state of:
   - skip link, top bar button, App picker, Run picker, View preset option, stat tile;
   - disclosure header, search field, chip remove, checkbox, sort header, issue row title;
   - pagination button, panel Close, action button, Copy button, instance row, text link;
   - radio, textarea, dialog Close, Menu button.

   Each item has a caption naming the element and "3 px ring, 2 px gap".
9. **Details at 320** (320): the details replace the list. "Back to issues" button at the top. The issue #2 panel content stacks. The instances table becomes numbered instance cards. The selector wraps. The screenshot is full width.
10. **Access screen** (1440, hosted mode):
    - Centered card: h1 "Sign in to Axcess". Text: "This copy of Axcess is shared on your network. Enter the access code your admin gave you."
    - A labeled field "Access code" (password type, with a "Show code" toggle button). Hint: "You can paste the code or let your password manager fill it."
    - Primary "Sign in". Link: "I do not have a code".
    - No CAPTCHA, no time limit. Help stays in the same top-bar place.
    - Error variant: "That code did not work. Check it and try again."
11. **Keyboard shortcuts dialog** (1440, over the dashboard with a dim overlay):
    - h2 "Keyboard shortcuts".
    - A switch "Single-key shortcuts: On".
    - A table: Key | Action | Where it works | Change key (button per row). Rows: J, K, X, C, D, T, ?.
    - The note "Shortcuts only work when you are in the issue list or the details, never in a text field."
    - "Close" button.

## 4. Round 1 rework (gauntlet fixes R1-01 to R1-21)

Apply to every affected frame, Light and Dark:
- **Header:** add "Evidence to review, not proof of compliance." under the h1. Add an "Export" secondary button (menu) at the end of the Run row. Top bar uses the real Axcess brand mark (open scan ring, node, rounded a).
- **Summary and tiles:** use the round 1 words in design-spec §5.
- **Issues header (Triage):** "13 of 15 issues shown" plus the link "What these words mean", and "Decided: 0 of 13" with a thin bar.
- **Rows:** Witness marks follow the one-mark-per-check rule, with the phrase "AI only" in place of "AI lead". Best practice rows say "No WCAG rule (best practice)". Zebra banding: odd rows use bg/page. In full-width lists the table is at most 1100 wide.
- **Details panel:**
  - WCAG badges carry the SC name.
  - Instance "Screenshot" and "HTML" become secondary buttons: "Show screenshot" or "Hide screenshot", with a chevron.
  - Each instance shows "Still present" or "Gone, needs a check".
  - New h3 "References" before History, with links:
    - Understanding 2.4.4 Link Purpose (In Context)
    - Understanding 4.1.2 Name, Role, Value
    - axe rule link-name
    - Alfa rule R11
  - Screenshot alt text is different from its caption. Alt: "Rush page at 320 px wide. The video frame runs past the right edge of the screen." Caption: "Instance 1, captured Sep 11, 2026." The drawn screenshot must show the rush page.
  - The confirmed state shows "Confirmed" plus an "Undo" button.
- **S2:** the Run picker says "Run 4 · Sep 11, 2026", with a separate chip beside it: "Run 5 scanning: 62%". "Stop scan" shows a confirmation: "Stop the scan? Results so far are kept." with "Stop scan" and "Keep scanning".
- **S5:**
  - First, a "By app" table: App, Blocker, Critical, Came back, Needs review, Last run, Health. It has 6 rows, and 2 apps have blockers.
  - The summary names the two apps.
  - Progress is expanded.
- **New frame "State 12 Triage in progress" (1440, Light and Dark):**
  - Triage view, "Decided: 3 of 13" in the Issues header.
  - Rows #4 and #1 are marked "Confirmed just now", and row #6 "Dismissed just now". The rows stay in place, and a "Refresh list" button appears.
  - The details panel is open on AI-only issue #7, "Headings do not describe their section".
  - The Checks table: "AI review, heading text: flagged 677". A related note (not an agreeing check): "axe heading-order also flags 122 of these headings, for a different reason (levels skip)."
  - A "What the AI saw" block for instance 1 (/s/Anishinaabe/item/117, `<h4> Title </h4>`): "Reason: The heading says only 'Title' and does not describe the content under it. Suggested heading: 'Item details'".
  - A "What the AI cannot see" line: "It reads text only. It does not see images or how the page looks."
  - A "Why this might be wrong" line: "Some headings are short on purpose, like 'Title' in a label and value list. If the heading labels a value, it can be fine."
  - An "Open the page" link.
  - A status message: "Dismissed. 3 of 13 decided. Undo".
- **New frame "State 13 Gone after rescan" (panel only, 560 wide, Light and Dark):**
  - Issue #2 in Run 5, with the banner "Gone in Run 5 on 19 of 19 pages. A person needs to confirm it is fixed."
  - A primary button "Confirm fixed".
  - Instances marked "Gone, needs a check".
  - The notice "You are looking at Run 5. The ticket linked Run 4."
- **New frame "Instance variants" on page 03:** XPath location (Alfa only) and Image instance, as in r1 fix R1-10.

### 4.1 Witness variant per row (round 1 rule: one mark per check that saw it)

| Issue # | Witness variant |
|---|---|
| 1, 6, 7, 8, 9, 10 | AI only |
| 2 | Person confirmed |
| 3, 4 | One check, browser |
| 5, 12 | Checks agree, 2 rule |
| 11, 13, 14, 15 | One check, rule |

Also in the Since column:
- "Came back" (row 4)
- "First seen in Run 4" (rows 1 and 11)
- "2 fixed, confirmed by a person" (row 2)
- "17 fixed, confirmed by a person" (row 5)
- "No change" (all others)

## Scope change (2026-09-23, requested by the user)
From round 2 on, only the desktop design (1440) is updated and critiqued. This covers "Dashboard 1440 Light, Dark, Forced colors", "Dashboard 1440 Overview Light and Dark", the 1440-wide states and the State 13 panel. The 1280, 768 and 320 frames, "State 9 Details at 320" and "Page annotations 320" stay as they were after round 1, each with a caption saying so. The reflow and zoom rules in ia.md §9 and a11y-annotations.md §1 still apply to the build. They are just not re-drawn.
