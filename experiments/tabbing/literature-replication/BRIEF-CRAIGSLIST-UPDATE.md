# Brief — add craigslist: regenerate the KAFE tables on 40 subjects

Working directory:
`/var/home/me/Development/axcess/experiments/tabbing/literature-replication`

## What changed

`craigslist` has been scored. `derived/kafe_matrix.jsonl` now has **53 lines**;
the first 52 still hash to `35d6de9c7da4a1c1` (sha256 prefix of `head -52`).
Line 53 is craigslist: status `scored`, KAFE label TRUE, 898 candidates,
48 detector verdicts (36 positive, 12 negative, 0 abstain), 5,351.6 s.

So the scored set is now **40 subjects (25 positive, 15 negative)**, unless your
controls say otherwise; if they do, stop and report.

## What to do

1. Check the hash and line count above before anything else.
2. Regenerate, each command on its own, exactly:

       uv run --offline --no-sync python -B -m tools.kafe_matrix controls
       uv run --offline --no-sync python -B -m tools.kafe_matrix assemble
       uv run --offline --no-sync python -B -m tools.kafe_matrix report
       uv run --offline --no-sync python -m pytest tests/test_capdiag.py -q

3. Confirm KAFE's reference row is recomputed on the 40, from the CSV labels and
   verdicts and from the per-subject logs in `artifacts/kafe_output/craigslist/`
   (already downloaded), not carried over from the 39.
4. Update every figure in `FINAL-REPORT.md` and `KAFE-HIGHLIGHTS.md` that
   depends on the scored set: counts, precision, strict and decided recall, F1,
   the KAFE cost figures, "N of M" claims, the denominator chain (craigslist
   moves from "not scored" to scored; the chain becomes 60 → 7 → 53 → 53
   attempted → 13 abstained → 40), and §8.4. Any finding whose conclusion
   changes, such as which detector has the best F1, must say so plainly. Don't
   quietly keep the old wording.
5. List every KAFE-table cell that changed, old → new, in your final message.
   Changes should be confined to what one extra positive subject can move.
   **Nothing in the four non-KAFE corpora may change.**

## Progress survives a crash

Append one line per step to `CRAIGSLIST-UPDATE-PROGRESS.md`; resume from its last
line if it exists.

## Boundaries

No edits under `src/audit/`. Don't run `run` or `capdiag`, or any detector.
Don't write to `derived/kafe_matrix.jsonl`. Don't commit. If a premise here is
wrong, stop and report it instead of working around it.
