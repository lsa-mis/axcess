# PLAN — Image Text Audit Tool (v1)

## Context

The accessibility lead who will use this tool has no good way to detect WCAG 1.4.5 violations (Images of Text) at site scale today — Siteimprove's coverage of this criterion is weak. We're building a local, offline tool that crawls a site, finds every image reference, runs a two-stage OCR→VLM pipeline to identify images containing text, cross-checks against alt text, and surfaces prioritized findings in a local web UI with rescan/diff support. The tool must itself be WCAG 2.1 AA clean, fully offline at runtime, and resumable on crash.

This plan covers v1 per the spec in [image-text-audit-prompt.md](image-text-audit-prompt.md). Once approved, it will be copied to the repo root as `PLAN.md` and implementation begins with Phase 0 scaffolding.

## Clarifications applied

| # | Question | Decision |
|---|---|---|
| 1 | Frontend | **HTMX + Jinja** (server-rendered, naturally accessible, fewer moving parts) |
| 2 | Scale ceiling | **Up to ~10k pages** per scan; design queue/DB around this |
| 3 | Default VLM / hardware | **Apple Silicon (MPS)** primary; default model **Qwen2-VL 2B** via Ollama Metal |
| 4 | Finding when alt is adequate | **Low-priority finding** in unified findings table; priority_score distinguishes urgency |
| 5 | Platform scope | **macOS + Linux**; Windows out of scope for v1 *(assumed — push back if wrong)* |

## Stack decisions

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Matches spec; asyncio, typing, exception groups |
| Crawler (JS) | Playwright (chromium only) | Required for JS-rendered pages + computed CSS backgrounds. Chromium only to keep footprint down. |
| Crawler (static) | httpx (async) | Fast path for static HTML; escalates to Playwright by heuristic |
| HTML parser | selectolax primary, BeautifulSoup4 fallback | selectolax is ~10x faster; BS4 for edge cases |
| URL utils | tldextract + urllib.robotparser | Registrable-domain detection; stdlib robots.txt (protego as fallback if edge cases bite) |
| OCR | Tesseract via pytesseract | Spec default; PaddleOCR held as optional backend behind interface |
| VLM | Ollama hosting `qwen3-vl:2b-instruct` default; `moondream:2b` alt | `VLMProvider` protocol; prompt versioned in `prompts/classify_v1.txt`; model version logged in `analyses.model_versions_json` |
| DB | SQLite + WAL | yoyo-migrations (simpler than Alembic, no SQLAlchemy dep) |
| Backend | FastAPI + uvicorn | Spec default |
| Frontend | Jinja templates + HTMX + hand-written CSS | No CSS framework needed for tabular UI; keeps offline footprint minimal, a11y surface small |
| Job queue | SQLite-backed async queue (`jobs` table with lease/claim) | Per spec: no Redis, no Celery |
| Packaging | uv + pyproject.toml | Spec default |
| Lint/type | ruff (+ ruff format), mypy strict on `src/` | Spec default |
| Tests | pytest, pytest-asyncio, Playwright + axe-core for UI | Spec default |
| CLI | typer (click-based, type-hinted) | Clean typing story |

**Substitutions from spec:** Tailwind dropped in favor of hand-rolled CSS — UI is tabular, framework overhead unjustified, and hand-rolled keeps the a11y audit surface area minimal. Can revisit if Phase 6 needs more polish.

## Directory structure

