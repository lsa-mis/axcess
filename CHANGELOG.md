# Changelog

Notable changes to Axcess, newest first. Versions are semver: the team
chooses the release line (now 0.2), and each desktop release published from
`main` counts up the last part, 0.2.0, 0.2.1 and on. Earlier previews were
numbered `0.1.<run number>` (to 0.1.34), then 0.60 to 0.63, one step per
merge.

## Unreleased

### Added

- Keyboard check: it now also finds controls that work with a mouse but not
  from the keyboard (WCAG 2.1.1): elements with a click handler that the Tab
  key cannot reach, and custom controls Tab reaches that have no key handler.
  It also finds clicks the page handles for the whole document (including
  jQuery's), and menus that open only when the mouse is over them (CSS
  `:hover` with no keyboard equivalent), and controls that act only on
  mouse-down, which Enter and Space never send. It reads the page's event listeners
  and styles in a few steps, so it adds well under a second per page. The switch is now called **Check keyboard access**.
- Click-Through, with the keyboard check on: each dialog a click opens is
  checked for keyboard access. Focus should move into it, Tab should not
  leave a modal for the page behind it, its close control should get
  keyboard focus, and Escape should close it. Click-Through now also opens
  links that go nowhere (`href="#"`), which scripts often use to open
  dialogs.
- Focus check: it now also finds controls that show no change at all when
  they have keyboard focus (WCAG 2.4.7), the Tab key stopping on plain content
  with `tabindex="0"`, and rows of controls whose Tab order differs from
  their order on screen (2.4.3). It adds about a tenth of a second per page.
- New scan: **Keyboard (Advanced)**, off by default. It clicks each control
  the keyboard check suspects, then tries Enter and Space, and reports only
  the ones that fail. It is slower, up to about 20 seconds more on a page
  where it finds something, and never operates a control whose name looks
  destructive. The comparison behind both is in
  `experiments/tabbing/ab/RESULTS.md`.
- Desktop app: the first time Axcess opens, the loading screen says
  "The first time Axcess opens, this can take a minute or two." under
  "Loading", since that first start sets up the reports database and the
  system checks the new app.
- Linux: Axcess as an AppImage, the whole app in one file, for 64-bit
  Linux from 2022 on (Ubuntu 22.04, Debian 12, Fedora 36 or newer), with
  text recognition built in. On Ubuntu 23.10 and later it opens with the
  browser sandbox off, because Ubuntu blocks it for AppImages. When a new
  version is out, Axcess offers the new file to download.
- Windows, without installing: a zip of Axcess for computers where you
  cannot install programs, or to carry Axcess and its reports on a USB
  drive. Axcess keeps everything in the "Axcess data" folder next to
  Axcess.exe, so moving the folder moves your reports too. When a new
  version is out, Axcess offers the new zip and says how to bring the data
  folder along. Do not keep it on a network drive.
- New scan: **Scan every page it finds**, for public scans. There is no page
  limit; the scan ends when it runs out of pages in scope within the link
  depth. Sign-in scans keep their cap.
- Inspector: a Zoom and layout check issue opens the saved copy the way the
  check saw it: 320 pixels wide for reflow, 640 by 450 for text at 200% zoom,
  or with WCAG's text spacing, with the element highlighted. "Show at full
  width" compares.
- **Issue guidance for every issue.** Every rule a scan can run now has a
  guidance card: all 93 axe rules (81 had none), all 58 Alfa rules a scan can
  select (none had one), the three AI review criteria that had none, and
  every image group (17 had none). The 29 existing cards were improved too.
  Each card says what the rule checks, why it matters and to whom, how to fix
  it (with code where it helps), how to test the fix, and when it is done.
  Each was written from the rule's own documentation (Deque University,
  Siteimprove Alfa, W3C ACT rules and Understanding WCAG) and from Axcess's
  code, then checked again against those sources: the second check changed
  wrong causes, a fix that would not pass its rule, and advice that could
  hide a meaningful image from screen readers. Rescan advice names the
  setting the check needs (Alfa or Both, Level AAA, WCAG version 2.2, the AI
  review, the motion check, the vision model), because a default scan skips
  those and the issue would look fixed. `tests/unit/test_guidance_cards.py`
  fails when a rule has no card, or a card breaks the plain-language rules.
