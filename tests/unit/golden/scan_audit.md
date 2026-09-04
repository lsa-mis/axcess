# Accessibility audit — Scan #1


**Seed URL:** http://example.com/
**Audited against:** WCAG 2.2 Level AA
**Pages crawled:** 2
**Detection methods used:** axe-core (deterministic DOM rules), image-of-text VLM, per-criterion LLM analyzer, dynamic keyboard-trap probe

## Executive summary

After self-critique, **3 open issue type(s)** need work (1 already-triaged item(s) moved to Appendix A; 4 review-only or informational item(s) to Appendix B).

Of those, **1 map to WCAG Level A** and **1 map to Level AA**. These are likely barriers, not a standalone conformance determination; Level A items should be triaged first.

The biggest themes by reach are: *Images don't announce text to screen readers* (on 1 page); *Text doesn't meet the 4.5:1 contrast ratio* (on 1 page); *Elements must meet enhanced color contrast* (on 1 page).

**Highest-impact fix this team could ship this week:** *Images don't announce text to screen readers* — Critical, Under 15 minutes, 1 page(s).

Rough effort to clear what this tool can see: **1 quick win(s) (< 15 min each) · 1 medium item(s) (< 2 hr each)**.


## Open barrier summary

Confirmed open issue groups by mapped WCAG level; prioritize user impact and foundational dependencies:

| Level | Open issue types | What it means |
|---|---:|---|
| **A** | 1 | Foundational requirements; triage promptly alongside actual user impact. |
| **AA** | 1 | Selected report target; confirm the applicable U-M and legal context. |
| **AAA** | 1 | Beyond the selected AA target; prioritize where it materially helps users. |

By WCAG principle (the "POUR" model):

| Principle | Open issue types |
|---|---:|
| Perceivable | 3 |

## Who is affected

Each issue is tagged with the user groups it blocks. One issue can affect several groups, so these counts overlap.

| User group | Issue types affecting them | Across (page-instances) |
|---|---:|---:|
| Vision (blind / low-vision / color-blind) | 2 | 2 |

## Coverage and method

This audit used multiple detection methods. Each sees different things; together they reach further than any one tool, but none of them replace a human reviewer.

| Method | Findings here? | What it checks | Confidence |
|---|---|---|---|
| **axe-core** | ✅ found issues | Contrast, missing alt/labels, ARIA misuse, landmark structure, heading order, link/button names, target size. | High-confidence deterministic evidence, but rule applicability and remediation still need expert verification; no fixed real-world false-positive rate is claimed. |
| **Siteimprove Alfa** | — | ACT rules mapped to WCAG 2.2 at the selected level; unresolved `cantTell` outcomes are review leads. | High for failed outcomes; `cantTell` is explicitly not a conformance failure. |
| **Image-of-text VLM** | ✅ found issues | WCAG 1.4.5 (images of text) and whether the alt conveys the same information the image does. | Medium — OCR/model classification can misread decorative or context-dependent images; every result remains an expert-review lead. |
| **Per-criterion LLM analyzer** | ✅ found issues | Judgment calls automated tools miss — e.g. SC 2.4.4, whether a link's text actually describes where it goes. | Medium — semantic judgments are inherently fuzzier; treat as strong leads, confirm before mass edits. |
| **Bidirectional keyboard-exit probe** | ✅ found issues | WCAG 2.1.2 review leads — both directions must remain blocked. Normal wrapping, two-control cycles, modal containment, and opaque embedded contexts are not counted as traps. | Medium — repeatable browser-observed evidence with exact attempt counts. Manually check for documented or state-specific exit commands before recording a failure. |
| **Responsive & zoom probe** | — | SC 1.4.10 reflow at 320px, SC 1.4.4 text clipping at 200% zoom, SC 1.4.12 clipping under user text-spacing. | Medium — deterministic geometry is useful evidence, but designed truncation and state-specific clipping need an expert decision. |
| **Live-page focus probe** | — | SC 2.4.11 — focus hidden behind sticky headers / cookie banners / overlays. | Medium — catches elements whose centre is covered; partial-overlap and post-click overlays still need a human. |
| **Click-through DOM states** | — | Barriers that a page load never shows because the content only exists after a control is operated. Links are never clicked, and controls labelled sign out, delete, remove, or unsubscribe are refused. | Same deterministic rule evidence as a load-state pass, on states a load-state pass cannot reach. Coverage is bounded per page, so absence of a finding is not evidence that a state is clean. |
| **Visual (VLM) probe** | — | SC 1.3.2 — content visually reordered by CSS so screen readers get a different, confusing sequence. | Medium — a vision-model judgement; treat as a lead and confirm. Only runs when a local vision model is available. |

