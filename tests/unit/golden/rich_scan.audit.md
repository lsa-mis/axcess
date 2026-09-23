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

**Highest-impact fix this team could ship this week:** *Images don't announce text to screen readers*, Critical, Under 15 minutes, 1 page(s).

Rough effort to clear what this tool can see: **3 quick win(s) (< 15 min each) · 1 medium item(s) (< 2 hr each)**.


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
| Vision (blind / low-vision / color-blind) | 4 | 5 |
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
| **Click-through DOM states** | ✅ found issues | Barriers that a page load never shows because the content only exists after a control is operated. Links are never clicked, and controls labelled sign out, delete, remove, or unsubscribe are refused. | Same deterministic rule evidence as a load-state pass, on states a load-state pass cannot reach. Coverage is bounded per page, so absence of a finding is not evidence that a state is clean. |
| **Visual (VLM) probe** | n/a | SC 1.3.2, content visually reordered by CSS so screen readers get a different, confusing sequence. | Medium, a vision-model judgement; treat as a lead and confirm. Only runs when a local vision model is available. |

_A “n/a” means this method produced no findings on this scan, it may have been disabled for the run, or it ran and found nothing. axe-core and Alfa record definitive ran-clean signals when selected._
_Alfa completed on 2 of 5 crawled page(s); its evidence is partial for this report._


### States behind a click

Click-through DOM state discovery operated 12 of 16 control(s) across 2 page(s), reaching 5 additional DOM state(s) that a page load alone does not show. 2 finding(s) in this report were visible only after a control was operated.

| Measure | Value |
|---|---|
| Pages probed | 2 |
| Controls found | 16 |
| Controls operated | 12 (75%) |
| Additional DOM states reached | 5 |
| Findings visible only after a click | 2 |
| Controls refused as destructive | 0 |

- 1 page(s) hit a bound before every control was operated, so their states are partially tested. They are listed below.
- Hover-only content, gestures, operating-system menus, closed shadow DOM, cross-origin embeds, and states with no observable DOM change are outside what this probe can reach and still require manual testing.
- Click-revealed findings are not yet compared across scans. If one is absent from a later report, confirm the fix directly, absence is not proof of repair.

**Pages where the sweep stopped early**

| Page | Controls operated | States | Why it stopped |
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
| 2.1.1 | Keyboard | A | Partly automated | axe flags some keyboard-inaccessible patterns; the keyboard probe confirms focus can move through the page. | Confirm every control (menus, custom widgets, drag handles) is fully operable by keyboard, the deepest part of this SC is manual. |
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

### Developers (39 item(s))

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
- [ ] **Elements must meet enhanced color contrast**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture: buttons [primary/secondary] need names?**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 05 synthetic check**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 13 synthetic check**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 17 synthetic check**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 25 synthetic check**, Serious, Effort: see fix steps, 1 page.
- [ ] **Fixture rule 29 synthetic check**, Serious, Effort: see fix steps, 1 page.
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
- [ ] **Alfa ACT rule, The image has no accessible name. [Stored evidence is unavailable.] (Alfa sia-r2)**, Moderate, Effort: see fix steps, 1 page.
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

- [ ] **Images don't announce text to screen readers**, Critical, Under 15 minutes, 1 page.
- [ ] **Links have no accessible name**, Serious, Under 15 minutes, 1 page.
- [ ] **Links don't describe their purpose (LLM-detected)**, Moderate, Under 15 minutes, 1 page.

### Designers (1 item(s))

- [ ] **Text doesn't meet the 4.5:1 contrast ratio**, Serious, Under 2 hours, 2 pages.


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

### 10. Images don't announce text to screen readers

**WCAG:** SC 1.1.1 Non-text Content, Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Image with class “banner”. **Technical target:** `main > img.banner`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

One or more <img> elements have no alt attribute (or have alt="" when the image is informative). Screen readers announce "image" with no context, so the information the image conveys is unreachable.

**Why it matters:**

Blind, low-vision, and screen-reader users get a broken version of the page, the image's content is silently dropped.

**Affects:** Vision.

**Severity:** Critical, Completely blocks an assistive-technology user from the affected content, no workaround.

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

### 11. Text doesn't meet the 4.5:1 contrast ratio