- **Hover hints** on words that need explaining: the Issues table's Type and
  Found by tags (in the glossary's own words), its column headers, the
  priority bands, the level badges, Compare's New, No longer found and Still
  found, and status chips. They follow the Hints setting; a column header's
  hint also shows on keyboard focus and is read as its description. The
  Issues glossary now explains the priority bands too, and an occurrence's
  page says what the chosen status means ("Fixed" is a person's decision;
  Axcess does not check it).

### Changed

- Versions: 0.2.0 starts a release line the team chooses, and each release
  counts up the last part (0.2.1, 0.2.2 ...). The previews 0.60 to 0.63
  numbered each merge instead and would have reached 1.00 by themselves.
  A copy of one of those is not offered 0.2.x: install it once from the Get
  started page.
- New scan button: it no longer turns grey on the New scan page. It looks
  the same everywhere, and there a screen reader says it is the current
  page.
- Download files are named in plain words, for who each is for and what
  it is, not processor codes: Axcess-0.61-Mac-Apple-Silicon.dmg,
  Axcess-0.61-Windows-Installer.exe, Axcess-0.61-Windows-Portable.zip and
  Axcess-0.61-Linux.AppImage (they were -arm64.dmg, -Setup.exe,
  -Windows-x64-portable.zip and -x86_64.AppImage). A Mac with an earlier
  preview installed is not offered this one: download it from the Get
  started page once. Releases are titled "Axcess 0.61 (preview)", and
  each holds just those four files and the two the Windows updater reads.
- Windows installer: a standard setup wizard replaces the screen that showed
  only an animation. It asks who to install Axcess for (only you, with no
  administrator permission, or everyone on the computer), shows the folder
  and lets you change it, and says where Axcess is installed when it is
  done. Every word in the installer and uninstaller is plain English. Updates still install in
  place from the update dialog. Uninstalling keeps your scans. A copy
  installed by the old installer is not offered updates; uninstall it and
  install the new version.
- Inspector and page code view: stepping through flagged elements uses two
  labelled buttons, Previous and Next (Jump when there is only one), each
  with its own border, beside the count "Flagged element 1 of 3". They were
  two arrows in one box with the count.
- Back returns you to where you were. Open a report from Reports and press
  Back: the table keeps its order, search, page and opened sites, and the
  page is scrolled where you left it. The Reports view is kept in the page
  address, so a copied link opens the same view too. A new page still
  starts at the top.
- A stopped scan's page: with a partial report, "Review what the scan
  found" is now the main button and comes first, with a sentence saying what
  it opens, like the other actions. Every action's button is the same
  width. With no report, "Change settings first" still leads.
- No text in the app is smaller than 14 pixels. Hints, chips, captions and
  table notes were 12 or 13 pixels. Secondary text now stands apart by its
  colour and weight rather than by being smaller. Checked at 320, 390 and
  1280 pixels wide on every main page: nothing is cut off and no page
  scrolls sideways.
- Inspector: the box of page-state links under the Page state picker is now
  one sentence: "3 more occurrences are in 2 other page states. Choose one
  in the Page state list." The links repeated the picker, which already
  lists those page states with their counts. Screen readers hear the
  sentence as the picker's description.
- Issues: the four numbers over the table (Pages checked, Occurrences
  found, Issues found, Page states opened by clicking) sit on the page
  itself, spaced apart, instead of in a white panel cut by lines. The
  table is the one card under the title, and the numbers look like the
  other number readouts in the app. Every colour still has at least 7:1
  contrast. More space above and below the four, and between them, than
  inside each one, so they read as one group without a box.
- Every card and panel has the same rounded corners, 8 pixels, like the
  Last scanned card. Several used to look square-cornered because what was
  inside painted square corners over the card's rounded ones: a table's bar
  and last row, the first and last rows of the report's "What was checked"
  box, and the saved copy's bar in the Inspector. The small tables inside
  a section or an expanded site (the checks list, a site's scans) were
  square too: a table's own corners cannot be rounded, so the frame is now
  on the box around it. A site's list of scans now scrolls sideways in its
  own box when it is wide, instead of widening the whole Reports table. The
  New scan settings, sign-in scan panels and summary used 6 pixels, and an
  open section's header had rounded corners where it meets its content.
- Reports: a simpler table, with one header row. The number of scans sits
  under each site's name ("7 scans, 4 completed"), so every column is about
  the latest completed scan, and one sentence over the table says so. That
  replaces the "Most recent completed scan" header over six columns, its
  blue shading, and the Scans column; the table no longer sorts by number
  of scans. Completed comes right after Site. "Open latest scan" is a link
  rather than a button in every row. The order is no longer a line of its
  own, because the sorted column's chip shows it; screen readers still hear
  it when it changes. The search count sits beside the search box. A sort
  arrow stays beside its label's last word instead of on a line of its own.
- Inspector: what the numbered box is on is a short table, with the same
  labels in the same places as you step: what it is, its text or label, its
  size, and its element locator. A long locator shows its end, the element
  itself, on one line; Show all lists one step per line, and Copy element
  locator copies it whole (or, where the browser blocks copying, selects it).
  A Rule check (Alfa) locator is named an XPath, not a CSS selector.

- New scan: every settings group is an accordion row, closed on arrival. A
  failed submit opens the group that holds the field it names.
- New scan: Start scan and Cancel sit at the foot of the summary beside the
  form, where they stay in view while you scroll the settings, and after
  the form on a narrow screen. They were at the top of the page, which
  scrolled away and came before every field in keyboard order. Enter in
  the address field still starts the scan.

### Fixed

- Reports: a site's very first scan now shows while it runs. Starting it
  and going straight back to Reports showed "No reports yet" until the
  page was reloaded.
- Images, grouped by issue: each thumbnail links to its image's page, and
  a screen reader now reads that link as "Open image #12". It had no name.
- Public site, Get started: the yellow note in the download card had grey
  text, below the 7:1 contrast the site keeps for text. It is dark now,
  like the same note everywhere else.
- Issues and Reports: a filter chosen while the search box was still
  catching up with your typing could be lost. Both are kept now.
- Tabbing to a long table scrolled the page to the table's middle, away from
  its header row. Now its top comes into view, just under the top bar. A
  table that fits the screen is no longer a tab stop of its own, so Tab goes
  straight to its links.
- Inspector: an element with no box of its own is marked where the reader
  can see it. The numbered box used to jump to the top left of the saved
  copy. Now an element styled `display: contents` is marked around what it
  holds, an option on its list box, and an image map area on the part of its
  image it covers. The table under the toolbar says where the box is.
- Inspector: an occurrence on the whole page (`<html>` or `<body>`, as for
  a missing page language) no longer draws a box around the whole saved
  copy, with its label off the top and the view scrolled to the middle.
  There is no box and no dimming, the view stays put, and the table under
  the toolbar says it is the whole page.
- Inspector: a flagged element taller than the view (a whole `<main>`, a
  long form) is scrolled so its top shows, a little below the edge, with
  the box's number above it. Centring it used to hide both.
- Inspector: a skip link placed off the screen until it has keyboard focus
  is shown where it appears with focus, and the box is drawn there. The box
  used to be off the screen with it. Axcess reads how the link looks with
  focus from the page's own styles, and never moves your keyboard focus to
  find out. When it cannot read those styles (they come from another
  site), there is no box, and the table under the toolbar says the link is
  off the screen and that pages often show such a link only with keyboard
  focus. Something else off the screen gets no box, and the table says so.
- Inspector: a flagged link that wraps onto two lines gets a ring on each
  line, with the number on the first. One box used to cover both lines and
  the words beside them.
- Inspector: a flagged element that a part of the page cuts off (a
  carousel slide out of view, a menu item that does not fit) is boxed only
  where it shows, and gets no box when none of it shows. The table under
  the toolbar says the part of the page around it hides it. The box used to
  be drawn over the slide or items beside it.
- Inspector: a flagged element inside a closed section (`<details>`) is
  shown: the inspector opens the section in the saved copy and says so. One
  that was not displayed in the saved copy, such as a button in a tab that
  was not open, gets no box, the view stays where it was, and the table
  says it was hidden. The box used to land at the top left, or somewhere
  near the section.
- Inspector: an occurrence inside a component's own page code (shadow DOM)
  or inside another page shown within this one (an iframe) is no longer
  pinned on a different element that looks the same. The saved copy keeps
  neither, so the inspector counts these and says why they are not
  outlined. A page that draws on a drawing area (canvas) is said to show no
  drawing in the saved copy, which runs no scripts, and a flagged canvas
  says the same.
- On a phone, the Issues page scrolled sideways (to 615 pixels at 320):
  words kept for screen readers in the table were placed against the page,
  outside the table's scrolling box. They now stay inside it.
- The breadcrumb's focus ring showed only its sides: the trail clips so a
  shortened name cannot spill, and it cut the ring off at the top and
  bottom. The whole ring now shows around the focused link.
- An issue's page: the Pages with this issue table was inset from the page
  edges. It now spans the same width as the Issues table, lined up with
  the title.
- Inspector: on an app-style page that scrolls a panel of its own (a
  sidebar, a dialog) rather than the whole page, the flagged element is
  scrolled into view in that panel, and the numbered box stays on it as the
  panel scrolls. The box used to be left behind at the top or bottom of the
  panel, over some other control. It is hidden while the element is
  scrolled out of its panel.
- **Saved-copy highlights are exact.** An occurrence is outlined only when
  its locator, checked against its recorded markup, or the markup alone
  names one element. Checked against every occurrence in the local reports
  (23,750): the old matcher guessed among identical-looking elements 45
  times and outlined a different element than the only real match 4 times;
  both are gone, and an occurrence that cannot be pinned is said, not
  outlined. Alfa's records are now checked by tag, attributes and text
  (3,653 located, where they were accepted unchecked).
- The current flagged element gets a numbered box with a yellow ring and the
  rest of the page dimmed, at least 18 pixels even for a tiny or empty
  element, and a line under the toolbar says what it is (kind, text, size)
  and its locator. Other flagged elements have a thin dashed outline and no
  tint, so nested ones stay readable.
- Two elements with identical markup but different locators were treated as
  one occurrence, so the second was never outlined; and an occurrence in a
  clicked state was dropped when the same markup was flagged at page load.
- Issue guidance showed the "Why it was flagged" line twice when an issue
  had no card, and that line read "Deterministic axe-core rule failure;
  verify after remediation." The evidence lines are plain now, an Alfa
  issue's title says "a person must decide" rather than "expert decision
  needed", and an Alfa issue keeps its outcome note (a "can't tell" is not a
  failure) after its card's words. The exports print the cards' code as code
  (Markdown) or plain text (Excel) instead of raw tags, and find the same
  card as the issue page, so Alfa and browser-check issues get theirs.
- The Barrier meaning said a new scan "confirms the fix". It now says to
  test the fix, then scan again to see if it is still found: a later scan not
  finding an issue does not prove it was fixed.
- With hints set to Always, focusing a control took its hint away while the
  hint showed, so a screen reader lost the control's description.
- **Needs review issues are highlighted exactly, as Barriers are.** AI review
  issues outlined nothing: the inspector compared their stored rule
  (`semantic:2.4.4`) with `2.4.4`. Each is now outlined by the element the AI
  review read, found by its place in the saved copy, because its `a[ord=6]`
  is not a selector a browser can use: all 1,032 local occurrences, where
  their code alone would have missed 64 (cut at 300 characters) and left 29
  ambiguous. An Alfa "can't tell" issue outlined the same rule's failed
  occurrences too, and the reverse; each outlines only its own now.
- Images with text issues outline their images: each by its place among
  the saved copy's images, checked against its address and alt text (1,867
  of 2,105 local occurrences). The other 237 are backup copies inside
  `<noscript>`, each with an outlined twin; the inspector says it does not
  show them. The evidence list shows each image's alt text and text.
