# Can cheaper rules reduce keyboard-detector errors?

Yes, on these development examples. Correcting the upstream candidate rules
and adding small browser observations finds more defects and removes some false
alarms. It does **not** eliminate the need to test what a control actually does.

This is an offline experiment on `tabbing`; normal Axcess scans are unchanged.
The rules were designed after inspecting errors on the frozen 95-target corpus,
so these are **development results**, not accuracy on an unseen test set. This
extension measures the desktop layout, 1280 by 900. Earlier narrow-layout
measurements do not validate the new cheap rules at that size.

## Read the results in two ways

A **standalone lead** says “investigate this as a possible keyboard defect.”
A **candidate** says “send this control to a behavioral test.” Candidates can
include working controls. Keeping a control in that queue is not finding a bug.

For example, a `div` with `tabindex="0"` and a click listener is reachable with
Tab but does not gain button activation automatically. Upstream's cheap rules
subtract the Tab set before reporting. That removes this element even when its
keyboard action is broken. The experiment now saves both sets: raw proposals
for discovery and reported leads after each rule's decision.

**False positive (FP)** means a flagged target was labelled as working or as a
decoy. **False negative (FN)** means a labelled defect was not flagged despite a
decided result. **Unknown** means the observation cannot support a decision.
Strict recall divides true positives by all 39 defects, including undecided
defects in the denominator. Precision divides true positives by all flags.

## Measured rules

The first measurement is
[cheap-study-v1.json](fixtures/results/bakeoff-fixtures-cheap-study-v1.json).
The following are separately named variants; none reads the answer-key labels
or descriptive notes while making a decision.

| Rule | True positives | False positives | False negatives | Unknown defects / negatives | Precision | Strict recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1: upstream D4/D5/D6 union, subtract Tab | 33 | 18 | 6 | 0 / 0 | 64.7% | 84.6% | 73.3% |
| C2: C1 plus screenshot-hover proposals | 33 | 20 | 6 | 0 / 0 | 62.3% | 84.6% | 71.7% |
| C3: reject inert and `pointer-events:none`; abstain on opaque Tab observation | 32 | 13 | 6 | 1 / 1 | 71.1% | 82.1% | 76.2% |
| C4: C3 plus a clear center hit test | 32 | 11 | 6 | 1 / 1 | 74.4% | 82.1% | 78.0% |
| C5: focusable custom mouse control with no observed key handler | 3 | 0 | 36 | 0 / 0 | 100% | 7.7% | 14.3% |
| C6: visible label for an enabled toggle absent from Tab | 1 | 0 | 38 | 0 / 0 | 100% | 2.6% | 5.0% |
| C7: ancestor mouse listener, subtract Tab | 7 | 3 | 32 | 0 / 0 | 70.0% | 17.9% | 28.6% |
| C8: C3 plus C5/C6/C7 | 37 | 13 | 1 | 1 / 1 | 74.0% | 94.9% | 83.1% |
| C9: C8 plus a clear center hit test | 37 | 11 | 1 | 1 / 1 | 77.1% | 94.9% | 85.1% |

The earlier adapted D4/D5/D6 union found 31 of 39 defects with 24 false alarms.
Using the transcribed upstream rules first raised that to 33 with 18 false
alarms. In particular, the new traversal recovered the iframe defects `h162`
and `p92`. The old adapted rows remain in the artifact for comparison.

The C3 change is **not** a free reduction in errors: `p91`, a genuine defect in
a closed shadow root, becomes undecided. So does the correctly operating closed
shadow button `h164`. An unreadable focus observation is not proof that either
works or fails.

## Which misses did the additions recover?

| Examples | Observation | What it adds and what it cannot prove |
|---|---|---|
| `h101`, `p10`, `p54` | A custom control is in Tab, has a mouse binding, and has no directly observed keyboard handler. | C5 adds three correct leads. A global or ancestor key handler could still supply a working shortcut on another page. |
| `p26` | `label.control` identifies an enabled checkbox; the label is visible but the checkbox is `display:none` and absent from Tab. | C6 adds one correct lead. The good clipped checkbox remains keyboard reachable and is not flagged. We test visibility on the **label**, not only the control it activates. |
| `h121` | A mouse listener is registered on an ancestor or `document`. | C7 proposes the delegated control. This is a broad clue: the same document listener ignores the decorative `h123`. |
| `h102` | Both mouse and keyboard handlers exist. The keyboard changes feedback while the mouse opens grades. | C9 still misses this defect as a standalone rule. Its raw shortlist retains it. Listener existence cannot prove that the two results mean the same thing. |

