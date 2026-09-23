# KAFE's benchmark, all 48 Axcess detectors and KAFE's own result

Generated 2026-09-23T13:21:53.500404+00:00 by `tools/kafe_matrix.py assemble`, from
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
| subjects scored | **40 of 53 attempted, of 60 in the corpus** — see control 2 |

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
`TP + FP + FN + TN + abst. = 53`, the subjects attempted.
**The KAFE row's `abst.` is 0 and that is literal** — KAFE decided every subject
in its own CSV. Its row is *restricted* to the 40 subjects this
replication scored, so the two sides are read on one denominator; the
13 subjects Axcess could not put in front of it are named in
control 2, not charged to KAFE.

**Two recalls, on two bases.** `abst.` counts over the 53 subjects
attempted. `unk pos` and `unk neg` count only the abstentions that fall inside
the 40 scored subjects, split by KAFE's label, so for every row
`TP + FN + unk pos = 25` and `FP + TN + unk neg = 15`, and
`abst.` is those two plus the 13 whole-subject abstentions.
**`strict recall`** is TP over all 25 KAFE-positive scored subjects:
an abstention on one of them counts as a miss. **`recall (decided)`** is
TP / (TP + FN), which drops those abstentions from the denominator, and it is
the recall **F1** uses. Where a row has `unk pos` 0 the two recalls agree.

**The two sides' ms columns are not measured the same way.** Only the
arithmetic is shared: both are pooled, total time over total controls. What goes
into it differs on both sides of the division.

- **Axcess** `ms/button` is this harness's wall time for the detector's arm on
  a subject — the `ms covers` column says what that includes — summed over the
  scored subjects and divided by the candidates `collect_candidates` surfaced on
  them. It includes the detector's own browser work: navigation, tab walks and
  behavioural passes where the row needs them. It excludes replay-server setup.
  It is an amortised quotient, not latency measured one button at a time, and
  it is headless Chromium under Playwright on one shared machine.
- **KAFE** `ms/button` is their **full pipeline** from their own per-subject
  logs (`execTime.csv` phases 00–11 plus `execTimeDetection.csv`'s
  `01-Type1Detection`): proxy start-up, both graph crawls (keyboard and
  pointer), node extraction, then Type 1 detection. It is divided by their
  `Size of All Visible Ctrl Nodes`, whose node-selection code was not
  published. That is the figure comparable to an Axcess row, because both
  include the browser work that produces the verdict. Type 1 detection alone
  (the graph comparison once both graphs exist) is given in `ms covers` and in
  the section below; it excludes both crawls and is not comparable. Type 2
  detection is counted in neither. It is an amortised quotient too, taken with
  their own instrument on their 2019 Firefox 68 / Selenium setup, and nothing
  here re-timed it.
- 44.8% of KAFE's full pipeline on the 40 is proxy
  initialisation (phases 00 and 06), which has no counterpart in an Axcess
  arm's time. Even so, the full pipeline is the only figure that includes
  KAFE's crawls.

Neither figure is measured per-button latency, and the two are comparable as
orders of magnitude only. The 300 ms per-button ceiling is this project's
constraint, not KAFE's. `ms/subject` is total time for one subject, pooled the
same way on each side and subject to the same caveat.

**The results CSV's `Detection` column is not used.** An earlier version of this
table divided it by the control count. It is not a per-subject detection time.
Across the 60 subjects in alphabetical order, the order their CSV lists them,
it falls only
2 times in 59 steps, where
`01-Type1Detection` falls 26 times and the CSV's crawl and
node-extraction columns 27–30 times. It also differs by more than 5% from
KAFE's own per-subject `01-Type1Detection` on
59 of 60 subjects. Its
figures are kept in `derived/kafe_matrix_summary.json` under
`results_csv_detection_column` only so the error stays visible.

**The candidate universe is Axcess's own.** `data-probe` could only be placed on
the elements `audit.analyzer.keyboard.kbdiff.candidates.collect_candidates`
surfaced, because `candidate_analysis.measure_candidate_page` requires its
feature sweep to cover exactly the probe set. No detector below could propose an
element that collector did not surface, which flatters the D0/C families. This
is the largest unclosed threat to validity in the table and is discussed in
`KAFE-MATRIX-REPORT.md`.

## The table

