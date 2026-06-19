# Phase 1 — Discovery audit

**Scope.** Inventory the current UI, baseline its accessibility, and map the
gap to the goal: every screen WCAG 2.2 **AAA** clean, designed against the
seven Universal Design principles and Nielsen's ten usability heuristics.

**Status.** Discovery only. Per the transformation brief, **no code is being
changed in this phase**. Phase 2 (Foundations) starts after sign-off.

**Date.** 2026-04-27.
**Raw scan output.** [`audits/baseline/20260427-135203/`](baseline/20260427-135203/) — `violations.json`, `summary.md`, and the runner.

---

## TL;DR for the scroll-averse

1. **Two parallel UIs ship today.** A React SPA at `/app/*` (the new build)
   and a server-rendered Jinja UI at `/scans/*` etc. (the original). Both
   are reachable from the same FastAPI app. The SPA is the primary surface
   going forward, but neither has been retired. _This is itself a finding:_
   maintaining two implementations doubles the AAA-cleanup surface area
   and creates two divergent mental models for the user. Recommendation in
   §11.

2. **Baseline a11y scan, all routes, axe-core with the AAA rule-pack
   enabled** (the in-tree test runs AA only — a real gap).

   | Severity | Rule | Failing nodes | Notes |
   |---|---|---:|---|
   | serious | `color-contrast-enhanced` (WCAG 2.2 SC 1.4.6, AAA, 7:1) | **60** | Six distinct color pairs fail; full breakdown in §6. |
   | serious | `color-contrast` (WCAG 2.2 SC 1.4.3, AA, 4.5:1) | **13** | `fg-subtle` on `surface-muted` is **4.39:1** — fails the floor we already claim to meet. |
   | serious | `target-size` (WCAG 2.2 SC 2.5.8, AA, 24×24) | **5** | Native checkboxes in the New-Scan form are 13×13. AAA bumps the bar to 44×44 (SC 2.5.5). |

   No `keyboard`, `aria-*`, `landmark`, `label`, `link-name`, or `region`
   violations. The structural ARIA work in both UIs is already in good
   shape — the AAA gap is overwhelmingly **color and target sizing**.

3. **`README.md` claim "Zero axe-core WCAG 2.1 AA violations on every Jinja
   view; SPA views inherit"** is, with the AA-only ruleset, correct on the
   Jinja side but **wrong on the SPA side**: 2 of the 13 AA violations come
   from `/app/scans` and `/app/scans/1/findings`. Discovery surfaces this
   gap; Phase 2 will close it.