_A “—” means this method produced no findings on this scan — it may have been disabled for the run, or it ran and found nothing. axe-core and Alfa record definitive ran-clean signals when selected._

### States behind a click

Click-through DOM state discovery reached 0 state(s) across 0 page(s). Per-page control coverage was not recorded for this scan, so the share of controls operated is unknown.

- Hover-only content, gestures, operating-system menus, closed shadow DOM, cross-origin embeds, and states with no observable DOM change are outside what this probe can reach and still require manual testing.
- Click-revealed findings are not yet compared across scans. If one is absent from a later report, confirm the fix directly — absence is not proof of repair.


_The next section breaks this down to every WCAG 2.2 A/AA success criterion — what was automated, what was AI-assisted, and the full list of what still needs manual testing._

## WCAG 2.2 A/AA coverage — what's automated vs. manual

Across all **55** Level A/AA success criteria, here is exactly what Axcess can and cannot test. Automated results are bounded evidence, AI-assisted findings are review leads, and manual-only criteria are not detected by any pipeline. Every final decision remains part of expert review.

| Coverage | Criteria | What it means |
|---|---:|---|
| **Automated** | 5 | Deterministic checks cover defined machine-testable conditions; an expert verifies applicability and remaining states. |
| **Partly automated** | 18 | Automated checks catch the mechanical failures; the rest needs a human. |
| **AI-assisted** | 6 | A local model flags candidates — a human confirms before counting them. |
| **Manual only** | 26 | No automated detection — a human must test this criterion. |

### Automated &amp; AI-assisted (29 criteria)

