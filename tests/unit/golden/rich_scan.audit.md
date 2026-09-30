# Accessibility audit, Scan #1

_Generated 2026-04-22 12:00 UTC by Axcess._

**Seed URL:** https://example.org/
**Audited against:** WCAG 2.2 Level AA
**Pages crawled:** 5
**Detection methods used:** axe-core (deterministic DOM rules), Siteimprove Alfa (ACT rules), image-of-text VLM, per-criterion LLM analyzer, dynamic keyboard-trap probe

## Executive summary

After self-critique, **43 open issue type(s)** need work (2 already-triaged item(s) moved to Appendix A; 9 review-only or informational item(s) to Appendix B).

Of those, **23 map to WCAG Level A** and **19 map to Level AA**. These are likely barriers, not a standalone conformance determination; Level A items should be triaged first.

The biggest themes by reach are: *Fixture rule 12 synthetic check* (on 2 pages); *Fixture rule 24 synthetic check* (on 2 pages); *Fixture rule 36 synthetic check* (on 2 pages).

**Highest-impact fix this team could ship this week:** *Images have no alt text for screen readers*, Critical, Under 15 minutes, 1 page(s).

Rough effort to clear what this tool can see: **4 quick win(s) (< 15 min each) · 2 medium item(s) (< 2 hr each)**.


## Open barrier summary

Confirmed open issue groups by mapped WCAG level; prioritize user impact and foundational dependencies:

| Level | Open issue types | What it means |
|---|---:|---|
| **A** | 23 | Foundational requirements; triage promptly alongside actual user impact. |
| **AA** | 19 | Selected report target; confirm the applicable U-M and legal context. |
| **AAA** | 1 | Beyond the selected AA target; prioritize where it materially helps users. |

By WCAG principle (the "POUR" model):

| Principle | Open issue types |
|---|---:|
| Perceivable | 14 |
| Operable | 20 |
| Understandable | 9 |

## Who is affected

Each issue is tagged with the user groups it blocks. One issue can affect several groups, so these counts overlap.

| User group | Issue types affecting them | Across (page-instances) |
|---|---:|---:|
| Vision (blind / low-vision / color-blind) | 6 | 7 |
| Motor (keyboard-only / switch / tremor) | 2 | 2 |
| Cognition (memory / attention / language) | 2 | 2 |

## Coverage and method

This audit used multiple detection methods. Each sees different things; together they reach further than any one tool, but none of them replace a human reviewer.

| Method | Findings here? | What it checks | Confidence |
|---|---|---|---|
| **axe-core** | ✅ found issues | Contrast, missing alt/labels, ARIA misuse, landmark structure, heading order, link/button names, target size. | High-confidence deterministic evidence, but rule applicability and remediation still need expert verification; no fixed real-world false-positive rate is claimed. |
| **Siteimprove Alfa** | ✅ found outcomes | ACT rules mapped to WCAG 2.2 at the selected level; unresolved `cantTell` outcomes are review leads. | High for failed outcomes; `cantTell` is explicitly not a conformance failure. |
| **Image-of-text VLM** | ✅ found issues | WCAG 1.4.5 (images of text) and whether the alt conveys the same information the image does. | Medium, OCR/model classification can misread decorative or context-dependent images; every result remains an expert-review lead. |
| **Per-criterion LLM analyzer** | ✅ found issues | Judgment calls automated tools miss, e.g. SC 2.4.4, whether a link's text actually describes where it goes. | Medium, semantic judgments are inherently fuzzier; treat as strong leads, confirm before mass edits. |
| **Bidirectional keyboard-exit probe** | ✅ found issues | WCAG 2.1.2 review leads, both directions must remain blocked. Normal wrapping, two-control cycles, modal containment, and opaque embedded contexts are not counted as traps. | Medium, repeatable browser-observed evidence with exact attempt counts. Manually check for documented or state-specific exit commands before recording a failure. |
| **Responsive & zoom probe** | n/a | SC 1.4.10 reflow at 320px, SC 1.4.4 text clipping at 200% zoom, SC 1.4.12 clipping under user text-spacing. | Medium, deterministic geometry is useful evidence, but designed truncation and state-specific clipping need an expert decision. |
| **Live-page focus probe** | n/a | SC 2.4.11, focus hidden behind sticky headers / cookie banners / overlays. | Medium, catches elements whose centre is covered; partial-overlap and post-click overlays still need a human. |
| **Click-Through** | ✅ found issues | Barriers that a page load never shows because the content only exists after a control is operated. Links are never clicked, and controls labelled sign out, delete, remove, or unsubscribe are refused. | Same deterministic rule evidence as a load-state pass, on states a load-state pass cannot reach. Coverage is bounded per page, so absence of a finding is not evidence that a state is clean. |
| **Visual (VLM) probe** | n/a | SC 1.3.2, content visually reordered by CSS so screen readers get a different, confusing sequence. | Medium, a vision-model judgement; treat as a lead and confirm. Only runs when a local vision model is available. |

_A “n/a” means this method produced no findings on this scan, it may have been disabled for the run, or it ran and found nothing. axe-core and Alfa record definitive ran-clean signals when selected._
_Alfa completed on 2 of 5 crawled page(s); its evidence is partial for this report._


### Click-Through: content behind a click

Click-Through operated 12 of 16 control(s) across 2 page(s), reaching 5 page states opened by clicking that a page load alone does not show. 2 finding(s) in this report were visible only after a control was operated.

