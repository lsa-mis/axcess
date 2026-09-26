# Axcess UX refresh: accessibility annotations (build from this page)

Status: Phase 3, 2026-09-23. This file is the source for Figma page "06 A11y Annotations".
Focus order numbers refer to ia.md §6. Heading outline and landmarks: ia.md §5. Live regions: ia.md §8. Keyboard: ia.md §7.
Rule of thumb: use native HTML first (`button`, `a`, `input`, `select`, `table`, `details` only where noted). ARIA fills the gaps.

## 1. Page level

| Topic | Annotation |
|---|---|
| Title | `<title>`: "Run 4, museumcollab.anthro.lsa.umich.edu, Axcess". Update it when the run, app or open issue changes; for example, append "Image links have no name" while details are open. |
| Language | `<html lang="en">`. Selectors and HTML snippets use `translate="no"`. |
| Landmarks | `header` (banner); `main`; each zone is a `section` with `aria-labelledby` pointing at its h2 (these are regions); `footer` (contentinfo). There is no `nav` landmark on the report page: the pickers are form controls, not site navigation. The pagination is `nav aria-label="Issue pages"`. |
| Headings | One h1 in the report header. h2 per zone. The details h2 is the issue title. h3 per details section. Dialog titles are h2 inside the dialog. |
| Skip links | The first two focusable elements: "Skip to issue list" (targets the Issues h2, `tabindex="-1"`) and "Skip to issue details" (rendered only while details are open). Visible on focus, 44 px high. |
| Focus ring | A 3 px `focus/ring` outline with a 2 px offset on every focusable element, using `outline` (never `box-shadow`), so forced colors keep it. Scroll containers have 6 px inner padding so rings are never clipped. |
| Not obscured | Nothing is sticky below 1024 px. At 1024 px and wider, the details panel is `position: sticky; top: 0` inside the split row only. The bulk bar sits in normal flow at the end of the Issues region; when it is sticky, the list gets `scroll-padding-bottom: 88px`. The page gets `scroll-padding-top: 16px`. |
| Reduced motion | `@media (prefers-reduced-motion: reduce)` removes the panel slide and disclosure transitions. Nothing else animates. |
| Color scheme | Follows `prefers-color-scheme` unless Settings > Theme overrides it. `color-scheme: light dark`. |
| Forced colors | Under `@media (forced-colors: active)`: every chip, tile, input and button keeps a 1 px border (`CanvasText`); pressed and selected states add the 4 px bar using `Highlight` plus a check icon and text; the focus ring uses `Highlight`; the came-back band stripes use `CanvasText`; chart marks use `CanvasText` with distinct shapes and dash patterns. No information is carried by background color alone. |
| Text spacing | No fixed heights anywhere and no `text-overflow: ellipsis`. Selectors, URLs and HTML use `overflow-wrap: anywhere`. Tiles and chips grow in height. Verified by applying 1.5 line height, 2× paragraph spacing, 0.12 em letter spacing and 0.16 em word spacing to every frame. |
| Reflow | 320 px CSS width with no horizontal scroll, except inside the instance HTML code block, which is a named, focusable scroll region that also offers "Wrap lines" (on by default). |
| Time | No time limits. Scan progress never auto-advances the page. Status messages stay in place until the next action; they are not toasts that vanish. |
| Consistent help | Help sits in the top bar at the same position in every state and on the Access screen, and the footer repeats "Help and contact". |

## 2. Components

