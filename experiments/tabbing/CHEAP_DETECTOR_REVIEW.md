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

| Rule | TP | FP | FN | Unknown defects / negatives | Precision | Strict recall | F1 | ms per target |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1: upstream D4/D5/D6 union, subtract Tab | 33 | 18 | 6 | 0 / 0 | 64.7% | 84.6% | 73.3% | 40 |
| C2: C1 plus screenshot-hover proposals | 33 | 20 | 6 | 0 / 0 | 62.3% | 84.6% | 71.7% | 289 |
| C3: reject inert and `pointer-events:none`; abstain on opaque Tab observation | 32 | 13 | 6 | 1 / 1 | 71.1% | 82.1% | 76.2% | 41 |
| C4: C3 plus a clear center hit test | 32 | 11 | 6 | 1 / 1 | 74.4% | 82.1% | 78.0% | 41 |
| C5: focusable custom mouse control with no observed key handler | 3 | 0 | 36 | 0 / 0 | 100% | 7.7% | 14.3% | 41 |
| C6: visible label for an enabled toggle absent from Tab | 1 | 0 | 38 | 0 / 0 | 100% | 2.6% | 5.0% | 37 |
| C7: ancestor mouse listener, subtract Tab | 7 | 3 | 32 | 0 / 0 | 70.0% | 17.9% | 28.6% | 37 |
| C8: C3 plus C5/C6/C7 | 37 | 13 | 1 | 1 / 1 | 74.0% | 94.9% | 83.1% | 41 |
| C9: C8 plus a clear center hit test | 37 | 11 | 1 | 1 / 1 | 77.1% | 94.9% | 85.1% | 41 |
| C10: C9 minus redundant click surfaces (R1) | 37 | 8 | 1 | 1 / 1 | 82.2% | 94.9% | 88.1% | 42 |
| C11: C10 minus roving-tabindex items (R2) | 37 | 7 | 1 | 1 / 1 | 84.1% | 94.9% | 89.2% | 42 |
| C12: C11 minus declared shortcuts (R3) | 37 | 6 | 1 | 1 / 1 | 86.0% | 94.9% | 90.2% | 42 |
| C13: C12 minus leads with no action path (R5) | 37 | **4** | 1 | 1 / 1 | **90.2%** | **94.9%** | **92.5%** | 146 |
| C14: C13 minus name-twinned leads (R6) | 37 | 3 | 1 | 1 / 1 | 92.5% | 94.9% | 93.7% | 146 |
| C15: C14 minus leads with no click effect (R7, R8) | 37 | 0 | 1 | 1 / 1 | 100% | 94.9% | 97.4% | 283 |
| C16: C15 plus divergent-key-effect promotions (R9) | 38 | 0 | 0 | 1 / 0 | **100%** | **97.4%** | **98.7%** | 283 |

The `ms per target` column divides each rule's measured browser work by the 95
targets in the corpus. It amortises per-page setup, so it is a throughput
figure, not a promise about any one button. C1–C14 are per-target uniform.
C15 and C16 are not: they run a behavioural pass only on the leads C14 still
holds, 42 of 95 here, and those cost a median of 442 ms and up to 1580 ms each
while the other 53 cost nothing. Under a hard per-button ceiling of 300 ms,
**C14 is the best available rule**; under an average-across-the-page ceiling,
C16 is, at 283 ms per target against the 1278 ms of the behavioural arm.

## The four rules that clear C9's false alarms

[PROBES.md](PROBES.md) explains every detector and rule in detail: what each
one observes, what it costs, and what it is not entitled to conclude.

R1–R3 and R5 are static. They read the DOM and one hover; none of them runs
page code.

| Rule | Dismisses a lead when | Clears |
|---|---|---|
| R1 redundant click surface | it contains, or sits inside, a Tab-reachable native control | `h112`, `p23`, `p27` |
| R2 roving tabindex | it is an ARIA item role under a composite owner, `tabindex="-1"`, with a sibling holding the tab stop | `h171` |
| R3 declared shortcut | `aria-keyshortcuts`, or a chord such as `Alt+K`, appears in its own accessible text | `h172` |
| R5 no action path | no activation listener is bound to it, no delegation reaches it, no label relation, **and** hovering reveals nothing that was hidden | `p20`, `p21` |

R5 is the one that needed care. Demoting every styled control with no direct
listener also costs `h151`, `p26` and `p30` — the CSS-only hover menus and the
label for a `display:none` checkbox — and drops F1 to 82.9. Gating that on
"does hover change anything" removes nothing, because `.btnish:hover` repaints
a background as visibly as `.menu:hover .panel` reveals a panel. The question
that separates them is structural, not pictorial: does hovering render an
element that was **not rendered** before?

| Probe | Kind | Hover reveals something hidden |
|---|---|---|
| `h150`, `h151`, `p30`, `p32` | real disclosure | yes |
| `h152`, `p20`, `p21` | cosmetic hover | no |

The screenshot arm could not make that distinction at 249 ms per target. This
costs no screenshot.

## The four rules that clear the rest

R6 and R7 are static and free. R8 and R9 run the page, and that is the whole
reason they reach cases nothing above could.