| Measure | Value |
|---|---|
| Pages probed | 2 |
| Controls found | 16 |
| Controls operated | 12 (75%) |
| Page states opened by clicking | 5 |
| Findings visible only after a click | 2 |
| Controls refused as destructive | 0 |

- 1 page(s) hit a bound before every control was operated, so their page states opened by clicking are partially tested. They are listed below.
- Hover-only content, gestures, operating-system menus, closed shadow DOM, cross-origin embeds, and states with no observable DOM change are outside what Click-Through can reach and still require manual testing.
- Click-Through findings are not yet compared across scans. If one is absent from a later report, confirm the fix directly, absence is not proof of repair.

**Pages where the sweep stopped early**

| Page | Controls operated | Page states opened by clicking | Why it stopped |
|---|---|---|---|
| https://example.org/ | 8 of 12 | 3 | reached the per-page click limit |

_These pages were tested, but not exhaustively: content behind the controls that were not reached has neither passed nor failed._

_The next section breaks this down to every WCAG 2.2 A/AA success criterion, what was automated, what was AI-assisted, and the full list of what still needs manual testing._

## WCAG 2.2 A/AA coverage, what's automated vs. manual

Across all **55** Level A/AA success criteria, here is exactly what Axcess can and cannot test. Automated results are bounded evidence, AI-assisted findings are review leads, and manual-only criteria are not detected by any pipeline. Every final decision remains part of expert review.

| Coverage | Criteria | What it means |
|---|---:|---|
| **Automated** | 5 | Deterministic checks cover defined machine-testable conditions; an expert verifies applicability and remaining states. |
| **Partly automated** | 18 | Automated checks catch the mechanical failures; the rest needs a human. |
| **AI-assisted** | 6 | A local model flags candidates, a human confirms before counting them. |
| **Manual only** | 26 | No automated detection, a human must test this criterion. |

### Automated &amp; AI-assisted (29 criteria)

