# Final report: the tabbing replication

Every benchmark, every detector, and where each benchmark comes from in the
literature. This is the single document to read for the whole study. It
supersedes nothing: every number here is carried from an existing artifact,
and each table names the one it came from.

**Data state.** The KAFE-corpus figures come from `derived/kafe_matrix.jsonl`
at **53 lines** (sha256 of the whole file begins `0d0bdceac1050fb3`; its first
52 lines still hash to `35d6de9c7da4a1c1`, checked before regenerating),
through `derived/kafe_matrix_summary.json` and `KAFE-MATRIX.md`. Line 53 is
`craigslist`, **now scored** on its fourth attempt (5,351.6 s), so the scored
set is **40 subjects**, up from 39 (§3.2). The fixtures, gds, ma11y and
edgecases figures come from `derived/matrix.json` through `MATRIX-RESULTS.md`,
`closed` run, and did not change. Nothing was re-run to write this report
beyond regenerating the KAFE tables (`controls`, `assemble`, `report`) from the
53 lines. Two earlier corrections recomputed KAFE-corpus cells from the first
52 lines, and the `craigslist` update then recomputed them from 53; all three
are listed in §8.4. KAFE's cost comes from KAFE's own per-subject timing logs,
not the results CSV's `Detection` column. The KAFE table's strict recall and
unknown-positive/negative columns are computed on the 40 scored subjects.

## 1. What this study can and cannot claim

**It can claim:**

- How 48 Axcess keyboard-accessibility detectors score on **KAFE's own 60-subject
  benchmark** (ESEC/FSE 2021), replayed offline from KAFE's captures, against
  KAFE's own published per-subject result. 40 subjects were scored; every
  subject that was not is named in §3 with its reason.
- That **no Axcess detector beats KAFE** on that benchmark. KAFE's published
  output scores 96.2% precision / 100% recall / F1 98.0% on the 40 subjects.
  KAFE decided all 40, so its strict and decided recall are the same. The
  best Axcess F1 is 85.7%, and it is now a **tie** between `D9+S4ours` and
  `D5 CDP getEventListeners` (both exactly 6/7), computed, like every
  KAFE-corpus F1 here, with recall over decided subjects. Their strict recalls
  are 96.0% and 84.0%.
- How the same detectors score on the **GDS Accessibility Tool Audit**'s six
  inoperable-functionality cases, where every one of the 13 tools GDS audited
  scored 0 of 6. The best Axcess detectors find 3 of 6.
- What each detector costs, as harness time divided by the number of buttons
  (candidates) it covered, and which detectors stay under the project's 300 ms
  per-button ceiling on each corpus.
- What KAFE itself costs per visible control, from KAFE's own per-subject
  timing logs, in two scopes. **Full pipeline** (both graph crawls plus Type 1
  detection): **19,978.6 ms** pooled over the 40, over 300 ms on all 40
  subjects. This is the figure comparable to an Axcess row, because both
  include the browser work that produces the verdict. **Type 1 detection
  alone** (the graph comparison once both crawls are done): **73.4 ms**, under
  300 ms on 35 of 40. It excludes the crawls and is not comparable (§7).
- That the cheap C-rules (C10–C16) lose precision when they leave the corpus
  they were written on, and which individual rules still do anything.

**It cannot claim:**

- **That KAFE was measured on our corpora.** It was not. The comparison runs
  one way: our detectors on their benchmark. KAFE's Java/Selenium/Firefox 68
  stack was not rebuilt, and KAFE labels pages while our corpora label elements.
  Both block the reverse direction. This was a deliberate scope decision
  (`BRIEF-ASYMMETRY.md`), not something left undone (§6).
- **That KAFE's row is a local run of KAFE.** It is their published CSV
  output (`artifacts/kafe_results_to_reproduce.csv`). It reproduces their
  paper's Table 1 exactly, which checks the arithmetic, not their tool.
- **Element-level precision on KAFE's corpus.** KAFE labels pages. A detector
  that flags 20 elements on a page with one real failure gets the same true
  positive as one that flags only that failure.
- **Strict recall over all 53 attempted KAFE subjects.** Strict recall on
  KAFE's corpus is taken over the **40 scored** subjects (TP / 25 positives).
  The 13 whole-subject abstentions are outside that basis, and they include
  one KAFE-positive subject (`indiegogo`) (§3.2, §4).
- **Measured per-button latency.** Every ms/button figure in the main table, on
  either side, is total time divided by a button count, not a latency measured
  one button at a time. Ours and KAFE's also differ in instrument, hardware and
  browser (§7).
- **A cost comparison from the results CSV's `Detection` column.** That column
  is not a per-subject detection time. The per-button figure earlier versions
  of this report took from it is withdrawn (§8.4).
- **Anything about the live sites.** Every KAFE subject is an offline replay of
  KAFE's own capture. A replay that renders no controls, or never ends its tab
  walk, says nothing about the site today.
- **Unbiased accuracy on `fixtures` or `edgecases`.** Both were written by this
  project. The cheap rules were written after looking at errors on `fixtures`,
  and `edgecases` was written alongside the detectors it tests.
- **A benchmark result from `ma11y`.** It has one verified fault and six
  controls. It is a check that each detector fires, and it cannot support a
  precision/recall comparison.

## 2. Findings

The findings that count against Axcess come first.

### 2.1 No Axcess detector beats KAFE

On the 40 scored subjects, KAFE's published output is 25 TP / 1 FP / 0 FN /
14 TN: **96.2% precision, 100% recall, F1 98.0%**. KAFE decided all 40, so its
strict recall and its recall over decided subjects are both 100%. Its cost,
from KAFE's own per-subject timing logs pooled over the 40 visible-control
counts, is **19,978.6 ms per button for the full pipeline** (both graph crawls
plus Type 1 detection). That is the figure comparable to Axcess's. Type 1
detection alone is **73.4 ms per button**; it excludes the crawls (§7).

The best Axcess F1 is **85.7%**, and **two rows now share it exactly** (F1 =
6/7 for both):

- `D9+S4ours` (24/8/0/0, 75.0% precision, 21 abstentions), at **1428.7
  ms/button**. Its recall over decided subjects is 100% (24 of 24), and its
  strict recall is **96.0%** (24 of the 25 KAFE-positive subjects: it
  abstained on one).
- `D5 CDP getEventListeners` (21/5/2/8, 80.8% precision, 17 abstentions), at
  **3.2 ms/button**. Its decided recall is 91.3% and its strict recall 84.0%.

**This changes a finding.** On the 39 subjects before `craigslist` was scored,
`D9+S4ours` held the best F1 alone (85.2%) and D5 was the best *cheap* row just
below it (85.1%). `craigslist` is KAFE-positive and both detectors flag it;
the extra true positive lifts D5, which already had two false negatives, a
little more than it lifts `D9+S4ours`. So the best F1 on KAFE's corpus, as the
table computes it, no longer belongs to a behavioural detector alone. A
single-signal detector matches it at about 1/450 of its cost. The tie holds
only for F1 with decided recall. With strict recall it breaks:
`D9+S4ours` 84.2%, D5 82.4% (D9 is third, at 82.1%), so on that basis
`D9+S4ours` is still the single best Axcess row. Five Axcess rows beat KAFE's
precision: D6, C5, U-D2, U-D3 and U-D6, all at 100%. They get there by
flagging almost nothing, and their strict recall is 8.0% to 48.0% (8.7% to
54.5% over decided subjects).

### 2.2 Where Axcess wins is cost

On the comparable basis, KAFE's full pipeline, **all 48 Axcess rows** have a
lower ms/button than KAFE's 19,978.6. That is **46 of the 46** rows with a
defined precision; D7 and U-D7 flag no subject, so their precision is
undefined. The dearest Axcess row, `D9+S4u` at 1715.6, costs about a
twelfth as much. Of the two best-F1 rows, `D9+S4ours` at 1428.7 costs about a
fourteenth, and D5 at 3.2 about a six-thousandth. 44.8% of KAFE's full
pipeline on the 40 is proxy initialisation (phases 00 and 06), which no
Axcess arm's time includes. Without it KAFE's figure would still be 11,036.6
ms/button (computed from the same logs), and every Axcess row would still be
below it.

On Type 1 detection alone, which excludes KAFE's crawls and is **not**
comparable, 30 of the 48 rows (28 of the 46) are lower than KAFE's 73.4. No
Axcess row falls between 73.4 and the withdrawn `Detection`-column figure
(22.1 on the 40), so this count is the same as the one earlier versions
reported (§8.4).

`D4 CSS + lexical` reaches **100% strict recall** (it abstains on no positive)
at **0.1 ms/button**, but with **14 false positives against KAFE's 1** (64.1%
precision). §7 explains why these cost figures compare only as orders of
magnitude.

### 2.3 The cheap rules do not transfer

