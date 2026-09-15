# Checkpoint: deliverable 1 done, deliverable 2 blocked

Written by Claude Code, 2026-09-14, between the two deliverables of
`BRIEF-CLAUDE-SCORED-RUN.md`. Nothing committed. No detector or `score.py`
touched. No network, no installs, no crawls.

**Read the blockers first (§3). Two of them stop deliverable 2 from starting at
all, and one is a premise in the brief that I believe is wrong.**

---

## 1. What changed

| File | Change | Tool that wrote it |
| --- | --- | --- |
| `FEASIBILITY.md` §6 | Rewritten in place, §6.1–§6.10 | `Edit` |
| `tools/kafe_denominator.py` | New; derives the 53-subject denominator and the matched-subset reference matrix | `Write` |
| `CHECKPOINT-SCORED-RUN.md` | This file | `Write` |

Nothing else was modified. `derived/` is unchanged — see §3.1 for why.

## 2. The §6 rewrite

Preserved intact, as the brief required: exclusive outcome buckets and
precedence (§6.3), repeat aggregation (§6.5), page-vs-element separation (§6.8),
the undefined-denominator rule and pessimistic abstention sensitivity (§6.6).

Changed:

- **§6.1 denominator.** N = 3 → **N = 53**, all labelled, **31 positive / 22
  negative, 0 label-unknown**. The 7 excluded subjects stay in the inventory with
  a stated reason each: 5 folder-form (`battlenet`, `canon`, `dmv_wc`, `gizmodo`,
  `speedway`), 2 with no entry document (`4shared`, `dmv_fl`).
- **§6.1 reference threshold.** The comparison threshold is **not** KAFE's
  published 36/39. Recomputed on the same 53: **TP=31 FP=2 FN=0 TN=20, precision
  31/33, recall 31/31**. `dmv_wc` — one of KAFE's three IAF false positives — is
  folder-form, so only `bowiestate` and `dell` carry into the run. Those two pages
  are the *entire* source of precision room.
- **§6.1 selection bias, stated not buried.** The exclusion is label-correlated:
  5 of 7 excluded subjects are IAF-positive (71% vs a 60% base rate). Positive
  rate moves 60.0% → 58.5%. No result here may be called a result on KAFE's corpus.
- **§6.7 target.** The old "equal recall with higher precision" is withdrawn with
  its arithmetic shown: on the three authorized subjects KAFE scores TP=2 FP=0
  FN=0 TN=1, i.e. **precision 1.0, recall 1.0**, so the target required beating
  1.0. It was unreachable, not merely hard. Replaced by **H1**, stated against a
  reference *recomputed on the common set* rather than a fixed fraction, plus
  three falsifiable sub-predictions P-A / P-B / P-C. I registered **P-B (recall)
  as the one I expect to fail**, because only D9 can see the
  reached-but-not-actionable half of IAF.
- **§6.4 timing.** Harry's constraint recorded verbatim in effect: **300 ms is a
  per-button cap the detector must not exceed, not a number to report as a win.**
  Unit defined as one actuation trial against one candidate. The 33.6 ms / 15-Tab
  figure is retracted as a per-button figure. No "faster than KAFE" claim is
  permitted, with the 19.22 min / 995 ms reasoning written out.
- **§6.2 controls.** Negative controls made mandatory in three layers (22 corpus
  negatives, an in-harness known-good element per subject, and one recorded
  reading per arm-1 defect mode). An unrecorded control counts as failed.
- **§6.10.** New table of standing limits that no result can clear.

### One error I made and corrected inside this session

My first draft of the §6.1 exclusion table split the folder-form five as 5
positive / 0 negative. `dmv_wc` is IAF-**negative** (it is one of KAFE's false
positives). Corrected to 4/1, and the total to 5 positive / 2 negative. The
31/22 subset split was unaffected — it was derived from the subset arithmetic,
which is what caught the table.

### How the numbers were verified

Not by a script — see §3.1. Two independent derivations that agree:

1. **Subset arithmetic** against the published totals: positives 36 − 5 excluded
   = 31; negatives 24 − 2 excluded = 22; TN 21 − 1 (`dmv_wc`) = 20; FP 3 − 1 = 2.
2. **Direct row listing** of the 53 from the CSV
   (`cut -d, -f1,12,13 … | grep -vE '<the 7>'`), which returned exactly 53 rows
   and 33 rows with a positive KAFE prediction — matching TP+FP = 31+2 = 33.

