# User guide

## Setup (once)

```bash
make setup     # uv sync + playwright install chromium + ollama pull
make migrate   # apply DB migrations
```

Requires Python 3.11+, tesseract (via `brew install tesseract`), and
Ollama running locally with a vision model pulled.

## Run a scan from the command line

```bash
# Default: path-scoped (stays under the seed's URL path)
uv run audit crawl https://example.com/docs/

# Crawl the entire host
uv run audit crawl https://example.com/ --whole-host

# Small test run
uv run audit crawl https://example.com/docs/ --max-pages 20 --max-depth 3

# Skip expensive stages while iterating
uv run audit crawl <url> --skip-vlm
uv run audit crawl <url> --skip-ocr

# Force Playwright for every page (Cloudflare / SPA-heavy sites)
uv run audit crawl <url> --use-js

# Authorized testing against a site with a restrictive robots.txt
uv run audit crawl <url> --ignore-robots
```

You'll get a Rich summary table at the end — pages fetched, images
persisted, OCR candidates, VLM classifications, findings by severity,
and (on rescans) the diff counters.

## Run a scan from the browser UI

```bash
uv run audit serve         # → http://127.0.0.1:8765
```

Open **http://127.0.0.1:8765/app/scans/new** and:

1. Paste the site URL. As you type, the **Scope** preview shows what
   the crawler will actually do:
   - `https://example.com/docs` → `example.com/docs/` (auto-added slash)
   - `https://example.com/` → whole host
   - any URL + ☑ *Crawl the entire host* → ignores path scope
2. Tweak max pages / depth / workers / RPS if needed. Defaults are
   conservative (100 pages, 2 RPS/host).
3. Check **Use real browser (Playwright) for every page** only if the
   site blocks static fetchers. Auto-escalation handles most cases.
4. Click **Start crawl**. You'll be redirected to the scan detail page
   which auto-refreshes every 2s while the crawl runs. A **Stop crawl**
   button is visible the whole time.

## Review findings

Once the scan is done:

- **List:** `/scans/<id>/findings` — compact table with thumbnails.
  - Columns: severity, thumbnail, OCR snippet, alt attribute,
    classification, page, status.
  - The alt column uses pills: `missing` (red), `alt=""` (muted), or the
    authored value in quotes.
  - Filter by severity, status, classification, or search text. Filters
    update the URL (back/forward works).
- **Detail:** `/findings/<id>` — image-first layout.
  - The image on the left, OCR text and authored alt side-by-side on the
    right so the decision is a visual glance.
  - Classification, VLM rationale, remediation hint.
  - **Occurrences** table shows every page the image appears on.

### Keyboard shortcuts

Scoped to the findings list and the finding detail page. All
shortcuts are suppressed while you're typing in a form field.

| Key | Action |
|---|---|
| `j` / `k` | Next / previous finding |
| `Enter` | Open focused finding |
| `/` | Focus the filter input |
| `s` | Focus the status dropdown (detail view) |
| `0`–`5` | Set status (`0`=new, `1`=reviewing, `2`=in_progress, `3`=remediated, `4`=accepted_risk, `5`=false_positive) |
| `?` | Toggle the keyboard help panel |

### Status workflow

The status dropdown is the reviewer's verdict. Destructive transitions
(`remediated`, `accepted_risk`, `false_positive`) require a confirmation
re-submit to prevent fat-finger mistakes. Every status change writes a
row to `finding_history` with timestamp + before/after — you can see who
did what when by inspecting the DB.

## Export

From the scan detail page:

- **CSV** — one row per (finding, occurrence). Flat, spreadsheet-friendly.
- **JSON** — nested per finding with `occurrences` array and
  `schema_version` field. Sorted keys so diffs are stable.
- **Jira CSV** — columns Jira Cloud's "External system import" accepts:
  Summary, Description, Priority (critical→Highest, info→Lowest),
  Labels (`wcag-1-4-5`, `sev-<level>`, `class-<vlm_label>`), Component.
- **Markdown report** — stakeholder-friendly: exec summary, severity
  breakdown table, top 20 findings, full findings table.
- **Excel workbook (.xlsx)** — the hand-off deliverable: the whole audit
  report with every section as its own filterable, trackable sheet —
  **Summary** (the at-a-glance dashboard), **Issues Overview** (the
  remediation-guide table: conformance level, owner, status, user impact,
  locations, action, resources), **Page Hotspots** (pages ranked by
  severity-weighted load), **Who's Affected** (issues by the ability each
  blocks), **Coverage & Method** (per-criterion automated-vs-manual coverage),
  and **Test Tracking** (the manual Pass / Fail checklist). Built from the
  same data as the Markdown audit report, so the two never drift.

From the CLI:

```bash
# Most recent scan, CSV, writes to data/exports/scan_<id>.csv
uv run audit export --format csv

# Specific scan to a custom path
uv run audit export 4 --format markdown -o /tmp/report.md

# Use a different base URL for the deep links inside the export
uv run audit export --format jira --ui-base https://audit.internal/

# The Excel remediation-guide workbook (Issues Overview + Test Tracking)
uv run audit export 4 --format xlsx -o /tmp/report.xlsx
```

## Rescan + diff

Run the same seed URL again:

```bash
uv run audit crawl https://example.com/docs/
```

The crawler creates a new scan row (content-addressed images are reused
via `content_hash`). The synthesizer auto-picks the most recent completed
scan of the same logical site as `compare_to` — even across dev-server
port changes on localhost — and writes `first_seen` / `resolved` rows
into `finding_history`.

In the UI, the scan detail page gains a **Diff vs scan #N** link pointing
at `/scans/<new>/diff?compare_to=<old>`, which breaks the change into:

- **New** — `(content_hash, url)` pairs present now but not before.
- **Resolved** — pairs present before but not now.
- **Status changed** — same pair in both scans with different statuses.
- **Still open** — same pair, same open status, unchanged.

Override the auto-diff target:

```bash
uv run audit crawl <url> --compare-to 7
uv run audit synthesize 9 --compare-to 4
```

## Inspect scan state

```bash
uv run audit status                # summary of the latest scan
sqlite3 data/audit.db ".tables"    # poke around the raw data
```

## What to do if a scan gets stuck

See [troubleshooting.md](./troubleshooting.md) — common issues include
Cloudflare challenges, tracking-pixel OCR, and the crawler following
more links than you want (use path scope or `--max-pages`).
