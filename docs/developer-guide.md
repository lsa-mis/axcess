# Developer guide

## Project layout (annotated)

```
src/audit/
├── __init__.py
├── cli.py                    # typer app — `audit crawl / synthesize /
│                             # export / serve / status`
├── config.py                 # pydantic-settings Settings (env AUDIT_*)
├── logging.py                # structlog setup
│
├── crawler/
│   ├── url_policy.py         # normalize / normalize_seed_url /
│   │                         # build_scope / is_in_scope / compare_key
│   ├── robots.py             # RobotsChecker (per-origin cache, fail-open)
│   ├── fetcher.py            # StaticFetcher (httpx) + FetchResult
│   ├── js_fetcher.py         # JsFetcher (Playwright chromium)
│   ├── render_detect.py      # is_js_only() + is_challenge_response()
│   ├── rate_limit.py         # HostLimiter (token bucket + semaphore)
│   └── orchestrator.py       # run_crawl — the main state machine
│
├── extractor/
│   ├── html_images.py        # extract_image_refs(body, base_url)
│   ├── svg_text.py           # find_inline_svg_text(body)
│   ├── downloader.py         # ImageDownloader + DownloadedImage
│   └── pipeline.py           # process_page — per-page glue
│
├── analyzer/
│   ├── ocr/
│   │   ├── base.py           # OcrResult dataclass
│   │   ├── tesseract.py      # run_tesseract (picklable module function)
│   │   └── pool.py           # OcrPool (ProcessPoolExecutor)
│   └── vlm/
│       ├── base.py           # VlmProvider protocol + Classification
│       ├── ollama.py         # OllamaProvider (HTTP client)
│       └── prompts/          # classify_v1.txt (content-hashed)
│
├── synthesizer/
│   ├── alt_compare.py        # AltAdequacy + compare() + worst()
│   ├── priority.py           # compute_priority_score + severity_for
│   ├── rules.py              # RemediationRules loader
│   ├── findings.py           # synthesize_findings (main entry)
│   └── diff.py               # compute_diff + materialize_history
│
├── exports/
│   ├── collector.py          # collect_scan — shared data source
│   ├── csv_export.py
│   ├── json_export.py
│   ├── jira_export.py
│   ├── markdown_report.py
│   └── webhook.py            # env-gated, opt-in
│
├── web/
│   ├── server.py             # FastAPI app factory (create_app)
│   ├── templates/            # Jinja: scans, findings, finding_detail, diff,
│   │                         # new_scan, partials/findings_table
│   └── static/
│       ├── styles.css        # hand-written, no framework
│       ├── app.js            # keyboard shortcuts
│       ├── htmx.min.js       # vendored
│       └── axe.min.js        # vendored (axe-core test harness)
│
├── db/
│   ├── schema.py             # connect(db_path) — PRAGMAs
│   ├── migrations/           # yoyo .sql files
│   ├── repo.py               # typed upsert helpers
│   └── queue.py              # enqueue / lease / complete / reclaim_expired
│
├── rules/
│   └── remediation.yaml      # hint text keyed on (classification, adequacy)
│
└── blob_store.py             # BlobStore + ext_from_mime

