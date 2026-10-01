# NavA11y focus dataset: how it is scored (written before the first run)

Detector code is frozen in `FREEZE.sha256` (commit `c549a4c`). The first run
of `score_nava11y.py` against that code is the **held-out result** and is
reported as it comes out. Only the 16 `contributed` pages are new to this
project; the 6 `original` pages are GDS cases already read while the focus
rules were written, so they are development pages from the start.

**Ground truth.** `ground_truth.json`, extracted verbatim from NavA11y's
`evaluation/run-gds-evaluation.mjs` (MIT, commit `d19e182`): 22 pages, each
with expected `PASS`/`FAIL` verdicts for one or more criteria. A criterion a
page does not list is not scored on that page.

**What runs on each page** (`file://`, 1280 × 900): exactly what a default
scan runs with the keyboard check, focus check and Click-Through on —
`KeyboardProbe` with the Standard operability check, `FocusProbe`, and
`InteractionProbe` with dialog checks.

**Page verdict per criterion: FAIL if any rule mapped to it fires on the page.**

| criterion | Axcess rules counted |
|---|---|
| 2.4.7 Focus Visible | `focus-not-visible` |
| 2.4.3 Focus Order | `focus-order-positive-tabindex`, `focus-order-non-interactive-stop`, `focus-order-visual-mismatch`, `keyboard-dialog-focus-not-moved`, `keyboard-dialog-focus-escapes` |
| 2.4.11 Focus Not Obscured (Minimum) | `focus-not-obscured` |
| 2.4.12 Focus Not Obscured (Enhanced) | `focus-not-obscured` (a covered centre is also "not entirely visible") |
| 2.4.13 Focus Appearance | none: Axcess has no rule, so it can only score PASS |

**Two scores.** *Strict*: the table above. *Defect-level*: the same, plus the
trap rules (`keyboard-trap-stuck`, `keyboard-dialog-no-keyboard-exit`) for
2.4.3, because NavA11y files its keyboard-trap page under 2.4.3 while Axcess
files traps under 2.1.2. Strict is the headline.

Precision, recall and F1 are over page × criterion pairs, as NavA11y's own
evaluator computes them.
