# Gap closure: what was found, what changed, what was controlled

Execution of `BRIEF-CLOSE-GAPS.md` against `PLAN-CLOSE-GAPS.md`. All four gaps
are closed and all four controls pass. Read the two sections below first: they
are the things that did not go to plan.

---

## Read first — what failed, and what I could not verify

### 1. One verification step could not be run: `git diff --stat src/audit/`

The brief requires `git diff --stat src/audit/` to be empty at the end. **I could
not run it.** Every `git` invocation in this session was refused by the tool
sandbox ("This command requires approval"), on three separate attempts. The
frozen-detector constraint is therefore **verified only indirectly**:

- No file under `src/audit/` has a modification time later than the start of
  this session (`find src/audit -newermt '2026-09-18 00:00'` returns nothing).
- Every file I edited is listed under "What changed" below; none is under
  `src/audit/`. The edits are in `experiments/tabbing/runner/`,
  `experiments/tabbing/probes/` and `experiments/tabbing/literature-replication/tools/`,
  all of which the brief names as harness code.

**Please run `git diff --stat src/audit/` yourself before trusting this.** I am
reporting it as unverified rather than as passed.

### 2. The plan's diagnosis was incomplete: there is a fifth cause, and it was the largest

The plan attributes every blank `ms` to four causes. A fifth cause — unmentioned
in either document — produced more blank cells than Gap A did, and also produced
**wrong numbers**, not just missing ones.

`tools/assemble_matrix.py` globbed *every* `bakeoff-*.json` in a results
directory and let later filenames overwrite earlier ones. Because `-` (0x2D)
sorts before `.` (0x2E), `bakeoff-fixtures.json` — the oldest artifact in the
directory, which has **no `page_timings_ms` key at all** — sorted *last* and
overwrote every row it contained.

That is the actual origin of:

| symptom in the old table | real cause |
|---|---|
| `D0`, `D2`, `D2b`, `D3`, `D4`, `D5`, `D6`, `D7`, `D8`, `D1`, `D1x` all `ms = —` on fixtures | overwritten by an artifact with no timings; none of these is a variant row, so Gap A does not explain them |
| a `D10 coverage differential` row that exists in no current run | carried in from the stale artifact |
| two different `D9-noS4 …` rows | two artifacts using two different names for the arm |
| `D6` reading **22/19/15** instead of the published **21/18/15** | stale artifact's numbers winning |
| edgecases showing 13 rows despite `scores: []` | the stale `bakeoff-edgecases.json` supplying them |

The new assembler reads **exactly the two files of one named run** and never
globs. It also cross-checks the cheap and full artifacts against each other and
reports disagreement rather than silently resolving it — which immediately
surfaced a real one (see "Findings", below).

I did not stop over this. Every premise the brief *states* is correct; the
diagnosis was incomplete rather than wrong, and the four tasks were well defined
as written.

### 3. Two smaller things I could not clean up

- `derived/_diag_*.py` (7 files) are scratch diagnostics from the Gap B
  investigation. `rm`, `mv` and `mkdir` are all blocked by the sandbox in this
  session, so **I could not delete them**. Their content is superseded by
  `tools/diagnose_pierced_tree.py`, which is the reproducible version.
  `derived/` is *not* gitignored, so please delete them before committing.
- `tools/run_matrix_closed.sh` and `tools/run_probes_all.sh` are written as the
  reproduction recipe but could not be executed (`bash <script>` needs
  approval). I ran the underlying `uv run` commands individually instead, in the
  same order and with the same arguments. The scripts are untested as scripts.

---

## Gap A — variant rows had no ms

**Found.** Seven rows are re-scorings of one measured trial, not separate
measurements: `D9-noS4`, `D9+S4ours`, `D9u+S4u`, `D10b`, `D10a+base`, `D10a-u`,
`D10b-u`. Confirmed against the `ms covers` column of
`results/detector-matrix.results.md` rather than taken from the brief's list, as
instructed. The published table agrees with the brief: all four D10 variants are
priced at `D10a` (all read 777.2 ms/target there, the same figure `D10a` carries
as `measured`), `D9-noS4` and `D9+S4ours` at `D9`, and `D9u+S4u` at `D9u`. The
plan splits the four D10 variants across two table rows and the brief keeps them
in one, but both name the same arm, so there is nothing to reconcile.

**Changed.** `tools/assemble_matrix.py` gained an `ms covers` column and an
`ARM` map transcribed from the published table. A variant with no key of its own
is priced at its arm and labelled `priced at its arm`; a row with its own key is
labelled `measured`.