| Rule | Effect | Clears |
|---|---|---|
| R6 name twin | dismiss: a visible, Tab-reachable native control carries the same accessible name | `h140` |
| R7 framework props beat delegation | dismiss: the element is in a React tree and its own props hold no activation prop, so the root delegation listener says nothing about it | `p55` |
| R8 no click effect | dismiss: a real click changes nothing observable | `h123`, `p22`, `p55` |
| R9 divergent key effect | **promote**: click and keyboard both do something, and it is not the same something | recovers `h102` |

R9 is a promotion, not a dismissal, and it is what takes strict recall past the
ceiling every listener-based rule shares. `h102` binds both `click` and
`keydown`; the keydown updates unrelated feedback while the click opens grades.
No amount of listener inspection can see that. Comparing the two outcomes can.

### What R8 must watch, and what it cost to learn

R8's first implementation compared the rendered DOM and dismissed nine real
defects. `e-nodom.html` exists to punish exactly that: `p60` only calls
`fetch()`, `p61` only writes `localStorage`, `p62` only draws on a canvas,
`p63` only logs, `h105` only writes storage. `h180` defers its DOM change by
700 ms, so a fixed short wait scores it dead too, and `h160`, `h162` and `p92`
put their effect in a child frame that a top-document digest never reads.

The working version digests every frame, pierces shadow roots, serialises both
web storages, hashes every canvas, and counts console and network activity,
then polls for up to 900 ms instead of sleeping a fixed 80. With those five
channels it dismisses `h123`, `p22` and `p55` and nothing else. **A DOM-diff
oracle is not a safe cheap substitute for a behavioural test**; a multi-channel
one with a deadline is closer, and still only as good as the channels it knows
to watch. A control whose only effect is a WebSocket frame, an IndexedDB write,
or a change inside a cross-origin frame would still read as dead.

Three repeats of the behavioural pass produced identical observations for all
95 targets.

### Why these numbers should not be quoted as accuracy

C16 scores 100% precision and 97.4% strict recall with no false positive and no
false negative on this corpus. That is a development result on 95 targets whose
labels were visible while the rules were written, and every rule above was
designed after reading a specific error. R2, R3, R6 and R7 each fire on exactly
one probe, which is the shape of a rule fitted to a fixture whatever the pattern
behind it. The remaining undecided target, `p91`, is a defect inside a closed
shadow root: C16 abstains on it rather than guessing, which is why recall is
97.4% and not 100%. None of this is measured accuracy on unseen pages.

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
| `h102` | Both mouse and keyboard handlers exist. The keyboard changes feedback while the mouse opens grades. | C9 still misses this defect as a standalone rule. Its raw shortlist retains it. Listener existence cannot prove that the two results mean the same thing — R9 recovers it by comparing the two outcomes instead. |

The center hit test removed the covered controls `h130` and `p70` from this
corpus's flags. An offscreen center is retained as untested. A center-only test
can miss a partly exposed control whose edge is clickable, and a child-frame
hit test does not detect every overlay in its parent page. These are limits to
test on new examples before promoting the gate into production.

## C9's eleven false alarms, and which rule cleared each

| Group | Targets | Why cheap inspection is insufficient | Cleared by |
|---|---|---|---|
| Styling with no useful action | `h123`, `p20`, `p21`, `p55` | A button-like class or pointer cursor does not prove interactivity. Ancestor listeners do not identify which children they handle. | R5 (`p20`, `p21`), R7/R8 (`p55`), R8 (`h123`) |
| A handler with no effect | `p22` | Registration says code may run; it does not establish that anything useful happens. | R8 |
| Another control supplies the action | `h112`, `h140`, `p23`, `p27` | A nested or separate native control can supply the same function. Containment alone does not prove equivalent behavior. | R1 (`h112`, `p23`, `p27`), R6 (`h140`) |
| A different keyboard path works | `h171`, `h172` | Arrow-key navigation and a documented shortcut can work without a direct Tab stop on the target. | R2 (`h171`), R3 (`h172`) |

The split that made the difference was between the two questions the groups ask.
"Another control supplies the action" and "a different keyboard path works" are
**structural**, and R1, R2, R3 and R6 answer them by reading the DOM. "Styling
with no useful action" and "a handler with no effect" are **behavioural**, and
only R8 answers those, by running the page. Every attempt to answer them
statically cost real defects: see R5 above, which works only because it stops at
the leads that have no action path of any kind at all.

Synthetic click dispatch executes page code; it is not a free static test. R8
costs a navigation and up to 900 ms per lead, which is why it is worth running
only on the leads the free rules could not settle.

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

C10–C16 are scored offline from the same artifact by standalone scripts in
[probes/](probes/), which do not import the detector or scoring implementation
either. `probe_containment.py`, `probe_composite.py` and `probe_effect.py`
collect R1/R2/R3/R5; `probe_effect2.py` collects R6–R9 and takes an optional
JSON list of probe ids so the behavioural pass runs only on surviving leads:

```bash
uv run python experiments/tabbing/probes/probe_containment.py /tmp/containment.json
uv run python experiments/tabbing/probes/probe_composite.py   /tmp/composite.json
uv run python experiments/tabbing/probes/probe_effect.py      /tmp/effect.json
uv run python experiments/tabbing/probes/probe_effect2.py     /tmp/effect2.json /tmp/leads.json
python experiments/tabbing/probes/score_new.py  /tmp   # C10-C13
python experiments/tabbing/probes/score_new2.py /tmp   # C14-C16
```

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
