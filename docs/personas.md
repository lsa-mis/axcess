# Personas — who we're building this for

Personas are documented assumptions about the user. They're not
research findings, and this document says so. They exist because every
design decision is made against an implicit user model — writing the
model down lets us *argue with it* instead of carrying around a
private one each.

> **Status.** Working assumptions, adopted in Phase 2. The discovery
> audit ([`audits/discovery.md`](../audits/discovery.md) §3) flagged
> the absence of a persona doc and proposed Sam below as an explicit
> assumption-of-record. Until we run user interviews this stands as the
> design ground truth — and any decision that rests on it should cite
> the specific assumption it's relying on so we can revisit if the
> assumption was wrong.

---

## Primary: Sam — Accessibility Lead, U-M LSA

A composite of the kind of user the product was commissioned for: an
in-house accessibility professional at a large university, responsible
for verifying WCAG conformance on dozens of marketing and program
sites between Siteimprove report cycles.

### Job to be done

> Find every WCAG 1.4.5 (Images of Text) violation across one of LSA's
> sites before the next Siteimprove report cycle, hand a prioritized
> list to a content editor, and verify the fixes on rescan.

That sentence determines roughly 80 % of the product's surface area.
The remaining 20 % is everything around it: configuring a crawl,
exporting findings, comparing scans over time, learning the tool.

### Context of use

* **Where:** Sam's laptop. Tool runs locally — no SaaS, no cloud
  account, no shared deployment. Often offline, often on a flaky
  network.
* **When:** Triage sessions of 1–3 hours, frequently. Sam may be
  staring at 100–2000 findings in one sitting.
* **What else is open:** the audited site in a separate browser tab,
  Siteimprove, a Jira board, sometimes a screen-sharing call with a
  content editor who has *not* used this tool before. The UI must
  explain its own decisions — "why is this critical, what is a logo
  classification" — without requiring Sam to swivel-chair into docs.
* **Pace:** mixed. Some findings are obvious 5-second triages
  ("clearly informational, alt is missing, mark new"). Some require
  reading the OCR text against the alt against the VLM rationale and
  forming a judgment. The UI should be fast at the easy ones and
  *deep* at the hard ones.

### Disabilities Sam might bring to the tool

This is the part the product brief said to take seriously. We assume
Sam is one of the following on any given day:

| Disability | Likelihood | What changes for the UI |
|---|---|---|
| Color-vision deficiency (deuteranopia / protanopia) | ~8% of men of European descent — likely | Severity must never be conveyed by color alone. Check today: severity chips are colored *and* labeled in text; live-progress dot is colored *and* paired with a "Crawl in progress" string. ✅ |
| Low vision (correctable with browser zoom + high contrast) | Realistic — Sam is reading small image-text and small alt strings all day | Reflow must work to 320px (✅, SPA hides sidebar; Jinja is single-column). Text must zoom to 200% without loss of function. Contrast must be AAA, not AA — see [`accessibility.md`](accessibility.md) §3. |
| RSI / keyboard-preferred | Realistic — Sam clicks ~ten thousand times a week otherwise | Every action reachable via keyboard. Specifically: `j/k` for findings nav, `0–5` for status set, `?` for help, Tab + Enter for everything else. The Findings table is virtualized but j/k still drives selection; verified in `tests/ui/test_keyboard_nav.py`. |
| Screen-reader primary user (NVDA / JAWS / VoiceOver) | Possible — Sam is an a11y professional and may be one themselves | Section headings must be in order (`<h1>` → `<h2>` → `<h3>`, no skips); breadcrumbs (`<nav aria-label="Breadcrumb">`) on every interior route; live regions used sparingly and politely; every form control labelled. AAA SC 1.4.8 (Visual Presentation), 2.4.10 (Section Headings), 1.3.5 (Identify Input Purpose) all bump in priority. |
| Cognitive load (situational) | Constant | UI must explain its own decisions in-product. Priority score formula visible on hover, severity glossary one click away, "Ignore robots.txt" warning treatment, Skip-OCR/Skip-VLM hints next to the toggle. |

**Working assumption to revisit.** That Sam is a *power user* of the
tool, not a first-time user. If wrong, we owe more onboarding (an
empty-state on the Dashboard could become a guided tour, the New-Scan
form could become a wizard). If right, we owe Sam efficiency —
keyboard shortcuts, density, no hand-holding modal dialogs. The
current build leans toward "power user" — Phase 4 instrumentation
will confirm or correct.