**Control — passed.** `D9` and `D9+S4u` keep their own measured values:

```
D9 behavioural differential      … 2015.6 ms/button  1591.3 ms/target  measured
D9+S4u differential with …       … 2100.2 ms/button  1658.1 ms/target  measured
D9-noS4 coverage-armed …         … 2015.6 ms/button  1591.3 ms/target  priced at its arm
```

`tools/check_controls.py` control 3 asserts this mechanically for every corpus:
**0 problems**.

---

## Gap D — columns dropped from `CHEAP_DETECTOR_REVIEW.md`

**Found.** Three columns were missing and one non-gap was being treated as one.

1. `abst.` collapsed `unknown_positive` and `unknown_negative`, both of which
   the raw JSON already carries.
2. `ms/button` had *replaced* `ms/target` rather than joining it.
3. The recall column was unlabelled. Resolved from the data, not the docs:
   `D0` on fixtures has `tp=1`, `fn=35`, `unknown_positive=3`, `recall=0.0256`,
   `recall_conditional=0.0278`. 1/39 = 0.02564 and 1/36 = 0.02778, and the
   published tables quote 2.6%. So **`recall` is strict recall** (TP over all 39
   labelled defects) and `recall_conditional` divides by decided defects only.
   The column is now labelled `strict recall`; `recall_conditional` is retained
   in `derived/matrix.json` and deliberately not shown.

**Changed.** The table now emits `unk pos` and `unk neg` as separate columns,
`ms/button` **and** `ms/target` side by side, `strict recall` under its real
name, and an `ms covers` note. `F1 —` where precision is `—` is left as `—` with
a footnote in the "What each column means" section stating that zero flags makes
precision undefined, so both dashes are correct rather than missing.

**Control — passed.** Fixtures rows match both published documents cell for
cell, comparing the underlying fractions rather than the rendered strings:

```
control 1: 48 published rows checked, 0 problems   (detector-matrix.results.md)
control 2: 16 review rows checked, 0 problems      (CHEAP_DETECTOR_REVIEW.md)
```

One tolerance is deliberate: the two published documents already disagree with
each other by one ulp on C3/C4 (32/39 rendered as 82.0% in one and 82.1% in the
other). The checker compares to a tenth of a point, so this rounding artifact
does not read as a measurement difference.

---

## Gap B — edgecases scored nothing

**Found — and the failing page is not the one the log implies.** The run log
stops after printing `pages/scale.html`, and `page_timings_ms` holds 13 pages,
which invites the conclusion that the *next* page (`shadow-tab-scope.html`, a
shadow-DOM page) is the culprit. It is not. Loading every edgecases page and
issuing the exact failing call names it directly:

```
pages/scale.html    depth= 154 els=  284  FAIL CBOR: stack limit exceeded
```

every other page, including both shadow-DOM pages and the iframe page, succeeds.

**It is a nesting limit, not a size limit.** Bisecting `DOM.getDocument`'s
`depth` on that page:

```
depth= 145  ok    response_bytes=72591
depth= 148  ok    response_bytes=73137
depth= 150  FAIL  CBOR: stack limit exceeded
depth=  -1  FAIL  CBOR: stack limit exceeded
```

73 KB is a trivial response. The page is 154 elements deep with only 284
elements in it, and each DOM level costs two CBOR nesting levels (the node map
plus its `children` array), so ~150 levels reaches Chromium's encoder stack
limit of ~300. Bounding `depth` alone is therefore not a fix — it would silently
truncate the tree and lose `e90`/`e91`.

The uncaught call is `upstream_candidates.resolve_probe_nodes`
(`runner/upstream_candidates.py:254`), reached from
`candidate_analysis.py:269`. `bakeoff.py`'s own `_pierced_centre` already caught
it; this one did not, and the exception propagated to the top-level handler,
which recorded it and suppressed every score for the corpus.

**Changed** — `runner/upstream_candidates.py`, new `get_pierced_document()`,
used by both call sites:

- The unbounded `{"depth": -1, "pierce": True}` call stays the **primary** path,
  so every corpus and page that already worked is byte-identical.
- Only on `stack limit exceeded` does it fall back to fetching the tree in
  bounded slices, descending with `DOM.describeNode` at `depth: 64`.
- Descent is by **`backendNodeId`, not `nodeId`**. This mattered: nodes arriving
  in a `describeNode` response are not registered with the frontend and come
  back with `nodeId: 0`, so a `nodeId`-based descent fails one slice in with
  "Could not find node with given id". I hit exactly that and had to correct it.
