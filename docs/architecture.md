# Architecture

## The problem

WCAG 1.4.5 says: if you're presenting text, use real text (selectable,
zoomable, translatable) — not text baked into an image. Hundreds of image
accessibility tools will tell you if an `<img>` has an `alt` attribute,
but very few will tell you whether that image actually *contains text*,
and whether the alt adequately conveys it. At scale — thousands of pages —
this is the violation that's hardest to catch and slowest to fix.

This tool crawls a site, finds every image, decides per image "does this
have text in it," compares the image's text to the authored `alt`, and
flags disagreements in a triage UI.

## The pipeline, top to bottom

```
   seed URL
     │
     ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. CRAWL      URL policy → robots.txt → fetcher (static / JS) →    │
│                link extraction → enqueue in-scope URLs              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  one HTML page at a time
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. EXTRACT    <img> / srcset / <picture> / inline SVG text →       │
│                download each raster image to blob store →           │
│                persist images row (dedup on sha256) + page_images   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  per image
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. ANALYZE    OCR (Tesseract in process pool) → text-candidate?    │
│          → VLM (Ollama, qwen3-vl:2b-instruct) classification →      │
│                persist analyses row                                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  once the crawl is done
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. SYNTHESIZE alt-compare (rapidfuzz) → priority score →           │
│                severity bucket → remediation hint → upsert          │
│                findings row, write first_seen/resolved history      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
                     ┌───────────┐        ┌────────────────┐
                     │ Review UI │        │ Exports        │
                     │ (React)   │        │ CSV/JSON/Jira/ │
                     │           │        │ Markdown       │
                     └───────────┘        └────────────────┘
```

Each stage lives in its own Python package under `src/audit/`:

| Stage | Package | Entry point |
|---|---|---|
| Crawl | `audit.crawler` | `orchestrator.run_crawl` |
| Extract | `audit.extractor` | `pipeline.process_page` |
| Analyze | `audit.analyzer` | `ocr.pool.OcrPool`, `vlm.ollama.OllamaProvider` |
| Synthesize | `audit.synthesizer` | `findings.synthesize_findings` |
| Serve | `audit.web` | `server.create_app` |
| Export | `audit.exports` | `csv_export`, `json_export`, `jira_export`, `markdown_report` |

## Data flow

```
                                  (host:path prefix)
                      normalize()      build_scope()
    "https://x/foo"  ──────────▶  "https://x/foo/" ──────────▶  HostScope
                     auto-slash                                  │
                                                                 │
                        ┌───────────────────────────────────────┘
                        │
                        ▼
                   jobs table (pending)
                        │
                        │ lease (atomic UPDATE … RETURNING)
                        ▼
                    _process_job
                        │
                        ├─── fetch (httpx) ──▶ maybe re-fetch (Playwright)
                        │                         if js_only or WAF challenge
                        │
                        ├─── pages row (upsert)
                        │
                        ├─── extract_image_refs → per-image:
                        │       ├─ download → blob_store.store()
                        │       ├─ images row  (unique on content_hash)
                        │       ├─ page_images row
                        │       └─ schedule OCR task (asyncio)
                        │
                        ├─── find_inline_svg_text → per hit:
                        │       ├─ synthetic image row (has_svg_text=1)
                        │       └─ page_images row
                        │
                        ├─── gather OCR results ─▶ analyses row
                        │
                        └─── enqueue in-scope child URLs
```

After every worker drains:

```
                    synthesize_findings(scan_id)
                              │
   ┌──────────────────────────┼──────────────────────────────┐
   │                          │                              │
   ▼                          ▼                              ▼
   pick best analysis    compare(alt, OCR)              priority_score
   per image             via rapidfuzz                  +severity
   (prefer VLM)          → AltAdequacy                  +remediation hint
                                                              │
                                                              ▼
                                                        findings row (upsert)
                                                        + finding_history
                                                          (first_seen /
                                                           resolved vs
                                                           previous scan)
```

## Components in detail

### Crawl layer (`audit.crawler.*`)

- **`url_policy`** — the gate on every link. Three functions matter:
  - `normalize(url)` — canonical form used as a dedup key (drop fragment,
    sort query, lowercase host, strip default ports).
  - `normalize_seed_url(url)` — auto-adds trailing slash on paths that
    look like directories, so `/bicentennial` → `/bicentennial/`.
  - `build_scope(seed, whole_host)` — derives `(registrable_domain,
    seed_host, path_prefix)`. `is_in_scope(url, scope)` checks both host
    AND path_prefix; `/bicentennial/` does not match `/bicentennial-news`.
  - `compare_key(url)` — cross-scan matching. Strips port on loopback
    hosts so a dev-server port change between crawls doesn't register
    every finding as "new + resolved".