### What Sam needs from the UI, ranked

1. **A prioritized list, fast.** Open the tool, click a scan, see the
   top-10 most-urgent findings before the page finishes loading. The
   priority score's job.
2. **A defensible verdict per finding.** Sam will be asked "why is
   this critical?" by an editor. The decision grid (OCR / Alt / VLM)
   must show the inputs to the verdict, not just the verdict.
3. **A way to mark progress and move on.** Status updates are
   one-keystroke; the table refreshes; the next finding is auto-focused.
4. **An undo for the destructive moves.** Delete cascades through
   pages, findings, history. A confirmed delete is final today; this
   is a known gap (discovery §8 item 8).
5. **An export that maps cleanly to the editor's tools.** Jira CSV
   uses Jira's column names. Markdown exports include the priority
   score column so non-Jira users can sort. CSV is the universal
   fallback.

### What Sam does *not* need from the UI

* Auth. The tool runs on Sam's laptop.
* User management. Same reason.
* Multi-tenancy. Same.
* SaaS-style "team" features (comments on findings, assignees,
  watchers). Sam is the team.
* Aggressive notifications. Sam knows when the scan is running — they
  started it. The progress block is informational, not urgent.

---

## Secondary: the editor receiving exported findings

The person on the other end of Sam's export. Encounters the tool only
indirectly — opens a Jira ticket, reads a Markdown report, never opens
the UI itself.

### Job to be done

> Take a finding from Sam, fix the alt text on the page, mark the
> ticket done, move on.

### What this means for the product

* **The export schema is the editor's UX.** Column names, ordering,
  defaults all matter. The Jira CSV uses Jira's standard "Summary,
  Description, Priority, Labels" headers; the Markdown report leads
  with severity and the page URL.
* **The deep-link from the export back to the local UI must be
  explicit.** Editors will sometimes want to see the audited image —
  the export includes `http://localhost:8765/findings/{id}` so Sam can
  share their screen and walk through it.
* **Plain language in remediation hints.** The hint that ships with a
  finding (`rules/remediation.yaml`) is read by the editor, not Sam.
  No internal jargon ("classification was VLM-essential, alt-adequacy
  bucket was inadequate") — instead "this image contains text that
  isn't in the alt; add the text to alt and consider whether the
  image-of-text could become real text."

### Out of scope for the visual-UI audit

The editor is downstream of the UI work. AAA-cleaning the Jira CSV
isn't a thing (it's a CSV). But the doc-clarity of the export
templates *is* a thing; tracked under Phase 5 (export polish).

---

## Tertiary: the developer maintaining the tool

That's whoever reads this repo six months from now. Including the
maintainer is a bit unusual for a personas doc, but it matters
because:

* The tool ships no telemetry. The only signal we have for "is the
  product working as intended" is the maintainer's eye on the test
  output and the discovery audits.
* Documentation *is* the developer's UX. README, this doc,
  [`design-principles.md`](design-principles.md), the docblocks on
  `components/ui.tsx`, the audit reports — all of it is read by the
  next person who touches the code.

What we owe the maintainer:

* **Decisions written down.** Every non-obvious tradeoff (token color
  choice, the 22-px-visual / 44-px-hit-zone Checkbox split, the
  AAA-not-AA target) lives in a doc with the *why*, not just the
  *what*.
* **Tests that explain themselves.** A failing axe test should make
  the next developer's path obvious — the `_AXE_TAGS` constant in
  `tests/ui/test_accessibility_axe.py` is named, not magic.
* **No silent regressions.** The five-gate process (see
  [`accessibility.md`](accessibility.md) §2) means a regression fails
  CI, not a quarterly audit.

---

## Personas we're explicitly *not* designing for

* **Anonymous internet users.** Tool is local-only and unauthenticated;
  there is no public surface. If we ever ship a hosted version this
  changes.
* **Mobile-only users.** The audited tool runs on a laptop. The UI
  reflows to 320 px because AAA reflow demands it, but we're not
  optimizing the experience for thumb navigation.
* **Bulk-orchestration users (CI / "audit every site nightly").**
  v1 ships a `audit crawl` CLI that *can* be cron'd, but the UI is
  designed for one-at-a-time triage. If a CI persona emerges, that's
  a real product expansion, not a UI tweak.

If a future feature request implies one of these personas, that's a
signal to revisit the persona doc *before* writing code.