| detector | TP | FP | FN | TN | abst. | unk pos | unk neg | precision | strict recall | recall (decided) | F1 (decided recall) | ms/button | ms/subject | ms covers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 18 | 9 | 5 | 5 | 16 | 2 | 1 | 66.7% | 72.0% | 78.3% | 72.0% | 0.1 | 20.0 | survey + method |
| D1 axe-core (keyboard rules) | 2 | 1 | 21 | 12 | 17 | 2 | 2 | 66.7% | 8.0% | 8.7% | 15.4% | 2.6 | 385.7 | survey + method |
| D1x axe-core (any rule, unsound) | 23 | 11 | 1 | 2 | 16 | 1 | 2 | 67.6% | 92.0% | 95.8% | 79.3% | 2.6 | 385.3 | survey + method |
| D2 inline onclick attribute | 5 | 2 | 18 | 11 | 17 | 2 | 2 | 71.4% | 20.0% | 21.7% | 33.3% | 0.1 | 20.4 | survey + method |
| D2b onclick property | 12 | 3 | 11 | 10 | 17 | 2 | 2 | 80.0% | 48.0% | 52.2% | 63.2% | 0.1 | 20.4 | survey + method |
| D3 tabindex / ARIA | 10 | 1 | 13 | 12 | 17 | 2 | 2 | 90.9% | 40.0% | 43.5% | 58.8% | 0.1 | 20.4 | survey + method |
| D4 CSS + lexical | 25 | 14 | 0 | 0 | 14 | 0 | 1 | 64.1% | 100.0% | 100.0% | 78.1% | 0.1 | 19.1 | survey + method |
| D5 CDP getEventListeners | 21 | 5 | 2 | 8 | 17 | 2 | 2 | 80.8% | 84.0% | 91.3% | 85.7% | 3.2 | 465.4 | survey + method |
| D6 addEventListener shim | 2 | 0 | 21 | 13 | 17 | 2 | 2 | 100.0% | 8.0% | 8.7% | 16.0% | 0.2 | 22.9 | survey + method |
| D7 React fiber props | 0 | 0 | 23 | 13 | 17 | 2 | 2 | undefined: flagged no subject | 0.0% | 0.0% | undefined: precision undefined [^f1] | 0.1 | 20.4 | survey + method |
| D8 hover-diff | 18 | 9 | 5 | 5 | 16 | 2 | 1 | 66.7% | 72.0% | 78.3% | 72.0% | 123.5 | 17845.4 | survey + method |
| U-D0 upstream crawler candidates | 11 | 3 | 11 | 12 | 16 | 3 | 0 | 78.6% | 44.0% | 50.0% | 61.1% | 5.2 | 749.5 | shared + method |
| U-D1 upstream tagged axe attribution | 21 | 8 | 1 | 7 | 16 | 3 | 0 | 72.4% | 84.0% | 95.5% | 82.4% | 7.7 | 1102.1 | shared + method |
| U-D2 upstream inline attributes | 4 | 0 | 18 | 15 | 16 | 3 | 0 | 100.0% | 16.0% | 18.2% | 30.8% | 5.2 | 750.0 | shared + method |
| U-D2b upstream mouse handler properties | 9 | 1 | 13 | 14 | 16 | 3 | 0 | 90.0% | 36.0% | 40.9% | 56.3% | 5.2 | 749.7 | shared + method |
| U-D3 upstream missing tabindex | 7 | 0 | 15 | 15 | 16 | 3 | 0 | 100.0% | 28.0% | 31.8% | 48.3% | 5.2 | 749.7 | shared + method |
| U-D4 upstream CSS and class tokens | 22 | 14 | 0 | 1 | 16 | 3 | 0 | 61.1% | 88.0% | 100.0% | 75.9% | 5.2 | 750.2 | shared + method |
| U-D5 upstream direct CDP listeners | 17 | 1 | 5 | 14 | 16 | 3 | 0 | 94.4% | 68.0% | 77.3% | 85.0% | 7.3 | 1042.3 | shared + method |
| U-D6 upstream registration shim | 12 | 0 | 10 | 15 | 16 | 3 | 0 | 100.0% | 48.0% | 54.5% | 70.6% | 5.2 | 749.7 | shared + method |
| U-D7 upstream React mouse props | 0 | 0 | 22 | 15 | 16 | 3 | 0 | undefined: flagged no subject | 0.0% | 0.0% | undefined: precision undefined [^f1] | 5.2 | 750.0 | shared + method |
| U-D8 upstream pixel hover difference | 16 | 14 | 6 | 1 | 16 | 3 | 0 | 53.3% | 64.0% | 72.7% | 61.5% | 114.7 | 16429.0 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 22 | 14 | 0 | 1 | 16 | 3 | 0 | 61.1% | 88.0% | 100.0% | 75.9% | 7.3 | 1050.1 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 22 | 15 | 0 | 0 | 16 | 3 | 0 | 59.5% | 88.0% | 100.0% | 74.6% | 116.8 | 16732.9 | shared + components |
| C3 union, reject inert and pointer-events:none | 22 | 14 | 0 | 1 | 16 | 3 | 0 | 61.1% | 88.0% | 100.0% | 75.9% | 7.5 | 1075.7 | shared + components |
| C4 union, additionally reject blocked center | 22 | 14 | 0 | 1 | 16 | 3 | 0 | 61.1% | 88.0% | 100.0% | 75.9% | 7.5 | 1075.7 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 3 | 0 | 19 | 15 | 16 | 3 | 0 | 100.0% | 12.0% | 13.6% | 24.0% | 7.5 | 1078.9 | shared + components |
| C6 visible label for a toggle absent from Tab | 0 | 1 | 21 | 13 | 18 | 4 | 1 | 0.0% | 0.0% | 0.0% | 0.0% | 5.3 | 774.3 | shared + components |
| C7 ancestor mouse listener, minus Tab | 22 | 12 | 0 | 3 | 16 | 3 | 0 | 64.7% | 88.0% | 100.0% | 78.6% | 5.4 | 772.1 | shared + components |
| C8 union + focusable + label + ancestor leads | 22 | 15 | 0 | 0 | 16 | 3 | 0 | 59.5% | 88.0% | 100.0% | 74.6% | 7.6 | 1083.0 | shared + components |
| C9 combined leads, additionally reject blocked center | 22 | 15 | 0 | 0 | 16 | 3 | 0 | 59.5% | 88.0% | 100.0% | 74.6% | 7.6 | 1083.0 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 20 | 8 | 2 | 7 | 16 | 3 | 0 | 71.4% | 80.0% | 90.9% | 80.0% | 7.8 | 1112.8 | C9 + rule observation |
| C11 = C10 minus roving-tabindex items (R2) | 20 | 8 | 2 | 7 | 16 | 3 | 0 | 71.4% | 80.0% | 90.9% | 80.0% | 8.0 | 1145.1 | C9 + rule observation |
| C12 = C11 minus declared shortcuts (R3) | 20 | 8 | 2 | 7 | 16 | 3 | 0 | 71.4% | 80.0% | 90.9% | 80.0% | 8.0 | 1145.1 | C9 + rule observation |
| C13 = C12 minus leads with no action path (R5) | 20 | 7 | 2 | 8 | 16 | 3 | 0 | 74.1% | 80.0% | 90.9% | 81.6% | 110.0 | 15757.9 | C9 + rule observation |
| C14 = C13 minus name-twinned leads (R6) | 20 | 7 | 2 | 8 | 16 | 3 | 0 | 74.1% | 80.0% | 90.9% | 81.6% | 110.0 | 15757.9 | C9 + rule observation |
| C15 = C14 minus leads with no click effect (R7, R8) | 19 | 4 | 3 | 10 | 17 | 3 | 1 | 82.6% | 76.0% | 86.4% | 84.4% | 337.7 | 49346.6 | C9 + rule observation |
| C16 = C15 plus divergent-key-effect promotions (R9) | 19 | 4 | 3 | 10 | 17 | 3 | 1 | 82.6% | 76.0% | 86.4% | 84.4% | 337.7 | 49346.6 | C9 + rule observation |
| D9 behavioural differential | 23 | 8 | 0 | 0 | 22 | 2 | 7 | 74.2% | 92.0% | 100.0% | 85.2% | 1422.6 | 220311.9 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 24 | 8 | 0 | 0 | 21 | 1 | 7 | 75.0% | 96.0% | 100.0% | 85.7% | 1428.7 | 216800.2 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 25 | 12 | 0 | 0 | 16 | 0 | 3 | 67.6% | 100.0% | 100.0% | 80.6% | 1715.6 | 256275.8 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 25 | 12 | 0 | 0 | 16 | 0 | 3 | 67.6% | 100.0% | 100.0% | 80.6% | 1585.6 | 236849.9 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 20 | 12 | 0 | 0 | 21 | 5 | 3 | 62.5% | 80.0% | 100.0% | 76.9% | 1354.4 | 200491.6 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 20 | 12 | 0 | 0 | 21 | 5 | 3 | 62.5% | 80.0% | 100.0% | 76.9% | 1354.4 | 200491.6 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 25 | 15 | 0 | 0 | 13 | 0 | 0 | 62.5% | 100.0% | 100.0% | 76.9% | 721.9 | 101162.3 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 25 | 15 | 0 | 0 | 13 | 0 | 0 | 62.5% | 100.0% | 100.0% | 76.9% | 721.9 | 101162.3 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 15 | 8 | 1 | 0 | 29 | 9 | 7 | 65.2% | 60.0% | 93.8% | 76.9% | 696.2 | 112205.1 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 25 | 15 | 0 | 0 | 13 | 0 | 0 | 62.5% | 100.0% | 100.0% | 76.9% | 721.9 | 101162.3 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 18 | 10 | 0 | 0 | 25 | 7 | 5 | 64.3% | 72.0% | 100.0% | 78.3% | 694.5 | 105136.9 | priced at its arm |
| KAFE (Chiou et al., ESEC/FSE 2021) | 25 | 1 | 0 | 14 | 0 | 0 | 0 | 96.2% | 100.0% | 100.0% | 98.0% | 19978.6 | 912521.7 | full pipeline from their per-subject logs (both graph crawls + Type 1 detection); Type 1 detection alone 73.4 ms/button |