- **`robots`** — per-origin robots.txt cache with fail-open on network
  errors (RFC 9309). `allowed(url)` + `crawl_delay(url)`.

- **`fetcher`** — `StaticFetcher` (httpx async). Every response comes back
  as a `FetchResult` (4xx/5xx don't raise; only true network errors do).

- **`js_fetcher`** — `JsFetcher` wraps Playwright chromium. Reusable
  single-browser lifecycle; per-page `BrowserContext`. Wait for
  `load` then `networkidle` (suppressed on timeout).

- **`render_detect`** — two heuristics:
  - `is_js_only(body)` — SPA bootstrap with empty mount point, noscript
    meta-refresh, or sparse DOM.
  - `is_challenge_response(status, body)` — Cloudflare / WAF / DataDome
    interstitial markers. Only matches 403/429/503 *and* a marker — plain
    403s stay plain 403s.

- **`rate_limit`** — `HostLimiter` with per-host token bucket + semaphore.
  Separate hosts don't block each other.

- **`orchestrator.run_crawl`** — the state machine. Creates (or resumes) a
  scan row; seeds the queue; spins up `config.workers` asyncio tasks;
  lazy-starts Playwright on first escalation; runs synthesis at the end.

### Extract layer (`audit.extractor.*`)

- **`html_images.extract_image_refs(body, base_url)`** — returns every
  `ImageRef` the page holds. Every `srcset` candidate is a separate ref.
  The `alt` attribute is preserved faithfully — `None` means absent,
  `""` means decorative, `"foo"` means authored.

- **`svg_text.find_inline_svg_text(body)`** — inline `<svg>` with visible
  `<text>` children is its own finding category (can't be OCR'd, can't be
  downloaded). `<title>`/`<desc>` are ignored (they're the accessible
  name, not content).

- **`downloader.ImageDownloader`** — fetches bytes, caps at `MAX_IMAGE_BYTES`,
  writes via content-addressed `BlobStore`, reads width/height via Pillow.

- **`blob_store.BlobStore`** — `data/blobs/<aa>/<sha256>.<ext>`. Writes
  via tmp-then-rename so a killed process never leaves a torn file.

- **`pipeline.process_page`** — the glue. For one fetched HTML body:
  extract → download (dedup on content_hash) → upsert rows → schedule
  OCR tasks → gather → upsert analysis rows → detect inline SVG text
  → another batch of synthetic image rows.

### Analyze layer (`audit.analyzer.*`)

- **`ocr.tesseract.run_tesseract(bytes, lang)`** — pure function (picklable
  for the process pool). Uses `image_to_data` for per-word confidences;
  mean-pools them. Returns `OcrResult(text, confidence, word_count,
  engine_version)`.

- **`ocr.pool.OcrPool`** — asyncio-friendly wrapper around
  `ProcessPoolExecutor`. Tesseract is CPU-bound; the pool runs OCR in
  parallel with the crawler's I/O. `in_process=True` mode exists for
  deterministic tests.

- **`vlm.base.VlmProvider`** — protocol: `classify(image_bytes, mime,
  context) -> Classification`.

- **`vlm.ollama.OllamaProvider`** — HTTP client against `localhost:11434`.
  Health check on start, retries with backoff, bounded concurrency
  (Ollama has its own queue internally). Prompt is hashed to a
  `prompt_version` so analyses dedupe cleanly across prompt edits.

### Synthesize layer (`audit.synthesizer.*`)

- **`alt_compare.compare(alt, visible_text)`** — both sides normalized
  (lowercase, strip punctuation, collapse whitespace); then rapidfuzz
  token-set ratio + substring check. Returns one of
  `missing | inadequate | partial | adequate`. Worst-across-occurrences
  aggregated by `worst([...])` for an image on many pages.

- **`priority.compute_priority_score(...)`** — pinned by golden tests:

  ```
  score = CLASSIFICATION_WEIGHTS[label]   # essential=4, informational=3,
                                           # logo=1, decorative=1, else=0
        + ADEQUACY_WEIGHTS[bucket]        # missing=3, inadequate=2,
                                           # partial=1, adequate=0
        + log1p(occurrence_count)         # ~0..3
        + (1 if above_fold else 0)

  severity = critical if score >= 8
           | major    if score >= 5
           | minor    if score >= 2
           | info     otherwise
  ```

- **`rules.RemediationRules`** — loads `src/audit/rules/remediation.yaml`.
  First rule whose `(classification, adequacy)` matches wins; a
  `classification: "*"` fallback covers inline SVG text and any row
  without a VLM label.

- **`findings.synthesize_findings(scan_id, compare_to=...)`** — iterates
  every image-with-text in the scan, runs the three layers above, and
  upserts on `(image_id, scan_id)`. When `compare_to` is set, writes
  `first_seen` / `resolved` history rows via
  `diff.materialize_history`.

- **`diff.compute_diff(current, prev)`** — keys on `(content_hash,
  compare_key(url))`. Buckets into `new | resolved | still_open |
  status_changed`. Loopback ports are stripped by `compare_key` so a
  rescan on `:18801` vs `:18800` doesn't look like every finding moved.

## Storage

### SQLite (`data/audit.db`)

Eight tables, all defined in `src/audit/db/migrations/0001_initial_schema.sql`.

```
scans
  id, seed_url, status (running|completed|failed|interrupted),
  started_at, finished_at, config_json (JSON snapshot of CrawlConfig),
  page_count, image_count, finding_count, error_count

pages (scoped to one scan)
  id, scan_id → scans, url_normalized, status_code, title,
  render_mode (static|js), html_hash, fetched_at
  UNIQUE (scan_id, url_normalized)

images (shared across scans — the content-addressed unit)
  id, content_hash UNIQUE, src_url_canonical, mime, bytes, width, height,
  blob_path (relative to data/blobs/), has_svg_text, first_seen_scan_id

page_images (one row per occurrence on a page)
  id, page_id → pages, image_id → images,
  alt_text (null = missing; "" = decorative; else = authored),
  role, context_snippet, position, bbox_json, above_fold
  UNIQUE (page_id, image_id, position)

analyses (OCR + VLM results)
  id, image_id → images, ocr_text, ocr_confidence,
  vlm_classification, vlm_rationale, has_text,
  model_versions_json, analyzed_at
  UNIQUE (image_id, model_versions_json)

findings
  id, image_id → images, scan_id → scans,
  severity (critical|major|minor|info), wcag_criterion,
  status (new|reviewing|in_progress|remediated|accepted_risk|false_positive),
  priority_score, remediation_hint, created_at, updated_at
  UNIQUE (image_id, scan_id)

finding_history
  id, finding_id → findings, scan_id, change_type, from_status, to_status,
  actor (system|user), changed_at, note

jobs  (SQLite-backed queue)
  id, kind, payload_json, state (pending|leased|completed|failed),
  lease_until, attempts, last_error, created_at, updated_at, dedupe_key UNIQUE
```

### Blob store (`data/blobs/`)

Content-addressed. Every downloaded image lives at
`data/blobs/<aa>/<sha256>.<ext>` where `aa` is the first two hex chars of
the SHA-256. A `BlobStore(root)` object is the single writer. Writes are
tmp-then-rename; repeat writes of identical bytes are a no-op.

Inline SVG findings don't have blob files — their `blob_path` is NULL
and `has_svg_text=1` distinguishes them.

## Resumability

Every durable unit of work is a row in `jobs`. A worker leases a job
atomically (`UPDATE … WHERE id = (SELECT id FROM jobs WHERE state='pending'
… LIMIT 1) RETURNING *`), processes it, and marks it completed or failed.
On Ctrl-C the worker loop exits, but pending rows stay in the table; the
next `audit crawl <same-url>` resumes them because `_ensure_scan` reuses
the existing `running` scan row for that seed.

A leased-but-dead-process job (e.g. the laptop slept) gets picked up by
`queue.reclaim_expired`, which moves stale leases back to `pending`.
Called once at the start of every crawl.

## Why SQLite

Every moving part that wanted to be Redis / Celery / Postgres — the job
queue, the scan state, the analyses cache, the findings, the history —
is a table in one SQLite file. WAL mode makes concurrent reads safe with
a single writer. The whole tool runs in one Python process.

For a 10k-page crawl this means:
- no cluster management, no service discovery, no broker
- `data/audit.db` is the only thing you back up (+ `data/blobs/`)
- Ctrl-C is safe (everything durable lands via transactions)
- resumability is "run the same command again"

Tradeoff: no parallel writers. That's fine — the orchestrator is the
only writer and it's single-process.

## Offline posture

| What | How it stays offline |
|---|---|
| Python deps | `uv sync` locks via `uv.lock`; one-time install |
| Playwright chromium | `playwright install chromium` is a one-time download |
| Ollama model | `ollama pull qwen3-vl:2b-instruct` downloads the 1.9GB local vision model once |
| Public Suffix List | tldextract opened with `suffix_list_urls=()` → bundled snapshot |
| axe-core | vendored under `src/audit/web/static/` (test harness) |
| Defusedxml | local pure-Python parser for sitemaps |

After the one-time setup, disconnecting from the internet and running a
crawl against `localhost` still works. The only external call at runtime
is to the target site being audited (which is the point) and to
`localhost:11434` for Ollama.
