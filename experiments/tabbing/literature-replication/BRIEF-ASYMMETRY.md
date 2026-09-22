# Brief — document the one-way comparison as a stated limitation

Working directory:
`/var/home/me/Development/axcess/experiments/tabbing/literature-replication`

## Background — a decision already made

The CEO was asked whether to close the reverse direction of the comparison by
rebuilding KAFE's Java/Selenium/Firefox-68 stack and running their detector
against our own corpora (fixtures, gds, ma11y). **The answer was no.** The
one-way comparison stands, and the asymmetry is to be documented as an explicit
limitation rather than closed.

Your job is to write that limitation into the reports. Do not attempt to
rebuild KAFE, do not add a KAFE row to the four non-KAFE corpora, and do not
propose doing so as future work framed as a deficiency to be fixed — it is a
deliberate scope decision.

## The facts to document, already verified

1. **The comparison runs in one direction only.** All 48 Axcess detector rows
   were scored on KAFE's own 60-subject corpus. KAFE's detector was never scored
   on our fixtures / gds / ma11y corpora.
2. **KAFE's row is their published output, not a local execution.** It comes
   from `artifacts/kafe_results_to_reproduce.csv`, which is their tool's real
   output on their corpus and reconciles with their paper's Table 1
   (TP 36, FP 3, FN 0, TN 21 over n=60 — 92.3% / 100.0%). Their Java / Selenium
   3.141.5 / Firefox 68 stack was not rebuilt here.
3. **A unit mismatch blocks the reverse direction independently of the above.**
   KAFE emits page-level labels; our fixtures/gds/ma11y truth is element-level.
   Even with their binary running, scoring it against our corpora would require
   inventing a projection between two different units of truth, and that
   projection would itself decide the result.
4. **The asymmetry is not neutral, and the writeup must say which way it cuts.**
   Measuring our detectors on their corpus is the harder and more honest
   direction, but it means nothing in this work independently validates our own
   corpora. `edgecases` is shared-author and already carries no unbiased
   accuracy claim; `fixtures` is authored here too.

## What to do

Add the limitation to both reports, in the voice and structure each already
uses. Do not duplicate one long passage into both — each should say what its
own reader needs:

- `KAFE-MATRIX-REPORT.md` — add to the existing "What I could not close"
  section (§1). This is the natural home; match the numbering and prose style
  of the entries already there.
- `MATRIX-RESULTS.md` — it already states that KAFE's corpus is not scored in
  its tables. Extend that existing note so it also says the converse: KAFE's
  detector is not scored on these four corpora, and why.

Keep it proportionate — this is a scope boundary being stated plainly, not an
essay. No new tables, no new numbers, nothing recomputed.

## Boundaries

- Do not edit anything under `src/audit/`.
- Do not change any published number, table, or score in either report.
- Do not re-run the matrix, the probes, or any detector. This task is
  documentation only; no experiment should execute.
- Do not commit. The manager commits after verification.
- `KAFE-MATRIX-REPORT.md` §1.3 may have just been updated by the capdiag task.
  Read the current file before editing and preserve that content.

## Output

Report what you changed, quoting the added passages. If either report already
states this limitation adequately, say so and leave it alone rather than
padding it.

If any premise in this brief turns out to be wrong or impossible, stop and
report that instead of working around it.
