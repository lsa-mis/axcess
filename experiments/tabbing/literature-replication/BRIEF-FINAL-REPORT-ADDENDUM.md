# Addendum to BRIEF-FINAL-REPORT.md — answers to your three questions, and one change

Your premise check was right on every point. The manager checked each claim
against the artifacts before answering; results below.

## Your three questions — all confirmed, with one condition

1. **Finding 3.** Confirmed: C9 → C10 goes 21/15/0/0 → 19/8/2/7, so R1 does the
   most work of any rule; C13 = C14, so R6 does nothing. Use your wording
   ("R2, R3, R6, R9 no effect; R1, R5, R7/R8 change the result").
2. **Finding 2.** Confirmed: 30 of 48 faster than KAFE's 25.7 ms, 28 of 46 with
   defined precision (D7 and U-D7 undefined). "29 of 46" was a manager typo that
   was never computed.
3. **Denominator.** Confirmed, and the missing reason is now known — see below.

**Condition:** craigslist is being scored now (next section), so every count
above will be recomputed. Do not type the numbers in this addendum into the
report. Recompute every figure from the regenerated artifacts.

## Update (20:30): write the report now; craigslist runs alongside

The CEO's decision: **write `FINAL-REPORT.md` now**, and rerun `craigslist` in
parallel. If it succeeds, you will be asked afterwards to update the tables.

What happened to the earlier attempts, so the report can state it: `craigslist`
has now failed three times without a result. The first run hung overnight. The
second was killed by the manager at 16:44. The third was killed at 16:56 when
the Hermes backend restarted. The fourth attempt runs as a host-side
`systemd-run --user` unit (`kafe-craigslist`), so a Hermes restart can't kill
it. It only **appends** one line to `derived/kafe_matrix.jsonl` when it
finishes. It does not rewrite any report.

Rules for you while it runs:

- Before you regenerate anything, check that `derived/kafe_matrix.jsonl` has
  exactly 52 lines and the first 52 hash to `35d6de9c7da4a1c1`. Report the
  line count you regenerated from.
- If it already has 53 lines when you start, include craigslist and say so.
- If it goes from 52 to 53 lines **after** you regenerated, don't try to merge
  it yourself. Finish the 39-subject version and say plainly in your final
  message that a craigslist result arrived after you regenerated.
- In the report, list craigslist as **not scored** and give the reason: three
  attempts lost to a hang, a manual kill and a backend restart. Don't call it
  an abstention; it was never measured.

The rest of this addendum still applies, except where it says to wait for
craigslist.

## What changed: craigslist is being scored

`craigslist` (KAFE label TRUE, 898 candidates, capture present) was never
attempted. That was the manager's mistake: after the overnight hang the
restart loop covered only `dmv_fl`, `4shared` and `usgsgov`, and craigslist was
most likely the subject that hung. The CEO asked for every subject to be run.

The manager is running the **unchanged** runner as a Hermes background job:
`tools.kafe_matrix run --only craigslist`, with a 4-hour cap. It appends one
line to `derived/kafe_matrix.jsonl`. The first 52 lines have sha256 prefix
`35d6de9c7da4a1c1` and must not change.

The scoring code has changed since the other 52 subjects were scored, in two
places inside `measure_subject`. The manager read both diffs: the discovery JS
and the focusable query were moved into constants (`DISCOVERY_TAG_JS`,
`FOCUSABLE_JS`) byte-for-byte, and no logic changed. **Confirm this yourself**
before trusting that craigslist and the other 52 were measured the same way.

## Your task, once the manager hands this over (craigslist finished or timed out)

1. Check that the first 52 JSONL lines still hash to `35d6de9c7da4a1c1`.
2. Regenerate `KAFE-MATRIX.md`, the summary and the controls from the JSONL
   (`controls`, then `assemble`/`report`), so the table covers whatever
   craigslist produced. If it capped or timed out, it becomes a named
   abstention with its reason, not a silent gap.
3. Correct the manager-written errors you found. You now own these edits:
   - `KAFE-HIGHLIGHTS.md`: the R1/R6 claim, the "29 of 46" count, and the
     KAFE-corpus "recall" labelled or compared as if it were strict recall.
   - `MATRIX-RESULTS.md`: the ma11y note says C9 has "3 abstentions"; the row
     shows 1.
   - `KAFE-MATRIX-REPORT.md` §1.3: use the 5-run capdiag record from
     `CAPDIAG-REPORT.md`, including spotify capping in 2 of 5 runs.
   - The claim in `KAFE-MATRIX.md` that "both ms columns are computed the same
     way on both sides" is false. Correct it in the generator, not by editing
     the output by hand.
4. Write `FINAL-REPORT.md` as the original brief specifies. Carry the
   non-blocking handling you proposed: say plainly that KAFE-corpus recall is
   not strict recall and why strict recall and the unknown counts can't be
   computed there; give all three fixture rows for C15/C16; give the 5-run
   capdiag verdict; and describe our ms/button as harness time divided by
   candidates, not latency measured per button.

## Boundaries (unchanged)

No edits under `src/audit/`. No commit. Do not re-run any subject other than
the craigslist result already on disk, and do not re-run detectors. If
anything here turns out to be wrong, stop and report.
