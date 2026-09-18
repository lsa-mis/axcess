# Plan: close every empty cell in MATRIX-RESULTS.md

Written by Opus 5 before execution, per the standing planning gate. Nothing here
has been run yet. Implementation is delegated to Claude Code; verification is
Opus 5's and is defined in §5 below.

## 1. Requirements, cumulative

Every requirement the user has stated across this project, with status.

| # | Requirement | Status |
|---|---|---|
| R1 | Replicate published environments; run the **frozen** detectors | done |
| R2 | **Every** detector, not one configuration | done (43) |
| R3 | Per detector: precision, recall, **ms** | **partial — ms blank on many rows** |
| R4 | ms for KAFE too, same axis | open (KAFE not in matrix) |
| R5 | One comparison table, `detector-matrix.results.md` format | **partial — missing columns** |
| R6 | 300 ms = per-button cap, not a win metric | done |
| R7 | Full 60 KAFE subjects | done (53 replayable) |
| R8 | All three environments, one table each | done (4 corpora) |
| R9 | Don't commit the two PDFs | done |
| R10 | KAFE scored page-level only | done |
| R11 | ms unit = per-button | done |
| R12 | Abstention is never a negative | done |
| R13 | Find the newer detectors from code | done |
| **R14** | **No empty fields in the table** | **OPEN — this plan** |
| **R15** | **C10–C16 must appear** (from `CHEAP_DETECTOR_REVIEW.md`) | **OPEN — this plan** |
| **R16** | **edgecases must have ms** | **OPEN — this plan** |
| **R17** | Every field in `CHEAP_DETECTOR_REVIEW.md` must be represented | **OPEN — this plan** |

## 2. Diagnosis: four distinct causes, not one

Opus 5 read the raw artifacts before planning. The blanks are not a single bug.

### Gap A — variant rows have no own timing key (7 rows per corpus)

`D9+S4ours`, `D9-noS4`, `D9u+S4u`, `D10a+base`, `D10b`, `D10a-u`, `D10b-u` show
`ms = —`. These are **re-scorings of one measured arm**, not separate
measurements. Only `D9`, `D9+S4u`, `D9u`, `D10a` carry timing keys.

The published `detector-matrix.results.md` already solved this: it has an
**`ms covers`** column reading `measured` or `priced at its arm`. Opus 5's
aggregator dropped that convention and left the cell blank instead.

**This needs no re-run.** It is a mapping plus one column.

| variant | priced at | covers |
|---|---|---|
| D9-noS4, D9+S4ours | D9 behavioural differential | priced at its arm |
| D9u+S4u | D9u upstream-style differential | priced at its arm |
| D10b, D10a+base | D10a coverage differential | priced at its arm |
| D10a-u, D10b-u | D10a coverage differential | priced at its arm |

### Gap B — edgecases has zero score rows (whole corpus blank)

`bakeoff-edgecases-matrix.json` contains `scores: []` but **13 pages of real
`page_timings_ms`**. The ms column is blank because there are no rows to attach
timings to. Cause: `CDPSession.send: Protocol error (DOM.getDocument): Failed to
convert response to JSON: CBOR: stack limit exceeded at position 53429`, which
aborts scoring for the corpus.

This is a **deeply-nested DOM defeating CDP's CBOR encoder**. `DOM.getDocument`
with unbounded `depth` serialises the entire tree in one response. The fix is to
bound the traversal (`depth=-1` → paged/`pierce` with explicit depth, or fall
back to a DOM walk) so the response fits. Diagnose before choosing.

### Gap C — C10–C16 are absent from every corpus

**These are not in `bakeoff.py` at all.** They are scored offline by
`experiments/tabbing/probes/score_new.py` (C10–C13) and `score_new2.py`
(C14–C16), reading four saved probe files: `containment.json`, `composite.json`,
`effect.json`, `effect2.json`.

Those probe scripts now accept `PROBE_CORPUS` (three already did; Opus 5 ported
`probe_effect2.py` in step 1 and verified it reproduces the published numbers
exactly under the original filter). So the pipeline **can** run per corpus, but
never has been run for gds, ma11y, or edgecases.

**Known scope caveat, already measured:** the published C16 = 100% precision was
produced by observing 42 of 95 probes (the C12 lead set, `c12.json`). Observing
all 95 gives 38 TP / 11 FP = 77.6%. Both numbers must appear, labelled by which
lead set was observed. Do not silently pick one.

### Gap D — columns from `CHEAP_DETECTOR_REVIEW.md` were dropped

That document's table carries columns the matrix lacks:

- **`Unknown defects / negatives`** — abstentions split into positive and
  negative. Opus 5 collapsed both into one `abst.` column. The raw data has
  `unknown_positive` and `unknown_negative` already; the split is free.
- **`ms per target`** — the amortised throughput figure the published tables
  use. Opus 5 replaced it with `ms/button`. **Both must appear**, in separate
  labelled columns, because they answer different questions and the 300 ms cap
  is stated per button while the published comparison is per target.
- **`Strict recall`** — divides TP by *all* defects including undecided ones,
  rather than by decided ones. Verify which `bakeoff.py` emits (`recall` vs
  `recall_conditional`) and label the column correctly.

An `F1` of `—` where precision is `—` is **correct**, not a gap: zero flags
means precision is undefined. Leave those, and add a footnote saying so.

## 3. What Claude Code implements

In order. Each step has a control that must pass before the next.

1. **Gap A** — add `ms covers` to `tools/assemble_matrix.py` and price the 7
   variants at their arms. Control: `D9` and `D9+S4u` keep their own measured
   values unchanged.
2. **Gap D** — split `abst.` into `unk pos / unk neg`; add `ms/target` beside
   `ms/button`; label the recall column correctly. Control: fixtures rows still
   match `detector-matrix.results.md` cell for cell.
3. **Gap B** — diagnose and fix the CDP CBOR overflow, re-run edgecases.
   Control: the run completes with a non-empty `scores` array, and fixtures
   still reproduces its published numbers after the change.
4. **Gap C** — run the four probe scripts + `score_new.py` + `score_new2.py` for
   each corpus; merge C10–C16 into the matrix. Control: fixtures C10–C16 must
   reproduce `CHEAP_DETECTOR_REVIEW.md` exactly (C13 37/4/1 90.2%, C15 37/0/1
   100%, C16 38/0/0 100%) when run under the `c12.json` filter.

## 4. Hard constraints

- **Do not edit `src/audit/`.** The detectors are frozen. `bakeoff.py` and
  `experiments/tabbing/probes/` are harness and may be changed.
- **Do not commit.** Opus 5 reviews and commits.
- **Do not fabricate a number.** If a cell cannot be measured, emit a short
  reason string (`not applicable`, `abstained`, `measurement failed: <why>`)
  rather than a blank or a guess.
- **Every changed measurement path needs a control** proving the published
  fixtures numbers are unmoved.

## 5. How Opus 5 verifies

Independently of whatever Claude Code reports:

1. Recompute the fixtures rows from the raw JSON and diff against
   `detector-matrix.results.md` and `CHEAP_DETECTOR_REVIEW.md`.
2. Assert **zero** unexplained blank cells: every empty cell must carry a reason
   string, and F1-undefined must coincide with precision-undefined.
3. Confirm C10–C16 are present for every corpus where the probe inputs exist,
   and that both the filtered and unfiltered C16 figures appear.
4. Confirm edgecases has a populated `scores` array and real ms.
5. Confirm `git diff --stat src/audit/` is empty.
