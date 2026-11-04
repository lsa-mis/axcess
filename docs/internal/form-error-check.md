# Form error check (WCAG 3.3.1 Error Identification)

Status: built, measured on synthetic pages, and wired into scans behind the
New scan switch "Check that forms describe their errors", **on by default for
public websites** since 2026-11-02 (the developer's decision, after the safety
review below), never in sign-in scans, and off in "Scan again with faster
settings". It is not yet validated on real forms, so its results are Not
sure leads. Code: `src/audit/analyzer/forms/`.
Measurement: `tests/integration/test_form_error_identification.py`. Crawl:
`tests/integration/test_form_error_crawl.py`.

In a report each failing form is one occurrence of the issue "Form shows an
error without describing it in text" (WCAG 3.3.1, Level A), in the Not sure
lane, with the submit control as the control that revealed it ("After
clicking"). Stored in `page_a11y_findings` with `pipeline = 'forms'`
(migration 0034).

## What it does

SC 3.3.1 (Level A): "If an input error is automatically detected, the item
that is in error is identified and the error is described to the user in
text." The check presses each form's submit control once with nothing typed,
watches what the page does, and reports a form that detected an error without
identifying it and describing it in text.

Its priorities, in order: safety, precision, speed, recall.

1. **Safety, decided before any click** (`base.skip_reason`). Never pressed:
   sign-in and account forms (a password field), payment forms (card fields),
   forms with a CAPTCHA, search forms, sensitive actions (Delete, Pay, Donate,
   Unsubscribe, Sign out, and the rest of `SENSITIVE_WORDS`), forms with
   nothing empty, and forms with no submit control. Every other form is
   pressed inside Click-Through's network guard, which blocks every request
   that could change anything and every page navigation. The check never
   types, clears a value or presses Enter.
2. **Precision** (`base.classify`). "Fail" needs a field newly marked
   `aria-invalid="true"`, turned an error colour (red or orange) or given an
   error class, and no new visible text, in words, describing it. Text counts
   as a description when it is linked to the field (`aria-describedby`,
   `aria-errormessage`), beside the field with error wording or a marked
   field, or announced or in an error colour with error wording. A form that
   shows nothing is not a failure. A form that tried to send itself is "not
   checked", never pass or fail, because the server's answer is unknown.
3. **Speed.** One attempt per form, at most 5 per page, a form repeated across
   pages checked once per scan, about 1.4 s per form.

Outcomes: `fail`, `pass`, `native` (only the browser's own message),
`not_applicable`, `not_checked`, `skipped`.

## Measured results (synthetic pages)

| Batch | Scored | Precision | Recall | Honest? |
| --- | --- | --- | --- | --- |
| Independent (written without seeing the detector), before any change | 24 | 100% (8/8) | 80% (8/10) | **Yes** |
| Blind 1, before the fixes it led to | 14 | 75% | 60% | Was; now tuned against |
| Blind 2, before the fixes it led to | 14 | 83% | 83% | Was; now tuned against |
| Real pages: copies of the first real-page mistakes, before the fix | 4 | 25% (1 of 4 failures right) | 100% (1/1) | No: written to the bug |
| All 134 scored cases, current code | 134 | 100% (0 false positives) | 93.9% | Mostly tuned against |

No form that must be skipped has ever been pressed. These are regression
evidence on synthetic pages, not a real-world accuracy estimate
(`DETECTION_EFFICACY.md`).

## Real pages (2026-11-03)

Run by hand in a visible browser on 32 public pages (validation-library
demos, design-system docs, accessibility demos), one fresh browser context
per page as in a scan. Each verdict was checked against the before/after
screenshots by the developer's agent, not by an accessibility expert, so
this is a sanity check, not validation. Pages behind a Cloudflare check
were left out.

| Run | Fail | Pass | Browser's own message | Wrong verdicts |
| --- | --- | --- | --- | --- |
| First, 14 pages, code before the fixes below | 3 | 0 | 0 | All 3 fails (Bootstrap, Parsley) |
| 32 pages, after the fixes below | 0 | 25 | 4 | None found |
| Last, 54 pages (the 32, broken-on-purpose practice sites, Accessible University), current code | 2 | 28 | 5 | None found |

The first run's mistakes, and one found later on atlassian.design, each
became a "real pages" case (`r01` to `r04` in `form_error_cases.py`) that
fails on the old code:

- Text the page revealed (Bootstrap's hidden feedback) was thrown away
  when the same words were visible elsewhere on the page.
- A radio group's single message (Parsley) was judged per radio button.
- Hint text in other forms' live regions, past a 6000-element cap on the
  record of visible text, counted as this form's error message.

The same runs found three robustness bugs, each with its own test: form
locators that matched several forms (`path` now climbs until unique), a
change watcher that kept busy pages' main thread occupied past the 30 s
limit (`test_form_error_busy_page.py`), and a network guard that could be
left on, or hang, when that limit cancelled it
(`test_exploration_guard_cleanup.py`).

The two true failures are both Accessible University "before" pages
(washington.edu and its updated copy on openassessittoolkit.github.io):
a box inside the form says "Your form has errors. Please correct them and
resubmit." It names no field, and no field is marked. The check counts error
words alone only for text inside the form itself, and only strong ones
(error, invalid, incorrect, failed, problem, could not be sent), since hint
and thank-you text use the weak ones; `r05` copies the page and `r06` is
the decoy. Its fixed "after" page comes out as the browser's own message.

What the real pages show the check cannot do yet: two failures are far too
few to measure recall on real forms. Most forms on library demo pages are
skipped (sign-in, search, no submit control, nothing empty), and 12 were
"not checked" because the page sent the form to its server when pressed.
W3C's BAD "before" survey is one of those: it is checked only on the
server, so the check cannot see its red labels without sending the form.

## To do

Ordered by what blocks using the check, then by expected value.

### 1. Before it runs in scans

- [ ] Validate on real forms: a sample of U-M public sites, labelled by at
      least two accessibility experts with disagreements settled, held out
      from tuning, with confidence intervals ("validation before promotion",
      AGENTS.md). It shipped on by default for public scans before this, by
      the developer's decision (2026-11-02); validation decides whether its
      results can ever leave the Not sure lane.
- [ ] Decide the four ambiguous cases with an expert (all currently reported
      as `fail`): a "Required" hint that only turns red; a message only screen
      readers get; a placeholder that changes to "Required"; a message drawn
      as an image with alt text.
- [x] Decide the policy for sign-in scans (2026-11-02): never. New scan has
      no switch for it there, and the fetcher refuses it in a signed-in
      browser. Pressing submit while signed in could act as the person, even
      with every request blocked. Revisit only as an explicit opt-in for test
      accounts, after validation.
- [x] Safety review of what the guard cannot block (2026-11-02). Found: it
      let same-origin GET, HEAD and OPTIONS requests through, and it cannot
      see sockets, so a socket open before the press could send, and a new
      one could open. Closed for this check: the guard's strict mode blocks
      every request of the page while a form is pressed, reads included, and
      the probe holds WebSocket and RTCDataChannel sends, and new
      WebSockets, in every frame (`_HOLD_JS`). A send held or a write refused
      leaves the form "not checked". Proved by
      `tests/integration/test_form_error_guard.py`, which fails without the
      fix. Left open, and said in the code: a page that kept its own copy of
      a socket's `send` before the press, and channels the browser offers
      beyond those (WebTransport). Service workers were already blocked.

### 2. Wiring it into Axcess

- [x] Run it in the crawl (`crawler/js_fetcher.py`), last on each page,
      behind a scan setting (off by default), with its own time budget.
- [x] Store results in `page_a11y_findings` with its own pipeline and rule
      id, the fields in error and the messages seen.
- [x] Report it: the check name "Form error check" in `lib/terms.ts`, an
      ordinary Issues row in the Not sure lane, a guidance card for 3.3.1 in
      `audit_report.yaml`.
- [x] Screenshots before and after the press, for the occurrence: the form,
      outlined, in the page itself (not in a frame), when the scan keeps
      screenshots. The after picture is the finding's `screenshot_hash`, the
      before one `before_screenshot_hash` (migration 0035); the issue's
      screenshots page shows the pair, "Before" above "After".
- [x] A "What was checked" row with its pages, pressed, skipped and not
      checked counts (scan counters, migration 0036; older scans say
      coverage was not recorded).
- [x] The glossary ("Form error check", "Error identification") and
      `docs/reading-your-report.md` (its screenshots and its "What was
      checked" counts).
- [ ] Move 3.3.1 in `src/audit/rules/wcag_coverage.yaml` from `manual` to
      partly automated, and update `docs/coverage-tracker.md` ("Form errors
      and stateful criteria") and the public coverage page.
- [x] Add the layer to `DETECTION_EFFICACY.md` ("Form error check") and the
      detection-evals workflow (job `form-error-check`, with Chromium). The
      measurement now also gates recall at 80%, as every other layer is.

### 3. Recall gaps (known misses)

- [ ] A generic banner placed right after the last field ("A required field
      is missing.", independent case i07) is tied to that field by position
      and counts as identifying it. Do not tie generic text by position when
      the form has several fields.
- [ ] Fields inside web components' shadow DOM are not found. Search open
      shadow roots.
- [ ] Only the submit button reacts (turns red, shakes): deliberately not
      reported, for precision. Revisit only with real-world evidence.
- [ ] Forms submitted only with Enter, and multi-step forms (only the first
      step is checked; say so in the report).
- [ ] Server-side validation, where the error appears only after the request:
      possible only by letting an empty request through, so an explicit
      per-scan opt-in for staging sites, never by default.

### 4. Speed

- [ ] Wait until the page goes quiet instead of a fixed 1.2 s, with a ceiling,
      and measure on real pages.
- [ ] Measure the cost of reloading the page between forms on heavy pages.