- Because callers pass the `nodeId` they find straight to `DOM.getBoxModel`, the
  spliced-in nodes are registered afterwards via
  `DOM.pushNodesByBackendIdsToFrontend` so they carry real ids.
- A recovered failure is removed from a `CheckedInstrument`'s error list, so a
  call that succeeded on retry is not later reported as a silent instrument
  failure.

**Control — passed, two parts.**

*The fallback returns the same tree.* `tools/diagnose_pierced_tree.py control`
forces the unbounded call to fail on pages where it normally works and compares
the two trees by structure and attributes:

```
pages/scale.html             unbounded impossible; paged finds ['e90', 'e91']
pages/shadow-tab-scope.html  identical=True  probes=['e130', 'e131']
pages/iframe-tab-scope.html  identical=True  probes=['e140']
upstream/h-shadow.html       identical=True  probes=['p90' … 'p94']
upstream/b-decoys.html       identical=True  probes=['p20' … 'p27b']
```

*edgecases now scores, and fixtures is unmoved.* edgecases went from
`scores: []` / 13 pages / exit 1 to **41 detectors, all 15 pages, exit 0** across
both stages. Fixtures was re-run through the changed code and reproduces its
published numbers exactly — see the control table at the end.

---

## Gap C — C10–C16 missing everywhere

**Found.** C10–C16 are not in `bakeoff.py`. They are dismissal/promotion rules
layered on C9, scored offline by `probes/score_new.py` and `probes/score_new2.py`
— both of which **hard-code the fixtures artifact and fixtures truth**, which is
why the rules had only ever been scored on fixtures.

**Changed.**

- `tools/run_probe_rules.py` — states R1, R2, R3 and R5–R9 transcribed verbatim
  from the two scorers, against whichever corpus it is pointed at. Imports no
  detector or scoring code; reads the answer key only to score.
- `tools/run_probes.py` — drives the four probe scripts for one corpus, setting
  `PROBE_CORPUS` in-process.
- The four `probe_*.py` scripts now write a sidecar `<name>.json.timing.json`
  recording the milliseconds spent **in the observation itself** (navigation and
  browser launch excluded, since every detector on the page pays those anyway).
  The observation files keep exactly the shape the scorers expect.
  `probe_effect2.py` also records which lead set it observed.

**Control — passed, exactly.** Under the `c12.json` lead set, fixtures reproduces
`CHEAP_DETECTOR_REVIEW.md` for all seven rows, from a *fresh* observation run
against the *new* bakeoff artifact:

| rule | TP | FP | FN | precision | strict recall | F1 | required |
|---|---:|---:|---:|---:|---:|---:|---|
| C10 | 37 | 8 | 1 | 82.2% | 94.9% | 88.1% | matches |
| C11 | 37 | 7 | 1 | 84.1% | 94.9% | 89.2% | matches |
| C12 | 37 | 6 | 1 | 86.0% | 94.9% | 90.2% | matches |
| C13 | 37 | **4** | 1 | **90.2%** | 94.9% | 92.5% | **37/4/1 at 90.2%** ✓ |
| C14 | 37 | 3 | 1 | 92.5% | 94.9% | 93.7% | matches |
| C15 | 37 | **0** | 1 | **100.0%** | 94.9% | 97.4% | **37/0/1 at 100%** ✓ |
| C16 | **38** | **0** | **0** | **100.0%** | 97.4% | 98.7% | **38/0/0 at 100%** ✓ |

**Both C16 figures are carried, each labelled.** Observing all 95 probes instead
of the 42-probe C12 lead set gives exactly what the brief predicted:

| row in `MATRIX-RESULTS.md` | TP | FP | precision |
|---|---:|---:|---:|
| `C16 … [observed 42 of 95: c12.json]` | 38 | 0 | 100.0% |
| `C16 … [observed 95 of 95: all probes]` | 38 | 11 | 77.6% |

C10–C15 are identical under both lead sets, so they are emitted once; only C16
splits. Suffixing rows that do not differ would imply a difference that is not
there.

**Coverage.** C10–C16 now appear for **all four** corpora — no corpus had to be
excluded. Every corpus supports them: each has a `truth.json` with `pages` and
`data-probe`-tagged targets, and each cheap run carries the C9 lead set.