| # | Component | Element and role | Accessible name (visible label is included, 2.5.3) | Keyboard | State, value, live region | Reflow and spacing |
|---|---|---|---|---|---|---|
| 0 | Every standalone text button and table link | `button` or `a` | | | | 44 px hit area through padding (`inline-flex; min-height: 44px`) even when drawn as text |
| 1 | Skip link | `a href="#issues-heading"` | "Skip to issue list" | Tab, Enter | Hidden until focused (no `display:none`) | Wraps |
| 2 | Axcess home | `a` | "Axcess home" (visible wordmark "Axcess" plus a hidden word) | Tab, Enter | | |
| 3 | App picker | `button aria-haspopup="listbox" aria-expanded`, then `ul role="listbox"` with `li role="option" aria-selected` | "App: museumcollab.anthro.lsa.umich.edu" | Enter or Space opens; Up and Down move; Enter selects; Escape closes and returns focus; type-ahead | Changing the app updates the URL and the page title. Polite: "Showing museumcollab…, Run 4." | At 320 it is inside Menu; the option text wraps. |
| 4 | Help | `button aria-haspopup="menu"` then `role="menu"` with `menuitem`s | "Help" | Enter opens; arrows move; Escape closes | | Inside Menu at 320 |
| 5 | Settings | `button` that opens a modal dialog | "Settings" | Enter | The dialog is `role="dialog" aria-modal="true" aria-labelledby`; focus goes to its h2 and returns to the button | |
| 6 | Run scan | `button` that opens a modal dialog | "Run scan" | Enter | The dialog is prefilled with Run 4 settings (3.3.7) | |
| 7 | Run and Compare pickers | Native `select` with a visible `label`, or the same listbox pattern as App | "Run", "Compare to" | Native | Change updates tiles and deltas. Polite: "Comparing Run 4 with Run 3." | Stack at 320 |
| 8 | Scan health chip | `button aria-controls="health" aria-expanded` | "Scan health: 2 notes" | Enter toggles and moves focus to the Health h2 | When a scan failed, the chip reads "Scan health: Sign-in failed" and the health section starts expanded | |
| 9 | View presets | `div role="radiogroup" aria-labelledby="view-label"` with 3 `role="radio"` (or native radio inputs styled as segments) | "View", options "Triage", "Fix", "Overview" | One tab stop; Left and Right arrows move and select; roving tabindex | Polite: "Triage view. Showing 13 of 15 issues." | 3 segments at 96 px each at 320 |
| 10 | Summary sentence | `p` directly under the At a glance h2 | | | Not live. It is the text equivalent of the strip. | Wraps |
| 11 | Stat tile | `button aria-pressed` | "Critical, 2 issues, up 1 since Run 3" (starts with the visible word "Critical") | Tab, Enter or Space toggles the filter | Pressed shows a bar, a check and "Filter on". Polite: "Filter on: Critical. Showing 2 issues." | 2 per row at 320; the height grows |
| 12 | Count caveat | `button` placed after the number | "Note about this count" | Enter opens Health and moves focus to that note | | |
| 13 | Disclosure (Health, Progress) | An h2 containing a `button aria-expanded aria-controls` (not `details`, so the h2 stays in the outline) | The h2 text, "Scan health and coverage" | Enter or Space | Expanded state is announced by the button | The summary line wraps |
| 14 | Done ledger | A `table` with caption "Work done per run" (columns: Run, Fixed, Dismissed, Accepted risk), shown as bars through CSS; each bar segment prints its count as text | | Not focusable except "Show as table" | | The bars stack under the text at 320 |
| 15 | Trend chart | An SVG with `role="img"` and `aria-labelledby` pointing at its visible text summary, plus a "Show as table" `button aria-expanded` that reveals a real `table` with a caption | "Open issues by severity, last 4 runs" | Enter toggles | | The chart becomes the table at 320 by default |
| 16 | Find an issue | `input type="search"` with a visible `label` | "Find an issue" | Standard | Debounced 600 ms. Polite: "Showing 3 issues." | Full width at 320 |
| 17 | Filter chip | A group: the text, then `button` | Button name "Remove filter: Status is Came back, Needs review, New" | Tab to the remove button; Enter removes, and focus moves to the next chip or to "Add filter" | Polite: "Filter removed. Showing 15 issues." | Chips wrap |
| 18 | Add filter | `button aria-haspopup="menu"`; the menu holds checkbox items per value | "Add filter" | Menu keys | | |
| 19 | Issue table | `table` with a caption, e.g. "Issues in Run 4, grouped by status, sorted by severity. 3 filters on." Groups are `tbody` elements with a first row `th scope="rowgroup" colspan`. Columns use `th scope="col"`. Each row's title is the row header (`th scope="row"`). | | Tab reaches Select all, the sortable headers, then per row the checkbox and the title button. Up and Down also move between row titles as an extra; Tab still visits every checkbox and title (explained in `aria-describedby`: "Press Enter to open an issue. Press question mark for shortcuts.") | `aria-sort` on the sorted `th`. A sort change is also announced politely. | Below 768 the table becomes an `ol` of issue cards (#30) |
| 20 | Sort header | `th aria-sort` containing a `button` | "Severity, sorted high to low" | Enter or Space cycles | | |
| 21 | Group row button | `button aria-expanded` inside the rowgroup `th` | "Came back, 1 issue" | Enter toggles | | |
| 22 | Row checkbox | `input type="checkbox"`, 44 px hit area through the label | "Select Image links have no name" | Space; X when shortcuts are on | The bulk bar appears. Polite: "1 issue selected." | |
| 23 | Row title | `button aria-controls="details" aria-expanded` (row header) | The issue title | Enter opens details and moves focus to the details h2 | The open row shows "Showing in details" as text plus a bar. `aria-current="true"` on the row. | Wraps to 3 lines |
| 24 | Witness marks | `span` containing hidden SVG shapes and a visible phrase | Text only: "Checks agree" plus hidden "2 rule checks and AI review" | Not focusable | | |
| 25 | Severity, status, WCAG badges | `span` with icon (`aria-hidden`) and a word | Text: "Critical", "Came back", "2.4.4, Level A" | Not focusable | | Wraps |
| 26 | Delta | `span` | "Up 1 since Run 3" (arrow `aria-hidden`) | | | |
| 27 | Came-back band | Decorative `::before` stripes. The meaning is in the "Came back" status text and the line "Fixed in Run 3. Found again in Run 4 on 8 pages." | | | | |
| 28 | Pagination | `nav aria-label="Issue pages"`; the range text is `role="status"` | "Previous page", "Next page", "Issues per page" | Tab | Polite: "Showing 26 to 50 of 512 issues" | Stacks at 320 |
| 29 | Bulk bar | `section aria-label="Bulk actions"` at the end of the Issues region | "3 issues selected" is visible text | Tab | Result, polite: "Confirmed 3 issues. Undo is available." Undo is a `button` in the message. | Buttons wrap to 2 rows at 768 and stack at 320 |
| 30 | Issue card (below 768) | `li` containing `article`, with the title as an h3 holding a `button` | The title | Tab to the checkbox and the title button | | Label-value pairs as a `dl` |
| 31 | Details region | `section id="details" aria-labelledby` pointing at the issue h2 | The issue title | Escape closes and returns focus to the row title. J and K work here. | Opening moves focus to the h2 (`tabindex="-1"`). Below 1024 px the list is hidden (`hidden`) and "Back to issues" appears first. | In place of the list below 1024 px |
| 32 | Previous, Next, Close | `button`s with text | "Previous issue", "Next issue", "Close details" | Enter; J, K, Escape | Next and Previous move focus to the new h2 | Wrap |
| 33 | Confirm | `button` | "Confirm" (becomes "Confirmed" plus an "Undo" button) | Enter; C | Polite: "Confirmed. 1 of 13 decided." Focus stays on the button, and an Undo button follows it. | |
| 34 | Dismiss or accept risk | `button aria-expanded` revealing an inline form: a `fieldset` whose `legend` is "Why?"; radios "Not a real problem (false positive)", "Real, but we accept the risk"; a required `textarea` "Reason", prefilled with the last reason as a suggestion the user can edit; Save; Cancel | "Dismiss or accept risk" | Enter; D. Focus moves to the first radio. | Errors: text under the field plus `aria-describedby` and `aria-invalid`; a missing reason says "Add a reason so others know why." Escape closes only the form, keeps the draft and returns focus to the button. Polite on save: "Dismissed. 3 of 13 decided. Undo is available." | Stacks |
| 35 | Create Jira ticket | `button aria-expanded` that opens the Jira ticket section and moves focus to its h3 | "Create Jira ticket" | Enter; T | The draft is plain text in labeled read-only fields, plus "Copy ticket", "Download for Jira (CSV)" and "Mark as ticketed" (an inline field "Ticket key"). Sending to Jira, if it is connected, asks for confirmation first. | |
| 36 | Copy selector, Copy HTML, Copy ticket | `button` | "Copy selector for instance 1" | Enter | The button text changes to "Copied" for 5 s, and a polite "Selector copied" | |
| 37 | Instances | `table` with caption "Where it happens: 143 instances. Showing 1 to 3." Columns: #, Page, Element, Selector, Evidence. Rows group under a `th scope="rowgroup"` per likely template. | | The Page cell is a link to the live page; it opens in a new tab and says so in its name ("…, opens in new tab"). Screenshot and HTML are `button aria-expanded`. | Selecting an instance reveals its evidence right below the row | Instance cards at 320 |
| 38 | Screenshot | `figure` with `img alt` and a `figcaption` | Alt describes what is in the image and differs from the caption. Alt: "Rush page at 320 px wide. The video frame runs past the right edge of the screen." Caption: "Instance 1, captured Sep 11, 2026." | "View full size" is a button that opens the image in a modal dialog | | Full width |
| 39 | Code block | `pre` inside a `div role="region" tabindex="0" aria-label="HTML for instance 1"` | | Arrow keys scroll when not wrapped | | Wraps by default |
| 40 | Fix options | An `ol` of `article`s with an h4 each; the recommended one has the text "Recommended" | | | | Stack |
| 41 | Done when | A `ul` of plain statements, plus a "Copy criteria" button | | | | |
| 42 | History | An `ol`, newest first, with `time` elements | | | | |
| 43 | Status message | Inline text under the triggering control; the same text goes to the page `role="status"` region | | | Polite. Errors use `role="alert"`. | Wraps |
| 44 | Scan progress | `progress max="214" value="132"` with a visible label "Checking pages: 132 of about 214"; a separate `role="status"` region for milestones only | "Scan progress" | "Stop scan" button | Announces started, 25%, 50%, 75%, finished or stopped | The bar stacks under the text |
| 45 | Empty states | An h2 or h3 per the zone, one sentence, one primary action | | | | |
| 46 | Keyboard shortcuts dialog | `role="dialog" aria-modal="true"`; the switch is `button role="switch" aria-checked`; the table has the caption "Single-key shortcuts" | "Keyboard shortcuts" | Tab trapped; Escape closes; "Change key" captures the next key and confirms it | Polite: "J is now N." | Table stacks at 320 |
| 47 | Access screen | `main` > `form` > `label` "Access code" + `input type="password" autocomplete="current-password"` + `button type="button" aria-pressed` "Show code" + `button type="submit"` "Sign in" | | Standard; Enter submits | Error: `role="alert"` text above the field plus `aria-invalid`; focus goes to the field. No CAPTCHA, no timeout, paste allowed. | Single column |
| 48 | Menu (320) | `button aria-expanded aria-controls` showing the word "Menu" | "Menu" | Enter toggles; focus moves to the first item | | |
| 49 | Footer | `footer` with the text and a "Help and contact" link | | | | Wraps |

