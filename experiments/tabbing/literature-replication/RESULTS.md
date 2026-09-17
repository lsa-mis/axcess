# Results: the frozen Axcess detectors on the 53 replayable KAFE subjects

> **SCOPE — read before quoting any number here.** This report covers **one
> detector configuration**: a default `TrialConfig` on `DifferentialRunner`,
> i.e. one arm of D9. The suite has **38 detectors and combination rules**
> (D0–D8, D1/D1x, six D9 variants, five D10 variants, C1–C16). None of the other
> 37 ran for this report, and it carries **no per-detector millisecond column**.
> Treating its single row as "the Axcess detectors" was a manager error.
>
> The full matrix is planned in `PLAN-FULL-MATRIX.md` and will land in
> `RESULTS-MATRIX.md`. Until then, the precision and recall below describe one
> configuration and must not be generalised to the suite.

Written by Claude Code on 2026-09-16 from the completed run. The experiment was
**not** re-run; every figure below is recomputed from
`derived/kafe_scored.jsonl` by `tools/analyze_scored.py`, which I executed:

```
uv run --offline --no-sync python -m tools.analyze_scored
```

Nothing is committed. Nothing under `src/audit/` is edited.

**This run does not clear `FEASIBILITY.md` §6.9.** Two of its five prerequisites
(independent Codex disposition on §6, R6 brotli clearance) were open when the run
started, per `PREREGISTRATION-SCORED.md` §2, and remain outside this report's
knowledge. This is a pilot with real numbers and an unmet gate.

---

## 0. The result, stated plainly

**On the 45 subjects both systems scored, the frozen Axcess detectors are worse
than KAFE on both axes: lower precision (0.657 vs 0.963) and lower recall
(0.885 vs 1.000).** Axcess missed 3 positives KAFE caught and raised 12 false
alarms against KAFE's 1.

The registered target hypothesis H1 — *equal recall, better precision* — is
**falsified on both limbs**. So are all three of its sub-predictions, including
P-B, the one I registered in advance as the one I expected to fail.

Two things make the comparison even less favourable than the headline, and both
are established below rather than asserted: the run also abstained on 8 further
subjects (5 of them positive), and by its own pre-registered criterion (P-C, one
of those abstentions being `dell`) it is **inconclusive as a test of H1**
regardless of the cell counts. Inconclusive about H1 is not the same as
favourable: the measured precision and recall deficits stand as observations on
the subjects that were scored.

---

## 1. Headline table — common set, 45 subjects

Both rows are computed on exactly the same 45 subjects: the ones Axcess scored.
KAFE's row is its own historical result restricted to that set
(`derived/kafe_denominator.json` → `subjects[].kafe_yhat`), **not** the published
36/39, which is a different retained subset.

| | TP | FP | FN | TN | n | Precision | Recall | F1 |
| --- | --: | --: | --: | --: | --: | --- | --- | --- |
| **Axcess frozen detectors** | 23 | 12 | 3 | 7 | 45 | **23/35 = 0.657** | **23/26 = 0.885** | 46/61 = 0.754 |
| **KAFE, same 45 subjects** | 26 | 1 | 0 | 18 | 45 | **26/27 = 0.963** | **26/26 = 1.000** | 52/53 = 0.981 |

Source: `derived/scored_summary.json` → `axcess_frozen_detectors`,
`kafe_same_common_set`. Reproduce with the command at the top of this file.

Delta: precision −0.306, recall −0.115. KAFE's single false positive on this set
is `bowiestate`; Axcess also reports `bowiestate` positive, so **the one page
where precision could have been gained was not gained**. Its partner `dell`,
KAFE's other false positive in the replayable subset, abstained and so is absent
from both rows.

### Coverage of the planned set

| Quantity | Value | Source |
| --- | --- | --- |
| Planned (replayable) subjects `\|L\|` | 53 | `derived/kafe_denominator.json` → `counts.replayable` |
| Scored `\|E\|` | 45 (0.849 of 53) | `derived/scored_summary.json` → `progress.scored` |
| Abstained | 8 | `progress.abstained` |
| Positive coverage | 26/31 = 0.839 | 31 replayable positives, 5 abstained |
| Negative coverage | 19/22 = 0.864 | 22 replayable negatives, 3 abstained |
| Identity check | 45 + 5 + 3 = 53 ✓ | — |

---