| SC | Criterion | Lvl | Coverage | What Axcess does | Still verify by hand |
|---|---|---|---|---|---|
| 1.1.1 | Non-text Content | A | Partly automated | axe flags missing alt on img / area / input[type=image] and unlabelled SVGs; the image-of-text VLM separately flags pictures that are really text. | Whether the alt text that IS present is a meaningful equivalent — and the decorative-vs-informative call — needs a human. |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | A | AI-assisted | For <audio> elements, the semantic LLM checks whether a transcript or text alternative is reachable (nearby "Transcript" link / surrounding text). | Confirm the transcript is accurate and equivalent. Video-only (silent video) can't be detected from the DOM — still a manual check. |
| 1.3.1 | Info and Relationships | A | Partly automated | axe checks list, table-header, definition-list, required-ARIA-children and heading-structure markup on the rendered DOM. | Relationships conveyed only visually (grouped fields, columns, emphasis that implies meaning) need a human to confirm they're also programmatic. |
| 1.3.2 | Meaningful Sequence | A | AI-assisted | The visual probe screenshots the page and asks a local vision model whether the visual reading order matches the DOM/source order (CSS can reorder content so screen readers hear a different sequence). | Confirm the model's call by tabbing/reading with a screen reader. Subtle reorderings and content below the fold still need a human, and the probe only runs when a local vision model is available. |
| 1.3.5 | Identify Input Purpose | AA | Partly automated | axe validates that any autocomplete tokens used are valid. | Confirm autocomplete IS present on fields collecting the user's own info (name, email, address) — missing autocomplete isn't auto-detected. |
| 1.4.1 | Use of Color | A | Partly automated | axe flags links distinguished from surrounding text by colour alone (a narrow heuristic). | Most colour-only meaning — form errors, chart series, required-field markers, status — needs a human to confirm a non-colour cue exists. |
| 1.4.2 | Audio Control | A | Partly automated | The visual probe measures actual playback advancement and flags audible audio longer than three seconds when no native or explicitly associated custom control is detected. Autoplay markup alone is not flagged. | Confirm every audible autoplay source can be paused, stopped, or volume controlled independently; test custom controls and browser autoplay policy. |
| 1.4.3 | Contrast (Minimum) | AA | Partly automated | axe measures text/background contrast on the rendered DOM against the 4.5:1 (3:1 large-text) thresholds. | Text baked into images, hover/focus/disabled states, and text over gradients or photos need a human to check. |
| 1.4.4 | Resize Text | AA | Automated | The responsive probe zooms to a 200% proxy viewport and flags text that clips or overflows its container. | Confirm no loss of content or function across the full zoom range in your target browsers. |
| 1.4.5 | Images of Text | AA | AI-assisted | OCR + a local vision model judge whether each image is really rendered text rather than a photo/diagram. | Confirm flagged images aren't the allowed exceptions (logos, or text that's essential to a particular presentation). |
| 1.4.10 | Reflow | AA | Automated | The responsive probe loads each page at 320 CSS px and flags horizontal scrolling / overflow. | Confirm no content or functionality is lost in the reflowed view (some loss can pass the geometry check but still fail in use). |
| 1.4.12 | Text Spacing | AA | Automated | The responsive probe injects the WCAG text-spacing override CSS (line-height 1.5, etc.) and flags clipping/overlap. | Confirm no text is cut off or overlapping with the spacing applied. |
| 2.1.1 | Keyboard | A | Partly automated | axe flags some keyboard-inaccessible patterns; the keyboard probe confirms focus can move through the page. | Confirm every control (menus, custom widgets, drag handles) is fully operable by keyboard — the deepest part of this SC is manual. |
| 2.1.2 | No Keyboard Trap | A | Partly automated | The keyboard probe emits a review lead only when the same observable element resists repeated Tab and Shift+Tab exit attempts. It suppresses normal focus wrapping, small focus cycles, modal containment, and opaque iframe or closed-shadow focus. | Reproduce every lead and test components that appear after interaction. Confirm whether arrow keys, Escape, a close control, or a documented non-standard command lets the user leave before recording a failure. |
| 2.2.2 | Pause, Stop, Hide | A | Partly automated | The visual probe measures actual playback advancement for visible video longer than five seconds without a detected control. It also records <marquee> as an expert-review lead. | CSS animations, auto-advancing carousels, and auto-updating regions aren't auto-detected — confirm any content that moves >5s can be paused, stopped, or hidden. |
| 2.4.1 | Bypass Blocks | A | Partly automated | axe checks for a skip link, landmark regions, and a heading structure that lets users bypass repeated content. | Confirm the skip link actually moves focus and works with the keyboard. |
| 2.4.2 | Page Titled | A | Automated | axe checks that every page has a non-empty <title>. | Confirm the title is descriptive and distinguishes the page (a light human check). |
| 2.4.3 | Focus Order | A | Partly automated | The focus probe flags positive tabindex (WCAG failure F44) — a manual tab order that overrides the natural DOM order and usually breaks the sequence. | Tab through the whole page and confirm the focus order preserves meaning and operability — the order can break without a positive tabindex (e.g. CSS-reordered columns), which still needs a human. |
| 2.4.4 | Link Purpose (In Context) | A | AI-assisted | axe flags empty/unnamed links; the semantic LLM judges whether the link text plus its context conveys where it goes. | Confirm the LLM's borderline calls ("read more", icon links) — it flags strong leads, not verdicts. |
| 2.4.6 | Headings and Labels | AA | AI-assisted | axe flags empty headings / unlabelled controls; the semantic LLM judges whether each heading actually describes the content it introduces. | Confirm the LLM's borderline heading calls, and check that form-control LABELS are descriptive — label descriptiveness is not yet AI-assisted. |
| 2.4.7 | Focus Visible | AA | Partly automated | axe has limited checks for suppressed focus indicators. | Tab the whole page and confirm a clearly visible focus indicator on every interactive element — largely manual. |
| 2.4.11 | Focus Not Obscured (Minimum) | AA | Partly automated | The live-page focus probe focuses each element and flags any whose centre is covered by a position:fixed/sticky overlay (the classic "focus hidden behind the sticky header" failure). | Confirm partial-overlap cases the centre-point check can miss, and tab through interactively — overlays that appear only after a click still need a human. |
| 2.5.3 | Label in Name | A | Partly automated | axe flags controls whose accessible name doesn't contain the visible label text (label-content-name-mismatch). | Confirm the visible text is fully contained in the accessible name for voice-control users. |
| 2.5.8 | Target Size (Minimum) | AA | Partly automated | axe checks interactive targets are at least 24x24 CSS px (with spacing). | Confirm the inline / essential / equivalent-control exceptions are genuinely met for any flagged small targets. |
| 3.1.1 | Language of Page | A | Automated | axe checks <html> has a present and valid lang attribute. | Confirm the declared language actually matches the page's main content. |
| 3.1.2 | Language of Parts | AA | Partly automated | axe validates lang attributes that are present on parts of the page. | Detecting foreign-language passages that are *missing* a lang attribute needs a human reader. |
| 3.3.2 | Labels or Instructions | A | AI-assisted | axe checks a programmatic label exists; the semantic LLM judges whether each control's label/instructions are sufficient to know what to enter. | Confirm the LLM's sufficiency calls, and test real form submissions — error-time instructions (SC 3.3.x) still need a human. |
| 4.1.2 | Name, Role, Value | A | Partly automated | axe checks names/roles/values for standard controls and ARIA widgets (button-name, link-name, aria-* validity, roles). | Custom widgets' state changes (expanded, selected, checked) need a screen reader to confirm they're announced. |
| 4.1.3 | Status Messages | AA | Partly automated | axe checks for some live-region / role=status markup. | Confirm dynamic updates (added-to-cart, validation, search counts) are actually announced — needs screen-reader testing. |