tests/
├── unit/                     # fast, hermetic
├── integration/              # fixture-site crawls (need tesseract)
└── ui/                       # TestClient + Playwright + axe-core
```

## Conventions

- **Strict typing.** `mypy --strict` runs in CI. No `Any` unless you
  justify it with a comment.
- **Explicit imports.** No `from foo import *`. Absolute imports from
  `audit.*`.
- **Dataclasses for value objects.** Frozen where the thing is
  conceptually immutable (`HostScope`, `ExportFinding`, `FetchResult`).
- **Module-level functions for anything that needs to be picklable**
  (the OCR process pool dispatches `audit.analyzer.ocr.tesseract.run_tesseract`
  directly).
- **Logs are structlog.** `log.info("namespace.event", key=value)`. Keep
  events lowercase dotted.
- **Tests are opinionated about what they verify.** Unit tests use
  `tmp_db` (fresh migrated SQLite) and `tmp_path` (fresh blob dir).
  Integration tests use the repo's `tests/fixtures/site` served from
  `stdlib http.server` on an ephemeral port.

## Running gates

```bash
make lint              # ruff check
make typecheck         # mypy strict
make test              # full pytest
make test-unit         # just tests/unit
make test-ui           # TestClient + Playwright
make a11y-check        # Playwright + axe-core
```

Ruff is aggressive (`S`, `SIM`, `UP`, `RUF`). mypy is strict on
`src/audit/` (tests are looser).

## Common extension tasks

### Add a new export format

1. Write a `render_<fmt>(scan: ExportScan) -> str` in
   `src/audit/exports/<fmt>_export.py`.
2. Register it in `audit.web.server._EXPORT_RENDERERS`,
   `_EXPORT_MEDIA_TYPES`, `_EXPORT_EXTENSIONS`.
3. Add it to the CLI dispatch in `cli.py` (`_EXPORT_FORMATS` + the
   renderer dict).
4. Add a golden-file test under `tests/unit/test_exports_<fmt>.py`
   using the existing `_assert_matches_golden` helper.
5. Regenerate the golden once with `AUDIT_UPDATE_GOLDEN=1 pytest …`.

### Swap the OCR backend

1. Write a module that exposes a picklable function taking `(bytes,
   lang) -> OcrResult`. It must be importable by
   `ProcessPoolExecutor` — so a top-level `def`, no closures.
2. Reference it from `analyzer.ocr.pool.OcrPool` by editing the
   `run_in_executor(self._executor, run_tesseract, …)` call, or make
   it pluggable via an `engine` arg.
3. `OcrResult.engine_version` should uniquely identify your backend +
   version so cached analyses don't collide.

### Swap the VLM backend

1. Implement the `VlmProvider` protocol from
   `audit.analyzer.vlm.base`: `async def classify(image_bytes, mime,
   context) -> Classification`.
2. Inject your provider via `run_crawl(conn, config,
   vlm_provider=YourProvider())` in a custom entry point, or wire it
   through `_build_vlm` in `orchestrator.py`.
3. Set `Classification.model_version` and `prompt_version` so
   `analyses.model_versions_json` uniqueness does what you want.

### Tune the priority formula

Open `src/audit/synthesizer/priority.py`:

- `CLASSIFICATION_WEIGHTS` — VLM label → numeric weight.
- `ADEQUACY_WEIGHTS` — alt bucket → numeric weight.
- Severity thresholds are inside `severity_for`.

The file is pinned by `tests/unit/test_priority.py` which tests the
full `(label × adequacy)` cross-product. When you change a weight,
rerun the tests and update the golden numbers in the test file.

### Edit remediation hints

`src/audit/rules/remediation.yaml`. First matching rule wins — keep
the most specific at the top, wildcard (`classification: "*"`) last.
Loader is `audit.synthesizer.rules.RemediationRules.load()`.

### Add a migration

```bash
# New file: src/audit/db/migrations/0002_<description>.sql
# Write standard SQL.
uv run yoyo apply --database "sqlite:///data/audit.db" --batch \
    src/audit/db/migrations
```

The unit-test `tmp_db` fixture picks up new migrations automatically
(it `.executescript`s every `.sql` file in the migrations dir in
filename order).

### Add a UI route

1. Add the route inside `create_app` in `src/audit/web/server.py`.
2. Create the template under `src/audit/web/templates/`.
3. If it needs an HTMX partial, render a separate `partials/*.html`
   and have the route's `render()` call pass `partial="partials/foo.html"`.
4. Add a route test in `tests/ui/test_routes.py` (TestClient-based,
   fast).
5. Add an axe-core test in `tests/ui/test_accessibility_axe.py` if the
   view is reachable from a user flow. Any WCAG 2.1 AA violation
   fails the suite.

## Testing philosophy

- **Unit tests** mock the edges, not the core. The priority formula
  test runs the real formula; the orchestrator test runs real SQL
  against a tmp DB.
- **Integration tests** stand up a real fixture HTTP server in a
  thread and run a real crawl against it. Tesseract is required; VLM
  is a stub (`_StubVlm`) so the tests don't need Ollama.
- **UI tests** have two flavors: `TestClient` for fast route
  coverage, Playwright for a11y + keyboard behavior. Axe-core is
  vendored so tests stay offline.
- `AUDIT_OLLAMA_LIVE=1` enables the one test that hits a real Ollama
  daemon. Skipped by default.
- `AUDIT_UPDATE_GOLDEN=1` regenerates golden files (CSV, JSON, Jira,
  Markdown). Use after intentional schema changes.

## Debugging tips

- **"My scan didn't do anything."** Check
  `sqlite3 data/audit.db "SELECT * FROM pages WHERE scan_id=<id>"`
  — the seed page's `status_code` tells you if you got a 403/challenge.
- **"The crawler followed too many links."** Look at
  `config_json` on the scans row (`SELECT config_json FROM scans
  WHERE id=<id>`). `whole_host: true` or `allow_subdomains: true`?
  If the config looks right but you still see out-of-scope URLs,
  you may have stale queued jobs from a pre-change scan; `DELETE FROM
  jobs WHERE json_extract(payload_json,'$.scan_id')=<id>` clears
  them.
- **"OCR is slow."** Check `AUDIT_OCR_MAX_WORKERS`; default is 2. For
  a laptop with 8+ cores you can safely raise it. Inline-SVG findings
  skip OCR so they cost nothing.
- **"Status changes in the UI don't persist."** Look at
  `finding_history` — if the row shows `actor='user'` with the new
  status, the DB is fine. If not, the POST is failing; browser
  devtools network tab will show you the error.
