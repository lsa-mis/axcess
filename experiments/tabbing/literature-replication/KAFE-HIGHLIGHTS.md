# Highlights: Axcess vs KAFE on KAFE's own benchmark

One page. Full table in [`KAFE-MATRIX.md`](KAFE-MATRIX.md), methodology and
caveats in [`KAFE-MATRIX-REPORT.md`](KAFE-MATRIX-REPORT.md).

**Benchmark:** the 60 subjects of KAFE's own ESEC/FSE 2021 evaluation corpus,
replayed offline from their mitmproxy captures.
**Paper:** Chiou, Alotaibi & Halfond, *Detecting and Localizing Keyboard
Accessibility Failures in Web Applications*, ESEC/FSE 2021, DOI
[10.1145/3468264.3468581](https://doi.org/10.1145/3468264.3468581).
**Their detector's result** comes from their published per-subject CSV, which
reproduces their paper's Table 1 exactly (36/3/0/21 → 92.3% / 100.0% over n=60).

## The headline: no Axcess detector beats KAFE

Scored on the same 39 subjects, KAFE posts **96.0% precision, 100% recall, 25.7 ms
per button**. Nothing in the suite matches that combination.

| | detector | TP | FP | FN | precision | recall (decided) | F1 | ms/button |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **reference** | **KAFE** | 24 | 1 | 0 | **96.0%** | **100.0%** | **98.0%** | **25.7** |
| best Axcess F1 | D9+S4ours | 23 | 8 | 0 | 74.2% | 100.0% | 85.2% | 1353.6 |
| best cheap | D5 CDP getEventListeners | 20 | 5 | 2 | 80.0% | 90.9% | 85.1% | **3.2** |
| best precision w/ recall | U-D5 upstream direct CDP listeners | 16 | 1 | 5 | 94.1% | 76.2% | 84.2% | 7.8 |
| best C-rule | C15 / C16 | 18 | 4 | 3 | 81.8% | 85.7% | 83.7% | 354.8 |

KAFE's F1 is **98.0%**. The best Axcess row is **85.2%**, and it pays 53× the
per-button cost to get there.

**"Recall (decided)" is not strict recall.** On this corpus recall is
TP / (TP + FN) over the subjects each detector *decided*; a subject it
abstained on is left out, not counted as a miss. The strict recall in
`MATRIX-RESULTS.md` (TP over every labelled defect, abstentions included) is not
available here: `derived/kafe_matrix_summary.json` records a detector's
abstentions as one count, not split by KAFE label, so neither strict recall nor
the unknown-positive / unknown-negative split can be read from the artifacts.
They were never computed, and no figure here should be compared with a strict
recall as though it were one.

## Where Axcess does win: cost

| | KAFE | Axcess |
|---|---|---|
| ms per button | 25.7 | **0.1** (D0, D2, D2b, D3, D4) |
| detectors under the 300 ms cap | 39/39 subjects (their amortised `Detection` ÷ visible ctrl nodes) | **33 of 46 rows** (35 of 48 counting D7 and U-D7) |
| detectors faster than KAFE | — | **28 of 46** (30 of 48 counting D7 and U-D7) |

The 46 are the rows with a defined precision; D7 and U-D7 flag no subject, so
their precision is undefined, and both are fast. Neither side's ms/button is
latency measured one button at a time: ours is harness time divided by
candidates, theirs is their `Detection` column divided by their control count,
on different hardware with a different instrument.

D4 CSS + lexical achieves **100% recall (decided) at 0.1 ms/button** — 257×
faster than KAFE — but at 63.2% precision (14 false positives against KAFE's 1).

**19 detectors post 100% recall over the subjects they decided.** That is not
strict recall and not a match for KAFE's: KAFE decided all 39, while D9, for
example, abstained on 22 of 52 attempted. None of the 19 matches KAFE's
precision. The suite finds the failures it looks at; it disagrees with KAFE
about what else is a failure.

## Five detectors beat KAFE's precision, none usefully

| detector | TP | FP | precision | recall (decided) | ms/button |
|---|---:|---:|---:|---:|---:|
| D6 addEventListener shim | 2 | 0 | 100.0% | 9.1% | 0.2 |
| C5 focusable custom mouse control | 3 | 0 | 100.0% | 14.3% | 8.0 |
| U-D2 upstream inline attributes | 4 | 0 | 100.0% | 19.0% | 5.7 |
| U-D3 upstream missing tabindex | 7 | 0 | 100.0% | 33.3% | 5.7 |
| U-D6 upstream registration shim | 11 | 0 | 100.0% | 52.4% | 5.7 |

All five reach 100% precision by flagging almost nothing. U-D6 is the only one
with real coverage, and it still misses half the corpus.

## The C-rules do not transfer

On the fixtures corpus `MATRIX-RESULTS.md` carries three rows for these two
rules (element precision / strict recall):

| fixtures row | precision | strict recall |
|---|---:|---:|
| C15 | 100.0% | 94.9% |
| C16, R9 observed on 42 of 95 probes (the C12 lead set) | 100.0% | 97.4% |
| C16, R9 observed on all 95 probes | 77.6% | 97.4% |

Here both score **81.8% page precision / 85.7% recall (decided)** — an
18.2-point precision drop from the two 100% rows. The recall figures are not
the same measure (strict on fixtures, decided-only here), so no recall delta is
quoted. Element and page precision are not the same unit either; the drop is
the direction of travel, not a like-for-like difference.

That is the honest measure of how much those rules were fitted to fixtures. Every
rule R1–R9 was written after reading a specific error on a 95-probe corpus whose
labels were visible. `CHEAP_DETECTOR_REVIEW.md` said so in its own words; this is
the first measurement on a corpus nobody here authored, and it confirms it.

C15 and C16 also produce **identical rows** — R9's divergent-key-effect promotion
changes no subject's verdict in this corpus.

## The cheap C-rules, C10–C16, end to end

These are the rules `CHEAP_DETECTOR_REVIEW.md` leads with. On KAFE's corpus:

| rule | TP | FP | FN | precision | recall (decided) | ms/button |
|---|---:|---:|---:|---:|---:|---:|
| C10 = C9 − redundant click surfaces (R1) | 19 | 8 | 2 | 70.4% | 90.5% | 8.3 |
| C11 = C10 − roving tabindex (R2) | 19 | 8 | 2 | 70.4% | 90.5% | 8.5 |
| C12 = C11 − declared shortcuts (R3) | 19 | 8 | 2 | 70.4% | 90.5% | 8.5 |
| C13 = C12 − no action path (R5) | 19 | 7 | 2 | 73.1% | 90.5% | 111.4 |
| C14 = C13 − name-twinned leads (R6) | 19 | 7 | 2 | 73.1% | 90.5% | 111.4 |
| C15 = C14 − no click effect (R7, R8) | 18 | 4 | 3 | 81.8% | 85.7% | 354.8 |
| C16 = C15 + divergent key effect (R9) | 18 | 4 | 3 | 81.8% | 85.7% | 354.8 |

Read against their fixtures figures, this is the whole story of the cheap rules:

| | fixtures (development): element precision / strict recall | KAFE (unseen): page precision / recall (decided) | precision delta |
|---|---|---|---|
| C13 | 90.2% / 94.9% | 73.1% / 90.5% | **−17.1** |
| C15 | 100% / 94.9% | 81.8% / 85.7% | **−18.2** |
| C16 (R9 on 42 of 95) | 100% / 97.4% | 81.8% / 85.7% | **−18.2** |
| C16 (R9 on 95 of 95) | 77.6% / 97.4% | 81.8% / 85.7% | +4.2 |

No recall delta is given: strict recall and recall over decided subjects are
different measures (see the note under the headline table).

**R2, R3, R6 and R9 have no effect here** — C10 = C11 = C12, C13 = C14 and
C15 = C16 are identical rows. R2 and R3 were each written to clear one fixture
probe (`h171`, `h172`) and R6 one more (`h140`); none of those patterns changes
a verdict here.

**R1, R5 and R7/R8 change the result.** R1 does the most work of any rule:
C9 → C10 goes 21/15/0/0 → 19/8/2/7 (TP/FP/FN/TN), removing 7 false positives
at the cost of 2 true positives. R5 removes 1 FP (C12 → C13), and R7/R8 remove
3 more at the cost of 1 TP (C14 → C15, with one more abstention). C10 costs
8.3 ms/button in total; C15, the first row carrying R7/R8, costs 354.8
ms/button — over the 300 ms cap, and 3× C14's 111.4 ms for 8.7 points of
precision.

**On the gds and ma11y corpora C10–C16 are all zero**, because each is *C9 minus
a rule* and C9 itself abstains on everything there. Those rows measure C9's
abstention, not the rules. See the note under each table in `MATRIX-RESULTS.md`.

## Caveats that materially affect the numbers

1. **Page-level scoring flatters everything.** KAFE labels pages, not elements, so
   a detector flagging 20 elements where 1 is real still scores a page-level true
   positive. Element-level precision lives in `MATRIX-RESULTS.md`, not here.
2. **39 of 60 subjects scored.** 7 excluded before the run (2 corrupt captures, 5
   folder-form asset dumps), 13 whole-subject abstentions, and 1 (`craigslist`)
   with no result: three attempts were lost to a hang, a manual kill and a
   backend restart, so it was never measured and is not an abstention. Every
   exclusion is named with a reason in the report; **none is counted as a
   negative**, which would have manufactured false negatives in all 48 rows.
3. **KAFE's row is their reported output, not a reproduction.** Their Java /
   Selenium 3.141.5 / Firefox 68 stack was not rebuilt. Their CSV reconciles with
   their paper, which verifies arithmetic, not their tool.
4. **The candidate universe is Axcess's own collector**, so upstream `U-D*` and
   `C*` rules cannot propose an element it missed. Measured against KAFE's own
   node counts, the Axcess universe is a median **1.78× larger** and smaller on
   only 1 of 16 checked subjects — so the bound is real but not binding, except
   on `tinyurl`. Containment is unproven: KAFE's node-selection code was never
   published.
5. **ms is not measured the same way on both sides.** Axcess timings are measured
   browser work in this harness; KAFE's is their `Detection` column divided by
   their visible-control-node count, on 2019 hardware. Treat the cost comparison
   as order-of-magnitude.

## Controls

All four pass, recorded in `derived/kafe_matrix_controls.json`:

| control | result |
|---|---|
| KAFE reproduction | 36/3/0/21 → 92.3% / 100.0%, matches published Table 1 |
| denominator | 60 → 7 excluded → 52 attempted → 13 abstained → **39 scored**, each named |
| negative control | on a KAFE-`FALSE` subject, 31 detectors record a true negative, 0 abstain |
| frozen code | all detectors imported from `src/audit/analyzer/keyboard/kbdiff/`; `git diff` on `src/audit/` empty |
