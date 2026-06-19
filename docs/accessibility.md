# Accessibility — WCAG 2.2 AAA, in practice

This document is the single source of truth for what "accessible" means
in this codebase, why it means that, and how to keep it that way as the
product evolves. It is the doc to read before you change a color, add a
form control, write a new template, or land a new route.

It is **deliberately concrete.** It names tokens, files, axe rule IDs,
and the exact contrast ratios we hold ourselves to. Generic advice
("use semantic HTML") is not useful when you're staring at a failing
test at 5 PM; specific advice ("the focus ring is `boxShadow.focus` in
`tailwind.config.ts`, currently `#003f75` solid 3 px, ≥3:1 on every
surface in [`audits/contrast_helper.py`](../audits/contrast_helper.py)
matrix") is.

> **Status.** Adopted in Phase 2 of the UI Transformation. Phase 1
> baseline (78 axe violations across 10 routes) is documented in
> [`audits/discovery.md`](../audits/discovery.md). Phase 2 closes that
> gap; the green-baseline scan ships in `audits/baseline/<later-ts>/`.

---

## 1. The bar

**Every screen, both UIs, every state, WCAG 2.2 AAA clean** —
measured by axe-core 4.10 with the `wcag2a, wcag2aa, wcag2aaa, wcag21a,
wcag21aa, wcag22aa, best-practice` tag set, and verified by manual
review against the Universal Design seven principles and Nielsen's ten
heuristics (see [`design-principles.md`](design-principles.md)).

**Why AAA, not AA.** AAA is normally aspirational. We hold ourselves
to it because:

* The product's *only purpose* is detecting accessibility defects on
  other people's sites. Shipping accessibility defects in our own UI
  would be a credibility-destroying contradiction.
* The tool's primary user is an accessibility professional
  (see [`personas.md`](personas.md)). They will notice every gap.
* AAA is achievable for a tool of this scope — a tabular triage UI
  with no auth, no media, and one form. It's not achievable for, say,
  a video player. We're in the easy regime.

**What "AAA clean" excludes.** AAA criteria where the rule does not
apply (3.3.9 Accessible Authentication — we have no auth; 1.4.9 Images
of Text — N/A for our UI chrome; 1.2.* — we have no media). We don't
claim to satisfy criteria that aren't relevant; we *do* enumerate them
in §6 below so reviewers can see the work was done.

---

## 2. The tools that enforce it

Five gates, each catches something the others miss. **All five must
pass before a PR can land on `main`.**

| Gate | What it catches | Where it runs |
|---|---|---|
| `eslint-plugin-jsx-a11y` (flat config) | Compile-time JSX a11y mistakes — `alt`-less `<img>`, `role="button"` on a `<div>`, `onClick` without `onKeyDown`, mis-paired `<label>`s. | Editor + `npm --prefix src/audit/web/frontend run lint`. |
| `tsc --noEmit` strict | Type errors, any prop drift on the shared primitives (`Checkbox`, `Button`, `LinkButton`). | `npm --prefix src/audit/web/frontend run typecheck`. |
| In-tree axe-core test | Runtime DOM checks against rendered routes (Playwright + axe-core, AAA tag set). | `pytest tests/ui/test_accessibility_axe.py`. |
| Baseline a11y scan (broader runner) | All 10 routes, both UIs, both light & dark modes, with the same AAA tag set the Phase-1 discovery used. | `python audits/baseline/<latest>/run_baseline.py`. |
| Manual UD/Nielsen review | Things axe can't see — undo-ability, in-product help, system-status visibility, error prevention. | Per [`design-principles.md`](design-principles.md) §3 checklist. |

**On adding a sixth gate (Lighthouse CI, Pa11y, jest-axe).** The
discovery audit recommended these and they remain on the roadmap. The
ranked priority is: jest-axe first (component-level snapshots so
primitive-level regressions surface in unit tests), then Pa11y (catches
some rules axe doesn't), then Lighthouse (perf signal, plus a
redundant a11y check). They're *additive* to the five above, not
replacements.

---

## 3. Color tokens — the contrast contract

Every text/background pair in the product must clear one of these
thresholds against [`audits/contrast_helper.py`](../audits/contrast_helper.py):

| Use | Threshold | WCAG SC |
|---|---:|---|
| Body & UI text | **7.0:1** | 1.4.6 (AAA) |
| Large text (18pt+ / 14pt+ bold) | **4.5:1** | 1.4.6 (AAA, large-text exception) |
| Non-text UI elements (focus ring, control border, severity chip border) | **3.0:1** | 1.4.11 |

**Source of truth: [`tailwind.config.ts`](../src/audit/web/frontend/tailwind.config.ts)
and [`static/styles.css`](../src/audit/web/static/styles.css).** Every
named color in those two files has been verified in
`contrast_helper.py`'s `PAIRS` matrix. Adding a new color means adding
a new row; the helper exits non-zero if any cell falls below the
threshold for its category.

**The pinned brand pairs.**

| Pair | Ratio | Status |
|---|---:|---|
| UMich Blue `#00274C` on white | 16.0:1 | Primary on white — fine |
| Maize `#FFCB05` on UMich Blue | 9.85:1 | Pinned brand pair — fine |
| Maize `#FFCB05` on white | 1.7:1 | **Reserved for non-text accents only.** Maize-on-white text would fail even AA; the Tailwind config and the `Checkbox` primitive document this. |

**Run the helper before locking a token change:**

```bash
# Print the canonical matrix (every documented pair, AAA-graded):
python audits/contrast_helper.py

# Spot-check one pair:
python audits/contrast_helper.py "#475263" "#F3F4F6"
# → ratio=7.19, AAA-pass for body text, AAA-pass for large text.
```

If the helper rejects a candidate, **darken the foreground or lighten
the background — don't lower the threshold.** The threshold is the
contract.

---

## 4. Target sizing — the 44×44 contract

WCAG 2.2 SC 2.5.5 (AAA) requires interactive controls to have at least
a 44×44 CSS-pixel hit target. SC 2.5.8 (AA) requires 24×24. We hold to
44×44.

### The size system: `sm` / `md` / `lg`

`Button` and `LinkButton` in [`src/audit/web/frontend/src/components/ui.tsx`](../src/audit/web/frontend/src/components/ui.tsx)
take a `size` prop. The choice is rule-driven, not stylistic:

| Size | Min-height | When to use |
|---|---:|---|
| `sm` | (does **not** clear 44 — opt-in only) | Reserved for non-interactive presentation chips (`SeverityChip`, `StatusChip`). **Do not use on actual buttons.** |
| `md` *(default)* | 44 px | Every secondary action — Cancel, filter Apply, table-row Delete/Findings, pagination Prev/Next. |
| `lg` | 52 px | The page's *one* primary action — "Start crawl" on `/scans/new`, "Save" on the finding triage row, "Findings (N)" on a completed scan, the topbar "Start a new scan", "Stop crawl" while running. There should be at most one `lg` per route. |

The same rule applies to inputs and selects: every editable control
gets `min-h-target` plus `text-base` (16 px). The `text-base` is not
cosmetic — iOS Safari only suppresses focus-zoom at ≥16 px font size,
so a `text-sm` input is *less* accessible to a low-vision user than a
`text-base` one.

**Hero inputs.** The seed URL on `/scans/new` is the entire form's
reason for being; it gets the `field-hero` treatment — `text-base`,
`py-3`, `border-2` — to read as visibly more important than the
secondary numerics below it. Both UIs implement this:

* **SPA:** inline classes on the `<input>` in
  [`routes/NewScan.tsx`](../src/audit/web/frontend/src/routes/NewScan.tsx).
* **Jinja:** `.field-hero` / `.field-hero__label` rules in
  [`static/styles.css`](../src/audit/web/static/styles.css).

### Correction to a Phase-2 claim

An earlier draft of this doc claimed the per-row Delete/Findings buttons
were "already 44×44 via the shared `Button` primitive's padding (`py-1.5`
× line-height + border)." That was wrong. `py-1.5` (= 6 px each side) +
20 px line-height + 2 px border ≈ 34 px tall — a SC 2.5.5 fail in
disguise. The size system above is the actual fix; the `md` baseline
forces every Button to clear 44 px regardless of which row it sits in.

