# Developer guide

This guide is for people who change Axcess code. It covers where things live,
the conventions, running scans from the command line, recipes for common
changes, and how the tests work. Setup and the quality gates are in the
[contributing guide](../../CONTRIBUTING.md), and the
[architecture guide](architecture.md) explains how a scan flows from crawl to
report.

## Project layout

```text
src/audit/
  cli.py                      the `audit` command (typer)
  config.py                   Settings from AUDIT_* environment variables
  logging.py                  structlog setup and the web server's log file
  blob_store.py               BlobStore: content-addressed files in data/blobs/
  coverage_matrix.py          loads rules/wcag_coverage.yaml
  evaluation.py               expert evaluation records and manual checks
  quality_benchmark.py        labeled corpus precision gate (make quality-gate)
  detection_evals.py          efficacy, efficiency, and scale evals
  desktop_server.py           desktop sidecar: migrate, then serve on loopback
  mcp_server.py               read-only report tools; no transport yet

  crawler/
    orchestrator.py           run_crawl: queue, workers, per-page pipeline
    url_policy.py             normalize, scope, blocklist, compare_key
    robots.py                 RobotsChecker (per-origin cache)
    fetcher.py                StaticFetcher (httpx) and FetchResult
    js_fetcher.py             JsFetcher (Playwright Chromium) and in-browser checks
    render_detect.py          is_js_only, is_challenge_response
    rate_limit.py             HostLimiter (token bucket and semaphore)
    search.py                 configured search journeys
    sitemap.py                sitemap parser (the crawl does not use it)

  extractor/
    html_images.py            extract_image_refs(body, base_url)
    svg_text.py               find_inline_svg_text(body)
    downloader.py             ImageDownloader and DownloadedImage
    pipeline.py               process_page: per-page image glue

  analyzer/
    axe.py                    AxeAnalyzer: runs the bundled axe-core
    alfa.py                   AlfaAnalyzer: drives the Node runner in alfa_runner/
    alfa_evidence.py          bounds and parses Alfa evidence
    keyboard/                 keyboard trap check
    responsive/               reflow, 200% zoom, and text spacing checks
    focus/                    focus not obscured and positive tabindex checks
    visual/                   motion, autoplay audio, meaningful sequence
    interaction/              click-through check and its network guard
    semantic/                 AI language checks: analyzers/, prompts/, registry.py
    ocr/                      run_tesseract and OcrPool
    vlm/                      VlmProvider, OllamaProvider, vision.py, prompts/
    ollama_base.py            shared Ollama client (retries, health check)
    model_registry.py         model picks from rules/analyzer_models.yaml
    model_registry_dump.py    prints the model matrix (make list-analyzer-models)

  synthesizer/
    alt_compare.py            AltAdequacy, compare(), worst()
    priority.py               image priority score and severity_for
    rules.py                  RemediationRules loader
    findings.py               synthesize_findings (image findings)
    diff.py                   compute_diff and materialize_history (images)

  db/
    schema.py                 connect(db_path): WAL, foreign keys, busy timeout
    migrations/               yoyo .sql files, each with a .rollback.sql
    repo.py                   typed upsert helpers
    queue.py                  enqueue, lease, complete, reclaim_expired

  exports/
    collector.py              collect_scan: shared data for every export
    csv_export.py
    json_export.py
    jira_export.py
    markdown_report.py        evidence inventory
    xlsx_export.py            remediation workbook
    audit_report.py           audit report (Markdown)
    interaction_coverage.py   click-through coverage text (workbook, audit report, Jira)
    webhook.py                env-gated webhook; nothing calls it yet

  web/
    server.py                 FastAPI app factory (create_app): /api/* and the app
    issues.py                 unified issue projection (list_issues)
    a11y_queries.py           queries and grouping for page_a11y_findings
    image_findings_queries.py queries and grouping for image findings
    comparison.py             rescan comparison between two reports
    export_readiness.py       final or draft export gating
    page_inspector.py         page and DOM inspector renderer
    coverage_status.py        shipped checks and roadmap for /tracking and the site
    protected_api.py          protected companion API
    protected_auth.py         identity checks for protected routes
    static/axe.min.js         bundled axe-core 4.10.2, the engine scans use
    frontend/                 React app (Vite, Tailwind), served at /app/
      src/routes/             one component per page
      src/components/         shared components
      src/api/                typed client (client.ts) and types (types.ts)
      dist/                   npm run build output (not committed)

  protected/                  login-scan browser session and protected companion
    session.py                visible sign-in browser and session handoff
    egress.py                 network policy for login and companion browsers
    companion.py              the protected companion's worker
    crypto.py, vaults.py, repository.py, retention.py, redaction.py, export.py,
    handoff.py, local_ai.py, models.py

  rules/
    wcag_coverage.yaml        per-criterion coverage matrix (WCAG 2.2 A and AA)
    audit_report.yaml         issue cards: titles, why it matters, fix steps
    remediation.yaml          image hints keyed on (classification, adequacy)
    analyzer_models.yaml      model picks for the AI checks

  alfa_runner/                Node runner for Siteimprove Alfa (make alfa-install)

desktop/                      Electron shell: main.cjs, runtime.cjs, updates.cjs
site/                         public site generator (build.py) and its pages
scripts/                      fixture site server, model fetch, export diff
tests/
  unit/                       fast, hermetic
  integration/                real crawls of tests/fixtures/site
  ui/                         FastAPI routes, plus Playwright and axe-core
  quality/                    labeled detection corpus and its gates
  fixtures/                   fixture site, sample evidence images, Vue search app
  support/                    shared test helpers (export rendering, goldens)
```