## 2. Pre-registered predictions, scored

Registered in `PREREGISTRATION-SCORED.md` §6, before the run. **Falsified first.**

| ID | Prediction | Verdict | Evidence |
| --- | --- | --- | --- |
| **H1** | On the common set, `R_A = R_K` **and** `P_A > P_K` | **FALSIFIED, both limbs** | `R_A` 0.885 < `R_K` 1.000; `P_A` 0.657 < `P_K` 0.963. Independently falsified by its own stated triggers: ≥1 missed positive (3) and ≥2 false positives (12). |
| **P-B** | Axcess reports all 31 positives | **FALSIFIED — the failure I predicted** | 3 of the 26 scored positives reported 0: `adorama`, `fandango`, `indiegogo` (`kafe_scored.jsonl` L3, L22, L26). A further 5 positives abstained and were never scored either way. |
| **P-A** | Axcess reports `bowiestate` = 0 and `dell` = 0 | **FALSIFIED** | `bowiestate` reported **1**, with 23 elements flagged (L9). `dell` abstained (L17), so it cannot be reported 0. Per P-A's own text, "the only available precision gain is gone and H1 is dead at that point." |
| **P-C** | Abstentions do not consume the comparison — falsified if `\|E\| < 40` **or** if `bowiestate` or `dell` abstains | **FALSIFIED** | `\|E\|` = 45, which passes; but `dell` abstained (L17), which is the second trigger. Registered consequence: the run is **inconclusive under §6.7 bucket 1 regardless of other cells**. |
| **P-D** | In-harness positive controls return non-`VIOLATION` on ≥90% of subjects | **NOT EVALUABLE** | The run planted no controls. `tools/kafe_scored_run.py` contains no control logic and `kafe_scored.jsonl` has no control field. The harness-over-reporting check I called "the most likely single point of failure in the run" **was not performed**. See §7. |
| **P-E**, **P-F** | GDS deliverable-A predictions | **NOT IN SCOPE HERE** | This report covers deliverable B only. `tools/gds_run.py`'s 6/6 is retracted per `PREMISE-CORRECTION.md` and is not cited as a result. |

### On P-B specifically

Yes — P-B failed, exactly as registered. But the reason I gave in advance for
discounting that failure **does not apply to this run**, and the failure is
therefore harder to explain away than pre-registration allowed for:

- P-B's text said a failure would be "over-determined and therefore uninformative
  about the detectors alone" because of two registered recall-reducing ablations:
  the candidate cap `N` = 12, and dropping `ArrowDown` from `TrialConfig.keys`.
- **Neither ablation was applied.** The run was unbounded — every addressable
  candidate on every subject was probed, 5,922 in total
  (`kafe_scored_run.py` docstring and line 216; `scored_summary.json` →
  `timing.total_probes`) — and `TrialConfig` was constructed with only `url`,
  `viewport` and `max_tabs` (line 185), so `keys` kept its default
  `("Enter", "Space", "ArrowDown")`
  (`src/audit/analyzer/keyboard/kbdiff/differential.py:65`).

So the three misses are not attributable to my budget or my key ablation. What
the raw records show instead, without inference beyond the file:

| Miss | Probes | Verdicts | Note |
| --- | --: | --- | --- |
| `adorama` (L3) | 30 | 29 `unknown`, 1 `no_lead` | essential denials present (`functionally_degraded: true`, 12 denied) |
| `fandango` (L22) | 13 | 12 `unknown`, 1 `no_lead` | essential denials present (16 denied) |
| `indiegogo` (L26) | 0 | none | capture yields 12 tagged nodes, 0 focusable, 0 candidates — nothing to probe |

`indiegogo` is not a detector miss in any meaningful sense; it is a page with
nothing on it that the run nonetheless scored negative. See §7.

---

## 3. Abstentions — 8 subjects, all one cause

An abstention is scored in neither class. It is **never** counted as a negative.

| Subject | Label `y` | Focusable | Derived cap | Tab stops found | Candidates (never probed) |
| --- | --- | --: | --: | --: | --: |
| `capitalone` (L10) | negative | 51 | 251 | 1 | 104 |
| `cnn` (L13) | **positive** | 283 | 483 | 133 | 510 |
| `costco` (L15) | negative | 69 | 269 | 39 | 126 |
| `dell` (L17) | negative | 97 | 297 | 36 | 148 |
| `dpreview` (L20) | **positive** | 94 | 294 | 97 | 177 |
| `raise` (L30) | **positive** | 62 | 262 | 34 | 77 |
| `salesforce` (L33) | **positive** | 38 | 238 | 9 | 14 |
| `spotify` (L36) | **positive** | 12 | 212 | 9 | 10 |

