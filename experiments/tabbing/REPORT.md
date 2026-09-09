# Testing mouse-only controls in Axcess

This report accompanies an experimental port of the keyboard study from
[`harryg02/a11y-crawler`](UPSTREAM.md). It asks one practical question:
**when a mouse can perform an action, can a keyboard user perform the same
action?**

The code is an offline experiment on Axcess's `tabbing` branch. It is not
connected to normal scans, and nothing here runs during a real audit.

**What we found.** On 95 frozen examples the detector found about 87% of the
labelled defects when it was handed the list of targets, and about 77-78% when
an alert also required candidate discovery. Both scores use annotated targets;
they do not measure a complete site scan. It raised some false alarms on controls
that do work by keyboard, and it could not decide 20 of the 95 targets per window size.
The strongest published upstream number is higher, on its own smaller corpus and
by a different procedure. The useful outcome is not the score: it is a
reproducible prototype, a documented set of failure modes, and a clear list of
what to fix before this becomes a real Axcess probe.

**Who this is for.** It assumes you can read HTML and JavaScript and have seen a
browser automation tool, but it explains the accessibility and measurement ideas
as it goes. Every number links to the saved file it came from.

---

## 1. Why pressing Tab is only half the test

Consider this control:

```html
<div tabindex="0" onclick="openReport()">Open report</div>
```

`tabindex="0"` puts the `div` in the **tab order**, the sequence of elements you
move through by pressing Tab. So a keyboard user can reach it. But adding
`tabindex` and `onclick` does not give this `div` Enter or Space activation.
Reaching a control and being able to *use* it are different things, and this
element passes the first test while failing the second. Start with a native
`<button>` for an action or an `<a href="...">` for navigation; both provide
built-in keyboard activation.

