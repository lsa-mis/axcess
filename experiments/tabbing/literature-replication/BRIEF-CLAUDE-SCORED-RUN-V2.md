# Brief v2: run the scored experiment with the frozen detectors

For Claude Code. Supersedes `BRIEF-CLAUDE-SCORED-RUN.md`. Working directory is
`experiments/tabbing/literature-replication/`. **Do not commit.**

**If any premise here turns out to be wrong or impossible, stop and report that
instead of working around it.** Your last checkpoint did exactly this and it was
correct — the premise you challenged was wrong and has been fixed below.

---

## What changed since your checkpoint

Your three blockers are resolved:

1. **Python execution is granted** for `uv run --offline --no-sync python ...`
   in this directory. Offline, no installs.
2. **`src/` is now in your allowed directories.** Read and import freely;
   **do not edit** anything under `src/audit/`.
3. **Your premise challenge was right and is accepted.** No arm had run the
   frozen detectors. Reading **(a) is chosen**: import the frozen detectors.
   `tools/frozen_detector_probe.py` shows the working import and call pattern.

Your `tools/kafe_denominator.py` had one defect: records are built with key
`kafe_yhat` but `matrix()` read `yhat` (`KeyError` on every run). Fixed. With
that fix **both your controls pass and every number you derived by hand is
confirmed** — P1 reproduces TP=36 FP=3 FN=0 TN=21, P2 accounts for all
exclusions, 53 subjects at 31 positive / 22 negative, KAFE's matched-subset
reference TP=31 FP=2 FN=0 TN=20, precision 31/33, recall 31/31. Your `dmv_wc`
self-correction was right. `derived/kafe_denominator.json` now exists.

## The finding that shapes this run

Running the frozen detectors on the GDS fake button returned **`no_lead`, not
`violation`** — where the reimplementation claimed a violation.

Cause, measured: the GDS page has **306 focusable elements against the 300-press
default tab cap**. `TabOrder.capped` was true, so `reachability_is_certain()`
returned false and the detector correctly refused to call an unproven absence a
failure. At cap 1200 the walk completes and unreachability becomes certain.

| Tab cap | Focusable | `capped` | reachability certain |
| --- | --- | --- | --- |
| 300 | 306 | true | **false** |
| 1200 | 306 | false | **true** |

**Consequence you must honour:** the tab cap is a pre-registered per-subject
parameter, not a default to inherit. Set it from each subject's own
focusable-element count with headroom, record the count and the cap, and treat
any still-capped walk as an **abstention**, never as a negative. craigslist has
1540 elements. A capped walk silently scored as "no violation" would understate
recall across the whole corpus.

## Objective

Produce the first real numbers: **precision, recall, and per-button milliseconds
for the frozen Axcess detectors**, on both corpora, against the published
references.

### Deliverable A — GDS re-run through the frozen detectors

`tools/gds_run.py` is a reimplementation; its 6/6 is retracted. Write a new
runner that imports `DifferentialRunner`, `TrialConfig` and `collect_candidates`
from `audit.analyzer.keyboard.kbdiff` and scores the same 8 cases (6 IAF
positives + 2 negative controls, listed in `gds_run.py`). Set the tab cap from
the page's focusable count. Report the confusion matrix and per-case ms.

Reference to beat: **all 13 audited tools score 0/6** on these 6 cases
(`tests.json` in the GDS repo, `results` field per case).

### Deliverable B — KAFE scored run, 53 subjects

Replay each subject with `tools/replay.py`, run the frozen detectors, project
element outputs to KAFE's page-level unit (page positive iff >=1 element
reported), and compare against the matched-subset reference in
`derived/kafe_denominator.json`.

Reference to beat, **on the same 53**: TP=31 FP=2 FN=0 TN=20,
**precision 31/33, recall 31/31**. Not 36/39 — that is a different retained
subset and §6.6 forbids comparing across subsets.

## Compute budget and checkpointing

The differential costs roughly a second per probe and the corpus is large, so
**scope before scaling**:

1. Smoke-test on **2 subjects** first (one positive, one negative). Write the
   results file. Confirm the pipeline end to end.
2. Then run the remaining 51, **appending each subject's result to
   `derived/kafe_scored.jsonl` as it completes**. A partial file of 30 subjects
   is worth far more than a transcript of 53.
3. If a per-subject budget is needed to finish, pre-register it (candidate cap,
   key set, timeout) and record it in the manifest. A stated bound is fine; an
   undisclosed one is not.

Target wall clock: under 90 minutes total. If you will exceed it, write what you
have and report.

## Non-negotiables

- **Pre-register before running.** Write predictions and falsification criteria
  to a file *first*. You already drafted H1 / P-A / P-B / P-C in §6.7 — lift
  them. You registered P-B (recall) as the one you expect to fail; keep that.
- **Negative controls in every run.** Without them a harness that reports
  everything scores perfect recall. §6.2 requires three layers.
- **Abstentions are not negatives.** Capped walks, `Verdict.UNKNOWN`,
  partial-read captures (`godaddy` is one — the census flags it), and replay
  failures all abstain. Report them separately with denominators.
- **Per-button timing.** 300 ms is a cap the detector must not exceed, not a
  number to report as a win. Record ms per actuation trial; report the
  distribution and any breach.
- Detectors and `score.py` stay frozen. No commits, no network, no installs.
- Keep every raw run including failures.

## Output

- `PREREGISTRATION-SCORED.md` — written before execution.
- `derived/gds_frozen.json`, `derived/kafe_scored.jsonl` — raw, appended live.
- `RESULTS.md` — one table per corpus: TP/FP/FN/TN, precision and recall as
  exact fractions, abstention counts with denominators, per-button ms
  distribution, and the side-by-side against the published reference.
- Separate **verified** (you ran it) from **claimed** (a doc says so) from
  **assumed**. The manager will recompute your headline numbers from the raw
  files, so do not report a number the raw output cannot reproduce.

## Boundaries

- Do not review your own §6 rewrite; Codex does that independently.
- R6 (brotli fidelity) and R5 (request bodies) are not yours.
- Arm 2 (Ma11y) is a separate workstream — not this task.
- Write only inside `experiments/tabbing/literature-replication/`.