Both derivations are reproducible from the transcript, but **neither has an
artifact on disk**, which is the gap `tools/kafe_denominator.py` exists to close.

---

## 3. Blockers

### 3.1 I cannot execute Python — this stops deliverable 2 entirely

Every execution attempt was refused by the permission layer:

- `uv run --offline --no-sync python -m tools.kafe_denominator` → *requires approval*
- `uv run --offline --no-sync python -c "import sys, playwright; …"` → *requires approval*
- `python3 -c …` → *requires approval*

Consequences:

- `derived/kafe_denominator.json` **does not exist**. §6.1 cites it as the
  derivation of its own denominator, so that citation is currently a forward
  reference. One approved invocation fixes it.
- `FEASIBILITY.md` §7 ("Exact runnable commands") was deliberately **not**
  updated with the new tool, because I have not run it and that section's claim
  is that its commands were run.
- **Deliverable 2 cannot begin.** The scored run is 53 subjects × Playwright;
  it is nothing but execution.

I did not use `dangerouslyDisableSandbox`; the brief forbids permission-bypass.

### 3.2 I cannot read the frozen detectors

`src/audit/analyzer/keyboard/kbdiff/` is outside this session's allowed working
directory. Both `ls` and `Read` were refused. So I cannot identify the detector
entry point, cannot import it, and cannot answer the question §6.1 now requires
the manifest to answer.

### 3.3 Premise check: no arm has run the frozen detectors

The brief calls `tools/gds_run.py` "a working reference for the same measurement
on a different corpus." It is a faithful reference for the *mechanism* and its
five defect fixes, but its own docstring says:

> Detectors themselves are untouched and unimported-from; this only supplies
> identities and a URL.

`grep` across `tools/`, `tests/` and the experiment root finds **no import of
anything under `src/audit/`**. So arm 1's TP=6 FN=0 FP=0 TN=2 validates a
reimplementation of the differential idea, not the shipped Axcess detectors.

This matters because the objective is stated as *"do the **frozen Axcess**
keyboard/mouse differential detectors do better than KAFE's?"* Extending the
arm-1 pattern to 53 subjects would answer a different question — "does this
harness's reimplementation of the differential idea do better than KAFE?" — and
the §6.1 text I wrote now forces that distinction to be declared rather than
blurred.

Per the brief's own instruction to stop rather than work around a wrong premise,
**I am not choosing between these two readings.** I need the manager to say which:

- **(a) Import the frozen detectors.** Requires read/import access to
  `src/audit/analyzer/keyboard/kbdiff/`, and answers the objective as written.
- **(b) Reimplement, as arm 1 did.** Runnable within current access, but the
  headline must then say it is a mechanism result, and the comparison to KAFE is
  weaker than the brief's objective implies.

### 3.4 Two stale statements outside §6, left unedited

Flagged rather than fixed, since §6 was my scope and Codex reviews it:

- **§8, blocker B1** still reads "licence — unresolved — blocks expansion beyond
  the 3 samples". §6.1 now scores 53. These contradict each other in one document.
- **§7** lists commands for the 3-subject era only.

---

## 4. What I need to proceed

1. A decision on **3.3 (a) or (b)** — this determines what deliverable 2 even is.
2. Approval to run Python in this directory (`uv run --offline --no-sync python …`),
   offline, no installs.
3. If (a): read access to `src/audit/analyzer/keyboard/kbdiff/`. Read-only; I will
   not edit it or `score.py`.
4. Confirmation on **3.4** — whether to correct §7/§8 or leave them for the manager.

With 2 alone I can emit `derived/kafe_denominator.json` and close the one gap in
deliverable 1. With 1–3 I can start deliverable 2: pre-registration file first,
then the frozen manifest, then the run.

## 5. Status against the brief's output list

| Required output | Status |
| --- | --- |
| `FEASIBILITY.md` §6 rewritten in place | **Done** |
| Pre-registration file for the scored run | Not started — deliverable 2; H1/P-A/P-B/P-C drafted in §6.7 and ready to lift |
| Raw per-subject outputs under `derived/` | **Blocked** (3.1) |
| Report: confusion matrix, abstentions, per-button timing, coverage | **Blocked** (3.1) |
| Nothing committed | **Held** |
| Detectors and `score.py` untouched | **Held** — and unreadable (3.2) |
