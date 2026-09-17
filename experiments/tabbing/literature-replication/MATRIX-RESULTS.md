# The full detector matrix across four environments

Every detector in the suite, run by `experiments/tabbing/runner/bakeoff.py` — the
real harness, importing the frozen detectors from
`src/audit/analyzer/keyboard/kbdiff/`. Nothing here is a reimplementation.

**43 detectors** were measured, not the 38 in `detector-matrix.results.md`: the
run surfaces variants that table never listed.

## What each column means

- **abst.** — abstentions. A probe the detector declined to decide, never scored
  as a negative. Reporting a budget limit as "no violation found" is the failure
  mode this column exists to prevent.
- **ms/button** — the detector's measured browser time divided by the probes it
  decided. This is the unit the 300 ms cap is stated in: the cost of deciding
  one button. It is **not** the `ms/target` in `detector-matrix.results.md`,
  which amortises over every target on the page and is a throughput figure.
  Where a detector has no measurement of its own (compositions like C1–C9), the
  cost of its inputs is summed, since they share one survey walk.
- Rules with no own timing key and no composition show `—` rather than a guess.

## Environments

| corpus | what it is | published reference |
|---|---|---|
| **fixtures** | blind-authored synthetic, 95 probes / 39 defects | none; the suite's own baseline |
| **edgecases** | shared-author development corpus | none; **no unbiased accuracy claim** |
| **gds** | GDS Accessibility Tool Audit (MIT, Crown Copyright 2017), 6 IAF cases + 2 controls | **all 13 audited tools score 0/6** |
| **ma11y** | Ma11y-generated mutants of the GDS page, ground truth by construction *and* verified behaviourally | none |

## Headline: the GDS environment

The GDS corpus is the only one here with a published competitor result, and it
is a hard one: **every one of the 13 tools GDS audited scores 0 of 6.**

| detector | TP | FP | precision | ms/button |
|---|---:|---:|---:|---:|
| D4 CSS + lexical | 3 | 0 | 100.0% | 1.9 |
| D6 addEventListener shim | 3 | 0 | 100.0% | 2.9 |
| D5 CDP getEventListeners | 3 | 0 | 100.0% | 9.5 |
| C1 upstream D4\|D5\|D6, minus Tab | 3 | 0 | 100.0% | 10.4 |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 3 | 0 | 100.0% | 190.3 |
| D9 behavioural differential | 2 | 0 | 100.0% | 2836.1 |
| D0 axcess collectClickables | 1 | 0 | 100.0% | 1.9 |

Three detectors find **3 of 6 at zero false positives**, for under 10 ms per
button. Against a published 0/6 that is a real gain, and it is the first result
in this project produced by the frozen detectors rather than by a harness
written to describe them.

**What it is not:** 3/6 is not 6/6, and half the cases are still missed by
everything in the suite. The three nobody finds are `gds-dropdown` (submenu
`display:none` until hover), `gds-role-button` (Space on `a[role=button]`), and
`gds-concertina` (`dt` toggling on click only).

## The finding that costs the suite its best number

**C8/C9 abstain on GDS on exactly the three cases their own inputs find.**

D4, D5 and D6 each return `gds-fake-button`, `gds-tooltip` and `gds-concertina`.
C8 and C9 combine those same detectors and return **0 TP with 3 abstentions** —
the union's filter stages (`inert`, `pointer-events:none`, blocked-centre)
cannot resolve those elements on a real page, so a safety filter suppresses
three true positives. On fixtures C9 scores 77.1% / 94.9%; on GDS it decides
nothing at all.

The cheap rules the combinations were built to improve on beat them here.

## Full matrix

### gds — GDS Accessibility Tool Audit; published reference 0/6 for all 13 audited tools

