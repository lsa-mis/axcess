# Accessibility audit — Scan #1


**Seed URL:** http://example.com/
**Pages crawled:** 2
**Detection methods used:** axe-core (deterministic DOM rules), image-of-text VLM, per-criterion LLM analyzer, dynamic keyboard-trap probe

## Executive summary

After self-critique, **6 open issue type(s)** need work (1 already-triaged item(s) moved to Appendix A; 1 best-practice item(s) to Appendix B).

Of those, **3 fail WCAG Level A** (the legal floor) and **2 fail Level AA** — Level A issues lock users out entirely and should be fixed first.

The biggest themes by reach are: *Images don't announce text to screen readers* (on 1 page); *Keyboard users can't escape this element* (on 1 page); *Text doesn't meet the 4.5:1 contrast ratio* (on 1 page).

**Highest-impact fix this team could ship this week:** *Images don't announce text to screen readers* — Critical, Under 15 minutes, 1 page(s).

Rough effort to clear what this tool can see: **3 quick win(s) (< 15 min each) · 2 medium item(s) (< 2 hr each)**.


## Conformance scorecard

Open issue types by WCAG conformance level (lower level = more urgent):

| Level | Open issue types | What it means |
|---|---:|---|
| **A** | 3 | Minimum bar. Failing locks users out — fix first. |
| **AA** | 2 | The legal/industry target in most jurisdictions. |
| **AAA** | 1 | Enhanced. Aspirational; fix after A and AA. |

By WCAG principle (the "POUR" model):

| Principle | Open issue types |
|---|---:|
| Perceivable | 4 |
| Operable | 2 |

## Who is affected

Each issue is tagged with the user groups it blocks. One issue can affect several groups, so these counts overlap.

| User group | Issue types affecting them | Across (page-instances) |
|---|---:|---:|
| Vision (blind / low-vision / color-blind) | 5 | 4 |
| Cognition (memory / attention / language) | 3 | 2 |
| Motor (keyboard-only / switch / tremor) | 1 | 1 |

## Coverage and method

This audit used multiple detection methods. Each sees different things; together they reach further than any one tool, but none of them replace a human reviewer.

| Method | Findings here? | What it checks | Confidence |
|---|---|---|---|
| **axe-core** | ✅ found issues | Contrast, missing alt/labels, ARIA misuse, landmark structure, heading order, link/button names, target size. | High — near-zero false positives; this is the industry baseline. |
| **Image-of-text VLM** | ✅ found issues | WCAG 1.4.5 (images of text) and whether the alt conveys the same information the image does. | Medium-high — the model occasionally over-flags decorative images; triage filters those. |
| **Per-criterion LLM analyzer** | ✅ found issues | Judgment calls automated tools miss — e.g. SC 2.4.4, whether a link's text actually describes where it goes. | Medium — semantic judgments are inherently fuzzier; treat as strong leads, confirm before mass edits. |
| **Dynamic keyboard-trap probe** | ✅ found issues | WCAG 2.1.2 — focus stuck on an element, modals that don't release on Escape, untitled tabbable iframes. | High for what it reaches — but only the initial DOM; interaction-triggered traps need manual testing. |
| **Responsive & zoom probe** | — | SC 1.4.10 reflow at 320px, SC 1.4.4 text clipping at 200% zoom, SC 1.4.12 clipping under user text-spacing. | High for reflow (deterministic geometry); medium for the clipping checks — designed truncation needs a human eye. |

_A “—” means this method produced no findings on this scan — it may have been disabled for the run, or it ran and found nothing. Only axe-core records a definitive ran-clean signal today._

_The next section breaks this down to every WCAG 2.2 A/AA success criterion — what was automated, what was AI-assisted, and the full list of what still needs manual testing._

## WCAG 2.2 A/AA coverage — what's automated vs. manual

Across all **55** Level A/AA success criteria, here is exactly what Axcess can and cannot determine for you. Automated coverage is high-confidence; AI-assisted findings are strong leads you should confirm; manual-only criteria are not detected by any pipeline.

| Coverage | Criteria | What it means |
|---|---:|---|
| **Automated** | 6 | A deterministic pipeline catches essentially all testable failures. |
| **Partly automated** | 15 | Automated checks catch the mechanical failures; the rest needs a human. |
| **AI-assisted** | 2 | A local model flags candidates — a human confirms before counting them. |
| **Manual only** | 32 | No automated detection — a human must test this criterion. |

### Automated &amp; AI-assisted (23 criteria)

