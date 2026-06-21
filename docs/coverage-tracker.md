# Coverage & feature tracker

> **In the app:** this same data renders live on the **Tracking** page
> (`/app/tracking`, linked from the sidebar), served from the
> `/api/tracking` endpoint. Both that page and this doc read from
> `src/audit/web/coverage_status.py` — flip a status there and both
> update. This file is the long-form version with the verification map.

> **Per-criterion coverage matrix.** For the complete, honest breakdown of
> all 55 WCAG 2.2 Level A/AA success criteria — which are checked
> automatically, which are AI-assisted, and which still need manual testing
> (with what to test for each) — see
> [`src/audit/rules/wcag_coverage.yaml`](../src/audit/rules/wcag_coverage.yaml).
> It's the single source of truth behind the audit report's "WCAG 2.2 A/AA
> coverage" section, the in-app **Tracking** page, and the landing page.
> Today: **23 of 55** covered (6 automated, 15 partly automated, 2
> AI-assisted), **32** manual-only.

A living view of **what's shipped, what's in progress, and what's planned**
across all detection pipelines. Status here is reconciled against the
*actual code* (the registry, the probes, the migrations) — not intentions.
If a row says "Shipped," there is a wired pipeline that persists findings.

> Last reconciled: 2026-06-19. To re-check, see the "How status is
> verified" note at the bottom — every claim maps to a file you can grep.

---

## 1. Shipped pipelines (what runs today)

These run on a default crawl. The three deterministic ones need **only
chromium** (no Ollama); the two AI ones need a local Ollama daemon.

| Pipeline | `pipeline` value | Engine | WCAG SC(s) | Needs AI? | Status |
|---|---|---|---|---|---|
| axe-core | `axe` | axe **dev API**, injected into rendered DOM | dozens (1.1.1 presence, 1.3.1, 1.4.3, 2.4.x, 4.1.2, meta-viewport, …) | No — rule engine | ✅ Shipped |
| Keyboard-trap probe | `keyboard` | Deterministic Playwright (Tab-walk, Esc, iframe) | **2.1.2** | No | ✅ Shipped |
| Responsive / zoom probe | `responsive` | Deterministic Playwright (viewport mutate + CSS inject) | **1.4.4**, **1.4.10**, **1.4.12** | No | ✅ Shipped |
| Image-of-text (VLM) | `image` | OCR (Tesseract) + VLM via Ollama | **1.4.5** | **Yes** — VLM | ✅ Shipped |
| Semantic analyzer | `semantic` | Per-SC LLM via Ollama | **2.4.4** | **Yes** — Text-LLM | ✅ Shipped (1 of N) |

**The AI gap in one line:** the semantic pipeline's *machinery* is built,
but only **2.4.4** has a registered analyzer. Everything in the roadmap
table below is the queue to close that gap.

---

## 2. AI roadmap — semantic / VLM / cross-page analyzers

Source: the AI-fit analysis. **Status column reflects the repo**, which
differs from the original triage in two places (flagged ⚠️): nothing in
this table is wired beyond what Section 1 already ships.

| WCAG | Issue | AI fit | Model class | What the AI step does | Status |
|---|---|---|---|---|---|
| 1.4.5 | Images of Text | Strong | VLM | Decide if an image is really rendered text → flag image-of-text | ✅ **Shipped** (Section 1) |
| 2.4.4 | Link Purpose (In Context) | Strong | Text-LLM | Judge whether link text + surrounding context conveys destination | ✅ **Shipped** (Section 1) |
| 1.3.2 | Meaningful Sequence | Strong | VLM | Screenshot + DOM-order text; does source order match visual reading order? | 🔲 Not Started ⚠️ *(no code yet — was marked in-progress)* |
| 3.2.3 | Consistent Navigation | Strong | Embedding (~30M, CPU) | Embed each page's `<nav>`, cluster; outliers = nav diverges | 🔲 Not Started ⚠️ *(no code yet — was marked in-progress)* |
| 2.4.6 | Headings and Labels | Strong | Text-LLM (~1B) | Does heading describe its section? Would a user know what a field wants? | 🔲 Not Started *(in default criteria list, no analyzer class)* |
| 3.3.2 | Labels or Instructions | Strong | Text-LLM | Per field: combine label + placeholder + `aria-describedby`; is it enough? | 🔲 Not Started *(in default criteria list, no analyzer class)* |
| 1.2.1 | Audio transcript (prerecorded) | Strong | Text-LLM (~1B) | Read DOM around each `<audio>`; is a transcript present/linked within reach? | 🔲 Not Started |
| 1.2.4 | Captions (prerecorded video) | Strong | ASR (Whisper) + Text-LLM | Transcribe audio track, diff vs published `<track>`; flag missing/garbage/desynced | 🔲 Not Started |
| 2.2.2 | Pause, Stop, Hide | Strong | VLM (video) | 3-sec capture; anything auto-moving >5s with no pause control? | 🔲 Not Started |
| 2.4.3 | Focus Order | Strong | VLM + Playwright | Tab through, capture focus bounding boxes; does order match reading order? | 🔲 Not Started |
| 2.4.11 | Focus Not Obscured (Min) | Strong | VLM + Playwright | Screenshot each focus state; is focused element hidden behind sticky/overlay? | 🔲 Not Started |
| 3.2.4 | Consistent Identification | Strong | Embedding + VLM | Find visually similar components across pages; verify accessible names match | 🔲 Not Started |
| 3.2.6 | Consistent Help | Strong | Embedding + geometry | Locate "help" affordances across crawl; flag pages where help moves | 🔲 Not Started |

### Reuse map (what each roadmap item slots into)

- **Text-LLM, static** (1.2.1, 2.4.6, 3.3.2): reuse the existing semantic
  HTML extractor + `registry.py` — each is one new analyzer class + prompt
  + one registry row. Cheapest to ship; closes the most-requested gap.
- **VLM + Playwright runtime** (1.3.2, 2.2.2, 2.4.3, 2.4.11): reuse the
  open Playwright session (same place the keyboard/responsive probes run).
- **Cross-page / embedding** (3.2.3, 3.2.4, 3.2.6): a *new* analyzer that
  runs **after** the crawl over all captured pages — no per-page hook
  exists yet; this is the largest net-new surface.

---

## How status is verified

| Claim | Where to confirm |
|---|---|
| Which semantic SCs have analyzers | `src/audit/analyzer/semantic/registry.py` (`_REGISTRY` dict) + `analyzers/` dir |
| Which probes ship | `src/audit/analyzer/keyboard/`, `src/audit/analyzer/responsive/` |
| Allowed `pipeline` values | latest `src/audit/db/migrations/000*_*pipeline.sql` CHECK |
| Default criteria the orchestrator requests | `CrawlConfig.semantic_criteria` in `src/audit/crawler/orchestrator.py` |

A criterion listed in `semantic_criteria` but **absent from `_REGISTRY`**
is logged at WARNING and skipped — configured ≠ implemented.