| detector | TP | FP | FN | abst. | precision | recall | F1 | ms/button |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 upstream D4|D5|D6, minus Tab | 3 | 0 | 3 | 0 | 100.0% | 50.0% | 66.7% | 10.4 |
| C2 upstream D4|D5|D6|D8, minus Tab | 3 | 0 | 3 | 0 | 100.0% | 50.0% | 66.7% | 190.3 |
| C3 union, reject inert and pointer-events:none | 0 | 0 | 3 | 3 | — | 0.0% | — | 304.4 |
| C4 union, additionally reject blocked center | 0 | 0 | 3 | 3 | — | 0.0% | — | 304.4 |
| C5 focusable custom mouse control, no observed key handler | 0 | 0 | 6 | 0 | — | 0.0% | — | 10.4 |
| C6 visible label for a toggle absent from Tab | 0 | 0 | 6 | 0 | — | 0.0% | — | 1.9 |
| C7 ancestor mouse listener, minus Tab | 0 | 0 | 6 | 0 | — | 0.0% | — | 10.4 |
| C8 union + focusable + label + ancestor leads | 0 | 0 | 3 | 3 | — | 0.0% | — | 304.4 |
| C9 combined leads, additionally reject blocked center | 0 | 0 | 3 | 3 | — | 0.0% | — | 304.4 |
| D0 axcess collectClickables | 1 | 0 | 5 | 0 | 100.0% | 16.7% | 28.6% | 1.9 |
| D1 axe-core (keyboard rules) | 0 | 0 | 6 | 0 | — | 0.0% | — | 1428.9 |
| D10a coverage differential (Enter only, no baseline subtraction) | 0 | 0 | 0 | 8 | — | 0.0% | — | — |
| D10a+base coverage differential (Enter only, baseline subtracted) | 0 | 0 | 0 | 8 | — | 0.0% | — | — |
| D10a-u upstream coverage presence (sequential keys, baselined) | 0 | 0 | 0 | 8 | — | 0.0% | — | — |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 0 | 0 | 0 | 8 | — | 0.0% | — | — |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 0 | 0 | 0 | 8 | — | 0.0% | — | — |
| D1x axe-core (any rule, unsound) | 0 | 1 | 6 | 0 | 0.0% | 0.0% | — | 1428.9 |
| D2 inline onclick attribute | 0 | 0 | 6 | 0 | — | 0.0% | — | 1.9 |
| D2b onclick property | 0 | 0 | 6 | 0 | — | 0.0% | — | 1.9 |
| D3 tabindex / ARIA | 0 | 0 | 6 | 0 | — | 0.0% | — | 1.9 |
| D4 CSS + lexical | 3 | 0 | 3 | 0 | 100.0% | 50.0% | 66.7% | 1.9 |
| D5 CDP getEventListeners | 3 | 0 | 3 | 0 | 100.0% | 50.0% | 66.7% | 9.5 |
| D6 addEventListener shim | 3 | 0 | 3 | 0 | 100.0% | 50.0% | 66.7% | 2.9 |
| D7 React fiber props | 0 | 0 | 6 | 0 | — | 0.0% | — | 1.9 |
| D8 hover-diff | 0 | 0 | 6 | 0 | — | 0.0% | — | 181.8 |
| D9 behavioural differential | 2 | 0 | 2 | 2 | 100.0% | 33.3% | 50.0% | 2836.1 |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 2 | 0 | 2 | 2 | 100.0% | 33.3% | 50.0% | — |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 2 | 0 | 2 | 2 | 100.0% | 33.3% | 50.0% | 2938.8 |
| D9-noS4 coverage-armed differential, no equivalence filter | 2 | 0 | 2 | 2 | 100.0% | 33.3% | 50.0% | — |
| D9u upstream-style differential (8 channels, keys in sequence) | 0 | 0 | 0 | 8 | — | 0.0% | — | — |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 0 | 0 | 0 | 8 | — | 0.0% | — | — |
| U-D0 upstream crawler candidates | 0 | 0 | 6 | 0 | — | 0.0% | — | 3.7 |
| U-D1 upstream tagged axe attribution | 0 | 1 | 6 | 0 | 0.0% | 0.0% | — | 1452.2 |
| U-D2 upstream inline attributes | 0 | 0 | 6 | 0 | — | 0.0% | — | 4.2 |
| U-D2b upstream mouse handler properties | 0 | 0 | 6 | 0 | — | 0.0% | — | 4.6 |
| U-D3 upstream missing tabindex | 0 | 0 | 6 | 0 | — | 0.0% | — | 4.4 |
| U-D4 upstream CSS and class tokens | 0 | 0 | 4 | 2 | — | 0.0% | — | 5.8 |
| U-D5 upstream direct CDP listeners | 0 | 0 | 4 | 2 | — | 0.0% | — | 12.6 |
| U-D6 upstream registration shim | 0 | 0 | 4 | 2 | — | 0.0% | — | 5.5 |
| U-D7 upstream React mouse props | 0 | 0 | 6 | 0 | — | 0.0% | — | 4.4 |
| U-D8 upstream pixel hover difference | 0 | 0 | 6 | 0 | — | 0.0% | — | 2.5 |

