# Brief: close every empty cell in the detector matrix

You are implementing `PLAN-CLOSE-GAPS.md`, in this directory. **Read it first**
— it contains the diagnosis of all four gaps. This brief is the execution
contract; the plan is the reasoning.

Working dir: `/var/home/me/Development/axcess/experiments/tabbing/literature-replication`

## The problem

`MATRIX-RESULTS.md` has many empty cells. They have **four different causes**
and four different fixes. Do not apply one fix to all of them.

## Hard constraints

1. **Never edit `src/audit/`.** The detectors are frozen. `git diff --stat
   src/audit/` must be empty when you finish. `experiments/tabbing/runner/` and
   `experiments/tabbing/probes/` are harness code and may be changed.
2. **Do not commit anything.** Leave changes in the working tree.
3. **Never fabricate a number.** If a cell cannot be measured, write a short
   reason string — `not applicable`, `abstained`, `measurement failed: <cause>`
   — never a blank and never a plausible-looking guess.
4. **Every measurement change needs a control** proving the published fixtures
   numbers did not move. If a control fails, stop and report; do not "fix" the
   number to match.
5. If you believe a premise in this brief is wrong, **say so and stop**. A
   previous agent on this project correctly challenged a premise and that
   caught a real error. That is wanted behaviour.

## Task 1 — Gap A: variant rows have no ms (no re-run needed)

Seven rows show `ms = —` because they are **re-scorings of one measured arm**,
not separate measurements: `D9-noS4`, `D9+S4ours`, `D9u+S4u`, `D10b`,
`D10a+base`, `D10a-u`, `D10b-u`.

The published `experiments/tabbing/results/detector-matrix.results.md` already
handles this with an **`ms covers`** column reading `measured` or `priced at its
arm`. Adopt that convention in `tools/assemble_matrix.py`:

| variant | priced at |
|---|---|
| D9-noS4, D9+S4ours | D9 behavioural differential |
| D9u+S4u | D9u upstream-style differential |
| D10b, D10a+base, D10a-u, D10b-u | D10a coverage differential |

Read the published table to confirm each mapping rather than trusting this list.

**Control:** `D9` and `D9+S4u` keep their own measured values, unchanged.

## Task 2 — Gap D: restore dropped columns

`experiments/tabbing/CHEAP_DETECTOR_REVIEW.md` has columns the matrix lost.

1. **Split abstentions.** The matrix has one `abst.` column; the review has
   `Unknown defects / negatives`. The raw JSON already carries
   `unknown_positive` and `unknown_negative` — emit both.
2. **Add `ms per target` beside `ms/button`.** They answer different questions:
   the 300 ms cap is per button, the published comparison is per target.
   Keep both, labelled. Do not replace one with the other.
3. **Label the recall column correctly.** The review uses *strict recall* (TP
   over ALL defects including undecided). `bakeoff.py` emits both `recall` and
   `recall_conditional`. Determine which is which and label accurately.
4. **F1 `—` where precision is `—` is correct**, not a gap: zero flags means
   precision is undefined. Leave those and add a footnote.

**Control:** fixtures rows still match `detector-matrix.results.md` cell for cell.

## Task 3 — Gap B: edgecases scores are empty

`experiments/tabbing/edgecases/results/bakeoff-edgecases-matrix.json` has
`scores: []` but 13 pages of real `page_timings_ms`. Cause:

```
CDPSession.send: Protocol error (DOM.getDocument):
Failed to convert response to JSON: CBOR: stack limit exceeded at position 53429
```

A deeply-nested DOM defeats CDP's CBOR encoder when `DOM.getDocument`
serialises the whole tree in one response.

**Diagnose first, then fix.** Find which page triggers it and how deep its DOM
is before choosing between: bounding `depth`, paging the traversal, or falling
back to a DOM walk on failure. Report what you found.

**Control:** after the change, fixtures must still reproduce its published
numbers, and edgecases must produce a non-empty `scores` array.

## Task 4 — Gap C: C10–C16 are missing everywhere

These are **not in `bakeoff.py`**. They are scored offline by
`experiments/tabbing/probes/score_new.py` (C10–C13) and `score_new2.py`
(C14–C16) from four saved probe files: `containment.json`, `composite.json`,
`effect.json`, `effect2.json`.

All four `probe_*.py` scripts accept a `PROBE_CORPUS` env var (three always did;
`probe_effect2.py` was ported and verified). So the pipeline can run per corpus
— it just never has for gds, ma11y, or edgecases.

Run the probes and both scorers for each corpus where it is possible, and merge
C10–C16 into the matrix. Where a corpus cannot support them, say why.

**Known scope caveat — carry both numbers.** The published C16 = 100% precision
came from observing **42 of 95 probes** (the C12 lead set, `probes/c12.json`).
Observing all 95 gives **38 TP / 11 FP = 77.6%**. Both must appear, each
labelled with which lead set was observed. Do not silently pick one.

**Control:** fixtures C10–C16 under the `c12.json` filter must reproduce
`CHEAP_DETECTOR_REVIEW.md` exactly — C13 37/4/1 at 90.2%, C15 37/0/1 at 100%,
C16 38/0/0 at 100%.

## Deliverables

1. Updated `tools/assemble_matrix.py` emitting every column with no
   unexplained blanks.
2. Whatever new tool Task 4 needs (suggest `tools/run_probe_rules.py`).
3. A fix for the edgecases CDP failure, or a written explanation of why it
   cannot be fixed without touching frozen code.
4. Regenerated `MATRIX-RESULTS.md` with all four gaps closed.
5. `GAP-CLOSURE-REPORT.md` recording, for each of the four gaps: what you
   found, what you changed, which control you ran, and what its output was.
   Lead with anything that failed or that you could not close.

## Verification you must run before reporting done

- `git diff --stat src/audit/` → must be empty.
- Fixtures rows diffed against **both** `detector-matrix.results.md` and
  `CHEAP_DETECTOR_REVIEW.md`.
- A scan of the final table asserting no cell is blank without a reason string.

Report honestly. A gap you could not close, reported clearly, is worth more than
a table with no blanks and a number nobody can trace.
