# Brief — correct the KAFE cost comparison

Working directory:
`/var/home/me/Development/axcess/experiments/tabbing/literature-replication`

## The error

Committed reports compare KAFE's **25.7 ms per button** with Axcess per-button
timings as if both were a detector's full cost. They are not:

- KAFE's 25.7 ms is its `Detection` column divided by its visible control
  count: the graph comparison **after** the two crawls. It excludes the crawls.
- Axcess timings include Axcess's own browser work, such as tab walks.

The manager recomputed from `artifacts/kafe_results_to_reproduce.csv` over all
60 subjects (phases `InitializeProxyKnfg`, `ExtractNodesKnfg`, `CrawlKnfg`,
`InitializeProxyPcnfg`, `ExtractNodesPcnfg`, `CrawlPcnfg`, `Detection`, each
divided by `Size of All Visible Ctrl Nodes`):

| KAFE cost per visible control | median | min | max | under 300 ms |
|---|---:|---:|---:|---:|
| Detection only | 25.8 ms | 1.1 | 225.8 | 60/60 |
| CrawlKnfg + CrawlPcnfg | 3,823.9 ms | 329.4 | 15,363.9 | 0/60 |
| all seven phases | 22,683.3 ms | 6,138.8 | 125,850.8 | 0/60 |

Mean full pipeline per subject: 19.12 min (paper: 19.22).

**Recompute these yourself** from the CSV, and also on the 39 scored subjects,
pooled the same way the report already pools the 25.7. Use your numbers, not
these. If yours differ, say so.

## Update (21:30): new direction after your stop — this overrides the table above

**Your finding holds, but your replacement figure doesn't.** The manager
confirmed the pattern: `Detection` rises almost steadily in alphabetical order
(2 drops in 59 steps, against 27–30 for the crawl columns). But KAFE's own
per-subject log files contradict the ~0.5 ms figure:

| subject | ctrl nodes | `execTimeDetection.csv` Type 1 | per ctrl | results CSV `Detection` |
|---|---:|---:|---:|---:|
| 4shared | 62 | 4,959 ms | 80.0 ms | 66 |
| adorama | 8 | 2,135 ms | 266.9 ms | 69 |
| bbc | 17 | 2,193 ms | 129.0 ms | 141 |

On those three subjects, the per-subject `execTime.csv` phases match the results
CSV's crawl/extract columns to within about 1–2% (for example, CSV
`ExtractNodesKnfg` ≈ `01-ExtractNodesKnfg` + `04-ExtractNodesInCrawlKnfg`). So the
crawl figures look sound; only `Detection` (and possibly `Localization`) doesn't.
Don't use 0.5 ms or 25.7 ms anywhere.

**CEO decision: get KAFE's per-subject timing files for all 60 subjects and
recompute from them.**

1. **Download.** `KAFE_output` is Drive folder `1hKV7KoaMA2Lsgzly9-3cwA-QTU4X-ZM4`,
   one subfolder per subject. List a folder with
   `https://drive.google.com/embeddedfolderview?id=<id>`, and download a file with
   `https://drive.google.com/uc?export=download&id=<file id>`.
   `tools/fetch_kafe_all.py` already does this for the captures, so reuse its
   approach. Write the downloader as a script under `tools/` and run it with
   `uv run --offline --no-sync python -B tools/<script>.py` (`--offline` only
   affects package resolution, so network access still works). Per subject,
   fetch `execTime.csv`, `execTimeDetection.csv` and `resultsSubjectStats.csv`.
   Nothing else.
2. **Keep them local.** These are unlicensed third-party files. Save them under
   `artifacts/kafe_output/<subject>/`, confirm they're gitignored
   (`git status` must not list them), and add an ignore rule if they aren't. They
   must never be committed.
3. **Name every gap.** List by name each subject whose files are missing,
   empty or unparseable.