### fixtures — blind-authored synthetic; the suite baseline

| detector | TP | FP | FN | abst. | precision | recall | F1 | ms/button |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 upstream D4|D5|D6, minus Tab | 33 | 18 | 6 | 0 | 64.7% | 84.6% | 73.3% | 10.0 |
| C2 upstream D4|D5|D6|D8, minus Tab | 33 | 20 | 6 | 0 | 62.3% | 84.6% | 71.7% | 237.2 |
| C3 union, reject inert and pointer-events:none | 32 | 13 | 6 | 2 | 71.1% | 82.0% | 76.2% | 242.3 |
| C4 union, additionally reject blocked center | 32 | 11 | 6 | 2 | 74.4% | 82.0% | 78.0% | 242.3 |
| C5 focusable custom mouse control, no observed key handler | 3 | 0 | 36 | 0 | 100.0% | 7.7% | 14.3% | 10.0 |
| C6 visible label for a toggle absent from Tab | 1 | 0 | 38 | 0 | 100.0% | 2.6% | 5.0% | 1.8 |
| C7 ancestor mouse listener, minus Tab | 7 | 3 | 32 | 0 | 70.0% | 17.9% | 28.6% | 10.0 |
| C8 union + focusable + label + ancestor leads | 37 | 13 | 1 | 2 | 74.0% | 94.9% | 83.2% | 242.3 |
| C9 combined leads, additionally reject blocked center | 37 | 11 | 1 | 2 | 77.1% | 94.9% | 85.1% | 242.3 |
| D0 axcess collectClickables | 1 | 1 | 35 | 6 | 50.0% | 2.6% | 4.9% | — |
| D1 axe-core (keyboard rules) | 0 | 1 | 36 | 6 | 0.0% | 0.0% | — | — |
| D10 coverage differential | 35 | 32 | 4 | 2 | 52.2% | 89.7% | 66.0% | — |
| D10a coverage differential (Enter only, no baseline subtraction) | 32 | 24 | 4 | 10 | 57.1% | 82.0% | 67.4% | 866.5 |
| D10a+base coverage differential (Enter only, baseline subtracted) | 32 | 24 | 4 | 10 | 57.1% | 82.0% | 67.4% | — |
| D10a-u upstream coverage presence (sequential keys, baselined) | 34 | 30 | 5 | 4 | 53.1% | 87.2% | 66.0% | — |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 36 | 31 | 0 | 10 | 53.7% | 92.3% | 67.9% | — |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 37 | 35 | 2 | 4 | 51.4% | 94.9% | 66.7% | — |
| D1x axe-core (any rule, unsound) | 18 | 11 | 18 | 6 | 62.1% | 46.2% | 52.9% | — |
| D2 inline onclick attribute | 1 | 0 | 35 | 6 | 100.0% | 2.6% | 5.0% | — |
| D2b onclick property | 4 | 0 | 32 | 6 | 100.0% | 10.3% | 18.6% | — |
| D3 tabindex / ARIA | 2 | 2 | 34 | 6 | 50.0% | 5.1% | 9.3% | — |
| D4 CSS + lexical | 27 | 21 | 9 | 6 | 56.2% | 69.2% | 62.1% | — |
| D5 CDP getEventListeners | 25 | 18 | 11 | 6 | 58.1% | 64.1% | 61.0% | — |
| D6 addEventListener shim | 22 | 19 | 15 | 4 | 53.7% | 56.4% | 55.0% | — |
| D7 React fiber props | 2 | 0 | 34 | 6 | 100.0% | 5.1% | 9.8% | — |
| D8 hover-diff | 18 | 6 | 18 | 6 | 75.0% | 46.2% | 57.1% | — |
| D9 behavioural differential | 34 | 5 | 2 | 20 | 87.2% | 87.2% | 87.2% | — |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 34 | 5 | 2 | 20 | 87.2% | 87.2% | 87.2% | — |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 34 | 9 | 2 | 20 | 79.1% | 87.2% | 82.9% | 1941.5 |
| D9-noS4 coverage-armed differential, no equivalence filter | 34 | 9 | 2 | 20 | 79.1% | 87.2% | 82.9% | — |
| D9-noS4 differential with no equivalence filter | 34 | 9 | 2 | 20 | 79.1% | 87.2% | 82.9% | — |
| D9u upstream-style differential (8 channels, keys in sequence) | 32 | 9 | 4 | 10 | 78.0% | 82.0% | 80.0% | 1482.1 |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 35 | 5 | 4 | 4 | 87.5% | 89.7% | 88.6% | — |
| U-D0 upstream crawler candidates | 1 | 3 | 38 | 0 | 25.0% | 2.6% | 4.7% | 2.9 |
| U-D1 upstream tagged axe attribution | 0 | 0 | 39 | 0 | — | 0.0% | — | 60.0 |
| U-D2 upstream inline attributes | 1 | 0 | 38 | 0 | 100.0% | 2.6% | 5.0% | 3.1 |
| U-D2b upstream mouse handler properties | 4 | 0 | 35 | 0 | 100.0% | 10.3% | 18.6% | 2.9 |
| U-D3 upstream missing tabindex | 1 | 0 | 38 | 0 | 100.0% | 2.6% | 5.0% | 2.8 |
| U-D4 upstream CSS and class tokens | 30 | 17 | 9 | 0 | 63.8% | 76.9% | 69.8% | 3.0 |
| U-D5 upstream direct CDP listeners | 29 | 13 | 10 | 0 | 69.0% | 74.4% | 71.6% | 10.7 |
| U-D6 upstream registration shim | 25 | 13 | 14 | 0 | 65.8% | 64.1% | 64.9% | 2.7 |
| U-D7 upstream React mouse props | 2 | 0 | 37 | 0 | 100.0% | 5.1% | 9.8% | 2.8 |
| U-D8 upstream pixel hover difference | 19 | 9 | 20 | 0 | 67.9% | 48.7% | 56.7% | 267.4 |

