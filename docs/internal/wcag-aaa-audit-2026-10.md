# WCAG 2.2 AAA audit of the review app, October 2026

What this is: an audit of the Axcess review app (`/app/`) against WCAG 2.2
Level AAA, done on 2026-10-07 from the code on `main` (desktop 0.2.5).
Findings are ordered by level and impact. Every finding has since been fixed
or checked on the `WCAGAAA` branch; see "Status" at the end.

## How it was checked

- **axe-core** (the copy the app ships, `src/audit/web/static/axe.min.js`)
  with the tags `wcag2a`, `wcag2aa`, `wcag2aaa`, `wcag21a`, `wcag21aa`,
  `wcag21aaa`, `wcag22aa` and `best-practice`, in light and dark, at
  1280 px.
- **Siteimprove Alfa** at Level AAA, WCAG 2.2, through the repo's runner
  (`src/audit/alfa_runner`), pointed at the installed headless Chromium with
  `ALFA_CHROMIUM_PATH`.
- **Scripted checks** for what neither engine covers: 44 by 44 px targets
  (SC 2.5.5), one link name with several destinations (SC 2.4.9), line
  length and line spacing (SC 1.4.8), focus outline and focus covered by
  sticky content while tabbing (SC 2.4.12, 2.4.13), abbreviations (SC
  3.1.4).
- **Reading the code** where a tool result needed explaining.

Screens: Reports, New scan, a report's summary and Issues, an issue, its
pages and screenshots, a page's evidence, the Page inspector, Images, Rule
check issues, Compare, Product roadmap, About, Settings, and Not found. One
local report (accessibility.umich.edu, 43 pages) supplied the data.