### Other 44×44 touchpoints

* **Native checkboxes are 13×13.** Two responses in this repo:
  * **SPA:** `Checkbox` keeps a 22×22 *visual* control (so it still
    reads as a checkbox) but wraps it in a `<label>` with `min-h-target`
    padding — click-the-label is native browser behavior, so
    screen-reader and keyboard users get the same affordance as pointer
    users.
  * **Jinja:** `.option`, `.option__body`, `.option__label`,
    `.option__hint` rules in `static/styles.css` achieve the same
    shape via the `--target-size` custom property.
* **Form labels generally** — the global `form label` rule in
  `static/styles.css` bumps every form label to the target size.
* **Sidebar nav links** — `min-h-target` on each link in `AppShell.tsx`
  and on `header.site nav a` in `static/styles.css`.
* **Pagination Prev/Next** in `Findings.tsx` use the shared `Button`
  primitive at default `md` so they inherit the 44 px floor.

### The token to use

**`min-h-target` (Tailwind) or `var(--target-size)` (CSS).** Never
hard-code `44px` in component CSS — the token is the contract and the
single place to revisit if guidance ever changes (or if we ever decide
to bump to 48 for finger-padding headroom).

---

## 4.5 Links must be visibly clickable — the 1.4.1 contract

WCAG 1.4.1 (Use of Color, Level A) forbids using color as the *only*
way to identify a link. Blue-tinted body text with no underline fails
this criterion. Reviewers running our own tool against our own UI
would (correctly) flag it.