| SC | Criterion | Lvl | Coverage | What Axcess does | Still verify by hand |
|---|---|---|---|---|---|
| 1.1.1 | Non-text Content | A | Partly automated | axe flags missing alt on img / area / input[type=image] and unlabelled SVGs; the image-of-text VLM separately flags pictures that are really text. | Whether the alt text that IS present is a meaningful equivalent — and the decorative-vs-informative call — needs a human. |
| 1.3.1 | Info and Relationships | A | Partly automated | axe checks list, table-header, definition-list, required-ARIA-children and heading-structure markup on the rendered DOM. | Relationships conveyed only visually (grouped fields, columns, emphasis that implies meaning) need a human to confirm they're also programmatic. |
| 1.3.5 | Identify Input Purpose | AA | Partly automated | axe validates that any autocomplete tokens used are valid. | Confirm autocomplete IS present on fields collecting the user's own info (name, email, address) — missing autocomplete isn't auto-detected. |
| 1.4.1 | Use of Color | A | Partly automated | axe flags links distinguished from surrounding text by colour alone (a narrow heuristic). | Most colour-only meaning — form errors, chart series, required-field markers, status — needs a human to confirm a non-colour cue exists. |
| 1.4.3 | Contrast (Minimum) | AA | Partly automated | axe measures text/background contrast on the rendered DOM against the 4.5:1 (3:1 large-text) thresholds. | Text baked into images, hover/focus/disabled states, and text over gradients or photos need a human to check. |
| 1.4.4 | Resize Text | AA | Automated | The responsive probe zooms to a 200% proxy viewport and flags text that clips or overflows its container. | Confirm no loss of content or function across the full zoom range in your target browsers. |
| 1.4.5 | Images of Text | AA | AI-assisted | OCR + a local vision model judge whether each image is really rendered text rather than a photo/diagram. | Confirm flagged images aren't the allowed exceptions (logos, or text that's essential to a particular presentation). |
| 1.4.10 | Reflow | AA | Automated | The responsive probe loads each page at 320 CSS px and flags horizontal scrolling / overflow. | Confirm no content or functionality is lost in the reflowed view (some loss can pass the geometry check but still fail in use). |
| 1.4.12 | Text Spacing | AA | Automated | The responsive probe injects the WCAG text-spacing override CSS (line-height 1.5, etc.) and flags clipping/overlap. | Confirm no text is cut off or overlapping with the spacing applied. |
| 2.1.1 | Keyboard | A | Partly automated | axe flags some keyboard-inaccessible patterns; the keyboard probe confirms focus can move through the page. | Confirm every control (menus, custom widgets, drag handles) is fully operable by keyboard — the deepest part of this SC is manual. |
| 2.1.2 | No Keyboard Trap | A | Automated | The keyboard probe tab-walks the page and tests Esc / iframe escape to detect focus traps. | Traps that only appear after interaction (a modal opened by a click) need a manual pass with the keyboard. |
| 2.4.1 | Bypass Blocks | A | Partly automated | axe checks for a skip link, landmark regions, and a heading structure that lets users bypass repeated content. | Confirm the skip link actually moves focus and works with the keyboard. |
| 2.4.2 | Page Titled | A | Automated | axe checks that every page has a non-empty <title>. | Confirm the title is descriptive and distinguishes the page (a light human check). |
| 2.4.4 | Link Purpose (In Context) | A | AI-assisted | axe flags empty/unnamed links; the semantic LLM judges whether the link text plus its context conveys where it goes. | Confirm the LLM's borderline calls ("read more", icon links) — it flags strong leads, not verdicts. |
| 2.4.6 | Headings and Labels | AA | Partly automated | axe flags empty headings and form controls missing a label. | Whether headings and labels are *descriptive* of their content is the core of this SC — an AI analyzer for it is in progress. |
| 2.4.7 | Focus Visible | AA | Partly automated | axe has limited checks for suppressed focus indicators. | Tab the whole page and confirm a clearly visible focus indicator on every interactive element — largely manual. |
| 2.5.3 | Label in Name | A | Partly automated | axe flags controls whose accessible name doesn't contain the visible label text (label-content-name-mismatch). | Confirm the visible text is fully contained in the accessible name for voice-control users. |
| 2.5.8 | Target Size (Minimum) | AA | Partly automated | axe checks interactive targets are at least 24x24 CSS px (with spacing). | Confirm the inline / essential / equivalent-control exceptions are genuinely met for any flagged small targets. |
| 3.1.1 | Language of Page | A | Automated | axe checks <html> has a present and valid lang attribute. | Confirm the declared language actually matches the page's main content. |
| 3.1.2 | Language of Parts | AA | Partly automated | axe validates lang attributes that are present on parts of the page. | Detecting foreign-language passages that are *missing* a lang attribute needs a human reader. |
| 3.3.2 | Labels or Instructions | A | Partly automated | axe checks that form controls have a programmatic label. | Whether the label + instructions are *sufficient* to know what to enter (format, required) needs judgement — an AI analyzer is on the roadmap. |
| 4.1.2 | Name, Role, Value | A | Partly automated | axe checks names/roles/values for standard controls and ARIA widgets (button-name, link-name, aria-* validity, roles). | Custom widgets' state changes (expanded, selected, checked) need a screen reader to confirm they're announced. |
| 4.1.3 | Status Messages | AA | Partly automated | axe checks for some live-region / role=status markup. | Confirm dynamic updates (added-to-cart, validation, search counts) are actually announced — needs screen-reader testing. |