5 positive, 3 negative (`scored_summary.json` → `abstentions`). Own denominator:
**8/53 = 0.151 of the planned set**, 5/31 = 0.161 of the positives.

### The cause is established, not open

All 8 are tab walks that **never cycle back to their start element**. This is the
one condition under which `compute_tab_order` leaves `capped` true: the loop exits
early only when focus leaves the document or when the sequence returns to its
first stop (`src/audit/analyzer/keyboard/kbdiff/taborder.py:136-156`). A capped
walk makes every *absent* probe inconclusive rather than unreachable
(`TabOrder` docstring, taborder.py:79-82), so the subject abstains before any
probe runs (`kafe_scored_run.py:203-209`).

**It is a page property, not a budget set too low.** The falsification test, as
recorded in `BRIEF-CLAUDE-RESULTS.md`: on `spotify`, at cap 212 the walk caps, and
at cap **2000** it still caps. Raising the cap does not fix it. The detector
abstains rather than guessing, which is correct behaviour — and is precisely the
safeguard whose absence made the retracted reimplementation score 6/6 on GDS
(`PREMISE-CORRECTION.md`).

> **Discrepancy, flagged not resolved.** The brief states that spotify at cap 212
> "finds 0 stops"; `derived/kafe_scored.jsonl` L36 records `tab_stops: 9` for
> spotify at cap 212. No artifact of the cap-2000 test exists anywhere under
> `experiments/tabbing/literature-replication/`, so I could not reconcile the two
> and did not re-run anything to try. The conclusion the test supports — raising
> the cap does not clear the abstention — is unaffected by which count is right;
> the number itself is classified **claimed**, not verified, in §9.

### Pessimistic sensitivity: every abstention counted against us

Positive abstention = miss, negative abstention = false alarm. This is the
registered §6.6 sensitivity and is computed on all 53.

| | TP | FP | FN | TN | Precision | Recall |
| --- | --: | --: | --: | --: | --- | --- |
| **Axcess, pessimistic** | 23 | 15 | 8 | 7 | **23/38 = 0.605** | **23/31 = 0.742** |
| **KAFE, all 53 replayable** | 31 | 2 | 0 | 20 | **31/33 = 0.939** | **31/31 = 1.000** |

Sources: `scored_summary.json` → `pessimistic_with_abstentions`;
`kafe_denominator.json` → `replayable_subset`. On matched denominators of 53 the
gap widens: precision −0.334, recall −0.258.

---

## 4. The other registered sensitivities

`PREREGISTRATION-SCORED.md` §5.4 requires these to be reported alongside the
primary matrix. None of them rescues precision — it is **identical at 23/35 in
two of the three** — and each shrinks the evidence base.

| Sensitivity | Rule | TP | FP | FN | TN | n | Precision | Recall |
| --- | --- | --: | --: | --: | --: | --: | --- | --- |
| Primary | as scored | 23 | 12 | 3 | 7 | 45 | 23/35 = 0.657 | 23/26 = 0.885 |
| **Essential-denial** (§5.4.4) | drop the 25 subjects with ≥1 essential denial | 8 | 7 | 1 | 4 | 20 | **8/15 = 0.533** | 8/9 = 0.889 |
| **Unknown-pessimistic** (§5.4.5) | drop the 5 subjects with ≥1 `UNKNOWN` and 0 `VIOLATION` | 23 | 12 | 1 | 4 | 40 | 23/35 = 0.657 | 23/24 = 0.958 |
| **Non-vacuous only** (post-hoc) | drop the 5 subjects with 0 addressable candidates | 23 | 12 | 2 | 3 | 40 | 23/35 = 0.657 | 23/25 = 0.920 |

Computed from `derived/kafe_scored.jsonl` fields `functionally_degraded`,
`verdicts`, `reported_elements` and `addressable_candidates`. The last row is
**post-hoc**, added because §7 shows the run did not implement the registered
`no-candidates` abstention; it is labelled as post-hoc and is not used anywhere
above.

