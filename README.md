<div align="center">

# Axcess

**A local-first, AI-augmented web accessibility auditor.**

Axcess crawls a website, renders every page in a real browser, and runs
**seven complementary detection pipelines** — a rule engine, three behavioural
probes, and three AI-assisted analyzers — covering **28 of 55 WCAG 2.2 A/AA
success criteria**. It runs entirely on your machine. No cloud, no telemetry,
no data leaving your laptop.

[Landing page](https://reganmaharjan.com.np/axcess) ·
[Documentation](./docs/README.md) ·
[What it covers](./docs/coverage-tracker.md) ·
[Hosting](./docs/hosting.md)

`Python 3.11+` · `WCAG 2.2 AAA` (the tool audits *itself* at AAA) · `MIT`

</div>

---

## Why Axcess

Most accessibility scanners are a single rule engine. Rule engines are fast and
exact, but they can only check what's mechanically decidable — *is there an
`alt` attribute?*, *does this text meet 4.5:1 contrast?* They go quiet on the
criteria that actually need **judgment**:

- Is this image *really text* dressed up as a picture? (WCAG 1.4.5)
- Does this link's text make sense out of context? (WCAG 2.4.4)
- Does the page reflow at 320px, or trap the keyboard in a modal?

Axcess closes that gap by combining seven kinds of detection in one crawl:

| | Pipeline | How it decides | SCs | Needs a model? |
|---|---|---|---|---|
| 🟦 | **axe-core** | Rule engine on the rendered DOM | dozens | No |
| 🟦 | **Keyboard-trap probe** | Tabs through every focusable element | 2.1.2 | No |
| 🟦 | **Responsive / zoom probe** | Mutates viewport + injects text-spacing CSS | 1.4.4/.10/.12 | No |
| 🟦 | **Focus probe** | Focus geometry + positive-tabindex (F44) | 2.4.11, 2.4.3 | No |
| 🟨 | **Image-of-text (VLM)** | OCR + a vision model judge each image | 1.4.5 | Yes (Ollama) |
| 🟨 | **Semantic analyzer** | A text model reads context like a human | 2.4.4/.6, 3.3.2, 1.2.1 | Yes (Ollama) |
| 🟨 | **Visual probe** | Screenshot + vision model (1.3.2); autoplay/marquee (2.2.2) | 1.3.2, 2.2.2 | 1.3.2 only |

The blue pipelines need only a browser — run Axcess with **zero AI** and still
get axe + keyboard + responsive + focus + motion coverage. The yellow pipelines
add the judgment calls, all via a **local [Ollama](https://ollama.com) daemon**
so your content never leaves the machine.

👉 **See exactly what's covered today vs. planned:** the in-app **Tracking**
page (`/app/tracking`) and [`docs/coverage-tracker.md`](./docs/coverage-tracker.md),
both generated from one source of truth so they can't drift from the code.

---

## Quickstart

```bash
# 1. Install (uv + Playwright chromium + data dirs), then the DB schema
make setup
make migrate

# 2. Crawl a site — renders every page and runs axe + keyboard + responsive
uv run audit crawl https://example.com --max-pages 50

# 3. Open the review UI (React SPA)
make frontend-build      # one time, builds the SPA
uv run audit serve       # → http://127.0.0.1:8765/app/
```

Want the AI pipelines too? Start [Ollama](https://ollama.com), then
`make fetch-models` to pull the vision + text models. Don't want them? Add
`--skip-vlm --skip-ocr --skip-semantic` and the three browser-only pipelines
still run.

**Requirements:** macOS or Linux · Python 3.11+ ·
[uv](https://github.com/astral-sh/uv) · Tesseract (`brew install tesseract`) ·
optionally [Ollama](https://ollama.com) for the AI pipelines.

---

## How it works

```
seed URL
   │
   ▼  queue-driven crawl (SQLite job queue, resumable)
render each page  ──►  static HTTP first, Playwright chromium when needed
   │
   ├─► axe-core ........... rule violations on the live DOM
   ├─► keyboard probe ..... tab-walk / Esc / iframe traps        (SC 2.1.2)
   ├─► responsive probe ... reflow @320px, zoom clip, text-spacing (1.4.4/10/12)
   ├─► focus probe ........ focus hidden by overlay / positive tabindex (2.4.11/2.4.3)
   ├─► image-of-text ...... OCR → VLM: is this image really text?  (SC 1.4.5)
   ├─► semantic ........... text LLM: headings/labels/links read right? (2.4.x/3.3.2/1.2.1)
   └─► visual ............. VLM reading-order + autoplay/marquee motion (1.3.2/2.2.2)
   │
   ▼  synthesize
prioritized findings  ──►  React review UI · CSV / JSON / Jira / Markdown exports · rescan diffs
```

Everything persists to one **SQLite** database (WAL mode, content-addressed
image blobs). A crashed or `Ctrl-C`'d crawl resumes from the queue. Re-crawling
the same site produces a **diff** — new / resolved / still-open findings.

For the full picture, read [`docs/architecture.md`](./docs/architecture.md).

---

## The review UI

A single **React SPA** (Vite + Tailwind + TanStack Query) served at `/app/`,
backed by a FastAPI `/api/*` JSON surface. It's a Michigan-palette design
system that **audits itself at WCAG 2.2 AAA** — every view has axe-core tests
in the AAA tag pack that fail the build on any violation.

- **Dashboard / Scans** — start a crawl, watch live per-pipeline progress.
- **Issues** — one row per issue across all pipelines, with conformance level,
  affected abilities, and a what / why / how fix card.
- **Findings** — filterable, paginated, with image previews and OCR/VLM evidence.
- **Tracking** — what the tool detects today vs. the AI roadmap.
- **Exports** — CSV · JSON · Jira CSV · Markdown · a holistic audit report.

---

## Hosting it for a team

Axcess is local-first, but you can host it on an always-on machine for a small
team over your LAN or [Tailscale](https://tailscale.com), behind an opt-in
shared-token gate:

```bash
export AUDIT_ACCESS_TOKEN=$(openssl rand -hex 16)
make serve     # binds 0.0.0.0; no token set = stays a local-only app
```

Full runbook (Tailscale, autostart, the security model): [`docs/hosting.md`](./docs/hosting.md).

---

## Documentation

Axcess keeps **one front door and one hub**, so docs don't sprawl:

- **This README** — what Axcess is, why, and how to start. The single entry point.
- **[`docs/README.md`](./docs/README.md)** — the documentation hub: read-in-order
  guides plus the design contract for the UI.

| Doc | For | Covers |
|---|---|---|
| [architecture.md](./docs/architecture.md) | understanding it | pipeline, data flow, storage |
| [user-guide.md](./docs/user-guide.md) | running it | CLI + UI walkthroughs |
| [developer-guide.md](./docs/developer-guide.md) | extending it | code layout, "add a page", tests |
| [coverage-tracker.md](./docs/coverage-tracker.md) | scoping it | shipped vs. planned, the AI roadmap |
| [hosting.md](./docs/hosting.md) | deploying it | LAN / Tailscale + token gate |
| [troubleshooting.md](./docs/troubleshooting.md) | unsticking it | Cloudflare, stuck scans, Ollama, scope |
| [accessibility.md](./docs/accessibility.md) · [personas.md](./docs/personas.md) · [design-principles.md](./docs/design-principles.md) | building the UI | the AAA contract, who it serves |

**Anti-drift principle:** anything that exists in two places is generated from
one. The coverage tables (in-app + `coverage-tracker.md` + this README) trace
back to [`src/audit/web/coverage_status.py`](./src/audit/web/coverage_status.py);
exports are pinned by golden-file tests. Flip a status in the source, and every
surface updates.

---

## Development

```bash
make test         # pytest (434 tests: unit + integration + Playwright/axe UI)
make lint         # ruff check + format --check
make typecheck    # mypy --strict on src/
make help         # every target
```

The gates a change must pass: **ruff**, **mypy (strict)**, **pytest**, and the
**frontend** lint/typecheck/build. The UI's own AAA axe tests run in CI against
the built SPA.

---

## Project layout

```
src/audit/
├── cli.py            # typer CLI: crawl / synthesize / export / serve / status
├── crawler/          # URL policy, fetchers, rate limit, orchestrator
├── extractor/        # HTML image parsing, content-addressed blob store
├── analyzer/         # OCR, VLM, semantic, keyboard + responsive probes
├── synthesizer/      # alt-compare, priority, remediation, diff
├── exports/          # CSV / JSON / Jira / Markdown / audit report / webhook
├── web/              # FastAPI /api/* + the React SPA (frontend/)
├── db/               # schema + migrations + typed upserts + job queue
└── rules/            # YAML rule packs (remediation, audit cards, models)
tests/                # unit · integration (fixture site) · ui (Playwright + axe)
docs/                 # the documentation hub
site/                 # the static landing page (deployed to GitHub Pages)
```

---

## License

[MIT](./LICENSE). Built at the University of Michigan. 〽️