[^f1]: F1 is undefined where precision is undefined — a detector that flagged no
subject at all has no precision to combine with its recall. That is the correct
result, not a missing measurement.

## KAFE on the same denominator

KAFE decided all 60 subjects. Restricted to the 40 subjects this
replication actually scored, their own numbers are
TP 25, FP 1, FN 0, TN 14.
The `KAFE` row in the table above is computed on that subset, so it is read
against the Axcess rows on one denominator.

Their cost, from their per-subject logs, in ms per visible control node
(denominator: the results CSV's `Size of All Visible Ctrl Nodes`,
1827 on the 40, 2992 on all 60).
"Pooled" is total ms over total controls, as for the Axcess rows; median, min
and max are over per-subject quotients:

| scope | pooled (40) | median (40) | min–max (40) | under 300 ms (40) | pooled (60) | median (60) | min–max (60) | under 300 ms (60) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Type 1 detection alone (`01-Type1Detection`) | 73.4 | 122.6 | 7.2–636.1 | 35/40 | 65.5 | 104.3 | 6.2–636.1 | 53/60 |
| both crawls (phases 02, 03, 05, 08, 09, 10) | 3,198.3 | 4,486.2 | 672.4–16,133.9 | 0/40 | 3,201.3 | 3,866.2 | 330.8–22,359.7 | 0/60 |
| **full pipeline** (phases 00–11 + Type 1 detection) | 19,978.6 | 27,668.0 | 5,182.0–68,265.3 | 0/40 | 23,261.2 | 24,004.7 | 5,182.0–130,006.9 | 0/60 |

Mean full pipeline per subject over all 60:
19.33 min (their paper:
19.22 min). The per-subject logs are
unlicensed third-party files, fetched by `tools/fetch_kafe_output.py` into the
git-ignored `artifacts/kafe_output/` and never committed.

## Controls

| control | result |
|---|---|
| 1 — KAFE reproduction | **pass**: 36/3/0/21 at 92.3% / 100.0% |
| 2 — denominator | **pass**: 40 scored, 13 whole-subject abstentions, 7 excluded before the run |
| 3 — negative control | **pass**: 15 KAFE-`FALSE` subjects scored |
| 4 — frozen code | **pass**: every detector imported from `src/audit/analyzer/keyboard/kbdiff/` |

Full control output: `derived/kafe_matrix_controls.json`.
