# Axcess architecture

This guide explains how Axcess turns a website into an accessibility report:
which code runs, in what order, where the evidence is stored, and what
connects beyond your computer. It is for people who change Axcess. Which
[report group](../glossary.md#report-groups) each check lands in, and why, is
covered in [Detection pipelines](detection-pipelines.md), so this guide links
there instead of repeating the rules.

## The system at a glance

![Diagram of how a scan flows through Axcess. The crawler visits the website you scan and renders each page in a browser, the checks run on every rendered page, results are stored as evidence in a local database and files, grouped into issues, and shown in the review app and exports. Everything except the website runs on your computer, and local AI models are optional.](../images/diagrams/system-architecture.png)

A scan starts at the crawler, which fetches each page in scope and renders it
in Chromium. The checks run on the [rendered page](../glossary.md#rendered-page),
their results are stored as [evidence](../glossary.md#evidence) in SQLite and a
folder of files, and the review app and exports read that evidence back as
[issue groups](../glossary.md#issue-group).

## Where the code lives

![Diagram of where the code lives: crawler, extractor, analyzer, synthesizer, database, web server and React app, exports, protected scan code, and rule files under src/audit, plus top-level modules such as the command line, settings, blob store, and Alfa runner, and next to it the desktop shell, the site generator, and the test suites.](../images/diagrams/code-map.png)

Scan code lives under `src/audit/`, one package per stage, and the YAML files
that tune the checks live in `src/audit/rules/`. The desktop shell
(`desktop/`), the public site generator (`site/`), and the test suites
(`tests/`) sit beside it. The [developer guide](developer-guide.md#project-layout)
has the file-by-file tree.

| Stage | Package | Main entry point |
| --- | --- | --- |
| Crawl and render | `audit.crawler` | `orchestrator.run_crawl`, `js_fetcher.JsFetcher.fetch` |
| Checks in the browser | `audit.analyzer` (`axe.py`, `keyboard/`, `focus/`, `visual/`, `interaction/`, `responsive/`) | `AxeAnalyzer.run` and each probe's `run` |
| Second rule engine (optional) | `audit.analyzer.alfa` and the Node runner in `src/audit/alfa_runner/` | `AlfaAnalyzer.run` |
| Image extraction | `audit.extractor` | `pipeline.process_page` |
| OCR and vision model | `audit.analyzer.ocr`, `audit.analyzer.vlm` | `ocr.pool.OcrPool`, `vlm.ollama.OllamaProvider` |
| AI language checks | `audit.analyzer.semantic` | `registry.build_analyzers` |
| Image finding synthesis | `audit.synthesizer` | `findings.synthesize_findings` |
| Storage | `audit.db`, `audit.blob_store` | `repo`, `queue`, `BlobStore` |
| Issue grouping | `audit.web.issues` | `list_issues`, `get_issue_detail` |
| Web server | `audit.web.server` | `create_app` |
| Exports | `audit.exports` | `csv_export`, `json_export`, `jira_export`, `markdown_report`, `xlsx_export`, `audit_report` |
| Login and protected scans | `audit.protected` | `session.ManualAuthenticationSession` |

`src/audit/mcp_server.py` holds read-only, report-scoped tool functions for a
future conversation feature. It starts no transport, and nothing in `src/`
imports it yet.

## From crawl to report

### Entry points

Every scan goes through `run_crawl` in `src/audit/crawler/orchestrator.py`.
Three callers build its `CrawlConfig`:

- **Command line.** `audit crawl` in `src/audit/cli.py` maps its flags onto a
  `CrawlConfig`. The [developer guide](developer-guide.md#running-scans-from-the-command-line)
  lists the flags.
- **Web form.** `POST /api/scans` in `src/audit/web/server.py` builds the
  config in `_build_crawl_config` and runs the crawl as a background task in
  the server process.
- **Login scan.** `POST /api/local-login-scans` builds a browser-only config
  and opens the sign-in browser, and the crawl starts once you confirm you are
  signed in. See [Authenticated scanning](#authenticated-scanning).

The desktop app runs the same web server as a sidecar
(`src/audit/desktop_server.py`), which applies the database migrations before
it accepts requests.

### What run_crawl does

1. Normalizes the seed URL and builds the [scope](../glossary.md#scope): the
   seed's host plus its path prefix, unless the whole host was requested.
2. Creates a scan row, or adopts one to resume (see
   [Resuming an interrupted crawl](#resuming-an-interrupted-crawl)).
3. Reclaims expired job leases, drops queued jobs that fall outside the scope,
   and seeds the queue with the start page, plus the search page when a search
   journey is configured.
4. Builds each analyzer once for the whole crawl: axe-core, Alfa, the
   keyboard, responsive, focus, visual, and click-through probes, the lazy
   Chromium holder, and the AI language checks.
5. Starts `config.workers` asyncio workers. Each one leases jobs from the
   SQLite queue with a 120 second lease and runs `_process_job`.
6. After the workers finish, runs `synthesize_findings` if the scan completed,
   synthesis is on, and at least one page was fetched. Synthesis covers image
   findings only.
7. Writes the final status, page count, and error count in `_finalize_scan`.

### What happens to each page

`_process_job` handles one URL in this order:

1. **Gatekeeping.** Scope, the blocklist and exclusions, and robots.txt are
   checked again. Skipped pages are counted in memory and logged, not stored.
2. **Fetch.** A plain HTTP fetch, then a render in Chromium. By default
   (`js_eager=True`) every HTML page is rendered. With `--static-only`, only
   pages that look like a script-only shell or a bot challenge are rendered.
   `skip_static_when_rendering` (off by default) skips the plain fetch, and
   login scans are always browser-only.
3. **Record the page** with `_record_page`. The rendered HTML is stored
   gzipped, up to 2,000,000 uncompressed bytes, unless rendered storage is off.
4. **Images.** `process_page` extracts images, stores them, and runs OCR and
   the vision model.
5. **Rule engines.** axe-core results are persisted, then Alfa runs its own
   browser capture of the same URL.
6. **Browser checks.** Keyboard, responsive, focus, visual, and click-through
   results are persisted. These exist only for rendered pages.
7. **AI language checks** run on the page's HTML, which is the rendered DOM
   when the page was rendered. They get no screenshots.
8. **Follow links.** In-scope links from `<a href>`, plus URLs that the
   click-through check and search journeys found, are queued while the depth
   and page limits allow.

### Checks inside the browser, in order

The browser checks run inside `JsFetcher.fetch` (`src/audit/crawler/js_fetcher.py`)
while the page is still open, in a fixed order:

1. axe-core, first, because it needs a quiet DOM.
2. The keyboard check, which presses Tab and Shift+Tab.
3. The focus check.
4. The visual check, which may take a screenshot for the vision model.
5. The click-through check, which operates controls and runs axe-core again on
   each new state. The load-state results are its baseline, so nothing is
   reported twice.
6. The responsive check, last, because it resizes the viewport and injects
   CSS.
7. Circled element screenshots for the findings, up to 100 per page.
8. The configured search journey, only on its entry page.

Results travel back on `FetchResult` fields (`src/audit/crawler/fetcher.py`).
Only axe-core runs again in revealed states. The keyboard, focus, responsive,
and visual checks run once, on the page as it loaded.

## The image-of-text pipeline in detail

This is the original pipeline, and it still works as described here. The
other checks are described in [Detection pipelines](detection-pipelines.md).

### Crawl layer (`audit.crawler`)

- **`url_policy`** gates every link:
  - `normalize(url)` builds the canonical form used as a dedupe key. It keeps
    hash routes such as `#/route` and drops ordinary `#anchors`.
  - `normalize_seed_url(url)` adds a trailing slash to paths that look like
    directories, so `/bicentennial` becomes `/bicentennial/`.
  - `build_scope(seed, whole_host)` and `is_in_scope(url, scope)` check the
    host and the path prefix. `/bicentennial/` does not match
    `/bicentennial-news`.
  - `compare_key(url)` matches pages across scans. It strips the port on
    loopback hosts, so a dev server that changes port does not make every
    finding look new.
  - `is_blocked` and `is_excluded` apply the sign-out and delete blocklist and
    the operator's exclusions.
- **`robots`** caches robots.txt per origin for an hour. A network error or a
  4xx allows everything, and a 5xx disallows everything. `Crawl-delay` is
  parsed, but nothing calls `crawl_delay()`.
- **`fetcher`**: `StaticFetcher` (httpx) returns every response as a
  `FetchResult`. Only true network errors raise.
- **`js_fetcher`**: on a public scan, `JsFetcher` reuses one Chromium for the
  crawl and gives each page a fresh `BrowserContext` at 1440 by 900. Login
  scans and the protected companion reuse the signed-in context instead, and
  login scans also reuse a fixed pool of tabs. It waits for `load`, then up to
  2.5 seconds for network quiet by default.
- **`render_detect`**: `is_js_only(body)` spots script-only shells, and
  `is_challenge_response(status, body)` spots bot challenges, which need a
  403, 429, or 503 status and a known marker.
- **`rate_limit`**: `HostLimiter` pairs a per-host token bucket with a
  per-host semaphore. On a public scan it paces the plain HTTP fetch, and the
  Chromium render runs outside it. Browser-only login scans render inside it.

### Extract layer (`audit.extractor`)

- **`html_images.extract_image_refs(body, base_url)`** returns every image
  reference from `<img>` and `<picture><source>`, and each `srcset` candidate
  is its own reference. CSS background images are not read. The `alt`
  attribute is kept faithfully: `None` means absent, `""` means marked
  decorative.
- **`svg_text.find_inline_svg_text(body)`** finds inline `<svg>` elements with
  visible `<text>`, ignoring `<title>` and `<desc>`. These are flagged without
  OCR or the vision model, and they have no blob.
- **`downloader.ImageDownloader`** fetches image bytes, capped at 25 MiB, and
  writes them through the content-addressed `BlobStore`.
- **`pipeline.process_page`** is the glue: extract, download (deduplicated by
  content hash), upsert rows, and start OCR. While OCR runs, it records the
  inline SVG text. Then it waits for OCR and runs the vision model on the text
  candidates.

### Analyze layer (`audit.analyzer.ocr` and `audit.analyzer.vlm`)

- **`ocr.tesseract.run_tesseract(bytes, lang)`** is a picklable function. It
  uses `image_to_data` for per-word confidences and returns an `OcrResult`
  with the text, mean confidence, word count, and engine version. An image is
  a text candidate at a mean confidence of 60 or more with at least 3 words.
- **`ocr.pool.OcrPool`** runs OCR in a `ProcessPoolExecutor`, 2 workers by
  default (`AUDIT_OCR_MAX_WORKERS`), so CPU-bound OCR runs beside the crawler's
  network work. `in_process=True` exists for deterministic tests.
- **`vlm.base.VlmProvider`** is the protocol: `classify(image_bytes, mime,
  context)` returns a `Classification`.
- **`vlm.ollama.OllamaProvider`** talks to Ollama, by default
  `qwen3-vl:2b-instruct` (`AUDIT_VLM_MODEL`). It checks health first, retries
  with backoff, and hashes the prompt into a `prompt_version`. If the health
  check fails, the crawl continues without the vision model.

### Synthesize layer (`audit.synthesizer`)

- **`alt_compare.compare(alt, visible_text)`** normalizes both strings and
  uses a rapidfuzz token-set ratio plus a substring check. It returns
  `missing`, `inadequate` (including `alt=""` on an image with text, or a
  ratio under 55), `partial` (55 to 84), or `adequate`. `worst()` combines
  the results for an image that appears on many pages.
- **`priority.compute_priority_score(...)`** adds a classification weight
  (essential 4, informational 3, logo 1, decorative 1, otherwise 0), an alt
  weight (missing 3, inadequate 2, partial 1, adequate 0), `log1p` of the
  occurrence count, and 1 if the image is above the fold. `severity_for` maps
  8 or more to critical, 5 or more to major, 2 or more to minor, and the rest
  to info. The crawl never sets `above_fold`, so that point is not applied in
  practice.
- **`rules.RemediationRules`** loads `src/audit/rules/remediation.yaml`. The
  first rule whose `(classification, adequacy)` matches wins, and a
  `classification: "*"` fallback covers inline SVG text and images without a
  vision label.
- **`findings.synthesize_findings(scan_id, compare_to=...)`** writes one
  finding per image with SVG text or an OCR text candidate, keyed on
  `(image_id, scan_id)`. With a previous scan to compare against, it records
  `first_seen` and `resolved` rows in `finding_history` through
  `diff.materialize_history`.
- **`diff.compute_diff(current, prev)`** matches on `(content_hash,
  compare_key(url))` and sorts pairs into `new`, `resolved`, `still_open`, and
  `status_changed`. This is the older image-only diff; the report comparison
  in the app is described in [Issue grouping](#issue-grouping-and-report-groups).

## Storage

`data/audit.db` and `data/blobs/` are the source of truth for a report.
Exports and the review app are views of them.

### SQLite database

`audit.db.schema.connect` opens every connection in WAL mode with foreign keys
on and a 5 second busy timeout. The schema lives in
`src/audit/db/migrations/` as 29 numbered forward migrations (`0001` to
`0029`), each paired with a `.rollback.sql` file.

- `make migrate` applies them with yoyo for a source install.
- The desktop sidecar applies them at startup, under a file lock.
- Tests skip yoyo and run every forward `.sql` file in filename order.

### Main tables

| Migration | Tables | What they hold |
| --- | --- | --- |
| `0001` | `scans`, `pages`, `images`, `page_images`, `analyses`, `findings`, `finding_history`, `jobs` | Reports, fetched pages, unique images and each place they appear, OCR and vision results, image findings and their status history, and the job queue |
| `0002` | `page_a11y_findings` | Every page-scoped result: axe-core, Alfa, the browser checks, and the AI language checks |
| `0009` | `evaluation_reports`, `manual_check_results`, `manual_check_evidence` | Expert evaluation records and manual WCAG decisions, kept apart from the crawl's evidence |
| `0011` | `protected_scans`, `protected_agent_enrollments`, `protected_audit_events`, `protected_artifacts` | Protected companion metadata and encrypted evidence |
| `0019` | `a11y_finding_history` | Status history for `page_a11y_findings` |
| `0025` | `scan_search_runs` | The outcome of each configured search journey |
| `0026` | `scan_interaction_runs` | A per-page ledger of the click-through check |
| `0028` | `page_dom_states` | Markup of click-revealed states that held a new finding |

Later migrations also add columns. For example, `scans` gained
`axe_pages_scanned` and `axe_violations_total` (`0002`), per-method coverage
counters (`0020`), and `failure_reason` (`0021`), and `pages` gained
`final_url` (`0023`) and `rendered_html` (`0027`).

`scans.config_json` snapshots the crawl settings, including which checks were
on. It does not record model names, the vision prompt, OCR thresholds, or the
AI language criteria.

### The pipeline discriminator

`page_a11y_findings.pipeline` says which check wrote a row. Its CHECK
constraint (last widened in `0012`) allows exactly these values:

| Value | Written by | Added in |
| --- | --- | --- |
| `axe` | axe-core, plus click-through and search results, which carry `revealed_by` | `0003` (the column default) |
| `semantic` | The AI language checks, with `rule_id` set to `semantic:<criterion>` | `0003` |
| `keyboard` | The keyboard trap check | `0004` |
| `responsive` | The reflow, zoom, and text spacing checks | `0005` |
| `focus` | The focus not obscured and positive tabindex checks | `0006` |
| `visual` | The motion, autoplay audio, and meaningful sequence checks | `0007` |
| `alfa` | Siteimprove Alfa | `0010` |
| `protected_image` | Image-of-text leads from the protected companion | `0012` |

Two things trip people up:

- `image` is not a database value. It is the issue pipeline for rows from the
  `findings` table.
- The dedupe key is `UNIQUE (page_id, rule_id, target_hash)`, and it ignores
  `pipeline`. A new check must use rule IDs no other check uses, which is why
  the focus check prefixes its IDs.

SQLite cannot change a CHECK constraint in place, so adding a value means
rebuilding the column. `0012_protected_image_pipeline.sql` is the latest
rebuild. A new one must also drop and recreate the index
`idx_a11y_rule_lookup` from `0029_hot_path_indexes.sql`, or SQLite refuses to
drop the column. [Adding a check](adding-a-check.md) has the full recipe.

### Content-addressed blobs

Downloaded images and the PNG element screenshots live in `data/blobs/` at
`<aa>/<sha256>.<ext>`, where `aa` is the first two hex characters of the
hash. `BlobStore` writes to a temporary file and renames it, so a killed
process never leaves a torn file, and storing the same bytes again does
nothing.

- Inline SVG findings have no blob: `blob_path` is NULL and `has_svg_text` is
  1.
- The server serves blobs at `/blobs/{content_hash}`, except blobs referenced
  by a protected scan.
- Deleting a report never deletes blob files, because another report may use
  them.

### Resuming an interrupted crawl

Every unit of work is a row in `jobs`. A worker leases a job, processes it, and
marks it completed or failed. `queue.reclaim_expired` returns stale leases to
the queue at the start of every crawl, for example after a laptop slept.

A crawl of the same seed URL resumes an existing report when `_ensure_scan`
finds one:

- a `running` row is always adopted;
- an `interrupted` row is adopted only while it still has queued jobs;
- protected reports and reports marked not resumable are never adopted.

Stopping a scan from the app clears its queue, so a stopped scan is not
resumed. Login scans are never resumable.

## Issue grouping and report groups

Nothing is grouped at write time. `issues.list_issues` in
`src/audit/web/issues.py` builds issue groups at read time from two sources:

- `_axe_issue_rows` groups `page_a11y_findings` by `(pipeline, rule_id)`
  through `a11y_queries.grouped_by_rule`. Alfa groups are also split by
  outcome, so "failed" and "cannot tell" never share a group.
- `_image_issue_rows` groups image findings by `(classification,
  alt_adequacy)` through `image_findings_queries.grouped_by_remediation`.

| Issue key | Source |
| --- | --- |
| `axe:<rule_id>` | axe-core, including click-through and search results |
| `alfa:<rule_id>:<failed or cant_tell>` | Siteimprove Alfa |
| `semantic:<criterion>` | AI language checks |
| `<pipeline>:<rule_id>` | The keyboard, responsive, focus, visual, and protected image checks |
| `image:<classification>_<adequacy>` | Image-of-text findings |

Each row gets a `review_lane` of `likely_barrier`, `expert_review`, or
`informational`, which the Issues table shows as
[Barrier](../glossary.md#barrier), [Needs review](../glossary.md#needs-review),
and [Informational](../glossary.md#informational). By default, rows sort by
group first, then by priority within a group. [Detection pipelines](detection-pipelines.md)
explains which checks land in which group and where to change it.

The API, the workbook, and the audit report all read this one projection. The
[rescan comparison](../glossary.md#rescan-comparison) in
`src/audit/web/comparison.py` compares it between two reports, sorting results
into new, still detected, changed, no longer detected, and cannot compare.

## Web server and review app

`create_app` in `src/audit/web/server.py` builds the FastAPI app:

- JSON routes live under `/api/`.
- `/app/` and every path below it serve the built React app, `/app/assets/`
  and `/app/fonts/` serve its files, and `/` redirects to `/app/`.
- Without `make frontend-build`, `/app/` answers with a 503 notice that the
  frontend bundle is not built.
- `/blobs/{content_hash}` serves stored images and screenshots, and `/health`
  answers uptime checks.

The React app lives in `src/audit/web/frontend/` (Vite, React, and
TypeScript). Pages are in `src/routes/`, and the typed API client is in
`src/api/client.ts` and `src/api/types.ts`. Keep those types in step with the
API responses.

When `AUDIT_ACCESS_TOKEN` is set, every request except `/health` and the
protected APIs must carry the token. It is an ingress gate, not user identity;
the [hosting guide](../hosting.md) covers shared use.

## Exports

Exports read the database when you ask for one, through
`GET /api/scans/{id}/export/{fmt}` or `audit export`.

| Format | Built from | In the app's Export menu | On the command line |
| --- | --- | --- | --- |
| `xlsx` (remediation workbook) | `issues.list_issues` on a live connection | Yes | Yes |
| `audit` (audit report, Markdown) | `issues.list_issues` on a live connection | Yes | No |
| `csv` (one row per finding) | `collector.collect_scan` | Yes | Yes, the default |
| `json` (full evidence payload) | `collector.collect_scan` | Yes | Yes |
| `jira` (Jira CSV) | `collector.collect_scan` | No | Yes |
| `markdown` (evidence inventory) | `collector.collect_scan` | No | Yes |

- **Draft gating.** A final export needs a completed expert evaluation. The
  app's menu always asks for a draft, so its downloads are marked
  [DRAFT](../glossary.md#draft-export) until review is complete. The command
  line does no readiness check and no draft labeling.
- **Protected reports.** The export route and the command line both refuse
  them. The protected report page offers a separate redacted summary.
- **Webhook.** `src/audit/exports/webhook.py` can post the JSON payload to
  `AUDIT_WEBHOOK_URL`, but nothing calls it today.

[Reading your report](../reading-your-report.md) describes the exports for the
people who use them.

## Process model: one process, one crawl

Axcess is built for one host and one writer process. SQLite runs in WAL mode,
and `data/audit.db` is a single file on local disk.

- **One active crawl per process.** The web server tracks the running crawl in
  `crawl_state`, in memory, inside `create_app`. A second scan request gets
  HTTP 409, "A crawl is already running." Login scans share the same guard.
- **The web server writes too.** Status changes, bulk status updates, manual
  checks and their evidence, expert evaluations, cancels, and deletions all
  write from request handlers. Each request opens its own connection, and
  SQLite serializes the writes, waiting up to the 5 second busy timeout.
- **The crawl runs inside the server.** A scan started from the app is an
  asyncio task in the web server process.
- **The command line is separate.** `audit crawl` runs `run_crawl` in its own
  process and cannot see `crawl_state`. Avoid crawling from the command line
  while the server is crawling against the same database.
- **Helper processes.** OCR uses a process pool, Alfa runs as a Node child
  process, and Chromium runs as its own processes. They send results back to
  the crawl; only the crawl writes them to the database.

## Authenticated scanning

Axcess has two ways to scan pages behind a sign-in. They share browser code in
`src/audit/protected/` but are separate features.

### Local login scan

![Diagram of a login scan. You choose "Site with a login or 2FA", Axcess opens a visible browser, you sign in directly with the site including any two-factor step, then select "I'm signed in, start scan". Axcess moves the session in memory to its scanning browser, crawls from where you landed, and deletes the temporary browser profile when the scan ends. Login scans need an HTTPS site whose address resolves to a public IP address.](../images/diagrams/login-scan-flow.png)

You sign in yourself in a visible browser, and Axcess scans with that session
without ever seeing your password. This is the [login scan](../glossary.md#login-scan)
that the desktop app offers.

How it works:

1. `POST /api/local-login-scans` opens a visible Chromium with a fresh,
   temporary profile under the system temp folder
   (`axcess-protected-browser`, mode 0700), at the page you typed.
2. You complete the full sign-in, including any two-factor step. During
   sign-in the browser may reach any public HTTPS host, so identity providers
   and two-factor services work.
3. "I'm signed in, start scan" calls `POST /api/local-login-scans/{id}/confirm`.
4. By default, the session's cookies and storage are copied in memory into a
   new headless Chromium, and the sign-in window closes. With "Show the
   scanning browser window", the scan reuses the signed-in tabs instead.
5. The crawl starts where sign-in landed, and the scope still comes from the
   URL you typed.
6. When the scan ends, `session.close()` shuts the browsers and deletes the
   temporary profile.

Rules that are fixed for login scans:

- The request must come from the same computer (loopback, matching origin).
- The start URL must use HTTPS and a DNS name, not an IP address,
  `localhost`, or `.local`, and every request must resolve to a public
  address. Private or loopback hosts are refused.
- robots.txt is ignored, the crawl is browser-only, the AI language and visual
  checks are off, the focus check is on, and the scan cannot be resumed.
- The vision model, if used, must be Ollama on a literal loopback address.

A login scan is an ordinary `scans` row with no `protected_scans` row. By
default it stores rendered HTML and element screenshots of signed-in pages in
the normal, unencrypted database and blob folder; "Don't store rendered pages"
turns both off. The server log records each page's URL and title.

### Protected companion (off by default)

A protected scan is a separate, hosted deployment feature, turned off unless
`AUDIT_PROTECTED_SCANS_ENABLED` is set. It needs a signed identity-aware proxy,
a companion mTLS proxy, a public origin, and a key vault that can destroy each
scan's key. The auditor runs `axcess-companion pair` and `axcess-companion run`
on their own computer.

Only an opaque, redacted issue index comes back to the server, with no URLs,
selectors, screenshots, or raw HTML. Its evidence is encrypted per scan and
kept for 7 days, and `audit protected-maintenance` runs the cleanup.
[Protected scans](protected-scans.md) covers deployment.

## Data and network boundary

![Diagram of what stays on your computer. Reports, stored pages, screenshots, images, and logs stay in local files, and optional Ollama runs locally. Axcess connects to the website you scan and, in the desktop app, to GitHub once per launch to check for updates. Links such as "Rule docs" and "Give feedback" open in your browser only when you click them. It has no account, telemetry, or upload. Files are not encrypted, and deleting a report keeps its image and screenshot files.](../images/diagrams/privacy-boundary.png)

Reports, stored pages, screenshots, images, and logs stay in local files.
Axcess connects to the website you scan, to an optional AI service that
normally runs on your computer, and, in the desktop app, to GitHub to check
for updates when the app window opens. This is what
[local-first](../glossary.md#local-first) means in practice.

### What stays local

- A source install keeps `data/audit.db`, `data/blobs/`, and
  `data/logs/axcess.log` (the web server's log, rotated at 5 MB with 3
  backups). The command line does not write that log file.
- The desktop app points the same settings at a `data` folder inside its
  user-data folder.
- Nothing is encrypted for public or login scans. Only protected companion
  artifacts are encrypted.

### What connects beyond your computer

| Destination | When | Code |
| --- | --- | --- |
| The website you scan | Every scan: the plain HTTP fetch, the Chromium render, and Alfa's separate capture. A render also loads the page's own subresources from whatever hosts it names, such as CDNs. Only the click-through check's guard blocks cross-origin requests, and only while it operates controls. | `crawler/fetcher.py`, `crawler/js_fetcher.py`, `analyzer/alfa.py`, `analyzer/interaction/safety.py` |
| The website you scan, from the page inspector | Opening a stored page: the capture gets the page's URL as `<base href>`, so the reviewer's browser loads that site's stylesheets, fonts, and images live. Its scripts never run. With no stored capture, the server renders the page again in a throwaway browser. | `frontend/src/routes/Inspector.tsx`, `web/page_inspector.py` |
| Sign-in and two-factor services | Login scans only, while you sign in | `protected/session.py`, `protected/egress.py` |
| Ollama, if you use it | The vision model, the visual reading-order check, the AI language checks, and one model-list request when the New scan form opens. The default address is `http://localhost:11434` (`AUDIT_OLLAMA_BASE_URL`). Axcess never pulls a model. | `config.py`, `web/server.py` |
| `api.github.com`, desktop app only | The update check, each time the app window opens (on macOS, also when the Dock icon reopens a closed window), until a newer release has been offered. It is skipped when the app runs unpackaged in development and when `AXCESS_DISABLE_UPDATE_CHECK=1`, and nothing downloads without a click. | `desktop/src/updates.cjs`, `desktop/src/main.cjs` |

Public scans do not check that the Ollama address is on your computer; login
scans do. Paths in the table are relative to `src/audit/` unless they start
with `desktop/`.

Apart from stored pages opened in the page inspector (see the table), the
review app's own interface makes no third-party requests. Its fonts are
vendored in `src/audit/web/frontend/public/fonts/` and served from
`/app/fonts/`, never from a CDN. The comment at the top of
`src/audit/web/frontend/src/fonts.css` relies on this promise, but its wording
is out of date: it cites `docs/architecture.md` and says the only runtime
network call is to the site being audited, which the table above corrects.
Update that comment the next time you change `fonts.css`, and keep both in
step if you add any external asset.

### Working offline

These downloads happen once, at setup:

- Python packages through `uv sync`, pinned by `uv.lock`.
- Chromium through `playwright install chromium`.
- The Alfa runner's pinned npm packages, if you run `make alfa-install`.
- Ollama models, if you pull them yourself.

Nothing else is installed at scan time. axe-core 4.10.2 is bundled at
`src/audit/web/static/axe.min.js`, the public suffix list comes from
tldextract's bundled snapshot, and the Alfa runner fetches no packages.
