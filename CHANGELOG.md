# Changelog

Notable changes to Axcess, newest first. Versions use three parts
(`0.60.0`). Desktop previews are published from CI as `0.60.<run number>`;
before 0.60 they were `0.1.<run number>`, up to `desktop-v0.1.33`.

## 0.60.0 - 2026-09-26

### Added

- **Compare scans** replaces Verify changes: New, Resolved and Remaining
  issue groups since an earlier scan of the same site, a trend over every
  completed scan, and coverage notes on what differed between the two.
- **WCAG version**: scans check against WCAG 2.1 (the default, the current
  U-M standard) or 2.2, in New Scan and as `--wcag-version`.
- **Reports grouped by site**, one row per site with its most recent
  completed scan, and a Last scanned card. The app opens on Reports.
- **Retry with the same settings**: GET `/api/scans/{id}/settings`, "Edit
  settings and retry" and "Quick retry" for a scan that failed or was stopped.
- **Settings** for how the app reads: theme, text size, contrast, colour
  vision, font and spacing, focus indicator, target size, table density, and
  confirmations and shortcuts; a keyboard shortcuts list; and an About page.
- **Export panel** with the formats a report offers (GET
  `/api/scans/{id}/exports`).
- **Issue filter menu** with finding types: WCAG, Click-Through and Alt Text.
- **Issue guidance**: an issue's what it is, how to fix or confirm it, and
  why it matters open together in one dialog from the issue page.
- **Previous / Next flagged element** on the inspector's rendered page.
- **Delete report** in a danger zone at the end of the Issues page.
- This changelog.

### Changed

- Finding screenshots **outline the flagged element** instead of drawing a
  circle over it. Reports made before 0.60 keep their circles until the site
  is scanned again.
- Every table uses one shared module: a top bar with search, one Filter
  menu and the pager. Column headings are centred, with short values
  centred under them and running text left-aligned.
- The Issues page says only when its evidence was captured ("Based on the
  scan completed ..."), counts its numbers in one summary line, and no longer
  splits the table with a header row per type.
- **What this scan checked** is a table: status, result, and what each check
  proves and its limits, all in view, with the checks that ran first.
- Compare scans reads trend first, then the change cards and table, with the
  coverage notes last.
- The issue pages table drops its Open live page and Stored evidence
  columns; both are one step away on a page's screenshots view.
- The inspector's "Page state" picker is "Which view of the page", and its
  counts say what they count ("As the page loaded: 19 flagged elements").
- Clicking a site's name on Reports expands its scans.
- The project version moves from 0.1.x to 0.60, and CI stamps desktop builds
  `0.60.<run number>`.

### Fixed

- The scan settings endpoint no longer returns `user:password@` for a seed
  URL too malformed for `urlsplit` to parse.

### Performance

- The final screenshot pass centres each element with one scroll call:
  about 26 ms per capture, down from 42 ms.

### Accessibility

- A live status line reads the count of each issue type as filters change.
- The labels glossary has real headings, and each term sits above its
  definition, drawn as the chip the table uses.
- The Issue guidance dialog is a native modal: focus is trapped and returned,
  Escape closes it, and a focused link cannot scroll under its header
  (SC 2.4.11).
- Check status chips pair colour with a check mark or dash and a word; the
  inspector's current flagged element is blue on yellow, the others red.
- The Reports site toggle's name includes its visible text (SC 2.5.3).
- Screenshot captions and alt text describe the outline marker.

### Security

- Credentials are stripped from unparseable seed URLs (see Fixed).
- The frontend's build-time dependencies take npm audit's semver-compatible
  patches, from 10 findings to 2.

### Docs

- Reading your report, the glossary, the developer guide (`--wcag-version`),
  Adding a check, and the release docs and diagram match the app as it is.
