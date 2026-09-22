# The full detector matrix across four environments

Every detector in the suite, run by `experiments/tabbing/runner/bakeoff.py` — the
real harness, importing the frozen detectors from
`src/audit/analyzer/keyboard/kbdiff/`. Nothing here is a reimplementation.
C10–C16 are not in `bakeoff.py`; they are scored from each corpus's own saved
probe observations by `tools/run_probe_rules.py`, which states the same rules
`probes/score_new.py` and `probes/score_new2.py` state.

Assembled by `tools/assemble_matrix.py` from the `closed` run. **No cell is
blank.** A cost that could not be measured carries the reason in place of a
number.

## What each column means

- **unk pos / unk neg** — abstentions, split. A probe the detector declined to
  decide, never scored as a negative, separated into labelled defects and
  labelled negatives. Reporting a budget limit as "no violation found" is the
  failure mode these columns exist to prevent.
- **strict recall** — true positives over **all** labelled defects, undecided
  ones included, so an abstention on a defect counts against the detector. This
  is `bakeoff.py`'s `recall`; its `recall_conditional`, which divides by decided
  defects only, is kept in `derived/matrix.json` but is not what the published
  tables quote and is not shown here.
- **ms/button** — measured browser work divided by the probes the detector
  **decided**. This is the unit the 300 ms cap is stated in: the cost of
  deciding one button.
- **ms/target** — the same work divided by **every** target in the corpus. It
  amortises per-page setup, so it is a throughput figure, not a promise about
  any single button. This is the column `detector-matrix.results.md` and
  `CHEAP_DETECTOR_REVIEW.md` quote. Both are kept because they answer different
  questions; neither replaces the other.
- **ms covers** — what the figure includes. A bare method call is meaningless
  without the shared work it reads, so that is added in. `measured` means the
  row has its own timing; `priced at its arm` means the row is a re-scoring of
  another arm's single measured trial, so it costs what that arm cost.
- **precision `—`** means the detector flagged nothing at all, so precision is
  undefined rather than missing; **F1 `—` follows from it** and is likewise
  correct, not a gap. Both are reported as `—` deliberately.

## Which benchmark, from which paper

Every table in this document names its source before the numbers. Summary:

| corpus | benchmark source | licence | published competitor result |
|---|---|---|---|
| **gds** | GDS Accessibility Tool Audit, `alphagov/accessibility-tool-audit` | MIT, Crown Copyright 2017 | **all 13 audited tools score 0/6** |
| **ma11y** | Ma11y mutation operators, `mahantaf/web-a11y-tool-analyzer`, applied to the GDS page | per upstream repo | none — corpus is generated |
| **fixtures** | this project's own frozen synthetic corpus | internal | none — internal baseline |
| **edgecases** | this project's own development corpus | internal | none — **no unbiased accuracy claim** |

