# Axcess UX refresh: design spec (tokens, components, patterns, copy)

Status: Phase 3 input, 2026-09-23. It extends the current Axcess visual language (research.md §3): U-M Blue and Maize, Atkinson Hyperlegible, 8 px radius, 4 px spacing, 44 px targets, soft blue-tinted shadows, neutral status chips and tinted severity chips.
Every change to the current design has an accessibility reason and is logged in §7. Figma file: https://www.figma.com/design/rLrpOJZ73V1qXS4qzy5t3p

Ratios below were computed with the WCAG relative-luminance formula.

## 1. Tokens

### 1.1 Color: one collection, "Axcess color", 3 modes

The High contrast mode approximates Windows High Contrast Black.

| Variable | Light | Dark | High contrast | Use | Worst ratio |
|---|---|---|---|---|---|
| `bg/page` | #F7F9FC | #0B1622 | #000000 | page background | |
| `bg/surface` | #FFFFFF | #111F2E | #000000 | cards, table, panel, top bar | |
| `bg/muted` | #F1F4F8 | #182939 | #000000 | table head, hover, disclosure open | |
| `bg/selected` | #EBF1F8 | #1B3350 | #000000 | selected row, pressed tile (always with a bar and a check icon) | |
| `fg/default` | #111827 | #F3F6FA | #FFFFFF | body text | L 15.03, D 11.84 |
| `fg/muted` | #374151 | #D3DCE6 | #FFFFFF | secondary text | L 9.34, D 12.03 |
| `fg/subtle` | #424C5C | #B4C2D1 | #FFFFFF | captions, table head text | L 7.63 (on selected), D 7.08 |
| `fg/link` | #00274C | #9CC7F2 | #FFFF00 | links (always underlined) | L 12.76, D 9.42 |
| `fg/on-primary` | #FFFFFF | #0B1622 | #FFFFFF | text on a primary button | L 15.06, D 10.30 |
| `action/primary` | #00274C | #9CC7F2 | #000000 | primary button fill (HC gets a 2 px white border) | |
| `action/primary-hover` | #003A6C | #BFDBF7 | #000000 | hover | L 11.53 white |
| `border/decorative` | #DCE3EC | #243447 | #FFFFFF | dividers, card edges (not needed to identify a control) | |
| `border/control` | #6F86A2 | #6B7F95 | #FFFFFF | inputs, checkboxes, secondary buttons, chips, tiles | L 3.29 (on selected), 3.39 (on muted), D 3.11 (on selected) |
| `focus/ring` | #00274C | #FFCB05 | #1AEBFF | 3 px outline, 2 px offset | L 14.28, D 10.96, HC 14.37 |
| `selected/bar` | #00274C | #9CC7F2 | #1AEBFF | 4 px bar on selected or pressed items | L 12.76, D 7.25 |
| `sev/blocker-fg` / `-bg` | #FFFFFF / #7A0000 | #3A1212 / #FFB3B3 | #FFFFFF / #000000 | Blocker chip, filled | L 11.49, D 9.69 |
| `sev/critical-fg` / `-bg` | #7A0000 / #FEE2E2 | #FFB3B3 / #3A1212 | #FFFFFF / #000000 | Critical chip, tinted | 9.41 / 9.69 |
| `sev/major-fg` / `-bg` | #6B2E00 / #FFEBC7 | #FFC98A / #3A2208 | #FFFFFF / #000000 | | 8.91 / 9.89 |
| `sev/minor-fg` / `-bg` | #4F4200 / #FEF9C3 | #EBDB6E / #2E2A08 | #FFFFFF / #000000 | | 9.26 / 10.26 |
| `sev/bp-fg` / `-bg` | #1F2937 / #E5E7EB | #E5E7EB / #243244 | #FFFFFF / #000000 | Best practice | 11.86 / 10.50 |
| `success/fg` / `-bg` | #0F5132 / #E2F2E8 | #9EE0B4 / #0F2A1C | #3FF23F / #000000 | Fixed credit, Done ledger | 8.07 / 10.07 |
| `comeback/band` | #FFCB05 | #FFCB05 | #FFFFFF | Came-back band base (Maize) | |
| `comeback/stripe` | #111827 | #0B1622 | #000000 | diagonal stripes on the band | 11.65 on Maize |
| `wcag/a` `aa` `aaa` `bp` | #A40059, #4B1D8A, #275580, #4A4A4A | same fills | #000000 (+ white border) | conformance badge fill, white text | 7.71 minimum |

