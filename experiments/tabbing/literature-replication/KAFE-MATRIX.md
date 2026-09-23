# KAFE's benchmark, all 48 Axcess detectors and KAFE's own result

Generated 2026-09-23T01:36:31.512206+00:00 by `tools/kafe_matrix.py assemble`, from
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

**Two recalls, on two bases.** `abst.` counts over the 52 subjects
attempted. `unk pos` and `unk neg` count only the abstentions that fall inside
the 39 scored subjects, split by KAFE's label, so for every row
`TP + FN + unk pos = 24` and `FP + TN + unk neg = 15`, and
`abst.` is those two plus the 13 whole-subject abstentions.
**`strict recall`** is TP over all 24 KAFE-positive scored subjects:
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
- 44.6% of KAFE's full pipeline on the 39 is proxy
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
| D0 axcess collectClickables | 17 | 9 | 5 | 5 | 16 | 2 | 1 | 65.4% | 70.8% | 77.3% | 70.8% | 0.1 | 17.8 | survey + method |
| D1 axe-core (keyboard rules) | 2 | 1 | 20 | 12 | 17 | 2 | 2 | 66.7% | 8.3% | 9.1% | 16.0% | 2.9 | 366.2 | survey + method |
| D1x axe-core (any rule, unsound) | 22 | 11 | 1 | 2 | 16 | 1 | 2 | 66.7% | 91.7% | 95.7% | 78.6% | 2.9 | 366.3 | survey + method |
| D2 inline onclick attribute | 5 | 2 | 17 | 11 | 17 | 2 | 2 | 71.4% | 20.8% | 22.7% | 34.5% | 0.1 | 18.2 | survey + method |
| D2b onclick property | 12 | 3 | 10 | 10 | 17 | 2 | 2 | 80.0% | 50.0% | 54.5% | 64.9% | 0.1 | 18.2 | survey + method |
| D3 tabindex / ARIA | 9 | 1 | 13 | 12 | 17 | 2 | 2 | 90.0% | 37.5% | 40.9% | 56.3% | 0.1 | 18.2 | survey + method |
| D4 CSS + lexical | 24 | 14 | 0 | 0 | 14 | 0 | 1 | 63.2% | 100.0% | 100.0% | 77.4% | 0.1 | 17.1 | survey + method |
| D5 CDP getEventListeners | 20 | 5 | 2 | 8 | 17 | 2 | 2 | 80.0% | 83.3% | 90.9% | 85.1% | 3.2 | 399.7 | survey + method |
| D6 addEventListener shim | 2 | 0 | 20 | 13 | 17 | 2 | 2 | 100.0% | 8.3% | 9.1% | 16.7% | 0.2 | 20.6 | survey + method |
| D7 React fiber props | 0 | 0 | 22 | 13 | 17 | 2 | 2 | undefined: flagged no subject | 0.0% | 0.0% | undefined: precision undefined [^f1] | 0.1 | 18.2 | survey + method |
| D8 hover-diff | 17 | 9 | 5 | 5 | 16 | 2 | 1 | 65.4% | 70.8% | 77.3% | 70.8% | 124.5 | 15383.7 | survey + method |
| U-D0 upstream crawler candidates | 11 | 3 | 10 | 12 | 16 | 3 | 0 | 78.6% | 45.8% | 52.4% | 62.9% | 5.7 | 701.8 | shared + method |
| U-D1 upstream tagged axe attribution | 20 | 8 | 1 | 7 | 16 | 3 | 0 | 71.4% | 83.3% | 95.2% | 81.6% | 8.6 | 1046.1 | shared + method |
| U-D2 upstream inline attributes | 4 | 0 | 17 | 15 | 16 | 3 | 0 | 100.0% | 16.7% | 19.0% | 32.0% | 5.7 | 702.2 | shared + method |
| U-D2b upstream mouse handler properties | 9 | 1 | 12 | 14 | 16 | 3 | 0 | 90.0% | 37.5% | 42.9% | 58.1% | 5.7 | 701.9 | shared + method |
| U-D3 upstream missing tabindex | 7 | 0 | 14 | 15 | 16 | 3 | 0 | 100.0% | 29.2% | 33.3% | 50.0% | 5.7 | 701.9 | shared + method |
| U-D4 upstream CSS and class tokens | 21 | 14 | 0 | 1 | 16 | 3 | 0 | 60.0% | 87.5% | 100.0% | 75.0% | 5.7 | 702.4 | shared + method |
| U-D5 upstream direct CDP listeners | 16 | 1 | 5 | 14 | 16 | 3 | 0 | 94.1% | 66.7% | 76.2% | 84.2% | 7.8 | 948.0 | shared + method |
| U-D6 upstream registration shim | 11 | 0 | 10 | 15 | 16 | 3 | 0 | 100.0% | 45.8% | 52.4% | 68.8% | 5.7 | 701.9 | shared + method |
| U-D7 upstream React mouse props | 0 | 0 | 21 | 15 | 16 | 3 | 0 | undefined: flagged no subject | 0.0% | 0.0% | undefined: precision undefined [^f1] | 5.7 | 702.1 | shared + method |
| U-D8 upstream pixel hover difference | 15 | 14 | 6 | 1 | 16 | 3 | 0 | 51.7% | 62.5% | 71.4% | 60.0% | 104.9 | 12828.3 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 21 | 14 | 0 | 1 | 16 | 3 | 0 | 60.0% | 87.5% | 100.0% | 75.0% | 7.8 | 955.4 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 21 | 15 | 0 | 0 | 16 | 3 | 0 | 58.3% | 87.5% | 100.0% | 73.7% | 107.0 | 13085.2 | shared + components |
| C3 union, reject inert and pointer-events:none | 21 | 14 | 0 | 1 | 16 | 3 | 0 | 60.0% | 87.5% | 100.0% | 75.0% | 8.0 | 977.2 | shared + components |
| C4 union, additionally reject blocked center | 21 | 14 | 0 | 1 | 16 | 3 | 0 | 60.0% | 87.5% | 100.0% | 75.0% | 8.0 | 977.2 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 3 | 0 | 18 | 15 | 16 | 3 | 0 | 100.0% | 12.5% | 14.3% | 25.0% | 8.0 | 980.2 | shared + components |
| C6 visible label for a toggle absent from Tab | 0 | 1 | 20 | 13 | 18 | 4 | 1 | 0.0% | 0.0% | 0.0% | 0.0% | 5.8 | 719.7 | shared + components |
| C7 ancestor mouse listener, minus Tab | 21 | 12 | 0 | 3 | 16 | 3 | 0 | 63.6% | 87.5% | 100.0% | 77.8% | 5.9 | 720.5 | shared + components |
| C8 union + focusable + label + ancestor leads | 21 | 15 | 0 | 0 | 16 | 3 | 0 | 58.3% | 87.5% | 100.0% | 73.7% | 8.0 | 984.1 | shared + components |
| C9 combined leads, additionally reject blocked center | 21 | 15 | 0 | 0 | 16 | 3 | 0 | 58.3% | 87.5% | 100.0% | 73.7% | 8.0 | 984.1 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 19 | 8 | 2 | 7 | 16 | 3 | 0 | 70.4% | 79.2% | 90.5% | 79.2% | 8.3 | 1012.2 | C9 + rule observation |
| C11 = C10 minus roving-tabindex items (R2) | 19 | 8 | 2 | 7 | 16 | 3 | 0 | 70.4% | 79.2% | 90.5% | 79.2% | 8.5 | 1043.3 | C9 + rule observation |
| C12 = C11 minus declared shortcuts (R3) | 19 | 8 | 2 | 7 | 16 | 3 | 0 | 70.4% | 79.2% | 90.5% | 79.2% | 8.5 | 1043.3 | C9 + rule observation |
| C13 = C12 minus leads with no action path (R5) | 19 | 7 | 2 | 8 | 16 | 3 | 0 | 73.1% | 79.2% | 90.5% | 80.9% | 111.4 | 13622.0 | C9 + rule observation |
| C14 = C13 minus name-twinned leads (R6) | 19 | 7 | 2 | 8 | 16 | 3 | 0 | 73.1% | 79.2% | 90.5% | 80.9% | 111.4 | 13622.0 | C9 + rule observation |
| C15 = C14 minus leads with no click effect (R7, R8) | 18 | 4 | 3 | 10 | 17 | 3 | 1 | 81.8% | 75.0% | 85.7% | 83.7% | 354.8 | 44230.8 | C9 + rule observation |
| C16 = C15 plus divergent-key-effect promotions (R9) | 18 | 4 | 3 | 10 | 17 | 3 | 1 | 81.8% | 75.0% | 85.7% | 83.7% | 354.8 | 44230.8 | C9 + rule observation |
| D9 behavioural differential | 22 | 8 | 0 | 0 | 22 | 2 | 7 | 73.3% | 91.7% | 100.0% | 84.6% | 1345.0 | 174989.1 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 23 | 8 | 0 | 0 | 21 | 1 | 7 | 74.2% | 95.8% | 100.0% | 85.2% | 1353.6 | 172826.2 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 24 | 12 | 0 | 0 | 16 | 0 | 3 | 66.7% | 100.0% | 100.0% | 80.0% | 1694.7 | 217907.0 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 24 | 12 | 0 | 0 | 16 | 0 | 3 | 66.7% | 100.0% | 100.0% | 80.0% | 1551.8 | 199540.3 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 19 | 12 | 0 | 0 | 21 | 5 | 3 | 61.3% | 79.2% | 100.0% | 76.0% | 1361.9 | 168657.0 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 19 | 12 | 0 | 0 | 21 | 5 | 3 | 61.3% | 79.2% | 100.0% | 76.0% | 1361.9 | 168657.0 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 24 | 15 | 0 | 0 | 13 | 0 | 0 | 61.5% | 100.0% | 100.0% | 76.2% | 762.8 | 92069.2 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 24 | 15 | 0 | 0 | 13 | 0 | 0 | 61.5% | 100.0% | 100.0% | 76.2% | 762.8 | 92069.2 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 14 | 8 | 1 | 0 | 29 | 9 | 7 | 63.6% | 58.3% | 93.3% | 75.7% | 753.2 | 97266.5 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 24 | 15 | 0 | 0 | 13 | 0 | 0 | 61.5% | 100.0% | 100.0% | 76.2% | 762.8 | 92069.2 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 17 | 10 | 0 | 0 | 25 | 7 | 5 | 63.0% | 70.8% | 100.0% | 77.3% | 744.7 | 92149.6 | priced at its arm |
| KAFE (Chiou et al., ESEC/FSE 2021) | 24 | 1 | 0 | 14 | 0 | 0 | 0 | 96.0% | 100.0% | 100.0% | 98.0% | 22747.5 | 897652.7 | full pipeline from their per-subject logs (both graph crawls + Type 1 detection); Type 1 detection alone 84.4 ms/button |