| SC | Criterion | Lvl | Coverage | What Axcess does | Still verify by hand |
|---|---|---|---|---|---|
| 1.1.1 | Non-text Content | A | Partly automated | axe flags missing alt on img / area / input[type=image] and unlabelled SVGs; the image-of-text VLM separately flags pictures that are really text. | Whether the alt text that IS present is a meaningful equivalent, and the decorative-vs-informative call, needs a human. |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | A | AI-assisted | For <audio> elements, the semantic LLM checks whether a transcript or text alternative is reachable (nearby "Transcript" link / surrounding text). | Confirm the transcript is accurate and equivalent. Video-only (silent video) can't be detected from the DOM, still a manual check. |
| 1.3.1 | Info and Relationships | A | Partly automated | axe checks list, table-header, definition-list, required-ARIA-children and heading-structure markup on the rendered DOM. | Relationships conveyed only visually (grouped fields, columns, emphasis that implies meaning) need a human to confirm they're also programmatic. |
| 1.3.2 | Meaningful Sequence | A | AI-assisted | The visual probe screenshots the page and asks a local vision model whether the visual reading order matches the DOM/source order (CSS can reorder content so screen readers hear a different sequence). | Confirm the model's call by tabbing/reading with a screen reader. Subtle reorderings and content below the fold still need a human, and the probe only runs when a local vision model is available. |
| 1.3.5 | Identify Input Purpose | AA | Partly automated | axe validates that any autocomplete tokens used are valid. | Confirm autocomplete IS present on fields collecting the user's own info (name, email, address), missing autocomplete isn't auto-detected. |
| 1.4.1 | Use of Color | A | Partly automated | axe flags links distinguished from surrounding text by colour alone (a narrow heuristic). | Most colour-only meaning, form errors, chart series, required-field markers, status, needs a human to confirm a non-colour cue exists. |
| 1.4.2 | Audio Control | A | Partly automated | The visual probe measures actual playback advancement and flags audible audio longer than three seconds when no native or explicitly associated custom control is detected. Autoplay markup alone is not flagged. | Confirm every audible autoplay source can be paused, stopped, or volume controlled independently; test custom controls and browser autoplay policy. |
| 1.4.3 | Contrast (Minimum) | AA | Partly automated | axe measures text/background contrast on the rendered DOM against the 4.5:1 (3:1 large-text) thresholds. | Text baked into images, hover/focus/disabled states, and text over gradients or photos need a human to check. |
| 1.4.4 | Resize Text | AA | Automated | The responsive probe zooms to a 200% proxy viewport and flags text that clips or overflows its container. | Confirm no loss of content or function across the full zoom range in your target browsers. |
| 1.4.5 | Images of Text | AA | AI-assisted | OCR + a local vision model judge whether each image is really rendered text rather than a photo/diagram. | Confirm flagged images aren't the allowed exceptions (logos, or text that's essential to a particular presentation). |
| 1.4.10 | Reflow | AA | Automated | The responsive probe loads each page at 320 CSS px and flags horizontal scrolling / overflow. | Confirm no content or functionality is lost in the reflowed view (some loss can pass the geometry check but still fail in use). |
| 1.4.12 | Text Spacing | AA | Automated | The responsive probe injects the WCAG text-spacing override CSS (line-height 1.5, etc.) and flags clipping/overlap. | Confirm no text is cut off or overlapping with the spacing applied. |
| 2.1.1 | Keyboard | A | Partly automated | axe flags some keyboard-inaccessible patterns; the keyboard check finds controls with mouse handlers that Tab cannot reach or Enter/Space cannot press, and its advanced mode operates each one to confirm it. | Confirm every control (menus, custom widgets, drag handles) is fully operable by keyboard, the deepest part of this SC is manual. |
| 2.1.2 | No Keyboard Trap | A | Partly automated | The keyboard probe emits a review lead only when the same observable element resists repeated Tab and Shift+Tab exit attempts. It suppresses normal focus wrapping, small focus cycles, modal containment, and opaque iframe or closed-shadow focus. | Reproduce every lead and test components that appear after interaction. Confirm whether arrow keys, Escape, a close control, or a documented non-standard command lets the user leave before recording a failure. |
| 2.2.2 | Pause, Stop, Hide | A | Partly automated | The visual probe measures actual playback advancement for visible video longer than five seconds without a detected control. It also records <marquee> as an expert-review lead. | CSS animations, auto-advancing carousels, and auto-updating regions aren't auto-detected, confirm any content that moves >5s can be paused, stopped, or hidden. |
| 2.4.1 | Bypass Blocks | A | Partly automated | axe checks for a skip link, landmark regions, and a heading structure that lets users bypass repeated content. | Confirm the skip link actually moves focus and works with the keyboard. |
| 2.4.2 | Page Titled | A | Automated | axe checks that every page has a non-empty <title>. | Confirm the title is descriptive and distinguishes the page (a light human check). |
| 2.4.3 | Focus Order | A | Partly automated | The focus probe flags positive tabindex (WCAG failure F44), a manual tab order that overrides the natural DOM order and usually breaks the sequence. | Tab through the whole page and confirm the focus order preserves meaning and operability, the order can break without a positive tabindex (e.g. CSS-reordered columns), which still needs a human. |
| 2.4.4 | Link Purpose (In Context) | A | AI-assisted | axe flags empty/unnamed links; the semantic LLM judges whether the link text plus its context conveys where it goes. | Confirm the LLM's borderline calls ("read more", icon links), it flags strong leads, not verdicts. |
| 2.4.6 | Headings and Labels | AA | AI-assisted | axe flags empty headings / unlabelled controls; the semantic LLM judges whether each heading actually describes the content it introduces. | Confirm the LLM's borderline heading calls, and check that form-control LABELS are descriptive, label descriptiveness is not yet AI-assisted. |
| 2.4.7 | Focus Visible | AA | Partly automated | axe has limited checks for suppressed focus indicators. | Tab the whole page and confirm a clearly visible focus indicator on every interactive element, largely manual. |
| 2.4.11 | Focus Not Obscured (Minimum) | AA | Partly automated | The live-page focus probe focuses each element and flags any whose centre is covered by a position:fixed/sticky overlay (the classic "focus hidden behind the sticky header" failure). | Confirm partial-overlap cases the centre-point check can miss, and tab through interactively, overlays that appear only after a click still need a human. |
| 2.5.3 | Label in Name | A | Partly automated | axe flags controls whose accessible name doesn't contain the visible label text (label-content-name-mismatch). | Confirm the visible text is fully contained in the accessible name for voice-control users. |
| 2.5.8 | Target Size (Minimum) | AA | Partly automated | axe checks interactive targets are at least 24x24 CSS px (with spacing). | Confirm the inline / essential / equivalent-control exceptions are genuinely met for any flagged small targets. |
| 3.1.1 | Language of Page | A | Automated | axe checks <html> has a present and valid lang attribute. | Confirm the declared language actually matches the page's main content. |
| 3.1.2 | Language of Parts | AA | Partly automated | axe validates lang attributes that are present on parts of the page. | Detecting foreign-language passages that are *missing* a lang attribute needs a human reader. |
| 3.3.2 | Labels or Instructions | A | AI-assisted | axe checks a programmatic label exists; the semantic LLM judges whether each control's label/instructions are sufficient to know what to enter. | Confirm the LLM's sufficiency calls, and test real form submissions, error-time instructions (SC 3.3.x) still need a human. |
| 4.1.2 | Name, Role, Value | A | Partly automated | axe checks names/roles/values for standard controls and ARIA widgets (button-name, link-name, aria-* validity, roles). | Custom widgets' state changes (expanded, selected, checked) need a screen reader to confirm they're announced. |
| 4.1.3 | Status Messages | AA | Partly automated | axe checks for some live-region / role=status markup. | Confirm dynamic updates (added-to-cart, validation, search counts) are actually announced, needs screen-reader testing. |

### Needs manual testing (26 criteria)

No Axcess pipeline detects these, they require a human. Treat this as your manual-test checklist for full Level A/AA conformance.

| SC | Criterion | Lvl | What to test |
|---|---|---|---|
| 1.2.2 | Captions (Prerecorded) | A | Play each video and confirm synchronized, accurate captions. Auto-caption diffing (Whisper) is on the roadmap. |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | A | Confirm an audio description or full text alternative for prerecorded video. |
| 1.2.4 | Captions (Live) | AA | Confirm live audio in synchronized media has real-time captions. |
| 1.2.5 | Audio Description (Prerecorded) | AA | Confirm prerecorded video has a synchronized audio description track. |
| 1.3.3 | Sensory Characteristics | A | Read instructions for reliance on shape/size/location/sound alone ("click the round button to the right"), judgement only a human can make. |
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

## Expert evaluation record

**Target:** WCAG 2.2 Level AA
**Review status:** in progress
**Reviewer:** Fixture Reviewer

