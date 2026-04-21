# Image Text Audit

Local, offline web accessibility auditor focused on **WCAG 1.4.5 — Images of Text**. Crawls a site, finds every image, runs OCR + a local VLM to detect images that contain text, cross-checks against `alt`, and surfaces prioritized findings in a local UI with rescan/diff support.

## Status — v0.1 (Phase 1: crawl and store)

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
- **CLI** — `audit crawl <url>` and `audit status` produce Rich summary tables.

Not yet implemented: image extraction, OCR, VLM, finding synthesis, review
UI, exports, rescans. See [PLAN.md](PLAN.md).

## Try it

```bash
make setup
make migrate
# in one shell, serve the fixture site
make fixture-site                    # → http://127.0.0.1:8000
# in another shell
uv run audit crawl http://127.0.0.1:8000 --max-pages 50
uv run audit status
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
