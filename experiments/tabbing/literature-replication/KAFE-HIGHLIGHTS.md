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

| | detector | TP | FP | FN | precision | recall | F1 | ms/button |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **reference** | **KAFE** | 24 | 1 | 0 | **96.0%** | **100.0%** | **98.0%** | **25.7** |
| best Axcess F1 | D9+S4ours | 23 | 8 | 0 | 74.2% | 100.0% | 85.2% | 1353.6 |
| best cheap | D5 CDP getEventListeners | 20 | 5 | 2 | 80.0% | 90.9% | 85.1% | **3.2** |
| best precision w/ recall | U-D5 upstream direct CDP listeners | 16 | 1 | 5 | 94.1% | 76.2% | 84.2% | 7.8 |
| best C-rule | C15 / C16 | 18 | 4 | 3 | 81.8% | 85.7% | 83.7% | 354.8 |

KAFE's F1 is **98.0%**. The best Axcess row is **85.2%**, and it pays 53× the
per-button cost to get there.

## Where Axcess does win: cost

| | KAFE | Axcess |
|---|---|---|
| ms per button | 25.7 | **0.1** (D0, D2, D2b, D3, D4) |
| detectors under the 300 ms cap | 39/39 subjects | **33 of 46 rows** |
| detectors faster than KAFE | — | **29 of 46** |

D4 CSS + lexical achieves **100% recall at 0.1 ms/button** — 257× faster than
KAFE — but at 63.2% precision (14 false positives against KAFE's 1).

**17 detectors match KAFE's 100% recall.** None matches its precision while
doing so. The suite finds the failures; it disagrees with KAFE about what else
is a failure.

## Five detectors beat KAFE's precision, none usefully

| detector | TP | FP | precision | recall | ms/button |
|---|---:|---:|---:|---:|---:|
| D6 addEventListener shim | 2 | 0 | 100.0% | 9.1% | 0.2 |
| C5 focusable custom mouse control | 3 | 0 | 100.0% | 14.3% | 8.0 |
| U-D2 upstream inline attributes | 4 | 0 | 100.0% | 19.0% | 5.7 |
| U-D3 upstream missing tabindex | 7 | 0 | 100.0% | 33.3% | 5.7 |
| U-D6 upstream registration shim | 11 | 0 | 100.0% | 52.4% | 5.7 |

All five reach 100% precision by flagging almost nothing. U-D6 is the only one
with real coverage, and it still misses half the corpus.

## The C-rules do not transfer

On the fixtures corpus C15/C16 score **100% precision, 97.4% recall**. Here they
score **81.8% / 85.7%** — a 18-point precision drop and 12 points of recall.

That is the honest measure of how much those rules were fitted to fixtures. Every
rule R1–R9 was written after reading a specific error on a 95-probe corpus whose
labels were visible. `CHEAP_DETECTOR_REVIEW.md` said so in its own words; this is
the first measurement on a corpus nobody here authored, and it confirms it.

C15 and C16 also produce **identical rows** — R9's divergent-key-effect promotion
fires on nothing in this corpus.

## Caveats that materially affect the numbers

1. **Page-level scoring flatters everything.** KAFE labels pages, not elements, so
   a detector flagging 20 elements where 1 is real still scores a page-level true
   positive. Element-level precision lives in `MATRIX-RESULTS.md`, not here.
2. **39 of 60 subjects scored.** 7 excluded before the run (2 corrupt captures, 5
   folder-form asset dumps), 13 whole-subject abstentions, 1 not attempted. Every
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