**Purpose:** Pre-launch accessibility review.

**Included scope:** Public marketing pages.

**Excluded scope:** Checkout.

**Sample:** Five representative templates.

**Methods:** Automated scan plus keyboard and screen reader checks.

**Limitations:** No mobile assistive technology testing.

### Manual-check decisions

| SC | Outcome | Rationale |
|---|---|---|
| 1.1.1 | fail | Banner image has no text alternative. |
| 1.2.1 | not tested | No prerecorded media on the sampled pages. |
| 2.4.7 | pass | Focus indicator visible on every control tested. |

### Not-tested criteria, documented evaluation limitations

These criteria were not tested. Their expert rationales are part of the evaluation's documented limitations.

| SC | Criterion | Limitation rationale |
|---|---|---|
| 1.2.1 | Audio-only and Video-only (Prerecorded) | No prerecorded media on the sampled pages. |

### Evidence references

| SC | Page | External reference | Expert note |
|---|---|---|---|
| 1.1.1 | https://example.org/ | https://evidence.example.org/1-1-1 | Screen reader announced the file name. |
| 2.4.7 | n/a | n/a | Checked with the keyboard only. |

## Page hotspots

Pages carrying the most (and most severe) open findings. Fixing shared templates here clears issues across the rest of the site too.

| Page | Weighted load | Findings shown |
|---|---:|---:|
| https://example.org/ (Home) | 87 | 32 |
| https://example.org/about (About us) | 47 | 19 |
| https://example.org/blog (Blog) | 14 | 6 |
| https://example.org/contact (Contact) | 14 | 6 |
| https://example.org/products | 12 | 4 |

_Weighted load = sum of severity weights (Critical 4 · Serious 3 · Moderate 2 · Minor 1) for the sample locations shown per card._

## Remediation worklist by owner

The same findings, re-sliced by who fixes them. Hand each team their pack.

### Developers (38 item(s))

- [ ] **Fixture rule 12 synthetic check**, Critical, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 24 synthetic check**, Critical, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 36 synthetic check**, Critical, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 04 synthetic check**, Critical, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 08 synthetic check**, Critical, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 16 synthetic check**, Critical, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 20 synthetic check**, Critical, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 28 synthetic check**, Critical, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 32 synthetic check**, Critical, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 09 synthetic check**, Serious, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 21 synthetic check**, Serious, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 33 synthetic check**, Serious, Effort: see fix steps, 2 pages.
- [ ] **Fixture: buttons [primary/secondary] need names?**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 05 synthetic check**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 13 synthetic check**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 17 synthetic check**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 25 synthetic check**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 29 synthetic check**, Serious, Effort: see fix steps, 1 page.
- [ ] **Links have no name for screen readers**, Serious, Under 15 minutes, 1 page.
- [ ] **Fixture rule without a documentation link**, Moderate, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 06 synthetic check**, Moderate, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 18 synthetic check**, Moderate, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 30 synthetic check**, Moderate, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 02 synthetic check**, Moderate, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 10 synthetic check**, Moderate, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 14 synthetic check**, Moderate, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 22 synthetic check**, Moderate, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 26 synthetic check**, Moderate, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 34 synthetic check**, Moderate, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 03 synthetic check**, Minor, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 15 synthetic check**, Minor, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 27 synthetic check**, Minor, Effort: see fix steps, 2 pages.
- [ ] **Fixture rule 07 synthetic check**, Minor, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 11 synthetic check**, Minor, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 19 synthetic check**, Minor, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 23 synthetic check**, Minor, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 31 synthetic check**, Minor, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 35 synthetic check**, Minor, Effort: see fix steps, 1 page.

### Content editors (3 item(s))

- [ ] **Images have no alt text for screen readers**, Critical, Under 15 minutes, 1 page.
- [ ] **Rule check (Alfa), The image has no accessible name. [Stored evidence is unavailable.] (Alfa sia-r2)**, Moderate, Under 15 minutes, 1 page.
- [ ] **Link text may not say where the link goes**, Moderate, Under 15 minutes, 1 page.

### Designers (2 item(s))

- [ ] **Text does not stand out enough from its background**, Serious, Under 2 hours, 2 pages.
- [ ] **Text misses the stricter Level AAA contrast ratio**, Serious, Under 2 hours, 1 page.


## Issue cards

### 1. Fixture rule 12 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.3.1, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-12`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-12`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 12 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-12` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-12

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-12_

### 2. Fixture rule 24 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.3.1, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-24`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-24`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 24 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-24` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-24

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-24_

### 3. Fixture rule 36 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.3.1, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-36`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-36`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 36 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-36` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-36

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-36_

### 4. Fixture rule 04 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.3.1, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Blog](<https://example.org/blog>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-04`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 04 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-04` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-04

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-04_

### 5. Fixture rule 08 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.3.1, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [https://example.org/products](<https://example.org/products>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-08`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 08 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-08` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-08

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-08_

### 6. Fixture rule 16 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.3.1, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-16`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 16 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-16` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-16

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-16_

### 7. Fixture rule 20 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.3.1, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-20`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 20 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-20` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-20

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-20_

### 8. Fixture rule 28 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.3.1, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [https://example.org/products](<https://example.org/products>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-28`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 28 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-28` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-28

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-28_

### 9. Fixture rule 32 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.3.1, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Contact](<https://example.org/contact>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-32`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 32 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-32` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-32

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-32_