### Needs manual testing (32 criteria)

No Axcess pipeline detects these — they require a human. Treat this as your manual-test checklist for full Level A/AA conformance.

| SC | Criterion | Lvl | What to test |
|---|---|---|---|
| 1.2.1 | Audio-only and Video-only (Prerecorded) | A | Confirm a text transcript exists for audio-only and an equivalent (transcript or audio track) for video-only. Transcript-presence analyzer is on the roadmap. |
| 1.2.2 | Captions (Prerecorded) | A | Play each video and confirm synchronized, accurate captions. Auto-caption diffing (Whisper) is on the roadmap. |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | A | Confirm an audio description or full text alternative for prerecorded video. |
| 1.2.4 | Captions (Live) | AA | Confirm live audio in synchronized media has real-time captions. |
| 1.2.5 | Audio Description (Prerecorded) | AA | Confirm prerecorded video has a synchronized audio description track. |
| 1.3.2 | Meaningful Sequence | A | Confirm the DOM/reading order matches the visual order (CSS can reorder content). A screenshot-vs-DOM VLM analyzer is on the roadmap. |
| 1.3.3 | Sensory Characteristics | A | Read instructions for reliance on shape/size/location/sound alone ("click the round button to the right") — judgement only a human can make. |
| 1.3.4 | Orientation | AA | Confirm content isn't locked to portrait or landscape (rotate the device / check for orientation-locking CSS). |
| 1.4.2 | Audio Control | A | Confirm any audio that plays automatically for >3s can be paused or muted. |
| 1.4.11 | Non-text Contrast | AA | Check that UI component boundaries (inputs, buttons, focus rings) and meaningful graphics meet 3:1. No reliable automated rule exists yet. |
| 1.4.13 | Content on Hover or Focus | AA | For tooltips/popovers triggered by hover/focus, confirm they're dismissable, hoverable, and persistent. |
| 2.1.4 | Character Key Shortcuts | A | If single-character shortcuts exist, confirm they can be turned off, remapped, or are active only on focus. |
| 2.2.1 | Timing Adjustable | A | For any time limit, confirm it can be turned off, adjusted, or extended. |
| 2.2.2 | Pause, Stop, Hide | A | Confirm moving/auto-updating content >5s can be paused/stopped/hidden. A motion-detection VLM analyzer is on the roadmap. |
| 2.3.1 | Three Flashes or Below Threshold | A | Confirm nothing flashes more than three times per second. Flash analysis is not implemented. |
| 2.4.3 | Focus Order | A | Tab through and confirm focus order matches the logical/visual order. A focus-order VLM+Playwright analyzer is on the roadmap. |
| 2.4.5 | Multiple Ways | AA | Confirm at least two ways to find pages (nav + search, or sitemap), except for steps in a process. |
| 2.4.11 | Focus Not Obscured (Minimum) | AA | Tab through and confirm the focused element isn't hidden behind sticky headers / cookie banners. A VLM+Playwright analyzer is on the roadmap. |
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
| 3.3.8 | Accessible Authentication (Minimum) | AA | Confirm login doesn't require a cognitive function test (puzzle, memorize) with no alternative. |

## Page hotspots

Pages carrying the most (and most severe) open findings. Fixing shared templates here clears issues across the rest of the site too.

| Page | Weighted load | Findings shown |
|---|---:|---:|
| http://example.com/ (Home) | 20 | 6 |

_Weighted load = sum of severity weights (Critical 4 · Serious 3 · Moderate 2 · Minor 1) for the sample locations shown per card._