### ma11y — Ma11y-generated mutants; 1 verified fault, 6 controls

| detector | TP | FP | FN | abst. | precision | recall | F1 | ms/button |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 upstream D4|D5|D6, minus Tab | 1 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4.3 |
| C2 upstream D4|D5|D6|D8, minus Tab | 1 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 186.3 |
| C3 union, reject inert and pointer-events:none | 0 | 0 | 0 | 1 | — | 0.0% | — | 217.3 |
| C4 union, additionally reject blocked center | 0 | 0 | 0 | 1 | — | 0.0% | — | 217.3 |
| C5 focusable custom mouse control, no observed key handler | 0 | 0 | 1 | 0 | — | 0.0% | — | 4.3 |
| C6 visible label for a toggle absent from Tab | 0 | 0 | 1 | 0 | — | 0.0% | — | 1.3 |
| C7 ancestor mouse listener, minus Tab | 0 | 0 | 1 | 0 | — | 0.0% | — | 4.3 |
| C8 union + focusable + label + ancestor leads | 0 | 0 | 0 | 1 | — | 0.0% | — | 217.3 |
| C9 combined leads, additionally reject blocked center | 0 | 0 | 0 | 1 | — | 0.0% | — | 217.3 |
| D0 axcess collectClickables | 1 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 1.3 |
| D1 axe-core (keyboard rules) | 0 | 0 | 1 | 0 | — | 0.0% | — | 341.9 |
| D10a coverage differential (Enter only, no baseline subtraction) | 0 | 0 | 0 | 4 | — | 0.0% | — | 1630.8 |
| D10a+base coverage differential (Enter only, baseline subtracted) | 0 | 0 | 0 | 4 | — | 0.0% | — | — |
| D10a-u upstream coverage presence (sequential keys, baselined) | 0 | 0 | 0 | 4 | — | 0.0% | — | — |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 0 | 0 | 0 | 4 | — | 0.0% | — | — |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 0 | 0 | 0 | 4 | — | 0.0% | — | — |
| D1x axe-core (any rule, unsound) | 0 | 3 | 1 | 0 | 0.0% | 0.0% | — | 341.9 |
| D2 inline onclick attribute | 0 | 0 | 1 | 0 | — | 0.0% | — | 1.3 |
| D2b onclick property | 0 | 0 | 1 | 0 | — | 0.0% | — | 1.3 |
| D3 tabindex / ARIA | 0 | 0 | 1 | 0 | — | 0.0% | — | 1.3 |
| D4 CSS + lexical | 0 | 0 | 1 | 0 | — | 0.0% | — | 1.3 |
| D5 CDP getEventListeners | 0 | 0 | 1 | 0 | — | 0.0% | — | 3.5 |
| D6 addEventListener shim | 0 | 0 | 1 | 0 | — | 0.0% | — | 2.2 |
| D7 React fiber props | 0 | 0 | 1 | 0 | — | 0.0% | — | 1.3 |
| D8 hover-diff | 0 | 0 | 1 | 0 | — | 0.0% | — | 183.3 |
| D9 behavioural differential | 0 | 0 | 1 | 0 | — | 0.0% | — | 3800.1 |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 0 | 0 | 1 | 0 | — | 0.0% | — | — |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 1 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 3906.7 |
| D9-noS4 coverage-armed differential, no equivalence filter | 1 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | — |
| D9u upstream-style differential (8 channels, keys in sequence) | 0 | 0 | 0 | 4 | — | 0.0% | — | 3678.9 |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 0 | 0 | 0 | 4 | — | 0.0% | — | — |
| U-D0 upstream crawler candidates | 0 | 0 | 1 | 0 | — | 0.0% | — | 3.9 |
| U-D1 upstream tagged axe attribution | 0 | 3 | 1 | 0 | 0.0% | 0.0% | — | 380.9 |
| U-D2 upstream inline attributes | 0 | 0 | 1 | 0 | — | 0.0% | — | 4.1 |
| U-D2b upstream mouse handler properties | 0 | 0 | 1 | 0 | — | 0.0% | — | 3.9 |
| U-D3 upstream missing tabindex | 0 | 0 | 1 | 0 | — | 0.0% | — | 3.7 |
| U-D4 upstream CSS and class tokens | 0 | 0 | 0 | 1 | — | 0.0% | — | 5.4 |
| U-D5 upstream direct CDP listeners | 0 | 0 | 1 | 0 | — | 0.0% | — | 4.5 |
| U-D6 upstream registration shim | 0 | 0 | 1 | 0 | — | 0.0% | — | 3.5 |
| U-D7 upstream React mouse props | 0 | 0 | 1 | 0 | — | 0.0% | — | 4.0 |
| U-D8 upstream pixel hover difference | 0 | 0 | 1 | 0 | — | 0.0% | — | 6.0 |