C15 and C16 were built on `fixtures`. There they carry three rows (element
precision / strict recall): C15 at 100.0% / 94.9%, C16 at 100.0% / 97.4% when
R9 observes the 42-probe C12 lead set, and C16 at 77.6% / 97.4% when R9
observes all 95 probes. On KAFE's corpus both score **82.6% page precision /
76.0% strict recall** (86.4% over decided subjects; F1 84.4% uses the latter).
Both recalls are now strict, but the units still differ (elements on
`fixtures`, pages on KAFE's corpus). So the 17.4-point precision drop and the
18.9-point strict-recall drop from C15's `fixtures` row give the direction, not
a like-for-like difference.

Rule by rule on KAFE's corpus:

- **R2, R3, R6 and R9 have no effect.** C10 = C11 = C12, C13 = C14 and
  C15 = C16 are identical rows.
- **R1, R5 and R7/R8 change the result.** R1 does the most work of any rule:
  C9 → C10 goes 22/15/0/0 → 20/8/2/7 (TP/FP/FN/TN), removing 7 false positives
  and losing 2 true positives. R5 removes 1 more FP. R7/R8 remove 3 more FPs and
  lose 1 TP. C15, the first row carrying R7/R8, costs **337.7 ms/button, over
  the 300 ms ceiling**. C14, without them, costs 110.0.

### 2.4 C10–C16 are all zero on `gds` and `ma11y`, and that says nothing about the rules

Each of C10–C16 is *C9 minus a rule*. On `gds`, C9 abstains on 3 of the 6
faults; on `ma11y` it abstains on the corpus's single fault. Every rule then
subtracts from an empty lead set. Those rows measure C9's abstention. The rules
are untested on those two corpora, which is different from being tested and
found useless.

### 2.5 The comparison is one-way

Our detectors ran on KAFE's corpus. KAFE never ran on ours. Two things block
it: KAFE's Java/Selenium 3.141.5/Firefox 68 stack was not rebuilt, and KAFE
emits page labels while `fixtures`, `gds` and `ma11y` label elements. Even with
their binary running, the result would depend on a page-to-element mapping
invented for the purpose. This is a deliberate scope decision
(`BRIEF-ASYMMETRY.md`); see §6.

### 2.6 The KAFE denominator: 60 → 40, every exclusion named

60 subjects in KAFE's corpus → **7 excluded before the run** → 53 replayable →
**53 attempted** (every replayable subject, `craigslist` included) → **13
whole-subject abstentions** → **40 scored** (25 KAFE-positive, 15
KAFE-negative; 5605 controls probed). §3.2 names each one. **No abstention was ever counted as a
negative.** A page scores negative for a detector only if the detector flagged
nothing on it and left no candidate undecided.

### 2.7 The 7 capped subjects: one focus trap, five instrument failures, one unstable

`CAPDIAG-REPORT.md` re-walked the 7 subjects whose tab walk capped, 5 times,
with a 4000-press ceiling. Its verdict:

- **`dell` is a genuine focus trap.** From press 36, focus stays on one
  `<a class="dropdown-toggle check-float-cs">` while the page holds focus. This
  was stable in all 5 runs, and it is the only result there reported as a
  property of the subject.
- **Five are not decided, for an instrument reason:** `salesforce`, `raise`,
  `costco`, `dpreview` and `cnn`. Their walk settles into a loop where
  `document.hasFocus()` is false, meaning focus has left the page for the
  browser's own UI. The frozen `compute_tab_order` tries to end the walk
  there, but it tests for `document.activeElement === null`. That never
  happens, because `activeElement` falls back to `<body>`, so the walk runs out
  its budget. Nothing here says whether those sites trap a keyboard user.
- **`spotify` is unstable.** It capped in 2 of the 5 runs and completed in 3,
  at 2472–2645 presses against a 212-press budget. In the run where it capped
  with the `hasFocus` check in place, it showed the same mechanism as the
  five.
- `salesforce`, `costco`, `dell` and `dpreview` were stable across all five
  runs. `raise` and `cnn` capped every time, but what their walks contained
  differed from run to run.

All 7 remain abstentions, and no published number moved. Deciding the five
would mean changing a frozen detector's end-of-walk test to
`document.hasFocus()`, which is out of scope.

### 2.8 The one clear gain: GDS

The GDS audit's own result is **0 of 6 for all 13 tools it audited**. Five
Axcess detectors find **3 of 6 at zero false positives under 300 ms/button**:
D4 (1.2), D6 (1.9), D5 (7.7), C1 (286.4) and C2 (286.8). That is a real gain,
and 3 of 6 is not 6 of 6. On the same corpus C8 and C9 abstain on the three
cases their own inputs find, so their safety filter suppresses true positives
that their components had already found.

## 3. The benchmarks

### 3.1 Where each benchmark comes from

| benchmark | as scored here | origin in the literature | identifier | what the citation covers |
|---|---|---|---|---|
| **KAFE corpus** | 60 subjects, page-level labels; 40 scored | Chiou, Alotaibi & Halfond, *Detecting and Localizing Keyboard Accessibility Failures in Web Applications*, ESEC/FSE 2021, pp. 855–867 | DOI [`10.1145/3468264.3468581`](https://doi.org/10.1145/3468264.3468581) | Their corpus (replayed offline from their mitmproxy captures) and their per-subject result. The paper also defines the **IAF** construct (functionality a keyboard user cannot operate) behind every "violation" label in the other four corpora. |
| **Ma11y mutants** | 1 verified fault + 6 controls, element-level | Tafreshipour, Deshpande, Mehralian, Ahmed & Malek, *Ma11y: A Mutation Framework for Web Accessibility Testing*, ISSTA 2024, pp. 100–111 | DOI [`10.1145/3650212.3652113`](https://doi.org/10.1145/3650212.3652113) | **The mutation operators only.** We applied those operators (from `mahantaf/web-a11y-tool-analyzer`) to the GDS page ourselves, so the corpus is ours by construction. It is **not** the Ma11y paper's published benchmark, and we did not run that. Only operator F55 yielded a verified fault: F59 is not implemented in Ma11y, F54 needs an inline `onclick` the page lacks, and F42's span never fires on a trusted click, so it was excluded rather than labelled. |
| **GDS audit** | 6 IAF cases + 2 controls, element-level | UK Government Digital Service, *Accessibility Tool Audit*, MIT licence, Crown Copyright 2017 (archived 2021) | [`github.com/alphagov/accessibility-tool-audit`](https://github.com/alphagov/accessibility-tool-audit). **No DOI**: it is a government repository, not a paper. | 142 test cases in 19 categories. Of the 16 under "Keyboard Access", 6 match the IAF construct. The audit's own published result is that **all 13 audited tools score 0 of 6**. |
| **fixtures** | 95 probes, 39 defects, element-level | This project: a blind-authored synthetic corpus | **No external literature** | The suite's own frozen baseline. The cheap rules were written against it with labels visible, so its rows are development results, not accuracy. |
| **edgecases** | 74 targets, element-level | This project: a shared-author development corpus | **No external literature** | **Carries no unbiased accuracy claim.** It was written alongside the detectors it scores. |

### 3.2 KAFE's corpus: from 60 subjects to 40

Source: control 2 in `derived/kafe_matrix_controls.json`, via
`KAFE-MATRIX-REPORT.md` §2.

| stage | count | subjects and reason |
|---|---:|---|
| KAFE's corpus | 60 | all 60 have a KAFE Type-1 label; KAFE's published CSV decides every one |
| excluded before the run | 7 | `4shared`, `dmv_fl`: capture parses to no HTML entry document. `battlenet`, `canon`, `dmv_wc`, `gizmodo`, `speedway`: folder-form on Drive, no flow dump fetched |
| replayable | 53 | the 60 minus the 7 above |
| attempted | 53 | the lines in `derived/kafe_matrix.jsonl`: every replayable subject. `craigslist` (KAFE label TRUE, 898 candidates) is line 53. Three earlier attempts ended with no result (a hang, a manual kill, a backend restart); the fourth completed and was **scored** in 5,351.6 s, with 36 detectors positive, 12 negative and none abstaining |
| whole-subject abstention: replay has no controls | 6 | `indiegogo` (label TRUE), `instagram`, `mozilla`, `sciencedirect`, `whitepages`, `capitalone` (all FALSE). The frozen candidate collector found no addressable element in the replayed document. |
| whole-subject abstention: tab walk capped | 7 | `spotify`, `salesforce`, `raise`, `costco`, `dell`, `dpreview`, `cnn`. The walk hit its `focusable + 200` press budget; see §2.7 for why. |
| **scored** | **40** | 25 KAFE-positive, 15 KAFE-negative, 5605 controls probed |

Inside the 40, some detectors still abstain on some subjects. The candidate
arm raised `candidate feature coverage differs from page probes` on `godaddy`,
`thefreedictionary` and `wendys`, so the 19 rows that arm produces abstain on
those three subjects. Element identity was unstable across page loads on
`godaddy` (19% of probe ids reappeared) and `wendys` (4%). The rest of each
row's abstentions come from the strict negative rule: a subject on which a
detector flagged nothing but left some candidate undecided is an abstention for
that detector, not a negative. That is why, for example, D9 abstains on 22
subjects while only 13 abstain as whole subjects. D9's other 9 are inside the
40: 2 on KAFE-positive subjects and 7 on negatives. Those are its unknown pos
and unknown neg in §5.1.

## 4. How to read the main table

The main table in §5 is split **by corpus**, one table per benchmark with the
same columns. It is never split by detector family. The cheap detectors, C1–C16
included, sit in detector order in every table, next to everything else.

| column | what it is | name in the source artifact |
|---|---|---|
| detector | the detector's full name as in the artifacts | same |
| TP / FP / FN | confusion counts. **Unit: the page** on KAFE's corpus; **the element probe** on the other four | same |
| unknown pos / unknown neg | abstentions on labelled defects / labelled negatives; an abstention is never scored as a negative | `unk pos` / `unk neg` (`MATRIX-RESULTS.md`; on KAFE's corpus `KAFE-MATRIX.md`, over the 40 scored subjects only) |
| precision | TP / (TP + FP). Page precision on KAFE's corpus, element precision elsewhere | `precision`. `—` in `MATRIX-RESULTS.md` is shown here as `undefined: flagged nothing` |
| strict recall | TP over **every** labelled defect, abstentions included | `strict recall` (`MATRIX-RESULTS.md`; `bakeoff.py`'s `recall`; `KAFE-MATRIX.md`). On KAFE's corpus the cell reads `X% · decided Y%`: strict recall over the 40 scored subjects, then recall over decided subjects; see below |
| F1 | harmonic mean of the precision and recall columns as the artifact computed it. **On KAFE's corpus it uses recall over decided subjects**; on the other four, strict recall | `F1` (`F1 (decided recall)` in `KAFE-MATRIX.md`). `—` is shown as `undefined: TP = 0` |
| **ms per element/button** | this is the CEO's "ms per element". Each figure is a total time divided by a count of buttons; none is a latency measured one button at a time | `ms/button`. Its denominator differs by corpus; see the next table |
| timing scope | what work the ms figure includes | `ms covers` |

**Two recalls on KAFE's corpus.** `KAFE-MATRIX.md`'s `recall (decided)` is
TP / (TP + FN) over the subjects each detector *decided*. A subject it
abstained on drops out of the denominator instead of counting as a miss. Its
`strict recall` is TP / 25, over every KAFE-positive subject among the **40
scored**, so an abstention on one of them counts as a miss. `unk pos` and
`unk neg` split each detector's abstentions *inside the 40* by KAFE's label,
so `TP + FN + unk pos = 25` and `FP + TN + unk neg = 15`. The table's `abst.`
column in `KAFE-MATRIX.md` still counts over the 53 attempted, and it equals
`unk pos + unk neg + 13`, the 13 being the whole-subject abstentions. The
counts come from each detector's per-subject verdict in
`derived/kafe_matrix.jsonl`, computed by `tools/kafe_matrix.py assemble`. The
§5.1 cell shows both recalls, strict first: `X% · decided Y%`. Where a row has
no unknown positive the two agree. The F1 column keeps the artifact's value,
which uses the decided recall.

**What each ms figure divides by.**

| corpus | numerator | denominator | source |
|---|---|---|---|
| KAFE, Axcess rows | this harness's wall time for the detector's arm, summed over the 40 scored subjects | every candidate `collect_candidates` surfaced on those subjects (5605), decided or not | `tools/kafe_matrix.py assemble` |
| KAFE, KAFE row | KAFE's **full pipeline** from their per-subject logs, summed over the 40: `execTime.csv` phases 00–11 (proxy start-up, node extraction, both graph crawls) plus `execTimeDetection.csv`'s `01-Type1Detection`. Type 1 detection alone is given beside it; Type 2 is in neither | KAFE's `Size of All Visible Ctrl Nodes` over the same 40 (1827), from the results CSV | their logs (`artifacts/kafe_output/`, git-ignored); not re-timed |
| fixtures, gds, ma11y, edgecases | measured browser work for the detector | the probes that detector **decided** | `tools/assemble_matrix.py` |

On the four element corpora `MATRIX-RESULTS.md` also carries `ms/target`, the
same work divided by every target including undecided ones. It is not
repeated here except where `ms/button` is undefined.

**Timing-scope values.** `survey + method`: the cheap tier's page survey plus
the detector's own method. `shared + method`: the shared candidate-analysis pass
plus the method. `shared + components`: the shared pass plus every component the
combination reads. `C9 + rule observation`, or `C9 + R1`, `C9 + behavioural
pass` and so on: C9's cost plus the probe-observation passes that rule needs
(`same pass` and `free` mean no extra pass). `measured`: the arm's own
timing. `priced at its arm`: the row re-scores another arm's single measured
trial, so it costs what that arm cost.

## 5. The main table

### 5.1 KAFE corpus — Chiou, Alotaibi & Halfond, ESEC/FSE 2021, DOI 10.1145/3468264.3468581

40 scored subjects (25 positive, 15 negative); unit = page. Source:
`KAFE-MATRIX.md` / `derived/kafe_matrix_summary.json`. For every Axcess row,
TP + FN + unknown pos = 25 and FP + TN + unknown neg = 15, over the 40 scored
subjects. The 13 whole-subject abstentions are outside both; `KAFE-MATRIX.md`'s
`abst.` column counts them too (TP + FP + FN + TN + abst. = 53). TN is not a
required column, and every row's TN is in `KAFE-MATRIX.md`. **F1 on this corpus
uses recall over decided subjects**, the second figure in the strict-recall
cell. The last row is the **reference row**: KAFE's **published CSV output**
(its accuracy), not a local run of their tool, restricted to the same 40
subjects. Its cost comes from KAFE's per-subject timing logs, not from that
CSV (§7). This is the only table with a KAFE row. KAFE was never run on the
other four corpora (§6), and by decision they carry no KAFE row.

| detector | TP | FP | FN | unknown pos | unknown neg | precision | strict recall | F1 | ms per element/button | timing scope |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 18 | 9 | 5 | 2 | 1 | 66.7% | 72.0% · decided 78.3% | 72.0% | 0.1 | survey + method |
| D1 axe-core (keyboard rules) | 2 | 1 | 21 | 2 | 2 | 66.7% | 8.0% · decided 8.7% | 15.4% | 2.6 | survey + method |
| D1x axe-core (any rule, unsound) | 23 | 11 | 1 | 1 | 2 | 67.6% | 92.0% · decided 95.8% | 79.3% | 2.6 | survey + method |
| D2 inline onclick attribute | 5 | 2 | 18 | 2 | 2 | 71.4% | 20.0% · decided 21.7% | 33.3% | 0.1 | survey + method |
| D2b onclick property | 12 | 3 | 11 | 2 | 2 | 80.0% | 48.0% · decided 52.2% | 63.2% | 0.1 | survey + method |
| D3 tabindex / ARIA | 10 | 1 | 13 | 2 | 2 | 90.9% | 40.0% · decided 43.5% | 58.8% | 0.1 | survey + method |
| D4 CSS + lexical | 25 | 14 | 0 | 0 | 1 | 64.1% | 100.0% · decided 100.0% | 78.1% | 0.1 | survey + method |
| D5 CDP getEventListeners | 21 | 5 | 2 | 2 | 2 | 80.8% | 84.0% · decided 91.3% | 85.7% | 3.2 | survey + method |
| D6 addEventListener shim | 2 | 0 | 21 | 2 | 2 | 100.0% | 8.0% · decided 8.7% | 16.0% | 0.2 | survey + method |
| D7 React fiber props | 0 | 0 | 23 | 2 | 2 | undefined: flagged nothing | 0.0% · decided 0.0% | undefined: TP = 0 | 0.1 | survey + method |
| D8 hover-diff | 18 | 9 | 5 | 2 | 1 | 66.7% | 72.0% · decided 78.3% | 72.0% | 123.5 | survey + method |
| U-D0 upstream crawler candidates | 11 | 3 | 11 | 3 | 0 | 78.6% | 44.0% · decided 50.0% | 61.1% | 5.2 | shared + method |
| U-D1 upstream tagged axe attribution | 21 | 8 | 1 | 3 | 0 | 72.4% | 84.0% · decided 95.5% | 82.4% | 7.7 | shared + method |
| U-D2 upstream inline attributes | 4 | 0 | 18 | 3 | 0 | 100.0% | 16.0% · decided 18.2% | 30.8% | 5.2 | shared + method |
| U-D2b upstream mouse handler properties | 9 | 1 | 13 | 3 | 0 | 90.0% | 36.0% · decided 40.9% | 56.3% | 5.2 | shared + method |
| U-D3 upstream missing tabindex | 7 | 0 | 15 | 3 | 0 | 100.0% | 28.0% · decided 31.8% | 48.3% | 5.2 | shared + method |
| U-D4 upstream CSS and class tokens | 22 | 14 | 0 | 3 | 0 | 61.1% | 88.0% · decided 100.0% | 75.9% | 5.2 | shared + method |
| U-D5 upstream direct CDP listeners | 17 | 1 | 5 | 3 | 0 | 94.4% | 68.0% · decided 77.3% | 85.0% | 7.3 | shared + method |
| U-D6 upstream registration shim | 12 | 0 | 10 | 3 | 0 | 100.0% | 48.0% · decided 54.5% | 70.6% | 5.2 | shared + method |
| U-D7 upstream React mouse props | 0 | 0 | 22 | 3 | 0 | undefined: flagged nothing | 0.0% · decided 0.0% | undefined: TP = 0 | 5.2 | shared + method |
| U-D8 upstream pixel hover difference | 16 | 14 | 6 | 3 | 0 | 53.3% | 64.0% · decided 72.7% | 61.5% | 114.7 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 22 | 14 | 0 | 3 | 0 | 61.1% | 88.0% · decided 100.0% | 75.9% | 7.3 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 22 | 15 | 0 | 3 | 0 | 59.5% | 88.0% · decided 100.0% | 74.6% | 116.8 | shared + components |
| C3 union, reject inert and pointer-events:none | 22 | 14 | 0 | 3 | 0 | 61.1% | 88.0% · decided 100.0% | 75.9% | 7.5 | shared + components |
| C4 union, additionally reject blocked center | 22 | 14 | 0 | 3 | 0 | 61.1% | 88.0% · decided 100.0% | 75.9% | 7.5 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 3 | 0 | 19 | 3 | 0 | 100.0% | 12.0% · decided 13.6% | 24.0% | 7.5 | shared + components |
| C6 visible label for a toggle absent from Tab | 0 | 1 | 21 | 4 | 1 | 0.0% | 0.0% · decided 0.0% | 0.0% [^kafe-f1] | 5.3 | shared + components |
| C7 ancestor mouse listener, minus Tab | 22 | 12 | 0 | 3 | 0 | 64.7% | 88.0% · decided 100.0% | 78.6% | 5.4 | shared + components |
| C8 union + focusable + label + ancestor leads | 22 | 15 | 0 | 3 | 0 | 59.5% | 88.0% · decided 100.0% | 74.6% | 7.6 | shared + components |
| C9 combined leads, additionally reject blocked center | 22 | 15 | 0 | 3 | 0 | 59.5% | 88.0% · decided 100.0% | 74.6% | 7.6 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 20 | 8 | 2 | 3 | 0 | 71.4% | 80.0% · decided 90.9% | 80.0% | 7.8 | C9 + rule observation |
| C11 = C10 minus roving-tabindex items (R2) | 20 | 8 | 2 | 3 | 0 | 71.4% | 80.0% · decided 90.9% | 80.0% | 8.0 | C9 + rule observation |
| C12 = C11 minus declared shortcuts (R3) | 20 | 8 | 2 | 3 | 0 | 71.4% | 80.0% · decided 90.9% | 80.0% | 8.0 | C9 + rule observation |
| C13 = C12 minus leads with no action path (R5) | 20 | 7 | 2 | 3 | 0 | 74.1% | 80.0% · decided 90.9% | 81.6% | 110.0 | C9 + rule observation |
| C14 = C13 minus name-twinned leads (R6) | 20 | 7 | 2 | 3 | 0 | 74.1% | 80.0% · decided 90.9% | 81.6% | 110.0 | C9 + rule observation |
| C15 = C14 minus leads with no click effect (R7, R8) | 19 | 4 | 3 | 3 | 1 | 82.6% | 76.0% · decided 86.4% | 84.4% | 337.7 | C9 + rule observation |
| C16 = C15 plus divergent-key-effect promotions (R9) | 19 | 4 | 3 | 3 | 1 | 82.6% | 76.0% · decided 86.4% | 84.4% | 337.7 | C9 + rule observation |
| D9 behavioural differential | 23 | 8 | 0 | 2 | 7 | 74.2% | 92.0% · decided 100.0% | 85.2% | 1422.6 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 24 | 8 | 0 | 1 | 7 | 75.0% | 96.0% · decided 100.0% | 85.7% | 1428.7 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 25 | 12 | 0 | 0 | 3 | 67.6% | 100.0% · decided 100.0% | 80.6% | 1715.6 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 25 | 12 | 0 | 0 | 3 | 67.6% | 100.0% · decided 100.0% | 80.6% | 1585.6 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 20 | 12 | 0 | 5 | 3 | 62.5% | 80.0% · decided 100.0% | 76.9% | 1354.4 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 20 | 12 | 0 | 5 | 3 | 62.5% | 80.0% · decided 100.0% | 76.9% | 1354.4 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 25 | 15 | 0 | 0 | 0 | 62.5% | 100.0% · decided 100.0% | 76.9% | 721.9 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 25 | 15 | 0 | 0 | 0 | 62.5% | 100.0% · decided 100.0% | 76.9% | 721.9 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 15 | 8 | 1 | 9 | 7 | 65.2% | 60.0% · decided 93.8% | 76.9% | 696.2 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 25 | 15 | 0 | 0 | 0 | 62.5% | 100.0% · decided 100.0% | 76.9% | 721.9 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 18 | 10 | 0 | 7 | 5 | 64.3% | 72.0% · decided 100.0% | 78.3% | 694.5 | priced at its arm |
| **KAFE (reference row: their published CSV output, not a local execution)** | 25 | 1 | 0 | 0 (decided all 40) | 0 (decided all 40) | 96.2% | 100.0% · decided 100.0% (all 40 decided) | 98.0% | 19978.6 | **full pipeline**, from their per-subject logs: proxy start-up, both graph crawls and Type 1 detection. Type 1 detection alone is 73.4, excludes both crawls, and is not comparable to an Axcess row. Amortised, their 2019 setup, not re-timed |

[^kafe-f1]: `KAFE-MATRIX.md` prints F1 0.0% for C6, which has TP 0 and a
defined precision of 0.0%. `MATRIX-RESULTS.md` prints `—` in the same
situation. Both mean there are no true positives. The artifact's value is kept
as it is.

### 5.2 fixtures — this project's blind-authored synthetic corpus; no external literature

95 element probes, 39 defects. Source: `MATRIX-RESULTS.md` / `derived/matrix.json`,
`closed` run. **These are development results, not accuracy**: the cheap
rules were written after reading errors on this corpus with its labels visible.
C16 has two rows because R9 was observed on two different probe sets.

| detector | TP | FP | FN | unknown pos | unknown neg | precision | strict recall | F1 | ms per element/button | timing scope |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 1 | 1 | 35 | 3 | 3 | 50.0% | 2.6% | 4.9% | 1.3 | survey + method |
| D1 axe-core (keyboard rules) | 0 | 1 | 36 | 3 | 3 | 0.0% | 0.0% | undefined: TP = 0 | 66.5 | survey + method |
| D1x axe-core (any rule, unsound) | 18 | 11 | 18 | 3 | 3 | 62.1% | 46.2% | 52.9% | 66.5 | survey + method |
| D2 inline onclick attribute | 1 | 0 | 35 | 3 | 3 | 100.0% | 2.6% | 5.0% | 1.3 | survey + method |
| D2b onclick property | 4 | 0 | 32 | 3 | 3 | 100.0% | 10.3% | 18.6% | 1.3 | survey + method |
| D3 tabindex / ARIA | 2 | 2 | 34 | 3 | 3 | 50.0% | 5.1% | 9.3% | 1.3 | survey + method |
| D4 CSS + lexical | 27 | 21 | 9 | 3 | 3 | 56.2% | 69.2% | 62.1% | 1.3 | survey + method |
| D5 CDP getEventListeners | 25 | 18 | 11 | 3 | 3 | 58.1% | 64.1% | 61.0% | 5.8 | survey + method |
| D6 addEventListener shim | 21 | 18 | 15 | 3 | 3 | 53.8% | 53.8% | 53.8% | 2.0 | survey + method |
| D7 React fiber props | 2 | 0 | 34 | 3 | 3 | 100.0% | 5.1% | 9.8% | 1.3 | survey + method |
| D8 hover-diff | 18 | 6 | 18 | 3 | 3 | 75.0% | 46.2% | 57.1% | 229.6 | survey + method |
| U-D0 upstream crawler candidates | 1 | 3 | 38 | 0 | 0 | 25.0% | 2.6% | 4.7% | 50.7 | shared + method |
| U-D1 upstream tagged axe attribution | 0 | 0 | 39 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 100.5 | shared + method |
| U-D2 upstream inline attributes | 1 | 0 | 38 | 0 | 0 | 100.0% | 2.6% | 5.0% | 50.8 | shared + method |
| U-D2b upstream mouse handler properties | 4 | 0 | 35 | 0 | 0 | 100.0% | 10.3% | 18.6% | 50.7 | shared + method |
| U-D3 upstream missing tabindex | 1 | 0 | 38 | 0 | 0 | 100.0% | 2.6% | 5.0% | 50.6 | shared + method |
| U-D4 upstream CSS and class tokens | 30 | 17 | 9 | 0 | 0 | 63.8% | 76.9% | 69.8% | 50.8 | shared + method |
| U-D5 upstream direct CDP listeners | 29 | 13 | 10 | 0 | 0 | 69.0% | 74.4% | 71.6% | 56.3 | shared + method |
| U-D6 upstream registration shim | 25 | 13 | 14 | 0 | 0 | 65.8% | 64.1% | 64.9% | 50.6 | shared + method |
| U-D7 upstream React mouse props | 2 | 0 | 37 | 0 | 0 | 100.0% | 5.1% | 9.8% | 50.7 | shared + method |
| U-D8 upstream pixel hover difference | 19 | 9 | 20 | 0 | 0 | 67.9% | 48.7% | 56.7% | 304.6 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 33 | 18 | 6 | 0 | 0 | 64.7% | 84.6% | 73.3% | 57.9 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 33 | 20 | 6 | 0 | 0 | 62.3% | 84.6% | 71.7% | 312.6 | shared + components |
| C3 union, reject inert and pointer-events:none | 32 | 13 | 6 | 1 | 1 | 71.1% | 82.0% | 76.2% | 60.3 | shared + components |
| C4 union, additionally reject blocked center | 32 | 11 | 6 | 1 | 1 | 74.4% | 82.0% | 78.0% | 60.3 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 3 | 0 | 36 | 0 | 0 | 100.0% | 7.7% | 14.3% | 59.8 | shared + components |
| C6 visible label for a toggle absent from Tab | 1 | 0 | 38 | 0 | 0 | 100.0% | 2.6% | 5.0% | 51.1 | shared + components |
| C7 ancestor mouse listener, minus Tab | 7 | 3 | 32 | 0 | 0 | 70.0% | 17.9% | 28.6% | 51.1 | shared + components |
| C8 union + focusable + label + ancestor leads | 37 | 13 | 1 | 1 | 1 | 74.0% | 94.9% | 83.2% | 61.9 | shared + components |
| C9 combined leads, additionally reject blocked center | 37 | 11 | 1 | 1 | 1 | 77.1% | 94.9% | 85.1% | 61.9 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 37 | 8 | 1 | 1 | 1 | 82.2% | 94.9% | 88.1% | 65.2 | C9 + R1 |
| C11 = C10 minus roving-tabindex items (R2) | 37 | 7 | 1 | 1 | 1 | 84.1% | 94.9% | 89.2% | 68.9 | C9 + R2 |
| C12 = C11 minus declared shortcuts (R3) | 37 | 6 | 1 | 1 | 1 | 86.0% | 94.9% | 90.2% | 68.9 | C9 + R3, same pass |
| C13 = C12 minus leads with no action path (R5) | 37 | 4 | 1 | 1 | 1 | 90.2% | 94.9% | 92.5% | 248.9 | C9 + R5 |
| C14 = C13 minus name-twinned leads (R6) | 37 | 3 | 1 | 1 | 1 | 92.5% | 94.9% | 93.7% | 248.9 | C9 + R6, free |
| C15 = C14 minus leads with no click effect (R7, R8) | 37 | 0 | 1 | 1 | 1 | 100.0% | 94.9% | 97.4% | 642.9 | C9 + behavioural pass |
| C16 = C15 plus divergent-key-effect promotions (R9) [observed 42 of 95: c12.json] | 38 | 0 | 0 | 1 | 1 | 100.0% | 97.4% | 98.7% | 642.9 | C9 + R9, same pass |
| C16 = C15 plus divergent-key-effect promotions (R9) [observed 95 of 95: all probes] | 38 | 11 | 0 | 1 | 1 | 77.6% | 97.4% | 86.4% | 1180.0 | C9 + R9, same pass |
| D9 behavioural differential | 34 | 5 | 2 | 3 | 17 | 87.2% | 87.2% | 87.2% | 2015.6 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 34 | 5 | 2 | 3 | 17 | 87.2% | 87.2% | 87.2% | 2015.6 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 33 | 4 | 3 | 3 | 17 | 89.2% | 84.6% | 86.8% | 2100.2 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 34 | 9 | 2 | 3 | 17 | 79.1% | 87.2% | 82.9% | 2015.6 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 36 | 10 | 3 | 0 | 4 | 78.3% | 92.3% | 84.7% | 1293.1 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 35 | 5 | 4 | 0 | 4 | 87.5% | 89.7% | 88.6% | 1293.1 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 32 | 24 | 4 | 3 | 7 | 57.1% | 82.0% | 67.4% | 1017.6 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 32 | 24 | 4 | 3 | 7 | 57.1% | 82.0% | 67.4% | 1017.6 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 33 | 11 | 6 | 0 | 4 | 75.0% | 84.6% | 79.5% | 950.5 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 36 | 31 | 0 | 3 | 7 | 53.7% | 92.3% | 67.9% | 1017.6 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 37 | 12 | 2 | 0 | 4 | 75.5% | 94.9% | 84.1% | 950.5 | priced at its arm |

### 5.3 gds — UK Government Digital Service, *Accessibility Tool Audit* (MIT, Crown Copyright 2017; no DOI)

6 IAF cases + 2 controls = 8 element targets. Published competitor result:
**all 13 audited tools score 0 of 6**. Source: `MATRIX-RESULTS.md` /
`derived/matrix.json`, `closed` run. The artifact records one internal
disagreement: for D8 hover-diff, `bakeoff-gds-closed.json` and
`bakeoff-gds-closed-full.json` disagree (1/0/5 vs 0/0/6). The row below is the
one `MATRIX-RESULTS.md` publishes.

| detector | TP | FP | FN | unknown pos | unknown neg | precision | strict recall | F1 | ms per element/button | timing scope |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 1 | 0 | 5 | 0 | 0 | 100.0% | 16.7% | 28.6% | 1.2 | survey + method |
| D1 axe-core (keyboard rules) | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1399.9 | survey + method |
| D1x axe-core (any rule, unsound) | 0 | 1 | 6 | 0 | 0 | 0.0% | 0.0% | undefined: TP = 0 | 1399.9 | survey + method |
| D2 inline onclick attribute | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1.2 | survey + method |
| D2b onclick property | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1.2 | survey + method |
| D3 tabindex / ARIA | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1.2 | survey + method |
| D4 CSS + lexical | 3 | 0 | 3 | 0 | 0 | 100.0% | 50.0% | 66.7% | 1.2 | survey + method |
| D5 CDP getEventListeners | 3 | 0 | 3 | 0 | 0 | 100.0% | 50.0% | 66.7% | 7.7 | survey + method |
| D6 addEventListener shim | 3 | 0 | 3 | 0 | 0 | 100.0% | 50.0% | 66.7% | 1.9 | survey + method |
| D7 React fiber props | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1.2 | survey + method |
| D8 hover-diff | 1 | 0 | 5 | 0 | 0 | 100.0% | 16.7% | 28.6% | 176.8 | survey + method |
| U-D0 upstream crawler candidates | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 281.7 | shared + method |
| U-D1 upstream tagged axe attribution | 0 | 1 | 6 | 0 | 0 | 0.0% | 0.0% | undefined: TP = 0 | 1697.7 | shared + method |
| U-D2 upstream inline attributes | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 281.7 | shared + method |
| U-D2b upstream mouse handler properties | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 281.6 | shared + method |
| U-D3 upstream missing tabindex | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 281.7 | shared + method |
| U-D4 upstream CSS and class tokens | 0 | 0 | 4 | 2 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 375.6 | shared + method |
| U-D5 upstream direct CDP listeners | 0 | 0 | 4 | 2 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 379.0 | shared + method |
| U-D6 upstream registration shim | 0 | 0 | 4 | 2 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 375.3 | shared + method |
| U-D7 upstream React mouse props | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 281.6 | shared + method |
| U-D8 upstream pixel hover difference | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 281.0 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 3 | 0 | 3 | 0 | 0 | 100.0% | 50.0% | 66.7% | 286.4 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 3 | 0 | 3 | 0 | 0 | 100.0% | 50.0% | 66.7% | 286.8 | shared + components |
| C3 union, reject inert and pointer-events:none | 0 | 0 | 3 | 3 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 460.3 | shared + components |
| C4 union, additionally reject blocked center | 0 | 0 | 3 | 3 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 460.3 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 288.7 | shared + components |
| C6 visible label for a toggle absent from Tab | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 281.9 | shared + components |
| C7 ancestor mouse listener, minus Tab | 0 | 0 | 6 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 281.9 | shared + components |
| C8 union + focusable + label + ancestor leads | 0 | 0 | 3 | 3 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 463.7 | shared + components |
| C9 combined leads, additionally reject blocked center | 0 | 0 | 3 | 3 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 463.7 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 0 | 0 | 3 | 3 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 477.2 | C9 + R1 |
| C11 = C10 minus roving-tabindex items (R2) | 0 | 0 | 3 | 3 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 482.8 | C9 + R2 |
| C12 = C11 minus declared shortcuts (R3) | 0 | 0 | 3 | 3 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 482.8 | C9 + R3, same pass |
| C13 = C12 minus leads with no action path (R5) | 0 | 0 | 3 | 3 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 748.5 | C9 + R5 |
| C14 = C13 minus name-twinned leads (R6) | 0 | 0 | 3 | 3 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 748.5 | C9 + R6, free |
| C15 = C14 minus leads with no click effect (R7, R8) | 0 | 0 | 3 | 3 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 2668.4 | C9 + behavioural pass |
| C16 = C15 plus divergent-key-effect promotions (R9) | 0 | 0 | 3 | 3 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 2668.4 | C9 + R9, same pass |
| D9 behavioural differential | 2 | 0 | 2 | 2 | 0 | 100.0% | 33.3% | 50.0% | 3613.3 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 2 | 0 | 2 | 2 | 0 | 100.0% | 33.3% | 50.0% | 3613.3 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 2 | 0 | 2 | 2 | 0 | 100.0% | 33.3% | 50.0% | 3889.4 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 2 | 0 | 2 | 2 | 0 | 100.0% | 33.3% | 50.0% | 3613.3 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 0 | 0 | 0 | 6 | 2 | undefined: abstained on all 8 | 0.0% | undefined: TP = 0 | n/a: decided 0 of 8 (ms/target 1437.6) | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 0 | 0 | 0 | 6 | 2 | undefined: abstained on all 8 | 0.0% | undefined: TP = 0 | n/a: decided 0 of 8 (ms/target 1437.6) | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 0 | 0 | 0 | 6 | 2 | undefined: abstained on all 8 | 0.0% | undefined: TP = 0 | n/a: decided 0 of 8 (ms/target 762.7) | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 0 | 0 | 0 | 6 | 2 | undefined: abstained on all 8 | 0.0% | undefined: TP = 0 | n/a: decided 0 of 8 (ms/target 762.7) | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 0 | 0 | 0 | 6 | 2 | undefined: abstained on all 8 | 0.0% | undefined: TP = 0 | n/a: decided 0 of 8 (ms/target 762.7) | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 0 | 0 | 0 | 6 | 2 | undefined: abstained on all 8 | 0.0% | undefined: TP = 0 | n/a: decided 0 of 8 (ms/target 762.7) | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 0 | 0 | 0 | 6 | 2 | undefined: abstained on all 8 | 0.0% | undefined: TP = 0 | n/a: decided 0 of 8 (ms/target 762.7) | priced at its arm |

### 5.4 ma11y — mutants built with the operators of Tafreshipour et al., ISSTA 2024, DOI 10.1145/3650212.3652113

1 verified fault (operator F55) + 6 controls = 7 element targets, generated here
from the GDS page. **This is a sanity check, not a benchmark**: one fault cannot
support a precision/recall comparison, and no published result exists for this
corpus. Source: `MATRIX-RESULTS.md` / `derived/matrix.json`, `closed` run.

| detector | TP | FP | FN | unknown pos | unknown neg | precision | strict recall | F1 | ms per element/button | timing scope |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 1 | 0 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 1.9 | survey + method |
| D1 axe-core (keyboard rules) | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 569.2 | survey + method |
| D1x axe-core (any rule, unsound) | 0 | 3 | 1 | 0 | 0 | 0.0% | 0.0% | undefined: TP = 0 | 569.2 | survey + method |
| D2 inline onclick attribute | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1.9 | survey + method |
| D2b onclick property | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1.9 | survey + method |
| D3 tabindex / ARIA | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1.9 | survey + method |
| D4 CSS + lexical | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1.9 | survey + method |
| D5 CDP getEventListeners | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 6.6 | survey + method |
| D6 addEventListener shim | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 2.8 | survey + method |
| D7 React fiber props | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1.9 | survey + method |
| D8 hover-diff | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 219.7 | survey + method |
| U-D0 upstream crawler candidates | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 985.9 | shared + method |
| U-D1 upstream tagged axe attribution | 0 | 3 | 1 | 0 | 0 | 0.0% | 0.0% | undefined: TP = 0 | 1509.6 | shared + method |
| U-D2 upstream inline attributes | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 985.7 | shared + method |
| U-D2b upstream mouse handler properties | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 985.5 | shared + method |
| U-D3 upstream missing tabindex | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 985.6 | shared + method |
| U-D4 upstream CSS and class tokens | 0 | 0 | 0 | 1 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1151.9 | shared + method |
| U-D5 upstream direct CDP listeners | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 989.3 | shared + method |
| U-D6 upstream registration shim | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 985.1 | shared + method |
| U-D7 upstream React mouse props | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 987.5 | shared + method |
| U-D8 upstream pixel hover difference | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 984.4 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 1 | 0 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 999.4 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 1 | 0 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 1002.6 | shared + components |
| C3 union, reject inert and pointer-events:none | 0 | 0 | 0 | 1 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1173.6 | shared + components |
| C4 union, additionally reject blocked center | 0 | 0 | 0 | 1 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1173.6 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1010.4 | shared + components |
| C6 visible label for a toggle absent from Tab | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 987.7 | shared + components |
| C7 ancestor mouse listener, minus Tab | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 987.7 | shared + components |
| C8 union + focusable + label + ancestor leads | 0 | 0 | 0 | 1 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1186.0 | shared + components |
| C9 combined leads, additionally reject blocked center | 0 | 0 | 0 | 1 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1186.0 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 0 | 0 | 0 | 1 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 1200.7 | C9 + R1 |
| C11 = C10 minus roving-tabindex items (R2) | 0 | 0 | 0 | 1 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 1226.6 | C9 + R2 |
| C12 = C11 minus declared shortcuts (R3) | 0 | 0 | 0 | 1 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 1226.6 | C9 + R3, same pass |
| C13 = C12 minus leads with no action path (R5) | 0 | 0 | 0 | 1 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 1476.4 | C9 + R5 |
| C14 = C13 minus name-twinned leads (R6) | 0 | 0 | 0 | 1 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 1476.4 | C9 + R6, free |
| C15 = C14 minus leads with no click effect (R7, R8) | 0 | 0 | 0 | 1 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 3238.4 | C9 + behavioural pass |
| C16 = C15 plus divergent-key-effect promotions (R9) | 0 | 0 | 0 | 1 | 0 | undefined: C9 abstains (§2.4) | 0.0% | undefined: TP = 0 | 3238.4 | C9 + R9, same pass |
| D9 behavioural differential | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 4454.5 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 0 | 0 | 1 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 4454.5 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 1 | 0 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4642.3 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 1 | 0 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4454.5 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 0 | 0 | 0 | 1 | 3 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 4600.5 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 0 | 0 | 0 | 1 | 3 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 4600.5 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 0 | 0 | 0 | 1 | 3 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 2219.8 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 0 | 0 | 0 | 1 | 3 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 2219.8 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 0 | 0 | 0 | 1 | 3 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 2219.8 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 0 | 0 | 0 | 1 | 3 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 2219.8 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 0 | 0 | 0 | 1 | 3 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 2219.8 | priced at its arm |

### 5.5 edgecases — this project's shared-author development corpus; no external literature

74 element targets. **Carries no unbiased accuracy claim**: it was written
alongside the detectors it scores. It is included for completeness, and for the
CDP-overflow fix it exercises. Source: `MATRIX-RESULTS.md` /
`derived/matrix.json`, `closed` run.

| detector | TP | FP | FN | unknown pos | unknown neg | precision | strict recall | F1 | ms per element/button | timing scope |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 9 | 0 | 29 | 2 | 0 | 100.0% | 22.5% | 36.7% | 1.7 | survey + method |
| D1 axe-core (keyboard rules) | 1 | 1 | 37 | 2 | 0 | 50.0% | 2.5% | 4.8% | 95.9 | survey + method |
| D1x axe-core (any rule, unsound) | 23 | 13 | 15 | 2 | 0 | 63.9% | 57.5% | 60.5% | 95.9 | survey + method |
| D2 inline onclick attribute | 2 | 0 | 36 | 2 | 0 | 100.0% | 5.0% | 9.5% | 1.7 | survey + method |
| D2b onclick property | 3 | 0 | 35 | 2 | 0 | 100.0% | 7.5% | 14.0% | 1.7 | survey + method |
| D3 tabindex / ARIA | 3 | 0 | 35 | 2 | 0 | 100.0% | 7.5% | 14.0% | 1.7 | survey + method |
| D4 CSS + lexical | 28 | 15 | 10 | 2 | 0 | 65.1% | 70.0% | 67.5% | 1.7 | survey + method |
| D5 CDP getEventListeners | 31 | 13 | 7 | 2 | 0 | 70.5% | 77.5% | 73.8% | 7.5 | survey + method |
| D6 addEventListener shim | 27 | 13 | 11 | 2 | 0 | 67.5% | 67.5% | 67.5% | 2.7 | survey + method |
| D7 React fiber props | 0 | 0 | 38 | 2 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 1.7 | survey + method |
| D8 hover-diff | 2 | 1 | 36 | 2 | 0 | 66.7% | 5.0% | 9.3% | 194.7 | survey + method |
| U-D0 upstream crawler candidates | 11 | 2 | 29 | 0 | 0 | 84.6% | 27.5% | 41.5% | 55.4 | shared + method |
| U-D1 upstream tagged axe attribution | 1 | 0 | 39 | 0 | 0 | 100.0% | 2.5% | 4.9% | 109.3 | shared + method |
| U-D2 upstream inline attributes | 2 | 0 | 38 | 0 | 0 | 100.0% | 5.0% | 9.5% | 55.4 | shared + method |
| U-D2b upstream mouse handler properties | 3 | 0 | 37 | 0 | 0 | 100.0% | 7.5% | 14.0% | 55.2 | shared + method |
| U-D3 upstream missing tabindex | 4 | 0 | 36 | 0 | 0 | 100.0% | 10.0% | 18.2% | 55.3 | shared + method |
| U-D4 upstream CSS and class tokens | 34 | 12 | 6 | 0 | 0 | 73.9% | 85.0% | 79.1% | 55.2 | shared + method |
| U-D5 upstream direct CDP listeners | 32 | 9 | 8 | 0 | 0 | 78.0% | 80.0% | 79.0% | 61.0 | shared + method |
| U-D6 upstream registration shim | 29 | 9 | 11 | 0 | 0 | 76.3% | 72.5% | 74.4% | 55.2 | shared + method |
| U-D7 upstream React mouse props | 0 | 0 | 40 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 55.2 | shared + method |
| U-D8 upstream pixel hover difference | 7 | 3 | 33 | 0 | 0 | 70.0% | 17.5% | 28.0% | 308.8 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 36 | 13 | 4 | 0 | 0 | 73.5% | 90.0% | 80.9% | 62.6 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 37 | 14 | 3 | 0 | 0 | 72.5% | 92.5% | 81.3% | 317.1 | shared + components |
| C3 union, reject inert and pointer-events:none | 35 | 11 | 4 | 1 | 0 | 76.1% | 87.5% | 81.4% | 64.8 | shared + components |
| C4 union, additionally reject blocked center | 32 | 10 | 7 | 1 | 0 | 76.2% | 80.0% | 78.0% | 64.8 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 2 | 1 | 38 | 0 | 0 | 66.7% | 5.0% | 9.3% | 64.7 | shared + components |
| C6 visible label for a toggle absent from Tab | 0 | 0 | 40 | 0 | 0 | undefined: flagged nothing | 0.0% | undefined: TP = 0 | 55.7 | shared + components |
| C7 ancestor mouse listener, minus Tab | 9 | 0 | 31 | 0 | 0 | 100.0% | 22.5% | 36.7% | 55.7 | shared + components |
| C8 union + focusable + label + ancestor leads | 37 | 12 | 2 | 1 | 0 | 75.5% | 92.5% | 83.2% | 66.4 | shared + components |
| C9 combined leads, additionally reject blocked center | 34 | 11 | 5 | 1 | 0 | 75.6% | 85.0% | 80.0% | 66.4 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 34 | 9 | 5 | 1 | 0 | 79.1% | 85.0% | 81.9% | 69.8 | C9 + R1 |
| C11 = C10 minus roving-tabindex items (R2) | 34 | 9 | 5 | 1 | 0 | 79.1% | 85.0% | 81.9% | 73.2 | C9 + R2 |
| C12 = C11 minus declared shortcuts (R3) | 34 | 9 | 5 | 1 | 0 | 79.1% | 85.0% | 81.9% | 73.2 | C9 + R3, same pass |
| C13 = C12 minus leads with no action path (R5) | 33 | 7 | 6 | 1 | 0 | 82.5% | 82.5% | 82.5% | 253.2 | C9 + R5 |
| C14 = C13 minus name-twinned leads (R6) | 30 | 7 | 9 | 1 | 0 | 81.1% | 75.0% | 77.9% | 253.2 | C9 + R6, free |
| C15 = C14 minus leads with no click effect (R7, R8) | 29 | 5 | 10 | 1 | 0 | 85.3% | 72.5% | 78.4% | 1153.2 | C9 + behavioural pass |
| C16 = C15 plus divergent-key-effect promotions (R9) | 30 | 5 | 9 | 1 | 0 | 85.7% | 75.0% | 80.0% | 1153.2 | C9 + R9, same pass |
| D9 behavioural differential | 35 | 4 | 2 | 3 | 8 | 89.7% | 87.5% | 88.6% | 1665.9 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 35 | 4 | 2 | 3 | 8 | 89.7% | 87.5% | 88.6% | 1665.9 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 35 | 5 | 2 | 3 | 8 | 87.5% | 87.5% | 87.5% | 1745.4 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 35 | 5 | 2 | 3 | 8 | 87.5% | 87.5% | 87.5% | 1665.9 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 32 | 5 | 7 | 1 | 3 | 86.5% | 80.0% | 83.1% | 1243.5 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 32 | 5 | 7 | 1 | 3 | 86.5% | 80.0% | 83.1% | 1243.5 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 34 | 15 | 3 | 3 | 3 | 69.4% | 85.0% | 76.4% | 577.0 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 34 | 15 | 3 | 3 | 3 | 69.4% | 85.0% | 76.4% | 577.0 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 33 | 5 | 6 | 1 | 3 | 86.8% | 82.5% | 84.6% | 560.5 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 37 | 24 | 0 | 3 | 3 | 60.7% | 92.5% | 73.3% | 577.0 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 35 | 12 | 4 | 1 | 3 | 74.5% | 87.5% | 80.5% | 560.5 | priced at its arm |

## 6. The comparison runs one way

All 48 Axcess detectors were scored on KAFE's own corpus, against KAFE's own
published result. KAFE's detector was never scored on `fixtures`, `gds`,
`ma11y` or `edgecases`. The CEO considered rebuilding KAFE's Java / Selenium
3.141.5 / Firefox 68 stack to close the reverse direction and decided not to
(`BRIEF-ASYMMETRY.md`). This is a scope boundary, not pending work.

A second obstacle would remain even with their binary running. KAFE emits page
labels, and our corpora label elements. Scoring KAFE on them would need a
page-to-element mapping invented for the purpose, and that mapping, not KAFE's
detector, would decide the result.

The asymmetry has two consequences. Measuring our detectors on someone else's
benchmark, against their published numbers, is the harder and more exposed
direction, and it is the one this study took. But **nothing in this work
validates our own corpora from outside**. `edgecases` is shared-author, and
`fixtures` was authored here too. No outside tool has been scored on either.
Of the four element corpora, only `gds` carries a published competitor result,
the audit's own 0-of-6 for 13 tools. That result does not come from KAFE.

## 7. The 300 ms per-button ceiling

The CEO's ceiling is **per-button detection latency**. Read the cost columns
with three facts in mind:

1. **None of the main-table figures is latency measured per button.** Every
   ms/button in §5 is a total time divided by a button count (§4). On KAFE's
   corpus our denominator is every candidate probed. On the element corpora it
   is the probes the detector decided. The two Axcess quotients are therefore
   not the same unit either.
2. **KAFE has two figures, from its own per-subject timing logs**
   (`execTime.csv`, `execTimeDetection.csv`), each divided by their
   `Size of All Visible Ctrl Nodes`. Both were taken with their instrument on
   their 2019 Firefox 68 / Selenium setup and were not re-timed here:

   | KAFE cost per visible control | pooled (40) | median (40) | min–max (40) | under 300 ms (40) | pooled (60) | median (60) | min–max (60) | under 300 ms (60) |
   |---|---:|---:|---:|---:|---:|---:|---:|---:|
   | Type 1 detection alone | 73.4 | 122.6 | 7.2–636.1 | 35 of 40 | 65.5 | 104.3 | 6.2–636.1 | 53 of 60 |
   | both crawls (phases 02, 03, 05, 08, 09, 10) | 3,198.3 | 4,486.2 | 672.4–16,133.9 | 0 of 40 | 3,201.3 | 3,866.2 | 330.8–22,359.7 | 0 of 60 |
   | **full pipeline** (phases 00–11 + Type 1) | **19,978.6** | 27,668.0 | 5,182.0–68,265.3 | **0 of 40** | 23,261.2 | 24,004.7 | 5,182.0–130,006.9 | 0 of 60 |

   **The full pipeline is the figure comparable to Axcess's**, because every
   Axcess figure includes that detector's own browser work (navigation, tab
   walks, behavioural passes), and KAFE's verdict needs both of its crawls.
   Type 1 detection alone is the graph comparison once both graphs exist. It
   excludes the crawls, so it understates KAFE's cost the way an Axcess D9
   figure without its tab walk would. Type 2 detection is counted in neither.
   The full pipeline averages 19.33 min per subject over all 60, against
   their paper's 19.22. Of it, 44.8% on the 40 is proxy initialisation, which
   no Axcess figure includes. None of these is a measured per-button latency,
   and none was measured the same way as any Axcess figure. They compare as
   orders of magnitude only.
3. **The only direct per-button measurement is outside the main table.**
   `TIMING-AND-SPOTCHECK.md` timed one `run_probe` call of the frozen
   `DifferentialRunner` (the D9 machinery) per button: 3 probes × 2 repeats,
   median **1,479.3 ms**, all 6 over 300 ms, with the once-per-page tab walk
   excluded.

Against 300 ms/button, read as the §5 quotient:

| corpus | rows at or under 300 ms/button | source |
|---|---:|---|
| KAFE | 35 of 48 Axcess rows. KAFE's own full pipeline (19,978.6) is over, on 0 of 40 subjects under; its Type 1 detection alone (73.4, not comparable) is under | §5.1 |
| fixtures | 33 of 49 rows | `MATRIX-RESULTS.md` cost table |
| gds | 20 of 41 timed rows (7 rows decided no target and have no ms/button) | `MATRIX-RESULTS.md` cost table |
| ma11y | 9 of 48 rows | `MATRIX-RESULTS.md` cost table |
| edgecases | 33 of 48 rows | `MATRIX-RESULTS.md` cost table |

By detector:

- **Clear 300 ms/button on all five corpora:** D0, D2, D2b, D3, D4, D5, D6, D7
  and D8, the cheap single-signal tier. On `ma11y` they are the only nine that
  clear.
- **Clear it on no corpus, wherever timed:** C15, C16, the six D9 variants (D9,
  D9+S4ours, D9+S4u, D9-noS4, D9u, D9u+S4u) and the five D10 variants (D10a,
  D10a+base, D10a-u, D10b, D10b-u). Every row in this group runs a behavioural
  pass (timing scope `measured`, `priced at its arm`, or `C9 + behavioural
  pass`), and on KAFE's corpus the group includes one of the two best-F1 rows
  (D9+S4ours, 1428.7). The other, D5 (3.2), is in the cheap tier above, which
  clears the ceiling on every corpus.
- **Depend on the corpus:** D1, D1x, U-D0–U-D8 and C1–C14. All are over on
  `ma11y`. On KAFE's corpus all are under. On `fixtures` and `edgecases` all
  are under except U-D8 and C2. On `gds`, U-D0, U-D2, U-D2b, U-D3, U-D7, U-D8,
  C1, C2, C5, C6 and C7 clear at 281–289 ms, and D1, D1x, U-D1, U-D4–U-D6, C3,
  C4 and C8–C14 do not.

## 8. Scope, threats, and what no artifact contains

### 8.1 Scope

The five benchmarks in §3.1 are the whole study. **BAGEL** (CHI 2023) was also
attempted, but its artifact proved inaccessible, so it is not replicated here
(`LITERATURE.md`). It was tried, not overlooked.

### 8.2 Threats to validity that are not closed

- **The candidate universe is Axcess's own.** On KAFE's corpus, `data-probe` can
  only be placed on elements that Axcess's `collect_candidates` surfaced. No
  detector, upstream `U-D*` or `C*` combination included, can propose an element
  it missed. `KAFE-MATRIX-REPORT.md` §1.1 calls this the largest unclosed
  threat to validity. KAFE's node-selection code was never published, so
  containment cannot be checked; `KAFE-HIGHLIGHTS.md` caveat 4 gives the
  node-count comparison that was possible.
- **Candidates are top-frame only.** A control inside an iframe is outside the
  universe for every row.
- **Offline replay is not the live page.** Six KAFE subjects replay with no
  controls at all, and the replay router marks many others functionally
  degraded.
- **Not KAFE's browser or hardware.** Headless Chromium under Playwright on one
  shared machine, against KAFE's Firefox 68 through Selenium.
- **Scoring conventions differ by corpus.** KAFE's corpus is scored per page,
  and a page with any undecided candidate cannot be negative. The element
  corpora are scored per element probe.

### 8.3 Numbers this report needed and no artifact contains

Each of these is stated as missing. None was generated for this report.

- Strict recall over all 53 attempted KAFE subjects. Strict recall and the
  unknown-positive/negative split now exist on the 40 scored subjects (§4),
  the basis KAFE's own row uses. A 53-subject figure would count the 13
  whole-subject abstentions as unknown for every row and is not reported.
- Element-level precision on KAFE's corpus: KAFE's labels are per page.
- A like-for-like KAFE cost. Their logs give the full pipeline and Type 1
  detection separately, but nothing isolates the part of an Axcess figure that
  corresponds to KAFE's proxy start-up or crawls (§7).
- Latency measured per button for any main-table detector (§7). The 6-trial
  probe in `TIMING-AND-SPOTCHECK.md` is the only per-button timing.
- Any KAFE result on `fixtures`, `gds`, `ma11y` or `edgecases` (§6).

A `craigslist` result used to be listed here as missing. It now exists and is
in every KAFE-corpus figure (§3.2, §8.4).

### 8.4 Corrections made while preparing this report

The addendum assigned the first set of corrections to this work, and none of
them moves a table cell. The two later corrections (`BRIEF-COST-FIX.md`) do
move cells, and each names every cell it moved. Both were made on the 39
subjects then scored, and their figures are quoted below as they stood at the
time. The last entry, the `craigslist` update (`BRIEF-CRAIGSLIST-UPDATE.md`),
moves every KAFE-corpus figure to the 40 now scored, and it names what moved.

- **`KAFE-HIGHLIGHTS.md`:**
  - The R1/R6 claim now says R1 does the most work of any rule, and that R2,
    R3, R6 and R9 have no effect.
  - "29 of 46 faster than KAFE" is now 28 of 46 (30 of 48). The old figure was
    never computed.
  - KAFE-corpus recall is relabelled "recall (decided)", and the recall delta
    against the fixtures' strict recall is removed.
  - The fixtures comparison now shows all three C15/C16 rows.
  - "17 detectors match KAFE's 100% recall" is now 19, counted from
    `KAFE-MATRIX.md`, and is qualified as decided-only recall. This error was
    not on the addendum's list; it was found while fixing the recall labelling.
  - `craigslist` is no longer called "not attempted".
- **`MATRIX-RESULTS.md`:** the note under the ma11y table is corrected. It had
  been copied from gds: C9 abstains once there, not three times, and D4, D5
  and D6 miss the ma11y fault rather than find it.
- **`tools/kafe_matrix.py`** (the generator behind `KAFE-MATRIX.md` and
  `KAFE-MATRIX-REPORT.md`; nothing under `src/audit/`):
  - The false "both ms columns are computed the same way on both sides" is
    replaced with what is actually shared (the pooling arithmetic) and what is
    not (instrument, hardware, browser, control count). It also no longer
    calls the 300 ms ceiling KAFE's.
  - §1.3 now reads all five capdiag runs, including the two that survive only
    in `derived/capdiag-runs.log`, and checks them against the three surviving
    JSON files. As a result, `spotify` is shown as capped in 2 of 5 runs, not
    as "freed".
  - The one-way-comparison section (§1.7), previously added by hand, is now
    generated, so regenerating no longer deletes it.
  - The "Never attempted" heading for `craigslist` is replaced.
- **Regenerated:** `KAFE-MATRIX.md`, `KAFE-MATRIX-REPORT.md` and the three
  `derived/kafe_matrix_*.json` summaries were regenerated from the corrected
  generator (`controls`, `assemble`, `report`; 2026-09-23 00:53 UTC) from the
  same 52 JSONL lines. `git diff` against the committed versions shows only
  the timestamps and the corrected prose: the ms paragraph and method note,
  the 5-run §1.3, and the `craigslist` heading. No table number moved, and the
  generated §1.7 is identical to the hand-added one it replaces.
  `tests/test_capdiag.py` passes (8 tests).

**Correction: KAFE's cost was quoted from a column that is not a per-subject
time.** Earlier versions of this report, `KAFE-HIGHLIGHTS.md` and
`KAFE-MATRIX.md` gave KAFE's cost as **25.7 ms per button**: the results CSV's
`Detection` column, pooled over the 39 and divided by `Size of All Visible Ctrl
Nodes`. They set that figure against Axcess's per-button timings as if both
were a detector's full cost. That was wrong twice over:

1. **Scope.** Even taken at face value, a detection-only figure excludes both
   of KAFE's graph crawls, while every Axcess figure includes its own browser
   work.
2. **The column is not per-subject detection time.** The evidence:
   - Listed alphabetically (the CSV's order), `Detection` falls only 2 times
     in 59 steps, and so does `Localization`. The CSV's crawl and extraction
     columns fall 27–30 times, and KAFE's own per-subject `01-Type1Detection`
     falls 26 times. `Detection`'s correlation with alphabetical rank is 0.93,
     against 0.02 for `01-Type1Detection`. Its correlation with the
     visible-control count is 0.05.
   - KAFE's per-subject `execTimeDetection.csv` disagrees with it by more
     than 5% on 59 of 60 subjects. The median ratio (log ÷ CSV) is 3.5, and it
     ranges from 0.38 (`ssa`) to 75 (`4shared`). The logged value is higher on
     55 of 60 subjects. Examples: `4shared` 4,959 ms against 66; `adorama`
     2,135 against 69; `bbc` 2,193 against 141.
   - The same logs agree with the CSV's other six columns (below), so they
     describe the same pipeline. Only `Detection` and `Localization` do not
     match.
   - What the column does measure was not established. An intermediate
     reading of it as a running total, differenced per subject, is also
     contradicted by the logs and is used nowhere.

**KAFE's per-subject logs.** `tools/fetch_kafe_output.py` fetched
`execTime.csv`, `execTimeDetection.csv` and `resultsSubjectStats.csv` for all
60 subjects from KAFE's `KAFE_output` Drive folder into the git-ignored
`artifacts/kafe_output/`. They are unlicensed third-party files and are not
committed. No file is missing, empty or unparseable. The 14 `execTime.csv`
phases map onto the results CSV's columns as follows. Each mapping was chosen
by testing every combination of up to four phases per column, and each best
fit matches the phase names. The ratio is per-subject log ÷ CSV, over all 60:

| results CSV column | per-subject phases | median ratio | within ±5% | within ±10% | pooled ratio | subjects off by >25% |
|---|---|---:|---:|---:|---:|---:|
| `InitializeProxyKnfg` | 00 | 1.007 | 17 of 60 | 28 of 60 | 1.028 | 15 |
| `ExtractNodesKnfg` | 01 + 04 | 0.991 | 38 of 60 | 44 of 60 | 1.035 | 8 |
| `CrawlKnfg` | 02 + 03 + 05 | 1.008 | 45 of 60 | 52 of 60 | 1.028 | 4 |
| `InitializeProxyPcnfg` | 06 | 1.019 | 16 of 60 | 31 of 60 | 0.978 | 12 |
| `ExtractNodesPcnfg` | 07 + 11 | 1.001 | 38 of 60 | 38 of 60 | 0.989 | 16 |
| `CrawlPcnfg` | 08 + 09 + 10 | 1.006 | 37 of 60 | 47 of 60 | 1.023 | 8 |
| `Detection` | **none**: vs `01-Type1Detection` | 3.48 | 1 of 60 | 1 of 60 | 3.28 | 58 |
| `Localization` | **none** (not used) | — | — | — | — | — |
| (not a CSV column) | 12, 13 `TotalConstruct*` | — | — | — | — | — |

Phases 12 and 13 equal phase 05 (resp. 10) plus 0.3–0.7 s (resp. 0.3–3.7 s).
They overlap other phases, so they are not summed. The six mapped columns agree
at the median and when pooled, but **not subject for subject everywhere**. The
two proxy-start-up columns are only loosely matched, and some subjects are off
by up to a factor of 6 (worst: `indiegogo` `CrawlKnfg` 5.96×, `dell`
`ExtractNodesPcnfg` 3.85×, `gizmodo` `CrawlPcnfg` 3.12×). `resultsSubjectStats.csv`
also differs from the results CSV's node counts in 8 values on 5 subjects
(`boostmobile`, `indiegogo`, `instagram`, `resellerratings`, `usgsgov`). The only
difference in the denominator is `resellerratings`: 50 visible controls in its
own file against 146 in the CSV. So the logs look like a separate run of the
same pipeline, not the same record. The denominator is kept from the results
CSV, the one the accuracy rows use. With the per-subject counts instead, the
39-subject pooled figures would be 90.0 (Type 1) and 24,260.9 (full pipeline),
and no under-300 count would change. On the 40 now scored they would be 77.5
and 21,086.6 (`craigslist` has 288 visible controls in both files), and again
no under-300 count changes.

**What changed.** KAFE's cost is now the full pipeline (22,747.5 ms per
button pooled over the 39 at the time; 19,978.6 over the 40 since the
`craigslist` update), with Type 1 detection alone (84.4; now 73.4) beside it,
as in §7. "Faster than KAFE" is re-derived on the full pipeline: 48 of 48 (46 of 46).
The detection-only count stays 30 of 48 (28 of 46), labelled as not
comparable. Cells moved:

- `KAFE-MATRIX.md` KAFE row: `ms/button` 25.7 → 22747.5, `ms/subject`
  1012.7 → 897652.7, and `ms covers`. No other number in that table moved.
- This report's §5.1 KAFE row: ms 25.7 → 22747.5 and its timing scope. The
  §7 table is new.
- `KAFE-HIGHLIGHTS.md`: every cost comparison.
- `tools/kafe_matrix.py`: the KAFE row and the "KAFE on the same denominator"
  section now read the per-subject logs. The results-CSV figures are kept in
  `derived/kafe_matrix_summary.json` only under `results_csv_detection_column`,
  marked as not a cost.

**Correction: strict recall and the unknown split on KAFE's corpus.** §5.1
used to read `n/a (N abst.)` in both unknown columns, where N counted
abstentions over the **52 attempted** subjects, in a table whose denominator
is **39**. It also read `n/a` for strict recall, and §4, §1 and §8.3 said
neither could be computed. They can: `derived/kafe_matrix.jsonl` holds every
detector's verdict on every subject. `tools/kafe_matrix.py assemble` now
computes `unknown_positive`, `unknown_negative` and `recall_strict` on the
39-subject basis. `KAFE-MATRIX.md` gains `unk pos`, `unk neg` and `strict
recall` columns, and relabels `recall` as `recall (decided)` and `F1` as
`F1 (decided recall)`. For example, C12 gave no verdict on 3 of the 39
(`godaddy`, `thefreedictionary` and `wendys`, all KAFE-positive). Its strict
recall is 19/24 = 79.2%, against 90.5% over decided subjects. Cells moved in
§5.1: the unknown pos, unknown neg and strict-recall cells of all 48 Axcess
rows, and the KAFE row's strict-recall cell (n/a → 100.0%). TP, FP, FN,
precision, F1 and the Axcess ms cells are unchanged, and so are TN and `abst.`
in `KAFE-MATRIX.md`. Where this report and `KAFE-HIGHLIGHTS.md` quote KAFE-corpus
recall, they now say which recall it is. Every KAFE-corpus F1 uses decided recall.

**Regenerated for these two corrections:** `KAFE-MATRIX.md`,
`KAFE-MATRIX-REPORT.md`, `derived/kafe_matrix_summary.json`,
`derived/kafe_matrix_summary_permissive.json` and
`derived/kafe_matrix_controls.json` (`assemble`, `report`), from the same 52
JSONL lines. The controls file changed only in control 1's timing block.
`tests/test_capdiag.py` passes (8 tests).

**Update: `craigslist` scored; the KAFE corpus moves from 39 to 40
subjects.** Its fourth attempt appended line 53 to `derived/kafe_matrix.jsonl`
(status `scored`, KAFE label TRUE, 898 candidates, 36 detectors positive, 12
negative, 0 abstaining, 5,351.6 s). The first 52 lines are unchanged (sha256
prefix `35d6de9c7da4a1c1`, checked first). `controls`, `assemble` and `report`
were re-run, and `tests/test_capdiag.py` still passes (8 tests). All four
controls pass. Control 2 now reads 53 attempted, 40 scored, 13 abstained, none
unattempted. The denominator chain is 60 → 7 excluded → 53 replayable → 53
attempted → 13 abstained → **40 scored** (25 positive, 15 negative, 5605
controls probed, up from 4707).

KAFE's reference row was **recomputed** on the 40, not carried over. Its
accuracy comes from the results CSV's labels and verdicts: `craigslist` is
TRUE/TRUE, so 24/1/0/14 → 25/1/0/14 and precision 96.0% → 96.2%. F1 is 98.0%
both times (97.96% → 98.04%). Its cost comes from the per-subject logs in
`artifacts/kafe_output/craigslist/`. The pooled totals rose by exactly that
subject's logged values: Type 1 +4,265 ms, crawls +242,741 ms, full pipeline
+1,492,414 ms (phases 00–11 plus Type 1), and controls +288. `craigslist`'s
full pipeline, 5,182.0 ms per control, is the cheapest of the 40, so KAFE's
pooled cost **falls**: full pipeline 22,747.5 → 19,978.6 ms/button, Type 1
alone 84.4 → 73.4, crawls 3,639.1 → 3,198.3. Proxy share 44.6% → 44.8%.
Without proxy start-up it is 12,594.4 → 11,036.6. Mean per subject 14.96 →
15.21 min (the 60-subject 19.33 is unchanged).

Every Axcess row gained one decided KAFE-positive subject. The 36 rows that
flag `craigslist` gained a TP, and the 12 that do not (D1, D2, D2b, D6, D7,
U-D0, U-D2, U-D2b, U-D3, U-D7, C5, C6) gained an FN. No FP, TN, `unk pos`,
`unk neg` or `abst.` changed, except that `abst.` now counts over 53. Every
Axcess ms/subject and most ms/button cells moved, because `craigslist` adds 898
candidates and its arm times. The sub-millisecond rows and D5 (3.2) round to
the same ms/button as before. The generated `KAFE-MATRIX.md` table is
the full list of cells that moved. What that does to the findings:

- **The best Axcess F1 is now a tie** (§2.1). `D9+S4ours` 85.2% → 85.7% and
  `D5 CDP getEventListeners` 85.1% → 85.7%, both exactly 6/7. The earlier
  text named `D9+S4ours` as the single best row and D5 as the best cheap row.
  Both statements have been replaced. Under strict recall `D9+S4ours` is still
  the single best row (83.6% → 84.2%; D5 82.4%).
- **Cost ratios shrink** (§2.2, §9), because KAFE's pooled cost fell while the
  dearest Axcess rows rose slightly. The dearest row, now 1715.6, is about a twelfth of
  KAFE (was a thirteenth), and `D9+S4ours`, now 1428.7, about a fourteenth (was a
  seventeenth). All 48 rows are still below KAFE's full pipeline and its
  proxy-free figure. The count under Type 1 alone stays 30 of 48 (28 of 46),
  and the count under 300 ms stays 35 of 48.
- **Unchanged conclusions, new figures:** the same five rows beat KAFE's
  precision, the same 19 reach 100% decided recall and the same 6 reach 100%
  strict recall. The C-rules keep the same rule-by-rule deltas (R1 −7 FP / −2
  TP; R5 −1 FP; R7/R8 −3 FP / −1 TP). C15/C16 still cross 300 ms (354.8 →
  337.7). Their transfer drops from `fixtures` narrow slightly: precision
  18.2 → 17.4 points, strict recall 19.9 → 18.9.
- **Nothing in `fixtures`, `gds`, `ma11y` or `edgecases` changed.**
  `derived/matrix.json` and `MATRIX-RESULTS.md` were not touched, and §5.2–§5.5
  are byte-identical.

## 9. What to take away

KAFE is better than anything Axcess has. On KAFE's own benchmark its published
output reaches 96% precision and 100% recall. Our best detectors reach an F1
of 86% (85.7%, computed with recall over decided subjects). Two detectors now
share that: the behavioural `D9+S4ours` (strict recall 96.0%) and the
single-signal `D5 CDP getEventListeners` (strict recall 84.0%). With strict
recall `D9+S4ours` is ahead. Where Axcess is ahead is cost. Per button, KAFE's
full pipeline, including the two crawls its verdict needs, costs about 20.0 s,
and every Axcess detector costs less. `D9+S4ours` costs about a fourteenth of
that, and D5 about a six-thousandth. KAFE's detection step alone, after the
crawls, is 73.4 ms per button, and it does not compare with our figures, which
include our own browser work. Our
cheapest detectors run at a fraction of a millisecond per button. The best of
them, D4, finds every labelled failure (100% strict recall), but it also flags
14 pages whose label says they are fine, where KAFE flags 1. The cheap rules
written to fix those false positives on our own test corpus mostly do not
carry over to real pages. Only R1, R5 and R7/R8 still change anything, and
R7/R8 break the 300 ms ceiling. On the GDS audit, where 13 published tools
found none of the six failures, five fast detectors find three with no false
positives. That is real, and it is half. Every cost figure here is a total
time divided by a count of buttons, not a measured per-button latency. KAFE
was never run on our corpora. So this study shows how our detectors fare
against an outside benchmark. It does not show how an outside tool fares
against ours.