The center hit test removed the covered controls `h130` and `p70` from this
corpus's flags. An offscreen center is retained as untested. A center-only test
can miss a partly exposed control whose edge is clickable, and a child-frame
hit test does not detect every overlay in its parent page. These are limits to
test on new examples before promoting the gate into production.

## The eleven remaining false alarms

| Group | Targets | Why cheap inspection is insufficient |
|---|---|---|
| Styling with no useful action | `h123`, `p20`, `p21`, `p55` | A button-like class or pointer cursor does not prove interactivity. Ancestor listeners do not identify which children they handle. |
| A handler with no effect | `p22` | Registration says code may run; it does not establish that anything useful happens. |
| Another control supplies the action | `h112`, `h140`, `p23`, `p27` | A nested or separate native control can supply the same function. Containment alone does not prove equivalent behavior. |
| A different keyboard path works | `h171`, `h172` | Arrow-key navigation and a documented shortcut can work without a direct Tab stop on the target. |

The practical next step is to prioritize these groups differently: test whether
the mouse produces an effect, compare the result with keyboard alternatives,
and support explicit arrow/shortcut paths. Rejecting all styled controls without
direct listeners would also lose CSS-only hover controls and delegated actions.
Synthetic click dispatch executes page code; it is not a free static test.

Stage 4 also has its own false-negative risk. In `h110`, one shared function
opens different reports depending on the control's data. Equal executed-function
sets can wrongly dismiss a real defect. The payload comparison retains that
case, but payload equality can itself fail on nondeterministic content. We must
measure both directions of error rather than assume either filter is always
better.

## What does this buy as a shortlist?

C1's raw queue has **81 targets**, including **37 of 39 defects**. C9's queue
has **78 targets**, including **all 39 defects**. The latter also retains
`h102` and `p91` for deeper investigation even though it does not confidently
flag them. This is better discovery on these examples, but only 17 of 95 target
trials would be omitted before accounting for alternative controls.

That is an 82.1% queue, not an 82.1% time saving. Target trials have different
costs, and Stage 4 needs measurements of equivalent keyboard controls even when
those controls are absent from the shortlist. No reduced behavioral pipeline
was timed here. Intersecting candidates with an already-completed oracle run
does not establish a faster real pipeline.

The JSON retains shared navigation, Tab traversal, resolution, feature-reading,
and method timings. In the first run, the upstream D4/D5/D6 method calls totalled
about **387 ms** for all 95 targets, while their shared setup/Tab/visibility/
resolution work added about **3.42 seconds**. Feature collection and other rules
add further work. The whole comparison is slower because it deliberately runs
every competing method, including two hover and two axe arms. Its screenshot
hover arm alone took about **23.7 seconds**, added no true positives to C1, and
added two false alarms (`h152`, `p33`). These are local fixture timings, not crawl
speed or a production performance guarantee.

## Reproduce and audit

Run a new experiment with a new label; the runner refuses to overwrite evidence:

```bash
uv run python experiments/tabbing/runner/bakeoff.py \
  --corpus fixtures --candidate-study --cheap-only --label my-cheap-run
```

Remove `--cheap-only` to include D9, D10, and Stage 4 comparisons. The published
artifact includes the frozen corpus hash, source hashes before and after,
browser/engine versions, raw proposals, Tab indices, feature observations,
exclusion reasons, and scores. It reports unexpected method failures explicitly.

[analyze_candidates.py](analyze_candidates.py) independently rebuilds the C1–C9
sets from saved observations and checks score arithmetic without importing the
detector or scoring implementation:

```bash
python experiments/tabbing/analyze_candidates.py \
  experiments/tabbing/fixtures/results/bakeoff-fixtures-cheap-study-v1.json
```

See [the per-family parity review](UPSTREAM_PARITY_REVIEW.md) before describing
any row as an exact upstream replication. In particular, D1's local axe engine
is 4.10.2 versus upstream's locked 4.11.1, and the harness has documented
differences in Tab traversal, state isolation, method ordering, and failure
handling. All twelve detector families are represented; the complete experiment
is not byte-for-byte or engine-identical to upstream.