```
imagetextscanner/
├── Makefile                       # setup, run, test, lint, typecheck, migrate, fetch-models
├── pyproject.toml                 # uv-managed
├── uv.lock
├── README.md                      # updated each phase
├── PLAN.md                        # approved plan (copied from plans dir)
├── .ruff.toml
├── mypy.ini
├── .gitignore                     # data/, .venv/, __pycache__, blobs, logs
├── image-text-audit-prompt.md     # existing source doc
├── scripts/
│   ├── setup.sh                   # idempotent: uv sync, playwright install, ollama pull
│   ├── fetch_models.sh            # pull qwen2-vl + moondream; detect MPS/CUDA/CPU
│   └── run_fixture_site.py        # serves tests/fixtures/site on :8000
├── src/audit/
│   ├── __init__.py
│   ├── cli.py                     # typer app: audit crawl / status / rescan / export
│   ├── config.py                  # pydantic-settings, paths, defaults
│   ├── logging.py                 # structured logging (structlog), --verbose
│   ├── db/
│   │   ├── schema.py              # connection, pragma (WAL)
│   │   ├── migrations/            # yoyo .sql
│   │   ├── repo.py                # typed helpers per table
│   │   └── queue.py               # jobs queue (lease, claim, complete, reclaim)
│   ├── crawler/
│   │   ├── fetcher.py             # httpx + playwright dispatch
│   │   ├── url_policy.py          # normalize, robots.txt, registrable-domain, subdomain allow
│   │   ├── sitemap.py             # discover + parse
│   │   ├── render_detect.py       # static vs JS heuristic
│   │   └── orchestrator.py        # seed→queue loop
│   ├── extractor/
│   │   ├── html_images.py         # <img>, srcset, <picture>
│   │   ├── svg_text.py            # inline SVG <text> → immediate finding
│   │   ├── css_bg.py              # computed background-image via Playwright
│   │   ├── context.py             # alt, figcaption, aria-*, role, snippet
│   │   └── downloader.py          # content-hash + blob_store write
│   ├── blob_store.py              # data/blobs/<aa>/<aabbcc...>.<ext>
│   ├── analyzer/
│   │   ├── hardware.py            # detect MPS / CUDA / CPU
│   │   ├── ocr/
│   │   │   ├── base.py
│   │   │   └── tesseract.py
│   │   └── vlm/
│   │       ├── base.py            # VLMProvider protocol + Classification dataclass
│   │       ├── ollama.py          # HTTP client, retry, health check
│   │       └── prompts/classify_v1.txt
│   ├── synthesizer/
│   │   ├── alt_compare.py         # normalize + rapidfuzz match
│   │   ├── priority.py            # priority_score formula
│   │   ├── rules.py               # loads rules/remediation.yaml
│   │   └── findings.py            # upsert findings + history
│   ├── rules/remediation.yaml     # (classification, alt_adequacy) → hint text
│   ├── web/
│   │   ├── server.py              # FastAPI app, mount static, routes
│   │   ├── routes/{scans,findings,pages,exports,status}.py
│   │   ├── templates/             # base.html + partials/
│   │   └── static/{styles.css,htmx.min.js,app.js}
│   └── exports/
│       ├── csv_export.py
│       ├── json_export.py
│       ├── jira_export.py
│       ├── markdown_report.py
│       └── webhook.py             # disabled by default
├── data/                          # gitignored
│   ├── audit.db
│   ├── blobs/
│   └── logs/
└── tests/
    ├── conftest.py                # fixture site server, tmp DB, ollama mock
    ├── fixtures/site/             # static HTML test site with every image type
    ├── unit/                      # url_policy, extractor, synthesizer, priority, alt_compare
    ├── integration/               # crawl_end_to_end, ocr_pipeline, scans_rescans
    └── ui/                        # keyboard_nav, axe_clean (Playwright + axe-core)
```

## Data model refinements

Starting from the spec schema, with additions in **bold**:

- `scans` — add **`error_count`**, **`page_count`**, **`finding_count`** denormalized for fast list view.
- `pages` — add **`render_mode` enum('static','js')`**, **`html_hash`** for cheap dedupe on rescan.
- `images` — add **`blob_path`** (relative), **`has_svg_text` bool**.
- `page_images` — add **`bbox_json`** (x,y,w,h from Playwright for visibility heuristic) and **`above_fold` bool`**.
- `analyses` — one row per (image × pipeline-version). Keyed unique on (image_id, model_versions_json) so rerunning with a new model adds a row instead of overwriting.
- `findings` — **unified table**. Severity enum: `critical|major|minor|info`. Adequate-alt text images land at `info`. Status enum per spec: `new|reviewing|in_progress|remediated|accepted_risk|false_positive`.
- `finding_history` — add **`from_status`**, **`to_status`**, **`actor`** (`system|user`).
- **New** `jobs(id, kind, payload_json, state, lease_until, attempts, last_error, created_at, updated_at)` — SQLite-backed queue.

