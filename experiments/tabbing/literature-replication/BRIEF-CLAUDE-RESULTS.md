# Brief: write RESULTS.md for the completed scored run

For Claude Code. Working directory
`experiments/tabbing/literature-replication/`. **Do not commit. Do not edit
anything under `src/audit/`. Do not re-run the experiment** — it is finished and
took roughly three hours; your job is to report it, not repeat it.

**If any premise here turns out to be wrong, stop and report that instead of
working around it.** Your last premise challenge was correct and changed the
experiment.

## What ran

`tools/kafe_scored_run.py` replayed all 53 replayable KAFE subjects and ran the
**frozen** Axcess detectors — `DifferentialRunner`, `TrialConfig` and
`collect_candidates` imported unmodified from `audit.analyzer.keyboard.kbdiff`
— against every addressable candidate. Unbounded: no candidate cap. 5,922
probes, 7,255 s of probe time.

## Your inputs

- `derived/kafe_scored.jsonl` — one record per subject, the raw result.
- `derived/scored_summary.json` — recomputed aggregates.
- `tools/analyze_scored.py` — run it yourself to reproduce every number.
- `derived/kafe_denominator.json` — the matched-subset reference.
- `PREREGISTRATION-SCORED.md` — your own predictions, written before the run.
- `TIMING-AND-SPOTCHECK.md`, `PREMISE-CORRECTION.md` — context you must not
  contradict.

## Verified results — do not re-derive, but do reproduce

| | TP | FP | FN | TN | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- |
| Axcess frozen detectors | 23 | 12 | 3 | 7 | **23/35 = 0.657** | **23/26 = 0.885** |
| KAFE, same 45 subjects | 26 | 1 | 0 | 18 | **26/27 = 0.963** | **26/26 = 1.000** |

45 scored, **8 abstained**, 53 planned. Abstentions are 5 positive / 3 negative
and are **not** counted as negatives.

**The abstention cause is established, so do not speculate about it.** All 8 are
tab walks that never cycle back to their start element. This was tested on
`spotify`: at cap 212 the walk finds 0 stops and caps; at cap **2000** it finds
0 stops and still caps. It is a page property, not a budget I set too low.
Raising the cap does not fix it. The detector abstains rather than guessing,
which is correct behaviour.

Timing, against Harry's **300 ms per-button cap**: median of per-subject medians
is **518 ms**; only **10 of 40** subjects have a median within the cap. Worst
observed subject medians exceed 3,500 ms. The cap is a ceiling the detector must
not exceed, **not** a number to report as a win, and it is currently missed.

For scale only, recomputed from KAFE's own artifact: its Detection phase
averages **995 ms per subject page**. That is per-page and is **not** comparable
to our per-probe figures. The published 19.22 min is proxy/crawl/extract
infrastructure, not detection. Do not build a speed comparison out of these.

## What RESULTS.md must contain

1. **Headline table**: Axcess vs KAFE on the common set, exact fractions and
   decimals, with the denominators visible.
2. **Abstentions**: all 8 named, with the established cause and the falsification
   test above. Report them with their own denominator and as a pessimistic
   sensitivity (positive abstention = miss, negative = false alarm).
3. **Timing**: per-probe distribution against the 300 ms cap, stated as a breach.
4. **Per-subject table** from the raw JSONL: y, yhat, probes, reported, median ms.
5. **Your predictions, scored.** You registered P-B (recall) as the one you
   expected to fail. Say plainly whether it did. Lead with what was falsified.
6. **Limits that no number here clears**, at minimum: Chromium-only (Firefox 68
   unavailable, permanent); the exclusion is label-correlated, so this is **not**
   a result on KAFE's corpus; 12 false positives are unadjudicated — no human has
   confirmed whether any is a true finding KAFE missed; single run, no repeats.
7. **Verified / claimed / assumed**, kept separate.

Be blunt about the comparison. Axcess has **lower precision and lower recall**
than KAFE on the same subjects. Do not soften that, do not bury it below the
abstention discussion, and do not lead with the 300 ms analysis to avoid it.

Write to `RESULTS.md`. Cite the raw file for every number so the manager can
recompute it.