## Conventions

- **Strict typing.** mypy runs in strict mode on `src/audit` (`mypy.ini`), in
  CI and in `make typecheck`. No `Any` unless you justify it with a comment.
- **Explicit imports.** No `from foo import *`. Use absolute imports from
  `audit.*`.
- **Dataclasses for value objects.** Freeze them where the thing is
  conceptually immutable (`HostScope`, `ExportFinding`, `FetchResult`).
- **Module-level functions for anything that must be picklable.** The OCR
  process pool dispatches `audit.analyzer.ocr.tesseract.run_tesseract`
  directly.
- **Logs are structlog.** Write `log.info("namespace.event", key=value)` and
  keep event names lowercase and dotted. Every log line from a crawl carries
  its `scan_id`.
- **Tests are specific about what they verify.** Unit tests use `tmp_db` (a
  fresh migrated SQLite database) and `tmp_path` (a fresh blob folder).
  Integration tests serve `tests/fixtures/site` from a standard library HTTP
  server on a spare port.
- **Browser tests share one Chromium per module, never a context.** Open
  pages through the module's own `page` fixture (tests/integration, built on
  `browser.new_context()`) or through `new_page` (tests/ui); either way each
  test gets a context of its own, closed when it ends. Playwright only works
  on the event loop that launched it, so mark the module
  `pytestmark = pytest.mark.asyncio(loop_scope="module")` and give async
  fixtures that touch the browser `loop_scope="module"`. Never put a bare
  `@pytest.mark.asyncio` on such a test: it overrides the module's mark, and
  the test would hang instead of failing, so collection refuses it.

## Running gates