Two readings that matter more than the recall movements:

- On the 20 subjects whose captures replayed without losing an essential
  resource, **precision falls to 0.533** — the cleanest-fidelity stratum is the
  worst-precision stratum.
- The two sensitivities that raise recall do so by deleting negatives: TN falls
  from 7 to 4 or 3. The negative evidence in this run is thin to start with (see
  §7) and does not survive its own registered robustness checks.

---

## 5. Timing: the 300 ms per-button cap is breached

**Unit**, stated precisely because it is not the registered one: one
`DifferentialRunner.run_probe` call against one candidate — the mouse trial plus
one keyboard trial per configured key (`Enter`, `Space`, `ArrowDown`), each trial
in its own fresh browser context, plus the frozen 80 ms + 250 ms settles inside
each. Timed in `kafe_scored_run.py:216-224`. `PREREGISTRATION-SCORED.md` §5.5
registered the unit as *one actuation trial* via a `TimedRunner` subclass; that
subclass was not used, so **these figures are per whole probe and are therefore
larger than the registered unit would have produced.** `tab_order()` is excluded.

| Quantity | Value | Source |
| --- | --- | --- |
| Probes run | 5,922 | `scored_summary.json` → `timing.total_probes` |
| Total probe time | 7,254.9 s | `timing.total_probe_seconds` |
| Mean per probe | 1,225 ms | 7,254.9 s ÷ 5,922 |
| **Median of per-subject medians** | **518.0 ms** | `timing.median_of_per_subject_medians_ms` |
| p95 of per-subject medians | 4,142.4 ms | recomputed from `ms_median` over 40 subjects |
| Fastest subject median | 199.6 ms (`adorama`) | L3 |
| Slowest subject median | 4,585.0 ms (`ed`) | L21 |
| Slowest single probe | 6,450.6 ms (`cloudflare`) | L12 / `timing.max_probe_ms_observed` |
| **Subjects within the 300 ms cap** | **10 of 40** | `timing.subjects_whose_median_is_within_cap` |
| Subjects whose median is ≥ 3,500 ms | 5 (`tesla`, `wiktionary`, `dmv_ca`, `tinyurl`, `ed`) | `ms_median` |
| Subjects with no timing | 5 (zero probes) | `ms_median: null` |

**Reportable outcome: `exceeded`.** Against Harry's 300 ms per-button cap, the
median per-subject median is 518 ms — 1.7× the cap — and 30 of 40 timed subjects
breach it, the worst by more than 15×. The cap is a ceiling the detector must not
exceed. It is currently missed, and nothing in this report should be read as
reporting it as a win.

The 10 subjects that come in under the cap are not a counter-example: per
`TIMING-AND-SPOTCHECK.md` §1, cost scales with how operable an element is — an
unreachable probe short-circuits after the mouse trial, while a reachable one
pays for every key. Cheap subjects are cheap because little was delivered.
`adorama`, the fastest at 199.6 ms, returned `unknown` on 29 of 30 probes.

**Scale reference, not a comparison.** KAFE's Detection phase averages 995 ms
**per subject page**, recomputed from its own artifact. That is per-page; every
figure in this section is per-probe. They are not comparable and no speed claim
is made from them. KAFE's published 19.22 min is proxy/crawl/extract
infrastructure, not detection.

---

## 6. Per-subject table

Every column is read directly from `derived/kafe_scored.jsonl`; `L` is the line
number in that file (the file's own order is run order, this table is
alphabetical). `kafe` is that subject's historical KAFE prediction from
`derived/kafe_denominator.json`. `probes` is candidates actually probed;
abstentions probe none, so their candidate counts appear in §3 instead.

