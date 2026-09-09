# Axcess keyboard differential experiment

The experiment compares real mouse actions with keyboard actions on frozen local
test pages. Start with [REPORT.md](REPORT.md) for the question, measured results,
and limitations. [UPSTREAM.md](UPSTREAM.md) records the published source study,
licenses, and retained labels.

This is an optional development experiment on the `tabbing` branch. Normal Axcess
scans do not import or run it. No database, report contents, model, account, or
external website is needed.

## Run

With Axcess's Python dependencies and Playwright Chromium already installed,
run from the repository root:

```bash
uv run --offline --no-sync python -m experiments.tabbing.runner --label my-run
```

The checked-in React fixture bundle means that scoring needs no npm install or
JavaScript build. The runner intercepts requests for `https://tabbing.axcess.test`
and serves local fixtures directly inside Playwright. It opens no listening
server. Unmatched requests must be aborted rather than sent to the internet.

Results include the run settings, file fingerprints, per-target observations,
and separate scores for the original corpus and new holdout cases. Keep the
first completed result when investigating errors; use a unique `--label` for each
repeat. Existing outputs are never overwritten. `--viewport desktop` selects
only the wide window; repeat the option for multiple windows. Defaults are 300
Tab presses, 250 ms settling, 60 seconds per measurement/discovery stage, and
1800 seconds for the full run. The smaller limits of an actual trial can leave
results unknown even when the full run completes.

The comparison of twelve detector ideas is a separate desktop-only command:

```bash
uv run --offline --no-sync python experiments/tabbing/runner/bakeoff.py --corpus fixtures --label my-matrix
```

Use `--corpus edgecases` for the supplemental development stress tests. Their
fixtures and detector share an author; they do not support an unbiased ranking.

The main runner's schema-2 records include the start and finish, the actual
browser version, and detector and runner fingerprints before and after
measurement. A changed source or frozen input invalidates the run and suppresses
its scores. The main JSON contains
post-equivalence `probes`, the separately scored `candidate_gated_probes`,
per-page/window `candidates_by_page`, and contextual dismissal evidence. Compare
`mouse_effect` with each `keyboard_by_key[key].effect`; keys are independent
trials and there is no combined keyboard effect. A null candidate list means
discovery failed, whereas an empty list means it completed and selected none.
The main process returns nonzero for an invalid or incomplete run. It rejects
source changes between import and execution before starting measurement.

The comparison runner writes `bakeoff-<corpus>-<label>.json` under the selected
corpus's `results/` directory, unless `--out` selects another directory. It uses
a separate record shape with `reported` and `unobservable` sets for each method,
D10a coverage evidence, and validity/provenance metadata under `run`. Its source
checks run before and after measurement. A page-level instrumentation failure
invalidates the comparison and suppresses its scores.

## Inputs

| Path | Purpose |
| --- | --- |
| `fixtures/upstream/` | Original 60 targets and unchanged source fixtures, plus a generated React bundle. |
| `fixtures/holdout/` | 35 independently authored targets. |
| `fixtures/truth.json` | Combined target lists and expected labels; only scoring may use the labels. |
| `fixtures/frozen-manifest.json` | SHA256 fingerprints frozen before the first score. |
| `runner/` | Offline browser orchestration and scoring. |
| `src/audit/analyzer/keyboard/kbdiff/` (repository root) | Experimental detector logic. |

Two viewport names are fixed: `desktop` is 1280 × 900 and `mobile` is 390 × 844.
The latter changes the window size; it does not emulate a mobile device. Labels
inherit their top-level value unless `labels_by_viewport` supplies an override.

The corpus fingerprint is the SHA256 of the `files` dictionary in the manifest,
serialized as sorted JSON without extra whitespace. Each dictionary value is
the SHA256 of that file's exact bytes. Do not update the manifest to conceal a
changed input. A changed fixture, label, or bundle is a new corpus version.

## Rebuild the reference React bundle

This is for intentional corpus maintenance, not a normal experiment run:

```bash
make frontend-install
node experiments/tabbing/build-react.mjs
```

The script uses the locked frontend dependencies and preserves dependency
license comments. It writes the package versions to `react/build.json`. Rebuilding
with different dependency or Node versions may change the frozen files; retain
the original study input and version a replacement before scoring it.

## Interpreting a result

An oracle score assumes the target was supplied. The saved `end_to_end` mode
is candidate-gated scoring over annotated targets: it requires discovery to
succeed but does not measure unannotated false alarms or a complete site scan.
`no_lead` means this bounded experiment did not produce a lead. `unknown` means
it could not support a classification. Neither is an accessibility certification.
The report explains precision, recall, uncertainty, and inherited label caveats.
