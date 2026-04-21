# Image Text Audit Tool — Claude Code Build Prompt

## Role and context

You are a senior engineer building a local, offline web accessibility auditing tool. The tool is inspired by the systematic issue tracking model of Siteimprove but focuses on one thing it does poorly: detecting images that contain text (WCAG 1.4.5, Images of Text). The user of this tool is an accessibility lead who needs to find these images across a site, prioritize them, and remediate them.

Before writing code, read this whole document, then ask up to 5 clarifying questions, then produce a PLAN.md with phased milestones. Do not start coding until the plan is approved.

## Product vision

A local desktop-class tool that:

1. Takes one or more public URLs (seeds) as input.
2. Crawls within the seed domain (with optional subdomain allowlist), respecting robots.txt.
3. Extracts every image reference it can find: `<img>`, `srcset`, `<picture><source>`, inline SVG text elements, and CSS background images.
4. Detects which of those images contain human readable text, using a two-stage pipeline (OCR then small local VLM).
5. Cross checks each finding against the image's alt attribute and surrounding context.
6. Stores findings in a queryable database with stable issue IDs and rescan history.
7. Exposes a local web UI for triage, filtering, status workflow, and exports.
8. Runs fully offline. No external API calls at runtime.

## Non-negotiables

- **Offline only at runtime.** Model downloads happen once during setup, then no network except the user's crawl target.
- **Accessibility of the tool itself.** Keyboard navigable, proper semantics, screen reader tested. The tool must not violate the standards it audits.
- **Deterministic, resumable crawls.** A crash at page 9,000 of 10,000 does not force restart.
- **Single-machine footprint.** Laptop-runnable. No Docker orchestration required, though a compose file is welcome.
- **No telemetry.** Ever.

## Recommended tech stack (justify any substitutions in PLAN.md)

- **Language:** Python 3.11+
- **Crawler:** Playwright for JS-rendered pages, httpx for fast static fallback
- **HTML parsing:** selectolax (fast) with BeautifulSoup as secondary
- **OCR:** Tesseract via pytesseract, with PaddleOCR as an optional higher-accuracy backend
- **VLM:** Ollama hosting Moondream 2B or Qwen2-VL 2B. Abstract behind a provider interface so users can swap models.
- **DB:** SQLite with a proper migration tool (alembic or yoyo)
- **Backend:** FastAPI
- **Frontend:** React with Vite and Tailwind, or HTMX plus Jinja. Pick the simpler one that meets the UI requirements and justify in PLAN.md.
- **Job queue:** asyncio task queue backed by SQLite. Avoid Redis and Celery unless strongly justified.
- **Packaging:** `uv` for dependency management. A single `make setup` and `make run` should work.

## Data model (starting point, refine in PLAN.md)

```
scans(id, seed_url, started_at, finished_at, status, config_json)
pages(id, scan_id, url_normalized, status_code, title, fetched_at, render_mode)
images(id, content_hash, src_url_canonical, width, height, bytes, mime, first_seen_scan_id)
page_images(id, page_id, image_id, alt_text, role, context_snippet, position)
analyses(id, image_id, ocr_text, ocr_confidence, vlm_classification, vlm_rationale, has_text, analyzed_at, model_versions_json)
findings(id, image_id, scan_id, severity, wcag_criterion, status, priority_score, remediation_hint)
finding_history(id, finding_id, scan_id, change_type, changed_at)
```

Issues are grouped by `content_hash`, so the same image reused across 40 pages is one finding with 40 occurrences.

## Phases

Build and ship end-to-end at each phase. Do not skip ahead. At the end of each phase, run the test suite, update the README, and pause for review.

### Phase 1: Crawl and store

- CLI command `audit crawl <url> --max-pages N --max-depth D`
- Respects robots.txt, follows sitemaps when present, normalizes URLs (strip fragments, sort query params, lowercase host).
- Stays within the seed registrable domain by default, with `--include-subdomain` flag.
- Writes to SQLite. Resumable on interrupt.
- Logs a clear summary at the end: pages crawled, images found, errors.
- Tests: crawl a small fixture site served from `tests/fixtures/` by a local server.

