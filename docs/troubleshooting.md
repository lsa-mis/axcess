# Troubleshooting

Quick fixes for the problems people run into most often. The first sections
cover scanning and reports. The last section is for developers working from a
source checkout.

## My scan only fetched one page

The first page probably returned an error. Open the scan page: when the start
address fails, a red notice says "Site URL returned HTTP" with the status code
and the page title.

- **403 with the title "Just a moment..."**: a Cloudflare bot check. Axcess
  opens pages in a real browser by default, but a heavier bot check can still
  block it. If you turned on **Fast crawl without a browser** (or used
  `--static-only`), Axcess uses the browser only for pages that look like a
  bot check or an app that needs scripts, so turn fast crawl off and scan
  again.
- **403 with the title "Access Denied"**: a firewall that refuses automated
  visitors, so Axcess cannot scan the site as it is. Ask the site owner
  whether they can allow your scan.
- **401, or a sign-in page**: the pages need a login. Start a new scan on the
  **Site with a login or 2FA** tab, sign in yourself in the browser window
  Axcess opens, then select **I'm signed in, start scan**. A
  [login scan](./glossary.md#login-scan) needs an `https://` address and a
  site with a public internet address. It runs only in Axcess on your own
  computer, not in a copy hosted for a team.
- **404**: check the address for a typo.

## It's crawling too much or too little

- **Too much.** An address with no path, such as `https://site.example/`, puts
  the whole host in [scope](./glossary.md#scope), and so does **Crawl the
  entire host** (under Advanced settings, **Coverage**). Enter an address with
  a path, such as `https://site.example/blog/`, and leave that switch off.
  Before you start, the line under the address says what will be scanned.
- **Too little.** The path leaves out pages you want. Enter a shorter path, or
  turn on **Crawl the entire host**. Also check **Max pages** (2,500 by default
  in the app, 500 on the command line) and **Max link depth** (10 by default).
- **A new scan continued an old one.** If an earlier scan of the same address
  ended early (for example, Axcess closed mid-scan) and still had pages
  waiting, starting that address again can continue the earlier report.
  Axcess drops queued pages that fall outside the new scope. A scan you stopped
  with **Stop scan** is never continued. If you want a separate report and no
  longer need the earlier one, delete it first with **Delete** on the
  **Reports** list.

## The scan is stuck or very slow

- **Stop it.** Select **Stop scan** on the scan page. Axcess marks the scan as
  interrupted, drops the pages still waiting in its queue, and keeps everything
  it already collected.
- **The site is struggling.** Lower **Requests per second** or **Parallel
  workers** under Advanced settings, **Speed and debugging**, then scan again.
  On the command line, lower `--rps`.
- **Text recognition is slow.** [OCR](./glossary.md#ocr) uses 2 workers by
  default. On a source install, raise `AUDIT_OCR_MAX_WORKERS`. If you only
  need the other checks, turn off **Read text inside images (OCR)**, or pass
  `--skip-ocr`.
- **Local AI is slow.** The optional AI checks add time to every page, which
  is why the app leaves them off by default. The vision model reviews one
  image at a time (`AUDIT_VLM_CONCURRENCY`, default 1), and raising that can
  back up the Ollama service on a small machine.

## The local AI checks aren't running

A [local AI model](./glossary.md#local-ai-model) runs through Ollama, which
you install separately.

- **Is the switch on?** For a public website, the AI switches under Advanced
  settings, **Local AI**, are off by default. **Read text inside images
  (OCR)** is on and needs no AI model. When a switch can't be used, the form
  says why, for example "Ollama is not running on this computer."
- **Is Ollama running?** `curl -s http://localhost:11434/api/tags` should
  return JSON.
- **Is the model installed?** The form names any missing model, and for the
  default vision model it shows the command: `ollama pull qwen3-vl:2b-instruct`.
  Install a model with `ollama pull <model>`. On a source install,
  `AUDIT_VLM_MODEL` picks a different vision model.
- **Want the AI checks off?** Leave the switches off. On the command line they
  are on by default, so pass `--skip-vlm --skip-semantic --skip-visual`. Image
  findings are still created from OCR text and the alt text comparison.

If Ollama can't be reached when a scan starts, Axcess logs a warning and
continues without those checks.

## Verify changes has nothing to compare, or shows a surprise

A [rescan comparison](./glossary.md#rescan-comparison) lives on a report's
**Verify changes** view. It compares the report with the latest earlier
completed report of the same start address.

- **Nothing to compare.** The two start addresses must match. Letter case in
  the host name and a missing trailing slash don't matter, but
  `www.example.edu` and `example.edu`, or two different ports, count as
  different sites. Start the new scan from the same address as the old one.
- **The wrong earlier report.** Add `?compare_to=<earlier report id>` to the
  Verify changes address (`/app/scans/<new id>/diff`). Both reports must be
  completed and share a start address.
- **The command-line image diff.** `audit crawl` picks the earlier scan for
  its image findings by itself, and ignores the port on `localhost` addresses.
  To choose it yourself, pass `--compare-to <id>` to `audit crawl` or
  `audit synthesize`.

## Old "running" scans clutter the list

When Axcess starts, it marks any scan still listed as running as interrupted,
because the process that ran it has ended. If you still see stale rows, that
database hasn't been opened since the restart. Start Axcess (or
`audit serve`) once and they clear.

## I want to start completely over

On a source install, stop Axcess, then delete every report and create a fresh
database. This cannot be undone.

```bash
make clean     # deletes data/audit.db, data/blobs and data/logs
make migrate   # creates an empty database
```

## For developers

### My UI changes aren't showing up

The review app is a React build that Axcess serves from `/app/`. Run
`make frontend-build` again after changing frontend code, then hard refresh
the browser. For quicker iteration, `make frontend-dev` runs the Vite
development server on port 5173 and passes API calls to Axcess on port 8765.

### The axe-core UI tests fail after my change

Run the suite on its own:

```bash
uv run pytest tests/ui/test_accessibility_axe.py -v
```

Each failure lists the rule id (such as `color-contrast` or `label`), its
impact, and the offending selectors. Fix the markup and run it again. The
suite checks the built React app against axe-core's WCAG A, AA, and AAA rules
plus best practices, and fails on any violation by design. It skips itself
when Playwright or the frontend build is missing, so run
`make frontend-build` first.

### I need to dig through the database

```bash
sqlite3 data/audit.db
```

Handy queries:

```sql
-- Latest scans
SELECT id, seed_url, status, page_count, finding_count, started_at
FROM scans ORDER BY id DESC LIMIT 5;

-- Image findings for one scan, highest priority first
SELECT f.severity, f.priority_score, f.status,
       substr(i.src_url_canonical, 1, 60) AS image,
       substr(a.ocr_text, 1, 40) AS ocr
FROM findings f
JOIN images i ON i.id = f.image_id
LEFT JOIN analyses a ON a.image_id = i.id
WHERE f.scan_id = <id>
ORDER BY f.priority_score DESC
LIMIT 20;

-- Page-level results for one scan (rule engines, browser checks, AI), by check
SELECT pipeline, rule_id, COUNT(*) AS occurrences
FROM page_a11y_findings
WHERE scan_id = <id>
GROUP BY pipeline, rule_id
ORDER BY occurrences DESC;

-- Why is the queue big?
SELECT state, COUNT(*) FROM jobs
WHERE json_extract(payload_json, '$.scan_id') = <id>
GROUP BY state;

-- Which pages were rendered in a browser ('js') or fetched without one ('static')?
SELECT render_mode, status_code, COUNT(*)
FROM pages WHERE scan_id = <id>
GROUP BY render_mode, status_code;
```