| corpus | targets observed | C16 precision / strict recall |
|---|---|---|
| fixtures | 95 of 95, and 42 of 95 | 100.0% / 97.4% (c12) · 77.6% / 97.4% (all) |
| edgecases | 74 of 74 | 85.7% / 75.0% |
| gds | 8 of 8 | — / 0.0% (C9 abstains on all three leads) |
| ma11y | 7 of 7 | — / 0.0% (C9 abstains on its one lead) |

**One honest caveat on the C10–C16 `ms` columns.** The published table hard-codes
the static rule costs (`R1_MS = 0.35`, `R23_MS = 0.57`, `R5_MS = 104.0`) as
constants measured against a navigate-only baseline. I re-measured per corpus
instead of copying them, because copying a fixtures constant into a gds row
would be a fabricated number. My figures read higher than the published
constants for R1/R2/R3 (3.2 vs 0.35 ms/target on fixtures) because the
measurement boundary differs: mine is the full `evaluate` round trip including
the IPC hop, the published one subtracts a navigate-only baseline. **The
C10–C16 ms columns are therefore not comparable with the published ones**, and
the accuracy columns — which are what the control checks — are.

---

## Findings that fell out of the work

1. **gds `D8 hover-diff` is not deterministic across runs.** The cheap run scores
   it 1/0/5 and the full run scores it 0/0/6 — same corpus, same code, same
   session. The new assembler surfaces this as a note on the gds table rather
   than silently taking whichever file it read last, which is what the old glob
   did. Worth chasing; not in scope here.
2. **The earlier ma11y run's `RuntimeError: D0 … returned a probe outside
   pages/mutant-F42.html` did not recur.** All eight runs in this session printed
   their score tables with no suppression.
3. **`bakeoff-fixtures.json` and `bakeoff-edgecases.json` are traps.** They are
   old artifacts with no `page_timings_ms`, sitting in the same directories the
   assembler reads, and they sort last. Anything that globs those directories
   will silently pick them up.

---

## What changed

Nothing under `src/audit/`.

| file | change |
|---|---|
| `runner/upstream_candidates.py` | `get_pierced_document()`: paged fallback for the CBOR nesting limit; both call sites use it |
| `runner/bakeoff.py` | `_pierced_centre` delegates to the shared helper |
| `probes/probe_containment.py` | times the observation, writes a timing sidecar |
| `probes/probe_composite.py` | same |
| `probes/probe_effect.py` | same |
| `probes/probe_effect2.py` | timing sidecar, records the lead set observed |
| `tools/assemble_matrix.py` | rewritten: named run instead of a glob, every column, no unexplained blanks, generates `MATRIX-RESULTS.md` |
| `tools/run_probe_rules.py` | new — C10–C16 for any corpus |
| `tools/run_probes.py` | new — drives the four probes per corpus |
| `tools/check_controls.py` | new — the four controls, mechanised |
| `tools/diagnose_pierced_tree.py` | new — survey / bisect / control for Gap B |
| `tools/run_matrix_closed.sh`, `tools/run_probes_all.sh` | new — reproduction recipe (unexecuted; see above) |
| `MATRIX-RESULTS.md` | regenerated |

Artifacts written: `bakeoff-<corpus>-closed.json` and
`bakeoff-<corpus>-closed-full.json` for all four corpora (the pre-fix `matrix`
artifacts are left on disk to diff against), `derived/probes/<corpus>/`,
`derived/probe-rules/<corpus>-<leadset>.json`, `derived/matrix.json`.

Nothing was committed.

---

## Every control, and its output

```
control 1: 48 published rows checked, 0 problems
control 2: 16 review rows checked, 0 problems
control 3: 0 problems
control 4: 0 problems

PASS      1. fixtures vs detector-matrix.results.md
PASS      2. fixtures vs CHEAP_DETECTOR_REVIEW.md
PASS      3. measured arms keep their own ms; variants priced at their arm
PASS      4. no unexplained blank in MATRIX-RESULTS.md
```

Fixtures reproduced its published numbers **after** every change, on both
stages, across all 48 published rows — including the cheap tier
(`D6` 21/18/15, `D5` 25/18/11, `C9` 37/11/1) and the expensive arms
(`D9` 34/5/2, `D9+S4u` 33/4/3, `D9u` 36/10/3, `D9u+S4u` 35/5/4,
`D10a` 32/24/4, `D10b` 36/31/0, `D10a-u` 33/11/6, `D10b-u` 37/12/2).

Assembler self-check, over all four corpora and all 193 rows:

```
unexplained blank cells: 0
```

Reproduce with:

```
uv run --offline --no-sync python -m tools.assemble_matrix --label closed
uv run --offline --no-sync python -m tools.check_controls
```