### Phase 2: Image extraction

- Pulls every image reference from each page, including srcset, picture, SVG with inline text, and CSS background images from computed styles.
- Downloads each unique image once, content-hashes it, stores bytes in a local blob directory organized by hash prefix.
- Captures alt text, figcaption, surrounding paragraph, ARIA attributes, and role.
- Flags inline SVG containing `<text>` elements as an immediate finding without running OCR.

### Phase 3: OCR pass

- Runs Tesseract on every non-SVG image.
- Stores detected text plus mean confidence.
- Heuristic flag: image is a "text candidate" if confidence > threshold and word count >= N (both configurable).

### Phase 4: VLM classification

- For each text candidate, runs a prompt against the local VLM via Ollama asking it to classify:
  - `logo_or_wordmark`
  - `decorative_text`
  - `informational_text`
  - `essential_text`
  - `no_meaningful_text` (false positive from OCR)
- Returns a short rationale.
- Model and prompt live behind a `VLMProvider` interface with versioned prompts. Log model version in `analyses.model_versions_json`.

### Phase 5: Finding synthesis

- Combines OCR text, VLM classification, and alt text to produce findings.
- Compares OCR text against alt text (normalized) to detect "text in image, alt does not cover it."
- Assigns a priority score from `(classification, alt_adequacy, occurrence_count, visibility_context)`.
- Attaches remediation hints from a rules file, not hardcoded strings.

### Phase 6: Review UI

- Local web UI at `http://localhost:8765`.
- Views: Scans list, Findings list (grouped by image, sortable and filterable), Finding detail with image preview and per-occurrence context, Page detail.
- Status workflow per finding: new, reviewing, in progress, remediated, accepted risk, false positive.
- Keyboard-first navigation. WCAG 2.1 AA clean. Test with axe-core in the test suite.

### Phase 7: Exports and integrations

- CSV and JSON exports of findings with all context.
- Jira-ready export: one row per finding, with summary, description, priority, and a deep link to the local UI.
- Markdown report export for stakeholders.
- Webhook stub (disabled by default) so integrations can be wired in later without refactoring.

### Phase 8: Rescans and diffs

- Rerunning against the same seed produces a new `scan` row.
- Findings are matched across scans by `content_hash` plus URL.
- Diff view: new, resolved, still open.

## Quality bar

- **Tests:** pytest for unit and integration. Fixture site served locally for crawler tests. Target 70% coverage on core modules (crawler, extractor, analyzer, synthesizer). UI tested with Playwright.
- **Type hints everywhere.** Run mypy in strict mode on `src/`.
- **Lint:** ruff with a sensible config.
- **Errors never swallowed.** Every network or model failure is logged with page and image context.
- **Idempotency:** reruns do not duplicate rows. Use upserts keyed on natural identifiers.
- **Observability:** a `--verbose` flag that shows per-page progress and a final summary table.

## What not to do

- Do not build an auth system. This is local.
- Do not add a cloud VLM fallback unless explicitly requested later.
- Do not pull in a full ML framework for classification. Use Ollama.
- Do not use `requests` + BeautifulSoup as the primary crawler path. JS rendering is needed for a meaningful fraction of real sites.
- Do not store images inside SQLite. Filesystem plus hash-prefixed directories.
- Do not ship without the tool's own UI passing axe.

## How to start

1. Read this document fully.
2. Ask up to 5 clarifying questions (batch them, do not drip feed).
3. Produce `PLAN.md` with: stack decisions with rationale, directory structure, milestone breakdown mapped to the phases above, risk list, and a first-week task list.
4. Wait for approval on `PLAN.md` before creating any code files.
5. Commit after every meaningful unit of work with a clear message. Use conventional commits.
6. Update `README.md` as features land. The README should always reflect what currently works.

## Definition of done for version 1

A user can:
- Run `make setup` once and have all dependencies and models ready.
- Run `audit crawl https://example.edu --max-pages 500` and watch it complete.
- Open the local UI, see findings grouped by image, filter to "informational text with inadequate alt," and export to CSV.
- Rerun the same audit a week later and see what changed.

If any of those flows are broken, version 1 is not done.