**WCAG:** SC 1.4.3 Contrast (Minimum), Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 3 finding(s) on **2** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** text element containing “low text” with class “muted”. **Technical target:** `p > span.muted`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [Home](<https://example.org/>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `footer small`. **Observed evidence:** Fix any of the following: the rule's check failed.
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `.details p`. **Seen after:** activating "Show more" on this page. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

Text falls below the WCAG 1.4.3 minimum contrast against its background (4.5:1 for body text; 3:1 for 18pt+ or 14pt-bold).

**Why it matters:**

Users with low vision, color blindness, or who view the site in bright sunlight can't read the text. This is one of the most commonly-reported barriers in user testing.

**Affects:** Vision.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Under 2 hours

**Owner:** Designer

**Fix (do this):**

1. Open the affected page in DevTools, inspect the failing element, and read its foreground and background colors.
2. Run the pair through WebAIM's Contrast Checker. Find a darker foreground (or lighter background) that clears 4.5:1.
3. Update the CSS custom property or design-system token, most contrast failures cascade from one token, so one change often fixes many findings at once.

**Verify it is fixed:**

- **Manual:** Open DevTools → Accessibility tab → Contrast ratio reading. Confirm ≥ 4.5:1 for body text, ≥ 3:1 for large text.
- **Automated:** axe-core color-contrast rule passes after the fix.
- **Acceptance:** All text on the affected pages clears 4.5:1 (body) or 3:1 (large) against its background, verified in DevTools or WebAIM.

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

### 15. Elements must meet enhanced color contrast

> ⚠ **Human review needed**, this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.4.6, Level AAA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [About us](<https://example.org/about>). **Location on page:** Affected element identified by the recorded page selector. **Technical target:** `p.subtle`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

1 finding(s) for Elements must meet enhanced color contrast across 1 page(s).

**Why it matters:**

Users relying on assistive technology hit a barrier here.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Human review needed, no templated fix for `axe:color-contrast-enhanced` in `rules/audit_report.yaml` yet. See the rule docs: https://dequeuniversity.com/rules/axe/4.10/color-contrast-enhanced

**My confidence:** Medium.

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

### 22. Links have no accessible name

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

One or more <a> elements have no visible text, no aria-label, and no aria-labelledby. Screen readers either skip them or announce "link" with no destination context.

**Why it matters:**

Screen reader users navigate by pulling up a list of links; an unnamed link is invisible in that list. Keyboard users also can't tell where the link goes from the focus indicator alone.

**Affects:** Vision, Cognition.

**Severity:** Serious, A real barrier for affected users, even if a workaround sometimes exists.

**Effort:** Under 15 minutes

**Owner:** Editor

**Fix (do this):**

1. If the link contains only an icon (e.g. a magnifier for search), add aria-label with a short description ("Search").
2. If the link wraps an <img>, ensure the image has a non-empty alt attribute that describes the link's destination.
3. Avoid "click here" and "read more", write text that describes the destination so users scanning a link list can decide.

**Verify it is fixed:**

- **Manual:** Tab through the affected page; the focus ring should land on each link with a descriptive announcement. Use a screen reader's link list (VoiceOver: VO+U then arrow to Links) to confirm every link has meaningful text.
- **Automated:** axe-core link-name rule passes after the fix.
- **Acceptance:** Every <a> on the affected pages has either visible text or an aria-label / aria-labelledby that describes the destination.

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

### 33. Alfa ACT rule, The image has no accessible name. [Stored evidence is unavailable.] (Alfa sia-r2)

> ⚠ **Human review needed**, Alfa ACT evidence is a review lead, not a conformance verdict. Confirm any `cantTell` outcome manually before reporting it as a barrier.

**WCAG:** SC 1.1.1, Level A

**Detected by:** Siteimprove Alfa (ACT rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Home](<https://example.org/>). **Location on page:** Element recorded in Alfa's structured target evidence. **Technical target:** `{"path":["html","body","img"]}`. **Observed evidence:** The image has no accessible name. [Stored evidence is unavailable.]

**What is happening:**

Siteimprove Alfa returned 1 failed ACT outcome(s) for this rule. WCAG 1.1.1; Alfa rule sia-r2. Observed diagnostic: The image has no accessible name. [Stored evidence is unavailable.]

**Why it matters:**

A failed ACT outcome is strong automated evidence, not a conformance verdict. Confirm that the rule applies and reproduce the barrier before presenting the row as a confirmed accessibility issue.

**Severity:** Moderate, 1 finding(s) on 1 page(s).

**Effort:** Effort: see fix steps

**Owner:** Dev

**Fix (do this):**

1. Open the linked page evidence and review the Alfa target and diagnostic.
2. Manually test the applicable WCAG success criterion with the relevant assistive technology.
3. Apply the correction, then rescan the same scope to verify the ACT outcome is resolved.

**My confidence:** Medium.

_Rule docs: https://alfa.siteimprove.com/rules/sia-r2_

### 34. Links don't describe their purpose (LLM-detected)

**WCAG:** SC 2.4.4 Link Purpose (In Context), Level A

**Detected by:** per-criterion LLM analyzer.

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- **Page:** [Contact](<https://example.org/contact>). **Location on page:** link containing “click here” with class “cta”. **Technical target:** `a.cta[ord=3]`. **Observed evidence:** Fix any of the following: the rule's check failed.

**What is happening:**

Our per-criterion language model reviewed every link on the page, together with up to five levels of ancestor context, and flagged cases where the link text, alone OR with its surrounding paragraph / heading / list-item, doesn't tell a user where the link goes. Common offenders: "click here", "read more", "details", raw URLs, and icon-only links with no aria-label.

**Why it matters:**

Screen-reader users pull up a list of every link on the page and jump between them. A link whose text is "click here" has no meaning out of context, so users either pick wrong or read the surrounding paragraph (an extra read step that ought not be necessary). This is one of the most-reported barriers in real accessibility audits.

**Affects:** Vision, Cognition.

**Severity:** Moderate, 1 finding(s) on 1 page(s).

**Effort:** Under 15 minutes

**Owner:** Editor

**Fix (do this):**

1. Rewrite link text so it names the destination. "Click here to download" becomes "Download the 2025 annual report (PDF)".
2. For icon-only links, add an `aria-label` that names the action, e.g. `aria-label="Search the catalog"`.
3. When the link wraps an image, give the image meaningful alt text describing the destination, not the picture.

**Verify it is fixed:**

- **Manual:** Run a screen reader's links-list view (VoiceOver: VO+U then Links; NVDA: K key). Every link should announce its destination clearly without needing the surrounding paragraph for context.
- **Automated:** Re-run a scan with semantic analyzers enabled, the same model shouldn't flag fixed links on the next pass. Watch for false positives that the model can't reliably distinguish (very long brand names, abbreviations).
- **Acceptance:** Every link on the affected pages tells a screen-reader user where it goes from its text alone, or from text + immediate heading / paragraph context.

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
| axe | Text doesn't meet the 4.5:1 contrast ratio | 1.4.3 | Triaged subset: false_positive (1) |
| axe | Form controls have no programmatic label | 4.1.2 | Already triaged: accepted_risk (1) |

## Appendix B, Review leads and informational evidence

These results are preserved for transparency but are not included in the remediation scorecard. They are AI-assisted or ambiguous review leads, informational/pass evidence, or best-practice observations with no criterion mapping. An expert decision is required before a review lead can be described as a barrier.

**Alfa note:** Alfa ACT evidence is a review lead when the engine returns `cantTell`; it is not a conformance failure until an expert reviews the stored evidence.

- **The page has no top-level heading** (`page-has-heading-one`), 3 finding(s) on 3 pages; **likely barrier / high confidence**. Deterministic axe-core rule failure; verify after remediation.
- **Top-level content isn't inside a landmark** (`region`), 2 finding(s) on 2 pages; **likely barrier / high confidence**. Deterministic axe-core rule failure; verify after remediation.
- **Images of text have no alt and can't be read** (`essential_missing`), 2 finding(s) on 2 pages; **expert review / medium confidence**. OCR/VLM-assisted image lead; confirm purpose and alternative in context.
- **Keyboard users can't escape this element** (`keyboard-trap-stuck`), 1 finding(s) on 1 page; **expert review / medium confidence**. Measured Tab and Shift+Tab exit attempts both remained on the same observable element; manually check for another documented exit command.
- **Links don't describe their purpose (LLM-detected)** (`2.4.4`), 2 finding(s) on 2 pages; **expert review / medium confidence**. AI-assisted semantic lead; confirm in page context.
- **Image (unclassified), inadequate alt** (`unclassified_inadequate`), 2 finding(s) on 2 pages; **expert review / low confidence**. Image analysis was inconclusive; classify manually before reporting a barrier.
- **Alfa ACT result, expert decision needed (Alfa sia-r111)** (`sia-r111:cant_tell`), 1 finding(s) on 1 page; **expert review / medium confidence**. Alfa returned 1 cantTell occurrence(s); this is not a failure. Alfa could not decide whether the target spacing is sufficient. [Stored evidence is unavailable.]
- **Image (unclassified), missing alt** (`unclassified_missing`), 1 finding(s) on 1 page; **expert review / low confidence**. Image analysis was inconclusive; classify manually before reporting a barrier.
- **Logo image, adequate alt** (`logo_adequate`), 1 finding(s) on 1 page; **informational / medium confidence**. Alt comparison appears adequate; retained as non-actionable evidence.

---

**Scope note.** Automated tooling evaluates only defined conditions within a subset of WCAG success criteria and reached page states. This report combines multiple methods, but a clean run is **necessary, not sufficient** for conformance. The manual matrix and recorded limitations remain part of the evaluation.