## Remediation worklist by owner

The same findings, re-sliced by who fixes them. Hand each team their pack.

### Developers (2 item(s))

- [ ] **Keyboard users can't escape this element** — Critical, Under 2 hours, 1 page.
- [ ] **Elements must meet enhanced color contrast** — Serious, Effort: see fix steps, 1 page.

### Content editors (3 item(s))

- [ ] **Images don't announce text to screen readers** — Critical, Under 15 minutes, 1 page.
- [ ] **Images of text have no alt and can't be read** — Critical, Under 15 minutes, 0 pages.
- [ ] **Links don't describe their purpose (LLM-detected)** — Moderate, Under 15 minutes, 1 page.

### Designers (1 item(s))

- [ ] **Text doesn't meet the 4.5:1 contrast ratio** — Serious, Under 2 hours, 1 page.


## Issue cards

### 1. Images don't announce text to screen readers

**WCAG:** SC 1.1.1 Non-text Content — Level A

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- http://example.com/ (Home) → `main > img.banner` — Element has no alt attribute.

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

### 2. Keyboard users can't escape this element

**WCAG:** SC 2.1.2 No Keyboard Trap — Level A

**Detected by:** dynamic keyboard-trap probe.

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- http://example.com/ (Home) → `#modal-trap` — Focus stayed on #modal-trap after 5 consecutive Tab presses.

**What is happening:**

Our dynamic keyboard probe pressed Tab repeatedly on the live page and watched <code>document.activeElement</code>. Either focus got stuck on a single element across several consecutive Tab presses (a custom keydown handler swallowed Tab), an open modal dialog held focus inside itself even after Escape, or an iframe is reachable by Tab but has no <code>title</code> and no <code>tabindex="-1"</code> escape valve.

**Why it matters:**

Keyboard-only users — including people who use sip-and-puff, head-tracking, voice control, or simply mice with broken right buttons — can't interact with any content past a trap. Screen reader users hit the same wall when navigating in focus mode. WCAG 2.1.2 is Level A: the lowest possible bar. Failing this criterion functionally locks a portion of your users out of the page entirely.

**Affects:** Motor, Vision, Cognition.

**Severity:** Critical — Completely blocks an assistive-technology user from the affected content — no workaround.

**Effort:** Under 2 hours

**Owner:** Dev

**Fix (do this):**

1. For stuck-focus findings: open the page, find the element matching the reported selector, and look at any `keydown` / `keypress` handlers attached to it (or its parents). Find the `event.preventDefault()` call that runs on the Tab key. Either remove it or guard it with a check that lets Tab through (`if (e.key === 'Tab') return;`).
2. For modal-no-escape findings: add an `onKeyDown` handler on the dialog that closes it on `Escape`, OR move to the native `&lt;dialog&gt;` element (which gets this behavior for free). The fix is usually a one-line keyboard listener.
3. For iframe findings: set `title="..."` on the iframe so screen readers announce what the user is entering. If the embedded document doesn't need keyboard access, set `tabindex="-1"` on the iframe so keyboard users skip past it entirely.

**Verify it is fixed:**

- **Manual:** Open the page. Press Tab repeatedly from the top. Focus should visibly move through every interactive element and eventually reach the browser's address bar. Reverse with Shift+Tab. Open any modals and press Escape — focus should return to the element that opened the modal.
- **Automated:** Re-run the crawl with `--keyboard-probe` enabled. The same target should not produce a finding on the next pass.
- **Acceptance:** All affected elements allow keyboard focus to move past them via Tab (or Shift+Tab in reverse), and all modal dialogs release focus to the calling element when the user presses Escape.

**My confidence:** High.

_Rule docs: https://www.w3.org/WAI/WCAG21/Understanding/no-keyboard-trap.html_

### 3. Images of text have no alt and can't be read

**WCAG:** SC 1.4.5 Images of Text — Level AA

**Detected by:** image-of-text VLM.

**Where:** 1 finding(s) on **0** page(s).

Specific locations:
- http://example.com/ (Home) → image `http://example.com/banner.png` — above the fold; image #1 on the page

**What is happening:**

One or more images contain essential text (headlines, calls to action, signage) but have no alt attribute, or alt="" marking them decorative. Screen readers skip the content entirely.

**Why it matters:**

Blind and low-vision users get a broken version of the page — the headline is silently dropped. Additionally, image text can't be zoomed without pixelation, translated, or selected.

**Affects:** Vision, Cognition.

**Severity:** Critical — Completely blocks an assistive-technology user from the affected content — no workaround.

