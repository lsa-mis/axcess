# Changelog

Notable changes to Axcess, newest first. Versions have two parts: `0.60`,
then `0.61` and on, `0.69` then `0.70`. Each desktop release published from
`main` is one step after the last. Before 0.60 desktop previews were
`0.1.<run number>`, up to `desktop-v0.1.33`.

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