4. **Universal Design + Nielsen review** turns up sharper issues that axe
   can't see: no in-app help for the "ignore robots.txt" decision (UD #5
   Tolerance for Error; Nielsen #5 Error prevention), no user-reversible
   action for delete (UD #5; Nielsen #3 User control), no visible system
   status for export downloads, etc. Full table in §8.

5. **Documentation gaps.** No `accessibility.md`, no design-principles
   doc, no documented persona, no journey maps. The product roadmap implies
   the user but never names them. Phase-2 deliverables should include these
   as living docs.

---

## 1. UI inventory

### 1.1 React SPA (`/app/*`) — primary surface

Vite-built, mounted under `/app/` by FastAPI; React Router with
`basename="/app"` handles client-side routing.

| Route | Component | Purpose |
|---|---|---|
| `/app/` | `Dashboard` | 4 stat cards + recent-scans list + "About" panel. |
| `/app/scans` | `Scans` | Sortable list with per-row Findings + Delete actions. |
| `/app/scans/new` | `NewScan` | Form to start a crawl; `aria-live` scope preview. |
| `/app/scans/:id` | `ScanDetail` | Live progress (running) or summary + exports + Delete. |
| `/app/scans/:id/findings` | `Findings` | Virtualized table (TanStack Virtual); j/k keyboard nav. |
| `/app/scans/:id/diff` | `Diff` | New / Resolved / Status-changed / Still-open across two scans. |
| `/app/findings/:id` | `FindingDetail` | OCR vs Alt vs VLM verdict grid; 0–5 status shortcuts. |
| `*` | `NotFound` | EmptyState only. |

Shell: `AppShell` provides a left sidebar (UMich Blue, hidden on `<md`),
a `TopBar`, a skip link to `#main`, and a footer claiming
"Local · offline · WCAG 1.4.5 review."

UI primitives live in `src/components/ui.tsx`: `Card`, `Button`,
`LinkButton`, `PageHeader`, `StatCard`, `EmptyState`, `Severity`/`Scan`
badges, `relativeTime` helper. Every primitive uses the Tailwind tokens
defined in `tailwind.config.ts`.

### 1.2 Jinja UI (`/scans/*` etc.) — legacy / parallel

Server-rendered with HTMX for live updates. Same FastAPI app, same DB.

| Route | Template | Purpose |
|---|---|---|
| `/scans` | `scans.html` | Table of all scans; inline styles. |
| `/scans/new` | `new_scan.html` | Same crawl-start form as SPA. |
| `/scans/{id}` | `scan_detail.html` | HTMX-polled progress block; severity counts. |
| `/scans/{id}/findings` | `findings.html` + `partials/findings_table.html` | Filter form, paginated table. |
| `/findings/{id}` | `finding_detail.html` | Hero image + verdict grid + status form. |
| `/scans/{id}/diff?compare_to=…` | `diff.html` | Same diff buckets as SPA. |
| `/pages/{id}` | `page_detail.html` | Per-page image table. |

`base.html` provides skip-link, primary nav (`aria-current="page"`), and a
floating `?` keyboard-help dialog. `static/styles.css` (518 lines) is the
sole stylesheet — hand-rolled, with `:focus-visible` + `prefers-reduced-motion`
+ `prefers-color-scheme: dark` already wired in.

### 1.3 Two-UI footprint — finding

Both UIs duplicate every screen except Dashboard and FindingDetail's
keyboard-shortcut block. Maintaining both means:

* Every contrast / spacing / aria fix has to be made twice.
* Two divergent component vocabularies: SPA has `Card`/`StatCard`/`Severity`;
  Jinja has `.card`-less inline styles and `.sev-{level}` badges.
* The user can land on either UI depending on which link they followed
  (e.g. an export download link from a finding email lands on Jinja).

**Recommendation (for Phase 2 sign-off):** decide whether to (a) retire
the Jinja UI and redirect its routes into the SPA, or (b) freeze the
Jinja UI on a maintenance branch and only AAA-clean the SPA. Doing both
to AAA effectively doubles the work in Phases 3–4. **My recommendation is
(a)** — the SPA is more componentized and a single surface is easier to
keep clean. But this is a real trade-off and needs explicit go/no-go.

---

## 2. Stack notes

* **Backend:** FastAPI + uvicorn. Single app, two route groups (JSON `/api/*`
  + Jinja `/scans/*` etc.) and the SPA bundle mounted at `/app/`.
* **DB:** SQLite WAL, foreign keys on, jobs queue with lease semantics.
* **Frontend:** React 18, TypeScript strict, TanStack Query + Virtual,
  React Router 6, Tailwind 3 with U-M brand tokens, lucide-react icons.
* **Styling, Jinja:** hand-written `static/styles.css`. Custom-properties
  driven; dark mode via `prefers-color-scheme`.
* **Testing already present:**
  * `tests/ui/test_accessibility_axe.py` — Playwright + axe-core, **but
    `runOnly: { type: 'tag', values: ['wcag2a','wcag2aa'] }`.** AAA rules
    are not in the gate.
  * `tests/ui/test_routes.py` — 12 server-route tests (incl. delete-cascade).
  * Total suite: 302 tests last run, all passing.
* **Tooling not yet present** (called out in the brief):
  * Lighthouse CI (a11y floor 100)
  * Pa11y with AAA ruleset
  * `jest-axe` for component-level axe
  * `eslint-plugin-jsx-a11y` (verified absent in `package.json`)
* **Docs:** `docs/` has architecture, developer-guide, troubleshooting,
  user-guide, and a doc README. **No** `accessibility.md`,
  `design-principles.md`, `personas.md`, or journey maps.

---

## 3. Assumed-user model — flagged as assumption

There is **no** `personas.md`, no analytics, no documented user research
in the repo. The transformation brief tells us to "include people with
disabilities as primary users, not edge cases" but does not name a
specific persona. Per the brief's working-style rule "When in doubt,
write the choice down and ask," I am writing down what I am assuming
and asking for confirmation:

**Primary persona (assumed): Sam — Accessibility Lead, U-M LSA.**

* **Job to be done.** Find every WCAG 1.4.5 (Images of Text) violation
  across one of LSA's marketing or program sites before the next
  Siteimprove report cycle, hand a prioritized list to a content editor,
  and verify it on rescan.
* **Context.** Internal tool, runs on Sam's laptop. Sam may be triaging
  100–2000 findings in a single sitting. Often goes back and forth
  between a finding and the source page in a separate browser tab.
* **Disabilities Sam might bring to the tool.** Color-vision deficiency
  is the most likely (∼8% of men of European descent); low vision and
  RSI / keyboard-preferred users are realistic; full screen-reader
  primary use is possible (Sam is an a11y professional). Cognitive load
  is high — Sam is reading a lot of small text + small images all day.
* **Constraints.** Often offline (the whole tool is offline-first).
  Likely uses both keyboard and pointer fluidly. May share screen with
  an editor who has not used the tool before — so the UI should explain
  its own decisions (priority score, severity) without external docs.

**Secondary persona (assumed): Editor receiving exported findings.**
Encounters the tool only via the Jira CSV / Markdown export → never
opens the UI. Their UX surface is the export schema and column names.
Out of scope for the visual-UI audit but worth noting for export-doc
clarity (Phase 5).

**Asks for sign-off:** confirm or correct the persona, especially the
primary user's assistive-tech baseline. If Sam is a screen-reader
primary user, that bumps AAA SCs 1.3.5 (Identify Input Purpose, AA),
1.4.8 (Visual Presentation, AAA), and 2.4.10 (Section Headings, AAA)
much higher in priority than they would be otherwise.

---

## 4. Critical user journeys

Five journeys, ordered by frequency-during-typical-use. Each is the
primary unit Phase 4 will optimize against.

### J1 — Start a scan (low frequency, high stakes)

`Dashboard` → `New scan` button → `NewScan` form → submit → redirect to
`ScanDetail` (status=running).

**Friction observed in the audit:**

* The "Ignore robots.txt" checkbox is presented identically to "Skip
  OCR" — but one has a legal/ethical implication and the other is a
  perf optimization. UD #5 (Tolerance for Error) and Nielsen #5 (Error
  prevention) both apply: this needs a confirmation step or at minimum
  a per-option explanation.
