# Brief — fix `capdiag`, then diagnose the 7 capped KAFE subjects

Working directory:
`/var/home/me/Development/axcess/experiments/tabbing/literature-replication`

## Objective

`KAFE-MATRIX-REPORT.md` §1.3 lists 7 subjects whose tab walk hit its budget and
were scored as abstentions. Whether those are genuine focus traps or merely
tight budgets is still unknown, and it is the last open item in the KAFE work.

`tools/kafe_matrix.py capdiag` exists to answer that. It ran to completion and
produced `derived/kafe_matrix_capdiag.json`, but the result is not usable:

```
every one of the 7 subjects:  presses_at_ceiling=4000,
                              still_capped_at_ceiling=true,
                              distinct_stops=0
```

`distinct_stops: 0` means the walk recorded no focus stop at all — including on
`cnn`, which has 283 focusable elements. A page with 283 focusable elements that
yields zero focus stops is an instrument failure, not a finding. Seven identical
verdicts across seven unrelated sites is the same signal.

**Suspected cause, stated as a hypothesis and not as fact:** `cap_diagnosis()`
calls `compute_tab_order(page, max_tabs=ceiling)` directly after `page.goto()`,
without whatever focus initialisation the scored path performs before it walks.
If focus is still outside the document, every Tab press does nothing observable
and the walk caps by construction. Confirm or refute this against the scored
path before changing anything — if the real cause is different, fix the real one
and say so.

## What to do

1. Diagnose why `capdiag` records zero focus stops. Compare `cap_diagnosis()`
   against the scored run's traversal setup in the same file.
2. Fix it so the diagnostic walks the page the same way the scored run does.
   Changing `cap_diagnosis()` is in scope. Changing the scored path, the
   detectors, or anything that would alter already-published matrix numbers is
   **not** — if the fix seems to require that, stop and report instead.
3. Re-run `capdiag` and overwrite `derived/kafe_matrix_capdiag.json`.
4. Update `KAFE-MATRIX-REPORT.md` §1.3: replace the `not diagnosed: capdiag did
   not run` line with the per-subject outcome, and state the ceiling used.

## Control — required, and it must be able to fail

Before trusting the re-run, show the instrument can produce **both** outcomes:

- Take one subject that scored normally in the matrix (not capped) and run the
  same diagnostic path against it with a deliberately tiny ceiling. It must come
  back capped.
- Run that same subject at the 4000 ceiling. It must come back **terminating**,
  with `distinct_stops > 0`.

A diagnostic that reports "capped" for every input is the bug you are fixing;
it must not survive the fix. Put both control outputs in your report.

If after the fix all 7 genuinely still cap with `distinct_stops > 0`, that is a
real and interesting result — report it as such. Do not tune the ceiling until
the subjects produce a preferred answer.

## Boundaries

- Do not edit anything under `src/audit/`. Those detectors are frozen.
- Do not change scored-run behaviour, detector logic, or any number already
  published in `KAFE-MATRIX.md`.
- Do not commit. The manager commits after verification.
- Do not re-run the full matrix; `derived/kafe_matrix.jsonl` (52 subjects) is
  finished and must not be regenerated or truncated.
- Keep chromium cleanup between subjects; earlier runs orphaned browsers.

## Output

Write `CAPDIAG-REPORT.md` leading with anything that failed, could not be
verified, or contradicted the suspected cause above. Include the two control
outputs and the final per-subject table.

If any premise in this brief turns out to be wrong or impossible, stop and
report that instead of working around it.