Every `make` gate, what it runs, and which ones CI runs are listed in the
[contributing guide](../../CONTRIBUTING.md#quality-gates). Two settings matter
while you code:

- Ruff selects E, W, F, I, B, C4, UP, N, S, SIM, RET, and RUF, with a
  100-character line limit (`.ruff.toml`). Under `tests/`, `assert` and
  hard-coded test passwords are allowed (S101, S106, S107).
- mypy checks `src/audit` only. Tests are not type-checked.

## Running scans from the command line

The `audit` command is installed by `make setup`. Run it from the repository
root with `uv run audit`, after `make migrate` has created the database. To
try a crawl without touching a real site, run `make fixture-site` and crawl
`http://127.0.0.1:8000/`.

| Command | What it does |
| --- | --- |
| `audit crawl URL` | Crawls and checks a site, stores a new report, or resumes an interrupted crawl of the same URL |
| `audit status` | Shows the latest report's status, pages, and errors. Its findings count covers image-of-text findings only. |
| `audit export [SCAN_ID] --format FORMAT` | Writes a report to a file. Formats are `csv` (the default), `json`, `jira`, `markdown`, and `xlsx`. |
| `audit synthesize [SCAN_ID]` | Recomputes image-of-text findings without crawling again |
| `audit serve` | Serves the review app, by default at `http://127.0.0.1:8765/` |
| `audit protected-maintenance` | Runs the retention cleanup for protected reports |
| `audit protected-companion pair` or `run` | The companion commands for [protected scans](protected-scans.md) |

`audit export` writes to `data/exports/scan_<id>.<ext>` unless you pass
`--output`, and it defaults to the latest report. It does no draft labeling,
and it refuses protected reports. The audit report format is available only
from the app.

Useful `audit crawl` flags:

| Flag | Default | What it does |
| --- | --- | --- |
| `--max-pages`, `-n` | 500 | Stops after this many fetched pages |
| `--max-depth`, `-d` | 10 | Limits how many links deep the crawl goes |
| `--whole-host` | Off | Crawls the whole host instead of the start URL's path |
| `--include-subdomain` | Off | Follows links onto subdomains |
| `--rps` | 2.0 | Maximum requests per second per host |
| `--block TEXT` | Sign-out and delete patterns | Adds a URL substring never to visit. Repeatable. |
| `--exclude PREFIX` | None | Adds a URL or path prefix never to visit. Repeatable. |
| `--allow-session-ending-urls` | Off | Drops the built-in blocklist (`/logout`, `/delete`, `/remove`, `/signout`, `/sign-out`, `/log-out`) and ignores any `--block` patterns |
| `--ignore-robots` | Off | Skips robots.txt, for authorized testing only |
| `--static-only` | Off | Fetches without a browser and renders only script-only pages and bot challenges. The browser checks skip every page it does not render. |
| `--skip-interaction` | Off | Skips the click-through check of menus, tabs, and dialogs |
| `--no-store-rendered` | Off | Keeps no copy of each page's rendered HTML. The page inspector then renders the live page on demand. |
| `--skip-screenshots` | Off | Skips the circled element screenshots |
| `--axe-level` | AA | Sets the axe-core level: A, AA, or AAA |
| `--compare-to SCAN_ID` | The last completed scan of the same site | The report to compare image findings against |

Each check also has an off switch: `--skip-axe`, `--skip-keyboard`,
`--skip-responsive`, `--skip-focus`, `--skip-visual`, `--skip-ocr`,
`--skip-vlm`, and `--skip-semantic`. `--skip-synthesize` skips the image
finding synthesis at the end, and `--semantic-criteria 2.4.4,3.3.2` narrows
the AI language checks. Run `uv run audit crawl --help` for the full list.

The command line differs from the app's New scan form in a few ways:

- Every check is on by default, including the vision model, the AI language
  checks, and the visual check, which the form leaves off. If Ollama is not
  reachable, the model-based passes are skipped with a warning and the crawl
  continues.
- There is no option for Siteimprove Alfa. Choose it in the app instead.
- It uses 4 workers and a 500 page limit, where the form uses 8 workers and
  2,500 pages.
- Ctrl-C interrupts the crawl. Run the same command again to resume it.

## Common extension tasks

### Add a new export format

1. Write a renderer in `src/audit/exports/<fmt>_export.py`. The CSV, JSON,
   Jira, and Markdown renderers take the `ExportScan` from
   `collector.collect_scan`; the workbook and audit report also need the live
   connection.
2. Register it in `audit.web.server`: `_EXPORT_RENDERERS`,
   `_EXPORT_MEDIA_TYPES`, and `_EXPORT_EXTENSIONS`.
3. Teach `label_draft_export` in `audit.web.export_readiness` how to mark a
   draft in the new format. Otherwise drafts go out unlabeled.
4. If the command line should offer it, add it to `_EXPORT_FORMATS`,
   `_EXPORT_EXT`, and the renderer dispatch in `cli.py`.
5. Add it to `EXPORT_EXTENSIONS` in `tests/support/export_render.py`.
   `tests/unit/test_export_goldens.py` fails until the test harness renders
   every route format.
6. If the app should offer it, add it to `FORMATS` in
   `src/audit/web/frontend/src/components/ExportMenu.tsx`.
7. Record the golden files with `AUDIT_UPDATE_GOLDEN=1` (see
   [Testing](#testing)), review the diff, then run the tests again without it.

### Final exports and the expert evaluation

An export is final, not a [draft](../glossary.md#draft-export), only when the
scan has a completed expert evaluation. The evaluation lives in the
`evaluation_reports` table (migration `0009`), and `src/audit/evaluation.py`
holds its logic.

- `GET /api/scans/{id}/evaluation` reads the record, and
  `PUT /api/scans/{id}/evaluation` updates it for a completed scan. The body
  (`EvaluationUpdate` in `server.py`) holds the target standard and level,
  purpose, included and excluded scope, sample description, reviewer,
  methods note, limitations, and `status` (`draft`, `in_progress`, or
  `completed`).
- Setting `status` to `completed` returns 409 `evaluation_not_ready` with a
  list of blockers until the reviewer, purpose, included scope, methods used,
  and limitations are filled in. Every WCAG A and AA manual check also needs
  an outcome with a rationale, and none may still need follow-up.
- A final export also needs every finding behind a Barrier or Needs review
  issue to have a review status of in progress, remediated, accepted risk, or
  false positive (`assess_public_export_readiness` in
  `src/audit/web/export_readiness.py`). If anything is missing, the export
  route returns 409 unless the request adds `?draft=acknowledged`, which
  downloads a labeled draft instead.

No screen in the review app calls these routes today. `api/client.ts` has
`getEvaluation` and `updateEvaluation`, and client functions for the manual
check routes (`GET /api/scans/{id}/manual-checks`,
`PATCH /api/scans/{id}/manual-checks/{sc}`, and
`POST /api/scans/{id}/manual-checks/{sc}/evidence`), but nothing uses them.
So completing the evaluation and the manual checks needs the API today.

The export menu always sends `?draft=acknowledged`, but that flag only matters
while something is missing: once the evaluation is completed with no
blockers, the same menu downloads a final export. The CLI's `audit export`
skips this check and writes unlabeled files whatever the evaluation state.

### Swap the OCR backend

1. Write a module that exposes a picklable function taking
   `(bytes, lang)` and returning an `OcrResult`. `ProcessPoolExecutor` must be
   able to import it, so use a top-level `def`, not a closure.
2. Point `analyzer.ocr.pool.OcrPool` at it by editing the
   `run_in_executor(self._executor, run_tesseract, ...)` call, or make it
   pluggable with an `engine` argument.
3. Make `OcrResult.engine_version` identify your backend and version, so
   cached analyses do not collide.

### Swap the VLM backend

1. Implement the `VlmProvider` protocol from `audit.analyzer.vlm.base`:
   `async def classify(image_bytes, mime, context) -> Classification`.
2. Inject your provider with `run_crawl(conn, config,
   vlm_provider=YourProvider())` in a custom entry point, or wire it through
   `_build_vlm` in `orchestrator.py`.
3. Set `Classification.model_version` and `prompt_version`, so the
   uniqueness of `analyses.model_versions_json` does what you want.

### Tune the image priority formula

Open `src/audit/synthesizer/priority.py`:

- `CLASSIFICATION_WEIGHTS` maps a vision label to a weight.
- `ADEQUACY_WEIGHTS` maps an alt text result to a weight.
- The severity thresholds are in `severity_for`.

`tests/unit/test_priority.py` pins the formula across every label and alt
result. When you change a weight, run the tests and update the expected
numbers in that file.

This formula covers image-of-text findings only. The Priority column in the
Issues table comes from `_priority` in `src/audit/web/issues.py`: an impact
weight (critical 4 down to minor 1) times `log1p` of the number of affected
pages.

### Edit remediation hints

Image-of-text hints live in `src/audit/rules/remediation.yaml`. The first
matching rule wins, so keep the most specific rules at the top and the
wildcard (`classification: "*"`) last. The loader is
`audit.synthesizer.rules.RemediationRules.load()`.

Fix text for other checks lives in the issue cards in
`src/audit/rules/audit_report.yaml`. [Adding a check](adding-a-check.md)
covers those.

### Add a migration

The newest migration is `0029`, so the next one is `0030`. Every migration is
a pair of files, as [AGENTS.md](../../AGENTS.md) requires:

```text
src/audit/db/migrations/0030_<description>.sql
src/audit/db/migrations/0030_<description>.rollback.sql
```

Write standard SQLite in both. If you need to widen the
`page_a11y_findings.pipeline` CHECK constraint, copy the column rebuild in
`0012_protected_image_pipeline.sql`, which lists every current value, because
SQLite cannot alter a CHECK in place. Drop and recreate both indexes on
`pipeline` around it (`idx_a11y_pipeline` and `idx_a11y_rule_lookup`), or the
rebuild fails. [Adding a check](adding-a-check.md#checklist-a-new-browser-probe)
has the full recipe.

Apply it with `make migrate`. The Makefile describes `make migrate-rollback`
as rolling back the last migration, so try it on a scratch database rather
than your real one:

```bash
make migrate DB=data/scratch.db
make migrate-rollback DB=data/scratch.db
```

The test fixtures pick up new migrations automatically. Each test session runs
every forward `.sql` file, in filename order, into a template database once.
`tmp_db` copies that template into each test's database with SQLite's backup
API, and tests that open their own connection get the same copy from
`migrate_db`.

### Add a UI page

The review app is the React app; there are no server-rendered pages.

1. Add a JSON endpoint inside `create_app` in `src/audit/web/server.py` (an
   `/api/*` route). Keep the handler thin and put the query in a typed module.
2. Add the response type to `frontend/src/api/types.ts` and a fetch method to
   `frontend/src/api/client.ts`.
3. Create the page component under `frontend/src/routes/` and register it in
   `frontend/src/App.tsx`. Add a sidebar entry in `components/AppShell.tsx` if
   it is a top-level destination.
4. Add an API test in `tests/ui/test_routes.py` (TestClient, fast).
5. Add an axe-core test in `tests/ui/test_accessibility_axe.py`. It drives the
   built app under `/app/`, and any WCAG 2.2 AAA violation fails the suite,
   so run `make frontend-build` first.

## Testing

- **Unit tests** mock the edges, not the core. The priority test runs the real
  formula, and the orchestrator tests run real SQL against a temporary
  database.
- **Integration tests** serve the fixture site from a thread and run real
  crawls against it. The tests that read image text need Tesseract and skip
  themselves without it. The vision model is a stub (`_StubVlm`), so no
  Ollama is needed.
- **UI tests** come in two kinds: TestClient tests for fast route coverage,
  and Playwright tests for accessibility and keyboard behavior. The axe-core
  tests inject the same bundled `axe.min.js` that scans use, so they stay
  offline.
- **Live model tests.** `AUDIT_OLLAMA_LIVE=1` enables the two tests that call
  a real Ollama: one in `tests/integration/test_vlm_pipeline.py` and one in
  `tests/integration/test_semantic_pipeline.py`. Both are skipped by default.
- **Golden files.** Exports and the API contract are pinned under
  `tests/unit/golden/` and `tests/ui/golden/`, including the draft export
  diffs and a fingerprint of the workbook. `AUDIT_UPDATE_GOLDEN=1` rewrites
  them after an intentional change. `tests/unit/test_export_goldens.py` and
  the API contract tests then fail on purpose, so review `git diff`, and run
  the tests again without the variable. Both refuse to rewrite anything when
  `CI` is set.

## Debugging tips

- **"My scan didn't do anything."** Look at the scan's pages:
  `sqlite3 data/audit.db "SELECT url_normalized, final_url, status_code FROM pages WHERE scan_id=<id>"`.
  The start page's status tells you whether you hit a 403 or a bot challenge.
  A failed scan also records `scans.failure_reason`.
- **"Where are the logs?"** The web server writes `data/logs/axcess.log`, and
  every line from a crawl carries its `scan_id`. The command line does not
  write that file.
- **"The crawler followed too many links."** Check `allow_subdomains` in the
  scan's settings:
  `sqlite3 data/audit.db "SELECT config_json FROM scans WHERE id=<id>"`. The
  whole-host setting is not recorded there, so compare the stored page URLs
  with the start URL's path. Queued jobs outside the scope are dropped when a
  crawl resumes and rejected again when leased, so leftover jobs cannot widen
  a scan.
- **"OCR is slow."** Raise `AUDIT_OCR_MAX_WORKERS` (default 2) on a computer
  with more cores. Inline SVG text skips OCR, so it costs nothing.
- **"Status changes in the app don't persist."** Look at `finding_history`
  for image findings and `a11y_finding_history` for everything else. A row
  with `actor='user'` and the new status means the database is fine. If there
  is none, the request is failing, and the browser's network panel will show
  the error.