4. **Map the phases.** Show how the 14 per-subject phases map onto the results
   CSV's 7 columns, and how well they agree, per phase, across all 60. Where they
   disagree, say so; don't force a mapping.
5. **Compute** ms per visible control (denominator `Size of All Visible Ctrl
   Nodes`; cross-check it against `resultsSubjectStats.csv`). Do this for
   Type 1 detection alone, for the crawl phases and for the full pipeline: median,
   min, max, pooled, and how many are under 300 ms, for all 60 and for the 39
   scored. Type 1 is the IAF comparison. State whether Type 2 is counted anywhere.
6. **Correct the reports** using the "What to change" list above, with these
   figures in place of the table. In §8.4, explain that the results CSV's
   `Detection` column isn't per-subject detection time, and give the evidence.

## Second correction, same files: abstention counts and strict recall

The KAFE table's cells like "n/a (16 abst.)" count abstentions over the **52
attempted** subjects, but the table's denominator is **39**. The manager's
check from `derived/kafe_matrix.jsonl` plus the CSV labels: **C12 gave no verdict
on 3 of 39** (`godaddy`, `thefreedictionary` and `wendys`, all positives), and its
**strict recall is 19/24 = 79.2%**, not the 90.5% decided-only figure.

Your earlier note said strict recall and the unknown counts don't exist for this
corpus. They do: the JSONL has each detector's verdict per subject. Fix this in
the generator, so the KAFE table's **strict recall**, **unknown pos** and
**unknown neg** columns are computed on the 39-subject basis. Keep decided-only
recall in the cell as well, clearly labelled. Then regenerate.

This deliberately changes those three columns. **TP, FP, FN, TN and precision
must not change**, and neither must any number in other columns. Check with
`git diff`, and list every cell that changed in your final message. Then update
every place in `FINAL-REPORT.md` and `KAFE-HIGHLIGHTS.md` that quotes KAFE-corpus
recall (for example, "100% recall" for D9+S4ours), and say which recall each
F1 figure uses.

## What to change

1. `FINAL-REPORT.md`: every place the 25.7 ms is used as KAFE's cost. At least
   §1 (what it can claim), §2.1, §2.2 ("Where Axcess wins is cost", "30 of 48
   rows have a lower ms/button than KAFE"), §7 (the 300 ms ceiling), §9, and
   the KAFE reference row's timing-scope cell. State both figures, detection
   only and full pipeline, and which one is comparable to Axcess's numbers.
   Re-derive every "N of M faster than KAFE" claim on the full-pipeline basis,
   and keep the detection-only count only if it's clearly labelled.
2. Add an entry to §8.4 (corrections) describing this error.
3. `KAFE-HIGHLIGHTS.md`: same correction wherever the cost comparison appears.
4. The generator text in `tools/kafe_matrix.py` that describes KAFE's ms
   column, so `KAFE-MATRIX.md` says the figure excludes the crawls. Then
   regenerate with `assemble` and `report` only. **No number in any table may
   change.** Check with `git diff` and stop if one does.

Don't change any accuracy number. This is a timing-scope correction only.

## How to run commands

`uv` is on the PATH. Run each regeneration command on its own, exactly:

    uv run --offline --no-sync python -B -m tools.kafe_matrix assemble
    uv run --offline --no-sync python -B -m tools.kafe_matrix report

Use `uv run --offline --no-sync python -B -c "..."` for the CSV arithmetic,
with nothing chained before or after it.

## Progress survives a crash

Append one line per completed step to `COST-FIX-PROGRESS.md`. If it already
exists when you start, continue from its last line.

## Boundaries

- Do not edit anything under `src/audit/`.
- Do not run `run`, `controls` or `capdiag`, or any subject or detector.
- Do not touch `derived/kafe_matrix.jsonl`. A separate process may append a
  craigslist line to it. If it has more than 52 lines when you start, stop
  and report instead of regenerating.
- Do not commit.

If any premise here is wrong, stop and report it instead of working around it.
