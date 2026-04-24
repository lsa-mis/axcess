# Troubleshooting

## "My scan only fetched one page"

The seed URL probably returned a non-2xx response. Open the scan
detail page — if the seed status was 4xx/5xx you'll see a red banner
showing the status code and the page title.

- **403 with title "Just a moment…"** — Cloudflare bot challenge. The
  auto-escalation path should re-fetch via Playwright, but it can
  miss heavier challenges. Rerun with **Use real browser (Playwright)
  for every page** checked (or `audit crawl --use-js`).
- **403 with title "Access Denied"** — WAF without a JS challenge.
  Nothing the tool can do — the site is refusing automated traffic.
- **401 / login wall** — the tool doesn't do auth. You'd need to
  scan a staging/dev mirror.
- **404** — typo in the seed URL.

## "It's crawling too much / too little"

- **Too much.** The seed URL has no path prefix (`https://site.com/`
  or the box wasn't trailing-slashed and somehow resolved to the
  root). Inspect `scans.config_json` — if `whole_host: true`, the
  scope is deliberately whole-host. Fix: enter the seed with a path,
  e.g. `https://site.com/blog/`, and leave the "Crawl the entire
  host" checkbox unchecked. Reload the form to see the live **Scope**
  preview.
- **Too little.** Your seed path excludes content you want. Enter a
  shallower path or tick "Crawl the entire host". Also make sure
  `max_depth` isn't artificially low.
- **Stale queue from a previous scan.** If you re-submit the same
  seed URL, `_ensure_scan` reuses the existing `running`/`interrupted`
  scan row. The orchestrator now auto-purges out-of-scope pending
  jobs on resume, but if you want a fresh start just stop the scan
  and run `DELETE FROM jobs WHERE
  json_extract(payload_json,'$.scan_id')=<id>` in the DB.

## "The scan is stuck or super slow"

- **Stop it.** Click **Stop crawl** on the scan detail page (or POST
  `/scans/<id>/cancel`). It flips status to `interrupted` and drops
  pending jobs.
- **Too many workers tripping rate limits.** Lower `--workers` or
  `--rps` and rerun.
- **Lots of CPU-bound OCR.** Set `AUDIT_OCR_MAX_WORKERS` higher (it
  defaults to 2). Or run with `--skip-ocr` if you just want to
  enumerate images.
- **Ollama queue.** If `vlm_concurrency` is too high the Ollama
  daemon backs up. Default is 1 for small models.

## "Ollama isn't classifying anything"

- **Is the daemon running?** `curl -s http://localhost:11434/api/tags`
  should return JSON.
- **Is the model pulled?** `ollama pull qwen2-vl:2b`. The default
  model name lives in `Settings.vlm_model`; override with
  `AUDIT_VLM_MODEL=<name>`.
- **Do you want VLM off?** `--skip-vlm` bypasses the stage entirely;
  findings still get synthesized using OCR + alt comparison.

## "Nothing changed between rescans but I see a diff"

Usually a URL canonicalization drift — different port on localhost,
or `www.` vs apex. Check the URLs in each scan's `pages` table. If
`compare_to` wasn't auto-discovered across the port change, the
`compare_key` in `audit.crawler.url_policy` isn't matching. Pass
`--compare-to <id>` explicitly as a workaround while you diagnose.

## "Stale 'running' scans clutter the list"

On server boot, `create_app` sweeps any `running` scan and flips it
to `interrupted` — the in-process asyncio task that was driving it is
gone after a restart. If you're seeing stale rows, you're probably
looking at a DB the web server hasn't opened yet. Start the server
(`audit serve`) once and they'll clear.

## "I want to start completely over"

```bash
rm -rf data/audit.db* data/blobs data/logs
make migrate
```

## "My UI changes aren't showing up"

Hard refresh the browser — the CSS and HTMX are cached aggressively by
default. Static files sit under `src/audit/web/static/` and are mounted
at `/static`.

## "Axe-core a11y tests fail after my template change"

Run `uv run pytest tests/ui/test_accessibility_axe.py -v`. The failure
message lists the rule id (`color-contrast`, `label`, etc.) and the
offending selector. Fix the markup and retest. The suite fails the
build on any WCAG 2.1 AA violation — by design.

## "I need to dig through the DB"

```bash
sqlite3 data/audit.db
```

Handy queries:

```sql
-- Latest scan summary
SELECT id, seed_url, status, page_count, finding_count, started_at
FROM scans ORDER BY id DESC LIMIT 5;

-- Findings for one scan, highest priority first
SELECT f.severity, f.priority_score, f.status,
       substr(i.src_url_canonical, 1, 60) AS image,
       substr(a.ocr_text, 1, 40) AS ocr
FROM findings f
JOIN images i ON i.id = f.image_id
LEFT JOIN analyses a ON a.image_id = i.id
WHERE f.scan_id = <id>
ORDER BY f.priority_score DESC
LIMIT 20;

-- Why is the queue big?
SELECT state, COUNT(*) FROM jobs
WHERE json_extract(payload_json, '$.scan_id') = <id>
GROUP BY state;

-- What pages got fetched under what render mode?
SELECT render_mode, status_code, COUNT(*)
FROM pages WHERE scan_id = <id>
GROUP BY render_mode, status_code;
```
