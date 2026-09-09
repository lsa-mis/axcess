# Testing mouse-only controls in Axcess

This report accompanies an experimental port of the keyboard study from
[`harryg02/a11y-crawler`](UPSTREAM.md). The question is practical: **when a mouse
can perform an action, can a keyboard user perform the same action?** The code
is an offline experiment on Axcess's `tabbing` branch. It is not connected to
normal scans.

The experiment is promising but incomplete. On the 95 frozen examples, the
historical reviewed behavior test found about 87% of the positive labels; adding
candidate discovery reduced this to about 77–78%. Some working keyboard paths
were falsely flagged and 20 targets per window remained unknown. The strongest
published upstream score was higher on its own smaller corpus. The useful
outcome here is a reproducible prototype, evidence about its failure modes, and
a clearer path to an Axcess probe.

## Why pressing Tab is only half the test

Consider a page with this control:

```html
<div tabindex="0" onclick="openReport()">Open report</div>
```

Tab can put focus on the `div`, but this code does not give it a keyboard
activation handler. A user can reach it and still be unable to open the report.
A native `<button>` supplies normal keyboard activation behavior, which makes
it a useful starting point for implementing this kind of control.

There are also legitimate alternatives. A clickable card might contain a normal
link that opens the same report. The whole card need not become a separate Tab
stop. The important question is whether the functionality is available through
the keyboard. That distinction follows [W3C's Keyboard guidance](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html).

Axcess already has a keyboard-trap probe. It asks whether focus gets stuck when
trying to leave a control. This experiment asks a different question: whether
the intended action can be performed in the first place. These checks are
complementary.

## What the published experiment established

The upstream author made nine test pages containing 60 labeled elements. Of
these, 26 were labeled as mouse-only violations and 34 as accessible controls,
decoys, or excluded elements. A *decoy* looks suspicious but does not establish
the target defect; for example, it might have button styling but no action.

The study compared methods based on HTML attributes, event listeners, appearance,
and actual browser interaction. Its strongest published configuration reported
26 correct detections, one false alarm, and no missed positive labels. On that
corpus, axe-core reported none of the 26 positive targets. This is a result for
that experiment's defect examples, not a claim that axe detects no keyboard
problems. [Published study and results](UPSTREAM.md#published-experiment)

The strongest result came from a *differential*: operate a control using a mouse,
operate it using a keyboard, and compare the observed effects. Effects included
changes to page content, layout, storage, requests, and navigation. A later step
looked for a keyboard-accessible control that supplied an equivalent action.

There is a crucial limit to its headline result: the differential was handed the
complete list of labeled targets. It did not have to discover those targets on
an arbitrary page. An excellent test of a supplied control can still miss many
defects if the search step never selects them.

## How we designed the Axcess experiment

Codex and Claude agreed on the question and methods through `LLMTalk` before
working separately. Codex prepared fixtures and expected answers; Claude
implemented the experimental detector and runner. Each agreed not to inspect
the other's implementation before the first score. Both could technically read
the shared filesystem, and both knew the upstream weaknesses. This reduces one
source of bias; it does not make the evaluation independent of the authors.

The corpus contains **95 targets on 19 pages**: the original 60 targets plus
35 new ones. The labels were frozen before scoring, with a SHA256 hash for each
input file. A SHA256 hash is a fingerprint of file contents: if a fixture or
answer changes, its fingerprint changes too.

We test two window sizes, **1280 × 900** and **390 × 844**, giving 190 target/window
combinations. The smaller window is a narrow desktop-browser layout test, not
proof of behavior on a phone, touchscreen, or screen reader. Three new labels
depend on the window size because the page hides or reveals controls.

Before freezing, Codex used an independent browser check to confirm that all 190
declared target appearances existed without page errors, and checked selected
keyboard paths, storage behavior, delayed actions, and responsive visibility.
This was fixture validation, not detector scoring.

The new examples test situations beyond straightforward clickable `div`s:

- Focus or key presses change a status message but do not perform the requested
  action.
- The same JavaScript function opens different reports depending on its input.
- A control writes to local storage only once.
- A working keyboard alternative disappears in a narrow layout.
- Arrow keys or a documented shortcut provide an alternative keyboard path.
- An action is delayed, appears inside a component or iframe, or sits beyond a
  long sequence of Tab stops.

All pages are checked-in local fixtures. Browser requests are intercepted and
fulfilled from those files or a simulated endpoint. The experiment does not need
a listening web server, external crawl, model, or access to completed scan data.

## Improvements being evaluated

The source review identified several reasons the upstream procedure could give
the wrong answer. The Axcess implementation addresses them as follows:

| Requirement | Why it matters |
| --- | --- |
| Fresh browser context for each input trial | Reloading a page leaves local storage and other state behind. The mouse trial could change what the keyboard trial sees. |
| Separate trials for separate keys | Enter may open a toggle and Space may close it. Combining them can hide the successful first action. |
| Take the keyboard baseline one Tab stop before the target | Earlier focus changes are excluded, while the target's own focus behavior can still open a working menu. |
| Compare effect contents | Opening report A and opening report B are both DOM changes, but they are different actions. |
| Restrict equivalent-control checks to the same page and window size | A button on an unrelated page, or hidden by a responsive layout, does not demonstrate a local working alternative. |
| Preserve uncertainty and complete denominators | Reaching a time or Tab limit is evidence that the experiment stopped, not that keyboard access is impossible. |

Playwright's isolated [browser contexts](https://playwright.dev/python/docs/browser-contexts)
provide separate cookies and browser storage for these trials. The source defects
motivating the requirements are documented in [the upstream references](UPSTREAM.md).

## Reading the measurements

An *oracle* score tests supplied targets. A *candidate-gated* score also requires
the candidate finder to select the target. The saved files call this second mode
`end_to_end`, but that name overstates what it measures: trials and equivalent
alternatives still come from the annotated list. Unannotated false alarms and
the cost of searching an arbitrary page are not measured. Candidate recall
measures how many positive targets the search step selects before confirmation.

- **True positive (TP):** a positive label receives a review lead.
- **False positive (FP):** a negative label receives a review lead.
- **False negative (FN):** a positive label receives no lead from a completed
  classification.
- **Unknown:** the experiment cannot support a classification within its
  observation limits. Unknown positives remain in the recall denominator.
- **Precision:** `TP / (TP + FP)`. Among the alerts, how many match positive labels?
- **Recall:** `TP / all positive labels`. How many expected defects were found?
- **F1:** the harmonic mean of precision and recall, useful as one summary but
  unable to explain the kinds of mistakes.

A high number on a small, synthetic test set does not establish real-world
accuracy. We report the original and new examples separately, retain first-run
results, and describe the actual errors rather than hiding them in an average.

## Results

### First run and subsequent experiments

The [first run](results/raw.json) is preserved. Only this run preceded release of
the no-reading agreement. All later fixes used examples that the implementer
could inspect, so their gains are exploratory and need a future untouched corpus.

| Cohort and mode | First desktop F1 | First narrow F1 | `diamond-fixes` desktop F1 | `diamond-fixes` narrow F1 |
| --- | ---: | ---: | ---: | ---: |
| Original 60, oracle | 90.6% | 90.6% | 92.3% | 92.3% |
| New 35, oracle | 71.4% | 75.0% | 76.9% | 80.0% |
| All 95, oracle | 84.0% | 84.7% | 87.2% | 87.8% |
| All 95, candidate-gated | 79.0% | 80.0% | 82.2% | 83.1% |

The historical [diamond-fixes run](results/diamond-fixes.raw.json) produced the
following counts. Unknown positive labels are included in recall, even though
they are listed separately from FN.

| Window / mode | TP | FP | FN | TN | Unknown positive / negative | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Desktop / oracle | 34 | 5 | 2 | 34 | 3 / 17 | 87.2% | 87.2% | 87.2% |
| Desktop / candidate-gated | 30 | 4 | 6 | 35 | 3 / 17 | 88.2% | 76.9% | 82.2% |
| Narrow / oracle | 36 | 5 | 2 | 32 | 3 / 17 | 87.8% | 87.8% | 87.8% |
| Narrow / candidate-gated | 32 | 4 | 6 | 33 | 3 / 17 | 88.9% | 78.0% | 83.1% |

For example, the desktop oracle raised 39 alerts: 34 matched positive labels and
five were false alarms, giving `34/39 = 87.2%` precision. There were also 39
positive labels; two received no lead and three were unknown, giving the same
`34/39` recall for a different reason. Only 75 of 95 targets received a supported
classification. An unknown is not a successful negative result.

Candidate discovery selected 32/39 positive targets on desktop (**82.0%**) and
34/41 in the narrow window (**82.9%**). This limits achievable candidate-gated
recall. Examples missed by discovery include a plain paragraph with a click
listener (`h120`) and one using event delegation (`h121`). Both lack the visual
or markup hints the finder uses. The finder also omits some plain native controls;
that can prevent finding useful keyboard alternatives in a future real scan.

Not every change helped. Scrolling offscreen targets into view improved aiming,
but the first `edge-fixes` run introduced false alarms when scroll changed
viewport-relative geometry. Narrow-window oracle F1 fell from **84.7% to 80.9%**.
Using document-relative coordinates in `edge-fixes-v2` raised it to **85.7%**.
Keeping both runs makes this regression visible. Higher later F1 also did not
mean greater coverage: classified desktop targets fell from 78/95 in the first
run to 75/95 in `diamond-fixes`.

### Comparing detector ideas

The [reviewed twelve-method comparison](fixtures/results/bakeoff-fixtures-reviewed.json)
runs on the same 95 frozen targets, at the desktop size only. These are Axcess
reimplementations of upstream-inspired ideas, with method differences described
below. Percentages use all positive labels as the recall denominator.

| Method | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| D9 mouse/keyboard effects plus equivalent alternative | 87.2% | 87.2% | 87.2% |
| D10a JavaScript ran for mouse, none for keyboard | 57.1% | 82.0% | 67.4% |
| D4 CSS appearance and text hints | 56.2% | 69.2% | 62.1% |
| D5 browser-debugger event listeners | 58.1% | 64.1% | 61.0% |
| D8 changes after hover | 75.0% | 46.2% | 57.1% |
| D6 intercepted listener registration | 53.8% | 53.8% | 53.8% |
| D2b JavaScript `onclick` property | 100.0% | 10.3% | 18.6% |
| D7 React event-handler properties | 100.0% | 5.1% | 9.8% |
| D3 tabindex / ARIA hints | 50.0% | 5.1% | 9.3% |
| D2 inline event attribute | 100.0% | 2.6% | 5.0% |
| D0 approximation of existing clickable collection | 50.0% | 2.6% | 4.9% |
| D1 selected keyboard-related axe rules | 0.0% | 0.0% | — |

A dash follows the saved scorer's undefined-F1 convention when both precision
and recall are zero. D1 emitted one false alarm (`p80`) and found none of the
39 positive labels. A separate `D1x` diagnostic credits unrelated axe rules to
these targets; it is deliberately unsound and is excluded from this comparison.
D0 approximates a discovery heuristic, not Axcess's complete normal scan pipeline.

On these examples, behavioral comparison gives the strongest balance. Cheap
markup checks can have perfect precision while missing almost every defect.
D10a raises 56 alerts to reach 32 of the 39 positive labels, so more than two
in five of its alerts are false: executing JavaScript is not the same as
performing a useful action. The ranking describes this corpus and
implementation, not every website.

These are the reviewed figures. The superseded
[legacy matrix](fixtures/results/bakeoff-fixtures.json) is kept for comparison
and differs in two rows: it recorded D10a as `D10` before the name was made
specific, at 52.2% / 89.7% / 66.0%, and D6 at 53.7% / 56.4% / 55.0%. The other
ten methods scored identically in both. The legacy file was written before the
runner recorded provenance, so only the reviewed file carries the fingerprints
and validity flag described below; where the two disagree, the reviewed file is
the measurement of record.

**We did not reproduce upstream's strongest Stage-4 filter.** Upstream compared
sets of executed V8 functions, using exact equality plus matching effect-channel
sets. Axcess instead compares effect signatures and restricts alternatives to the
same page and window size. The main experiment uses no V8 coverage by default; the
matrix's D10a collects it for a different test. Optional coverage strategies in
the source are unscored prototypes. The structural strategy abstains because
records do not include actual DOM containment. Neither function identity nor our
lossy signatures prove semantic equivalence. Upstream's **98.1% F1** and our
**92.3% F1 on its original 60 cases** belong to different procedures. The port
improves aspects of the method but does not beat that published headline result.

### What the errors teach us

The `diamond-fixes` results illustrate why a review lead needs human checking:

- `h103` has a working custom keyboard toggle, but focus and activation effects
  make its signature differ. It is a false alarm.
- `h171` uses a roving menu with ArrowRight; `h172` has a documented Alt+K
  shortcut. The trial tries Tab plus Enter, Space, and ArrowDown, so it incorrectly
  flags these working alternatives.
- `h160` changes content inside an open shadow root. The top-document snapshot
  misses that internal change and produces no lead for a positive label.
- `h180` waits 700 ms before acting; the default observation window is 250 ms.
  A short observation can miss a real action.
- Closed-shadow targets (`p91`, `h164`) and iframe targets (`p92`, `p94`, `h162`,
  `h163`) are unresolved. They remain unknown, including three positive labels.
- `p33` is counted as a false alarm against an inherited tooltip label whose
  interpretation is debatable. A benchmark label is not a standards ruling.

Ten further targets per window were recorded as not rendered or not reachable
by the sampled mouse points. Four produced instrumentation errors. Together
with the six unresolved targets, that explains the historical 20 unknowns.
The outer runner's empty `errors` list did not mean all measurements succeeded.
The reviewed runs still have twenty, but split 14 / 0 / 6: those four
instrumentation errors were the harness mis-reporting a zero-sized element, and
are described under *Final reviewed run and reproducibility* below.

### Supplemental stress tests

Claude also authored [seven development pages](edgecases/truth.json) with 60
labeled targets, including 28 positive labels. They cover a 1 × 1 pixel control,
a below-fold target, a scroll container, a wrapped inline target, transparent
occlusion, alternative key handlers, non-DOM effects, and delayed actions. One
page places a defect after 120 normal buttons; another target sits 150 wrappers
deep. Those 120 background buttons are not additional scored negatives.

The saved development run exercised useful mechanics: the behavioral test found
the tiny, distant, scrolling, wrapped, and deeply nested click-only targets. It
accepted Space-only and keyup-only controls, and flagged a focusable control that
could not activate and one whose keyboard action did the wrong thing. It missed
a double-click-only action and a 600 ms delayed action, showing the limits of
single-click input and the 250 ms observation window.

These are development tests, not an unbiased accuracy evaluation: the same
author wrote the fixtures and detectors and used these results while debugging.
Giving every method the same pages helps compare individual observations but
does not remove selection bias or establish a general ranking. Tiny-target
operability here also does not assess the separate WCAG target-size criterion.

### Review of the evidence format

Review found problems worth fixing even when they did not improve F1: failed
probes could disappear from scoring; saved individual verdicts preceded the
alternative-control filter while score tables followed it; and browser version
and start-time fields were inaccurate. All five historical main runs remain
untouched, and the two reviewed runs were added beside them rather than over
them, so seven are now saved.
The legacy matrix files were updated in place during development; their earlier
versions are not retained. New runs use unique labels and refuse overwrites.
The old main runs' post-filter oracle scores were independently reconstructed
from per-key effects, but candidate lists were not saved well enough to
independently rebuild all candidate-gated negative classifications.

The final runner verifies source fingerprints before import, before measurement,
and after measurement; it also rechecks the frozen inputs afterward. If those
checks disagree, the run is marked invalid and publishes no scores. Failed
pages, failed candidate searches, and omitted measurements remain represented
as unknowns. New schema-2 artifacts save the final verdicts for both scoring
modes, per-key observations, candidate lists, and page/window-specific dismissals.
There is no invented effect formed by combining parts of different key trials.

### Final reviewed run and reproducibility

Two full runs of the frozen experiment were measured against the reviewed
source: [`reviewed`](results/reviewed.raw.json), started 13:14 UTC, and
[`reviewed-repeat`](results/reviewed-repeat.raw.json), started 20:08 UTC the
same day. Both report the same corpus fingerprint `763e0495…`, the same
detector fingerprint `c897005148…`, zero errors, and `valid: true`. Wall times
were 315.9 s and 319.4 s.

The repeat reproduces the reviewed run exactly:

| compared | records | differences |
| --- | ---: | ---: |
| Oracle verdicts | 190 | 0 |
| Candidate-gated verdicts | 190 | 0 |
| Candidate lists per page/window | 38 | 0 |
| Equivalence dismissals | 7 | 0 |
| Tab orders | 38 | 0 |

**One instability was found, and it is the disclosed one.** Two of the 190
saved probe records differ between the runs, both `p61`, and both only in a
stored value: the page writes `local:set:p61=<epoch ms>`, so the payload
carries a timestamp that necessarily changes. This is the cost of the decision
recorded in `channels.py` not to normalize digit runs — collapsing them would
absorb order numbers and record ids along with clocks. Here it changed nothing:
`p61` is not in the tab order, so its verdict follows from reachability and the
payload never enters a comparison. But the mechanism is real. Had the same
element been focusable, the mouse and keyboard trials would have written
different timestamps, the effects would not have matched, and a working control
would have been reported as a defect. It is the only such payload the two runs
exposed: every other one of the 190 records was byte-identical across them.

**Method improvements are not accuracy improvements, and this run separates
them.** The reviewed scores are identical — cell for cell — to `diamond-fixes`
and `audit-fixes`:

| run | source state | desktop oracle F1 | mobile oracle F1 | desktop gated F1 | mobile gated F1 |
| --- | --- | ---: | ---: | ---: | ---: |
| `diamond-fixes` | pre-review | 87.2% | 87.8% | 82.2% | 83.1% |
| `audit-fixes` | audit applied | 87.2% | 87.8% | 82.2% | 83.1% |
| `reviewed` | reviewed and frozen | 87.2% | 87.8% | 82.2% | 83.1% |
| `reviewed-repeat` | unchanged | 87.2% | 87.8% | 82.2% | 83.1% |

Everything the review corrected — probes that could vanish from the
denominator, saved verdicts that disagreed with the scores computed from them,
inaccurate browser and start-time fields, effects assembled from parts of
different key trials — changed **no score on this corpus**. That is the
honest reading, and it cuts both ways. These were defects in the evidence, not
in the detector: they governed whether a published number could be trusted and
audited, not what the number was. A corpus that happened not to exercise them
cannot show a gain, and the absence of a gain is not evidence the fixes were
unnecessary. It does mean none of the accuracy figures in this report should be
attributed to them.

**The measured gaps are unchanged**, which is expected given identical
verdicts, and they remain the four described in *What the errors teach us*:
documented keyboard shortcuts and roving-menu keys the trial never tries
(`h171`, `h172`); actions slower than the 250 ms observation window (`h180` at
700 ms); iframe targets (`p92`, `p94`, `h162`, `h163`); and shadow-root
internals, both content changes the top-document snapshot misses (`h160`) and
closed roots that cannot be resolved at all (`p91`, `h164`). Twenty targets per
window remain undecided. These are limits of what was tried and observed, not
findings about the pages.

**The composition of those twenty did change, and it is the one review fix with
a visible effect.** Earlier runs split them 10 not-rendered / 4
instrument-error / 6 unresolved; the reviewed runs split them 14 / 0 / 6. Eight
records moved from `instrument_error` to `not_rendered` and now carry a cause,
*not mouse-operable: display:none, zero-size*: `p26i`, `p73` and `p74` in both
windows, plus `h142` on desktop and `h141` on mobile, the two whose labels are
themselves viewport-dependent. A zero-sized element yields no client
rects, so the locator had no point to aim at, dereferenced the empty list and
threw; the failure was recorded as an internal fault indistinguishable from a
browser problem. The element was simply not rendered. The count is unchanged
and no score moves, because an undecided probe stays undecided either way — but
four probes per window stopped blaming the instrument for the page's own
markup. That is the difference between a number that is right and a number that
can be read.


## Limits of the evidence

The original labels are preserved for reference comparisons, including a
debatable tooltip label and a console-only action. Their interpretations are
explained in [UPSTREAM.md](UPSTREAM.md#label-caveats). Matching those labels is
not the same as settling a WCAG judgment.

Effect signatures are deliberately limited observations: DOM and geometry use
compact hashes; canvas records operation counts rather than pixels; network
records URLs rather than response meaning. Inner frame and shadow-root DOM state
is not fully captured. Equal signatures can hide different outcomes, while
random IDs or timing can make equivalent outcomes look different. The historical
`diamond-fixes` run also normalized long numbers and hex strings, which could
erase meaningful differences such as report IDs. Its results remain historical
evidence of that particular implementation.

The new labels were authored separately from the detector, but the authors had
already discussed likely failure modes. We used one browser engine and two
window sizes, with a finite observation period and a finite number of inputs.
Documented shortcuts, composite widgets, asynchronous applications, or other
starting states can require paths the experiment never tries. A human must
confirm the missing functionality and whether another keyboard path exists.

The experimental code does not change Axcess's SQLite evidence, issue grouping,
normal scans, or UI. A future production port would need a deliberate action
policy, protected-page data handling, report-scoped evidence, and coverage
reporting. The measured result should determine which parts are ready for that
next step.

## How to bring this into normal Axcess scans

The reusable part is the isolated browser experiment in
[`src/audit/analyzer/keyboard/kbdiff`](../../src/audit/analyzer/keyboard/kbdiff/).
It is a useful prototype for a keyboard-operability probe; the results do not yet
justify enabling it in every scan.

A practical next implementation should first improve candidate discovery and
observation of components and frames, then test richer keyboard paths and repeat
trials to detect unstable effects. Evaluate those changes on newly authored,
untouched examples and representative permitted websites. Report candidate
coverage and unknown reasons alongside precision and recall.

When integrating, use Axcess's existing probe pipeline and store each lead under
its `scan_id`, with a target reference, attempted actions, observed effects,
uncertainty, and supporting screenshots. Keep keyboard-operability leads distinct
from the existing keyboard-trap check. Active clicks can change application
state, so choose the permitted actions deliberately before adding this to real
site scans. A human should confirm the missing keyboard functionality before
turning an experimental lead into a remediation conclusion.