## 3. Announcement script (what a screen reader user hears, in order)

These are the key moments in flow F1.
1. The page loads: "Run 4, museumcollab.anthro.lsa.umich.edu, Axcess". The h1 is first in the reading order after the banner.
2. Skip to issue list: "Issues, heading level 2".
3. Tab into the table: "Issues in Run 4, grouped by status, sorted by severity. 3 filters on. Table. Came back, 1 issue, button, expanded. Select Embedded videos make…, checkbox, not checked. Embedded videos make the page scroll sideways on phones, button, collapsed."
4. Enter: "Embedded videos make the page scroll sideways on phones, heading level 2."
5. C (in focus mode, or Alt+Shift+C in browse mode): "Confirmed. 1 of 13 decided."
6. J: "Poster text is only in an image, heading level 2."
7. D: "Why? grouping. Not a real problem (false positive), radio button, not checked, 1 of 2."
8. Save: "Dismissed. Undo is available."

## 4. Round 1 notes
- Single-key shortcuts do not reach Axcess while a screen reader is in browse mode; this is expected. Each has a button one to four Tabs away, and Settings offers Alt+Shift variants that pass through browse mode (ia.md §7).
- Decided rows stay in place until "Refresh list", so focus return targets always exist (ia.md §6).
- Triage progress "Decided: 3 of 13" is plain text; the decision message carries the count.

## 5. Round 2 notes
- #29 Bulk bar: a `section aria-label="Bulk actions"` placed between the filter chips and the table while issues are selected. Buttons are reached with Tab; B jumps to the bar. Escape returns focus to the last focused row and never clears the selection. "Clear selection" says "Selection cleared. Undo".
- #33 Confirm: after a decision the button reads "Confirmed" with `aria-disabled="true"` (still focusable, no action). A second Enter, Space or C says "Already confirmed. Use Undo to change it." Undo is the only reversal.
- #35 Create Jira ticket: focus moves to the Jira ticket h3; the next Tab stop is "Copy ticket".
- Status label "Not decided" replaces "New" everywhere in the UI (stored value `new`).