### edgecases — shared-author development corpus; NO unbiased accuracy claim

| detector | TP | FP | FN | abst. | precision | recall | F1 | ms/button |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| D0 axcess collectClickables | 2 | 0 | 26 | 0 | 100.0% | 7.1% | 13.3% | — |
| D1 axe-core (keyboard rules) | 1 | 1 | 27 | 0 | 50.0% | 3.6% | 6.7% | — |
| D10 coverage differential | 26 | 19 | 2 | 0 | 57.8% | 92.9% | 71.2% | — |
| D1x axe-core (any rule, unsound) | 22 | 13 | 6 | 0 | 62.9% | 78.6% | 69.8% | — |
| D2 inline onclick attribute | 2 | 0 | 26 | 0 | 100.0% | 7.1% | 13.3% | — |
| D2b onclick property | 3 | 0 | 25 | 0 | 100.0% | 10.7% | 19.4% | — |
| D3 tabindex / ARIA | 1 | 0 | 27 | 0 | 100.0% | 3.6% | 6.9% | — |
| D4 CSS + lexical | 25 | 15 | 3 | 0 | 62.5% | 89.3% | 73.5% | — |
| D5 CDP getEventListeners | 22 | 12 | 6 | 0 | 64.7% | 78.6% | 71.0% | — |
| D6 addEventListener shim | 18 | 12 | 10 | 0 | 60.0% | 64.3% | 62.1% | — |
| D7 React fiber props | 0 | 0 | 28 | 0 | — | 0.0% | — | — |
| D8 hover-diff | 1 | 1 | 27 | 0 | 50.0% | 3.6% | 6.7% | — |
| D9 behavioural differential | 26 | 3 | 2 | 8 | 89.7% | 92.9% | 91.2% | — |