- The focus, keyboard, motion and reading-order, and zoom and layout checks
  keep only the first 240 or 300 characters of an element's code, without
  marking the cut, so a longer element matched nothing even where its
  selector named it. That code now matches as the start of the element's:
  zoom and layout occurrences not found fell from 156 to 20 (those 20 are
  no longer in the saved copy), and every focus occurrence is found.
- **Pages at once (workers)** now also sets how many pages are fetched from
  the site at once. It stayed at 2, so every worker past two waited: on a
  test site 32 workers took 12.3 s against 14.5 s for 8, and now take 5.5 s.
  Page requests per second still paces the site.
- New scan: on a narrow screen, the Scan type tabs' highlight covered half of
  the second tab's name. It now fits the selected tab.

## 0.60 - 2026-09-26

### Added

- **Compare reports** replaces Verify changes: New, No longer found and Still
  found issues since an earlier report of the same site, a trend over every
  completed report, and notes on what was checked in each.
- **WCAG version**: scans check against WCAG 2.1 (the default, the current
  U-M standard) or 2.2, in New Scan and as `--wcag-version`.
- **Reports grouped by site**, one row per site with its most recent
  completed scan, and a Last scanned card. The app opens on Reports.
- **Retry with the same settings**: GET `/api/scans/{id}/settings`, "Change
  settings first" and "Scan again with faster settings" for a scan that failed
  or was stopped.