| L | Subject | y | ŷ | kafe | probes | reported | median ms | outcome |
| --: | --- | :-: | :-: | :-: | --: | --: | --: | :-- |
| 3 | adorama | 1 | 0 | 1 | 30 | 0 | 199.6 | **FN** |
| 4 | alexa | 1 | 1 | 1 | 271 | 9 | 320.0 | TP |
| 5 | ancestry | 0 | 1 | 0 | 122 | 14 | 278.4 | **FP** |
| 6 | ask | 0 | 1 | 0 | 89 | 51 | 912.6 | **FP** |
| 7 | bbc | 0 | 1 | 0 | 40 | 4 | 873.6 | **FP** |
| 8 | boostmobile | 1 | 1 | 1 | 140 | 11 | 442.0 | TP |
| 9 | bowiestate | 0 | 1 | 1 | 73 | 23 | 861.9 | **FP** (KAFE FP too) |
| 10 | capitalone | 0 | — | 0 | — | — | — | abstain |
| 11 | carlsjr | 1 | 1 | 1 | 81 | 2 | 345.1 | TP |
| 1 | citiprogram | 1 | 1 | 1 | 27 | 3 | 218.9 | TP |
| 12 | cloudflare | 1 | 1 | 1 | 105 | 5 | 842.5 | TP |
| 13 | cnn | 1 | — | 1 | — | — | — | abstain |
| 14 | coinbase | 1 | 1 | 1 | 96 | 4 | 519.5 | TP |
| 2 | coronavirus | 0 | 0 | 0 | 59 | 0 | 3090.9 | TN |
| 15 | costco | 0 | — | 0 | — | — | — | abstain |
| 16 | craigslist | 1 | 1 | 1 | 898 | 202 | 793.5 | TP |
| 17 | dell | 0 | — | 1 | — | — | — | abstain |
| 18 | discordapp | 1 | 1 | 1 | 263 | 8 | 613.7 | TP |
| 19 | dmv_ca | 0 | 1 | 0 | 39 | 4 | 4023.4 | **FP** |
| 20 | dpreview | 1 | — | 1 | — | — | — | abstain |
| 21 | ed | 0 | 1 | 0 | 139 | 34 | 4585.0 | **FP** |
| 22 | fandango | 1 | 0 | 1 | 13 | 0 | 453.3 | **FN** |
| 23 | flickr | 1 | 1 | 1 | 30 | 21 | 918.5 | TP |
| 24 | godaddy | 1 | 1 | 1 | 21 | 10 | 743.4 | TP (partial capture) |
| 25 | groupon | 1 | 1 | 1 | 55 | 22 | 767.0 | TP |
| 26 | indiegogo | 1 | 0 | 1 | 0 | 0 | — | **FN** (no candidates) |
| 27 | instagram | 0 | 0 | 0 | 0 | 0 | — | TN (no candidates) |
| 28 | live | 0 | 1 | 0 | 262 | 1 | 200.0 | **FP** |
| 29 | mozilla | 0 | 0 | 0 | 0 | 0 | — | TN (no candidates) |
| 30 | raise | 1 | — | 1 | — | — | — | abstain |
| 31 | resellerratings | 1 | 1 | 1 | 308 | 33 | 593.8 | TP |
| 32 | roblox | 0 | 1 | 0 | 86 | 12 | 450.2 | **FP** |
| 33 | salesforce | 1 | — | 1 | — | — | — | abstain |
| 34 | sciencedirect | 0 | 0 | 0 | 0 | 0 | — | TN (no candidates) |
| 35 | snapchat | 1 | 1 | 1 | 22 | 3 | 292.9 | TP |
| 36 | spotify | 1 | — | 1 | — | — | — | abstain |
| 37 | ssa | 0 | 1 | 0 | 131 | 22 | 209.0 | **FP** |
| 38 | stacksocial | 1 | 1 | 1 | 236 | 1 | 479.4 | TP |
| 39 | steam | 1 | 1 | 1 | 343 | 26 | 246.7 | TP |
| 40 | stickermule | 1 | 1 | 1 | 68 | 5 | 456.6 | TP |
| 41 | telegram | 0 | 1 | 0 | 171 | 28 | 801.0 | **FP** |
| 42 | tesla | 1 | 1 | 1 | 11 | 1 | 3593.1 | TP |
| 43 | thefreedictionary | 1 | 1 | 1 | 63 | 1 | 288.5 | TP |
| 44 | tinyurl | 0 | 0 | 0 | 15 | 0 | 4148.7 | TN |
| 45 | ubersignup | 1 | 1 | 1 | 250 | 3 | 516.5 | TP |
| 46 | usgsgov | 1 | 1 | 1 | 624 | 129 | 254.7 | TP |
| 47 | venmo | 0 | 1 | 0 | 49 | 4 | 879.2 | **FP** |
| 48 | vk | 1 | 1 | 1 | 79 | 8 | 353.7 | TP |
| 49 | walmart | 0 | 0 | 0 | 85 | 0 | 201.8 | TN |
| 50 | waze | 1 | 1 | 1 | 22 | 11 | 893.6 | TP |
| 51 | wendys | 1 | 1 | 1 | 221 | 12 | 345.8 | TP |
| 52 | whitepages | 0 | 0 | 0 | 0 | 0 | — | TN (no candidates) |
| 53 | wiktionary | 0 | 1 | 0 | 285 | 84 | 3937.7 | **FP** |