All upserts keyed on natural identifiers:
- `images` on `content_hash`
- `pages` on `(scan_id, url_normalized)`
- `page_images` on `(page_id, image_id, position)`
- `findings` on `(image_id, scan_id)`

## Milestone breakdown

End of each phase: tests pass, README updated, conventional-commit tag `phase-N`, pause for review.

### Phase 0 — Scaffolding (~1 day)
Repo skeleton, `pyproject.toml`, Makefile targets, first migration (all tables empty), CLI stub, ruff/mypy/pytest running green on empty code.

### Phase 1 — Crawl and store (~1 week)
- URL normalization (strip fragment, sort query params, lowercase host; registrable-domain via tldextract).
- robots.txt fetch + parse; sitemap discovery (both `/sitemap.xml` and robots-declared).
- httpx static fetcher + Playwright JS fetcher; render-mode heuristic (framework signatures, noscript redirects, low DOM node count).
- SQLite-backed job queue with lease/reclaim semantics (resume on crash).
- Per-host semaphore + configurable RPS; honor `Retry-After` and `crawl-delay`.
- CLI: `audit crawl <url> --max-pages N --max-depth D --include-subdomain --rps X`.
- End-of-run summary table (pages, images, errors).
- Tests: fixture site served locally, small crawl, interrupt/resume.

### Phase 2 — Image extraction (~1 week)
- Extract from `<img>` (incl. `srcset`, `sizes`), `<picture><source>`, computed `background-image` (via Playwright `getComputedStyle` during render), inline SVG `<text>`.
- Inline SVG with non-empty `<text>` → immediate finding (skip OCR).
- Dedupe by content_hash (SHA-256), write to `data/blobs/<aa>/<aabbcc…>.<ext>`.
- Capture alt, figcaption, aria-label, aria-labelledby, role, 200-char surrounding snippet; bounding box for above-fold detection.
- Tests: fixture site with every image type, blob store idempotency, SVG-text immediate finding.

### Phase 3 — OCR pass (~3 days)
- Tesseract (English default; lang configurable).
- Async OCR pool using ProcessPoolExecutor (CPU-bound).
- "Text candidate" flag: `confidence >= 60 AND word_count >= 3` (both configurable via config.py).
- Tests: known-text and no-text fixture images, threshold edges.

### Phase 4 — VLM classification (~1 week)
- `VLMProvider` protocol: `classify(image_bytes, context) -> Classification(label, rationale, model_version, prompt_version)`.
- `OllamaProvider` implementation with health check, retry+backoff, bounded concurrency against Ollama's queue.
- Prompt file `prompts/classify_v1.txt`, content-hashed → `prompt_version`.
- Hardware detection: default to `qwen3-vl:2b-instruct` on MPS/CUDA, `moondream:2b` on CPU-only.
- Only OCR-candidate images reach VLM.
- `--skip-vlm` CLI flag for faster iteration.
- Tests: mocked Ollama for unit; one live integration test gated on `AUDIT_OLLAMA_LIVE=1`.

### Phase 5 — Finding synthesis (~1 week)
- `alt_compare`: normalize both strings (lowercase, strip, collapse whitespace, drop punctuation), rapidfuzz token-set ratio + substring. Buckets: `adequate|partial|inadequate|missing`.
- `priority.py` formula:
  ```
  priority_score =
      classification_weight[vlm_class]         # essential=4, informational=3, logo=1, decorative=1, none=0
    + alt_adequacy_weight[bucket]              # missing=3, inadequate=2, partial=1, adequate=0
    + log1p(occurrence_count)                  # ~0..3
    + visibility_weight                        # above_fold=+1, hidden=-1, else=0
  ```
  Severity mapping: `>=8 critical`, `>=5 major`, `>=2 minor`, else `info`.