### Needs manual testing (26 criteria)

No Axcess pipeline detects these — they require a human. Treat this as your manual-test checklist for full Level A/AA conformance.

| SC | Criterion | Lvl | What to test |
|---|---|---|---|
| 1.2.2 | Captions (Prerecorded) | A | Play each video and confirm synchronized, accurate captions. Auto-caption diffing (Whisper) is on the roadmap. |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | A | Confirm an audio description or full text alternative for prerecorded video. |
| 1.2.4 | Captions (Live) | AA | Confirm live audio in synchronized media has real-time captions. |
| 1.2.5 | Audio Description (Prerecorded) | AA | Confirm prerecorded video has a synchronized audio description track. |
| 1.3.3 | Sensory Characteristics | A | Read instructions for reliance on shape/size/location/sound alone ("click the round button to the right") — judgement only a human can make. |
| 1.3.4 | Orientation | AA | Confirm content isn't locked to portrait or landscape (rotate the device / check for orientation-locking CSS). |
| 1.4.11 | Non-text Contrast | AA | Check that UI component boundaries (inputs, buttons, focus rings) and meaningful graphics meet 3:1. No reliable automated rule exists yet. |
| 1.4.13 | Content on Hover or Focus | AA | For tooltips/popovers triggered by hover/focus, confirm they're dismissable, hoverable, and persistent. |
| 2.1.4 | Character Key Shortcuts | A | If single-character shortcuts exist, confirm they can be turned off, remapped, or are active only on focus. |
| 2.2.1 | Timing Adjustable | A | For any time limit, confirm it can be turned off, adjusted, or extended. |
| 2.3.1 | Three Flashes or Below Threshold | A | Confirm nothing flashes more than three times per second. Flash analysis is not implemented. |
| 2.4.5 | Multiple Ways | AA | Confirm at least two ways to find pages (nav + search, or sitemap), except for steps in a process. |
| 2.5.1 | Pointer Gestures | A | For any multipoint/path gesture (swipe, pinch), confirm a single-pointer alternative exists. |
| 2.5.2 | Pointer Cancellation | A | Confirm actions fire on the up-event and can be aborted (no critical action on down-press). |
| 2.5.4 | Motion Actuation | A | If a function is triggered by device motion (shake/tilt), confirm a UI alternative and a way to disable motion actuation. |
| 2.5.7 | Dragging Movements | AA | For any drag operation (sliders, reorder, kanban), confirm a single-pointer alternative (tap/click) exists. |
| 3.2.1 | On Focus | A | Confirm moving focus to a control doesn't trigger an unexpected context change (auto-submit, new window). |
| 3.2.2 | On Input | A | Confirm changing a setting (select, checkbox) doesn't auto-trigger a context change without warning. |
| 3.2.3 | Consistent Navigation | AA | Confirm navigation repeated across pages stays in the same relative order. A cross-page embedding analyzer is on the roadmap. |
| 3.2.4 | Consistent Identification | AA | Confirm components with the same function are labelled consistently across pages. A cross-page analyzer is on the roadmap. |
| 3.2.6 | Consistent Help | A | Confirm help mechanisms (contact, self-help) appear in the same relative order on every page that has them. |
| 3.3.1 | Error Identification | A | Submit forms with invalid data and confirm errors are identified in text. Requires interaction the crawler doesn't perform. |
| 3.3.3 | Error Suggestion | AA | Trigger validation errors and confirm the page suggests how to fix them. |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | AA | For legal/financial/data submissions, confirm reversal, checking, or confirmation is available. |
| 3.3.7 | Redundant Entry | A | In multi-step flows, confirm previously-entered info is auto-populated or selectable rather than re-typed. |
| 3.3.8 | Accessible Authentication (Minimum) | AA | Manually test each in-scope sign-in and MFA step. Confirm it does not require a cognitive function test (for example, solving a puzzle or memorizing/transcribing information) without an accessible alternative. A successful post-MFA crawl only proves that an auditor established a temporary browser session; it does not automatically evaluate or pass the authentication experience. Do not record passwords, OTPs, passkeys, recovery codes, cookies, or session details in this report. |