[^f1]: F1 is undefined where precision is undefined — a detector that flagged no
subject at all has no precision to combine with its recall. That is the correct
result, not a missing measurement.

## KAFE on the same denominator

KAFE decided all 60 subjects. Restricted to the 39 subjects this
replication actually scored, their own numbers are
TP 24, FP 1, FN 0, TN 14.
The `KAFE` row in the table above is computed on that subset, so it is read
against the Axcess rows on one denominator.

Their cost, from their per-subject logs, in ms per visible control node
(denominator: the results CSV's `Size of All Visible Ctrl Nodes`,
1539 on the 39, 2992 on all 60).
"Pooled" is total ms over total controls, as for the Axcess rows; median, min
and max are over per-subject quotients:

| scope | pooled (39) | median (39) | min–max (39) | under 300 ms (39) | pooled (60) | median (60) | min–max (60) | under 300 ms (60) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Type 1 detection alone (`01-Type1Detection`) | 84.4 | 128.5 | 7.2–636.1 | 34/39 | 65.5 | 104.3 | 6.2–636.1 | 53/60 |
| both crawls (phases 02, 03, 05, 08, 09, 10) | 3,639.1 | 4,638.4 | 672.4–16,133.9 | 0/39 | 3,201.3 | 3,866.2 | 330.8–22,359.7 | 0/60 |
| **full pipeline** (phases 00–11 + Type 1 detection) | 22,747.5 | 27,682.0 | 7,344.1–68,265.3 | 0/39 | 23,261.2 | 24,004.7 | 5,182.0–130,006.9 | 0/60 |

Mean full pipeline per subject over all 60:
19.33 min (their paper:
19.22 min). The per-subject logs are
unlicensed third-party files, fetched by `tools/fetch_kafe_output.py` into the
git-ignored `artifacts/kafe_output/` and never committed.

## Controls

| control | result |
|---|---|
| 1 — KAFE reproduction | **pass**: 36/3/0/21 at 92.3% / 100.0% |
| 2 — denominator | **pass**: 39 scored, 13 whole-subject abstentions, 7 excluded before the run |
| 3 — negative control | **pass**: 15 KAFE-`FALSE` subjects scored |
| 4 — frozen code | **pass**: every detector imported from `src/audit/analyzer/keyboard/kbdiff/` |

Full control output: `derived/kafe_matrix_controls.json`.