**The rule:** every link gets a non-color affordance. In practice that
means an **always-visible underline** for content links. The few
exceptions — buttons that happen to be anchors, nav chips with a
background/padding, severity-chip-as-link — carry a clear non-color
shape (border, fill, padding) that makes their interactivity obvious,
and only those are permitted to opt out of the underline.

**Anti-pattern to forbid in PRs:** `text-{color} no-underline
hover:underline`. That's color-only signaling until the user hovers.
Reviewers should fail this pattern on sight.

**Source of truth.** In the SPA, content `<Link>` / `<a>` uses
`underline underline-offset-2`. In the Jinja UI, the base `a` rule in
`static/styles.css` sets `text-decoration: underline` with an
`underline-offset` of `0.15em`; hover/focus thickens the line as a
reinforcement, never as the primary signal. Both surfaces were swept
in Phase 2.1 to remove a pre-existing 20-instance pattern.

If a designer asks to drop the underline for a content link, the
answer is no — add a non-color affordance instead (button shape, icon,
border treatment) and document the exception in the component's
docblock.

---

## 5. Focus indicator — the 3:1 contract

WCAG 2.2 SC 1.4.11 (AA) and SC 2.4.13 (AAA Focus Appearance) both
apply. We satisfy both with one design:

* **Solid `#003f75`** (a UMich-Blue-shifted blue picked for ≥3:1 on
  every surface in the product) at 3 px, with a 1 px white halo so the
  ring stays visible against blue surfaces too. Defined as
  `boxShadow.focus` in `tailwind.config.ts` and `--focus` in `styles.css`.
* **For the dark blue sidebar / inverse surfaces:** `boxShadow.focus-inverse`
  uses Maize at full opacity — verified ≥3:1 against UMich Blue.

**Don't ship per-component focus rings.** The single shared ring is
what makes focus *consistent* across every interactive element —
buttons, links, checkboxes, table rows, the lot. If a component needs
a different ring, that's a sign the component isn't reusing the
shared `Button` / `LinkButton` / `Checkbox` primitive and the fix is
upstream.

---

## 6. WCAG 2.2 AAA criterion-by-criterion

What we satisfy, where, and what's N/A. Items in **bold** required
explicit work in Phase 2; items in italics are inherited from Phase 1.

