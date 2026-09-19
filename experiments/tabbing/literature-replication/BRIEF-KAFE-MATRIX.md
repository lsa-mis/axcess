# Brief: all 48 detectors on KAFE's benchmark, against KAFE's own result

Working dir: `/var/home/me/Development/axcess/experiments/tabbing/literature-replication`

Produce one table comparing **every Axcess detector (C1–C16 and the full D/U
families, 48 rows)** against **KAFE's own published result**, on **KAFE's own
60-subject benchmark**, with precision, recall, and **milliseconds** filled for
every row.

Reference: Chiou, Alotaibi & Halfond, *Detecting and Localizing Keyboard
Accessibility Failures in Web Applications*, ESEC/FSE 2021,
DOI [10.1145/3468264.3468581](https://doi.org/10.1145/3468264.3468581).

## Decisions already made — do not revisit

1. **KAFE's detector = their published per-subject CSV**
   (`artifacts/kafe_results_to_reproduce.csv`). That file IS their tool's output
   on their corpus. Do **not** try to build the Java/Selenium/Firefox-68 stack.
2. **All 48 detectors run**, including the expensive D9/D10 behavioural arms.
   Runtime is accepted, however many hours. Checkpoint per subject.
3. **Scoring is page-level.** KAFE labels pages, not elements.
4. **Abstention is never a negative.** A capped walk or unreadable page is an
   abstention, reported in its own column.

## Already verified — do not re-derive

These are controls Opus 5 has already run. Reuse them; if your run disagrees,
that is a finding, so report it rather than adjusting.

- KAFE IAF (Type 1) recomputed from their CSV: **n=60, TP=36, FP=3, FN=0,
  TN=21, precision 92.3%, recall 100.0%** — matches their published Table 1
  (92% / 100%).
- KAFE Detection phase, **ms per subject**: median 1088, mean 995, 8/60 under
  300 ms.
- KAFE Detection phase, **ms per button** (`Detection` ÷ `Size of All Visible
  Ctrl Nodes`): **median 25.8, mean 46.7, 60/60 under the 300 ms cap.**
- 53 of 60 subjects are replayable; `4shared` and `dmv_fl` have a corrupted
  length prefix on record 0, and 5 subjects are folder-form asset dumps.

## What to build

### 1. Page-level scoring adapter

`bakeoff.py` scores element-level probes and its `load_truth` demands them.
KAFE gives page-level labels and its captures carry no `data-probe`.

Add an adapter (suggest `tools/kafe_matrix.py`) that, per subject:

- replays the capture (see `tools/kafe_scored_run.py` and `tools/replay.py`);
- runs every detector through the same seams `bakeoff.py` uses — `run_page` for
  the cheap tier and `run_behavioural` for the D9/D10 arms — so the **frozen**
  detectors produce the verdicts, not a reimplementation;
- aggregates each detector's element proposals to one page verdict:
  **page-positive iff the detector flagged ≥1 element**;
- scores that against `Type 1 Detection Ground Truth` in their CSV;
- records, per subject per detector: verdict, count of elements flagged,
  candidates probed, and **measured milliseconds**.

Checkpoint to JSONL per subject so an interruption costs one subject.

### 2. The ms column, both units

- **ms per button** = detector's measured browser time ÷ candidates it probed.
  This is the 300 ms cap unit and the headline.
- **ms per subject** = total measured time for that subject.

Both must appear for Axcess rows and for KAFE, computed the same way on both
sides. KAFE's per-button figure comes from their own columns as above.

### 3. The table

One row per detector (48) plus one row for **KAFE**, with: TP, FP, FN, TN,
abstentions, precision, recall, F1, ms/button, ms/subject, and a `ms covers`
column (`measured` or `priced at its arm`) following the convention already in
`tools/assemble_matrix.py`.

**No cell may be blank.** If something cannot be measured, write a short reason
(`not applicable`, `abstained`, `measurement failed: <cause>`). F1 undefined
where precision is undefined is correct — footnote it.

## Hard constraints

- **Never edit `src/audit/`.** Detectors are frozen. `git diff --stat
  src/audit/` must be empty at the end. If git is blocked in your sandbox, say
  so explicitly rather than claiming it passed.
- **Do not commit.**
- **Never fabricate a number.** A missing measurement is reported, not guessed.
- Every subject that fails to replay is **excluded and counted**, never scored
  as a negative.
- If you think a premise here is wrong, say so and stop. A previous agent on
  this project correctly challenged a premise and caught a real error; that is
  wanted.

## Controls you must run

1. **KAFE reproduction**: recompute their confusion matrix from their CSV and
   confirm 36/3/0/21 at 92.3%/100%. If it differs, stop.
2. **Denominator control**: the subject count you score must equal the subjects
   that actually replayed. State it explicitly; excluded subjects listed by name
   and reason.
3. **Negative control**: at least one subject KAFE labels `FALSE` (no IAF) must
   be scored, and detectors that flag nothing there must record a true negative,
   not an abstention.
4. **Frozen-code control**: confirm the detectors imported are the ones under
   `src/audit/analyzer/keyboard/kbdiff/`, not a local copy.

## Deliverables

1. `tools/kafe_matrix.py` (or equivalent) + the per-subject JSONL.
2. `KAFE-MATRIX.md`: the full 49-row table, with provenance stated before it —
   benchmark, paper, DOI, KAFE's published 92%/100%, and the caveat that
   page-level scoring discards element precision (a detector flagging 20
   elements where 1 is real still scores a page-level TP).
3. `KAFE-MATRIX-REPORT.md`: what you found, which controls you ran and their
   output, and **anything you could not close, first**.

Lead with whatever failed. A gap reported clearly beats a full table nobody can
trace.