### 10. Images have no alt text for screen readers

**WCAG:** SC 1.1.1 Non-text Content, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Image with class “banner”. **Technical target:** `main > img.banner`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

An image (`<img>`) has no alt text (the text a screen reader reads for an image). The rule check (axe) found no `alt` attribute, `aria-label`, `aria-labelledby` or `title`, and no role that marks it as decoration (`role="none"` or `role="presentation"`). An `alt` that holds only a space, such as `alt=" "`, also fails. The check only sees whether alt text exists, not whether it is good.

**Why it matters:**

Blind and deafblind people who use a screen reader or a braille display get nothing from the image. Without an alt attribute, screen readers often read the file name instead, such as "image.jpg".

**Affects:** Vision.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

**Effort:** Under 15 minutes

**Owner:** Editor

**Fix (do this):**

1. Decide what the image does on this page. If it gives information, write alt text that says what it means, not how it looks. For example, write "Acme logo", not "blue square with letters": `<img src="logo.png" alt="Acme logo">`. Do not use the file name or the word "image".
2. If the image is only decoration, add an empty alt: `alt=""`, with nothing between the quotes. Screen readers then skip it.
3. An image that is the only content of a link or a button needs alt text that says what it does. For a link, say where it goes: `<a href="/search"><img src="search.svg" alt="Search"></a>`.
4. Change the content management system (CMS) field or the page template so every image always gets an `alt` attribute, even an empty one.

**Verify it is fixed:**

- **Manual:** Turn on a screen reader (VoiceOver: Cmd+F5 on macOS; NVDA: Ctrl+Alt+N on Windows). Tab does not stop on images, so read line by line (VoiceOver: Control+Option+Right Arrow; NVDA: Down Arrow). You should hear alt text that makes sense for each image that gives information, and nothing for decorative images.
- **Automated:** Scan again and see if this image is still found.
- **Acceptance:** Every image on the affected pages has alt text that says what it means, or alt="" when it is only decoration.

**My confidence:** High.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/image-alt_

### 11. Text does not stand out enough from its background

**WCAG:** SC 1.4.3 Contrast (Minimum), Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 3 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** text element containing “low text” with class “muted”. **Technical target:** `p > span.muted`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `footer small`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `.details p`. **Seen after:** activating "Show more" on this page. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

The rule check (axe) measured the contrast between the text color and its background color, and it is too low. Normal text needs a ratio of at least 4.5:1, and large text needs 3:1. Large text is at least 18pt (24px), or at least 14pt (about 18.7px) and bold. The rule check does not report text it cannot measure, such as text over an image or a gradient.

**Why it matters:**

People with low vision or color blindness may not be able to read text that is too close in color to its background. Glare from bright sunlight makes such text hard for everyone to read.

**Affects:** Vision.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Under 2 hours

**Owner:** Designer

**Fix (do this):**

1. Open the occurrence and read the measured ratio, the two colors, the font size and the font weight. For example: "color contrast of 4.16 (foreground color: #3170fb, background color: #fafafc, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1". The foreground color is the text color.
2. Put the two colors into a contrast checker, such as the WebAIM Contrast Checker. Find a darker text color or a lighter background that reaches 4.5:1, or 3:1 for large text. Do not round up: 4.499:1 does not pass.
3. Change the color where the whole site sets it, such as a shared color setting (design token) or a CSS custom property like `--link-color`. One setting often colors many elements, so one change can fix many occurrences.
4. Check the same text in every state people can see, such as hover, focus and visited.

**Verify it is fixed:**

- **Manual:** In Chrome's developer tools, use the Inspect tool and point at the text: the pop-up shows the contrast ratio. Check text over images or gradients by eye, because the rule check does not report it. Text in a logo, or on a control that is turned off (disabled), has no contrast requirement.
- **Automated:** Scan again and see if this text is still found.
- **Acceptance:** Every piece of text on the affected pages reaches 4.5:1 against its background, or 3:1 when it is large text.

**My confidence:** High.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/color-contrast_

### 12. Fixture rule 09 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.4.7, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-09`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-09`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 09 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-09` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-09

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-09_

### 13. Fixture rule 21 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.4.7, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-21`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-21`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 21 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-21` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-21

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-21_

### 14. Fixture rule 33 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.4.7, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-33`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-33`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 33 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-33` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-33

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-33_

### 15. Text misses the stricter Level AAA contrast ratio

**WCAG:** SC 1.4.6 Contrast (Enhanced), Level AAA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `p.subtle`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

The rule check (axe) found text that meets the Level AA contrast minimum but not the stricter Level AAA level. The contrast ratio measures how much lighter one color is than the other, from 1:1 (same color) to 21:1 (black on white). This text is at least 4.5:1 but under 7:1, or, for large text, at least 3:1 but under 4.5:1. Text below the AA minimum shows up in the `color-contrast` issue instead.

**Why it matters:**

Text that blends into its background is hard to read for people with low vision, and color blindness can lower the contrast even more. The 7:1 level makes up for the contrast loss of about 20/80 vision (seeing at 20 feet what most people see at 80 feet).

**Affects:** Vision.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Under 2 hours

**Owner:** Designer

**Fix (do this):**

