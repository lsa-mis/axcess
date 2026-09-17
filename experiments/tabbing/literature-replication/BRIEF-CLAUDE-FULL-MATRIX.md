# Brief: run the FULL detector matrix on KAFE, not one configuration

For Claude Code. Working directory `experiments/tabbing/literature-replication/`.
**Do not commit. Do not edit anything under `src/audit/`.**

**If any premise here is wrong or impossible, stop and report that instead of
working around it.** Your last two premise challenges were both correct.

## The defect this fixes

`RESULTS.md` reports a single row called "the frozen Axcess detectors". That row
is **one configuration of D9** — a default `TrialConfig` on `DifferentialRunner`.
Harry has 10-20 detectors and combination rules. The report presented one of
them as if it were the whole system. That is a manager error (mine), not yours.

The real detector suite, from
`experiments/tabbing/results/detector-matrix.results.md` and
`experiments/tabbing/runner/bakeoff.py`:

- **Cheap generators**: D0, D2, D2b, D3, D4, D5, D6, D7, D8, plus D1/D1x axe-core
- **Differential arms**: D9, D9-noS4, D9+S4u, D9+S4ours, D9u, D9u+S4u
- **Coverage arms**: D10a, D10b, D10a-u, D10b-u, D10a+base
- **Combination rules**: C1-C16, built from rules R1, R2, R3, R5, R6, R7, R8, R9

`bakeoff.py` already runs this entire matrix and scores it. It is the harness
that should have been used.

## The structural problem you must solve

`bakeoff.py` takes a corpus of static pages plus a `truth.json` carrying
**element-level** labels (95 probes: `violation` / `ok` / `decoy` / `excluded`),
and the cheap detectors' `_SURVEY_JS` only sees elements carrying `data-probe`.

KAFE gives neither. Its subjects are mitmproxy captures replayed through
`tools/replay.py`, and its labels are **page-level** only (page has >=1 IAF, or
does not). There is no element-level ground truth for KAFE subjects and **you
must not invent one** — no heuristic labelling, no "probably a violation".

So the two are not directly compatible. Your job is to find the honest bridge.
Options, and you may propose better:

- **(a)** Run the full matrix per subject, project each detector's element
  output up to a page verdict (page-positive iff >=1 element reported), and
  score every detector against the page-level label. Element-level precision is
  then **not estimable** and must be reported as such.
- **(b)** Run the matrix only on the corpora that *do* have element labels
  (`fixtures`, `edgecases`) to get the per-detector table, and report KAFE
  separately at page level. Two tables, neither pretending to be the other.
- **(c)** Both.

State which you chose and why. **Do not** report an element-level precision
figure for KAFE that no element-level truth supports.

## Inputs

- `tools/kafe_scored_run.py` — how to replay a subject and apply the neutral
  census so detectors can address elements. Reuse this; it works.
- `tools/analyze_scored.py` — recompute pattern.
- `derived/kafe_denominator.json` — 53 subjects, page labels, matched reference.
- `derived/kafe_scored.jsonl` — the completed single-config run.
- `experiments/tabbing/runner/bakeoff.py` — the full matrix harness.
- `experiments/tabbing/results/detector-matrix.results.md` — the existing
  per-detector table on the synthetic corpora. **This is your format target.**

## Verified facts — do not re-derive

- 53 KAFE subjects replay; 45 scored and 8 abstained in the single-config run.
- **7 of 8 abstentions are genuine** (tab walks that never cycle; identical stop
  counts at 10-20x cap, tested in `derived/abstention_probe.json`).
  **`capitalone` was a budget limit** and should have scored — `TAB_HEADROOM=200`
  was too small. Fix that for this run.
- KAFE's reference on the matched set: **TP=26 FP=1 FN=0 TN=18, precision 26/27,
  recall 26/26.** Not the published 36/39.
- Single-config D9 result: precision 23/35, recall 23/26, median 518 ms/probe.
- Environment: Python 3.14.7, Playwright 1.58.0, Chromium 145.0.7632.6, offline.

## Required output

A table with **one row per detector and per combination rule**, in the format of
`detector-matrix.results.md`: TP, FP, FN, unknown, precision, recall, F1, and
**ms per target**. Every detector that exists gets a row, including any not in
that file. A detector that cannot run on KAFE captures gets a row saying so and
why — an empty row with a reason beats a missing row.

Then the comparison table: every detector against KAFE's 26/27 and 26/26 on the
same subjects, plus against the GDS reference (all 13 audited tools score 0/6).

Write to `RESULTS-MATRIX.md`. Keep `RESULTS.md` but add a note at its top that
it covers one configuration only and points to the new file.

## Constraints

- Detectors and `score.py` stay **frozen**. Import, never edit.
- Cost: the single-config run took ~3 hours for 5,922 probes. The full matrix is
  far larger. **Bound it**: run the cheap generators (D0-D8) on all 53 first —
  they are fast — then the expensive differential arms on a pre-registered
  subset if the full set will not finish. State the subset and why. Append
  per-subject results to a JSONL as you go so nothing is lost.
- Pre-register predictions before running.
- Abstentions are never negatives.
- Report per-probe ms against the **300 ms cap** Harry set.
- Separate verified / claimed / assumed.
