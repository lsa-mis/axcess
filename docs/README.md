# Image Text Audit — Docs

A local, offline tool for finding WCAG 1.4.5 (Images of Text) violations at
site scale. Crawls a URL, extracts every image it renders, runs OCR + a
vision-language model to decide whether each image is actually text, and
compares that against the `alt` text the page offered. The result is a
prioritized list of findings in a local web UI that you can triage, export
to CSV / Jira / Markdown, and diff across rescans.

## Read in this order

1. **[Architecture](./architecture.md)** — the big picture. What the tool
   does, the pipeline stages, how data flows from seed URL to finding, and
   what lives where on disk.
2. **[User guide](./user-guide.md)** — how to run it. Start a scan from the
   CLI or the UI, review findings, export results, rerun and see what
   changed.
3. **[Developer guide](./developer-guide.md)** — where the code lives and
   how to extend it. Adding an export format, swapping OCR or VLM
   backends, tweaking the priority formula, running tests.
4. **[Troubleshooting](./troubleshooting.md)** — what to do when a scan
   gets stuck, when a site blocks the crawler, when Ollama isn't
   answering, when scope creeps.

## Mental model in one paragraph

**A crawl is a queue-driven pipeline.** The seed URL becomes a job in a
SQLite-backed queue. Workers lease jobs, fetch the page (static HTTP first,
Playwright chromium as fallback for SPAs or WAF challenges), parse every
image reference (`<img>`, `srcset`, `<picture>`, inline SVG text), download
each image into a content-hashed blob store, OCR it, classify it through
Ollama, then move on. New in-scope links on the page become new jobs. At
end-of-crawl, the synthesizer walks every image-with-text, compares its
OCR content to the authored `alt` using rapidfuzz, computes a priority
score, and writes a findings row. The review UI reads the same SQLite DB
live.

## One-liners for the most common tasks

```bash
# Set it up (once)
make setup

# Crawl a site
uv run audit crawl https://example.com/docs/

# Open the review UI
uv run audit serve                       # → http://127.0.0.1:8765

# Rerun against the same site and see the diff
uv run audit crawl https://example.com/docs/

# Export the latest scan
uv run audit export --format csv
```

## Where things live

```
src/audit/
├── cli.py              # typer CLI: crawl / synthesize / export / serve / status
├── config.py           # Settings (env-driven, AUDIT_ prefix)
├── crawler/            # URL policy, fetchers, rate limit, orchestrator
├── extractor/          # HTML image parsing, blob store, downloader, pipeline
├── analyzer/           # OCR (tesseract) + VLM (ollama) clients
├── synthesizer/        # alt-compare, priority, remediation rules, findings
├── exports/            # CSV / JSON / Jira / Markdown / webhook
├── web/                # FastAPI + Jinja + HTMX review UI
├── db/                 # schema + migrations + typed upsert helpers + job queue
└── rules/              # remediation.yaml (hints keyed on class × adequacy)

data/                   # gitignored runtime data
├── audit.db            # SQLite with WAL
├── blobs/              # <aa>/<sha256>.<ext> image files
├── logs/               # structlog output
└── exports/            # CLI-written exports land here by default

tests/
├── unit/               # fast, no network, no browser
├── integration/        # fixture-site crawls, require tesseract
└── ui/                 # TestClient + Playwright + axe-core
```

## Non-negotiables that drive the design

- **Fully offline at runtime** after initial model pull. No telemetry, no
  CDN calls. htmx and axe-core are vendored under `src/audit/web/static/`;
  tldextract uses a bundled PSL snapshot.
- **The tool itself is WCAG 2.1 AA.** Every review-UI view has axe-core
  tests that fail the build on any violation.
- **Resumable.** All long work is in the SQLite queue. A crashed or
  Ctrl-C'd crawl picks up where it left off.
- **Single-machine footprint.** SQLite for everything — no Redis, no
  Postgres, no Celery. Workers are asyncio tasks.
- **Deterministic exports.** CSV / JSON / Markdown / Jira outputs are
  pinned by golden-file tests.

## Quick vocabulary

- **Seed URL** — where the crawl starts. Defines the scope.
- **Scope** — `(host, path_prefix)` that bounds which links to follow.
  `/bicentennial/` seeds only crawl under `/bicentennial/*`.
- **Image ref** — one occurrence of an image on a page (`<img src=…>`,
  one `srcset` candidate, one `<picture><source>`). Deduped across the
  site by `content_hash`.
- **Analysis** — the OCR + VLM output for one image. Keyed by
  `(image_id, model_versions_json)`.
- **Finding** — the review unit: one image, one scan, with severity,
  priority, remediation hint, and a workflow status.
- **Priority score** — `classification_weight + alt_adequacy_weight +
  log1p(occurrences) + above_fold_bonus`. Maps to severity via fixed
  thresholds (`>=8 critical`, `>=5 major`, `>=2 minor`, else `info`).