| SC | Title | Status | How |
|---|---|---|---|
| 1.4.6 | Contrast (Enhanced, 7:1) | **Pass** | §3 contrast contract; every token verified. |
| 1.4.8 | Visual Presentation | Partial | Body text widths capped via Tailwind `prose`-style max-widths on long text (Card descriptions, finding rationale). User-controlled spacing inherited from native browser controls. |
| 1.4.9 | Images of Text (No Exception) | N/A | Tool ships no images-of-text in its UI chrome (the audited *content* is the whole point). |
| 1.4.10 | Reflow | *Pass* | SPA hides sidebar below `md`; Jinja UI is single-column from the start. Re-verified after the Phase-2 token recolor. |
| 1.4.11 | Non-text Contrast | **Pass** | §5 focus ring; severity chip borders ≥3:1 in the recolored token set. |
| 1.4.12 | Text Spacing | Pass | Tailwind defaults respect user CSS; explicit test in `tests/ui/test_accessibility_text_spacing.py` re-applies user-CSS overrides and verifies no clipping. |
| 1.4.13 | Content on Hover or Focus | Pass | Tooltips on disabled-export buttons (`title=` attr) are dismissible, hoverable, and persistent — native `title` semantics. |
| 2.1.3 | Keyboard (No Exception) | Pass | All interactive elements reachable via Tab; `j/k` (Findings nav), `0–5` (FindingDetail status), `?` (keyboard help). |
| 2.2.3 | No Timing | Pass | No session timeouts. Background scans poll, but the user is never timed out. |
| 2.2.4 | Interruptions | Pass | The only interruption is `aria-live` polite — never assertive. |
| 2.2.5 | Re-authenticating | N/A | No auth. |
| 2.2.6 | Timeouts | N/A | No timeouts. |
| 2.3.2 | Three Flashes | Pass | The pulsing scan-in-progress dot pulses once per ~1.5 s — well under three flashes/second. `prefers-reduced-motion` respected globally. |
| 2.3.3 | Animation from Interactions | Pass | `prefers-reduced-motion` respected globally; scan-progress pulse is the only animation. |
| 2.4.8 | Location | Pass | Breadcrumbs in `PageHeader` on every interior route; sidebar `aria-current="page"`. |
| 2.4.9 | Link Purpose (Link Only) | Pass | Body links are descriptive ("View progress →" not "click here"). Per-row links are wrapped in row anchors with the row content as accessible name. |
| 2.4.10 | Section Headings | Pass | Heading order linted via axe; `<h1>` is route-title, `<h2>` for sections inside a Card, `<h3>` for sub-sections. No skips. |
| 2.4.13 | Focus Appearance (AAA) | **Pass** | §5 focus ring meets the 2px-solid, 4.5:1, fully-enclosing test. |
| 2.5.5 | Target Size (AAA, 44×44) | **Pass** | §4 target-size contract. |
| 2.5.6 | Concurrent Input Mechanisms | Pass | Pointer + keyboard + touch all work concurrently; no input-mode-locked controls. |
| 3.1.5 | Reading Level | Pass | Form help-text and remediation hints rewritten to US grade-9 (Hemingway-app verified) in Phase 2. |
| 3.1.6 | Pronunciation | N/A | No words whose meaning depends on pronunciation. |
| 3.2.5 | Change on Request | Pass | No auto-redirects, no auto-submit forms, no auto-refreshing components except `aria-live` polite progress announcements. |
| 3.3.5 | Help (AAA) | Pass | Every form field has contextual help (`aria-describedby` on the URL field; `hint` slot on every Checkbox; tooltip on every disabled-state action). |
| 3.3.6 | Error Prevention (All) | Pass | "Ignore robots.txt" carries a warning treatment; delete is gated by a typed-confirm modal; submit is blocked on invalid input via HTML5 + JS revalidation. |
| 3.3.9 | Accessible Authentication | N/A | No auth in product today. |

---

## 7. Two UIs — parity, not divergence

The product currently ships two parallel UIs (React SPA at `/app/*`,
Jinja templates at `/scans/*`). The Phase-1 discovery flagged this as
a maintenance liability and recommended retiring the Jinja UI.

**Until that decision lands, both UIs must satisfy this document.**
That means:

* Every token change in `tailwind.config.ts` has a mirror in
  `static/styles.css` (CSS custom properties).
* Every primitive built in `components/ui.tsx` has a CSS equivalent in
  `static/styles.css` (e.g. `Checkbox` ↔ `.option` rules).
* Every axe gate runs against both UI surfaces.

The cost is real — that's what makes the discovery doc's "decide UI
strategy" recommendation a real recommendation. But until the strategy
lands, parity is the contract.

---

## 8. How to add a new screen / component without breaking AAA

A short checklist, in order:

1. **Sketch the affordance using existing primitives.** `Card`, `Button`,
   `LinkButton`, `Checkbox`, `PageHeader`, `EmptyState`, `StatCard`,
   `SeverityChip`, `StatusChip`, `AltTag`, `ScanStatusBadge` cover most
   needs. Reach for a new primitive only if none fits.
2. **If you do build a new primitive,** put it in `components/ui.tsx`
   with a docblock that lists the WCAG SCs it satisfies. Mirror it in
   `static/styles.css` if the Jinja UI will use it. Add a row to the
   contrast matrix in `audits/contrast_helper.py` for any new color
   pair.
3. **Run the five gates.** Lint, typecheck, axe, baseline scan, manual
   UD/Nielsen review per the [`design-principles.md`](design-principles.md)
   checklist.
4. **Read the docblock convention.** Every primitive in `ui.tsx` has a
   docblock that explains *why* it exists and what WCAG SCs it satisfies.
   Match that style — the docblock is read by the next maintainer when
   they're about to touch the file at 5 PM on a Friday.

If you find yourself wanting to write `style={{ color: "#999" }}` or
`<div onClick={…} />`, stop and re-read this doc. There is always a
named token or a primitive that does what you want.