Not in scope: the scanned site's own content inside the Inspector's saved
copy (Alfa's sia-r113 and sia-r14 results point there), the desktop
installer, and the public website (audited separately).

## Findings

### Level A and AA (fix first)

| # | Where | Problem | Criterion | Evidence | Fix |
| --- | --- | --- | --- | --- | --- |
| 1 | Rule check issues (`/a11y`), impact chips | White text on the pale severity colours: 1.16:1 for "serious" (white on `#ffebc7`). | 1.4.3 Contrast (Minimum), AA | axe color-contrast (7 nodes, light and dark); Alfa sia-r69 | `ImpactChip` in `routes/A11y.tsx` uses `text-white bg-sev-*-bg`. Use the paired tokens (`text-sev-* bg-sev-*-bg`), as every other severity chip does. |
| 2 | Page inspector, page-state picker (`#inspect-state`) | The combobox has no accessible name in Alfa's reading: a `<label for>` points at a `<button role="combobox">`. | 4.1.2 Name, Role, Value, A | Alfa sia-r8 | In the shared `Select` (`components/ui.tsx`), add `aria-labelledby={labelId}` to the trigger, as the APG select-only combobox does. Every Select benefits. |
| 3 | Page inspector, saved copy `<iframe>` | The iframe takes keyboard focus (`tabindex` 0) but shows no focus outline (`outline: none`). | 2.4.7 Focus Visible, AA | Tabbing through the page | Give the iframe (or its frame) the app's focus ring on `:focus-visible`. |
| 4 | Images (`/findings`) | Tabbing to "Back to Report #1" and "Group by issue" leaves them partly under the sticky top bar. | 2.4.11 Focus Not Obscured (Minimum), AA, if fully covered; 2.4.12, AAA, as found | Focus check: the top bar is the element drawn over them | Add `scroll-padding-top` equal to the top bar's height (72 px) on the scrolling container, or scroll focused elements below it. |

### Level AAA

| # | Where | Problem | Criterion | Evidence | Fix |
| --- | --- | --- | --- | --- | --- |
| 5 | Most screens | Small text (`text-sm`, 14 px on 20 px) has line height 1.43; AAA asks for at least 1.5 in paragraphs. | 1.4.8 Visual Presentation, AAA | Alfa sia-r73: 122 paragraphs; scripted check on 13 of 15 screens | Raise the line height of `text-sm` to 1.5 (21 px) in the Tailwind theme, then check that no layout breaks at 320 px. |
| 6 | Product roadmap intro, Rule check issues intro, About, a page's evidence | Lines of 92 to 133 characters. | 1.4.8 Visual Presentation, AAA | Scripted check | Cap running text at about 35em, as the public site does. |
| 7 | Targets under 44 by 44 px (not in a sentence) | "1 screenshot of this issue on ..." icon links (81 by 18) on an issue's pages; "Open the image" (123 by 20) on a page's evidence; "Image #N" and page links (about 64 by 20) on Images; "WCAG 1.4.3" (98 by 24) and "About this rule" (111 by 20) on Rule check issues; the six links on About (about 100 by 20); Settings' option inputs (42 px tall); Roadmap's "Level" filter (43 px wide). | 2.5.5 Target Size (Enhanced), AAA | Scripted check; Alfa sia-r111 (37 targets) | Give these links `min-h-target` (and `min-w-target` for icon links), as the table title links already have. |
| 8 | A page's evidence; Rule check issues | One link name for several destinations: "Open the image, opens in a new tab" four times; "About this rule (opens in a new tab)" seven times. | 2.4.9 Link Purpose (Link Only), AAA | Scripted check; Alfa sia-r41 (cannot tell) | Add the image number or rule name in screen-reader-only text, as "N issues in Report #N" already does. |
| 9 | Rule check issues, impact chips | Shows axe's raw values ("serious", "critical"), not the app's words. | Repo rule: Interface language rule 2 (and SC 3.1.5 Reading Level, AAA) | Reading the code | Show the shared label from `lib/terms.ts` (add one if missing). |
| 10 | Images | 99 text nodes over screenshots that Alfa could not measure for 7:1. | 1.4.6 Contrast (Enhanced), AAA | Alfa sia-r66 / sia-r69 "cannot tell" | Check by hand; give text over pictures a solid backing. |
| 11 | Not found | No level 1 heading. | Best practice (supports 1.3.1 and 2.4.6) | axe page-has-heading-one | Make the page's title an `<h1>`. |

### Checked and not a problem

- **The links in the developer's screenshots** ("10 issues", "Open latest
  scan", "Heading levels skip a step", a page title such as "Log in to
  CodeGrade - CodeGrade"): each is 44 px or taller and names its
  destination (screen-reader-only text adds "in Report #1", "of
  accessibility.umich.edu", ", full details"). One thing differs between
  them: "N issues" has a 1 px underline 4 px below the text, the others the
  browser's default 2 px below. Consider one underline style for all links
  (SC 3.2.4 Consistent Identification, in spirit).
- **The selected tab in New scan and Compare**: Alfa reports 1.1:1, but the
  navy fill is a separate element sliding behind the text, which Alfa does
  not see; axe passes it and the text is white on navy. A false alarm; it
  would go away if the selected tab also carried its own background.
- **Contrast at 7:1** for everything axe can measure, in light and dark.
- **Focus outlines**: every focused control except the iframe (finding 3)
  has a visible outline of at least 2 px.
- **Line spacing below 1.5 in headings and controls** is allowed; only
  paragraphs need 1.5.
- **Text inside the Inspector's saved copy** belongs to the scanned site.

## Not covered by tools

These AAA criteria need a person with the app: 2.2.6 Timeouts (the 30
minute kept sign-in says so on screen), 3.1.5 Reading Level (the interface
follows docs/plain-language.md, but help text was not measured), 3.3.5 Help
and 3.3.6 Error Prevention (All) on New scan and status changes, and 2.4.8
Location (breadcrumbs exist on report screens; check the others).

## Status

Fixed on the `WCAGAAA` branch, one commit per finding, each rechecked with
the tool that found it:

| # | Fix |
| --- | --- |
| 1 | One shared `ImpactChip` with each severity's dark-on-pale pair; axe passes both Rule check views. |
| 2 | `Select` triggers are named with `aria-labelledby`; Alfa sia-r8 is gone. |
| 3 | The saved copy's frame gets the focus ring while focus is inside it (`data-focused`, set from the frame's own focus and blur, since a focused iframe matches no focus selector). |
| 4 | Page-wide `scroll-padding-top` for the top bar, and the narrow-screen report bar only where it shows; the table region's and occurrence cards' own scroll margins were removed so they no longer add up. |
| 5 | Small text's line height is 1.5 on the size tokens; eleven hints with their own tighter `leading-*` lost it. Alfa sia-r73 is gone. |
| 6 | Each paragraph of running text that ran long carries `max-w-measure` (35em, in the Tailwind theme). The first fix capped every `p`, `li` and `dd` in the main area at once; in use it cut the Inspector's bands and boxed notes short and squeezed the element locator beside its buttons, so it was replaced. SC 1.4.8 does not need a cap on every element: its sufficient techniques for width are G204 (text reflows as the window narrows) and C20 (relative widths). |
| 7 | `min-h-target` on the small links (a page title link's eye icon starts beside the title's first line, with 10 px above and below for the 44 px height; centring the text left the icon above it), `min-w-target` on sort headers. The regression tests then found two more the live report did not show: Settings' two-character options ("On", "10") were 41 px wide, now `min-w-target` there and in New scan's matching choices; and an issue's page title link, shown only for pages with a saved copy, was 24 px tall. |
| 8 | Screen-reader-only context on repeated links, including the shared `PageLink` (`shortLocator`). |
| 9 | `IMPACT_LABEL` in `lib/terms.ts`. |
| 10 | The report and scan headers' separators are drawn shapes, not light text; the other unresolved results are on the page's faint background gradient, where axe passes 91 elements at 7:1 and the darkest point (`#f4f5f7`) still clears 7:1 for the app's text colours. |
| 11 | `EmptyState` takes a heading `level`; Not found uses 1. |

Left as they are, with reasons:

- About's resource links: each stretches over its card, which is the real
  target and is 44 px or more.
- Alfa reports the Images sample-page links at 43.5 px tall; the same links
  measure 44 px in a full Chromium, and their minimum height is a fixed
  44 px, so this is rounding in Alfa's headless browser build.
- The selected tab's 1.1:1 result in New scan and Compare (a sliding fill
  Alfa cannot see).
- Results inside the saved copy, which belong to the scanned site.

## Regression tests

`tests/ui/test_wcag_aaa.py` checks each fix on a seeded report at 1280 by
720, on 13 screens: 44 px targets, one destination per link name, line
length and line height, focus clear of the top bar, the saved copy's focus
ring, named dropdowns, the impact chips' contrast and words (light and
dark), Not found's level 1 heading, drawn header separators, no reading-width cap on a band or box, and page title icons beside the first line. The last two were checked against the replaced design and fail on it.