## Page hotspots

Pages carrying the most (and most severe) open findings. Fixing shared templates here clears issues across the rest of the site too.

| Page | Weighted load | Findings shown |
|---|---:|---:|
| http://example.com/ (Home) | 10 | 3 |

_Weighted load = sum of severity weights (Critical 4 · Serious 3 · Moderate 2 · Minor 1) for the sample locations shown per card._

## Remediation worklist by owner

The same findings, re-sliced by who fixes them. Hand each team their pack.

### Developers (1 item(s))

- [ ] **Elements must meet enhanced color contrast** — Serious, Effort: see fix steps, 1 page.

### Content editors (1 item(s))

- [ ] **Images don't announce text to screen readers** — Critical, Under 15 minutes, 1 page.

### Designers (1 item(s))

- [ ] **Text doesn't meet the 4.5:1 contrast ratio** — Serious, Under 2 hours, 1 page.


## Issue cards

### 1. Images don't announce text to screen readers

**WCAG:** SC 1.1.1 Non-text Content — Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<http://example.com/>). **Location on page:** Image with class “banner”. **Technical target:** `main > img.banner`. **Observed evidence:** Element has no alt attribute.

**What is happening:**

One or more <img> elements have no alt attribute (or have alt="" when the image is informative). Screen readers announce "image" with no context, so the information the image conveys is unreachable.

**Why it matters:**

Blind, low-vision, and screen-reader users get a broken version of the page — the image's content is silently dropped.

**Affects:** Vision.

**Severity:** Critical — Completely blocks an assistive-technology user from the affected content — no workaround.

**Effort:** Under 15 minutes

**Owner:** Editor

**Fix (do this):**

1. For each affected image, decide what the image conveys. If it conveys information, write alt text that describes the *meaning*, not the appearance ("Acme logo", not "blue square with letters").
2. If the image is purely decorative (a divider, a stock photo with no semantic role), set `alt=""` explicitly so screen readers skip it cleanly.
3. Update the CMS field or the template so the alt attribute is always present, even when empty.

**Verify it is fixed:**

