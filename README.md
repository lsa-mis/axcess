# Axcess

Local, offline web accessibility auditor. Started as a **WCAG 1.4.5 — Images of Text** detector and has grown into an overall accessibility scanner: it crawls a site, finds every image, runs OCR + a local VLM to detect images that contain text and cross-checks against `alt`, probes pages for keyboard traps (WCAG 2.1.2) with a real browser, and surfaces prioritized findings in a local UI with rescan/diff support. A companion test-management app, **Accessibility Testing Tracker**, lives under [`tracker/`](./tracker/).

## Docs

Full documentation lives under [`docs/`](./docs/README.md):

- **[Architecture](./docs/architecture.md)** — pipeline, data flow, storage model
- **[User guide](./docs/user-guide.md)** — CLI + UI walkthroughs
- **[Developer guide](./docs/developer-guide.md)** — code layout + extension points
- **[Troubleshooting](./docs/troubleshooting.md)** — Cloudflare, stuck scans, Ollama, scope

## Status — v1.0 (Phase 8: rescans + diff — **v1 feature-complete**)

What works today:

- Repo scaffolded, `uv`-managed, ruff + mypy (strict) + pytest green (77 tests).
- SQLite schema per `0001_initial_schema.sql`; WAL, FK on.
- **URL policy** — deterministic normalization and registrable-domain scope
  checks using an offline tldextract PSL snapshot.
- **robots.txt** — per-origin cache with fail-open behavior on network errors;
  `--ignore-robots` escape hatch for authorized testing.
- **Sitemap** — `defusedxml` parsing of `urlset`/`sitemapindex` with recursion
  cap; discovery unions robots-declared sitemaps with conventional paths.
- **Job queue** — SQLite-backed with atomic `UPDATE … RETURNING` lease,
  dedupe keys, retry budget, and `reclaim_expired` for crash recovery.
- **Fetchers** — async httpx static fetcher (HTTP/2, Retry-After parsing)
  plus Playwright chromium JS fetcher (shared browser, per-page contexts).
- **Render heuristic** — escalates to JS on sparse DOM, `<noscript>` meta
  refresh redirects, or empty SPA mount points.
- **Rate limiting** — per-host semaphore + token-bucket RPS limiter.
- **Orchestrator** — workers lease from queue, fetch, record pages, enqueue
  in-scope links. Resumable after Ctrl-C or crash.
- **Image extraction** — pulls `<img>` (incl. `srcset`) and
  `<picture><source>` refs from the rendered HTML; preserves the
  missing-vs-empty-alt distinction, captures `aria-label`,
  `aria-labelledby`, `role`, the nearest `<figcaption>`, and a
  surrounding-text snippet.
- **Inline SVG text** — top-level `<svg>` elements with visible `<text>`
  are recorded as findings with `has_svg_text=1` (no blob needed).
- **Content-addressed blob store** — images land at
  `data/blobs/<aa>/<sha256>.<ext>`, deduped across the whole site.
- **OCR pass** — Tesseract (via `pytesseract`) runs in a
  `ProcessPoolExecutor` in parallel with the crawl. Each downloaded
  raster image is OCR'd; the mean per-word confidence and word count
  are stored alongside the extracted text in the `analyses` table.
  The text-candidate gate is `confidence >= 60.0 AND word_count >= 3`
  (both configurable via `AUDIT_OCR_MIN_CONFIDENCE` / `AUDIT_OCR_MIN_WORD_COUNT`).
  SVG and icon MIMEs are skipped. Pass `--skip-ocr` to disable entirely.
- **VLM classification** — only OCR text-candidate images reach the VLM.
  `OllamaProvider` POSTs to a local `/api/generate` with the image
  base64-encoded and a content-hashed prompt (default
  `classify_v1.txt`). Returns one of `essential | informational | logo |
  decorative | no_meaningful_text` plus a rationale, merged into the
  same `analyses` row with combined `{ocr, vlm, prompt}` versioning.
  Transient HTTP errors (408/429/5xx) are retried with exponential
  backoff. If the Ollama daemon is unreachable or the model isn't
  pulled, the crawler logs `vlm.unavailable` and completes without VLM.
  Pass `--skip-vlm` to opt out explicitly.
- **Finding synthesis** — end-of-crawl (or via `audit synthesize`):
  - `alt_compare` normalizes alt and visible text (lowercase, strip
    punctuation, collapse whitespace) and uses `rapidfuzz` token-set
    ratio plus substring checks to bucket adequacy as `missing |
    inadequate | partial | adequate`.
  - `priority_score = classification_weight + alt_adequacy_weight +
    log1p(occurrence_count) + (above_fold ? 1 : 0)`, mapped to
    severity `critical >=8 | major >=5 | minor >=2 | info`.
  - Remediation hints live in `src/audit/rules/remediation.yaml`, keyed
    on `(classification, adequacy)` with a `*` fallback for inline SVG
    text and other cases with no VLM label.
  - Findings are upserted on `(image_id, scan_id)` so re-runs don't
    stomp human-set `status` values; re-synthesizing with
    `audit synthesize [scan_id]` refreshes scores and hints.
  - Pass `--skip-synthesize` to crawl only and run synthesis later.