* The "Use real browser (Playwright) for every page" checkbox costs
  ~10× the time at scale; no time estimate is shown.
* Native `<input type="checkbox">` is 13×13 px — fails 24×24 (AA) and
  44×44 (AAA SC 2.5.5).
* No way to save / re-use a scan config. Sam will run the same site many
  times; defaults reset every visit. Nielsen #7 (Flexibility & efficiency).

### J2 — Watch a crawl progress (medium-frequency, low-effort)

`ScanDetail` (running) → 2-second poll → in-flight URL list updates.

**Friction:**

* The pulsing "Crawl in progress" dot is the only visible system status.
  The *exact* same indicator appears for completed scans tinted blue —
  ambiguous at a glance.
* "refreshing every 2s" is shown as caption text — but the ARIA live
  region is on the Stop-crawl button only. Screen-reader users get no
  announcement when new pages arrive (UD #4 Perceptible Information).
* Stop-crawl is a 1-click action with a `confirm()` — fine for
  destructive intent but doesn't explain what "drop pending pages"
  means to someone unfamiliar with the queue model.

### J3 — Triage findings (high frequency, dominates time-on-tool)

`Findings` (filtered) → row click → `FindingDetail` → set status (0–5
keys or dropdown) → back to `Findings`.

**Friction:**

* Findings table is virtualized (TanStack Virtual) — works great for
  pointer users but the existing j/k keyboard nav was written for the
  Jinja UI (server-rendered DOM). Need to verify j/k still works on the
  virtualized list (deferred to Phase 4 instrumentation).
* Severity badge is a colored chip with a text label — color is *not*
  the only signal (good), but the sev color (`#B15A00` major on
  `#FEF3C7`) is below 4.5:1 contrast on its own background. See §6.
* No bulk-status action. If 50 findings are clearly false-positives
  (e.g. an icon-font sprite present site-wide), Sam triages them one at
  a time. Nielsen #7 (Flexibility) miss.
* No explanation of the priority score in-product. The number appears
  to 2 decimals next to the severity but the formula lives in
  `synthesizer/priority.py`. UD #4 (Perceptible Information) +
  Nielsen #2 (Match between system and real world).

### J4 — Status-update + export (low-frequency, hand-off moment)

`Findings` → bulk-mark or per-row → `ScanDetail` → CSV / JSON / Jira / Markdown.

**Friction:**

* Export buttons are styled like body links but trigger a download.
  No "Preparing report…" status, no row-count preview, no "0 findings
  matched current filter — export will be empty" warning. Nielsen #1
  (Visibility of system status).
* The Jira CSV is fixed-template; no preview before export. Sam can
  ship the wrong template and only find out when import fails. UD #5
  (Tolerance for Error).

### J5 — Diff vs prior scan (low-frequency, high-value)

`ScanDetail` → "Diff vs #N" link → `Diff` → click into a delta finding.

**Friction:**

* Diff shows counts but no overall verdict ("9 new, 12 resolved → net
  improvement"). Sam has to do the arithmetic.
* "Status changed" rows show `previous → current` but don't link to
  who/when (the `finding_history` rows are recorded but not displayed).
  That's a Phase-5 enhancement, not a blocker.

---

## 5. Baseline a11y scan — methodology

* **Runner:** [`audits/baseline/20260427-135203/run_baseline.py`](baseline/20260427-135203/run_baseline.py).
  Spins up a tmp-DB FastAPI app, walks 10 routes (5 SPA + 5 Jinja),
  runs vendored axe-core 4.10 against each.
* **Tag set:** `wcag2a, wcag2aa, wcag2aaa, wcag21a, wcag21aa, wcag22aa, best-practice`.
  This is broader than the in-tree `tests/ui/test_accessibility_axe.py`,
  which runs `wcag2a + wcag2aa` only.
* **Seed data:** one completed scan with two findings — a missing-alt
  banner image (essential / critical) and a logo with adequate alt
  (logo / info). Same seed `tests/ui/conftest.py` uses for the in-tree
  Playwright tests.
* **Caveats.** Scope is the rendered DOM at page-ready. Not exercised:
  hover states, focus rings under animation, modal/`confirm()` dialogs
  (they're native, not in-DOM until invoked), the `ScanDetail` running
  state (the seeded scan is `completed`).

### 5.1 Per-route violation counts

| UI | Route | Violations |
|---|---|---:|
| spa | `/app/` | 1 |
| spa | `/app/scans` | 2 |
| spa | `/app/scans/new` | 1 |
| spa | `/app/scans/1` | 1 |
| spa | `/app/scans/1/findings` | 2 |
| jinja | `/scans` | 1 |
| jinja | `/scans/new` | 2 |
| jinja | `/scans/1` | 1 |
| jinja | `/scans/1/findings` | 1 |
| jinja | `/pages/1` | 1 |
| **total** | | **13** (AAA enabled adds 60 more nodes for `color-contrast-enhanced`) |

### 5.2 Rules failed (deduped across all routes)

| Rule | Impact | Failing nodes | WCAG |
|---|---|---:|---|
| `color-contrast-enhanced` | serious | 60 | 1.4.6 (AAA, 7:1) |
| `color-contrast` | serious | 13 | 1.4.3 (AA, 4.5:1) |
| `target-size` | serious | 5 | 2.5.8 (AA, 24×24) |

No keyboard, ARIA, landmark, label, link-name, region, or
heading-order failures across any route. The structural-semantic work
in both UIs is already AA clean.

---

## 6. Color-token contrast audit (manual + axe)

Failing foreground/background pairs from the baseline scan, tallied by
unique pair (the duplicates in `summary.md` are axe sub-pixel
re-checks of the same color combo on different elements):

| FG | BG | Contrast | Need (AAA) | Where used |
|---|---|---:|---:|---|
| `#6B7280` (Tailwind `fg-subtle`) | `#FFFFFF` (`surface`) | **4.83** | 7.0 | StatCard captions, secondary text everywhere |
| `#6B7280` `fg-subtle` | `#F3F4F6` (`surface-muted`) | **4.39** | 4.5 (AA) | StatCard tinted, footer, table-row meta — **fails the AA floor we already claim to meet** |
| `#4B5563` `fg-muted` | `#F3F4F6` `surface-muted` | **6.86** | 7.0 | Card body text on tinted cards |
| `#0059A8` (legacy `--accent`) | `#FAFAFA` (legacy `--bg`) | **6.71** | 7.0 | Every link in the Jinja UI |
| `#555555` (legacy `--fg-muted`) | `#D8D8D8` (legacy table-header tint) | **5.23** | 7.0 | Jinja table headers |
| `#99A9B7` (sidebar caption gray) | `#00274C` (UMich Blue) | **6.24** | 7.0 | SPA sidebar legend / footer |

Plus three pairs that **pass** today and we want to keep that way:

| FG | BG | Contrast | Notes |
|---|---|---:|---|
| `#FFCB05` (Maize) | `#00274C` (Blue) | ~9.85 | Pinned brand pair — fine |
| `#00274C` (Blue) | `#FFFFFF` | ~16.0 | Primary on white — fine |
| `#FFCB05` Maize | `#FFFFFF` | ~1.7 | **Reserved for non-text accents** — using Maize on white for *text* would fail even AA; this is documented in the Tailwind config and we should keep enforcing it. |

**Focus indicator (separate concern, WCAG 1.4.11 Non-text Contrast 3:1).**
`tailwind.config.ts` defines `boxShadow.focus: 0 0 0 3px rgba(255, 203, 5, 0.55)`
— a 55% Maize ring. Against white this is ~1.7:1 effective contrast,
which **fails** SC 1.4.11. Against the dark blue sidebar it's fine.
Phase-2 token work will need a focus ring that is the same UMich Blue
or a darker Maize, with proper contrast on every surface.

**Severity badges (already partly broken).**
* `sev.major` `#B15A00` on `sev.major-bg` `#FEF3C7` ≈ **4.04:1** — fails AA.
* `sev.minor` `#7A6700` on `sev.minor-bg` `#FEF9C3` ≈ **5.5:1**  — passes AA, fails AAA.
* `sev.critical` `#8B0000` on `sev.critical-bg` `#FEE2E2` ≈ **8.0:1** — passes AAA.
* `sev.info` `#1F2937` on `sev.info-bg` `#E5E7EB` ≈ **12:1** — passes AAA.

The major/minor badges are the primary visual cue for two-thirds of
findings and **the major badge fails AA**. This is the highest-impact
single fix in Phase 2.

---

## 7. Touch / click target audit

`target-size` (AA SC 2.5.8: 24×24; AAA SC 2.5.5: 44×44) failures from
the baseline scan:

| Element | Size today | AA need | AAA need | Where |
|---|---|---:|---:|---|
| `<input type="checkbox">` | 13 × 13 | 24 | 44 | New-scan form (5 checkboxes) |
| Pagination `<a>` chips | ~28 high | OK | 44 | Jinja `findings.html` pagination |
| Severity badge link in findings table | ~22 high | borderline | 44 | Jinja `findings_table.html` |
| Per-row Delete `<button>` | ~28 | OK | 44 | SPA scans list |
| Per-row Findings `<button>` | ~28 | OK | 44 | SPA scans list |

The native checkbox is the headline — Tailwind doesn't restyle
checkboxes by default. Phase-2 will need either CSS-rebuilt
checkboxes (with `appearance: none` + custom check) or an explicit
44×44 hit zone via `<label>` padding.

---

## 8. Universal Design + Nielsen heuristic gap analysis

Items axe cannot see. Cross-tabbed against UD's 7 principles and
Nielsen's 10 heuristics. Effort estimate is rough order-of-magnitude:
S = <½ day, M = ½–2 days, L = >2 days.

| # | Issue | Where | Principle violated | Proposed remediation | Effort |
|---|---|---|---|---|---|
| 1 | Major-severity badge fails AA contrast on its own background | Tailwind `sev.major*` tokens | UD #4; WCAG 1.4.3 | Re-pick `sev.major` to `#7C3500` or shift bg to `#FFEBC2`; verify all four sev pairs ≥7:1 | S |
| 2 | `fg-subtle` on `surface-muted` fails AA (4.39:1) | Tailwind tokens | UD #4; WCAG 1.4.3 | Darken `fg-subtle` from `#6B7280` to `#525864` (≥7:1 on both white and muted) | S |
| 3 | Focus ring (semi-transparent Maize) fails 1.4.11 on white | Tailwind `boxShadow.focus` | UD #4; WCAG 1.4.11 | Use UMich Blue or solid darker Maize with adjacent-contrast ≥3:1 | S |
| 4 | Native checkboxes 13×13 in New-Scan form | `NewScan.tsx`, `new_scan.html` | UD #1, #2; WCAG 2.5.5/2.5.8 | Custom `Checkbox` component with 44×44 hit area | M |
| 5 | "Ignore robots.txt" presented identically to perf options | Both New-Scan UIs | UD #5; Nielsen #5 | Promote to confirm-modal step, with explanation; default off | S |
| 6 | No bulk-status action for findings | SPA Findings, Jinja Findings | Nielsen #7 | Multi-select column + bulk-status toolbar | L |
| 7 | Priority-score formula not explained in-product | FindingDetail, both UIs | UD #4; Nielsen #2 | Tooltip / popover on the score, listing weights | S |
| 8 | Delete is irreversible (no undo / trash) | Scans list, ScanDetail | UD #5; Nielsen #3 | Soft-delete + 30-day undo, OR a clearer multi-step confirm with the scan stats included | M |
| 9 | Export download has no system-status feedback | ScanDetail | Nielsen #1 | Inline "Preparing CSV (N rows)…" and a "0 findings matched" warning | S |
| 10 | Two parallel UIs (SPA + Jinja) drift independently | App-wide | UD #3 (Simple & Intuitive); Nielsen #4 (Consistency) | Either retire Jinja (recommended) or freeze it for read-only | L |
| 11 | No in-product help / glossary for "essential vs informational vs decorative vs logo" | FindingDetail, Findings filter | UD #4; Nielsen #2, #10 | Inline definitions on hover + a `/help/glossary` route | M |
| 12 | Sidebar collapses below `md` with no replacement nav | `AppShell.tsx` | UD #2 (Flexibility in Use) | Add hamburger-toggled mobile drawer or top-nav fallback | M |
| 13 | "About" panel on Dashboard claims "WCAG 2.1 AA" — out of date once Phase 2 lands | `Dashboard.tsx` | Nielsen #2 (Match with reality) | Update copy + tie to `package.json` version | S |
| 14 | Live regions (`role="status"` etc.) are present but inconsistent — `ScanDetail` running state has no `aria-live` for new pages arriving | `ScanDetail.tsx` | UD #4; WCAG 4.1.3 | Wrap progress block in `aria-live="polite"` summary line | S |
| 15 | No documented persona, journey map, or design-principles file | `docs/` | All UD; Nielsen #10 (Help & docs) | Phase-5 deliverable: `docs/accessibility.md`, `docs/personas.md`, `docs/design-principles.md` | M |
| 16 | Existing axe gate is AA-only; AAA regressions land silently | `tests/ui/test_accessibility_axe.py` | (process) | Add AAA tag to `runOnly`, fail on regression; add Lighthouse CI + Pa11y AAA + jest-axe + jsx-a11y per brief | M |
| 17 | "Crawl in progress" dot pulses by `animate-pulse` — works in `prefers-reduced-motion` because Tailwind respects it, but the pulse is also the *only* moving thing on the page (no fallback static state needed); good. _No fix._ | — | — | — | — |
| 18 | Keyboard help dialog is `tabindex="-1"` and `hidden` — opened by `?` shortcut but no on-screen affordance for non-keyboard users to discover it exists | `base.html`, SPA AppShell | UD #1, #2; Nielsen #6 (Recognition over recall) | Visible `?` icon-button in TopBar; opens same dialog | S |
| 19 | `confirm()` dialogs lose styling and don't match the rest of the UI; not a blocker but breaks visual consistency | Delete, Stop-crawl | Nielsen #4 | Replace with custom modal — but only if we can keep it ≥AAA (axe-tested); otherwise keep `confirm()` | M |
| 20 | Severity badge on `findings_table.html` (Jinja) is also the row's primary link — the click target is the colored chip, which conflates "show me this finding" with "filter by severity" mental models | `findings_table.html` | Nielsen #2; UD #3 | Click-target should be a discrete cell or row affordance; badge stays purely semantic | M |

---

## 9. WCAG 2.2 AAA criterion coverage map

What the brief calls out explicitly, where we stand today:

| SC | Title | Today | After Phase 2 (planned) |
|---|---|---|---|
| 1.4.6 | Contrast (Enhanced) — 7:1 | **fail** (60 nodes) | Pass — token recolor + sev re-pick |
| 1.4.8 | Visual Presentation | partial | Need: line-length cap, user-controlled spacing, 80-char limit on body text. Currently no max-width on prose. |
| 1.4.10 | Reflow | pass at 320px (SPA hides sidebar; Jinja is one column) | Re-verify after token changes |
| 1.4.11 | Non-text Contrast | **fail** (focus ring) | Pass — focus-token recolor |
| 1.4.12 | Text Spacing | likely pass (Tailwind defaults) | Add explicit test — apply user CSS overrides, verify no clipping |
| 2.1.3 | Keyboard (No Exception) | likely pass (j/k + 0–5 + ?) | Add an explicit "every interactive element reachable & operable by keyboard" test sweep |
| 2.4.10 | Section Headings | partial | Audit `<h2>`/`<h3>` ordering on every screen; some Jinja templates jump from `<h2>` to `<h3>` cleanly but FindingDetail's structure could be tighter |
| 2.4.13 | Focus Appearance (AAA) | unknown — depends on focus-ring fix | Define: minimum 2px solid, 4.5:1 against background, fully encloses element |
| 2.5.5 | Target Size (AAA) — 44×44 | **fail** (checkboxes + several link chips) | Pass — checkbox + chip fixes |
| 3.1.5 | Reading Level | unknown | Audit form help-text + remediation hints; rewrite anything over US grade-9 |
| 3.2.5 | Change on Request | pass (no auto-redirects, no auto-submit forms) | — |
| 3.3.5 | Help (AAA) | partial (only `aria-describedby` for URL field) | Add contextual help on every form field + finding glossary |
| 3.3.6 | Error Prevention (All) | partial — submit on `<form>` is not currently blocked from invalid input beyond browser HTML5 | Add reversal/confirmation for: start scan with `ignore_robots`, delete scan |
| 3.3.9 | Accessible Auth | N/A — no auth in product today | Track for if/when auth lands |

---

## 10. Universal Design 7-principle coverage map

| # | Principle | Today's strongest example | Today's weakest |
|---|---|---|---|
| 1 | Equitable Use | Skip-link, `aria-current`, axe-AA on Jinja, color is never the sole signal | Native checkboxes too small for low-dexterity / mobile users |
| 2 | Flexibility in Use | j/k + 0–5 + pointer all do the same things | No bulk-action affordance; mobile sidebar disappears with no replacement |
| 3 | Simple & Intuitive | Findings detail's verdict grid (OCR / Alt / VLM stacked side by side) | Two parallel UIs; priority score with no in-product explanation |
| 4 | Perceptible Information | Severity badge has both color and text | Live progress doesn't announce; sev.major fails contrast |
| 5 | Tolerance for Error | `confirm()` on destructive actions; cascading delete is documented | No undo; "Ignore robots.txt" presented as a normal toggle |
| 6 | Low Physical Effort | Keyboard shortcuts replace mouse for hot paths | Small targets force precise pointing for everyone |
| 7 | Size & Space for Approach | Reflow works at 320px | Sidebar hidden below `md` with no fallback |

---

## 11. Recommended Phase-2 sequence (proposal — needs sign-off)

The brief defines Phase 2 as "Foundations." Concretely I'd sequence:

1. **Decide UI strategy.** SPA-only (recommended) vs SPA + maintained
   Jinja vs SPA + frozen Jinja. Everything else depends on this.
2. **Recolor the design tokens** for AAA contrast.
   * Re-pick `sev.major` and `sev.minor` foregrounds.
   * Darken `fg-subtle` to ≥7:1 on `surface` *and* `surface-muted`.
   * Repaint focus ring to UMich Blue or a darker Maize, ≥3:1 on every
     surface; document with a `tokens.md` matrix.
3. **Build a universal `Checkbox` / `Radio` / `Switch` component** with
   44×44 hit zones and proper focus rings. Replace native inputs.
4. **Tighten the a11y test gate.**
   * Update `test_accessibility_axe.py` to include `wcag2aaa, wcag22aa,
     wcag22aaa` and re-run.
   * Add Lighthouse CI with a11y floor 100.
   * Add Pa11y with AAA ruleset.
   * Add `eslint-plugin-jsx-a11y` to the SPA build.
   * Add `jest-axe` for component-level snapshots.
5. **Write `docs/accessibility.md`, `docs/personas.md`,
   `docs/design-principles.md`** so the rules land *before* the
   component remediation work begins.
6. **Update the Dashboard "About" panel** to reflect the new target
   (AAA), and tie it to a single-source-of-truth (e.g. read from
   `package.json` or a constant).

That gets us to a clean baseline. Phases 3+ tackle the larger UX
pieces: bulk-status, in-product help, mobile nav, the diff verdict
roll-up, etc.

---

## 12. Open questions for sign-off

Per the brief's "When in doubt, write the choice down and ask," these
are the explicit decisions I'd like a yes/no on before Phase 2:

1. **Persona.** Is "Sam, U-M LSA Accessibility Lead" the right primary
   user? In particular — what is their assistive-tech baseline?
2. **UI strategy.** SPA-only (recommend) vs keep both?
3. **Brand-token flexibility.** UMich Blue and Maize are pinned. The
   neutral grays are not — am I free to re-pick `fg-subtle`,
   `surface-muted`, sev tokens to satisfy AAA, or do they need design
   review at U-M Marketing?
4. **Soft-delete vs reversible-confirm for scan deletion.** Soft-delete
   means a new column + a "Trash" route; reversible-confirm is just a
   bigger dialog. Which fits the user's mental model better?
5. **`confirm()` vs custom modals.** I lean toward keeping native
   `confirm()` for destructive actions (axe-clean by browser default,
   no styling to drift) — agree?
6. **Mobile target.** Phone-sized viewport (< 768px) — is this a real
   user surface, or laptop only? Affects whether the sidebar gets a
   mobile fallback (medium effort) or stays hidden (no effort).

---

## 13. Inputs for the next phase

* Raw axe data: `audits/baseline/20260427-135203/violations.json`
* Re-runnable scanner: `audits/baseline/20260427-135203/run_baseline.py`
* This document.
* All decisions from §12.

**End of Phase 1. Awaiting sign-off before any code changes.**
