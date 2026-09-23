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

Scored on the same 40 subjects, KAFE posts **96.2% precision and 100% recall**.
It decided all 40, so that is both its strict recall and its recall over decided
subjects. Nothing in the suite matches that accuracy.

| | detector | TP | FP | FN | precision | strict recall | recall (decided) | F1 (decided recall) | ms/button |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **reference** | **KAFE** | 25 | 1 | 0 | **96.2%** | **100.0%** | **100.0%** | **98.0%** | **19978.6** (full pipeline) |
| best Axcess F1 (tied) | D9+S4ours | 24 | 8 | 0 | 75.0% | 96.0% | 100.0% | 85.7% | 1428.7 |
| best Axcess F1 (tied), and best cheap | D5 CDP getEventListeners | 21 | 5 | 2 | 80.8% | 84.0% | 91.3% | 85.7% | **3.2** |
| best precision w/ recall | U-D5 upstream direct CDP listeners | 17 | 1 | 5 | 94.4% | 68.0% | 77.3% | 85.0% | 7.3 |
| best C-rule | C15 / C16 | 19 | 4 | 3 | 82.6% | 76.0% | 86.4% | 84.4% | 337.7 |

KAFE's F1 is **98.0%**. The best Axcess F1 is **85.7%**, and since `craigslist`
was scored it is **a tie**. D9+S4ours and D5 both score exactly 6/7. On the 39
subjects before it, D9+S4ours led alone (85.2% against D5's 85.1%). Every F1
here uses recall over decided subjects. With strict recall the tie breaks:
D9+S4ours is 84.2% and D5 82.4%, so D9+S4ours stays the best Axcess row on that
basis. D9+S4ours costs about a fourteenth of KAFE's full pipeline per button
(1428.7 against 19,978.6 ms). D5 matches its F1 at 3.2 ms, about 1/450 of
D9+S4ours's cost.

**Two recalls.** `strict recall` is TP over all 25 KAFE-positive subjects among
the 40 scored, so an abstention on one counts as a miss. `recall (decided)` is
TP / (TP + FN) over the subjects each detector *decided*; a subject it abstained
on is left out. Both come from each detector's per-subject verdicts in
`derived/kafe_matrix.jsonl`, via `KAFE-MATRIX.md`, which also gives the
unknown-positive / unknown-negative split. The fixtures' strict recall in
`MATRIX-RESULTS.md` is the same measure as `strict recall` here, though on
elements rather than pages.

## Where Axcess does win: cost

KAFE's cost comes from KAFE's own per-subject timing logs, pooled over the 40
subjects' visible controls. **The full pipeline is the comparable figure**:
KAFE's verdict needs both of its graph crawls, just as every Axcess figure
includes that detector's own browser work (navigation, tab walks, behavioural
passes). KAFE's Type 1 detection step alone runs after the crawls, excludes
them, and is shown only so it is not mistaken for the cost.

| | KAFE | Axcess |
|---|---|---|
| ms per button, **full pipeline** (comparable) | **19,978.6** (both crawls + Type 1 detection) | **0.1** (D0, D2, D2b, D3, D4); highest row 1715.6 |
| ms per button, Type 1 detection alone (**not** comparable) | 73.4 | — |
| under the 300 ms cap | full pipeline: **0 of 40 subjects**. Detection alone: 35 of 40 | **33 of 46 rows** (35 of 48 counting D7 and U-D7) |
| cheaper per button than KAFE's full pipeline | — | **46 of 46** (48 of 48 counting D7 and U-D7) |
| cheaper than KAFE's detection step alone (not comparable) | — | 28 of 46 (30 of 48) |

The 46 are the rows with a defined precision; D7 and U-D7 flag no subject, so
their precision is undefined, and both are fast. 44.8% of KAFE's full pipeline
here is proxy start-up, which no Axcess figure includes. Without it KAFE's
figure is still 11,036.6 ms per button, above every Axcess row. Neither side's
ms/button is latency measured one button at a time. Ours is harness time
divided by candidates; theirs is their logged time divided by their control
count, on different hardware with a different instrument.