- **Review UI** — two front-ends sharing the same FastAPI backend at
  `127.0.0.1:8765` (launch with `audit serve` or `make run`):
  - **React SPA** at `/app/` — default UI. Tanstack Query + React
    Router + a Michigan-palette design system in hand-rolled CSS, all
    driven by the `/api/*` JSON endpoints (`/api/scans`,
    `/api/scans/{id}/findings`, `/api/findings/{id}`, etc.). Build
    with `make frontend-build`; dev server on `:5173` via
    `make frontend-dev` (proxies `/api` and `/blobs` to FastAPI).
  - **Legacy Jinja + HTMX** at `/scans`, `/findings/{id}`, … — still
    shipped while the SPA matures. Filter-as-you-type with
    `hx-push-url` so back/forward works; destructive status
    transitions (`remediated`, `accepted_risk`, `false_positive`)
    confirm before saving.

  Shared across both: scan list + detail with severity breakdown,
  filterable paginated findings list, finding detail with image
  preview and OCR/VLM metadata, per-page image inventory. Keyboard
  shortcuts: `j/k` next/prev finding, `Enter` to open, `/` focus
  filter, `s` focus status dropdown, `?` help. Zero axe-core WCAG
  2.1 AA violations on every Jinja view; SPA views inherit the same
  focus-ring, skip-link, and landmark semantics. Dark-mode +
  prefers-reduced-motion honored. Content-hash-validated
  `/blobs/{hash}` for image previews.
- **Exports** — one shared collector feeds four deterministic formats,
  all with golden-file tests so any change is explicit:
  - **CSV** — flat, one row per (finding, occurrence) pair.
  - **JSON** — nested per finding with an `occurrences` array; sorted
    keys so diffs are meaningful. `schema_version` field.
  - **Jira CSV** — Summary / Description / Priority / Labels mapping
    that Jira Cloud's External import accepts out of the box. Severity
    maps to Jira priorities (critical→Highest, info→Lowest).
  - **Markdown** — stakeholder-friendly report with exec summary, top
    20 findings, and a full severity table.
  - **Webhook** — opt-in via `AUDIT_WEBHOOK_URL`, optional bearer
    token, async POST of the JSON payload; best-effort, never fails
    the scan.
  Available from the review UI (`/scans/{id}/export/<format>` download
  links) and from the CLI (`audit export <scan_id> --format <fmt>`).
- **Rescans + diff** — a second crawl of the same seed URL creates a
  new scan row but reuses the `images` table via `content_hash`.
  Finding match is keyed on `(content_hash, url_normalized)` so an
  image that moves pages shows as "resolved on old URL, new on new
  URL". At end of each crawl the synthesizer auto-picks the most
  recent completed scan of the same seed as `compare_to` and writes
  `first_seen` / `resolved` rows into `finding_history`. The UI has
  `/scans/{id}/diff?compare_to={prev}` with sections for New,
  Resolved, Status changed, and Still open — plus a diff link from
  the scan detail when a prior scan exists.
- **CLI** — `audit crawl <url>`, `audit synthesize`, `audit export`,
  `audit serve`, and `audit status`. Summary tables cover pages,
  images, SVG-text, OCR, VLM, finding-by-severity, and rescan
  first_seen / resolved counters.

**Port-tolerant rescan matching**: auto-diff uses
`url_policy.compare_key`, which drops the port on loopback hosts (and
canonicalizes `localhost` / `127.0.0.1` / `::1` / `0.0.0.0` to a single
form). So a second crawl of the same local site on a different dev-server
port still lands in the right diff buckets instead of showing every
finding as new + resolved. Real-host ports stay significant
(`example.com:8443` is not the same as `example.com:9443`). Override
auto-discovery with `audit crawl --compare-to <scan_id>` or
`audit synthesize --compare-to <scan_id>`.

Not yet implemented: CSS `background-image` extraction.

## Try it

```bash
make setup
make migrate
# Shell 1 — fixture site
make fixture-site                    # → http://127.0.0.1:8000
# Shell 2 — crawl it
uv run audit crawl http://127.0.0.1:8000 --max-pages 50
uv run audit status
# Shell 2 — open the review UI
uv run audit serve                   # → http://127.0.0.1:8765
```

## Requirements

- macOS or Linux
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (`brew install uv`)
- [Ollama](https://ollama.com) (for Phase 4+)
- Tesseract OCR (Phase 3+): `brew install tesseract` on macOS

## Setup

```bash
make setup           # uv sync + playwright install chromium + create data dirs
make migrate         # apply SQLite schema
make fetch-models    # pull Ollama VLM models (requires ollama daemon)
```

## Development

```bash
make test            # run pytest
make lint            # ruff check + format --check
make typecheck       # mypy strict on src/
make help            # list all targets
```

## Project layout

```
src/audit/          # application code
  cli.py            # typer CLI
  config.py         # pydantic-settings
  logging.py        # structlog config
  db/               # schema + migrations + repo + queue
  crawler/          # (Phase 1)
  extractor/        # (Phase 2)
  analyzer/         # (Phases 3–4: OCR + VLM)
  synthesizer/      # (Phase 5)
  web/              # (Phase 6)
  exports/          # (Phase 7)
tests/
  unit/             # fast pure-python tests
  integration/      # end-to-end (fixture site)
  ui/               # Playwright + axe-core (Phase 6+)
  fixtures/site/    # static HTML fixture site
scripts/            # setup, fetch-models, fixture-site runner
data/               # gitignored runtime (SQLite + blobs + logs)
```

See [PLAN.md](PLAN.md) for milestones, risks, and the first-week task list.

## License

MIT
