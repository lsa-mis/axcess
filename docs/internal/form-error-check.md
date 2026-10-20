# Form error check (WCAG 3.3.1 Error Identification)

Status: built, measured on synthetic pages, and wired into scans behind the
New scan switch "Check that forms describe their errors", **off by default**
until it is validated on real forms. Code: `src/audit/analyzer/forms/`.
Measurement: `tests/integration/test_form_error_identification.py`. Crawl:
`tests/integration/test_form_error_crawl.py`.

In a report each failing form is one occurrence of the issue "Form shows an
error without describing it in text" (WCAG 3.3.1, Level A), in the Not sure
lane, with the submit control as the control that revealed it ("After
clicking"). Stored in `page_a11y_findings` with `pipeline = 'forms'`
(migration 0032).

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
| All 130 scored cases, current code | 130 | 100% (0 false positives) | 93.8% | Mostly tuned against |

No form that must be skipped has ever been pressed. These are regression
evidence on synthetic pages, not a real-world accuracy estimate
(`DETECTION_EFFICACY.md`).

## To do

Ordered by what blocks using the check, then by expected value.

### 1. Before it runs in scans

- [ ] Validate on real forms: a sample of U-M public sites, labelled by at
      least two accessibility experts with disagreements settled, held out
      from tuning, with confidence intervals ("validation before promotion",
      AGENTS.md). Ship off by default until then.
- [ ] Decide the four ambiguous cases with an expert (all currently reported
      as `fail`): a "Required" hint that only turns red; a message only screen
      readers get; a placeholder that changes to "Required"; a message drawn
      as an image with alt text.
- [ ] Decide the policy for sign-in scans. The guard holds there too, but a
      signed-in session raises the stakes; the safest start is off for
      sign-in scans.
- [ ] Safety review of what the guard cannot block: writes over WebSockets
      already open, and GET requests with side effects.

### 2. Wiring it into Axcess

- [x] Run it in the crawl (`crawler/js_fetcher.py`), last on each page,
      behind a scan setting (off by default), with its own time budget.
- [x] Store results in `page_a11y_findings` with its own pipeline and rule
      id, the fields in error and the messages seen.
- [x] Report it: the check name "Form error check" in `lib/terms.ts`, an
      ordinary Issues row in the Not sure lane, a guidance card for 3.3.1 in
      `audit_report.yaml`.
- [ ] Screenshots before and after the press, for the occurrence.
- [ ] A "What was checked" row with its pages, skipped and not checked
      counts (needs scan-level counters, so a migration), the glossary, and
      `docs/reading-your-report.md`.
- [ ] Move 3.3.1 in `src/audit/rules/wcag_coverage.yaml` from `manual` to
      partly automated, and update `docs/coverage-tracker.md` ("Form errors
      and stateful criteria") and the public coverage page.
- [ ] Add the layer to `DETECTION_EFFICACY.md` and the detection-evals
      workflow (it needs a browser, so a separate job).

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