D4 CSS + lexical achieves **100% strict recall at 0.1 ms/button**, five orders
of magnitude below KAFE's full pipeline, but at 64.1% precision (14 false
positives against KAFE's 1).

**19 detectors post 100% recall over the subjects they decided, and 6 post
100% strict recall** (D4, D9+S4u, D9-noS4, D10a, D10a+base, D10b). The other
13 abstained on at least one KAFE-positive subject; D9, for example, abstained
on 2 of them (22 of 53 attempted overall). None of the 19 matches KAFE's
precision. The suite finds the failures it looks at; it disagrees with KAFE
about what else is a failure.

## Five detectors beat KAFE's precision, none usefully

| detector | TP | FP | precision | strict recall | recall (decided) | ms/button |
|---|---:|---:|---:|---:|---:|---:|
| D6 addEventListener shim | 2 | 0 | 100.0% | 8.0% | 8.7% | 0.2 |
| C5 focusable custom mouse control | 3 | 0 | 100.0% | 12.0% | 13.6% | 7.5 |
| U-D2 upstream inline attributes | 4 | 0 | 100.0% | 16.0% | 18.2% | 5.2 |
| U-D3 upstream missing tabindex | 7 | 0 | 100.0% | 28.0% | 31.8% | 5.2 |
| U-D6 upstream registration shim | 12 | 0 | 100.0% | 48.0% | 54.5% | 5.2 |

All five reach 100% precision by flagging almost nothing. U-D6 is the only one
with real coverage, and it still misses more than half of the 25 KAFE-positive
subjects (strict recall 48.0%).

## The C-rules do not transfer

On the fixtures corpus `MATRIX-RESULTS.md` carries three rows for these two
rules (element precision / strict recall):

| fixtures row | precision | strict recall |
|---|---:|---:|
| C15 | 100.0% | 94.9% |
| C16, R9 observed on 42 of 95 probes (the C12 lead set) | 100.0% | 97.4% |
| C16, R9 observed on all 95 probes | 77.6% | 97.4% |

Here both score **82.6% page precision / 76.0% strict recall** (86.4% recall
over decided subjects). That is a 17.4-point precision drop from the two 100%
rows, and a strict-recall drop of 18.9 points from C15's 94.9% and 21.4 from
C16's 97.4%. Strict recall is now the same measure on both sides, but element
and page are not the same unit. The drops are the direction of travel, not a
like-for-like difference.

That is the honest measure of how much those rules were fitted to fixtures. Every
rule R1–R9 was written after reading a specific error on a 95-probe corpus whose
labels were visible. `CHEAP_DETECTOR_REVIEW.md` said so in its own words; this is
the first measurement on a corpus nobody here authored, and it confirms it.

C15 and C16 also produce **identical rows** — R9's divergent-key-effect promotion
changes no subject's verdict in this corpus.

## The cheap C-rules, C10–C16, end to end

These are the rules `CHEAP_DETECTOR_REVIEW.md` leads with. On KAFE's corpus:

| rule | TP | FP | FN | precision | strict recall | recall (decided) | ms/button |
|---|---:|---:|---:|---:|---:|---:|---:|
| C10 = C9 − redundant click surfaces (R1) | 20 | 8 | 2 | 71.4% | 80.0% | 90.9% | 7.8 |
| C11 = C10 − roving tabindex (R2) | 20 | 8 | 2 | 71.4% | 80.0% | 90.9% | 8.0 |
| C12 = C11 − declared shortcuts (R3) | 20 | 8 | 2 | 71.4% | 80.0% | 90.9% | 8.0 |
| C13 = C12 − no action path (R5) | 20 | 7 | 2 | 74.1% | 80.0% | 90.9% | 110.0 |
| C14 = C13 − name-twinned leads (R6) | 20 | 7 | 2 | 74.1% | 80.0% | 90.9% | 110.0 |
| C15 = C14 − no click effect (R7, R8) | 19 | 4 | 3 | 82.6% | 76.0% | 86.4% | 337.7 |
| C16 = C15 + divergent key effect (R9) | 19 | 4 | 3 | 82.6% | 76.0% | 86.4% | 337.7 |