## Cost against the 300 ms/button cap

| corpus | detectors timed | at or under 300 ms/button |
|---|---:|---:|
| fixtures | 22 | 19 |
| gds | 32 | 23 |
| ma11y | 34 | 27 |

The cheap tier lands between 1.8 and 11 ms per button. The behavioural arms
(D9 family) run 1,400–2,900 ms per button and are **over the cap by an order of
magnitude** — on GDS, D9 buys one extra true positive over D0 for roughly 1,500×
the per-button cost.

## Corrections carried into this document

1. **C16's published 100% precision is an artifact of a filtered run.** The
   saved `effect2.json` observed 42 of 95 probes (the C12 lead set). R9 promotes
   from the whole universe but can only promote what was observed; observing all
   95 promotes 11 more, every one labelled `ok`, giving **38 TP / 11 FP =
   77.6%**, not 100%. Re-running under the original filter reproduces the
   published 38/0/0 exactly, so the port is faithful and the number is scoped.

2. **The harness capped the tab walk at 300 presses on a 306-element page.**
   `bakeoff.py` called `compute_tab_order()` with the frozen default, so 5 of 6
   GDS violations came back `unknown` — a budget limit reported as absence of
   evidence. The cap is now derived per page; the frozen detector's own default
   is untouched, and fixtures reproduces its published numbers unchanged.

3. **Ma11y yields one verified fault, not four.** F59 does not exist in Ma11y
   (404). F54 is inapplicable to the GDS page, which has zero inline `onclick`
   attributes — the exact attribute Ma11y's own `applicable()` requires. F42's
   generated span never fires on a trusted click, so it is not an IAF and was
   **excluded rather than labelled**, since a violation nobody can detect
   penalises every detector for missing a fault that is not there.

4. **The ma11y arm is a sanity check, not a benchmark.** One violation and six
   controls cannot support a precision/recall comparison, and its rows should be
   read as "does this detector fire on a known-good fault" only.

5. **edgecases is a shared-author corpus.** Its rows are included for
   completeness and carry **no unbiased accuracy claim**. Its stage-B run also
   hit a pre-existing CDP limit (`CBOR: stack limit exceeded`), unrelated to any
   change here, so its detector count is lower than the others.

## Reproducing

```
uv run --offline --no-sync python -m tools.build_gds_corpus
uv run --offline --no-sync python -m tools.build_ma11y_corpus
uv run --offline --no-sync python -m tools.verify_ma11y_corpus
bash tools/run_matrix.sh
uv run --offline --no-sync python -m tools.assemble_matrix
```