**The IAF construct** every "violation" label in this document uses comes from
**KAFE**: Chiou, Alotaibi & Halfond, *Detecting and Localizing Keyboard
Accessibility Failures in Web Applications*, **ESEC/FSE 2021**, ACM DOI
[10.1145/3468264.3468581](https://doi.org/10.1145/3468264.3468581). IAF =
functionality a keyboard user cannot operate — both what the Tab sequence never
reaches and what is reached but cannot be actuated. KAFE's own published IAF
result is **92% precision / 100% recall** over 60 proxy-captured subjects, at
**19.22 min** average per subject.

**KAFE's 60-subject corpus is *not* scored in the tables below.** Its labels are
page-level and its captures carry no `data-probe` attributes, so `bakeoff.py`,
which scores element-level probes, cannot consume it. The KAFE replication is a
separate arm; see `RESULTS.md`, which covers **one** detector configuration on
53 replayable subjects and must not be read as a result for the suite.

**And the converse: KAFE's detector is not scored on the four corpora below.**
The comparison runs one way. Every Axcess detector row in `KAFE-MATRIX.md` was
scored on KAFE's own corpus, against KAFE's own published result; KAFE was never
run on `fixtures`, `gds`, `ma11y` or `edgecases`. Their Java / Selenium 3.141.5 /
Firefox 68 stack was not rebuilt here, and that is a scope decision, not pending
work. The same unit mismatch blocks this direction independently: KAFE emits
page-level labels and these four corpora label elements, so even with their
binary running, scoring it here would require inventing a projection between two
different units of truth — and that projection, not the detector, would decide
the result. So read these tables knowing that our detectors have been measured
against an outside benchmark but nothing outside has been measured against these
corpora. `gds` is the only one below that carries a published competitor result
at all, and it comes from the GDS audit's own 13 tools, not from KAFE.

**BAGEL** (Chiou, Alotaibi & Halfond, CHI 2023, DOI
[10.1145/3544548.3580749](https://doi.org/10.1145/3544548.3580749)) is in
`LITERATURE.md` for scope but is **not replicated here**: its artifact folder was
unreachable, and its construct is navigation-order faults rather than IAF.

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

| detector | TP | FP | abst. | precision | ms/button |
|---|---:|---:|---:|---:|---:|
| D0 axcess collectClickables | 1 | 0 | 0 | 100.0% | 1.2 |
| D4 CSS + lexical | 3 | 0 | 0 | 100.0% | 1.2 |
| D6 addEventListener shim | 3 | 0 | 0 | 100.0% | 1.9 |
| D5 CDP getEventListeners | 3 | 0 | 0 | 100.0% | 7.7 |
| D8 hover-diff | 1 | 0 | 0 | 100.0% | 176.8 |
| C1 upstream D4\|D5\|D6, minus Tab | 3 | 0 | 0 | 100.0% | 286.4 |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 3 | 0 | 0 | 100.0% | 286.8 |
| D9 behavioural differential | 2 | 0 | 2 | 100.0% | 3613.3 |
| D9-noS4 coverage-armed differential, no equivalence filter | 2 | 0 | 2 | 100.0% | 3613.3 |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 2 | 0 | 2 | 100.0% | 3613.3 |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 2 | 0 | 2 | 100.0% | 3889.4 |

5 detectors find **3 of 6 under the 300 ms/button cap**, at zero false positives where precision reads 100%. Against a published 0/6 for all 13 tools GDS audited, that is a real gain — and **3/6 is not 6/6**. The cases nobody in the suite finds are still missed.

## The finding that costs the suite its best number

**C8/C9 abstain on GDS on exactly the cases their own inputs find.** D4 finds 3, D5 finds 3, D6 finds 3; C8 returns 0 TP with 3 abstentions; C9 returns 0 TP with 3 abstentions. The union's filter stages (`inert`, `pointer-events:none`, blocked-centre) cannot resolve those elements on a real page, so a safety filter suppresses true positives its own components had already found. The cheap rules the combinations were built to improve on beat them here.

## Full matrix

### gds — GDS Accessibility Tool Audit (MIT, Crown Copyright 2017); 6 IAF cases + 2 controls

**Benchmark provenance.** GDS Accessibility Tool Audit —
[`alphagov/accessibility-tool-audit`](https://github.com/alphagov/accessibility-tool-audit),
UK Government Digital Service, MIT licence, Crown Copyright 2017 (archived 2021).
142 test cases in 19 categories; 16 under "Keyboard Access", of which **6 match
the IAF construct** defined by KAFE (5 unreachable-half, 1 reached-but-not-actionable).

**Published competitor result** (`tests.json`, `results` field per case):
**all 13 audited tools score 0 of 6.** That is the number the rows below are
measured against. The 2 controls are correctly-built elements from the same page.

**Construct definition borrowed from:** Chiou, Alotaibi & Halfond, *Detecting and
Localizing Keyboard Accessibility Failures in Web Applications*, ESEC/FSE 2021
(ACM DOI [10.1145/3468264.3468581](https://doi.org/10.1145/3468264.3468581)) —
**IAF** = functionality a keyboard user cannot operate, covering both what Tab
never reaches *and* what is reached but cannot be actuated.

Published reference: all 13 audited tools score 0/6. 8 targets; artifacts: bakeoff-gds-closed.json, bakeoff-gds-closed-full.json.

- Note: D8 hover-diff: bakeoff-gds-closed.json and bakeoff-gds-closed-full.json disagree (1/0/5 vs 0/0/6)

| detector | TP | FP | FN | unk pos | unk neg | precision | strict recall | F1 | ms/button | ms/target | ms covers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 1 | 0 | 5 | 0 | 0 | 100.0% | 16.7% | 28.6% | 1.2 | 1.2 | survey + method |
| D1 axe-core (keyboard rules) | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 1399.9 | 1399.9 | survey + method |
| D1x axe-core (any rule, unsound) | 0 | 1 | 6 | 0 | 0 | 0.0% | 0.0% | — | 1399.9 | 1399.9 | survey + method |
| D2 inline onclick attribute | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 1.2 | 1.2 | survey + method |
| D2b onclick property | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 1.2 | 1.2 | survey + method |
| D3 tabindex / ARIA | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 1.2 | 1.2 | survey + method |
| D4 CSS + lexical | 3 | 0 | 3 | 0 | 0 | 100.0% | 50.0% | 66.7% | 1.2 | 1.2 | survey + method |
| D5 CDP getEventListeners | 3 | 0 | 3 | 0 | 0 | 100.0% | 50.0% | 66.7% | 7.7 | 7.7 | survey + method |
| D6 addEventListener shim | 3 | 0 | 3 | 0 | 0 | 100.0% | 50.0% | 66.7% | 1.9 | 1.9 | survey + method |
| D7 React fiber props | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 1.2 | 1.2 | survey + method |
| D8 hover-diff | 1 | 0 | 5 | 0 | 0 | 100.0% | 16.7% | 28.6% | 176.8 | 176.8 | survey + method |
| U-D0 upstream crawler candidates | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 281.7 | 281.7 | shared + method |
| U-D1 upstream tagged axe attribution | 0 | 1 | 6 | 0 | 0 | 0.0% | 0.0% | — | 1697.7 | 1697.7 | shared + method |
| U-D2 upstream inline attributes | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 281.7 | 281.7 | shared + method |
| U-D2b upstream mouse handler properties | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 281.6 | 281.6 | shared + method |
| U-D3 upstream missing tabindex | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 281.7 | 281.7 | shared + method |
| U-D4 upstream CSS and class tokens | 0 | 0 | 4 | 2 | 0 | — | 0.0% | — | 375.6 | 281.7 | shared + method |
| U-D5 upstream direct CDP listeners | 0 | 0 | 4 | 2 | 0 | — | 0.0% | — | 379.0 | 284.2 | shared + method |
| U-D6 upstream registration shim | 0 | 0 | 4 | 2 | 0 | — | 0.0% | — | 375.3 | 281.5 | shared + method |
| U-D7 upstream React mouse props | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 281.6 | 281.6 | shared + method |
| U-D8 upstream pixel hover difference | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 281.0 | 281.0 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 3 | 0 | 3 | 0 | 0 | 100.0% | 50.0% | 66.7% | 286.4 | 286.4 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 3 | 0 | 3 | 0 | 0 | 100.0% | 50.0% | 66.7% | 286.8 | 286.8 | shared + components |
| C3 union, reject inert and pointer-events:none | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 460.3 | 287.7 | shared + components |
| C4 union, additionally reject blocked center | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 460.3 | 287.7 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 288.7 | 288.7 | shared + components |
| C6 visible label for a toggle absent from Tab | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 281.9 | 281.9 | shared + components |
| C7 ancestor mouse listener, minus Tab | 0 | 0 | 6 | 0 | 0 | — | 0.0% | — | 281.9 | 281.9 | shared + components |
| C8 union + focusable + label + ancestor leads | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 463.7 | 289.8 | shared + components |
| C9 combined leads, additionally reject blocked center | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 463.7 | 289.8 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 477.2 | 298.2 | C9 + R1 |
| C11 = C10 minus roving-tabindex items (R2) | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 482.8 | 301.7 | C9 + R2 |
| C12 = C11 minus declared shortcuts (R3) | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 482.8 | 301.7 | C9 + R3, same pass |
| C13 = C12 minus leads with no action path (R5) | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 748.5 | 467.8 | C9 + R5 |
| C14 = C13 minus name-twinned leads (R6) | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 748.5 | 467.8 | C9 + R6, free |
| C15 = C14 minus leads with no click effect (R7, R8) | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 2668.4 | 1667.7 | C9 + behavioural pass |
| C16 = C15 plus divergent-key-effect promotions (R9) | 0 | 0 | 3 | 3 | 0 | — | 0.0% | — | 2668.4 | 1667.7 | C9 + R9, same pass |
| D9 behavioural differential | 2 | 0 | 2 | 2 | 0 | 100.0% | 33.3% | 50.0% | 3613.3 | 2710.0 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 2 | 0 | 2 | 2 | 0 | 100.0% | 33.3% | 50.0% | 3613.3 | 2710.0 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 2 | 0 | 2 | 2 | 0 | 100.0% | 33.3% | 50.0% | 3889.4 | 2917.0 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 2 | 0 | 2 | 2 | 0 | 100.0% | 33.3% | 50.0% | 3613.3 | 2710.0 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 0 | 0 | 0 | 6 | 2 | — | 0.0% | — | n/a: decided 0 of 8 | 1437.6 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 0 | 0 | 0 | 6 | 2 | — | 0.0% | — | n/a: decided 0 of 8 | 1437.6 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 0 | 0 | 0 | 6 | 2 | — | 0.0% | — | n/a: decided 0 of 8 | 762.7 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 0 | 0 | 0 | 6 | 2 | — | 0.0% | — | n/a: decided 0 of 8 | 762.7 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 0 | 0 | 0 | 6 | 2 | — | 0.0% | — | n/a: decided 0 of 8 | 762.7 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 0 | 0 | 0 | 6 | 2 | — | 0.0% | — | n/a: decided 0 of 8 | 762.7 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 0 | 0 | 0 | 6 | 2 | — | 0.0% | — | n/a: decided 0 of 8 | 762.7 | priced at its arm |

> **Why C10–C16 are all zero on this corpus.** Each of C10–C16 is defined as
> *C9 minus a dismissal rule*. C9 itself scores **0 TP with 3 abstentions**
> here, because its filter stages (`inert`, `pointer-events:none`,
> blocked-centre) cannot resolve the three elements D4/D5/D6 each find. Every
> rule downstream therefore subtracts from an empty lead set and inherits the
> zero. These rows measure **C9's abstention, not the rules themselves** — the
> rules are untested on this corpus, which is different from having been tested
> and found useless. The same cascade applies on `ma11y`.

### fixtures — blind-authored synthetic; 95 probes, 39 defects

**Benchmark provenance.** No external literature. This is the project's own
blind-authored, frozen synthetic corpus: 95 element-level probes, 39 labelled
defects, labels `violation` / `ok` / `decoy` / `excluded`.

**Reference for these rows:** `experiments/tabbing/results/detector-matrix.results.md`
(D-family and C1–C9) and `experiments/tabbing/CHEAP_DETECTOR_REVIEW.md` (C1–C16).
Both are this project's own prior measurements, and both are used here as the
**control**: any change to the measurement path must leave these cells unmoved.

**Not an accuracy claim.** `CHEAP_DETECTOR_REVIEW.md` §"Why these numbers should
not be quoted as accuracy" states it directly — the rules were written after
reading errors on this corpus, with labels visible, so these are development
results on 95 targets, not accuracy on unseen pages.

Published reference: none; the suite's own baseline. 95 targets; artifacts: bakeoff-fixtures-closed.json, bakeoff-fixtures-closed-full.json.

| detector | TP | FP | FN | unk pos | unk neg | precision | strict recall | F1 | ms/button | ms/target | ms covers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 1 | 1 | 35 | 3 | 3 | 50.0% | 2.6% | 4.9% | 1.3 | 1.2 | survey + method |
| D1 axe-core (keyboard rules) | 0 | 1 | 36 | 3 | 3 | 0.0% | 0.0% | — | 66.5 | 62.3 | survey + method |
| D1x axe-core (any rule, unsound) | 18 | 11 | 18 | 3 | 3 | 62.1% | 46.2% | 52.9% | 66.5 | 62.3 | survey + method |
| D2 inline onclick attribute | 1 | 0 | 35 | 3 | 3 | 100.0% | 2.6% | 5.0% | 1.3 | 1.2 | survey + method |
| D2b onclick property | 4 | 0 | 32 | 3 | 3 | 100.0% | 10.3% | 18.6% | 1.3 | 1.2 | survey + method |
| D3 tabindex / ARIA | 2 | 2 | 34 | 3 | 3 | 50.0% | 5.1% | 9.3% | 1.3 | 1.2 | survey + method |
| D4 CSS + lexical | 27 | 21 | 9 | 3 | 3 | 56.2% | 69.2% | 62.1% | 1.3 | 1.2 | survey + method |
| D5 CDP getEventListeners | 25 | 18 | 11 | 3 | 3 | 58.1% | 64.1% | 61.0% | 5.8 | 5.5 | survey + method |
| D6 addEventListener shim | 21 | 18 | 15 | 3 | 3 | 53.8% | 53.8% | 53.8% | 2.0 | 1.8 | survey + method |
| D7 React fiber props | 2 | 0 | 34 | 3 | 3 | 100.0% | 5.1% | 9.8% | 1.3 | 1.2 | survey + method |
| D8 hover-diff | 18 | 6 | 18 | 3 | 3 | 75.0% | 46.2% | 57.1% | 229.6 | 215.1 | survey + method |
| U-D0 upstream crawler candidates | 1 | 3 | 38 | 0 | 0 | 25.0% | 2.6% | 4.7% | 50.7 | 50.7 | shared + method |
| U-D1 upstream tagged axe attribution | 0 | 0 | 39 | 0 | 0 | — | 0.0% | — | 100.5 | 100.5 | shared + method |
| U-D2 upstream inline attributes | 1 | 0 | 38 | 0 | 0 | 100.0% | 2.6% | 5.0% | 50.8 | 50.8 | shared + method |
| U-D2b upstream mouse handler properties | 4 | 0 | 35 | 0 | 0 | 100.0% | 10.3% | 18.6% | 50.7 | 50.7 | shared + method |
| U-D3 upstream missing tabindex | 1 | 0 | 38 | 0 | 0 | 100.0% | 2.6% | 5.0% | 50.6 | 50.6 | shared + method |
| U-D4 upstream CSS and class tokens | 30 | 17 | 9 | 0 | 0 | 63.8% | 76.9% | 69.8% | 50.8 | 50.8 | shared + method |
| U-D5 upstream direct CDP listeners | 29 | 13 | 10 | 0 | 0 | 69.0% | 74.4% | 71.6% | 56.3 | 56.3 | shared + method |
| U-D6 upstream registration shim | 25 | 13 | 14 | 0 | 0 | 65.8% | 64.1% | 64.9% | 50.6 | 50.6 | shared + method |
| U-D7 upstream React mouse props | 2 | 0 | 37 | 0 | 0 | 100.0% | 5.1% | 9.8% | 50.7 | 50.7 | shared + method |
| U-D8 upstream pixel hover difference | 19 | 9 | 20 | 0 | 0 | 67.9% | 48.7% | 56.7% | 304.6 | 304.6 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 33 | 18 | 6 | 0 | 0 | 64.7% | 84.6% | 73.3% | 57.9 | 57.9 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 33 | 20 | 6 | 0 | 0 | 62.3% | 84.6% | 71.7% | 312.6 | 312.6 | shared + components |
| C3 union, reject inert and pointer-events:none | 32 | 13 | 6 | 1 | 1 | 71.1% | 82.0% | 76.2% | 60.3 | 59.1 | shared + components |
| C4 union, additionally reject blocked center | 32 | 11 | 6 | 1 | 1 | 74.4% | 82.0% | 78.0% | 60.3 | 59.1 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 3 | 0 | 36 | 0 | 0 | 100.0% | 7.7% | 14.3% | 59.8 | 59.8 | shared + components |
| C6 visible label for a toggle absent from Tab | 1 | 0 | 38 | 0 | 0 | 100.0% | 2.6% | 5.0% | 51.1 | 51.1 | shared + components |
| C7 ancestor mouse listener, minus Tab | 7 | 3 | 32 | 0 | 0 | 70.0% | 17.9% | 28.6% | 51.1 | 51.1 | shared + components |
| C8 union + focusable + label + ancestor leads | 37 | 13 | 1 | 1 | 1 | 74.0% | 94.9% | 83.2% | 61.9 | 60.6 | shared + components |
| C9 combined leads, additionally reject blocked center | 37 | 11 | 1 | 1 | 1 | 77.1% | 94.9% | 85.1% | 61.9 | 60.6 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 37 | 8 | 1 | 1 | 1 | 82.2% | 94.9% | 88.1% | 65.2 | 63.8 | C9 + R1 |
| C11 = C10 minus roving-tabindex items (R2) | 37 | 7 | 1 | 1 | 1 | 84.1% | 94.9% | 89.2% | 68.9 | 67.4 | C9 + R2 |
| C12 = C11 minus declared shortcuts (R3) | 37 | 6 | 1 | 1 | 1 | 86.0% | 94.9% | 90.2% | 68.9 | 67.4 | C9 + R3, same pass |
| C13 = C12 minus leads with no action path (R5) | 37 | 4 | 1 | 1 | 1 | 90.2% | 94.9% | 92.5% | 248.9 | 243.6 | C9 + R5 |
| C14 = C13 minus name-twinned leads (R6) | 37 | 3 | 1 | 1 | 1 | 92.5% | 94.9% | 93.7% | 248.9 | 243.6 | C9 + R6, free |
| C15 = C14 minus leads with no click effect (R7, R8) | 37 | 0 | 1 | 1 | 1 | 100.0% | 94.9% | 97.4% | 642.9 | 629.3 | C9 + behavioural pass |
| C16 = C15 plus divergent-key-effect promotions (R9) [observed 42 of 95: c12.json] | 38 | 0 | 0 | 1 | 1 | 100.0% | 97.4% | 98.7% | 642.9 | 629.3 | C9 + R9, same pass |
| C16 = C15 plus divergent-key-effect promotions (R9) [observed 95 of 95: all probes] | 38 | 11 | 0 | 1 | 1 | 77.6% | 97.4% | 86.4% | 1180.0 | 1155.1 | C9 + R9, same pass |
| D9 behavioural differential | 34 | 5 | 2 | 3 | 17 | 87.2% | 87.2% | 87.2% | 2015.6 | 1591.3 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 34 | 5 | 2 | 3 | 17 | 87.2% | 87.2% | 87.2% | 2015.6 | 1591.3 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 33 | 4 | 3 | 3 | 17 | 89.2% | 84.6% | 86.8% | 2100.2 | 1658.1 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 34 | 9 | 2 | 3 | 17 | 79.1% | 87.2% | 82.9% | 2015.6 | 1591.3 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 36 | 10 | 3 | 0 | 4 | 78.3% | 92.3% | 84.7% | 1293.1 | 1238.6 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 35 | 5 | 4 | 0 | 4 | 87.5% | 89.7% | 88.6% | 1293.1 | 1238.6 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 32 | 24 | 4 | 3 | 7 | 57.1% | 82.0% | 67.4% | 1017.6 | 910.5 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 32 | 24 | 4 | 3 | 7 | 57.1% | 82.0% | 67.4% | 1017.6 | 910.5 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 33 | 11 | 6 | 0 | 4 | 75.0% | 84.6% | 79.5% | 950.5 | 910.5 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 36 | 31 | 0 | 3 | 7 | 53.7% | 92.3% | 67.9% | 1017.6 | 910.5 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 37 | 12 | 2 | 0 | 4 | 75.5% | 94.9% | 84.1% | 950.5 | 910.5 | priced at its arm |

### ma11y — Ma11y-generated mutants; 1 verified fault, 6 controls

**Benchmark provenance.** Mutants generated with the Ma11y mutation operators
([`mahantaf/web-a11y-tool-analyzer`](https://github.com/mahantaf/web-a11y-tool-analyzer)),
applied to the GDS page above. Ground truth is known by construction **and**
verified behaviourally before any detector saw it (`tools/verify_ma11y_corpus.py`).

**No published competitor result exists for this corpus** — it is generated, so
no prior tool has been scored on it. Treat these rows as a sanity check ("does
the detector fire on a known-good fault"), **not** as a benchmark: 1 verified
violation and 6 controls cannot support a precision/recall comparison.

Of 4 operators, only **F55** produced a verified fault. F59 is not implemented in
Ma11y (404); F54 requires an inline `onclick`, which the GDS page has none of;
F42's generated span never fires on a trusted click and was excluded rather than
labelled.

Published reference: no published reference; ground truth by construction. 7 targets; artifacts: bakeoff-ma11y-closed.json, bakeoff-ma11y-closed-full.json.

| detector | TP | FP | FN | unk pos | unk neg | precision | strict recall | F1 | ms/button | ms/target | ms covers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 1 | 0 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 1.9 | 1.9 | survey + method |
| D1 axe-core (keyboard rules) | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 569.2 | 569.2 | survey + method |
| D1x axe-core (any rule, unsound) | 0 | 3 | 1 | 0 | 0 | 0.0% | 0.0% | — | 569.2 | 569.2 | survey + method |
| D2 inline onclick attribute | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 1.9 | 1.9 | survey + method |
| D2b onclick property | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 1.9 | 1.9 | survey + method |
| D3 tabindex / ARIA | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 1.9 | 1.9 | survey + method |
| D4 CSS + lexical | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 1.9 | 1.9 | survey + method |
| D5 CDP getEventListeners | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 6.6 | 6.6 | survey + method |
| D6 addEventListener shim | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 2.8 | 2.8 | survey + method |
| D7 React fiber props | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 1.9 | 1.9 | survey + method |
| D8 hover-diff | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 219.7 | 219.7 | survey + method |
| U-D0 upstream crawler candidates | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 985.9 | 985.9 | shared + method |
| U-D1 upstream tagged axe attribution | 0 | 3 | 1 | 0 | 0 | 0.0% | 0.0% | — | 1509.6 | 1509.6 | shared + method |
| U-D2 upstream inline attributes | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 985.7 | 985.7 | shared + method |
| U-D2b upstream mouse handler properties | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 985.5 | 985.5 | shared + method |
| U-D3 upstream missing tabindex | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 985.6 | 985.6 | shared + method |
| U-D4 upstream CSS and class tokens | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 1151.9 | 987.4 | shared + method |
| U-D5 upstream direct CDP listeners | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 989.3 | 989.3 | shared + method |
| U-D6 upstream registration shim | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 985.1 | 985.1 | shared + method |
| U-D7 upstream React mouse props | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 987.5 | 987.5 | shared + method |
| U-D8 upstream pixel hover difference | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 984.4 | 984.4 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 1 | 0 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 999.4 | 999.4 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 1 | 0 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 1002.6 | 1002.6 | shared + components |
| C3 union, reject inert and pointer-events:none | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 1173.6 | 1006.0 | shared + components |
| C4 union, additionally reject blocked center | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 1173.6 | 1006.0 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 1010.4 | 1010.4 | shared + components |
| C6 visible label for a toggle absent from Tab | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 987.7 | 987.7 | shared + components |
| C7 ancestor mouse listener, minus Tab | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 987.7 | 987.7 | shared + components |
| C8 union + focusable + label + ancestor leads | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 1186.0 | 1016.5 | shared + components |
| C9 combined leads, additionally reject blocked center | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 1186.0 | 1016.5 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 1200.7 | 1029.1 | C9 + R1 |
| C11 = C10 minus roving-tabindex items (R2) | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 1226.6 | 1051.3 | C9 + R2 |
| C12 = C11 minus declared shortcuts (R3) | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 1226.6 | 1051.3 | C9 + R3, same pass |
| C13 = C12 minus leads with no action path (R5) | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 1476.4 | 1265.4 | C9 + R5 |
| C14 = C13 minus name-twinned leads (R6) | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 1476.4 | 1265.4 | C9 + R6, free |
| C15 = C14 minus leads with no click effect (R7, R8) | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 3238.4 | 2775.7 | C9 + behavioural pass |
| C16 = C15 plus divergent-key-effect promotions (R9) | 0 | 0 | 0 | 1 | 0 | — | 0.0% | — | 3238.4 | 2775.7 | C9 + R9, same pass |
| D9 behavioural differential | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 4454.5 | 4454.5 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 0 | 0 | 1 | 0 | 0 | — | 0.0% | — | 4454.5 | 4454.5 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 1 | 0 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4642.3 | 4642.3 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 1 | 0 | 0 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4454.5 | 4454.5 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 0 | 0 | 0 | 1 | 3 | — | 0.0% | — | 4600.5 | 1971.6 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 0 | 0 | 0 | 1 | 3 | — | 0.0% | — | 4600.5 | 1971.6 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 0 | 0 | 0 | 1 | 3 | — | 0.0% | — | 2219.8 | 951.3 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 0 | 0 | 0 | 1 | 3 | — | 0.0% | — | 2219.8 | 951.3 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 0 | 0 | 0 | 1 | 3 | — | 0.0% | — | 2219.8 | 951.3 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 0 | 0 | 0 | 1 | 3 | — | 0.0% | — | 2219.8 | 951.3 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 0 | 0 | 0 | 1 | 3 | — | 0.0% | — | 2219.8 | 951.3 | priced at its arm |

> **Why C10–C16 are all zero on this corpus.** Each of C10–C16 is defined as
> *C9 minus a dismissal rule*. C9 itself scores **0 TP with 3 abstentions**
> here, because its filter stages (`inert`, `pointer-events:none`,
> blocked-centre) cannot resolve the three elements D4/D5/D6 each find. Every
> rule downstream therefore subtracts from an empty lead set and inherits the
> zero. These rows measure **C9's abstention, not the rules themselves** — the
> rules are untested on this corpus, which is different from having been tested
> and found useless. The same cascade applies on `ma11y`.

### edgecases — shared-author development corpus; NO unbiased accuracy claim

**Benchmark provenance.** No external literature. Shared-author development
corpus internal to this project.

**Carries no unbiased accuracy claim** — it was authored alongside the detectors
it scores. Included for completeness and for the CDP-overflow fix it exercises,
not as evidence of accuracy.

Published reference: none; shared-author, so no unbiased accuracy claim. 74 targets; artifacts: bakeoff-edgecases-closed.json, bakeoff-edgecases-closed-full.json.

| detector | TP | FP | FN | unk pos | unk neg | precision | strict recall | F1 | ms/button | ms/target | ms covers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D0 axcess collectClickables | 9 | 0 | 29 | 2 | 0 | 100.0% | 22.5% | 36.7% | 1.7 | 1.7 | survey + method |
| D1 axe-core (keyboard rules) | 1 | 1 | 37 | 2 | 0 | 50.0% | 2.5% | 4.8% | 95.9 | 93.3 | survey + method |
| D1x axe-core (any rule, unsound) | 23 | 13 | 15 | 2 | 0 | 63.9% | 57.5% | 60.5% | 95.9 | 93.3 | survey + method |
| D2 inline onclick attribute | 2 | 0 | 36 | 2 | 0 | 100.0% | 5.0% | 9.5% | 1.7 | 1.7 | survey + method |
| D2b onclick property | 3 | 0 | 35 | 2 | 0 | 100.0% | 7.5% | 14.0% | 1.7 | 1.7 | survey + method |
| D3 tabindex / ARIA | 3 | 0 | 35 | 2 | 0 | 100.0% | 7.5% | 14.0% | 1.7 | 1.7 | survey + method |
| D4 CSS + lexical | 28 | 15 | 10 | 2 | 0 | 65.1% | 70.0% | 67.5% | 1.7 | 1.7 | survey + method |
| D5 CDP getEventListeners | 31 | 13 | 7 | 2 | 0 | 70.5% | 77.5% | 73.8% | 7.5 | 7.3 | survey + method |
| D6 addEventListener shim | 27 | 13 | 11 | 2 | 0 | 67.5% | 67.5% | 67.5% | 2.7 | 2.6 | survey + method |
| D7 React fiber props | 0 | 0 | 38 | 2 | 0 | — | 0.0% | — | 1.7 | 1.7 | survey + method |
| D8 hover-diff | 2 | 1 | 36 | 2 | 0 | 66.7% | 5.0% | 9.3% | 194.7 | 189.5 | survey + method |
| U-D0 upstream crawler candidates | 11 | 2 | 29 | 0 | 0 | 84.6% | 27.5% | 41.5% | 55.4 | 55.4 | shared + method |
| U-D1 upstream tagged axe attribution | 1 | 0 | 39 | 0 | 0 | 100.0% | 2.5% | 4.9% | 109.3 | 109.3 | shared + method |
| U-D2 upstream inline attributes | 2 | 0 | 38 | 0 | 0 | 100.0% | 5.0% | 9.5% | 55.4 | 55.4 | shared + method |
| U-D2b upstream mouse handler properties | 3 | 0 | 37 | 0 | 0 | 100.0% | 7.5% | 14.0% | 55.2 | 55.2 | shared + method |
| U-D3 upstream missing tabindex | 4 | 0 | 36 | 0 | 0 | 100.0% | 10.0% | 18.2% | 55.3 | 55.3 | shared + method |
| U-D4 upstream CSS and class tokens | 34 | 12 | 6 | 0 | 0 | 73.9% | 85.0% | 79.1% | 55.2 | 55.2 | shared + method |
| U-D5 upstream direct CDP listeners | 32 | 9 | 8 | 0 | 0 | 78.0% | 80.0% | 79.0% | 61.0 | 61.0 | shared + method |
| U-D6 upstream registration shim | 29 | 9 | 11 | 0 | 0 | 76.3% | 72.5% | 74.4% | 55.2 | 55.2 | shared + method |
| U-D7 upstream React mouse props | 0 | 0 | 40 | 0 | 0 | — | 0.0% | — | 55.2 | 55.2 | shared + method |
| U-D8 upstream pixel hover difference | 7 | 3 | 33 | 0 | 0 | 70.0% | 17.5% | 28.0% | 308.8 | 308.8 | shared + method |
| C1 upstream D4\|D5\|D6, minus Tab | 36 | 13 | 4 | 0 | 0 | 73.5% | 90.0% | 80.9% | 62.6 | 62.6 | shared + components |
| C2 upstream D4\|D5\|D6\|D8, minus Tab | 37 | 14 | 3 | 0 | 0 | 72.5% | 92.5% | 81.3% | 317.1 | 317.1 | shared + components |
| C3 union, reject inert and pointer-events:none | 35 | 11 | 4 | 1 | 0 | 76.1% | 87.5% | 81.4% | 64.8 | 64.0 | shared + components |
| C4 union, additionally reject blocked center | 32 | 10 | 7 | 1 | 0 | 76.2% | 80.0% | 78.0% | 64.8 | 64.0 | shared + components |
| C5 focusable custom mouse control, no observed key handler | 2 | 1 | 38 | 0 | 0 | 66.7% | 5.0% | 9.3% | 64.7 | 64.7 | shared + components |
| C6 visible label for a toggle absent from Tab | 0 | 0 | 40 | 0 | 0 | — | 0.0% | — | 55.7 | 55.7 | shared + components |
| C7 ancestor mouse listener, minus Tab | 9 | 0 | 31 | 0 | 0 | 100.0% | 22.5% | 36.7% | 55.7 | 55.7 | shared + components |
| C8 union + focusable + label + ancestor leads | 37 | 12 | 2 | 1 | 0 | 75.5% | 92.5% | 83.2% | 66.4 | 65.5 | shared + components |
| C9 combined leads, additionally reject blocked center | 34 | 11 | 5 | 1 | 0 | 75.6% | 85.0% | 80.0% | 66.4 | 65.5 | shared + components |
| C10 = C9 minus redundant click surfaces (R1) | 34 | 9 | 5 | 1 | 0 | 79.1% | 85.0% | 81.9% | 69.8 | 68.8 | C9 + R1 |
| C11 = C10 minus roving-tabindex items (R2) | 34 | 9 | 5 | 1 | 0 | 79.1% | 85.0% | 81.9% | 73.2 | 72.2 | C9 + R2 |
| C12 = C11 minus declared shortcuts (R3) | 34 | 9 | 5 | 1 | 0 | 79.1% | 85.0% | 81.9% | 73.2 | 72.2 | C9 + R3, same pass |
| C13 = C12 minus leads with no action path (R5) | 33 | 7 | 6 | 1 | 0 | 82.5% | 82.5% | 82.5% | 253.2 | 249.7 | C9 + R5 |
| C14 = C13 minus name-twinned leads (R6) | 30 | 7 | 9 | 1 | 0 | 81.1% | 75.0% | 77.9% | 253.2 | 249.7 | C9 + R6, free |
| C15 = C14 minus leads with no click effect (R7, R8) | 29 | 5 | 10 | 1 | 0 | 85.3% | 72.5% | 78.4% | 1153.2 | 1137.6 | C9 + behavioural pass |
| C16 = C15 plus divergent-key-effect promotions (R9) | 30 | 5 | 9 | 1 | 0 | 85.7% | 75.0% | 80.0% | 1153.2 | 1137.6 | C9 + R9, same pass |
| D9 behavioural differential | 35 | 4 | 2 | 3 | 8 | 89.7% | 87.5% | 88.6% | 1665.9 | 1418.3 | measured |
| D9+S4ours coverage-armed differential, our payload Stage 4 | 35 | 4 | 2 | 3 | 8 | 89.7% | 87.5% | 88.6% | 1665.9 | 1418.3 | priced at its arm |
| D9+S4u differential with upstream Stage 4 (coverage-exact) | 35 | 5 | 2 | 3 | 8 | 87.5% | 87.5% | 87.5% | 1745.4 | 1485.9 | measured |
| D9-noS4 coverage-armed differential, no equivalence filter | 35 | 5 | 2 | 3 | 8 | 87.5% | 87.5% | 87.5% | 1665.9 | 1418.3 | priced at its arm |
| D9u upstream-style differential (8 channels, keys in sequence) | 32 | 5 | 7 | 1 | 3 | 86.5% | 80.0% | 83.1% | 1243.5 | 1176.3 | measured |
| D9u+S4u upstream differential with upstream Stage 4 (1:1) | 32 | 5 | 7 | 1 | 3 | 86.5% | 80.0% | 83.1% | 1243.5 | 1176.3 | priced at its arm |
| D10a coverage differential (Enter only, no baseline subtraction) | 34 | 15 | 3 | 3 | 3 | 69.4% | 85.0% | 76.4% | 577.0 | 530.2 | measured |
| D10a+base coverage differential (Enter only, baseline subtracted) | 34 | 15 | 3 | 3 | 3 | 69.4% | 85.0% | 76.4% | 577.0 | 530.2 | priced at its arm |
| D10a-u upstream coverage presence (sequential keys, baselined) | 33 | 5 | 6 | 1 | 3 | 86.8% | 82.5% | 84.6% | 560.5 | 530.2 | priced at its arm |
| D10b coverage set-difference (Enter only, no baseline subtraction) | 37 | 24 | 0 | 3 | 3 | 60.7% | 92.5% | 73.3% | 577.0 | 530.2 | priced at its arm |
| D10b-u upstream coverage set-difference (sequential keys, baselined) | 35 | 12 | 4 | 1 | 3 | 74.5% | 87.5% | 80.5% | 560.5 | 530.2 | priced at its arm |

## Cost against the 300 ms/button cap

| corpus | detectors timed | at or under 300 ms/button | not timed (reason given in the row) |
|---|---:|---:|---:|
| gds | 41 | 20 | 7 |
| fixtures | 49 | 33 | 0 |
| ma11y | 48 | 9 | 0 |
| edgecases | 48 | 33 | 0 |

## Corrections carried into this document

1. **C16's published 100% precision is a property of the lead set that was
   observed, not of the rule.** The saved `effect2.json` observed 42 of 95
   probes — the C12 lead set. R9 promotes from the whole universe but can only
   promote what it looked at. Both scopes are scored here and, where they
   disagree, both rows appear, each labelled with the set observed.

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
   completeness and carry **no unbiased accuracy claim**.

6. **The edgecases CDP failure is fixed, and it was not the page the log
   suggested.** `DOM.getDocument` with `depth: -1, pierce: true` returned a
   response Chromium's CBOR encoder could not serialise. The cause is
   `pages/scale.html`, nested 154 elements deep with only 284 elements in it:
   `depth: 148` encodes in 73 KB and `depth: 150` fails, so it is a nesting
   limit and not a size limit. `runner/upstream_candidates.py` now keeps the
   unbounded call as its primary path and falls back to fetching the tree in
   bounded slices only when that call raises, so every corpus that already
   worked is unaffected.

7. **A stale-artifact merge, not a measurement failure, blanked most of the
   earlier `ms` column.** The previous assembler globbed every `bakeoff-*.json`
   in a results directory and let later names overwrite earlier ones; `-` sorts
   before `.`, so `bakeoff-fixtures.json` — an old run carrying no
   `page_timings_ms` at all — sorted last and overwrote every row it contained.
   That is where the earlier table's `D10 coverage differential` row, its
   duplicate `D9-noS4` row and its 22/19/15 `D6` came from. This assembler reads
   exactly the two files of one named run.

## Reproducing

```
uv run --offline --no-sync python -m tools.build_gds_corpus
uv run --offline --no-sync python -m tools.build_ma11y_corpus
uv run --offline --no-sync python -m tools.verify_ma11y_corpus
bash tools/run_matrix_closed.sh
bash tools/run_probes_all.sh
uv run --offline --no-sync python -m tools.assemble_matrix --label closed
```
