# System Design + Coverage Gap

This document is the single-page answer to three questions about the
WCAG accessibility audit tool:

1. **How is the system designed?** — components, data flow, schemas,
   what the operator sees, where the code lives.
2. **What does it actually detect, and how?** — per-pipeline behavior,
   strengths, failure modes.
3. **What is the gap to 100% WCAG manual-testing coverage?** — every
   Level A + AA success criterion classified as automated, partial, or
   manual-only, with the reason and what a human needs to do for the
   ones we can't reach.

Read top to bottom for orientation. The coverage table in §6 and the
manual test plan in §7 are the practical deliverables for an
accessibility lead deciding "what does this tool do for me, what do I
still have to do myself, and how?"

> **Honest framing.** This tool does not deliver WCAG conformance. No
> automated tool does. Even the GenA11y LLM pipeline (peer-reviewed,
> FSE 2025) tops out around **37 of WCAG 2.2's ~50 testable success
> criteria** — about 60–70 % coverage at best. The remaining ~30–40 %
> *require* human judgment: meaningful alt text, descriptive headings,
> keyboard-trap detection in custom widgets, caption accuracy. Treat
> a green run of this tool as "necessary, not sufficient" — see §7 for
> the manual test plan that fills the rest.

---

## Table of contents

- [1. Architecture at a glance](#1-architecture-at-a-glance)
- [2. The three detection pipelines](#2-the-three-detection-pipelines)
- [3. Data flow per crawled page](#3-data-flow-per-crawled-page)
- [4. Data model](#4-data-model)
- [5. Operator workflow](#5-operator-workflow)
- [6. WCAG 2.2 A + AA criterion-by-criterion coverage](#6-wcag-22-a--aa-criterion-by-criterion-coverage)
- [7. The gap to 100 % — what manual testing must add](#7-the-gap-to-100--what-manual-testing-must-add)
- [8. Recommended manual test plan](#8-recommended-manual-test-plan)
- [9. References](#9-references)

---

## 1. Architecture at a glance

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            OPERATOR INTERFACES                              │
│  ┌──────────────────────────┐   ┌──────────────────────────────────────┐    │
│  │ CLI                      │   │ Web (FastAPI on :8765)               │    │
│  │   audit crawl            │   │   /          → Dashboard             │    │
│  │   audit synthesize       │   │   /scans     → list + new scan       │    │
│  │   audit export           │   │   /scans/:id → progress + summary    │    │
│  │   audit diff             │   │   /scans/:id/issues → unified cards  │    │
│  │   audit ollama-serve     │   │   /scans/:id/issues/:key → detail    │    │
│  └──────────────┬───────────┘   │   /scans/:id/findings → image grid   │    │
│                 │               │   /scans/:id/a11y     → WCAG by SC   │    │
│                 │               │   /scans/:id/a11y/by-rule            │    │
│                 │               │   /pages/:id          → per-page     │    │
│                 │               │   /scans/:id/diff?compare_to=...     │    │
│                 │               │   /scans/:id/export/{csv|json|jira|  │    │
│                 │               │     markdown|audit}                  │    │
│                 │               └────────────────┬─────────────────────┘    │
│                 │                                │                          │
│                 │       ┌────────────────────────┴───────────┐              │
│                 └──────►│ src/audit/cli.py / web/server.py   │              │
│                         └────────────────┬───────────────────┘              │
└──────────────────────────────────────────┼──────────────────────────────────┘
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            ORCHESTRATOR                                     │
│  src/audit/crawler/orchestrator.py                                          │
│                                                                              │
│  ┌─ Seed URL → URL policy ──────────────────────────────┐                   │
│  │   • normalize, robots.txt, scope, sitemap discovery   │                   │
│  └──────────────────────────────────────────────────────┘                   │
│  ┌─ SQLite-backed job queue (resumable) ────────────────┐                   │
│  │   • enqueue / lease / complete / reclaim_expired      │                   │
│  └──────────────────────────────────────────────────────┘                   │
│  ┌─ Per-host limiter + worker pool ─────────────────────┐                   │
│  │   • configurable RPS, concurrency_per_host             │                   │
│  └──────────────────────────────────────────────────────┘                   │
│                                                                              │
│   For each leased URL the orchestrator runs:                                │
│                                                                              │
│   1. FETCH                                                                  │
│      ┌──────────────────────────┐    escalate     ┌────────────────────┐   │
│      │ httpx StaticFetcher      │ ───────────────►│ Playwright Js…     │   │
│      │ src/audit/crawler/       │   on JS-only /  │ src/audit/crawler/ │   │
│      │   fetcher.py             │   WAF interstn  │   js_fetcher.py    │   │
│      └──────────────────────────┘                 └─────────┬──────────┘   │
│                                                              │              │
│   2. EXTRACT IMAGES (per HTML page)                          │              │
│      ┌──────────────────────────────────────────────────┐    │              │
│      │ src/audit/extractor/                              │    │              │
│      │   html_images.py · svg_text.py · css_bg.py        │    │              │
│      │   context.py · downloader.py · pipeline.py        │    │              │
│      │   blob_store (content-hash dedupe, data/blobs/)   │    │              │
│      └────────────────────────┬─────────────────────────┘    │              │
│                               ▼                              │              │
│   3. ANALYZE (three independent pipelines)                   │              │
│   ┌─────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐   │
│   │ axe-core JS     │  │ OCR + VLM (1.4.5)    │  │ Per-criterion LLM    │   │
│   │ (DOM rules)     │  │ image-of-text class. │  │ (semantic SCs)       │   │
│   │ analyzer/axe.py │  │ analyzer/ocr/        │  │ analyzer/semantic/   │   │
│   │ Phase 8         │  │ analyzer/vlm/        │  │ Phase 9              │   │
│   └────────┬────────┘  └──────────┬───────────┘  └──────────┬───────────┘   │
│            └──────────────┬───────┴──────────────────────────┘              │
│                           ▼                                                 │
│   4. PERSIST + SYNTHESIZE → SQLite                                          │
│      ┌──────────────────────────────────────────────────────────────┐       │
│      │ data/audit.db (WAL mode, yoyo migrations 0001..0003)         │       │
│      │   scans · pages · images · page_images · analyses · findings │       │
│      │   page_a11y_findings (axe + semantic) · finding_history      │       │
│      │   jobs                                                       │       │
│      └──────────────────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │ HTTP /api/* + Jinja templates
                                  │
┌─────────────────────────────────┴────────────────────────────────────────────┐
│                          UI + EXPORTS                                       │
│  src/audit/web/{server.py, issues.py, a11y_queries.py,                      │
│                 image_findings_queries.py, templates/}                      │
│  src/audit/web/frontend/ (React SPA at /app/*)                              │
│  src/audit/exports/{audit_report,csv,json,jira,markdown}.py                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Footprint**: ~60 Python source modules, ~30 React components (the only
UI — the legacy Jinja/HTMX pages were retired), ~450 unit / integration
tests. Local-first by design — every
inference call routes through Ollama on the loopback (no cloud, no API
costs). The Phase-2 transformation hardened the UI itself to WCAG 2.2
AAA (the audit tool's own UI passes the audit it runs).

---

## 2. The three detection pipelines

Each pipeline reaches a different *class* of WCAG defect. They compose;
none replaces the others.

### 2.1 axe-core (DOM, rule-based) — Phase 8

| Property | Value |
|---|---|
| Source | `src/audit/analyzer/axe.py` + bundled `axe.min.js` |
| Trigger | Every page rendered through Playwright (`js_fetcher.py`) |
| Detection style | Deterministic rules over the live DOM |
| WCAG SCs covered | ~13 (1.1.1 partial, 1.3.1 partial, 1.4.1, 1.4.3, 1.4.4 partial, 1.4.10, 2.4.3 partial, 2.4.4 syntactic, 2.4.7 partial, 2.5.5 partial, 2.5.8, 3.1.1, 4.1.2 syntactic) |
| Best at | "Does this attribute exist?" — alt-attribute presence, `lang` on `<html>`, label/for pairing, contrast math, positive tabindex |
| Blind spot | *Meaning*. Cannot say whether an alt text is descriptive, whether a label is clear, whether a heading is meaningful. |
| Precision | ~98–100 % on what it flags (axe is conservative) |

### 2.2 OCR → VLM (image-of-text classification) — Phases 3 + 4

| Property | Value |
|---|---|
| Source | `src/audit/analyzer/ocr/` + `src/audit/analyzer/vlm/ollama.py` |
| Trigger | Every image extracted from a page that passes the OCR "text-candidate" threshold (`confidence ≥ 60 % AND word_count ≥ 3`) |
| Detection style | Tesseract OCR detects candidate text; local Qwen2-VL (or Moondream) classifies the image into `essential / informational / logo / decorative / no_meaningful_text` |
| WCAG SCs covered | 1.4.5 (Images of Text) — *the* criterion no other open tool detects well |
| Best at | Distinguishing intentional content-bearing text-in-image (a headline rendered as a JPEG) from decorative use (a logo, a stock photo with incidental text) |
| Blind spot | Foreign-script OCR accuracy; very stylized fonts; OCR false positives on noisy images (VLM filters these but not perfectly) |
| Precision | ~85 % in practice (on M-series with qwen2-vl:2b, against hand-labeled fixtures) |

### 2.3 Per-criterion LLM (semantic SCs) — Phase 9 (in progress)

| Property | Value |
|---|---|
| Source | `src/audit/analyzer/semantic/` |
| Trigger | After fetch, before persistence — one LLM call per (page × enabled criterion) |
| Detection style | Per-SC element extractor (selectolax) → per-SC prompt template → local Ollama text model → JSON parse → per-finding rows |
| WCAG SCs covered today | **1** (SC 2.4.4 Link Purpose — pilot) |
| WCAG SCs planned (Phase 9.2) | +9 more: 2.4.9, 2.4.6, 2.4.10, 2.5.3, 3.3.2, 1.3.5, 1.3.1, 4.1.2, 1.1.1 |
| Ultimate cap (Phase 9.4 calibration → ≥22 SCs) | Matches GenA11y's 37-SC static-detectable set |
| Best at | The "is this meaningful?" judgments axe can't make — descriptive link text, label-in-name match, ARIA role coherence |
| Blind spot | Probabilistic: 85–95 % precision depending on prompt + model. Costs ~1.5 s/call × N criteria × N pages. No multilingual calibration. |
| Why local-only | At 10k pages × 10 criteria = 100k LLM calls. The same scan on OpenAI would cost ≈ $48k per GenA11y's numbers; on local Ollama it costs $0 marginal. |

### Pipeline boundaries

```
       ┌─────────────────────────────────────────────┐
       │      Whole-page DOM (Playwright/static)     │
       └────────────────┬────────────────────────────┘
                        │
        ┌───────────────┼────────────────────────────────────┐
        │               │                                    │
        ▼               ▼                                    ▼
  ┌──────────┐    ┌─────────────────────┐         ┌─────────────────────────┐
  │ axe-core │    │ Per-criterion       │         │ Image extraction        │
  │ ~13 SCs  │    │ semantic LLM        │         │ → OCR → VLM (SC 1.4.5)  │
  │ rule-    │    │ ~1 SC today, 22+    │         │ image-of-text classifier│
  │ based    │    │ over Phase 9.x      │         │                         │
  └────┬─────┘    └─────────┬───────────┘         └─────────┬───────────────┘
       │                    │                               │
       │                    │                               │
       ▼                    ▼                               ▼
  page_a11y_findings (pipeline column distinguishes)    findings table
  ──────────────────────────────────────────────       (image-of-text only)
  pipeline='axe'  ·  pipeline='semantic'
```

---

## 3. Data flow per crawled page

```
                         orchestrator._process_one(url)
                                       │
              ┌────────────────────────┴────────────────────────┐
              │                                                 │
              ▼                                                 ▼
       robots + scope check                              limit / RPS gate
              │
              ▼
       StaticFetcher (httpx)
              │
              ├── 200 / HTML?  ───► render_detect.is_js_only? ───► JsFetcher
              │                                                     (chromium)
              ├── 4xx / 5xx ────► persist page row with status, exit
              │
              ▼
   _record_page(scan_id, url, html_hash) → upsert pages row
              │
              ▼
   process_page() — image extraction
   ┌───────────────────────────────────────────────────────┐
   │   <img>, <picture>, srcset, computed background-image,│
   │   inline <svg><text> → ImageRef list                  │
   │   downloader → blob_store (content_hash dedupe)       │
   │   OCR (confidence ≥ 60, word_count ≥ 3) → flag        │
   │   VLM classify → analyses row + synthesize finding    │
   └───────────────────────────────────────────────────────┘
              │
              ├── axe enabled? ────► axe.run(page) → tuple[AxeViolation]
              │                       │
              │                       ▼
              │                  _persist_axe() → page_a11y_findings
              │                                       (pipeline='axe')
              │
              ├── semantic enabled? ─► for each enabled SC:
              │                          extract → prompt → Ollama → parse
              │                       │
              │                       ▼
              │                  _persist_semantic() → page_a11y_findings
              │                                       (pipeline='semantic')
              │
              ▼
   _enqueue_children(in-scope hrefs) → job queue
```

**Resumability.** Every step writes to SQLite under a single connection
held by the worker. An interrupted crawl leaves jobs in `leased` state;
on restart, `queue.reclaim_expired()` re-enqueues anything past its
lease deadline and the run picks up where it left off without
duplicating rows (every upsert is idempotent on its natural key).

---

## 4. Data model

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│   scans      │1───*│   pages      │1───*│  page_images     │
│              │     │              │     │                  │
│ id PK        │     │ id PK        │     │ id PK            │
│ seed_url     │     │ scan_id FK   │     │ page_id FK       │
│ status       │     │ url_norm     │     │ image_id FK      │
│ started_at   │     │ status_code  │     │ alt_text         │
│ finished_at  │     │ title        │     │ role             │
│ page_count   │     │ render_mode  │     │ context_snippet  │
│ finding_*    │     │ html_hash    │     │ above_fold       │
│ axe_*        │     └──────┬───────┘     │ position         │
└──────────────┘            │             └──────┬───────────┘
                            │                    │
                            │            ┌───────┴────┐
                            │            ▼            │
                            │     ┌─────────────┐     │
                            │     │  images     │*────┘
                            │     │             │
                            │     │ id PK       │
                            │     │ content_h   │  (SHA-256, dedupe)
                            │     │ src_url_can │
                            │     │ mime / size │
                            │     │ blob_path   │  (data/blobs/<aa>/<...>.<ext>)
                            │     │ has_svg_txt │
                            │     └──────┬──────┘
                            │            │
                            │            │1
                            │            ▼*
                            │     ┌──────────────┐
                            │     │  analyses    │   one row per
                            │     │              │   (image × model
                            │     │ id PK        │    × prompt) tuple
                            │     │ image_id FK  │
                            │     │ ocr_text     │
                            │     │ ocr_confid   │
                            │     │ vlm_label    │
                            │     │ vlm_rational │
                            │     │ model_vers   │
                            │     │ prompt_vers  │
                            │     └──────────────┘
                            │
                            │1                          ┌─────────────────────┐
                            ▼*                         │ page_a11y_findings  │
                     ┌──────────────┐                  │ (axe + semantic)    │
                     │  findings    │                  │                     │
                     │ (image       │                  │ id PK               │
                     │  pipeline    │                  │ page_id FK          │
                     │  only —      │                  │ scan_id FK          │
                     │  SC 1.4.5)   │                  │ pipeline (axe|sem)  │
                     │              │                  │ criterion_sc        │
                     │ id PK        │                  │ rule_id             │
                     │ image_id FK  │                  │ wcag_sc, wcag_level │
                     │ scan_id FK   │                  │ impact, help        │
                     │ severity     │                  │ target_selector     │
                     │ wcag_criter  │                  │ failure_summary     │
                     │ status       │                  │ html_snippet        │
                     │ priority_sc  │                  │ target_hash         │
                     │ remediation  │                  │ status              │
                     └──────┬───────┘                  └──────────┬──────────┘
                            │                                     │
                            └─────────────┬───────────────────────┘
                                          ▼
                                  ┌──────────────────┐
                                  │ finding_history  │
                                  │ id PK            │
                                  │ finding_id FK    │
                                  │ change_type      │
                                  │ from / to_status │
                                  │ actor (sys|user) │
                                  │ changed_at       │
                                  └──────────────────┘
```

**Key dedupe identities** (idempotent upserts everywhere — re-running
a crawl never produces duplicate rows):

| Table | Natural key |
|---|---|
| `images` | `content_hash` |
| `pages` | `(scan_id, url_normalized)` |
| `page_images` | `(page_id, image_id, position)` |
| `analyses` | `(image_id, model_versions_json)` |
| `findings` | `(image_id, scan_id)` |
| `page_a11y_findings` | `(page_id, rule_id, target_hash)` |

Why two finding tables? Image-of-text findings dedupe across pages by
`content_hash` (one image shows up on N pages, gets one finding row).
DOM/semantic findings are page-scoped — the same axe rule firing on
two pages is two findings. Different lifecycles → different tables;
the Issues view unifies them at read time via
`src/audit/web/issues.py`.

---

## 5. Operator workflow

### 5.1 Crawl

```
  $ uv run audit crawl https://example.com/section/ \
      --max-pages 500 --use-js \
      --semantic-criteria 2.4.4
```

Or via the UI: **Scans → New scan**. The orchestrator persists the
config (`scans.config_json`) so a re-run of the same seed URL resumes
the same scan row.

CLI flags worth knowing (all opt-out, all default-on):

| Flag | Effect |
|---|---|
| `--skip-ocr` | Skip OCR; image-of-text classifier won't fire |
| `--skip-vlm` | Skip VLM (SC 1.4.5 classification only) |
| `--skip-axe` | Skip axe-core pass |
| `--skip-semantic` | Skip per-criterion LLM pass |
| `--axe-level {A,AA,AAA}` | WCAG level filter for axe rules |
| `--semantic-criteria 2.4.4,1.3.1` | Override default 10-SC list |
| `--use-js` | Force Playwright on every page (default: heuristic escalation) |
| `--rps 2.0` | Polite-crawler rate limit per host |

### 5.2 Triage

The unified **Issues view** at `/scans/:id/issues` is the operator's
main entry point. Each card shows:

- WCAG conformance badge (A / AA / AAA / BP)
- Pipeline (axe / image / semantic — different glyphs)
- Occurrence count + affected page count
- Priority (severity × log(1+pages) — pinned in `web/issues.py`)
- Status chips (`new / reviewing / in_progress / remediated / accepted_risk / false_positive`)
- Expandable body with **what / why / how** drawn from
  `src/audit/rules/audit_report.yaml`
- Deep-link to per-issue detail with "Pages with this issue" table

Bulk status: per-group select + Apply button changes status across
many findings in one POST. Useful for closing-out N occurrences of
the same root cause.

Keyboard shortcuts on the detail pages: `j/k` next/prev, `0–5` set
status (`0`=new, `5`=false_positive), `?` show help. Verified in
`tests/ui/test_accessibility_axe.py`.

### 5.3 Export

`/scans/:id/export/{format}` — five formats:

| Format | Audience | Notes |
|---|---|---|
| `audit` (Markdown) | Web team / stakeholders | The framework-shaped report — issue cards with fix steps, owner, effort, verification. **Lead with this one.** |
| `csv` | Spreadsheets, scripts | Unified row shape with `finding_kind` discriminator |
| `json` | Downstream pipelines | Schema v2, includes both finding kinds |
| `jira` | Ticket import | One Jira issue per finding, with labels (`wcag-1-4-3`, `owner-dev`) and priority mapped from severity/impact |
| `markdown` | Data-dense report | Tabular dump of everything |

Triaged-out findings (`remediated` / `accepted_risk` / `false_positive`)
are excluded from the Jira export so a re-run doesn't reopen closed
tickets.

---

## 6. WCAG 2.2 A + AA criterion-by-criterion coverage

Every Level A + AA success criterion in WCAG 2.2 (50 total), classified
honestly. Conventions:

- **✓ Full** — automated detection is reliable; minimal human review
  needed.
- **◐ Partial** — automation catches the syntactic case (attribute
  present? value valid?); a human still has to judge meaning.
- **◯ Manual** — automation can't testably reach this. The tool may
  surface evidence (e.g. a screenshot at 200 % zoom) but the verdict
  is human.
- **N/A** — out of scope for static analysis (live media / no auth).

| SC | Level | Title | Coverage | How |
|---|---|---|---|---|
| 1.1.1 | A | Non-text Content | ◐ | axe `image-alt` flags missing alt; Phase-9 LLM judges alt-text *descriptiveness*; manual review for complex content (charts, diagrams) |
| 1.2.1 | A | Audio-only / Video-only (Prerecorded) | ◯ | Needs human review of transcript adequacy |
| 1.2.2 | A | Captions (Prerecorded) | ◯ | Caption accuracy + sync requires human |
| 1.2.3 | A | Audio Description / Media Alternative | ◯ | Human review |
| 1.2.4 | AA | Captions (Live) | ◯ | Live media — out of scope for static crawl |
| 1.2.5 | AA | Audio Description (Prerecorded) | ◯ | Human review |
| 1.3.1 | A | Info and Relationships | ◐ | axe catches list/heading misuse; Phase-9 LLM flags styled-div-as-heading; meaning judgment human |
| 1.3.2 | A | Meaningful Sequence | ◯ | Reading order + DOM order + visual order alignment — needs human + assistive tech |
| 1.3.3 | A | Sensory Characteristics | ◯ | "Click the round button" type instructions need human review |
| 1.3.4 | AA | Orientation | ◐ | CSS media-query check possible; not yet implemented |
| 1.3.5 | AA | Identify Input Purpose | ◐ | Phase-9 LLM flags missing/wrong `autocomplete`; human checks intent |
| 1.4.1 | A | Use of Color | ◐ | axe `link-in-text-block` flags color-only links; broader uses of color need human |
| 1.4.2 | A | Audio Control | ◯ | Behavioral — needs interaction |
| 1.4.3 | AA | Contrast (Minimum) | ✓ | axe `color-contrast` — deterministic 4.5:1 / 3:1 math |
| 1.4.4 | AA | Resize Text | ◐ | Tool captures 200 %-zoom screenshots; human verifies no clipping |
| 1.4.5 | AA | Images of Text | ✓ | Full OCR + VLM pipeline — our flagship |
| 1.4.10 | AA | Reflow | ◐ | Captures 320 px screenshot; human verifies no 2-axis scroll |
| 1.4.11 | AA | Non-text Contrast | ✓ | axe + Phase-2 contrast helper covers focus rings, borders, severity chips |
| 1.4.12 | AA | Text Spacing | ◐ | Test in `tests/ui/test_accessibility_text_spacing.py`; human re-verifies on third-party content |
| 1.4.13 | AA | Content on Hover or Focus | ◯ | Tooltip + popover dismissability — behavioral, needs human |
| 2.1.1 | A | Keyboard | ◯ | Custom-widget keyboard support — pure manual |
| 2.1.2 | A | No Keyboard Trap | ◯ | Trap detection — pure manual |
| 2.1.4 | A | Character Key Shortcuts | ◯ | Behavioral |
| 2.2.1 | A | Timing Adjustable | ◐ | If no JS timers detected, presumed OK; human verifies any popup countdowns |
| 2.2.2 | A | Pause, Stop, Hide | ◯ | Auto-playing animations / carousels — human checks pause control |
| 2.3.1 | A | Three Flashes / Below Threshold | ◯ | Flash detection — out of scope; manual review |
| 2.4.1 | A | Bypass Blocks | ◐ | axe `skip-link` checks structural skip-link presence; human verifies it works |
| 2.4.2 | A | Page Titled | ✓ | axe `document-title` |
| 2.4.3 | A | Focus Order | ◐ | axe `tabindex` flags positive tabindex (likely-wrong); full order requires keyboard pass |
| 2.4.4 | A | Link Purpose (In Context) | ◐ | axe `link-name` (syntactic); **Phase-9 LLM judges descriptiveness** |
| 2.4.5 | AA | Multiple Ways | ◐ | Detect sitemap.xml + search box + nav — presence only |
| 2.4.6 | AA | Headings and Labels | ◐ | Phase-9 (planned) LLM for descriptiveness; manual fallback |
| 2.4.7 | AA | Focus Visible | ◐ | axe partial (focus-visible CSS detection); human verifies under real interaction |
| 2.4.11 | AA | Focus Not Obscured (Minimum) | ◯ | Sticky-header overlap with focused element — manual |
| 2.5.1 | A | Pointer Gestures | ◯ | Multi-touch / drag gestures need single-pointer alternative — manual |
| 2.5.2 | A | Pointer Cancellation | ◯ | Touch / mouse-up behavior — manual |
| 2.5.3 | A | Label in Name | ◐ | **Phase-9 (planned)** LLM checks accessible-name ⊇ visible-label |
| 2.5.4 | A | Motion Actuation | ◯ | Shake / tilt UI — manual |
| 2.5.7 | AA | Dragging Movements | ◯ | Drag UI needs click alternative — manual |
| 2.5.8 | AA | Target Size (Minimum) | ✓ | axe `target-size` |
| 3.1.1 | A | Language of Page | ✓ | axe `html-has-lang` |
| 3.1.2 | AA | Language of Parts | ◐ | axe detects missing `lang` attr; correctness needs human |
| 3.2.1 | A | On Focus | ◯ | No context-change-on-focus — behavioral |
| 3.2.2 | A | On Input | ◯ | Behavioral — needs interaction |
| 3.2.3 | AA | Consistent Navigation | ◯ | Cross-page consistency — manual |
| 3.2.4 | AA | Consistent Identification | ◯ | Same affordance, same identifier — manual |
| 3.2.6 | A | Consistent Help | ◯ | Manual |
| 3.3.1 | A | Error Identification | ◐ | Form error pattern detection — partial via aria-invalid presence |
| 3.3.2 | A | Labels or Instructions | ◐ | axe `label` (syntactic); **Phase-9 (planned)** LLM checks clarity |
| 3.3.3 | AA | Error Suggestion | ◯ | Quality of error message — manual |
| 3.3.4 | AA | Error Prevention (Legal, Financial, Data) | ◯ | Behavioral — manual |
| 3.3.7 | A | Redundant Entry | ◯ | Behavioral — manual |
| 3.3.8 | AA | Accessible Authentication (Minimum) | ◯ | Auth UX — manual |
| 4.1.2 | A | Name, Role, Value | ◐ | axe (syntactic); **Phase-9 (planned)** LLM for ARIA coherence |

**Summary**:

| Status | Today (Phase 8 + 9.1) | After Phase 9.2 (Wave 1 done) | After Phase 9.4 (calibrated) |
|---|---:|---:|---:|
| ✓ Full | 7 | 7 | 7 |
| ◐ Partial (auto + human review) | 11 | 19 | up to 25 |
| ◯ Manual only | 32 | 24 | up to 18 |
| **Total of 50 testable A + AA SCs** | | | |

In other words: **the tool helps with up to 64 % of WCAG 2.2 A + AA SCs
after the full Phase-9 roadmap ships, and the remaining 36 % (≥18 SCs)
genuinely require human testing.** This number aligns with the
GenA11y paper (FSE 2025), which sets the same ceiling at ~60–70 %.

---

## 7. The gap to 100 % — what manual testing must add

> Reality check: there is no path to 100 % via static analysis. The
> WCAG Working Group explicitly states some criteria (e.g. SC 3.1.5
> Reading Level) cannot be reliably auto-tested. Treat the 36 %
> manual surface as a permanent feature of accessibility work, not a
> tooling bug to fix.

The criteria that genuinely require humans break into seven families.
Each family is named here with what to test, how to test it, and
which assistive technology is needed.

### 7.1 Keyboard-only operation (SC 2.1.1, 2.1.2, 2.4.3 deep)

**What automation can't tell you**: whether every interactive control
is reachable via Tab, whether focus can ever get trapped in a custom
widget (modal, autocomplete, carousel), whether the focus order
matches the visual reading order, whether arrow-key navigation works
inside grids / tabs / menus per ARIA APG.

**Manual test**: unplug the mouse. Tab through every page from top
to bottom. Confirm:
- Every control receives focus.
- Focus is always visible.
- The order is sensible.
- Pressing Esc / Tab exits every modal and popover.
- Custom widgets (date pickers, autocompletes, carousels) follow the
  ARIA Authoring Practices keyboard pattern for their role.

**Time budget**: 30–60 min per page template.

### 7.2 Screen-reader experience (SC 1.3.1 deep, 1.3.2, 2.4.6 deep, 4.1.2 deep)

**What automation can't tell you**: whether the document outline
reads as a coherent page (not just "valid"), whether announcement
order matches reading order, whether ARIA roles convey the actual
semantic, whether the page's *meaning* is intact via the API tree.

**Manual test**: with a real screen reader.
- **macOS**: VoiceOver (Cmd+F5). Use `VO+A` to read all, `VO+U` for
  the rotor (Landmarks / Headings / Links / Form controls).
- **Windows**: NVDA (free, donate). Read with Down arrow,
  `Insert+F7` for the elements list.

What to confirm:
- The page makes sense if you only hear it.
- Headings outline matches the visual structure.
- Form fields are announced with their purpose.
- Status changes (live regions) are announced.
- Dynamic content (modals, toasts) is reached at the right time.

**Time budget**: 60–120 min per page template, plus practice.

### 7.3 Vision-impairment simulations (SC 1.4.4, 1.4.10, 1.4.11 edges)

**What automation can't tell you**: whether 200 % zoom causes content
loss, whether reflow to 320 px works without two-axis scroll, whether
custom focus rings have enough non-color contrast in odd surface
combinations.

**Manual test**:
- Set browser zoom to 200 %. Read the page. Look for clipped text,
  overlapping elements, lost interactivity.
- Resize the viewport to 320 px wide. Confirm no horizontal scroll
  (except where content has its own scroll context, like a code
  block or a wide table).
- Use OS-level Color Filters: macOS *Settings → Accessibility →
  Display → Color Filters → Grayscale*. Confirm interactive
  elements are still identifiable without color.

**Time budget**: 15–30 min per page template.

### 7.4 Cognitive / readability load (SC 3.1.3, 3.1.4, 3.2.3, 3.2.4)

**What automation can't tell you**: whether the language level matches
the audience, whether unusual words have definitions, whether
abbreviations are expanded, whether the same affordance is named
consistently across pages.

**Manual test**: read the page out loud. Check:
- Reading age (Flesch-Kincaid or the Hemingway editor target of
  grade 9 / below).
- Every abbreviation has an `<abbr title="...">` or in-text
  expansion on first use.
- "Submit", "Send", and "Confirm" aren't used interchangeably for
  the same action across pages.

**Time budget**: 30 min per content type.

### 7.5 Time-based + motion (SC 1.4.2, 2.2.x, 2.3.x, 2.5.x)

**What automation can't tell you**: whether auto-playing media has a
pause control reachable by all input modes, whether timeouts can be
extended, whether flashing content stays under three flashes per
second, whether motion-based interactions have a non-motion
alternative.

**Manual test**:
- Open every page with `prefers-reduced-motion` on. Confirm
  animations are subdued / disabled.
- Test every video / audio control for play / pause / volume via
  keyboard.
- For timeouts (session, form), confirm the user is warned and can
  extend.

**Time budget**: 10–20 min per page that has media or timeouts.

### 7.6 Forms + error messages (SC 3.3.1, 3.3.3, 3.3.4, 3.3.7)

**What automation can't tell you**: whether the error message
explains *what* went wrong and *what to do*, whether destructive /
financial submissions have confirmation steps, whether prior-entered
data isn't lost on validation failure.

**Manual test**: deliberately fail every form. For each error:
- Is the message specific (not just "invalid input")?
- Is the offending field programmatically associated with the
  error (`aria-describedby`)?
- Does the page focus / scroll to the first error?
- For commerce / financial: is there a "review" step before
  irreversible submission?

**Time budget**: 30 min per form.

### 7.7 Captions + audio descriptions (SC 1.2.x)

**What automation can't tell you**: whether captions are accurate,
synchronized, identify speakers, and convey relevant non-speech
audio. Whether audio descriptions cover what's visually important.

**Manual test**: watch every prerecorded video with captions on and
audio off. Watch with audio descriptions and visuals off. Confirm
information parity.

**Time budget**: 1.5 × video runtime per asset.

---

## 8. Recommended manual test plan

Use this as the operator's checklist alongside the tool's automated
output. The total time budget for a single page template, every
family, is roughly **3–5 hours** of focused manual testing.

```
┌───────────────────────────────────────────────────────────────────────┐
│  MANUAL TEST PLAN — per page template                                 │
│                                                                       │
│  1. Run the automated audit                                           │
│     $ audit crawl <url> --max-pages 1 --use-js                        │
│     • Address every "Critical" + "Serious" finding before manual.     │
│                                                                       │
│  2. Keyboard-only pass               (~45 min)         → §7.1         │
│     ☐ Tab through. Every control reaches focus.                       │
│     ☐ Focus indicator visible on every focused element.               │
│     ☐ No keyboard traps in modals, popovers, autocomplete.            │
│     ☐ Esc dismisses every overlay.                                    │
│     ☐ Custom widgets follow ARIA APG keyboard patterns.               │
│                                                                       │
│  3. Screen-reader pass               (~90 min)         → §7.2         │
│     ☐ VoiceOver (macOS) OR NVDA (Windows).                            │
│     ☐ Read-all (VO+A) end to end. Page makes sense.                   │
│     ☐ Rotor (VO+U) — Landmarks, Headings, Links lists are coherent.   │
│     ☐ Form fields announce their purpose + state.                     │
│     ☐ Live regions announce updates.                                  │
│                                                                       │
│  4. Visual + reflow pass             (~20 min)         → §7.3         │
│     ☐ Browser zoom 200 %. No clipping, no lost controls.              │
│     ☐ Viewport 320 px wide. No 2-axis scroll.                         │
│     ☐ Grayscale color filter. Interactive elements still identifiable.│
│     ☐ Apply WCAG 1.4.12 text-spacing CSS overrides. No clipping.      │
│                                                                       │
│  5. Cognitive + content pass         (~30 min)         → §7.4         │
│     ☐ Reading level grade ≤ 9 (Hemingway editor or similar).          │
│     ☐ Abbreviations expanded on first use.                            │
│     ☐ Action names consistent across pages.                           │
│     ☐ No instructions that depend on color / shape / position alone.  │
│                                                                       │
│  6. Forms + errors pass              (~30 min/form)    → §7.6         │
│     ☐ Each error message: what went wrong + what to do.               │
│     ☐ aria-describedby links the error to its field.                  │
│     ☐ Focus moves to first error on submit.                           │
│     ☐ Destructive actions have a confirmation step.                   │
│                                                                       │
│  7. Time + motion pass               (~15 min)         → §7.5         │
│     ☐ prefers-reduced-motion respected.                               │
│     ☐ Auto-playing media has a keyboard-reachable pause.              │
│     ☐ Session / form timeouts warn + offer extension.                 │
│                                                                       │
│  8. Media review                     (~1.5× runtime)   → §7.7         │
│     ☐ Captions accurate + synchronized + identify speakers.           │
│     ☐ Audio descriptions cover essential visuals.                     │
│     ☐ Transcripts available for audio-only.                           │
│                                                                       │
│  9. Record decisions                                                  │
│     ☐ Mark each automated finding remediated / accepted_risk /        │
│       false_positive in the tool's Issues view.                       │
│     ☐ For manual-only findings, file in Jira manually with the        │
│       SC code and your test notes (the tool's Jira export covers      │
│       automated rows only).                                           │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 9. References

**Internal**

- `docs/accessibility.md` — the tool's *own* UI conformance contract
  (WCAG 2.2 AAA across both Jinja + SPA)
- `docs/architecture.md` — original Phase-0 architecture decisions
- `docs/personas.md` — primary user (Sam, accessibility lead) +
  secondary / non-personas
- `docs/design-principles.md` — Universal Design × Nielsen mapped on
  the actual code
- `PLAN.md` (root) — current phase plan including Phase 9 semantic
  pipeline build-out
- `src/audit/rules/audit_report.yaml` — per-rule editorial copy
  (what / why / how)
- `src/audit/rules/analyzer_models.yaml` — per-criterion local-model
  picks

**External**

- W3C, *Web Content Accessibility Guidelines (WCAG) 2.2*, Recommendation
  October 2023 — <https://www.w3.org/TR/WCAG22/>
- He, Z., Huq, S. F., Malek, S., *Enhancing Web Accessibility:
  Automated Detection of Issues with Generative AI*, FSE 2025 — the
  paper this tool's Phase-9 semantic pipeline is modeled on
- WebAIM, *The WebAIM Million* (annual report) — baseline data on
  accessibility-defect prevalence in the top 1M sites
- Deque, *axe-core rule documentation* —
  <https://dequeuniversity.com/rules/axe/>
- W3C, *ARIA Authoring Practices Guide* — keyboard patterns for
  every common widget — <https://www.w3.org/WAI/ARIA/apg/>

---

> **One-line takeaway**: this tool covers up to ~64 % of WCAG 2.2 A + AA
> success criteria automatically after the in-progress Phase 9
> finishes; the remaining ~36 % require a 3–5 hour manual pass per
> page template, following the checklist in §8. A green audit is
> evidence of automated coverage — not of conformance.