- `rules/remediation.yaml` keyed on `(classification, alt_adequacy)` → hint text.
- Findings upserted idempotently on `(image_id, scan_id)`.
- Tests: golden table covering every (classification × alt_adequacy) combo.

### Phase 6 — Review UI (~1.5 weeks)
- FastAPI on `localhost:8765`.
- Routes: `/scans`, `/scans/{id}`, `/scans/{id}/findings`, `/findings/{id}`, `/pages/{id}`, `/findings/{id}/status` (POST).
- HTMX partials for filter/sort/paginate (`hx-get`, `hx-push-url`) — no full reloads, still server-rendered.
- Semantic landmarks (`<main>`, `<nav>`, `<search>`), skip link, visible focus ring, labelled form controls.
- Status workflow dropdown with confirmation for destructive transitions.
- Keyboard shortcuts: `j/k` navigate findings, `s` set status, `/` focus filter.
- Hand-written CSS only (no framework); prefers-reduced-motion honored.
- Playwright + axe-core tests per view; keyboard-only flow test.

### Phase 7 — Exports and integrations (~3 days)
- CSV: flat, one row per (finding × occurrence).
- JSON: nested per finding with occurrences array.
- Jira CSV template (Summary, Description, Priority, Labels, deep-link back to local UI).
- Markdown stakeholder report (exec summary, top 20 findings, counts by severity).
- Webhook stub in `exports/webhook.py`: env-gated, POST JSON payload, disabled by default.
- Tests: golden-file outputs for each format.

### Phase 8 — Rescans and diffs (~1 week)
- Rerun creates new `scans` row; `images` reused by `content_hash`.
- Cross-scan finding match on `(content_hash, url_normalized)`.
- Diff view at `/scans/{id}/diff?compare_to={prev_id}`: new, resolved, still-open, status-changed.
- `finding_history` rows written on every status change and on first-appearance/resolution detection.
- Tests: two-scan rescan with fixture-site mutation, verify each diff bucket.

## Risk list

1. **Playwright chromium footprint (~300 MB).** Mitigate: document in README; pin version; `playwright install chromium` only.
2. **VLM throughput at 10k scale.** 10k pages × avg 15 images ≈ 150k refs; dedup cuts that ~10x; OCR candidacy filters further. Expect ~2–5k VLM calls. On M-series at ~1–2 s/call that's 1–3 h. Mitigate: bounded concurrency against Ollama, `--skip-vlm` for iteration, progress dashboard.
3. **Headless vs real rendering differences.** Some backgrounds only appear after interaction. Mitigate: scroll to bottom, `wait_for_load_state('networkidle')`, capture at 1440 and 375 viewports.
4. **Polite crawling vs throughput.** Mitigate: per-host semaphore, configurable RPS, default 2 RPS/host, honor `Retry-After` + `crawl-delay`.
5. **Ollama not running.** Mitigate: startup health check with actionable error, `make ollama-serve` target, env-var override for model URL.
6. **UI shipping with axe violations.** Mitigate: axe-in-the-loop from day one; fail Phase 6 tests on any violation.
7. **SQLite at 10k scale.** Mitigate: WAL mode, indexes on `(scan_id)`, `(content_hash)`, `(url_normalized)`, `(image_id, scan_id)`; batched inserts; `ANALYZE` before UI reads.
8. **Cache-buster query strings breaking dedup.** Mitigate: dedupe by `content_hash`, not URL. Rescan match is `(content_hash, url_normalized)`.
9. **False positives from OCR on noisy images.** Mitigate: VLM's `no_meaningful_text` label filters these; confidence + word-count thresholds configurable.
10. **Icon-font SVGs tripping SVG-text detector.** Mitigate: only flag SVG `<text>` elements with non-empty rendered text content; ignore `<title>` and `<desc>` (those are already the accessible name).
11. **robots.txt strictness vs user intent.** Mitigate: refuse disallowed paths by default; `--ignore-robots` flag for authorized testing, logged and flagged in scan config.
12. **Priority formula drift / calibration.** Mitigate: formula lives in one module with golden tests; `config.json` per scan captures weights so historic scans are interpretable.

