# Design principles — Universal Design + Nielsen, applied

Two frameworks, one product. This document maps both onto the actual
UI of this tool — what we already do, where we know we fall short,
and what the checklist is for new work.

> **Status.** Adopted in Phase 2. The Phase-1 discovery audit
> ([`audits/discovery.md`](../audits/discovery.md) §10) used these
> frameworks as the lens for the gap analysis; this doc promotes that
> lens to a living principles document.

The two frameworks overlap in places (UD #4 Perceptible Information ≈
Nielsen #1 Visibility of System Status) and contradict in others (UD
#5 Tolerance for Error pulls toward soft confirmations and undo;
Nielsen #7 Flexibility & Efficiency pulls toward zero-friction power
user shortcuts). When they pull apart, **Universal Design wins** — the
product's primary user is an accessibility professional, and we'd
rather sacrifice a keystroke than ship a one-click destructive action
without an undo.

---

## 1. Universal Design — seven principles

| # | Principle | What it asks | Strongest example in this codebase | Weakest (with the fix path) |
|---|---|---|---|---|
| 1 | **Equitable Use.** The design is useful to people with diverse abilities. | "Same means of use for all users; identical when possible, equivalent when not." | Severity is paired color + text — colorblind users get the same signal as everyone else. Skip-link, `aria-current`, AAA contrast on every token. | The Jinja keyboard-help dialog had no on-screen affordance for non-keyboard users to discover it (discovery §8 #18). Fix on the roadmap: visible `?` icon-button in TopBar opens the same dialog. |
| 2 | **Flexibility in Use.** The design accommodates a wide range of preferences. | "Choice in methods of use; right- or left-handed access; user pacing." | `j/k` keyboard nav and pointer click both select the same row in Findings; `0–5` shortcuts and the dropdown both set status. | No bulk-status action — Sam triages 50 obvious false-positives one at a time (discovery §8 #6). On the Phase-3+ roadmap. |
| 3 | **Simple & Intuitive Use.** Use is easy to understand regardless of experience, knowledge, language skills, or current concentration level. | "Eliminate unnecessary complexity; consistent with expectations." | The decision grid on FindingDetail puts OCR / Alt / VLM side-by-side so the verdict is *visibly* derived from its inputs, not stated as fiat. | Two parallel UIs (SPA + Jinja) drift independently and force the user to remember which routes exist on which surface. The product owner's decision on UI strategy (discovery §11) is the unblock. |
| 4 | **Perceptible Information.** The design communicates necessary information effectively to the user, regardless of ambient conditions or sensory abilities. | "Use redundant modes for essential info; maximize legibility; differentiate elements in describable ways." | Every form field has visible label + `hint` text + `aria-describedby`; every severity chip pairs color + text + (now) AAA-clean contrast; live progress wraps in `aria-live="polite"`. | The priority score is rendered as a number with no in-product explanation — the formula lives in `synthesizer/priority.py` (discovery §8 #7). Phase-4 fix: tooltip / popover on the score listing weights. |
| 5 | **Tolerance for Error.** The design minimizes hazards and adverse consequences of accidental or unintended actions. | "Arrange elements to minimize hazards; provide warnings; provide fail-safe; discourage unconscious action." | The `Checkbox` `tone="warning"` variant ("Ignore robots.txt") is amber when checked and visually distinct from perf options; delete is gated by a typed-confirm modal that explicitly lists what's about to be removed. | Delete is still irreversible — no undo, no soft-delete with a 30-day window (discovery §8 #8). Open question for Phase 3+. |
| 6 | **Low Physical Effort.** The design can be used efficiently and comfortably with a minimum of fatigue. | "Reasonable operating forces; minimize repetitive actions; minimize sustained physical effort." | Keyboard shortcuts replace the mouse for the highest-frequency action (status set, finding nav). Forms remember inputs across sub-route navigation within a session. | Native checkboxes were 13×13 — fixed in Phase 2 (`Checkbox` primitive provides 44×44 hit zones). |
| 7 | **Size & Space for Approach & Use.** Appropriate size and space is provided for approach, reach, manipulation, and use regardless of user's body size, posture, or mobility. | "Comfortable reach; clear sight lines for seated and standing; accommodate variations in hand and grip size; adequate space for assistive devices." | Reflow works to 320 px (SPA hides sidebar; Jinja is one column from the start). Density on the Findings table is set so a row is comfortably hit-able with a coarse pointer (touchscreen-friendly even though we don't optimize for it). | Sidebar disappears below `md` with no replacement nav (discovery §8 #12). Phase-3+: hamburger-toggled mobile drawer or top-nav fallback. |

---

## 2. Nielsen — ten usability heuristics

| # | Heuristic | What it asks | Strongest example | Weakest |
|---|---|---|---|---|
| 1 | **Visibility of System Status.** Keep users informed about what is going on, through appropriate feedback within reasonable time. | "Always tell the user what's happening." | Live scan progress polls every 2 s, shows in-flight URLs and last-fetched URLs with status codes. Toast on status save ("Status updated to remediated"). | Export download has no system-status feedback — Sam clicks "CSV" and gets a download with no "Preparing report (N rows)…" intermediate (discovery §8 #9). Phase-4 fix. |
| 2 | **Match Between System and the Real World.** Speak the user's language, follow real-world conventions. | "Words, phrases, concepts familiar to the user." | Status names are workflow-real ("new", "reviewing", "in_progress", "remediated", "accepted_risk", "false_positive") — not enum names ("STATE_0", "STATE_1"). Severity is "critical/major/minor/info" — Jira-compatible vocabulary. | "Essential vs informational vs decorative vs logo" classification labels are domain jargon; no in-product glossary (discovery §8 #11). Phase-3+ fix: hover definitions + `/help/glossary` route. |
| 3 | **User Control and Freedom.** Users need a clearly marked "emergency exit" to leave unwanted state. | "Support undo and redo." | Stop-crawl is a one-click action with a clear-language `confirm()`. Cancel buttons present on every form. Browser back works (we use `history.pushState` correctly). | No undo on delete (UD #5 cross-reference). Form values lost on browser back from a successful submit. |
| 4 | **Consistency and Standards.** Users should not have to wonder whether different words, situations, or actions mean the same thing. | "Follow platform and industry conventions." | All buttons go through the shared `Button` / `LinkButton` primitive (single source of truth for primary / secondary / danger / ghost variants). All severity rendering goes through `SeverityChip`. All status rendering goes through `StatusChip`. | The two-UI parity problem cuts here too: a `.card` in Jinja and a `<Card>` in SPA are spelled differently and styled in different files (discovery §1.3). |
| 5 | **Error Prevention.** Even better than good error messages is a careful design which prevents a problem from occurring. | "Eliminate error-prone conditions or confirm before commit." | The New-Scan URL field has a live scope-preview (`aria-live="polite"`) that shows what the crawl scope will be *before* the user submits. "Ignore robots.txt" is visually distinct from perf toggles and carries a warning tone. | Submit on a `<form>` is currently not blocked from invalid input beyond browser HTML5; could double-confirm if `ignore_robots` AND `whole_host` are both checked simultaneously (a particularly aggressive combination). |
| 6 | **Recognition Rather Than Recall.** Minimize the user's memory load by making elements, actions, and options visible. | "Don't make the user remember information." | Breadcrumbs on every interior route (`<nav aria-label="Breadcrumb">`); current-route highlighted in the sidebar (`aria-current="page"`); recently-fetched URLs visible during a crawl (Sam doesn't have to remember which URLs are queued). | Keyboard shortcuts (`j/k`, `0–5`, `?`) require recall. The `?` key opens a help dialog *if* you know to press it — there's no on-screen affordance pointing at it (discovery §8 #18). |
| 7 | **Flexibility and Efficiency of Use.** Accelerators may speed up the interaction for the expert user. | "Allow users to tailor frequent actions; offer shortcuts." | Keyboard shortcuts (`j/k`, `0–5`, `?`); persistent filter state in URL params (Sam can bookmark "all critical findings on scan #5"). | No saved scan configs — Sam re-enters the same URL + options every time (discovery §4 J1). No bulk-status action. |
| 8 | **Aesthetic and Minimalist Design.** Dialogues should not contain information which is irrelevant or rarely needed. | "Every extra unit of information competes with the relevant units and diminishes their relative visibility." | Empty states are short; severity chips are dense (no icons cluttering the chip); the dashboard's "About" panel is one paragraph and one bullet, not a marketing block. | The Findings table currently shows every column for every row — a Sam who only cares about severity + alt-adequacy still sees the OCR snippet column. Phase-4: column-visibility menu. |
| 9 | **Help Users Recognize, Diagnose, and Recover from Errors.** Error messages should be expressed in plain language, indicate the problem, and constructively suggest a solution. | "No error codes; precise problem statement; constructive solution." | When the seed URL returns 4xx/5xx, the ScanDetail page shows a `<Card role="alert">` that names the status code, names the page title (if any), and *suggests the fix* (try Playwright mode). | When a crawl fails partway through, the error state is a single line ("interrupted") in the scans list — Sam has to dig into the scan detail to see the partial state. Phase-3+: surface the error reason in the list. |
| 10 | **Help and Documentation.** Even though it is better if the system can be used without documentation, it may be necessary to provide help and documentation. | "Easy to search; focused on the user's task; lists concrete steps." | The README and the four `docs/` files (architecture, developer-guide, troubleshooting, user-guide) are concrete, task-oriented, and runnable. The `?` keyboard-help dialog is in-product. | No in-product glossary for the classification labels; help is "open the README" (Nielsen #2 cross-reference). |

---

## 3. The new-work checklist

Before opening a PR for a new screen, route, or interactive element,
walk through these. They take five minutes and they're the manual-review
gate from [`accessibility.md`](accessibility.md) §2.

### UD checklist (in order — these are about the user's body)

- [ ] **#1 Equitable.** Does every interaction work with keyboard
  alone? With pointer alone? With touch (24×24 minimum if we ever
  drop the AAA bar; 44×44 today)? With a screen reader?
- [ ] **#1 Equitable.** Is any signal conveyed by color alone? (Failure
  mode: severity badge that's just `bg-red-500`. Pass: badge that's
  red *and* has the word "critical" in it.)
- [ ] **#2 Flexibility.** Is there more than one way to do the
  primary action? (Pointer + keyboard at minimum; voice when feasible.)
- [ ] **#3 Simple & Intuitive.** Does the screen explain its own
  decisions? (Failure mode: a "priority: 7.4" pill with no tooltip.
  Pass: the pill links to a popover that lists the formula's inputs.)
- [ ] **#4 Perceptible.** Are all live updates announced via
  `aria-live="polite"`? (Failure mode: progress block that updates
  silently for sighted users.)
- [ ] **#5 Tolerance for Error.** Is every destructive action either
  reversible or gated by an explicit confirm that names what will be
  destroyed? (Failure mode: red "Delete" button with `confirm("Are you
  sure?")`.)
- [ ] **#6 Low Physical Effort.** Are repeated actions one keystroke
  away? (Failure mode: status set requires Tab × 4 + Enter.)
- [ ] **#7 Size & Space.** Does the screen reflow to 320 px without
  loss of function? Without horizontal scrolling? Without text
  clipping when the user applies WCAG 1.4.12 spacing overrides?

### Nielsen checklist (in order — these are about the user's mind)

- [ ] **#1 System Status.** Does every action that takes >100 ms show
  a "working…" indicator? (Failure mode: button that just stops
  responding.) Does every state change announce itself?
- [ ] **#2 Match the World.** Are the words on the screen words the
  user would use? (Failure mode: "Trigger crawl pipeline" instead of
  "Start scan".)
- [ ] **#3 User Control.** Can the user undo? Can they cancel
  mid-flight? Does Browser Back do something sensible?
- [ ] **#4 Consistency.** Does this screen reuse the existing
  primitives (`Button`, `Card`, `Checkbox`, `PageHeader`)? If a new
  primitive is needed, is it added to `components/ui.tsx` and mirrored
  in `static/styles.css`?
- [ ] **#5 Error Prevention.** Are the dangerous options visually
  distinct from the safe ones? (Failure mode: "delete all" rendered
  identically to "save".)
- [ ] **#6 Recognition over Recall.** Is anything important hidden
  behind a keystroke with no on-screen hint? (Failure mode: the `?`
  shortcut without a visible `?` button.)
- [ ] **#7 Flexibility.** Are there shortcuts for the high-frequency
  actions? Are filter and sort states URL-persistent so a user can
  bookmark or share?
- [ ] **#8 Minimalism.** Is every element on the screen earning its
  pixels? (Failure mode: a card with three icons, a subtitle, a
  caption, and a hint, all saying roughly the same thing.)
- [ ] **#9 Error Recovery.** When something fails, does the message
  name the problem in plain language, name the cause if known, and
  suggest a fix?
- [ ] **#10 Help.** Is help findable from the screen where the user
  has the question?

If any of these can't be answered "yes," that's a design discussion
to have *before* writing the code, not a regret to have after.

---

## 4. When the principles disagree

Real cases where UD and Nielsen pull apart in this codebase:

* **Stop-crawl button vs UD #5.** Stop-crawl is a one-click action
  (Nielsen #7 efficiency: power user wants it fast). But it's
  destructive (UD #5 says: gate it). We resolve it with a `confirm()`
  dialog that explicitly says "drops pending pages." UD wins; the
  efficiency cost is one Enter keypress.
* **`j/k` keyboard nav vs UD #6 Recognition.** `j/k` is great for
  efficiency (Nielsen #7) but invisible (UD #6 / Nielsen #6). We
  resolve it with the on-screen keyboard-shortcut footer in the
  Findings page and the `?`-help dialog. The footer is always-visible
  even though it's redundant for power users — UD wins.
* **Color severity vs Nielsen #4 Consistency.** A red badge for
  "critical" is clear (Nielsen #4: industry standard). But red on a
  red-tinted background was failing AA before Phase 2. We could have
  kept the consistency by lowering the bg tint; we instead recolored
  the foreground darker. UD #4 (Perceptible) wins over Nielsen #4
  (Consistency-with-Bootstrap-style-defaults).

The pattern: **Universal Design constrains the solution space;
Nielsen's heuristics optimize within it.** When the optimization runs
into the constraint, the constraint wins.