The existing brand token `umich.blue` (#00274C) maps to `action/primary` and `focus/ring` (Light). `umich.maize` maps to `focus/ring` (Dark) and `comeback/band`.

### 1.2 Type: Atkinson Hyperlegible Next (sans) and Atkinson Hyperlegible Mono (code)

The scale is the existing one. The mock uses nothing below 13 px.

| Style | Size / line height | Weight | Letter spacing | Use |
|---|---|---|---|---|
| `h1` | 28 / 36 | 600 | -2.5% | the page h1 (once) |
| `h2` | 20 / 28 | 600 | 0 | zone headings, panel title |
| `h3` | 16 / 24 | 600 | 0 | panel sections |
| `body` | 16 / 24 | 400 | 0 | prose, summary sentence (summary uses 18 / 28) |
| `body-sm` | 14 / 20 | 400 | 0 | table cells, secondary text |
| `label` | 14 / 20 | 600 | 0 | buttons, chips, tile labels, table head |
| `caption` | 13 / 20 | 400 | 0 | deltas, hints, timestamps |
| `count` | 32 / 36 | 600 | -2.5% | tile numbers |
| `mono` | 14 / 20 | 400 | 0 | selectors, HTML (wraps anywhere) |
| `mono-sm` | 13 / 20 | 600 | 0 | key caps |

### 1.3 Other tokens
- **Spacing:** 4, 8, 12, 16, 20, 24, 32, 40, 48, 64.
- **Radius:** `r-chip` 5, `r-control` 8, `r-dialog` 12, `r-pill` 999.
- **Focus:** a 3 px `focus/ring` outline with a 2 px offset, drawn as an outline and not a box-shadow, so forced colors keep it. The ring must never be clipped; scroll regions get 6 px inner padding.
- **Target:** 44 × 44 minimum for every interactive element, including chip remove buttons and checkboxes (hit area) and skip links.
- **Elevation:** `shadow-card` is 0 1 2 rgba(0,39,76,.05) plus 0 6 18 rgba(0,39,76,.045). Dark mode uses a border instead of a shadow. HC uses a border only.
- **Motion:** 150 ms ease-out for panel and disclosure changes, and none under `prefers-reduced-motion`. Nothing loops except the scan progress bar fill, which is static under reduced motion.
- **Grid:**

  | Width | Side padding | Split (list / panel) | Gap |
  |---|---|---|---|
  | 1440 | 40 | 776 / 560 | 24 |
  | 1280 | 32 | 700 / 492 | 24 |
  | 768 | 24 | one column | |
  | 320 | 16 | one column | |

## 2. Icons (drawn, 20 px, stroke 2 px, `currentColor`, never the only signal)

**Severity shapes.** The same shapes always go with the same words:

| Severity | Shape |
|---|---|
| Blocker | filled octagon with a white bar |
| Critical | triangle with ! |
| Major | diamond |
| Minor | circle |
| Best practice | square with i |

**Status icons:**

| Status | Icon |
|---|---|
| New | dot in a circle |
| Needs review | eye |
| Confirmed | check in a circle |
| Ticketed | ticket stub |
| Fixed | check in a square, success color |
| Came back | curved return arrow |
| Accepted risk | shield |
| Dismissed | slashed circle |

**Witness mark shapes** (see §4.1):

| Mark | Shape |
|---|---|
| Rule check | square |
| Browser test | circle |
| AI review | triangle |
| Person | pentagon with a check |

## 3. Components (03 Components)

Every component has variants for each listed state. The Focus state shows the 3 px ring with a 2 px offset. Text is bound to the text styles; colors are bound to variables.

| # | Component | Variants and states | Spec |
|---|---|---|---|
| 1 | Button | Primary, Secondary, Ghost, Danger × Default, Hover, Pressed, Focus, Disabled | 44 px high (Run scan: 52), px 16, `label`, radius 8. Secondary: surface fill with a 1 px `border/control`. Every button has visible text; an icon is optional and sits on the left. Disabled: 60% opacity plus `aria-disabled`, still focusable. |
| 2 | Link | Default, Hover, Focus, Visited | Always underlined, 1 px, offset 3. Hover: 2 px underline. |
| 3 | Severity badge | Blocker, Critical, Major, Minor, Best practice × Small (24 high, row) and Large (32 high, panel and tile) | Shape icon plus the word. Radius 5, px 8, 1 px border in the fg color. Blocker is filled; the others are tinted. |
| 4 | Status badge | New, Needs review, Confirmed, Ticketed, Fixed, Came back, Accepted risk, Dismissed | Neutral surface with a 1 px `border/control` and fg text plus an icon (the current StatusChip is neutral on purpose). Two exceptions: Fixed uses `success/*`, and Came back uses fg text on the Maize band with stripes on its left 8 px. |
| 5 | WCAG badge | A, AA, AAA, BP | Shows "2.4.4" plus a level pill ("A"). The level pill is the existing ConformanceBadge. |
| 6 | Witness marks | Compact: AI only, One check, Checks agree (2), Checks agree (3), Person confirmed. Expanded: a list with each check and its result. | Compact is a row of up to 4 shapes (16 px), filled = saw it, outline = ran and did not see it, plus a text label. Expanded is a table: Check, What it found, Instances. |
| 7 | Stat tile | Severity × 5 and Work × 3 (Needs review, Came back, Fixed) × Default, Hover, Focus, Pressed | 176 × 112 at 1440. Label with icon, `count`, and a delta line in `caption`. Pressed: `bg/selected`, a 4 px top `selected/bar` and a check icon plus "Filter on" text. Came back > 0: the Maize band on the left. It is a toggle button. |
| 8 | Delta | Worse, Better, Same, New run | "Up 1 since Run 3" with an up-arrow icon; "Down 17" with a down arrow; "Same as Run 3"; "First run". Words and an arrow, never color alone. |
| 9 | Count caveat | Default, Focus | A small "Note" text button with a dagger-shaped icon after a number. It opens the related health note. |
| 10 | Filter chip | Default, Hover, Focus (on remove) | "Status: Needs review" plus a remove button (44 × 44 hit area). Name: "Remove filter Status: Needs review". |
| 11 | View presets | Triage, Fix, Overview selected × Focus | Segmented radio group styled like the current Tabs track (muted track, blue selected fill, white text). The selected option also shows a check icon. |
| 12 | Picker | App, Run, Compare × Default, Hover, Focus, Open | 44 px, a label above ("App", "Run", "Compare to"), the value, and a chevron. Open shows a listbox with a checkmark on the selected option; each option has 2 lines (name, detail). |
| 13 | Text field | Default, Focus, Filled, Error | 44 px, 16 px text (inputs use 16 so iOS does not zoom), 1 px `border/control`, visible label. Error: an icon, text and a 2 px critical border. |
| 14 | Checkbox, Radio | Unchecked, Checked, Indeterminate (checkbox), Focus, Disabled | 20 px box, 2 px `border/control`, 44 px hit area. |
| 15 | Textarea | Default, Focus, Error | Reason field. |
| 16 | Disclosure header | Collapsed, Expanded × OK, Notes, Failed × Focus | Full-width 56 px button containing the h2 text, a summary line and a state icon plus words ("2 notes", "Failed"). |
| 17 | Sort header | Unsorted, Ascending, Descending, Focus | Button in a `th`; an arrow plus words in `caption` ("Sorted high to low"). |
| 18 | Issue row | Default, Hover, Focus, Selected, Open, Came back | Checkbox · Severity (S) · title button (`label` 16 underlined on hover and focus) + WCAG badge + Fix reach line · Checks (Witness compact) · Since · Instances ("143 on 19 pages") · Status. Open: 4 px `selected/bar` on the left, `bg/selected` and the text "Showing in details". |
| 19 | Group header row | Came back, Needs review, New, Confirmed; each Expanded or Collapsed | A `th scope=rowgroup` row: name, count, and a collapse button. |
| 20 | Issue card (below 768) | Default, Focus, Came back | The same content as label-value pairs; the title button is the card heading. |
| 21 | Instance row | Default, Selected, Focus | #, page (link), element summary, selector (mono, wraps), evidence ("Screenshot", "HTML"), Copy selector. Selected: bar plus the evidence shown below. |
| 22 | Code block | Selector, HTML × Default, Copied | Mono, wraps anywhere, 1 px border, a "Copy" button with a text result ("Copied"). |
| 23 | Screenshot | Default, Focus, Expanded | Outlined element; the caption says what is outlined; alt text such as "Screenshot of the Walpole page. The first item image link is outlined." |
| 24 | Fix option | Recommended, Other | Option label, "How", "Watch out", "Effort". Recommended adds a star icon and the word "Recommended". |
| 25 | Health item | OK, Note, Failed | Icon (check, flag, octagon) plus words plus a detail line. |
| 26 | Done ledger | Bars per run × Chart and Table | See §4.3 |
| 27 | Bulk bar | 1, several | "3 issues selected" plus Confirm, Dismiss or accept risk…, Create Jira tickets, Clear selection |
| 28 | Status message | Success, Error | Inline text under the triggering control, with an icon. The same text goes to the page status region. |
| 29 | Skip link | Hidden, Focused | 44 px, primary fill, top-left, shown on focus |
| 30 | Top bar | 1440, 768, 320 (Menu) | Home mark, App picker, then on the right Help, Settings and Run scan |
| 31 | Key cap | Default | `mono-sm` in a 1 px border box, used in the shortcut list and hints |
| 32 | Scan progress | Running, Stopped, Failed | Determinate bar with "132 of about 214 pages", a stage name and "Stop scan" |
| 33 | Empty state | First scan, Zero issues, Filtered to none | Heading, one sentence, one primary action |
| 34 | Dialog | Keyboard shortcuts, Run scan, Settings | 12 radius, h2, Close button with text, trapped focus |
| 35 | Pagination | Default | "Showing 1 to 25 of 512 issues", Previous, Next, page size |

## 4. Original patterns

Each pattern is named, states the problem it solves, and explains why it is not borrowed.

### 4.1 Witness marks (trust)
- **Problem.** Axcess mixes deterministic rule results, browser-observed behavior and AI onlys, and the team is aiming for zero false positives. Users cannot tell a corroborated failure from a single model's guess. Confidence percentages would be jargon, and the models do not store them.
- **Pattern.** Every independent check that saw the problem leaves a mark, and each kind of check has its own shape:
  - square: rule check (axe, Alfa);
  - circle: browser test (keyboard, zoom and spacing, focus);
  - triangle: AI review (language or image model);
  - pentagon with a check: a person confirmed it.

  **One mark per check that saw it.** axe and Alfa each draw their own square, so two rule checks show two squares. A person's confirmation adds the pentagon. Checks that ran and did not see it draw nothing in the row; the panel lists them. The marks sit in a row, followed by a fixed phrase: **"Person confirmed"**, **"Checks agree"** (2 or more checks), **"One check"**, **"AI only"** (only an AI review saw it), **"Cannot tell"** (a rule check could not decide). The expanded view in the panel lists each check: "Rule check, axe: failed on 143 of 143", "Rule check, Alfa: failed on 143 of 143", "AI review: flagged 27 of 143".
- **Why it is not borrowed.** Single-engine tools show one engine's own certainty, such as "needs review" or "best practice". Axcess runs several independent engines over the same crawl, so it can show corroboration. The shapes and vocabulary come from Axcess's own principle that results are "evidence to review, not proof": the marks read as witnesses, not a score.

### 4.2 Came-back band (since last run)
- **Problem.** A regression is the most expensive surprise, yet today every rescan resets triage and "no longer detected" is easily mistaken for "fixed".
- **Pattern.** An issue that was Fixed or Dismissed in an earlier run and is detected again gets:
  - an 8 px Maize band with ink diagonal stripes on its left edge;
  - the status "Came back" with a return arrow;
  - the line "Fixed in Run 3. Found again in Run 4 on 8 pages."

  In the Triage view it is pinned in its own first group. Its strip tile carries the same band whenever the count is above 0. The band is Maize, the U-M attention color. The stripes give 11.65:1 against Maize, and the label carries the meaning.

  Every row's "Since" cell uses words: "8 new", "17 fixed", "No change", "Cannot compare" (with the reason in the panel). A change is labeled Fixed only after a person confirms it; otherwise it reads "Gone, needs a check".
- **Why it is not borrowed.** Diff views show added and removed lines in green and red. This pattern separates "new" from "came back", which needs triage memory across runs, and it refuses to call something fixed when the runs are not comparable. It uses Axcess's own Maize accent, not a traffic light.

### 4.3 Done ledger (progress over perfection)
- **Problem.** Open counts alone punish teams: a large site can fix 200 instances and still show "1,774 open". Leaders need credit and trend in 10 seconds.
- **Pattern.** A ledger of work done, one row per run and newest first:

  | Part | Drawing |
  |---|---|
  | Fixed (confirmed) | solid `success` bar growing from the left |
  | Dismissed with a reason | hatched bar |
  | Accepted risk | dotted-outline bar |

  Each segment carries its count as text. A running total heads the ledger: "Your team has closed 212 instances since the first run, and 19 since Run 3." A small open-by-severity trend (direct-labeled lines with shape markers, no legend lookup) sits beside it. **"Show as table"** switches both to data tables with captions, and the text summary is always visible.
- **Why it is not borrowed.** Tools show burndown of open issues or a site score. The Done ledger counts decisions as work: a dismissal with a reason is credited, because in a zero-false-positive program ruling something out is real work. There are no scores, gauges or donuts.

### 4.4 Fix reach (template lens)
- **Problem.** Developers get 143 instances and cannot see that one template change fixes all of them. Analysts cannot see which fix has the widest reach.
- **Pattern.** Axcess groups instances by shared selector pattern across pages and says **"Likely 1 template: `.item.resource > a` on 19 pages"**. "Likely" is always shown, because this is a heuristic. The Fix view sorts by reach. In the panel, the instances table groups under each likely template, with a count and a "Copy pattern" button.
- **Why it is not borrowed.** Page-by-page tools list instances per page. Axcess has cross-page selector evidence from one crawl, which makes this possible.

### 4.5 Count caveats (health-gated numbers)
- **Problem.** Scan health can distort numbers. For example, 5 pages were crawled over both http and https, which doubles 152 rows.
- **Pattern.** A number that a health note affects carries a small "Note" button next to it. Activating it opens Scan health at that note: "Counts may be high: 5 pages were checked twice (http and https)."
- **Why it is not borrowed.** It ties the number to Axcess's own coverage ledger. It is not a generic footnote or a tooltip.

## 5. Copy deck (plain language, about grade 8, no em dashes)

**Top bar:**
- "Axcess" (home link, name "Axcess home").
- "App" picker; value "museumcollab.anthro.lsa.umich.edu".
- "Help", "Settings", "Run scan".

**Report header:**
- h1: "Accessibility report: museumcollab.anthro.lsa.umich.edu".
- Run picker label "Run", value "Run 4 · Sep 11, 2026, 6:39 PM".
- Compare picker label "Compare to", value "Run 3 · Aug 28, 2026".
- Meta line: "Took 1 hr 30 min. 214 pages checked."
- Health chip: "Scan health: 2 notes".
- View label "View". Options: "Triage", "Fix", "Overview".

**At a glance (h2):**
- Summary sentence: "2 critical issues are open. 1 issue came back since Run 3. Your team fixed 19 instances since Run 3. 6 issues need a person to review."
- Tiles:

  | Tile | Count | Delta line |
  |---|---|---|
  | Blocker | 0 | "Same as Run 3" |
  | Critical | 2 | "Up 1 since Run 3" |
  | Major | 8 | "Up 1 since Run 3" |
  | Minor | 2 | "Up 1 since Run 3" |
  | Best practice | 3 | "Same as Run 3" |
  | Needs review | 6 | "issues to decide" |
  | Came back | 1 | "Since Run 3" |
  | Fixed | 19 | "instances since Run 3", plus "All confirmed by a person" |

**Scan health and coverage (h2):**
- Summary: "214 pages checked with 9 kinds of checks. 2 notes may change the counts."
- Items:
  - "5 pages were checked twice, once with http and once with https. Counts on those pages may be doubled."
  - "2 admin links led to the sign-in page. Those results are about the sign-in page."
  - "189 image files were found as links and were not checked as pages."
  - "Checks: Rule check axe 214 of 214 pages. Rule check Alfa 214 of 214. AI language review 214 of 214. Keyboard test 214 of 214, nothing found. Zoom and spacing test 214 of 214. Clicking menus and buttons: 21 controls, no new states. Image text: 381 images. Visual reading order 214 of 214. Focus visibility 214 of 214, nothing found."
  - "Not checked: pages matching /logout, /delete, /remove, /signout, /sign-out, /log-out."
  - "Sign-in: not used. This is a public site."
  - "26 of 55 WCAG 2.2 A and AA criteria can only be checked by a person."

**Progress (h2):**
- "Your team has closed 212 instances since the first run, and 19 since Run 3."
- Ledger rows:
  - "Run 4: 19 fixed, 0 dismissed, 0 accepted risk"
  - "Run 3: 64 fixed, 12 dismissed, 1 accepted risk"
  - "Run 2: 101 fixed, 15 dismissed, 0 accepted risk"
- Button: "Show as table".

**Issues (h2):**
- "15 issues, 1,774 instances".
- Search label: "Find an issue".
- Chips: "Status: Came back, Needs review, New", then "Add filter", "Clear all".
- "Group by: Status"; "Sort: Severity".
- Caption: "Issues in Run 4, grouped by status, sorted by severity. 3 filters on."

**Detail panel (issue 2):**
- h2: "Image links have no name".
- Meta: "Critical" · "Confirmed" · "2.4.4 A, 4.1.2 A" · Witness: "Checks agree".
- Buttons: "Previous issue", "Next issue", "Close details".
- Actions: "Confirm" (shows "Confirmed" when current), "Dismiss or accept risk…", "Create Jira ticket", "Copy selector".
- **What is wrong:** "Item pictures in the Related items lists are links. Each link holds only a picture with empty alt text (alt=""), so the link has no name. Screen readers say "link" and nothing else."
- **Who it affects:** "People who use screen readers cannot tell which item a link opens. People who use voice control cannot say the link's name to click it."
- **Checks that found it:** "Rule check, axe (link-name): 143 of 143". "Rule check, Alfa (R11): 143 of 143". "AI review, link purpose: 27 of 143". "Person: confirmed by the accessibility team, Sep 12".
- **Since Run 3:** "2 fixed. 141 still present. None came back."
- **Where it happens:** "Likely 1 template: .item.resource > a on 19 pages."

  | # | Page | Element | Selector |
  |---|---|---|---|
  | 1 | /s/Anishinaabe/page/Walpole | Image link to item 29 | `.item.resource:nth-child(1) > a[href="/s/Anishinaabe/item/29"]` |
  | 2 | /s/Anishinaabe/page/Bell | Image link to item 29 | same pattern |
  | 3 | /s/Anishinaabe/page/braided_mat | Image link to item 73 | same pattern |

  HTML: `<a href="/s/Anishinaabe/item/29"><img src="…" alt=""></a>`
  Steps to reproduce: "1. Open the Walpole page. 2. Turn on a screen reader. 3. Press Tab until you reach the first picture under Related items. 4. Listen: it says "link" and nothing else."
- **Suggested fixes:**

  | Option | How | Watch out | Effort |
  |---|---|---|---|
  | (Recommended) Make the picture and the title one link | Put the image and the item title inside the same link in the item card template | Changes the card template; test the card layout | Medium |
  | Give each picture alt text | Set alt to the item title, for example "Braided rush mat" | Editors must fill it in for every item; missing alt brings the problem back | Low per item, high overall |
  | Hide the picture link from assistive tech | Add aria-hidden and tabindex -1 to the picture link and keep the title link | Mouse users still have two links; do not use if the title link is missing | Low |

  Disclaimer: "These fixes are suggestions, not a guarantee. Test the change with a screen reader before you close the ticket."
- **Done when:** "Every item link has a name that matches the item title." "axe link-name and Alfa R11 pass on all 19 pages." "With NVDA, the Links list shows item names, not "link"."
- **Jira ticket** (draft) sections: Summary, Current Behavior, Steps to Reproduce, Impact, Expected Behavior, Suggested Fix (with the disclaimer), References, Instances table (#, URL, Selector, Element). Buttons: "Copy ticket", "Download for Jira (CSV)", "Mark as ticketed".
- **History:** "Sep 12, 2026: Confirmed by R. Maharjan. Reason: seen on 3 pages with NVDA." (illustrative)

**Words (round 1):**
- Glossary "What these words mean" (in Help, and a link beside the Issues count): **Issue**: one problem with one cause. **Instance**: one place on one page where the issue shows up. **Run**: one scan of the app. **Resolved**: fixed, dismissed with a reason, or risk accepted. **Template**: a part of the page that many pages share. **Rule check**: automatic tests (axe, Alfa). **Browser test**: Axcess used the page like a person would (keyboard, zoom). **AI only**: only an AI review saw it; a person should check. **WCAG**: the web accessibility standard; each rule has a number like 2.4.4.
- Since column: "First seen in Run 4" (not "New in Run 4"). The status "New" means not decided yet.
- Best practice rows show "No WCAG rule (best practice)" instead of rule ids.
- In the panel, WCAG badges show the name: "2.4.4 Link Purpose, Level A".
- Work tiles: "6 issues to decide", "1 issue", "19 instances".
- Summary: "2 critical issues are open. 1 issue came back since Run 3. 12 issues need a decision, and 6 of them are AI only. Your team fixed 19 instances since Run 3."
- Progress: "Your team has resolved 212 instances since the first run, and 19 since Run 3." ("closed" is not used.)
- Under the h1: "Evidence to review, not proof of compliance."
- Report header adds an "Export" menu button: CSV, XLSX, Markdown, JSON, Jira CSV (for the current filter).

**Footer:** "Axcess runs on this computer. Results are evidence to review, not proof of compliance." "Help and contact". "Version 0.1".

## 6. Annotation keys (for page 06)

Each component card lists: Role, Accessible name, Heading level, Landmark, Focus order, Keyboard, Live region, Reflow. The full-page annotation numbers the focus order 1 to 12 (ia.md §6) and labels landmarks and headings. See ia.md §5 to §9 for the rules the annotations must match.

## 7. Changes from the current design (each with its accessibility reason)

| # | Current | New | Reason |
|---|---|---|---|
| D1 | Maize global focus ring, 1.27 to 1.52:1 | Blue ring in Light (14.28:1), Maize in Dark (10.96:1), cyan in HC; 3 px outline, not a box-shadow | 1.4.11, 2.4.13; box-shadows vanish in forced colors (T1, T8) |
| D2 | Control borders #B8C4D2 (1.60 to 1.77:1) | `border/control` #798FAA (3.01:1 or better); #B8C4D2 stays for decoration | 1.4.11 (T3) |
| D3 | fg.subtle #475263 | #424C5C (7.35:1 on the new selected fill) | 1.4.6 on tinted surfaces |
| D4 | No dark theme | Dark mode (all text 7:1 or better) plus a High contrast approximation | Bar requirement (T7, T8) |
| D5 | Links underlined on hover only | Always underlined | 1.4.1 (T6) |
| D6 | Impact chip white on tint | Severity badge with fg on tint, a shape icon and a word; Blocker filled | 1.4.3, 1.4.1 (T4) |
| D7 | Sticky 72 px top bar | Not sticky; only the panel is sticky, and only at 1024 px and wider | 2.4.11 and 2.4.12 (T10) |
| D8 | 4-level severity (critical, major, minor, info) | 5-level ITS scale with a shape per level | Brief; 1.4.1 |
| D9 | `window.prompt` for reasons | Inline Decide form | 3.3.2, 3.3.7 (T15) |
| D10 | 0 to 5 single-key shortcuts that cannot be turned off | Scoped J/K/X/C/D/T/? shortcuts that can be turned off and remapped | 2.1.4 (T12) |
| D11 | Pulsing running badge | A static badge plus a determinate bar; milestone announcements only | 2.3.3, 4.1.3 (T5, T16) |
| D12 | Skip link 36 px, crumbs 18 px | 44 px everywhere | 2.5.5 (T11) |
| D13 | Sidebar app shell | No sidebar on the report page | IA C11 (one page, reflow) |
| D14 | Plain-text 401 access gate | Access screen with a password-manager-friendly field | 3.3.8 (T18) |
| D15 | Review lanes named 3 different ways (Barrier, Needs review, Review leads) plus a confidence word | Witness marks with one fixed phrase set | 3.2.4 Consistent Identification; 1.3.1 (the trust signal is text, not only a lane color) |
| D16 | No success color | `success/*` tokens (8.07:1 and up) for Fixed credit, always with a word and an icon | 1.4.1, 1.4.6 |
| D17 | 4-level severity chips | 5-level scale with one shape per level (D8's accessibility reason) | 1.4.1: level is readable without color |
| D18 | Report-level Export and the "evidence, not proof" line | Kept: Export in the report header; the line under the h1 | Not a change: restored after round 1 |
| D19 | Text-style buttons and table links at text height | Every standalone text button and table link has a 44 px hit area | 2.5.5 |

Kept unchanged: U-M Blue primary, Atkinson Hyperlegible, the type scale, the 8 px radius, the 4 px spacing, 44 px targets, the neutral status chip, severity tints, ConformanceBadge colors, the tabs look for presets, the sortable-table pattern, and the soft blue shadows.

## 8. Round 2 copy and behavior (supersedes earlier lines where they differ)
- Summary sentence: "15 issues are open, with 2,180 instances. 2 are critical, and 1 came back since Run 3. 6 need review by a person. Since Run 3, your team fixed 19 instances on 2 issues."
- Fixed tile: count "19", unit "instances fixed since Run 3", sub-line "On 2 issues, all confirmed by a person."
- Issues header in Triage: "Decided in this view: 0 of 13".
- Status label "Not decided" replaces "New" (stored `new`); group header "Not decided (6)"; chip "Status: Came back, Needs review, Not decided".
- "Gone after rescan" panel: banner "Gone in Run 5 on 19 of 19 pages. A person needs to check that it is fixed." Primary button "Mark as fixed".
- Progress line: "Since Run 3, your team fixed 19 instances. Since the first run, your team has resolved 212."
- Overview (full-width) issue table: 880 px wide, columns Severity 128, Issue 400, Since Run 3 176, Status 176; every row has a 1 px bottom divider in `border/control` (3.39:1 on muted, 3.64:1 on white) so each row reads as one unit when magnified.
- Bulk actions bar sits between the filter chips and the table while issues are selected; its status message: "3 issues selected. Bulk actions are above the table. Press B to go there."
- Jira ticket section: the action row ("Copy ticket", "Download for Jira (CSV)", "Mark as ticketed") comes first after the h3.
- Change log addition, D20: status "New" is shown as "Not decided" (3.2.4 and plain language: "New" clashed with "No change" in the same row).