**Effort:** Under 15 minutes

**Owner:** Editor

**Fix (do this):**

1. Best path: replace the image with real HTML text styled in CSS so users can zoom, translate, and copy it.
2. Short-term fix: add an alt attribute matching the image's full visible text exactly.

**Verify it is fixed:**

- **Manual:** With a screen reader, tab to each affected image — it should announce the visible text verbatim. Better: see real HTML text in the DOM where the image used to be.
- **Automated:** Re-run the audit; finding moves to alt_adequacy=adequate or disappears.
- **Acceptance:** Each affected image either has alt text matching its visible text or has been replaced with semantic HTML text.

**My confidence:** High.

### 4. Text doesn't meet the 4.5:1 contrast ratio

**WCAG:** SC 1.4.3 Contrast (Minimum) — Level AA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- http://example.com/ (Home) → `p > span.muted` — Foreground/background contrast is 2.1.

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

### 5. Elements must meet enhanced color contrast

> ⚠ **Human review needed** — this finding doesn't have a templated fix in our rule book yet. The data is real; the prescriptive guidance below is light.

**WCAG:** SC 1.4.6 — Level AAA

**Detected by:** axe-core (deterministic DOM rules).

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- http://example.com/ (Home) → `p.subtle` — Contrast 6.1 — fails AAA threshold of 7.

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

### 6. Links don't describe their purpose (LLM-detected)

**WCAG:** SC 2.4.4 Link Purpose (In Context) — Level A

**Detected by:** per-criterion LLM analyzer.

**Where:** 1 finding(s) on **1** page(s).

Specific locations:
- http://example.com/ (Home) → `a.cta[ord=3]` — Link text 'click here' is not descriptive.

**What is happening:**

Our per-criterion language model reviewed every link on the page, together with up to five levels of ancestor context, and flagged cases where the link text — alone OR with its surrounding paragraph / heading / list-item — doesn't tell a user where the link goes. Common offenders: "click here", "read more", "details", raw URLs, and icon-only links with no aria-label.

**Why it matters:**

Screen-reader users pull up a list of every link on the page and jump between them. A link whose text is "click here" has no meaning out of context, so users either pick wrong or read the surrounding paragraph (an extra read step that ought not be necessary). This is one of the most-reported barriers in real accessibility audits.

**Affects:** Vision, Cognition.

**Severity:** Moderate — 1 finding(s) on 1 page(s).

**Effort:** Under 15 minutes

**Owner:** Editor

**Fix (do this):**

1. Rewrite link text so it names the destination. "Click here to download" becomes "Download the 2025 annual report (PDF)".
2. For icon-only links, add an `aria-label` that names the action — e.g. `aria-label="Search the catalog"`.
3. When the link wraps an image, give the image meaningful alt text describing the destination, not the picture.

**Verify it is fixed:**

- **Manual:** Run a screen reader's links-list view (VoiceOver: VO+U then Links; NVDA: K key). Every link should announce its destination clearly without needing the surrounding paragraph for context.
- **Automated:** Re-run a scan with semantic analyzers enabled — the same model shouldn't flag fixed links on the next pass. Watch for false positives that the model can't reliably distinguish (very long brand names, abbreviations).
- **Acceptance:** Every link on the affected pages tells a screen-reader user where it goes from its text alone, or from text + immediate heading / paragraph context.

**My confidence:** Medium.

_Rule docs: https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html_

## Appendix A — Findings dropped during self-critique

These issue types *were* detected but every finding in them has already been triaged (remediated, accepted as a risk, or marked a false positive). Listed here so the reader can confirm the self-critique didn't quietly hide a real bug.

| Method | Issue | WCAG | Reason set aside |
|---|---|---|---|
| axe | Form controls have no programmatic label | 4.1.2 | Already triaged: accepted_risk (1) |

## Appendix B — Out of scope but worth knowing

Best-practice findings (mostly from axe-core) that don't map to a specific WCAG success criterion. They catch real issues — missing landmarks, heading-order quirks — but they aren't WCAG fails in the strict sense. Worth tracking, not blocking.

- **Page should contain a level-one heading** (`page-has-heading-one`) — 1 finding(s) on 1 page.

---

**Scope note.** Automated tooling detects roughly 30-40% of WCAG 2.x AA success criteria. This report combines four methods (see *Coverage and method* above) to push past the usual axe-only ceiling, but a clean run is **necessary, not sufficient** for conformance. The criteria listed under *What we did not check* still require a human.