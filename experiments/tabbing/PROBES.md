# What each probe observes, and what it can prove

This is a reader's guide to the detectors and rules in this experiment: what
question each one asks the browser, what it costs, and — the part that matters
most when porting one — what it is **not** entitled to conclude.

Everything here targets one WCAG success criterion, [2.1.1
Keyboard](https://www.w3.org/WAI/WCAG21/Understanding/keyboard): can everything
you can do with a mouse also be done with a keyboard? The hard part is not
finding controls. It is deciding whether a given control is *broken*, and doing
that without running the page for every candidate.

## Two layers, and why the distinction keeps mattering

**Candidate generators** (D0, D2–D8) answer *"does this look interactive?"*
They propose elements. They do not decide anything.

**Oracles** (D9, D10) answer *"does the keyboard reach what the mouse reaches?"*
They decide, and they are expensive: D9 costs about **1278 ms per target**
because it drives the mouse, drives the keyboard, compares the outcomes, and
reloads to undo the damage.

Upstream turned each generator into a detector by reporting `candidates − T`,
where `T` is the true tab order. That convention is reproduced here so the
numbers stay comparable, and it carries a permanent blind spot worth stating
before anything else:

> An element that **is** in the tab order but does nothing when you press a key
> is removed by the subtraction, no matter which generator proposed it.

| id | asks |
|---|---|
| D0 | what this repo's clickable collector ships today |
| D1 | does a general scanner (axe-core) see it at all |
| D2 / D2b | is a handler in the `onclick` attribute / property |
| D3 | does `tabindex` or ARIA claim it is interactive |
| D4 | does it *look* clickable (`cursor`, class lexicon) |
| D5 | is a listener actually bound to it (CDP `getEventListeners`) |
| D6 | was a listener registered after load (`addEventListener` shim) |
| D7 | did React bind a handler (fiber props) |
| D8 | does hovering change the rendering (screenshot diff) |
| D9 | does the mouse do something the keyboard cannot |
| D10 | did the mouse run code the keyboard did not (V8 coverage) |

The C-rules (`candidate_analysis.py`) combine generators with cheap browser
observations. C9 is the best of those: **77.1% precision, 94.9% strict recall,
41 ms per target.** Everything below exists to attack C9's eleven false alarms
and one miss.

## The nine newer rules

Read them as two groups, because the split is the actual finding.

### Structural rules — R1, R2, R3, R5, R6, R7

These read the DOM. They never run page code. Cost is somewhere between
"unmeasurable" and 104 ms per target.

#### R1 — redundant click surface · `probe_containment.py`

*Observes:* whether the element contains, or sits inside, something matching
`a[href], button, input, select, textarea, summary, [tabindex]:not([tabindex="-1"])`.

*Why:* a card wrapping a link, or a decorative span inside a button, is one
action with two click surfaces. The keyboard route already exists on the other
one.

*Clears:* `h112`, `p23`, `p27`. *Cost:* ~0.4 ms/target.

*Cannot prove:* that the wrapper does the same thing as the control it wraps.
Containment is a proximity argument, not an equivalence argument. A card whose
click opens a preview while its nested link navigates elsewhere would be
dismissed wrongly.

#### R2 — roving tabindex · `probe_composite.py`

*Observes:* an ARIA item role (`menuitem`, `tab`, `option`, `radio`,
`treeitem`, `gridcell`, …) inside a composite owner (`menubar`, `tablist`,
`listbox`, `radiogroup`, `tree`, `grid`, `toolbar`), with `tabindex="-1"` and at
least one sibling item holding a non-negative `tabindex`.

*Why:* this is the pattern the [ARIA Authoring
Practices](https://www.w3.org/WAI/ARIA/apg/patterns/) prescribe. Exactly one
child is a tab stop; arrow keys move focus among the rest. A `tabindex="-1"`
child of such a container is correct, not broken.

*Clears:* `h171`. *Cost:* shares ~0.6 ms/target with R3.

*Cannot prove:* that the arrow-key handler is actually wired. The rule reads the
shape of the widget, not its behaviour — a container that declares `role="menubar"`
and binds nothing would be dismissed wrongly.

#### R3 — declared shortcut · `probe_composite.py`

*Observes:* `aria-keyshortcuts`, or a chord such as `Alt+K` matched by
`/\b(alt|ctrl|control|cmd|command|shift|meta)\s*[+\-]\s*\S/i` in the element's
own text, `aria-label` or `title`.

*Clears:* `h172`. *Cost:* shares ~0.6 ms/target with R2.

*Cannot prove:* anything, really. **This is the weakest rule here and should be
treated as a lead, not a dismissal.** No fixture uses `aria-keyshortcuts`, so
on this corpus the entire rule rests on a regex over label text, on one probe.
Advertised text is not evidence a shortcut is bound. If you port one rule with
a warning attached, make it this one.

#### R5 — no observable action path · `probe_effect.py`

*Observes, all four at once:* no activation listener bound directly to the
element (CDP `getEventListeners` at `depth: 0`), no delegated listener reaching
it, no label/control relation, **and** hovering reveals nothing that was hidden.

*Why this one took three attempts:* the obvious version — demote every styled
control with no direct listener — costs `h151`, `p26` and `p30`, the CSS-only
hover menus and the label for a `display:none` checkbox, and drops F1 from 85.1
to 82.9. The second version gated that on "does hover change anything", and
removed nothing at all, because `.btnish:hover { background: #d3e2fb }` produces
a hover diff exactly as readily as `.menu:hover .panel { display: block }`.

The question that separates them is **structural, not pictorial**: does hovering
cause an element that was *not rendered* to become rendered?

| Probe | Kind | Labelled | Reveals something hidden |
|---|---|---|---|
| `h151`, `p30` | disclosure, keyboard-unreachable | defect | yes |
| `h150`, `p32` | disclosure, keyboard-reachable | working | yes |
| `h152`, `p20`, `p21` | cosmetic hover | decoy | no |

Note that the rule must spare all four disclosures, not just the two broken
ones. R5 decides whether an **action path exists**, which is a separate question
from whether the keyboard can reach it. Conflating the two is what made the
first two attempts lose real defects.

D8's screenshot arm cannot make that distinction, and costs 249 ms per target to
not make it. This costs no screenshot.

*Clears:* `p20`, `p21`. *Cost:* ~104 ms/target — ~8.5 ms of CDP listener reads,
~36 ms of hover and DOM walks, and ~35 ms of fixed settle waits that a tuned
implementation could shorten.

*Cannot prove:* that nothing happens. It proves that none of four specific
channels shows anything. A control driven by a capture-phase listener on
`window`, or by a CSS `:active` rule, would be dismissed wrongly.

#### R6 — name twin · `probe_effect2.py`

*Observes:* a visible, Tab-reachable `a[href], button, input, select, textarea,
summary` elsewhere in the document whose normalised accessible name matches the
lead's.

*Why:* the `h140` shape. `h140` is a `div` reading "Open resources"; `h141` is a
`button` reading "Open resources". R1 cannot see this because the two are
siblings, not nested.

*Clears:* `h140`. *Cost:* free (one extra `evaluate` per page).

*Cannot prove:* that the twin does the same thing. Two "Download" buttons on a
page may download different files. Name matching is weaker than containment,
and containment was already weak. **Of the dismissal rules this has the highest
chance of being wrong on real pages**, where repeated generic names are common.

#### R7 — framework props beat delegation · `probe_effect2.py`

*Observes:* the element carries `__reactProps$…` or `__reactFiber$…`, and none
of its props matches `/^on(Click|MouseDown|MouseUp|PointerDown|PointerUp|KeyDown|KeyUp|KeyPress)$/`.

*Why:* React attaches one delegation listener at the root of the app, so a rule
like C7 ("an ancestor has a mouse listener") flags **every element in a React
tree**. `p55` is a styled `div` with no `onClick` at all; C7 flagged it on
evidence that was never about `p55`. Inside a React tree the fiber props are the
authority, and they say no.

*Clears:* `p55`. *Cost:* free (shares R6's pass).

*Cannot prove:* anything outside React, and nothing about a component that binds
its own listener in an effect rather than through a prop. The `framework` field
is `null` for non-React elements, and the rule deliberately does nothing there.

### Behavioural rules — R8, R9

These run the page. They are not cheap, and calling them cheap would be the
single most misleading thing this document could do.

#### R8 — no click effect · `probe_effect2.py`

*Observes:* dispatch a real click on a freshly navigated page; does anything
observable change?

*Clears:* `h123` (decorative), `p22` (`/* intentionally empty */` handler),
`p55`. These are the "registration is not effect" cases that no static rule
reaches.

**This rule failed three different ways before it worked, and each failure is
worth knowing before you reimplement it.**

1. **Rendered-DOM diffing dismissed nine real defects.** `e-nodom.html` exists
   to punish exactly that: `p60` only calls `fetch()`, `p61` only writes
   `localStorage`, `p62` only draws on a canvas, `p63` only logs, `h105` only
   writes storage. All five are real defects. All five look dead to a DOM diff.
2. **A fixed 80 ms settle scored `h180` dead.** It defers its DOM change by
   700 ms.
3. **A top-document digest missed `h160`, `h162` and `p92`,** whose effects land
   in a child frame.

The working version therefore digests **every frame**, **pierces shadow roots**,
serialises **both web storages**, hashes **every canvas**, counts **console and
network activity**, and **polls to a 900 ms deadline** rather than sleeping.
With those channels it dismisses exactly `h123`, `p22` and `p55` and nothing
else, identically across three repeats.

The conclusion generalises past this corpus: **a DOM-diff oracle is not a safe
cheap substitute for a behavioural test.** A multi-channel one with a deadline is
closer, and is still bounded by the channels it happens to watch. A WebSocket
frame, an IndexedDB write, or a change inside a cross-origin frame would all
still read as dead.

#### R9 — divergent key effect · `probe_effect2.py`

*Observes:* focus the element, press Enter then Space, and compare the resulting
digest against the click digest. Both act, but differently?

*This is a promotion, not a dismissal* — the only rule here that **adds** a
finding.

*Recovers:* `h102`, which binds both `click` and `keydown`. The keydown updates
unrelated feedback; the click opens grades. Every listener-based rule in this
repository shares a ceiling that `h102` sits above, because listener existence
cannot show that two handlers *mean* the same thing. Comparing outcomes can.

*Cannot prove:* equivalence when the digests differ for innocent reasons —
nondeterministic content, a timestamp, a focus ring that changes layout. The
digest deliberately excludes styling, but this is the rule most exposed to
noise on real pages.

*Cost of R8 + R9 together:* a median of **442 ms** and a maximum of **1580 ms**
per lead that reaches them, on the 42 of 95 targets the free rules could not
settle. Amortised over all 95: **283 ms/target**.

## Reading the cost column

`CHEAP_DETECTOR_REVIEW.md` reports `ms per target` as measured browser work
divided by the corpus's 95 targets. That amortises per-page setup, so it is a
**throughput figure, not a per-button guarantee**.

- C1–C14 are per-target uniform. Every target costs the same.
- C15 and C16 are not. They triage first and run the behavioural pass only on
  survivors, so most targets cost nothing and a few cost over a second.

Under a hard per-button ceiling of 300 ms the best rule is **C14** — 92.5%
precision, 94.9% strict recall, 146 ms/target. Under an average-across-the-page
ceiling it is C16, at 283 ms/target against D9's 1278 ms.

## Running them

Each probe writes JSON; the scorers read those files plus the published artifact
and the frozen answer key. No scorer imports the detector or scoring
implementation, so a bug there cannot flatter these numbers.

```bash
uv run python experiments/tabbing/probes/probe_containment.py /tmp/p/containment.json
uv run python experiments/tabbing/probes/probe_composite.py   /tmp/p/composite.json
uv run python experiments/tabbing/probes/probe_effect.py      /tmp/p/effect.json
# The second argument is a JSON list of probe ids. Omit it to run the
# behavioural pass on all 95 targets instead of just the surviving leads.
uv run python experiments/tabbing/probes/probe_effect2.py     /tmp/p/effect2.json /tmp/p/leads.json

python experiments/tabbing/probes/score_new.py  /tmp/p   # C10-C13
python experiments/tabbing/probes/score_new2.py /tmp/p   # C14-C16
```

The observation files committed alongside the scripts reproduce the published
table without re-running a browser.

## The caveat that outranks the results

C16 scores 100% precision and 97.4% strict recall with no false positive and no
false negative. **Do not quote that as accuracy.**

Every rule above was written after reading a specific error on a 95-target
corpus whose labels were visible throughout. R2, R3, R6 and R7 each fire on
exactly one probe, which is the shape of a rule fitted to a fixture whatever
principle stands behind it. The rules are predeclared in `LLMTalk` [10] and
[11] so a fresh corpus can *measure* them rather than confirm them; until that
happens these are development numbers.

The one target C16 leaves undecided, `p91`, is a defect inside a closed shadow
root. It abstains rather than guessing, which is why recall reads 97.4% and not
100%. That abstention is the correct behaviour and should survive any port:
`Verdict.UNKNOWN` is a first-class outcome here, and strict recall keeps
undecided positives in the denominator precisely so that abstaining is never
free.