1. Check whether your policy asks for Level AAA. If it asks only for Level AA, you do not have to fix this, but a fix still helps people with low vision. The World Wide Web Consortium (W3C), which writes WCAG, does not advise requiring Level AAA for a whole site. Some content cannot meet every Level AAA criterion.
2. Open each occurrence and read the check's message. It gives the contrast ratio, the text color (foreground color), the background color, the font size and the font weight. For example: "contrast of 6.54 ... Expected contrast ratio of 7:1".
3. Pick a darker text color, or a lighter background, that reaches 7:1 for normal text, or 4.5:1 for large text. Large text is 24px (18pt) or bigger, or 14pt (about 18.7px) or bigger in bold. Do not round up: 6.99:1 does not meet 7:1. For example, on white, `#767676` gives 4.54:1 and `#595959` just reaches 7:1.
4. Change the color in the shared style (the design token or CSS custom property, such as `--text-muted: #595959;`), not on each element. One shared color often causes many occurrences, so one change can fix them all.

**Verify it is fixed:**

- **Manual:** Inspect the text in your browser's developer tools; in Chrome, the color picker shows the contrast ratio with AA and AAA lines. Check hover and focus states too. Use a contrast checker for text on images or gradients, text under other elements, and images of text, because the rule check (axe) skips them.
- **Automated:** Scan again at Level AAA and see if this text is still found, because a Level AA scan does not run this rule.
- **Acceptance:** Every text element on the affected pages reaches 7:1 contrast with its background, or 4.5:1 if large, except logos and disabled controls.

**My confidence:** High.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/color-contrast-enhanced_

### 16. Fixture: buttons [primary/secondary] need names?

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.4.7, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-01`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture: buttons [primary/secondary] need names? across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-01` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-01

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-01_

### 17. Fixture rule 05 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.4.7, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-05`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 05 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-05` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-05

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-05_

### 18. Fixture rule 13 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.4.7, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [https://example.org/products](<https://example.org/products>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-13`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 13 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-13` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-13

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-13_

### 19. Fixture rule 17 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.4.7, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Contact](<https://example.org/contact>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-17`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 17 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-17` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-17

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-17_

### 20. Fixture rule 25 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.4.7, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-25`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 25 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-25` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-25

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-25_

### 21. Fixture rule 29 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.4.7, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Blog](<https://example.org/blog>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-29`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 29 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-29` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-29

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-29_

### 22. Links have no name for screen readers

**WCAG:** SC 2.4.4 Link Purpose (In Context), Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 12 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Link with class “nav-1”. **Technical target:** `nav > a:nth-child(1)`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Link with class “nav-2”. **Technical target:** `nav > a:nth-child(2)`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Link with class “nav-3”. **Technical target:** `nav > a:nth-child(3)`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Link with class “nav-4”. **Technical target:** `nav > a:nth-child(4)`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Link with class “nav-5”. **Technical target:** `nav > a:nth-child(5)`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Link with class “nav-6”. **Technical target:** `nav > a:nth-child(6)`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Link with class “nav-7”. **Technical target:** `nav > a:nth-child(7)`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Link with class “nav-8”. **Technical target:** `nav > a:nth-child(8)`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Link with class “nav-9”. **Technical target:** `nav > a:nth-child(9)`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Link with class “nav-10”. **Technical target:** `nav > a:nth-child(10)`. **Observed evidence:** Fix any of the following: the rule's check failed.
- _…and 2 more location(s)._

**What is happening:**

A link (`<a href>`) has no name that a screen reader can read (accessible name). The rule check (axe) found no text inside the link that a screen reader can read, and no `aria-label`, `aria-labelledby` or `title`. Common causes are an empty link, a link with only an icon, and a link around an image with no alt text. The check only sees whether a name exists, not whether it is clear.

**Why it matters:**

Screen reader users do not know where the link goes, on the page or in their list of links. The screen reader may say only "link", or read out an image's file name. People who use voice control cannot say the link's name to click it.

**Affects:** Vision, Motor, Cognition.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Under 15 minutes

**Owner:** Dev

**Fix (do this):**

1. If the link holds only an image, give the image alt text that says where the link goes: `<a href="/search"><img src="search.svg" alt="Search"></a>`.
2. If the link holds only an icon, add `aria-label="Search"` to the link, or visually hidden text inside it.
3. If the link has text, make sure `display: none` or `aria-hidden="true"` does not hide it from screen readers. If an empty link sits next to a link to the same page, remove the empty one.
4. Make each name say where the link goes. A list of links that all say "read more" or "click here" does not tell people which link is which.

**Verify it is fixed:**

- **Manual:** Turn on a screen reader and open its list of links (VoiceOver: Control+Option+U, then choose Links; NVDA: Insert+F7). Every link should have a name that says where it goes. Then press Tab to each fixed link and listen to what the screen reader says.
- **Automated:** Scan again and see if this link is still found.
- **Acceptance:** Every link on the affected pages has a name a screen reader can read, and the name says where the link goes.

**My confidence:** High.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/link-name_