## First-week task list

**Day 1 — Scaffold**
- `uv init`, directory skeleton, Makefile (`setup`, `run`, `test`, `lint`, `typecheck`, `migrate`, `fetch-models`, `a11y-check`).
- `pyproject.toml` with all phase-1 deps pinned.
- `.ruff.toml`, `mypy.ini` strict, pre-commit config.
- First yoyo migration: all tables per refined schema, all indexes.
- `audit --help` stub (typer).
- `.gitignore` for `data/`, `.venv/`, build artifacts.

**Day 2 — URL policy + robots**
- `url_policy.normalize(url)` + tests (fragment, query-sort, host-case, scheme-normalize, trailing slash rules).
- `url_policy.is_in_scope(url, seed, allow_subdomains)` via tldextract + tests.
- robots.txt fetch with short TTL cache; parse + honor; `--ignore-robots` flag wired.
- Sitemap discovery stub (fetch + parse XML).

**Day 3 — Job queue**
- `db/queue.py`: `enqueue`, `lease(kind, lease_secs)`, `complete`, `fail`, `reclaim_expired`.
- Atomic claim via `UPDATE … RETURNING` (SQLite 3.35+).
- Unit tests for lease expiry, reclaim, idempotent enqueue.
- structlog configured; `--verbose` flag.

**Day 4 — Fetchers**
- `httpx` async static fetcher with timeouts, redirect limits, content-type gate.
- Playwright JS fetcher (chromium headless, single reusable browser, per-page context).
- `render_detect.py` heuristic (cheap static check → upgrade to JS on signal).
- Per-host semaphore and RPS limiter.

**Day 5 — Orchestrator + demo**
- `orchestrator.py`: seed → enqueue → lease → fetch → parse links → enqueue in-scope → repeat until limits.
- Summary table at end (pages, images, errors, avg latency).
- Fixture site in `tests/fixtures/site/` (varied link depth, one JS-only page).
- Integration test: `audit crawl http://localhost:8000 --max-pages 50`.
- Interrupt/resume integration test.
- README: "What works today" section for phase 1.
- Commit `feat(crawler): phase 1 crawl-and-store complete` and tag `phase-1`.

## Verification (end-to-end for v1 Definition of Done)

**Setup works offline after initial model pull:**
```bash
make setup           # uv sync, playwright install chromium, ollama pull qwen3-vl:2b-instruct
make migrate         # yoyo apply
make fetch-models    # idempotent; detects hardware
```
After setup, disable network and confirm `make run` + a full crawl against `localhost:8000` both work.

**Crawl flow:**
```bash
audit crawl http://localhost:8000 --max-pages 500 --verbose
# expect: progress per page, final summary table, exit 0
```

**Interrupt/resume:**
```bash
audit crawl http://localhost:8000 --max-pages 500 &
sleep 3 && kill -INT $!
audit crawl http://localhost:8000 --max-pages 500    # resumes, no duplicate rows
```

**UI + export:**
```bash
make run    # serves :8765
# in browser: navigate by keyboard to /scans/1/findings,
# filter classification=informational, alt_adequacy=inadequate,
# Export → CSV → file downloads with matching rows
make a11y-check   # axe-core via Playwright, exits 0
```

**Rescan + diff:**
```bash
# mutate fixtures (swap one image's text), then:
audit crawl http://localhost:8000 --max-pages 500
# UI: /scans/2/diff?compare_to=1 shows new=1, resolved=1, still_open=N
```

**Tests:**
```bash
make test
# unit: url_policy, extractor, synthesizer, priority, alt_compare
# integration: crawl, ocr_pipeline, scans_rescans
# ui: keyboard_nav, axe_clean
# coverage >= 70% on crawler, extractor, analyzer, synthesizer
```

If any of those five flows fail, v1 is not done.
