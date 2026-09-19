# KAFE's benchmark, all 48 Axcess detectors and KAFE's own result

Generated 2026-09-19T15:36:51.760508+00:00 by `tools/kafe_matrix.py assemble`, from
`derived/kafe_matrix.jsonl` (one checkpoint per subject).

## Provenance

| | |
|---|---|
| benchmark | the 60 subjects of KAFE's own evaluation corpus, replayed offline from their mitmproxy captures |
| paper | Chiou, Alotaibi & Halfond, *Detecting and Localizing Keyboard Accessibility Failures in Web Applications*, ESEC/FSE 2021 |
| DOI | [10.1145/3468264.3468581](https://doi.org/10.1145/3468264.3468581) |
| KAFE's published Table 1 (Type 1 detection) | **92% precision, 100% recall** |
| KAFE's result recomputed here from `artifacts/kafe_results_to_reproduce.csv` | **TP 36, FP 3, FN 0, TN 21 over n=60 — 92.3% / 100.0%** |
| KAFE's detector | their published per-subject CSV. That file **is** their tool's output on their corpus; the Java/Selenium/Firefox-68 stack was not rebuilt |
| Axcess detectors | imported unmodified from `src/audit/analyzer/keyboard/kbdiff/` — see control 4 |
| scoring unit | **the page**, because KAFE labels pages, not elements |
| subjects scored | **39 of 52 attempted, of 60 in the corpus** — see control 2 |

## Read this before the table

**Page-level scoring discards element precision.** A detector that flags 20
elements on a page where 1 is really inoperable scores exactly the same
page-level true positive as a detector that flags only the real one. Every
precision figure below is therefore *page* precision against KAFE's page label,
and it is a much weaker claim than element precision. On a real page with
hundreds of candidates, "flagged at least one element" is close to free, and
rows near the corpus base rate should be read as evidence of that, not of skill.

**Abstention is never a negative, and a negative requires a complete look.**
A page is positive for a detector iff it flagged at least one element — a
finding is evidence whatever else went unread. A page is *negative* only where
the detector flagged nothing **and left no candidate undecided**. Anything in
between is an abstention. That strictness is not pedantry: on `godaddy` only 4
of 21 candidates survived to a second page load, and the permissive rule turned
that into twelve confident "no defect here" verdicts off four elements. The
permissive numbers are reported in full in `KAFE-MATRIX-REPORT.md` so the size of
the difference is visible rather than asserted.

A subject that would not replay, whose tab walk capped, or whose arm raised
abstains for every row. For every Axcess row,
`TP + FP + FN + TN + abst. = 52`, the subjects attempted.
**The KAFE row's `abst.` is 0 and that is literal** — KAFE decided every subject
in its own CSV. Its row is *restricted* to the 39 subjects this
replication scored, so the two sides are read on one denominator; the
13 subjects Axcess could not put in front of it are named in
control 2, not charged to KAFE.

**Both ms columns are computed the same way on both sides.**
`ms/button` is measured browser time divided by the number of controls probed —
for Axcess the candidates it addressed, for KAFE their own
`Size of All Visible Ctrl Nodes`. This is the unit KAFE's 300 ms cap is stated
in. `ms/subject` is total measured time for one subject. KAFE's figures come
from their `Detection` column, pooled the same way.

**The candidate universe is Axcess's own.** `data-probe` could only be placed on
the elements `audit.analyzer.keyboard.kbdiff.candidates.collect_candidates`
surfaced, because `candidate_analysis.measure_candidate_page` requires its
feature sweep to cover exactly the probe set. No detector below could propose an
element that collector did not surface, which flatters the D0/C families. This
is the largest unclosed threat to validity in the table and is discussed in
`KAFE-MATRIX-REPORT.md`.

## The table

| detector | TP | FP | FN | TN | abst. | precision | recall | F1 | ms/button | ms/subject | ms covers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 17 | 9 | 5 | 5 | 16 | 65.4% | 77.3% | 70.8% | 0.1 | 17.8 | survey + method |
| D1 axe-core (keyboard rules) | 2 | 1 | 20 | 12 | 17 | 66.7% | 9.1% | 16.0% | 2.9 | 366.2 | survey + method |
| D1x axe-core (any rule, unsound) | 22 | 11 | 1 | 2 | 16 | 66.7% | 95.7% | 78.6% | 2.9 | 366.3 | survey + method |
| D2 inline onclick attribute | 5 | 2 | 17 | 11 | 17 | 71.4% | 22.7% | 34.5% | 0.1 | 18.2 | survey + method |
| D2b onclick property | 12 | 3 | 10 | 10 | 17 | 80.0% | 54.5% | 64.9% | 0.1 | 18.2 | survey + method |
| D3 tabindex / ARIA | 9 | 1 | 13 | 12 | 17 | 90.0% | 40.9% | 56.3% | 0.1 | 18.2 | survey + method |
| D4 CSS + lexical | 24 | 14 | 0 | 0 | 14 | 63.2% | 100.0% | 77.4% | 0.1 | 17.1 | survey + method |
| D5 CDP getEventListeners | 20 | 5 | 2 | 8 | 17 | 80.0% | 90.9% | 85.1% | 3.2 | 399.7 | survey + method |
| D6 addEventListener shim | 2 | 0 | 20 | 13 | 17 | 100.0% | 9.1% | 16.7% | 0.2 | 20.6 | survey + method |
| D7 React fiber props | 0 | 0 | 22 | 13 | 17 | undefined: flagged no subject | 0.0% | undefined: precision undefined [^f1] | 0.1 | 18.2 | survey + method |
| D8 hover-diff | 17 | 9 | 5 | 5 | 16 | 65.4% | 77.3% | 70.8% | 124.5 | 15383.7 | survey + method |
| U-D0 upstream crawler candidates | 11 | 3 | 10 | 12 | 16 | 78.6% | 52.4% | 62.9% | 5.7 | 701.8 | shared + method |
| U-D1 upstream tagged axe attribution | 20 | 8 | 1 | 7 | 16 | 71.4% | 95.2% | 81.6% | 8.6 | 1046.1 | shared + method |
| U-D2 upstream inline attributes | 4 | 0 | 17 | 15 | 16 | 100.0% | 19.0% | 32.0% | 5.7 | 702.2 | shared + method |
| U-D2b upstream mouse handler properties | 9 | 1 | 12 | 14 | 16 | 90.0% | 42.9% | 58.1% | 5.7 | 701.9 | shared + method |
| U-D3 upstream missing tabindex | 7 | 0 | 14 | 15 | 16 | 100.0% | 33.3% | 50.0% | 5.7 | 701.9 | shared + method |
| U-D4 upstream CSS and class tokens | 21 | 14 | 0 | 1 | 16 | 60.0% | 100.0% | 75.0% | 5.7 | 702.4 | shared + method |
| U-D5 upstream direct CDP listeners | 16 | 1 | 5 | 14 | 16 | 94.1% | 76.2% | 84.2% | 7.8 | 948.0 | shared + method |
| U-D6 upstream registration shim | 11 | 0 | 10 | 15 | 16 | 100.0% | 52.4% | 68.8% | 5.7 | 701.9 | shared + method |
| U-D7 upstream React mouse props | 0 | 0 | 21 | 15 | 16 | undefined: flagged no subject | 0.0% | undefined: precision undefined [^f1] | 5.7 | 702.1 | shared + method |
| U-D8 upstream pixel hover difference | 15 | 14 | 6 | 1 | 16 | 51.7% | 71.4% | 60.0% | 104.9 | 12828.3 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 21 | 14 | 0 | 1 | 16 | 60.0% | 100.0% | 75.0% | 7.8 | 955.4 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 21 | 15 | 0 | 0 | 16 | 58.3% | 100.0% | 73.7% | 107.0 | 13085.2 | shared + components |
| C3 union, reject inert and pointer-events:none | 21 | 14 | 0 | 1 | 16 | 60.0% | 100.0% | 75.0% | 8.0 | 977.2 | shared + components |
| C4 union, additionally reject blocked center | 21 | 14 | 0 | 1 | 16 | 60.0% | 100.0% | 75.0% | 8.0 | 977.2 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 3 | 0 | 18 | 15 | 16 | 100.0% | 14.3% | 25.0% | 8.0 | 980.2 | shared + components |
| C6 visible label for a toggle absent from Tab | 0 | 1 | 20 | 13 | 18 | 0.0% | 0.0% | 0.0% | 5.8 | 719.7 | shared + components |
| C7 ancestor mouse listener, minus Tab | 21 | 12 | 0 | 3 | 16 | 63.6% | 100.0% | 77.8% | 5.9 | 720.5 | shared + components |
| C8 union + focusable + label + ancestor leads | 21 | 15 | 0 | 0 | 16 | 58.3% | 100.0% | 73.7% | 8.0 | 984.1 | shared + components |
| C9 combined leads, additionally reject blocked center | 21 | 15 | 0 | 0 | 16 | 58.3% | 100.0% | 73.7% | 8.0 | 984.1 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 19 | 8 | 2 | 7 | 16 | 70.4% | 90.5% | 79.2% | 8.3 | 1012.2 | C9 + rule observation |
| C11 = C10 minus roving-tabindex items (R2) | 19 | 8 | 2 | 7 | 16 | 70.4% | 90.5% | 79.2% | 8.5 | 1043.3 | C9 + rule observation |
| C12 = C11 minus declared shortcuts (R3) | 19 | 8 | 2 | 7 | 16 | 70.4% | 90.5% | 79.2% | 8.5 | 1043.3 | C9 + rule observation |
| C13 = C12 minus leads with no action path (R5) | 19 | 7 | 2 | 8 | 16 | 73.1% | 90.5% | 80.9% | 111.4 | 13622.0 | C9 + rule observation |
| C14 = C13 minus name-twinned leads (R6) | 19 | 7 | 2 | 8 | 16 | 73.1% | 90.5% | 80.9% | 111.4 | 13622.0 | C9 + rule observation |
| C15 = C14 minus leads with no click effect (R7, R8) | 18 | 4 | 3 | 10 | 17 | 81.8% | 85.7% | 83.7% | 354.8 | 44230.8 | C9 + rule observation |
| C16 = C15 plus divergent-key-effect promotions (R9) | 18 | 4 | 3 | 10 | 17 | 81.8% | 85.7% | 83.7% | 354.8 | 44230.8 | C9 + rule observation |
| D9 behavioural differential | 22 | 8 | 0 | 0 | 22 | 73.3% | 100.0% | 84.6% | 1345.0 | 174989.1 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 23 | 8 | 0 | 0 | 21 | 74.2% | 100.0% | 85.2% | 1353.6 | 172826.2 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 24 | 12 | 0 | 0 | 16 | 66.7% | 100.0% | 80.0% | 1694.7 | 217907.0 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 24 | 12 | 0 | 0 | 16 | 66.7% | 100.0% | 80.0% | 1551.8 | 199540.3 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 19 | 12 | 0 | 0 | 21 | 61.3% | 100.0% | 76.0% | 1361.9 | 168657.0 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 19 | 12 | 0 | 0 | 21 | 61.3% | 100.0% | 76.0% | 1361.9 | 168657.0 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 24 | 15 | 0 | 0 | 13 | 61.5% | 100.0% | 76.2% | 762.8 | 92069.2 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 24 | 15 | 0 | 0 | 13 | 61.5% | 100.0% | 76.2% | 762.8 | 92069.2 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 14 | 8 | 1 | 0 | 29 | 63.6% | 93.3% | 75.7% | 753.2 | 97266.5 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 24 | 15 | 0 | 0 | 13 | 61.5% | 100.0% | 76.2% | 762.8 | 92069.2 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 17 | 10 | 0 | 0 | 25 | 63.0% | 100.0% | 77.3% | 744.7 | 92149.6 | priced at its arm |
| KAFE (Chiou et al., ESEC/FSE 2021) | 24 | 1 | 0 | 14 | 0 | 96.0% | 100.0% | 98.0% | 25.7 | 1012.7 | measured (their Detection column / their visible ctrl nodes) |

[^f1]: F1 is undefined where precision is undefined — a detector that flagged no
subject at all has no precision to combine with its recall. That is the correct
result, not a missing measurement.

## KAFE on the same denominator

KAFE decided all 60 subjects. Restricted to the 39 subjects this
replication actually scored, their own numbers are
TP 24, FP 1, FN 0, TN 14;
their pooled cost on that subset is 25.7 ms/button and
1012.7 ms/subject. The `KAFE` row in the table above is
computed on that subset, so it is read against the Axcess rows on one denominator.

## Controls

| control | result |
|---|---|
| 1 — KAFE reproduction | **pass**: 36/3/0/21 at 92.3% / 100.0% |
| 2 — denominator | **pass**: 39 scored, 13 whole-subject abstentions, 7 excluded before the run |
| 3 — negative control | **pass**: 15 KAFE-`FALSE` subjects scored |
| 4 — frozen code | **pass**: every detector imported from `src/audit/analyzer/keyboard/kbdiff/` |

Full control output: `derived/kafe_matrix_controls.json`.