### 23. Fixture rule without a documentation link

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.3.1, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `div.card`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Blog](<https://example.org/blog>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `div.card`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule without a documentation link across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Moderate, 2 finding(s) on 2 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-empty-help` in `rules/audit_report.yaml` yet.

**My confidence:** Medium.

### 24. Fixture rule 06 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 3.3.2, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-06`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-06`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 06 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Moderate, 2 finding(s) on 2 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-06` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-06

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-06_

### 25. Fixture rule 18 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 3.3.2, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-18`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-18`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 18 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Moderate, 2 finding(s) on 2 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-18` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-18

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-18_

### 26. Fixture rule 30 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 3.3.2, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-30`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-30`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 30 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Moderate, 2 finding(s) on 2 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-30` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-30

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-30_

### 27. Fixture rule 02 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 3.3.2, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Contact](<https://example.org/contact>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-02`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 02 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Moderate, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-02` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-02

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-02_

### 28. Fixture rule 10 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 3.3.2, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-10`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 10 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Moderate, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-10` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-10

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-10_

### 29. Fixture rule 14 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 3.3.2, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Blog](<https://example.org/blog>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-14`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 14 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Moderate, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-14` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-14

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-14_

### 30. Fixture rule 22 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 3.3.2, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Contact](<https://example.org/contact>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-22`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 22 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Moderate, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-22` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-22

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-22_

### 31. Fixture rule 26 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 3.3.2, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-26`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 26 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Moderate, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-26` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-26

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-26_

### 32. Fixture rule 34 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 3.3.2, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Blog](<https://example.org/blog>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-34`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 34 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Moderate, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-34` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-34

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-34_

### 33. Rule check (Alfa), The image has no accessible name. [Stored evidence is unavailable.] (Alfa sia-r2)

> ⚠ **Human review needed**, Alfa ACT evidence is a review lead, not a conformance verdict. Confirm any `cantTell` outcome manually before reporting it as a barrier.

**WCAG:** SC 1.1.1, Level A

**Detected by:** Siteimprove Alfa (ACT rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Element recorded in Alfa's structured target evidence. **Technical target:** `{"path":["html","body","img"]}`. **Observed evidence:** The image has no accessible name. [Stored evidence is unavailable.]

**What is happening:**

This rule check (Alfa) looks at every element that screen readers treat as an image. That means an `<img>`, or any HTML element with `role="img"`, that is not hidden from screen readers. It fails when the image has no name for a screen reader to read (accessible name), or the name is only spaces. A common cause is an `<img>` with no `alt` attribute and no other name.

**Why it matters:**

Blind and low-vision people who use a screen reader get no words that say what the image shows. People who read the page on a braille display lose the same information. A failed rule is strong evidence, but it does not prove the page fails WCAG. Check that the rule applies here before you report it.

**Affects:** Vision.

**Severity:** Moderate, 1 finding(s) on 1 page(s).

**Effort:** Under 15 minutes

**Owner:** Editor

**Fix (do this):**

1. Decide what each flagged image is for. If it gives information, add alt text (the text a screen reader reads for an image) that says the same thing in a few words. Example: `<img src="chart.png" alt="Sales rose 20% in 2025">`
2. If the image is only decoration, give it an empty alt: `<img src="swirl.png" alt="">`. Do not also give it `tabindex`, `aria-label`, `aria-labelledby` or `aria-describedby`. Any of these makes screen readers treat it as an image again.
3. For an element that is not an `<img>`, such as `<div role="img">`, add a name with `aria-label` or `aria-labelledby`. Example: `<div role="img" aria-label="Five stars out of five">`
4. Fix the template or the image field in your content system. Editors should either write alt text or choose to mark the image as decoration. Do not add `alt=""` to every image by default, because that hides images that give information.

**Verify it is fixed:**

- **Manual:** Turn on a screen reader (VoiceOver: Cmd+F5 on macOS; NVDA on Windows) and move through each flagged image. An image that gives information should read out a useful name. A decorative image should be skipped.
- **Automated:** Scan again with Alfa or Both as the rule check tool, and see if these images are still found.
- **Acceptance:** Every image that screen readers can reach has a name that is not empty, and every decorative image is hidden from screen readers.

**My confidence:** High.

_Rule docs: https://alfa.siteimprove.com/rules/sia-r2_

### 34. Link text may not say where the link goes

**WCAG:** SC 2.4.4 Link Purpose (In Context), Level A

**Detected by:** per-criterion LLM analyzer.

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Contact](<https://example.org/contact>). **Location on page:** link containing “click here” with class “cta”. **Technical target:** `a.cta[ord=3]`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

The AI review (a language model on this computer) reads the first 50 links on each page. It skips links to a spot on the same page, and email, phone, text-message and script (`javascript:`) links. For each link, it sees the link address and the name a screen reader reads (accessible name). It also sees the text of up to 5 elements that contain the link, such as its paragraph or list item. It reports a link only when it judges that you cannot tell where the link goes, even with that text. Examples are "click here", "read more", a bare web address, or an icon link with no name. The model can be wrong, for example about long brand names or abbreviations, so a person must confirm each occurrence.

**Why it matters:**

Screen reader users often jump from link to link, or open a list of all links. Then they hear only the link text, so "read more" tells them nothing unless they stop to read the text around it. Clear links also help people with physical disabilities skip links they do not want, and help people with cognitive disabilities avoid getting lost.

**Affects:** Vision, Cognition, Motor.

**Severity:** Moderate, 1 finding(s) on 1 page(s).

**Effort:** Under 15 minutes

**Owner:** Editor

**Fix (do this):**

1. Read the model's reason and suggested fix in the occurrence. Then find the link on the live page and read it together with its sentence, paragraph, list item, table cell, or the heading before it.
2. If the purpose is clear from that nearby text, set the status to Not a problem (false positive).
3. If it is not clear, rewrite the link text so it names the destination. For example, change "Click here" to "Download the 2025 annual report (PDF)".
4. For a link that is only an image or icon, give it a name. Give the image alt text (the text a screen reader reads for an image) that names the destination. Or add an `aria-label` to the link, for example `<a href="/search" aria-label="Search the catalog">`.

**Verify it is fixed:**

- **Manual:** Open the list of links in a screen reader (VoiceOver: VO+U, then Links; NVDA: Insert+F7). For a link that is unclear on its own, read its sentence, paragraph, list item or table cell, and the heading before it. Each link should make clear where it goes, from its text or from that context.
- **Automated:** Scan again with AI review of wording turned on, and see if the link is still found.
- **Acceptance:** Every link on the affected pages tells people where it goes, from its own text or from the text and heading around it.

**My confidence:** Medium.

_Rule docs: https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html_

### 35. Fixture rule 03 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.5.8, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-03`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-03`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 03 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Minor, 2 finding(s) on 2 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-03` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-03

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-03_

### 36. Fixture rule 15 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.5.8, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-15`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-15`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 15 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Minor, 2 finding(s) on 2 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-15` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-15

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-15_

### 37. Fixture rule 27 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.5.8, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 2 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-27`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-27`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

2 finding(s) for Fixture rule 27 synthetic check across 2 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Minor, 2 finding(s) on 2 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-27` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-27

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-27_

### 38. Fixture rule 07 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.5.8, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Contact](<https://example.org/contact>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-07`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 07 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Minor, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-07` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-07

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-07_

### 39. Fixture rule 11 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.5.8, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-11`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 11 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Minor, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-11` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-11

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-11_

### 40. Fixture rule 19 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.5.8, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Blog](<https://example.org/blog>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-19`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 19 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Minor, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-19` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-19

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-19_

### 41. Fixture rule 23 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.5.8, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [https://example.org/products](<https://example.org/products>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-23`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 23 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Minor, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-23` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-23

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-23_

### 42. Fixture rule 31 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.5.8, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-31`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 31 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Minor, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-31` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-31

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-31_

### 43. Fixture rule 35 synthetic check

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 2.5.8, Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `#fixture-35`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Fixture rule 35 synthetic check across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Minor, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:fixture-rule-35` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-35

**My confidence:** Medium.

_Rule docs: https://dequeuniversity.com/rules/axe/4.10/fixture-rule-35_

## Appendix A, Findings dropped during self-critique

These detected findings or finding subsets were set aside after triage (remediated, accepted as a risk, or marked a false positive). Listed here so the reader can confirm the self-critique didn't quietly hide a real bug.

| Method | Issue | WCAG | Reason set aside |
|---|---|---|---|
| axe | Text does not stand out enough from its background | 1.4.3 | Triaged subset: false_positive (1) |
| axe | Form fields have no name for screen readers | 4.1.2 | Already triaged: accepted_risk (1) |

## Appendix B, Review leads and informational evidence

These results are preserved for transparency but are not included in the remediation scorecard. They are AI-assisted or ambiguous review leads, informational/pass evidence, or best-practice observations with no criterion mapping. An expert decision is required before a review lead can be described as a barrier.

**Alfa note:** Alfa ACT evidence is a review lead when the engine returns `cantTell`; it is not a conformance failure until an expert reviews the stored evidence.

- **The page has no main heading (h1)** (`page-has-heading-one`), 3 finding(s) on 3 pages; **likely barrier / high confidence**. The rule check (axe) found the page code breaks this rule.
- **Some content sits outside any page region** (`region`), 2 finding(s) on 2 pages; **likely barrier / high confidence**. The rule check (axe) found the page code breaks this rule.
- **Images with important text have no alt text** (`essential_missing`), 2 finding(s) on 2 pages; **expert review / medium confidence**. Text recognition (OCR) and a vision model found text in this image. Check what the image is for and whether its alt text says the same.
- **Keyboard focus may be stuck on one element** (`keyboard-trap-stuck`), 1 finding(s) on 1 page; **expert review / medium confidence**. Pressing Tab and pressing Shift+Tab both left focus on the same element. Check by hand whether another key, such as Escape, moves focus out.
- **Link text may not say where the link goes** (`2.4.4`), 2 finding(s) on 2 pages; **expert review / medium confidence**. The AI review (a language model on this computer) judged this. Check it on the page before you report it.
- **Image with words has empty or different alt text** (`unclassified_inadequate`), 2 finding(s) on 2 pages; **expert review / low confidence**. Axcess could not tell what this image is for: the vision model did not sort it. Decide that by hand before you report a barrier.
- **Rule check (Alfa), a person must decide (Alfa sia-r111)** (`sia-r111:cant_tell`), 1 finding(s) on 1 page; **expert review / medium confidence**. The rule check (Alfa) could not decide on 1 occurrence. That is not a failure. Alfa could not decide whether the target spacing is sufficient. [Stored evidence is unavailable.]
- **Image with words has no alt text** (`unclassified_missing`), 1 finding(s) on 1 page; **expert review / low confidence**. Axcess could not tell what this image is for: the vision model did not sort it. Decide that by hand before you report a barrier.
- **Logo alt text uses words from the logo** (`logo_adequate`), 1 finding(s) on 1 page; **informational / medium confidence**. The alt text says the same as the text in the image. It is kept as a record, not a problem to fix.

---

**Scope note.** Automated tooling evaluates only defined conditions within a subset of WCAG success criteria and reached page states. This report combines multiple methods, but a clean run is **necessary, not sufficient** for conformance. The manual matrix and recorded limitations remain part of the evaluation.