- **Settings** for how the app reads: theme, text size, contrast, colour
  vision, font and spacing, focus indicator, target size, table density, and
  confirmations and shortcuts; a keyboard shortcuts list; and an About page.
- **Export panel** with the formats a report offers (GET
  `/api/scans/{id}/exports`).
- **Issue filter menu**, including "Found by": WCAG, Click-Through and Alt Text.
- **Issue guidance**: an issue's what it is, how to fix or confirm it, and
  why it matters open together in one dialog from the issue page.
- **Previous / Next flagged element** on the inspector's rendered page.
- **Delete report**, in a "Delete this report" section at the end of the Issues page.
- **Settings from Search**: type a setting's name in Search (Cmd/Ctrl+K) and
  its choices are results; Enter applies one and Search stays open.
- **Pages and checks** on a running scan: a row per page and a column per
  check, each cell Done, Checking, Waiting or Not run.
- Reports shows a running scan's progress, with a link to it.
- The inspector says when other page states hold more occurrences of the
  issue, how many, and links to each state.
- The website's "What Axcess checks" page has a short card for each check,
  and each row of a report's "What was checked" table links to its card.
- CI runs the desktop release's version pick, stamp and installer-name check
  on every pull request, and builds both installers on pull requests that
  change the desktop app or its release workflow.