- **Manual:** With a screen reader running (VoiceOver: Cmd+F5 on macOS; NVDA: Ctrl+Alt+N on Windows), tab to each affected image. It should announce meaningful text or be skipped entirely if marked decorative.
- **Automated:** axe-core image-alt rule passes after the fix.
- **Acceptance:** Every <img> on the affected pages has either a non-empty alt attribute that describes its purpose, or alt="" explicitly when decorative.

**My confidence:** High.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/image-alt_

### 2. Text doesn't meet the 4.5:1 contrast ratio

**WCAG:** SC 1.4.3 Contrast (Minimum) — Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<http://example.com/>). **Location on page:** text element containing “low text” with class “muted”. **Technical target:** `p > span.muted`. **Observed evidence:** Foreground/background contrast is 2.1.

**What is happening:**

Text falls below the WCAG 1.4.3 minimum contrast against its background (4.5:1 for body text; 3:1 for 18pt+ or 14pt-bold).

**Why it matters:**

Users with low vision, color blindness, or who view the site in bright sunlight can't read the text. This is one of the most commonly-reported barriers in user testing.

**Affects:** Vision.

**Severity:** Serious — A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Under 2 hours

**Owner:** Designer

**Fix (do this):**

1. Open the affected page in DevTools, inspect the failing element, and read its foreground and background colors.
2. Run the pair through WebAIM's Contrast Checker. Find a darker foreground (or lighter background) that clears 4.5:1.
3. Update the CSS custom property or design-system token — most contrast failures cascade from one token, so one change often fixes many findings at once.

**Verify it is fixed:**

- **Manual:** Open DevTools → Accessibility tab → Contrast ratio reading. Confirm ≥ 4.5:1 for body text, ≥ 3:1 for large text.
- **Automated:** axe-core color-contrast rule passes after the fix.
- **Acceptance:** All text on the affected pages clears 4.5:1 (body) or 3:1 (large) against its background, verified in DevTools or WebAIM.

**My confidence:** High.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/color-contrast_

### 3. Elements must meet enhanced color contrast

> ⚠ **Human review needed** — this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.4.6 — Level AAA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<http://example.com/>). **Location on page:** paragraph containing “subtle text” with class “subtle”. **Technical target:** `p.subtle`. **Observed evidence:** Contrast 6.1 — fails AAA threshold of 7.

**What is happening:**

1 finding(s) for Elements must meet enhanced color contrast across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious — A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed — no templated fix for `axe:color-contrast-enhanced` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/color-contrast-enhanced

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/color-contrast-enhanced_

## Appendix A — Findings dropped during self-critique

These issue types *were* detected but every finding in them has already been triaged (remediated, accepted as a risk, or marked a false positive). Listed here so the reader can confirm the self-critique didn't quietly hide a real bug.

| Method | Issue | WCAG | Reason set aside |
|---|---|---|---|
| axe | Form controls have no programmatic label | 4.1.2 | Already triaged: accepted_risk (1) |

## Appendix B — Review leads and informational evidence

These results are preserved for transparency but are not included in the remediation scorecard. They are AI-assisted or ambiguous review leads, informational/pass evidence, or best-practice observations with no criterion mapping. An expert decision is required before a review lead can be described as a barrier.

- **Keyboard users can't escape this element** (`keyboard-trap-stuck`) — 1 finding(s) on 1 page; **expert review / medium confidence**. Measured Tab and Shift+Tab exit attempts both remained on the same observable element; manually check for another documented exit command.
- **Images of text have no alt and can't be read** (`essential_missing`) — 1 finding(s) on 1 page; **expert review / medium confidence**. OCR/VLM-assisted image lead; confirm purpose and alternative in context.
- **The page has no top-level heading** (`page-has-heading-one`) — 1 finding(s) on 1 page; **likely barrier / high confidence**. Deterministic axe-core rule failure; verify after remediation.
- **Links don't describe their purpose (LLM-detected)** (`2.4.4`) — 1 finding(s) on 1 page; **expert review / medium confidence**. AI-assisted semantic lead; confirm in page context.

---

**Scope note.** Automated tooling evaluates only defined conditions within a subset of WCAG success criteria and reached page states. This report combines multiple methods, but a clean run is **necessary, not sufficient** for conformance. The manual matrix and recorded limitations remain part of the evaluation.