Every one of these abstains on the same 3 KAFE-positive subjects (`godaddy`,
`thefreedictionary`, `wendys`), where the candidate arm raised. That is the
whole gap between the two recalls. C15 and C16 also abstain on one negative
(`dmv_ca`), which affects neither recall.

Read against their fixtures figures, this is the whole story of the cheap rules:

| | fixtures (development): element precision / strict recall | KAFE (unseen): page precision / strict recall (decided) | precision delta | strict-recall delta |
|---|---|---|---|---|
| C13 | 90.2% / 94.9% | 74.1% / 80.0% (90.9%) | **−16.1** | −14.9 |
| C15 | 100% / 94.9% | 82.6% / 76.0% (86.4%) | **−17.4** | −18.9 |
| C16 (R9 on 42 of 95) | 100% / 97.4% | 82.6% / 76.0% (86.4%) | **−17.4** | −21.4 |
| C16 (R9 on 95 of 95) | 77.6% / 97.4% | 82.6% / 76.0% (86.4%) | +5.0 | −21.4 |

The recall delta is strict against strict. Element and page remain different
units, so both deltas give the direction, not a like-for-like difference.

**R2, R3, R6 and R9 have no effect here** — C10 = C11 = C12, C13 = C14 and
C15 = C16 are identical rows. R2 and R3 were each written to clear one fixture
probe (`h171`, `h172`) and R6 one more (`h140`); none of those patterns changes
a verdict here.

**R1, R5 and R7/R8 change the result.** R1 does the most work of any rule:
C9 → C10 goes 22/15/0/0 → 20/8/2/7 (TP/FP/FN/TN), removing 7 false positives
at the cost of 2 true positives. R5 removes 1 FP (C12 → C13), and R7/R8 remove
3 more at the cost of 1 TP (C14 → C15, with one more abstention). C10 costs
7.8 ms/button in total; C15, the first row carrying R7/R8, costs 337.7
ms/button — over the 300 ms cap, and 3× C14's 110.0 ms for 8.5 points of
precision.

**On the gds and ma11y corpora C10–C16 are all zero**, because each is *C9 minus
a rule* and C9 itself abstains on everything there. Those rows measure C9's
abstention, not the rules. See the note under each table in `MATRIX-RESULTS.md`.

## Caveats that materially affect the numbers

1. **Page-level scoring flatters everything.** KAFE labels pages, not elements, so
   a detector flagging 20 elements where 1 is real still scores a page-level true
   positive. Element-level precision lives in `MATRIX-RESULTS.md`, not here.
2. **40 of 60 subjects scored.** 7 excluded before the run (2 corrupt captures, 5
   folder-form asset dumps) and 13 whole-subject abstentions. All 53 replayable
   subjects were attempted. `craigslist`, lost on three earlier attempts to a
   hang, a manual kill and a backend restart, was scored on its fourth. Every
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
   browser work in this harness. KAFE's are from their own per-subject timing
   logs (full pipeline, and Type 1 detection alone), divided by their
   visible-control-node count, on 2019 hardware. Treat the cost comparison as
   order-of-magnitude. An earlier version of this page quoted KAFE's cost from
   the results CSV's `Detection` column, which is not a per-subject detection
   time. That figure is withdrawn; `FINAL-REPORT.md` §8.4 gives the evidence.

## Controls

All four pass, recorded in `derived/kafe_matrix_controls.json`:

| control | result |
|---|---|
| KAFE reproduction | 36/3/0/21 → 92.3% / 100.0%, matches published Table 1 |
| denominator | 60 → 7 excluded → 53 replayable → 53 attempted → 13 abstained → **40 scored**, each named |
| negative control | on a KAFE-`FALSE` subject, 31 detectors record a true negative, 0 abstain |
| frozen code | all detectors imported from `src/audit/analyzer/keyboard/kbdiff/`; `git diff` on `src/audit/` empty |