- This changelog.

### Changed

- Occurrence screenshots **outline the flagged element** instead of drawing a
  circle over it. Reports made before 0.60 keep their circles until the site
  is scanned again.
- Every table uses one shared module: a top bar with search, one Filter
  menu and the pager. Column headings are centred, with short values
  centred under them and running text left-aligned.
- The Issues page says only when its evidence was captured ("Based on the
  report generated ..."), shows its four numbers as cells (the number, what it
  counts, one line), and no longer splits the table with a header row per type.
- **What was checked** is a table: status, result, and one line each on what
  the check does and its limit, with the checks that ran first. The check
  names follow the rest of the app ("Rule check (axe)", "AI review").
- **Scan in progress** wears the report header and leads with one progress
  bar, the three steps, the time left and Stop scan. Each check's totals and
  live updates are behind Show details.
- Compare scans is now **Compare reports**.
- Table cells have more room: wider padding and taller rows. The Table
  spacing setting's Tight and Roomy each step up to match.
- Settings' quick presets sit on one row under their explanation.
- New scan: Reset to default settings moves to the top right of the summary,
  beside "Customized", and shows only once a setting has changed.
- Each check in "What was checked" says what it does and its main limit in
  one sentence each, across the whole column; its card on the website keeps
  the rest.
- The running scan's table drops its check columns when the scan's checks
  are not recorded page by page, and shows a single-page app's pages by
  their route ("/#/about") instead of "/" for every row.
- Long control names in the inspector's Page state list are cut short, and
  the Issues search box's hint fits it ("Issue name or WCAG number (1.4.3)").
- Compare reports reads trend first, then the change cards and table, with the
  coverage notes last.
- The issue pages table drops its Open live page and Stored evidence
  columns; both are one step away on a page's screenshots view.
- The inspector's "Page state" picker says what its counts count ("At page
  load: 19 occurrences").
- Clicking a site's name on Reports expands its scans.
- The project version moves from 0.1.x to two-part versions: this is 0.60,
  and each desktop release from `main` is the next (0.61, 0.62, ... 0.70).
  npm and the Windows installer still get a three-part package version
  (0.61.0); every name and label people see says 0.61.

### Fixed

- The scan settings endpoint no longer returns `user:password@` for a seed
  URL too malformed for `urlsplit` to parse.
- One older report with a start address too malformed to parse no longer
  breaks Reports or every report's link to its previous report.
- The desktop build no longer stops at its version stamp when the version is
  the one package.json already has, as on the first 0.60 build.

### Performance

- The final screenshot pass centres each element with one scroll call:
  about 26 ms per capture, down from 42 ms.
- Reports counts each completed report's issues once, not on every refresh,
  and counts again only when the report's evidence changes.

### Accessibility

- A live status line reads the count of each issue type as filters change.
- The labels glossary has real headings, and each term sits above its
  definition, drawn as the chip the table uses.
- The Issue guidance dialog is a native modal: focus is trapped and returned,
  Escape closes it, and a focused link cannot scroll under its header
  (SC 2.4.11).
- Check status chips pair colour with a check mark or dash and a word; the
  inspector's current flagged element is blue on yellow, the others red.
- In the page code (DOM) view the current flagged element is blue with a
  thicker bar, the others yellow, so the one you moved to stands out.
- Search's results are a listbox of named groups. A setting's current
  choice says "Current setting" beside a tick.
- The Reports site toggle's name includes its visible text (SC 2.5.3).
- Screenshot captions and alt text describe the outline marker.

### Security

- Credentials are stripped from unparseable seed URLs (see Fixed).
- A start address's `user:password@` never shows: not in a label, a tooltip
  or a delete prompt.
- The frontend's build-time dependencies take npm audit's semver-compatible
  patches, from 10 findings to 2.

### Docs

- Merged with main's plain-language rewrite (PR #36): interface words follow
  docs/plain-language.md and lib/terms.ts, and numbered reports read "Report #N".
- Reading your report, the glossary, the developer guide (`--wcag-version`),
  Adding a check, and the release docs and diagram match the app as it is.