Totals: 23 TP, 12 FP, 3 FN, 7 TN, 8 abstain = 53. Element-level totals across the
scored set: 811 `violation`, 1,246 `no_lead`, **3,865 `unknown`** (65.3% of all
5,922 probes), 0 probe errors. `reported_ids` in the raw file is truncated at 50
entries per subject; `reported_elements` is the full count.

---

## 7. Deviations from the pre-registration, found in the run script

Every item is read from `tools/kafe_scored_run.py` and `derived/kafe_scored.jsonl`
and is verifiable there. These are not findings; they are limits on what the
numbers above mean. Three of them favour the reported result.

| Registered (`PREREGISTRATION-SCORED.md`) | What actually ran | Effect |
| --- | --- | --- |
| §4.3 candidate cap `N` = 12/subject | **No cap** — all 5,922 addressable candidates probed (docstring, line 216) | Favours Axcess: a registered recall ceiling was removed. Also removes it as an excuse for P-B's failure. |
| §4.1 `keys = ("Enter","Space")`, dropping `ArrowDown` | **Default keys** including `ArrowDown` (line 185 passes no `keys`) | Favours Axcess: the registered recall-reducing ablation was not applied. Raises per-probe cost by ~1 trial. |
| §4.3 up to 2 in-harness positive controls per subject; **P-D** | **No controls planted** | The §6.2 over-reporting check did not run. Under §6.2 an over-reporting harness voids a run; that possibility is untested here, and with 12 false positives it is exactly the hypothesis one would want excluded. |
| §5.3 bucket 6 `no-candidates` → abstain | **Not implemented.** 5 subjects with 0 candidates were scored: `indiegogo` (FN), `instagram`, `mozilla`, `sciencedirect`, `whitepages` (TN) | **4 of the 7 true negatives are vacuous** — the detector had nothing to examine and was credited with a correct negative. |
| §5.3 bucket 1 `unreadable-capture` → abstain (named `godaddy` in advance) | **Not implemented.** `godaddy` has `unreadable_flows: 1` (`kafe_denominator.json` → `partial_read_subjects`) and was scored as a TP (L24) | Favours Axcess by one TP. Without it: 22/34 = 0.647 precision, 22/25 = 0.880 recall. |
| §4.2 `max_tabs = min(4000, max(300, 2F + 100))`, rendered/enabled/shadow-aware `F` | `cap = focusable + 200` with a simpler selector (lines 154-157, 184) | Different caps than registered. Does not change the abstention conclusion — §3's cap-2000 test is the relevant evidence — but the registered formula was not the one used. |
| §7 `derived/manifest_scored.json` with re-verified detector hashes and browser build | **Not produced** (absent from `derived/`) | The detectors' frozen-ness rests on the import statements at `kafe_scored_run.py:50-54` and on the session's git snapshot showing no modification under `src/audit/`, not on a re-verified hash manifest. The Chromium build string used by the run was never recorded. |
| §5.5 timing unit = one actuation trial via `TimedRunner` | Whole-probe wall time | §5 figures are larger than the registered unit. |
| §4.4 fresh `ReplayRouter` per context | **One router** shared across contexts (line 109) | Repeated requests advance one shared cursor across trials, so two trials of the same probe can be served different responses for the same URL — the exact confound §4.4 was written to avoid. Untested magnitude. |

---

## 8. Limits that no number in this report clears

1. **Chromium-only; this is not a reproduction of KAFE's condition.** KAFE ran
   Firefox 68.0 under Selenium 3.141.5 (`LITERATURE.md:40`). This run used
   Chromium via Playwright 1.58.0; Playwright's expected Firefox and WebKit
   binaries are absent from the local cache (`ENVIRONMENT.md`). Treated as
   **permanent** per `PROTOCOL.md` B3. Browser, capture fidelity and detector are
   confounded and are not separable here.