The opposite mistake matters too. A clickable card might contain an ordinary
link that opens the same report. The card itself does not need to be a separate
tab stop, because the functionality is already available from the keyboard. The
question is never "is this specific element focusable" but "can the user get
this done", which follows
[W3C's Keyboard guidance](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html).

Axcess already has a keyboard-*trap* probe, which asks whether focus gets stuck
and cannot leave a control. This experiment asks whether the action can be
performed at all. The two checks are complementary.

## 2. What the published experiment established

The upstream author built nine test pages holding 60 labelled elements: 26
labelled mouse-only violations and 34 negatives. The negatives include *decoys*,
which look suspicious but are not defects - something styled like a button that
genuinely does nothing is not a keyboard bug.

That study compared detection methods based on HTML attributes, event listeners,
appearance, and real browser interaction. Its strongest published configuration
reported 26 true positives, one false positive and no false negatives - 96.3%
precision and 100% recall. On that corpus, axe-core flagged none of the 26. That
is a statement about those particular defect examples, not a claim that axe
misses keyboard problems generally.
[Published study and results](UPSTREAM.md#published-experiment)

The winning idea was a **differential**: perform the action with the mouse,
perform it with the keyboard, and compare what changed. A later stage looked for
a keyboard-reachable control that produced an equivalent effect.

**One limit shapes everything below.** That differential was handed the complete
list of labelled targets. It never had to find them on a page it had not seen. A
detector can be excellent at judging a control it is given and still miss most
defects on a real page, because the search step never proposed them.

## 3. How this experiment was designed

Two agents, Codex and Claude, agreed the question and the method in a shared log
before working separately. Codex wrote the fixtures and the answer key; Claude
wrote the detector and the runner. They agreed not to inspect each other's
work before the first score.

Be precise about what that buys. Both could read the same filesystem, and both
had studied the same upstream weaknesses beforehand. The agreement reduced the
opportunity to tune the detector to individual new fixtures before the first
score. It does not make the evaluation independent of its authors, and no number
here should be read as if it were.

**The corpus** is [95 targets across 19 pages](fixtures/truth.json): the
original 60, plus 35 new ones. Labels were frozen before scoring, with a SHA256
hash recorded for every input file. A SHA256 hash is a fingerprint of a file's
contents - change one byte and the fingerprint changes - so the runner can prove
the fixtures and answers were not edited to fit the results.

**Two window sizes**, 1280 x 900 and 390 x 844, give 190 target/window
combinations. The narrow size is a narrow *desktop browser* layout. It is not
evidence about phones, touchscreens or screen readers. Exactly three labels
differ between the two sizes, because those pages hide or reveal controls
responsively: `h140`, `h141` and `h142`.

Before freezing, Codex independently confirmed in a browser that all 190
declared target appearances existed without page errors, and spot-checked
keyboard paths, storage behaviour, delayed actions and responsive visibility.
That was fixture validation, not detector scoring.

The 35 new examples deliberately go past the easy clickable `div`:

- focus or a keypress changes a status message but does not perform the action;
- one JavaScript function opens different reports depending on its argument;
- a control writes to local storage only the first time;
- a working keyboard alternative disappears in the narrow layout;
- arrow keys or a documented shortcut provide the real keyboard path;
- the action is delayed, or lives inside a component or an iframe, or sits past
  a long run of tab stops.

Every page is a checked-in local fixture. Browser requests are intercepted and
served from those files or from a simulated endpoint, so the experiment needs no
web server, no crawl, no model and no access to real scan data.

## 4. How the detector works

For one target, in one window size, the runner:

1. loads the page in a fresh browser context and records a snapshot;
2. clicks the target with the mouse and records what changed;
3. throws that whole context away;
4. loads the page again, Tabs to the target, presses **one** key, and records
   what changed;
5. repeats step 4 for each key, each in its own fresh context.

If the mouse produced an effect and no key reproduced *the same* effect, that is
a lead. Effects are observed on seven channels: DOM, geometry, storage, network,
console, canvas and navigation.

Five departures from the upstream implementation, each fixing a defect located
in its source:

| Requirement | The bug it prevents |
| --- | --- |
| A fresh browser context per trial | Upstream reloaded one page, so `localStorage` written by the mouse survived into the keyboard run. A write that only happens once then produced no keyboard effect and scored as a false violation. |
| One key per trial | Enter opens a menu, Space closes it. Pressed in sequence against one page they net to "nothing happened", and a working control is reported as broken. |
| Baseline taken one tab stop before the target | Snapshotting before the whole Tab walk blames the target for every focus side effect of every element passed on the way. Snapshotting after focus lands hides the target's own focus-triggered reveal, which would condemn a `:focus-within` menu that works. |
| Compare effect *contents*, not just channels | Opening report A and opening report B are both "the DOM changed". Upstream asked whether any channel changed, so an unrelated console warning during the keyboard trial could clear a real defect. |
| Same page and window size for equivalence | A button on another page, or one hidden by the responsive layout, does not demonstrate that *this* user can do the job here. |

Playwright's isolated [browser contexts](https://playwright.dev/python/docs/browser-contexts)
give each trial its own cookies and storage.

**A sixth rule governs the scoring.** `unknown` is a real verdict, not a
rounding of "pass" or "fail". If the runner hits its Tab budget, cannot resolve
a target, or the element is not rendered, it says so. Upstream folded "could not
reach it" into "not keyboard reachable", which converts a measurement failure
into a defect. Recall here is deliberately strict: undecided targets that were
really defects stay in the denominator, so a detector can never raise its score
by refusing to answer.

## 5. How to read the numbers

Two scoring modes, from the same measurements:

- **oracle** - the detector is handed the labelled targets. Upstream also used
  supplied targets, although its best configuration uses a different procedure.
- **candidate-gated** - the target must first be proposed by the candidate
  finder, i.e. what a scanner could locate on an unfamiliar page. The saved
  files call this `end_to_end`, which overstates it: the trials and the
  equivalence check still come from the annotated list, so the cost of searching
  a real page and any false alarms on unlabelled elements are *not* measured.

The gap measures the loss from requiring discovery of those annotated targets.
Throughout the score tables, a "defect" means a positive benchmark label; it is
not a confirmed WCAG judgment.

- **True positive (TP)** - a real defect gets a lead.
- **False positive (FP)** - a negative gets a lead.
- **False negative (FN)** - a real defect gets no lead, from a completed test.
- **True negative (TN)** - a negative gets no lead, from a completed test.
- **Unknown** - the run could not decide within its limits. Unknown positives
  stay in the recall denominator.
- **Precision** = `TP / (TP + FP)`. Of the alerts raised, how many were real?
- **Recall** = `TP / all real defects`. Of the real defects, how many were found?
- **F1** - the harmonic mean of the two. One convenient number that cannot tell
  you *which kind* of mistake was made.

A high score on a small synthetic corpus does not establish real-world accuracy.
So the original and new examples are reported separately, every main run is kept
including the ones that got worse, and the individual errors are described
rather than averaged away.

---

## 6. Results

### 6.1 The headline

From the reviewed run, [`reviewed.raw.json`](results/reviewed.raw.json):

| Window / mode | TP | FP | FN | TN | Unknown pos / neg | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Desktop / oracle | 34 | 5 | 2 | 34 | 3 / 17 | 87.2% | 87.2% | 87.2% |
| Desktop / candidate-gated | 30 | 4 | 6 | 35 | 3 / 17 | 88.2% | 76.9% | 82.2% |
| Narrow / oracle | 36 | 5 | 2 | 32 | 3 / 17 | 87.8% | 87.8% | 87.8% |
| Narrow / candidate-gated | 32 | 4 | 6 | 33 | 3 / 17 | 88.9% | 78.0% | 83.1% |

Worked example, desktop oracle. The detector raised 39 alerts; 34 matched positive
labels, so precision is `34/39 = 87.2%`. There were also 39 positive labels; two
got no lead and three were undecided, so recall is `34/39` as well - the same fraction for a
different reason. Only 75 of the 95 targets got a supported classification, so
coverage is `75/95 = 78.9%`. **An unknown is not a pass.**

Split by cohort, the original examples score higher than the new ones:

| Cohort | Window | Oracle F1 | Candidate-gated F1 |
| --- | --- | ---: | ---: |
| Original 60 | desktop | 92.3% | 89.8% |
| Original 60 | narrow | 92.3% | 89.8% |
| New 35 | desktop | 76.9% | 66.7% |
| New 35 | narrow | 80.0% | 71.4% |

That gap is the point of writing new examples. The upstream pages were the ones
the method was designed against; the new ones are harder and were written
without seeing the detector.

### 6.2 The ceiling: candidate discovery

The oracle cannot confirm a defect it is never handed. The candidate finder
proposed **32 of 39** real defects on desktop (**82.1%**) and **34 of 41** in the
narrow window (**82.9%**). That is a hard ceiling on candidate-gated recall.

Among the misses: a plain paragraph carrying a click listener (`h120`), and one
that works through event delegation (`h121`). Neither has the visual or markup
hints the finder looks for. The finder also skips some ordinary native controls,
which in a real scan would also cost it the ability to spot a working keyboard
*alternative*.

> **A note on rounding.** `32/39` is 82.051...%, which is **82.1%** to one
> decimal. The older `diamond-fixes` and `audit-fixes` files display 82.0%
> because they rounded the stored 4-decimal value a second time. The reviewed
> runs compute the percentage from the counts and print 82.1%.
> Coverage has a similar display issue: saved tables show 79.0%, but rounding
> `75/95` directly gives **78.9%**. The first run's desktop candidate-gated F1
> also rounds directly to **78.9%**, rather than its saved display of 79.0%.
> This report computes percentages from counts; the original artifacts remain
> unchanged.

### 6.3 History: what each change actually did

Every main run is preserved, including the ones that made things worse. Only the
[first run](results/raw.json) predates the release of the no-reading agreement,
so later gains were made against examples the implementer could inspect, and are
exploratory rather than clean measurements.

All percentages in the following table are **F1**.

| Cohort and mode | First run, desktop | First run, narrow | Reviewed, desktop | Reviewed, narrow |
| --- | ---: | ---: | ---: | ---: |
| Original 60, oracle | 90.6% | 90.6% | 92.3% | 92.3% |
| New 35, oracle | 71.4% | 75.0% | 76.9% | 80.0% |
| All 95, oracle | 84.0% | 84.7% | 87.2% | 87.8% |
| All 95, candidate-gated | 78.9% | 80.0% | 82.2% | 83.1% |

Two things this table hides, both worth seeing:

**A fix made it worse before it made it better.** Scrolling offscreen targets
into view improved aiming, but the first `edge-fixes` run introduced false
alarms because scrolling changed viewport-relative geometry, and the
narrow-window oracle F1 *fell* from 84.7% to 80.9%. Switching to
document-relative coordinates in `edge-fixes-v2` brought it to 85.7%. Both runs
are kept so the regression stays visible.

**A higher F1 did not mean more coverage.** Classified desktop targets fell from
78/95 in the first run to 75/95 later. The detector became more accurate on what
it decided while deciding slightly less.

### 6.4 Comparing every detector idea

The [full matrix](fixtures/results/bakeoff-fixtures-upstream-full.json) runs
fifteen approaches over the same 95 frozen targets, desktop only. These are
Axcess reimplementations of upstream's published detectors, not the original
code. Recall uses all positive labels as the denominator.

| Method | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| D9 mouse/keyboard effects plus equivalent alternative | 87.2% | 87.2% | 87.2% |
| **D9u upstream's differential (8 channels, keys in sequence)** | **78.0%** | **82.1%** | **80.0%** |
| **D10b coverage set-difference (mouse ran what the keyboard never reached)** | **53.7%** | **92.3%** | **67.9%** |
| D10a JavaScript ran for the mouse, none for Enter | 57.1% | 82.1% | 67.4% |
| **D10a+base, the same with a handler-free baseline subtracted** | **57.1%** | **82.1%** | **67.4%** |
| D4 CSS appearance and text hints | 56.2% | 69.2% | 62.1% |
| D5 browser-debugger event listeners | 58.1% | 64.1% | 61.0% |
| D8 changes after hover | 75.0% | 46.2% | 57.1% |
| D6 intercepted listener registration | 53.8% | 53.8% | 53.8% |
| D2b JavaScript `onclick` property | 100.0% | 10.3% | 18.6% |
| D7 React event-handler properties | 100.0% | 5.1% | 9.8% |
| D3 tabindex / ARIA hints | 50.0% | 5.1% | 9.3% |
| D2 inline event attribute | 100.0% | 2.6% | 5.0% |
| D0 approximation of the existing clickable collection | 50.0% | 2.6% | 4.9% |
| D1 selected keyboard-related axe rules | 0.0% | 0.0% | - |

The dash follows the scorer's convention for an undefined F1 when precision and
recall are both zero. D1 raised one false alarm (`p80`) and found none of the 39
real defects. A separate `D1x` diagnostic credits axe for *any* violation on the
element, including colour contrast and landmark structure; it is deliberately
unsound, shown only to demonstrate that artefact, and excluded here. D0
approximates a discovery heuristic, not the complete Axcess scan pipeline.

**What the ranking says.** Behavioural comparison gives the best balance. Cheap
markup checks reach perfect precision while missing almost every defect - `D2`
finds one real defect in 39. And running JavaScript is not the same as doing
something useful: D10a raises 56 alerts to reach 32 real defects, so more than
two in five of its alerts are false.

**What D10a actually is.** It compares which JavaScript functions executed
during a mouse click against those executed for **Enter only**. It does not
apply the equivalent-control filter. It is a coarser instrument than D9 by
construction.

#### The three upstream formulations we had not measured

The first version of this matrix was missing three of upstream's detectors. They
are now implemented and scored, as their own rows rather than folded into ours,
because a comparison stops being one the moment the alternatives are merged.

**D9u is upstream's differential, bugs included** - the same eight channels
(ours drops `mutations`, which the `dom` digest covers except when edits net
out), compared by *presence* rather than payload, with Enter, Space and
ArrowDown pressed in sequence against a single page state. It scores
78.0% / 82.1% / **80.0% F1** against our D9's **87.2%**.

The interesting part is not the 7.2-point gap but its shape. D9u raises **9
false alarms to our 5**, which is the presence comparison clearing or creating
findings on unrelated channel activity, and it returns **10 unknowns to our
20** - it decides twice as much and is wrong more often. That is the cost of
folding "could not measure" into a verdict, measured rather than asserted.

**D10b is the set-difference form**, asking whether the mouse ran anything the
keyboard never reached, rather than whether the keyboard ran nothing at all. It
has the **highest recall of any detector here, 92.3%, and zero false
negatives** - the only method that missed no decidable defect. Upstream
predicted exactly this: an element the keyboard *reaches* runs focus code, so
D10a falls silent while the handler itself still never runs. It costs 31 false
alarms for that recall, so it is a funnel stage, not an output.

**D10a+base subtracts a per-page handler-free baseline** - click something with
no handler, see what runs anyway, discount it. It changed **no verdict at all**,
and that null result needs its qualification stated: the baseline was *empty for
82 of the 95 targets*, because these fixtures are static pages where an inert
click executes nothing. It only had real work to do on the React page, where it
removed 15 functions per click (upstream reported 28 on theirs). The mechanism
is implemented and correct; this corpus barely exercises it, and a
framework-heavy corpus is where it would earn its place.

The [legacy matrix](fixtures/results/bakeoff-fixtures.json) is kept for
comparison but is **superseded, not an equally reliable second opinion**. It
recorded D10a as `D10` before the name was made specific (52.2% / 89.7% /
66.0%), and D6 at 53.7% / 56.4% / 55.0%. The other ten methods scored
identically in precision, recall and F1. The legacy implementation swallowed
coverage failures and caps, and let a reported violation override an `unknown`,
which could turn failed measurements into confident verdicts. It also predates
provenance recording, so only the reviewed file carries fingerprints and a
validity flag. Where they disagree, the reviewed file is the measurement of
record.

#### What each detector costs

Measured on this corpus, 19 pages and 95 targets, from
[`page_timings_ms`](fixtures/results/bakeoff-fixtures-upstream-full.json). The
behavioural detectors are quoted per target because that is how they scale; the
rest are quoted per page.

| Detector | Cost | Recall | Cost per point of recall |
| --- | ---: | ---: | --- |
| D0, D2, D2b, D3, D4, D7 (filters) | < 0.01 ms/page each | 2.6-69.2% | effectively free |
| shared DOM walk feeding all six | 4.2 ms/page | - | paid once |
| D6 `addEventListener` shim | 1.6 ms/page | 53.8% | negligible |
| D5 CDP `getEventListeners` | 13.3 ms/page | 64.1% | negligible |
| D1 axe-core | 205 ms/page | 0.0% | no return at any price |
| D8 hover-diff | 1.02 s/page | 46.2% | 240x D5 for worse recall |
| D10a / D10b coverage | 0.78 s/target | 82.1 / 92.3% | ~1000x the cheap filters |
| D9u upstream differential | 1.31 s/target | 82.1% | ~1700x |
| **D9 our differential** | **1.48 s/target** | **87.2%** | **~1900x** |

The whole cheap family - six detectors and the DOM walk that feeds them - costs
about **4.2 ms per page**. Our differential costs **1.48 s per target**, which
on this corpus is roughly 350x the entire cheap suite per page, and upstream
measured the same ratio on theirs (1.20 s/probe against 34 ms).

That is the economic argument for the funnel, and it is why §6.2's 82% candidate
ceiling matters more than any accuracy number here. The cheap detectors are not
competing with the differential; they exist to decide what the expensive one
runs on. D4 is the clearest case - 69.2% recall for a rounding error of a
millisecond, at precision far too low to report to anyone.

Two costs deserve singling out. **D1 axe-core spends 205 ms per page to find
nothing at all** on this defect class. And **D8 hover-diff is the worst trade
measured**: a full second per page, two screenshots and a buffer comparison, for
recall below the listener route that costs 13 ms.

**We did not reproduce upstream's strongest filter.** Upstream compared sets of
executed V8 functions using exact equality plus matching effect-channel sets.
This port compares effect signatures and restricts alternatives to the same page
and window size. The main experiment collects no V8 coverage by default; only
the matrix's D10a does, for a different test. The optional coverage strategies
in the source are unscored prototypes, and the structural one abstains outright
because the records do not capture real DOM containment. Neither function
identity nor our lossy signatures prove two things are semantically the same.
Upstream's **98.1% F1** and our **92.3% F1 on its original 60 cases** come from
different procedures. This port improves parts of the method; it does not beat
that published headline.

### 6.5 Stage 4: functionality the keyboard can already reach

WCAG asks whether the *functionality* is keyboard-operable, not whether one
particular element is. A card whose whole surface is clickable is not a defect
when the heading inside it is a real link doing the same job. Without this stage
the output is accurate and unusable, because it reports every such wrapper.

Upstream calls this Stage 4 and reports it as the single highest-value step in
their pipeline: precision 86.7% to 96.3%, recall unchanged at 100%, for no extra
page loads. We implement the stage, and it fired **7 times** in the reviewed run
- four on desktop, three in the narrow window. Every dismissal was correct:
`p25` (labelled ok), `p27`, `h112` and `h140` (decoys). **No real defect was
lost**, and each is recorded in `dismissals` with the control that cleared it.

**We changed two things, and both are departures from upstream, not ports.**

*Same page and same window size.* Upstream built one `keyboardReachable` list
across the whole corpus and searched it without a page guard, so a finding on
page A could be cleared by a control on page B. Conformance is judged per page;
a control on another page is not an alternative a user has.

The corpus contains the exact case that separates these. `h140` is a **decoy on
desktop and a real violation in the narrow window**, because its keyboard
alternative `h141` is hidden by the responsive layout at 390 px. Our run
dismisses it on desktop and correctly leaves it a violation on mobile. A
corpus-wide search - or a viewport-blind one - gets that backwards.

*Effect payloads, not executed-function sets.* Upstream compares V8
executed-function sets with a similarity threshold. Their own sweep is the
argument against it: 0.50, 0.80 and 0.95 all scored **identically**, and only
exact equality reached the headline, because two *different* handlers inside one
framework share nearly every function they execute - the scheduler, the
reconciler, the synthetic event system. Any tolerant threshold silently deletes
real defects. We compare what the user can observe instead.

Upstream's signal is implemented, as `by_coverage_exact`, along with their
threshold sweep as `by_coverage_jaccard`. Both are **unscored prototypes**: the
main experiment collects no V8 coverage by default, so they abstain rather than
dismissing on absent evidence. A third strategy, `by_containment`, abstains
unconditionally because the outcome records carry no real DOM relationships.

**On the same 60 upstream fixtures**, their configuration and ours:

| | TP | FP | FN | Undecided | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Upstream, with Stage 4 | 26 | 1 | 0 | - | 96.3% | 100% |
| Ours, reviewed | 24 | 2 | 0 | 2 | 92.3% | 92.3% |

Both corpora hold 26 positives. We missed none outright - our two shortfalls are
*undecided*, and over decided targets alone our recall is also 100%. Strict
recall counts those two against us, which is the intended behaviour: refusing to
answer must never raise a score. The comparison is still not like-for-like,
because 96.3 / 100 is their whole configuration measured by a different
procedure, not Stage 4 in isolation.

### 6.6 What the errors teach us

Every lead needs a human. Examples from the saved errors:

- **`h103`** has a working custom keyboard toggle, but its focus and activation
  effects make the signature differ from the mouse's. A false alarm.
- **`h171`** uses a roving menu driven by ArrowRight; **`h172`** has a documented
  Alt+K shortcut. The trial presses only Enter, Space and ArrowDown, so it flags
  two controls that work.
- **`h160`** changes content inside an open shadow root - a DOM subtree attached
  to an element and deliberately isolated from the main document. The
  top-document snapshot misses the change, so a real defect gets no lead.
- **`h180`** waits 700 ms before acting; the observation window is 250 ms.
- **Closed shadow roots** (`p91`, `h164`) and **iframes** (`p92`, `p94`, `h162`,
  `h163`) cannot be resolved by this probe. They stay unknown, and three of them are
  real defects.
- **`p33`** is scored as a false alarm against an inherited tooltip label whose
  interpretation is genuinely arguable. A benchmark label is not a WCAG ruling.

The remaining undecided targets are the ones the instrument could not read: 14
per window not rendered or not reachable by the sampled mouse points, and 6
unresolved, giving the 20 unknowns per window. The runner's empty `errors` list
never meant every measurement succeeded - that is exactly why `unknown` is
tracked separately.

### 6.7 Reproducibility

Two full runs against the reviewed source:
[`reviewed`](results/reviewed.raw.json) at 13:14 UTC and
[`reviewed-repeat`](results/reviewed-repeat.raw.json) at 20:08 UTC on 2026-09-09.
Both report corpus fingerprint `763e0495...`, detector fingerprint
`c897005148...`, zero errors and `valid: true`. Wall times 315.9 s and 319.4 s.

The repeat reproduces the reviewed run's verdicts and summaries:

| Compared | Records | Differences |
| --- | ---: | ---: |
| Oracle verdicts | 190 | 0 |
| Candidate-gated verdicts | 190 | 0 |
| Candidate lists per page/window | 38 | 0 |
| Equivalence dismissals | 7 | 0 |
| Tab-order summaries | 38 | 0 |

**One instability showed up, and it is the documented one.** Two probe records
differ between the runs - `p61` in both windows - and only in a stored value:
the page writes `local:set:p61=<epoch ms>`, so the payload carries a clock
reading that necessarily changes. Every other record is identical.

This is the price of a deliberate decision in `channels.py` *not* to normalise
digit runs. Collapsing them would absorb timestamps, but it would equally absorb
order numbers, account ids and amounts, letting two genuinely different outcomes
compare equal. Non-determinism is therefore a disclosed limitation rather than
something papered over.

It changed no classification here. To turn this into a false alarm you would
need a control whose *working* keyboard handler writes its own fresh timestamp:
the mouse and keyboard signatures could then differ solely because of the clock,
and a working control could be reported as a defect. `p61` is not that case, and
the corpus contains no other payload of this shape.

### 6.8 What the evidence review changed

Codex's review of the saved evidence found problems worth fixing whether
or not they moved a score, in the detector's failure handling as well as in the
reporting:

- probes could vanish from the denominator when a measurement crashed;
- saved per-probe verdicts were written *before* the equivalent-control filter
  while the score tables were computed *after* it, so `raw.json` asserted
  "violation" for probes the score had already dismissed;
- a zero-sized element made the locator dereference an empty list of rectangles
  and throw, recording a page's own markup as an internal instrument fault;
- effects were summarised by union across key trials, which could describe a
  state no single trial ever produced;
- browser version and start-time fields were inaccurate.

**The scores did not move.** The reviewed figures are identical, cell for cell,
to `diamond-fixes` and `audit-fixes`:

| Run | Source state | Desktop oracle F1 | Narrow oracle F1 | Desktop gated F1 | Narrow gated F1 |
| --- | --- | ---: | ---: | ---: | ---: |
| `diamond-fixes` | pre-review | 87.2% | 87.8% | 82.2% | 83.1% |
| `audit-fixes` | audit applied | 87.2% | 87.8% | 82.2% | 83.1% |
| `reviewed` | reviewed and frozen | 87.2% | 87.8% | 82.2% | 83.1% |
| `reviewed-repeat` | unchanged | 87.2% | 87.8% | 82.2% | 83.1% |

Read that carefully, because it is easy to draw the wrong conclusion in either
direction. Two of these defects - the zero-size crash and the pre/post
equivalence mismatch - *were* exercised by this corpus and still moved no
accuracy metric. They governed whether a published number could be trusted and
audited, not what the number was. Other failure paths were not exercised here at
all and need dedicated tests rather than a corpus run. So: no accuracy figure in
this report should be credited to the review, and the absence of a gain is not
evidence the fixes were unnecessary.

One change is visible in the evidence. The 20 unknowns per window used to split
10 not-rendered / 4 instrument-error / 6 unresolved; they now split **14 / 0 /
6**. Eight records - `p26i`, `p73` and `p74` in both windows, plus `h142` on
desktop and `h141` in the narrow window - moved from `instrument_error` to
`not_rendered` and now name a cause: *not mouse-operable: display:none,
zero-size*. The count is unchanged and no score moves, because an undecided
probe stays undecided. But four probes per window stopped blaming the instrument
for the page's own markup, which is the difference between a number that is
right and a number that can be read.

**Provenance guards now in place.** The main runner fingerprints its sources
before importing the measured code and again before and after measurement, and
rechecks the frozen inputs afterwards. A mismatch at import rejects the command
before any measurement happens; drift detected later produces an artifact marked
invalid that publishes no scores. The matrix runner checks before and after
measurement, but not before import, and its records have a different shape - the
schema-2 per-mode evidence described here applies to the main runs. All five
historical main runs were left untouched and the two reviewed runs were written
beside them, so seven are now saved, and new runs refuse to overwrite an
existing label.

The one gap: earlier matrix files were overwritten in place during development,
so their per-probe JSON is gone. The ranking tables from six of those runs
survive as stdout in
[`edgecases/results/console-logs/`](edgecases/results/console-logs/), which
recovers the rankings but not the individual verdicts.

### 6.9 Supplemental stress tests (development only)

Claude also wrote [seven development pages](edgecases/truth.json) with 60
targets, 28 of them positive: a 1 x 1 pixel control, a below-fold target, a
scroll container, a wrapped inline element, transparent occlusion, alternative
key handlers, non-DOM effects and delayed actions. One page hides a defect after
120 ordinary buttons; another puts a target 150 wrappers deep. Those 120
background buttons are not scored as extra negatives.

The saved development run,
[`bakeoff-edgecases.json`](edgecases/results/bakeoff-edgecases.json), showed the
mechanics working: the behavioural test found the tiny, distant, scrolling,
wrapped and deeply nested click-only targets; it accepted Space-only and
keyup-only controls; it flagged both a focusable control that could not activate
and one whose keyboard action did the *wrong* thing. It missed a
double-click-only action and a 600 ms delayed one - the limits of single-click
input and a 250 ms window.

**These are development artifacts, not an evaluation.** The same author wrote
the pages and the detector and used these results while debugging. They are
useful for comparing individual observations but do not support an unbiased
ranking. This file also predates the reviewed source and has not been
regenerated. Note too that operating a 1 x 1 target here says nothing about the
separate WCAG target-size criterion.

---

## 7. Limits of the evidence

**The labels are not rulings.** The original labels are preserved for
comparison, including the debatable tooltip case and a console-only action; see
[UPSTREAM.md](UPSTREAM.md#label-caveats). Matching a benchmark label is not the
same as settling a WCAG judgment.

**The observations are deliberately lossy.** DOM and geometry are compact
hashes; canvas records operation counts, not pixels; network records URLs, not
what the response meant. Inner-frame and shadow-root state is not fully
captured. Equal signatures can hide different outcomes, and random ids or timing
can make equivalent outcomes look different. The historical `diamond-fixes` run
additionally normalised long digit and hex runs, which could erase a real
difference such as a report id; that behaviour was removed, and those results
remain evidence about that implementation only.

**The blindness is partial.** The new labels were authored separately from the
detector, but both authors had already discussed the likely failure modes.

**The coverage is narrow.** One browser engine, two window sizes, a finite
observation window and a finite set of keys. Documented shortcuts, composite
widgets, asynchronous applications and other starting states all require paths
this experiment never tries. A human has to confirm both that the functionality
is missing and that no other keyboard path exists.

**Nothing here touches production.** The experimental code does not write to
Axcess's SQLite evidence, issue grouping, scans or UI.

## 8. Getting this into normal scans

The reusable piece is the isolated browser experiment in
[`src/audit/analyzer/keyboard/kbdiff`](../../src/audit/analyzer/keyboard/kbdiff/).
It is a good prototype for a keyboard-operability probe. The results do not yet
justify turning it on for every scan.

In rough priority order:

1. **Improve candidate discovery.** It is the ceiling at 82%, and no
   confirmation stage can beat what it never proposes.
2. **See inside components and frames.** This probe cannot currently resolve
   targets inside iframes or closed shadow roots, and the top-document
   snapshot misses changes inside open shadow roots.
3. **Try richer keyboard paths.** Arrow keys, documented shortcuts and roving
   focus account for real false alarms today.
4. **Repeat trials** to detect unstable effects rather than reporting the first
   reading.
5. **Re-evaluate on newly authored, untouched examples** and on representative
   permitted sites. Report candidate coverage and unknown reasons next to
   precision and recall, never precision and recall alone.

When integrating, use the existing probe pipeline and store each lead under its
`scan_id` with a target reference, the actions attempted, the effects observed,
the uncertainty and supporting screenshots. Keep keyboard-operability leads
distinct from the keyboard-trap check. Clicking things changes application
state, so the permitted actions need to be chosen deliberately before this runs
against real sites. And a human should confirm the missing functionality before
any lead becomes a remediation conclusion.

## 9. Verification and current check status

After Claude drafted this report, Codex checked its numbers against the saved
evidence. All 12 score rows in each reviewed main run were reconstructed from
the individual verdicts and frozen labels. Every matrix row was checked against
its reported and unobservable target sets. Source fingerprints match across both
main runs, the reviewed matrix and the current source files; frozen input hashes
also match. The repeat comparisons above come from the records themselves.

Validation completed during implementation and final review:

- 817 unit tests, 29 browser integration checks and 80 existing UI route checks
  passed. The route checks used an isolated, migrated temporary database.
- Project Python and frontend type checks, strict type checks for the eight
  runner modules, frontend lint and the frontend build passed.
- Ruff lint and format checks passed for all 25 new Python files.

The full `make lint` gate still fails its formatting check on three unchanged,
pre-existing files: `src/audit/crawler/orchestrator.py`, `src/audit/web/issues.py`
and `tests/ui/test_accessibility_axe.py`. The full Ruff lint check passed; those
unrelated formatting changes were left to their owners. This is not a claim that
every project gate is green. The final report corrections changed documentation
only and did not trigger another browser run.

To reproduce the experiment with installed dependencies, follow the commands in
[README.md](README.md). Use a new run label to preserve the existing evidence.

---

## Appendix: the saved artifacts

| File | What it is |
| --- | --- |
| [`fixtures/truth.json`](fixtures/truth.json) | The frozen answer key: 95 targets, 19 pages, per-window labels. |
| [`fixtures/frozen-manifest.json`](fixtures/frozen-manifest.json) | SHA256 for every fixture and label file. |
| [`results/raw.json`](results/raw.json) | First run - the only one completed before the no-reading agreement was lifted. |
| [`results/edge-fixes.raw.json`](results/edge-fixes.raw.json) | The scroll regression, kept deliberately. |
| [`results/edge-fixes-v2.raw.json`](results/edge-fixes-v2.raw.json) | The document-relative fix for it. |
| [`results/diamond-fixes.raw.json`](results/diamond-fixes.raw.json) | Pre-review baseline. |
| [`results/audit-fixes.raw.json`](results/audit-fixes.raw.json) | Audit applied; scores unchanged. |
| [`results/reviewed.raw.json`](results/reviewed.raw.json) | **The measurement of record.** |
| [`results/reviewed-repeat.raw.json`](results/reviewed-repeat.raw.json) | Separate repeat run; identical verdicts. |
| [`fixtures/results/bakeoff-fixtures-upstream-full.json`](fixtures/results/bakeoff-fixtures-upstream-full.json) | **Full fifteen-method matrix**, incl. D9u, D10b, D10a+base and per-detector timings. |
| [`fixtures/results/bakeoff-fixtures-reviewed.json`](fixtures/results/bakeoff-fixtures-reviewed.json) | Reviewed twelve-method matrix; every shared row reproduces in the full run. |
| [`fixtures/results/bakeoff-fixtures.json`](fixtures/results/bakeoff-fixtures.json) | Legacy matrix; superseded. |
| [`edgecases/results/bakeoff-edgecases.json`](edgecases/results/bakeoff-edgecases.json) | Development stress run; not an evaluation. |
| [`edgecases/results/console-logs/`](edgecases/results/console-logs/) | Stdout of six earlier matrix runs, whose JSON was overwritten. |
| [`UPSTREAM.md`](UPSTREAM.md) | The upstream study, its licence and its label caveats. |

Each main JSON has generated Markdown beside it: `raw.json` pairs with
`results.md`, and `<label>.raw.json` with `<label>.results.md`. These hold the
same runs as formatted tables, with the rounding caveats above.
