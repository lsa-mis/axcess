# Brief: §6 rewrite and the 53-subject scored run

For Claude Code. Written by Opus 5 (manager). Working directory is
`experiments/tabbing/literature-replication/` in the `axcess` repo, branch
`tabbing`. Everything is untracked; **do not commit**.

**If any premise in this brief turns out to be wrong or impossible, stop and
report that instead of working around it.**

---

## Objective

Produce a defensible answer to: *do the frozen Axcess keyboard/mouse
differential detectors do better than KAFE's published detectors, measured on
KAFE's own subjects?*

Two deliverables, in order. The second must not start until the first is
reviewed.

1. **Rewrite `FEASIBILITY.md` §6.** Its current target hypothesis is falsified
   (see below) and its denominator assumes three subjects when 53 are now on
   disk.
2. **Execute the scored run** on the 53 replayable subjects, producing raw
   per-subject outputs and a confusion matrix.

## Verified facts — do not re-derive these

Each was confirmed by running it this session. Re-deriving them wastes budget.

- **55/60 KAFE subjects are on disk** under `artifacts/subjects/*.bin`, 82 MB,
  zero download errors, all hashes unique. 5 are folder-form and absent
  (`battlenet`, `canon`, `dmv_wc`, `gizmodo`, `speedway`); those are expanded
  asset directories on Drive, not flow dumps.
- **53/55 are replayable.** `tools/kafe_corpus_census.py` parses all 55:
  3,178 flows, 3,164 exchanges, 53 with an HTML entry document.
  `4shared` and `dmv_fl` have a corrupted length prefix on record 0. A magic
  scan recovers 52/74 and 15/30 exchanges respectively, but **neither yields an
  entry document**, so both are excluded. Do not spend time on them.
- **KAFE's per-subject reference results** are in
  `artifacts/kafe_results_to_reproduce.csv`. Full-corpus recompute:
  TP=36 FP=3 FN=0 TN=21, reproducing the published 92.3%/100% exactly.
- **KAFE's 3 IAF false positives are `bowiestate`, `dell`, `dmv_wc`.** Only
  `bowiestate` and `dell` are in the replayable 53; `dmv_wc` is folder-form.
- **The timing columns are milliseconds.** Summing the 7 detection phases gives
  a 19.12 min mean against the paper's published 19.22 (0.54% error). That total
  is proxy/crawl infrastructure. KAFE's **Detection phase alone averages
  995 ms**, and 8/60 subjects already finish under 300 ms.
- Environment: Python 3.14.7, Playwright 1.58.0, Chromium 145.0.7632.6, offline.
  Always `uv run --offline --no-sync ...`. Firefox/WebKit are absent, so the
  historical Firefox 68 condition cannot be reproduced — permanent caveat.
- Repository suite: `uv run pytest tests/unit` — 849 passed. Experiment suite:
  87 passed.
- `kbdiff` lives at `src/audit/analyzer/keyboard/kbdiff/` (an earlier handover
  gave a wrong path).

## The falsified target, and why §6 needs rewriting

`FEASIBILITY.md` §6.7 currently sets the target as "equal recall with higher
precision." Recomputed from KAFE's own CSV, on the three originally authorized
subjects KAFE scores **precision 1.0, recall 1.0** — so that comparison could
only tie or lose. The target is unreachable there and is withdrawn.

With 53 subjects the denominator changes and `bowiestate`/`dell` give precision
room to differ. §6 must be rewritten against the real denominator. Preserve
everything in the existing §6 that is still sound — the exclusive outcome
buckets, abstention precedence, page-vs-element separation, undefined-denominator
rule, repeat aggregation. The parts that need work are scope, denominator, and
the target hypothesis.

Harry's constraint, to record in §6: **300 ms is a per-button cap the detector
must not exceed, not a number to report as a win.** Measure and report whether
the cap holds per button; do not build a "faster than KAFE" headline. A prior
figure of 33.6 ms for 15 Tab presses measured the wrong unit and is retracted.

## Constraints

- **Detectors stay frozen.** Do not edit anything under
  `src/audit/analyzer/keyboard/kbdiff/` or `score.py`. If a detector defect
  blocks the run, report it as a separate finding.
- **No commits, no network, no installs, no crawls, no nested agents, no
  permission-bypass flags, no sudo.**
- Artifacts under `artifacts/` are third-party captures with **no licence**.
  Local inspection only. Never commit, publish, or redistribute those bytes.
  `artifacts/` is gitignored — keep it that way.
- Keep every raw run including failures. A re-run goes beside the original; the
  original is never discarded.
- Pre-register predictions and falsification criteria **before** executing the
  scored run, in a file, not in your head. A prediction that cannot fail is not
  a prediction.
- Report nulls and falsifications first, not buried.

## Method notes from arm 1, which cost five defects to learn

The GDS arm (`tools/gds_run.py`) is a working reference for the same
measurement on a different corpus. Five harness defects were found there, each
by a **negative control reading impossibly**, not by inspection. They will
recur here if the same care is not taken:

1. `element.click()` synthesises `detail === 0` and bypasses hit-testing. Use
   trusted pointer input at real coordinates.
2. Enter on a link commits a navigation that destroys in-page counters.
3. Keyboard and mouse trials contaminate each other (`window.open` detached the
   page). Give each modality its own fresh context.
4. Force-revealing hidden scopes makes `display:none` elements look
   Tab-reachable. Read reachability in the page's natural state.
5. Requiring Space of a plain link reports every link on the web. Expected keys
   are role-dependent.

**Include negative controls in the scored run.** Without them a harness that
flags everything scores perfect recall and looks correct.

## Output format

- `FEASIBILITY.md` §6, rewritten in place, superseding the current text.
- A pre-registration file for the scored run.
- Raw per-subject outputs under `derived/`.
- A short report: confusion matrix with denominators, abstention counts,
  per-button timing against the 300 ms cap, coverage (`|E|/|L|`), and what is
  verified vs claimed vs assumed.
- Do not report a summary table of "verified" rows without the artifacts behind
  them; the manager will re-run your numbers from the raw output.

## Boundaries

- The §6 rewrite is yours. **Do not also review it** — Codex reviews it
  independently afterwards.
- R6 (brotli fidelity) is unresolved and is **not** yours to solve or waive.
- R5 (request matching ignores bodies) is deferred until interactive subjects.
- Arm 2 (Ma11y mutation analysis) is a separate workstream. Puppeteer 25.11.0 is
  installed at `arm2/node_modules`. **Not your task.**
- Write only inside `experiments/tabbing/literature-replication/`. Name the tool
  that performs each write; no shell redirects outside that path.

Write partial artifacts at checkpoints. If you run out of turns mid-run, a
written partial result is worth far more than a transcript.