2. **The exclusion is label-correlated, so this is not a result on KAFE's
   corpus.** 7 of 60 subjects were unreplayable and **5 of the 7 are
   IAF-positive** (`kafe_denominator.json` → `counts.excluded_positive`). The 53
   are a biased remainder, and the 45 scored are a further non-random subset of
   those. No figure here may be described as a result on the published corpus.
3. **The 12 false positives are unadjudicated.** No human has looked at any of
   them. It is not known whether any is a real inaccessible-action finding that
   KAFE missed, nor whether any is a harness artifact — and with no positive
   controls (§7), the artifact hypothesis was never tested. `PREREGISTRATION-
   SCORED.md` §3 (§6.8) explicitly withheld element adjudication: **no element
   precision is reported at all**, and 811 flagged elements stand unexamined.
4. **Single run, one repeat, no stability check.** §6.5's three repeats were not
   run. Nothing here establishes within-subject stability; no subject may be
   called stable, and `unstable` cannot be detected.
5. **The run is inconclusive about H1 by its own pre-registered criterion** (P-C,
   §2), because `dell` abstained.
6. **No same-replay comparator.** No axe-core, no `candidates − TabOrder`, no
   re-run of KAFE. KAFE's column is a 2021 historical result replayed against
   2026 Chromium, which is a fidelity-conditional contrast, not a head-to-head.
7. **Capture fidelity is degraded on most subjects.** 25 of the 45 scored lost at
   least one essential (`.js`/`.css`/`.json`/`.html`) resource to default-deny
   (`functionally_degraded: true`). §5.3's registered precedence would have
   abstained them; this run deliberately did not, which makes the primary matrix
   **more permissive** than §6.3 allows.
8. **§6.9 is not met** (§0), so no number here is a release-gated result.

---

## 9. Verified / claimed / assumed

**Verified** — I executed the analysis and the raw file reproduces it:

- Every cell of §1, §3's pessimistic table, §4, §5 and §6: recomputed by
  `tools/analyze_scored.py` from `derived/kafe_scored.jsonl` in this session, and
  matching `derived/scored_summary.json`.
- 45 scored / 8 abstained / 53 planned; 5 positive and 3 negative abstentions.
- All 8 abstention reasons are capped tab walks (`reason` field, all 8 records).
- Every deviation in §7: read from `tools/kafe_scored_run.py` and confirmed
  against field values in the raw file.
- Element verdict totals, probe count, probe seconds, 0 probe errors.

**Claimed** — asserted by a document, not re-executed here (I was instructed not
to re-run the experiment):

- The spotify cap-2000 falsification test, and its "0 stops at cap 212"
  (`BRIEF-CLAUDE-RESULTS.md`). No artifact of it exists in this tree, and the
  stop count conflicts with `kafe_scored.jsonl` L36's `tab_stops: 9` (§3).
- KAFE's Detection phase averaging 995 ms per subject page, and the 19.22 min
  being infrastructure (`TIMING-AND-SPOTCHECK.md` §1).
- KAFE's historical per-subject predictions (`kafe_denominator.json`), which
  reproduce the published 36/3/0/21 via that file's own P1 control.
- Chromium 145.0.7632.6 / Playwright 1.58.0 (`PROTOCOL.md:102`) — the run wrote no
  manifest, so the browser build actually used is not recorded anywhere (§7).
- `src/audit/` unmodified during the run: from the session's git snapshot, not
  re-verified with `git` in this session.
- The run took roughly three hours (brief). The raw file accounts for 7,457.5 s
  (2 h 04 min) of per-subject elapsed time; the difference is unaccounted setup.

**Assumed** — neither verified nor separately documented:

- That `data-probe` ids mirrored from the neutral positional census
  (`kafe_scored_run.py:124-153`) address the same elements across the separate
  contexts of a single probe. Identity is structural, so this should hold, but no
  control in this run tests it.
- That the 2021 captures replayed in 2026 present pages whose keyboard behaviour
  resembles what KAFE observed. §8.7 is the direct evidence against.

---

## 10. Reproducing this report

```bash
cd experiments/tabbing/literature-replication
uv run --offline --no-sync python -m tools.analyze_scored
```

Prints the §1 matrices, the abstention counts and reasons, and the §5 timing
line; rewrites `derived/scored_summary.json`. The per-subject table of §6 and the
sensitivities of §4 are read from `derived/kafe_scored.jsonl` directly, one JSON
record per line, line numbers as given.
