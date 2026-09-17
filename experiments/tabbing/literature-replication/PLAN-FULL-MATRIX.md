# Plan: the full 38-detector matrix across three environments

Written by Opus 5 before execution, after the planning gate. Supersedes the
single-configuration `RESULTS.md`. Nothing in this file has been run yet.

## Why this plan exists

`RESULTS.md` reported one row, "the frozen Axcess detectors", which was a single
default `TrialConfig` on `DifferentialRunner` — one configuration of D9. The
suite has **38 detectors and combination rules**. The report also omitted the
millisecond column entirely. Three hours of compute answered a question Harry
never asked.

The cause was executing before planning. That is now a mechanical gate in
`SOUL.md` and `agent-manager`, not a judgment call.

## Requirements, cumulative and binding

Every requirement Harry has stated across the conversation, not just the latest.

| # | Requirement | Source |
| --- | --- | --- |
| R1 | Replicate published environments; run the **frozen** detectors, never a reimplementation | original brief; enforced after the arm-1 retraction |
| R2 | **Every** detector and rule, not one configuration | this round |
| R3 | Per detector: precision, recall, **and milliseconds** | this round |
| R4 | Milliseconds for the KAFE reference too, on the same axis | this round |
| R5 | One comparison table, in `detector-matrix.results.md` format | this round |
| R6 | 300 ms is a per-button **cap the detector must not exceed**, never a win metric | earlier clarification |
| R7 | All 60 KAFE subjects, not N=3 | earlier instruction |
| R8 | All three environments, one table each | this round |
| R9 | Do not commit the two research PDFs | this round — done, ignored at repo root |
| R10 | KAFE scored **page-level only**; element precision only where element labels exist | this round |
| R11 | ms unit = **per-button** (total detector ms / candidates probed) | this round |
| R12 | An abstention is **never** a negative | this round |
| R13 | Find the newer detectors from code myself | this round |
| R14 | Ma11y mutates the **GDS page** with F42, F54, F55, F59 | this round |
| R15 | Port the 4 `probe_*.py` scripts so C10–C16 can run off-fixtures | this round |

## What the enumeration found

Enumerated from code, not from the results file. The 38 split into tiers with
**different execution requirements**, which is what makes this more than one run:

| Tier | Members | Cost | Runs on KAFE/GDS today? |
| --- | --- | --- | --- |
| Cheap static | D0, D2, D2b, D3, D4, D7 | pure functions over one `survey()` call | yes |
| Cheap dynamic | D5 (CDP), D6 (shim), D8 (hover pass) | moderate | yes |
| External | D1, D1x (axe-core) | moderate | yes |
| Combinations | C1–C9 | built inside `bakeoff.py` | yes |
| Combinations | **C10–C16** | offline reconstruction | **no — see below** |
| Behavioural | D9, D9-noS4, D9+S4u, D9+S4ours, D9u, D9u+S4u | ~1.5 s/probe | yes |
| Coverage | D10a, D10b, D10a-u, D10b-u, D10a+base | ~0.8 s/probe | yes |

**The C10–C16 blocker.** These are not implemented in detector code at all.
`experiments/tabbing/probes/score_new2.py` reconstructs them offline from four
saved observation files — `containment.json`, `composite.json`, `effect.json`,
`effect2.json` — produced by `probe_*.py` scripts hardcoded to
`experiments/tabbing/fixtures`. Without the port (R15) seven of the 38 rows are
permanently blank on every corpus except fixtures. The scripts live under
`experiments/`, not `src/audit/`, so porting them does not touch frozen code.

## Environments

| Env | Pages | Labels | Reference to beat |
| --- | --- | --- | --- |
| **KAFE** | 53 replayable of 60 | page-level IAF only | TP=26 FP=1 FN=0 TN=18 on the matched set → precision 26/27, recall 26/26 |
| **GDS** | 1 page, 8 cases | element-level, from `tests.json` | all 13 audited tools score **0/6** |
| **Ma11y** | GDS page × {F42, F54, F55, F59} | element-level **by construction** | none published; the mutation is the ground truth |

Per R10, KAFE is scored page-positive iff ≥1 element reported, and **no
element-level precision figure is reported for it**. Fixtures and edgecases keep
their element-level scoring, which is where the existing 95-probe table lives.

## Sequence

1. **Port the 4 `probe_*.py` scripts** to take a corpus root (R15). Mechanical.
   Verify by reproducing the published fixtures C10–C16 numbers exactly — if the
   port changes a known result, the port is wrong.
2. **Build the Ma11y environment** (R14): apply F42, F54, F55, F59 to the GDS
   page, each mutant its own page, ground truth recorded at generation time.
   F54 is already validated to manufacture genuine mouse-only controls.
3. **Cheap tier** (D0–D8, D1, D1x) on all three environments. Fast; fills most
   rows.
4. **C1–C9** via `bakeoff.py` on all three.
5. **C10–C16** via the ported probes on all three.
6. **Expensive tier** (D9 ×6, D10 ×5) on all three. This is the multi-hour part.
   Append per-subject to JSONL so an interruption costs one subject.
7. **Tables**: one per environment, plus the comparison against each published
   reference.

## Measurement rules, fixed before running

- **Per-button ms** (R11) = total detector milliseconds / candidates probed.
  Reported per detector. The amortised `ms/target` from the existing table is a
  different number and will be labelled as such if shown alongside.
- **300 ms** (R6) is a ceiling, reported as met or breached. No speed ranking,
  no "faster than KAFE" claim. KAFE's 995 ms Detection phase is **per page** and
  is not commensurable with per-button figures.
- **Abstentions** (R12) get their own column and denominator. Never folded into
  negatives. `capitalone` abstained on a cap I set too low (`TAB_HEADROOM=200`)
  and is fixed for this run; the other 7 are genuine page properties, confirmed
  at 10–20× cap in `derived/abstention_probe.json`.
- Every detector gets a row. One that cannot run on a corpus gets a row stating
  why — an empty row with a reason beats a missing row.
- Pre-register predictions per stage before running it.

## Constraints

Detectors and `score.py` stay frozen: imported, never edited. No commits without
asking. No network, no installs. Captured KAFE bytes stay under the gitignored
`artifacts/` and are never committed or redistributed — their licence is
unresolved and they are copies of third-party commercial sites.
