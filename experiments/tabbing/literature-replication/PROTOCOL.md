# Proposed protocol (SUPERSEDED in part — see FEASIBILITY.md)

> **Status 2026-09-14, after execution.** Approach C was executed. Its
> preconditions C-P1 (licence) remain unresolved; C-P4 resolved *in favour* of
> feasibility. Blockers B2 and B4 below are withdrawn/resolved, and the
> hypotheses in §3 are superseded by `FEASIBILITY.md` §6, which is the version
> submitted for approval. The text below is retained unedited as the
> pre-registration record.



Companion to `LITERATURE.md`. Baseline `fc5a1d5be193212c44f4b92b57a3fbb0679eb1eb`.
Nothing here has been run. Detectors stay frozen. No scoring until the manager
approves a frozen version of this document.

---

## 0. What the evidence already forces

Three facts from `LITERATURE.md` constrain every option below:

1. **KAFE's page labels and reference predictions are recovered and verified.**
   60 subjects, 36 IAF-positive / 24 IAF-negative, 9 KTF-positive; recomputed
   P/R 92.3%/100% and 90.0%/100%. Real third-party labels exist.
2. **KAFE's subject bytes are unlicensed and undownloaded**, ~100 MB estimated,
   and are captured copies of live commercial sites.
3. **The frozen detectors cannot enumerate candidates on a real page.**
   `_SURVEY_JS` requires `data-probe`. So "run Axcess on KAFE subjects" is not
   executable without a detector edit, which is forbidden for the primary
   experiment.

Fact 3 is the one that decides the shape of this protocol. It was not visible
in the preflight brief, and it invalidates the obvious plan.

---

## 1. Three approaches considered

### Approach A — Full KAFE replay

Download all 60 subjects, replay them offline, run the frozen detectors,
project element outputs to KAFE's page × IAF unit, compare to the recovered
labels and to `QualWeb_output` / `WAVE_output`.

Strongest claim available, and blocked five ways: no licence (§2.1); ~100 MB
download needs permission; Firefox 68 is unavailable and Playwright's Firefox
path is absent; `runner/serve.py` reads a fixture *directory*, not mitmproxy
flows; and fact 3 above means the detectors would report nothing. Estimated
work to unblock is large and at least two blockers are not ours to clear.
**Rejected as the next step.**

### Approach B — Artifact-anchored external-validity study, no replay

Do not run anything on KAFE subjects. Use the recovered artifact as
*literature* evidence: publish the recomputation of KAFE's Table 1 from its own
sheet, the per-subject label distribution, and the construct map; then report
the frozen detectors on the existing repo corpus, projected onto KAFE's page ×
type unit, labelled explicitly as a mechanism comparison and never as a
replication. Cheap, honest, and entirely within the frozen-detector rule. Its
weakness is M1: the repo corpus is development evidence, so the Axcess half
carries no accuracy claim. **Keep as the fallback deliverable.**

### Approach C — Bounded replay-fidelity probe (recommended next step)

Before spending anything on A, spend one small, permissioned step on the single
question that decides whether A is even possible: *does a KAFE capture replay
offline in the browser we have, and does what loads resemble what the appendix
says loaded in 2021?*

Three named subjects only, chosen now so the choice cannot be label-driven
later: **`citiprogram`** (347 KB, 3 IAF, 0 KTF — smallest positive),
**`craigslist`** (284 KB, 11 IAF, 0 KTF — smallest file, densest faults, 288
control elements) and **`coronavirus`** (1 MB, 0 IAF, 0 KTF — clean control).
Two positives and one negative, ~1.6 MB total. No scoring, no detector
invocation, no labels consulted during execution.

**Recommended.** It is reversible, small enough to authorise, and it produces a
yes/no on Approach A for roughly 1/60th of the download.

---

## 2. Approach C in detail

### 2.1 Preconditions (all must hold before any byte is fetched)

- **C-P1 Licence.** A licence or terms statement is located for the KAFE
  artifact, or Harry explicitly accepts fetching three files for local,
  non-redistributed inspection. Absent both, stop.
- **C-P2 Download permission.** Explicit approval for ~1.6 MB across three
  named Drive file IDs. No bulk fetch, no recursive mirroring.
- **C-P3 Storage.** Files land under
  `experiments/tabbing/literature-replication/artifacts/` and are
  **git-ignored**. Captured third-party site bytes are not checked in.
- **C-P4 Format.** If a subject file turns out to be a mitmproxy flow dump
  rather than a directory of static resources, Approach A is declared
  infeasible without new tooling and Approach C stops at that finding.

### 2.2 Fixed conditions

| Knob | Value | Why |
| --- | --- | --- |
| Browser | Chromium 145.0.7632.6 via Playwright 1.58.0 | only engine present; Firefox 68 unavailable |
| Viewport | 1920 × 1080 | matches KAFE §5.1, not the repo's 1280 × 900 |
| Network | `runner/serve.py` default-deny; every unmatched request aborted and counted | prevents silent live-network dependence |
| Actions | page load + `networkidle` + 3 s settle. **No key presses, no clicks.** | fidelity probe only |
| Budget | 60 s wall-clock per page load; exceeded ⇒ `timeout`, recorded, not retried silently |
| Repeats | 3 per subject, fresh context each | reproducibility of the replay, not statistics |
| Provenance | `runner/provenance.py` source fingerprints + SHA-256 of each fetched artifact recorded before use |

### 2.3 Falsifiable criteria

The appendix table gives 2021 element counts per subject. Define
`ratio = observed / appendix` for each of `#Total`, `#Visible`, `#Ctrl`.

- **C-H1 (replay fidelity).** For each of the three subjects and all three
  repeats, `0.95 ≤ ratio ≤ 1.05` on `#Total`.
  *Falsified if* any subject's median `#Total` ratio falls outside
  `[0.80, 1.20]` ⇒ Approach A is declared infeasible on fidelity grounds and
  the protocol falls back to B.
  *Ambiguous zone* `[0.80, 0.95) ∪ (1.05, 1.20]` ⇒ reported as degraded, and
  Approach A may proceed only with the degradation stated in every later table.
- **C-H2 (hermetic replay).** Aborted-request count is 0 for every repeat.
  *Falsified if* any repeat aborts ≥1 request ⇒ the capture is incomplete;
  record the aborted URL list, and treat `#Total` from that repeat as
  unreliable rather than as a fidelity measurement.
- **C-H3 (determinism).** Across the 3 repeats, `#Total` varies by ≤1%.
  *Falsified if* spread >5% ⇒ the subject is non-deterministic on replay and is
  reported in an `unstable` bucket, excluded from C-H1 with the count stated.

Every subject lands in exactly one of `ok` / `degraded` / `unstable` /
`timeout` / `format-unsupported`, and all five counts are reported with
denominator 3. No subject is dropped silently.

### 2.4 Explicit non-goals

No detector runs. No scoring. No `truth.json` consultation. No comparison to
`QualWeb_output` / `WAVE_output`. No claim about Axcess accuracy of any kind.
Approach C can only ever produce a feasibility verdict.

---

## 3. If Approach C passes: the shape of the scored arm

Recorded now so that hypotheses are frozen before any measurement, per the
coordination contract. None of this executes without a fresh approval gate, and
it additionally requires resolving fact 3 (candidate discovery), which needs a
**separately identified follow-up change**, not a quiet edit.

- **Unit.** KAFE's page × IAF binary, denominator 60 (36 positive, 24
  negative). Axcess element outputs project up: page positive iff ≥1 element
  reported. Element-level numbers are reported separately and never mixed.
- **H-A1.** Axcess page-level IAF recall ≥ 0.90 on the 60 subjects.
  *Falsified* below 0.90.
- **H-A2.** Axcess page-level IAF precision ≥ 0.80.
  *Falsified* below 0.80. (KAFE reports 0.923; this is deliberately a weaker
  bar, because a lower bar is the falsifiable one.)
- **H-A3 (same-corpus control).** On the identical 60 subjects with the
  identical projection, Axcess's page-level F1 exceeds WAVE's as normalised by
  KAFE §5.3 ("any mention of keyboard accessibility issues" = detection),
  recomputed from `WAVE_output` rather than quoted from Table 1.
  *Falsified* if it does not.
- **Controls.** (i) the 24 label-negative KAFE subjects; (ii) WAVE and QualWeb
  recomputed on the same subjects from their saved outputs; (iii) the existing
  repo corpus, run unchanged, as a regression check that nothing in the
  environment drifted.
- **Repeats.** 3 per subject, fresh context. Repeats measure reproducibility,
  not independent samples, and are reported as spread, never as confidence
  intervals.
- **Denominators and abstentions.** Four separate columns, never folded into
  TP/FP/FN: `unknown` (Verdict.UNKNOWN / reachability not certain),
  `abort-degraded` (≥1 aborted request), `timeout`, `unstable`. Precision and
  recall are reported twice — once excluding abstentions, once counting every
  abstention as a miss — and both appear in the report.
- **Full-page false alarms.** On real pages there is no label for most
  elements, and `score.py` currently drops unlabelled predictions. The
  protocol therefore writes **every** reported element to an out-of-band
  adjudication ledger
  (`artifacts/adjudication/<subject>.jsonl`), which a human labels as
  true / false / undecidable *after* predictions are frozen and hashed.
  `score.py` is not edited. Precision is computed from the ledger, not from
  the scorer's filtered view, and the undecidable count is reported.
- **Oracle hygiene.** Subject selection, hypotheses and thresholds are frozen
  in this file before any label is read for scoring. The three Approach-C
  subjects are named above for exactly this reason.
- **Stopping rule.** The scored arm runs once over 60 subjects × 3 repeats. No
  re-runs after seeing scores; a re-run for any reason is reported alongside
  the original, and the original is not discarded.

---

## 3a. A cheaper alternative that sidesteps the licence blocker

Late finding, recorded because it may dominate Approach C. NavA11y (ENASE 2026,
`LITERATURE.md` §2.3) built its labelled dataset by extending six focus-related
pages from the **GDS Accessibility Tool Audit** — a UK Government Digital
Service published corpus of deliberately-broken test pages with documented
expected results. If that corpus exists as described, is openly licensed, and
contains cases in the mouse-operable-but-not-keyboard-operable class, it is a
better primary target than KAFE's captures: no licence blocker (B1), no
100 MB download, no mitmproxy replay problem (B4), static pages that
`runner/serve.py` can already serve, and labels authored by a third party with
no knowledge of Axcess — which is exactly what M1 says the current corpus
lacks.

It does **not** solve B2: the frozen detectors still cannot enumerate
candidates without `data-probe`. And none of it is verified — the corpus URL,
licence, page count and failure-class coverage are all **unchecked**. Treat this
as the highest-value thing to check next, not as an established option.

---

## 4. Exact bounded next step

Given §3a, the recommended order is: **check the GDS corpus first (free, no
permission needed), and only then decide on the KAFE download.**

The KAFE decision, when it comes, is Harry's, not mine:

> Authorise fetching three named KAFE subject files (`citiprogram`,
> `craigslist`, `coronavirus`; ~1.6 MB total) into a git-ignored
> `artifacts/` directory for local format inspection only — subject to a
> licence answer (C-P1)?

If yes, the next session does C-P4 (format inspection) and nothing else, and
reports back what a KAFE subject file actually is. If no, the work switches to
Approach B and the deliverable becomes the artifact-anchored literature study
plus the recomputation already completed.

Either way, no detector is edited and no score is produced under this document.

---

## 5. Known blockers

| ID | Blocker | Status |
| --- | --- | --- |
| B1 | KAFE artifact licence unknown | unresolved; needs a human decision |
| B2 | Frozen detectors cannot discover candidates without `data-probe` | **WITHDRAWN — this was wrong.** `collect_candidates` already walks all elements. See FEASIBILITY.md §5. |
| B3 | Firefox 68 / Selenium 3.141.5 unavailable; Chromium-only | permanent; fidelity caveat, not fixable here |
| B4 | `serve.py` cannot read mitmproxy flows | **RESOLVED** — `tools/flowfile.py` + `tools/replay.py`; 12/12 sample runs loaded |
| B5 | BAGEL artifact folder returns 404 | proved inaccessible; alternates in `LITERATURE.md` §2.2 unchecked |
| B6 | Internet Archive offline during this session | retryable |
| B7 | `dl.acm.org` returns 403 to this client | blocked |
| B8 | `sources.json` registration script not runnable here | pending-sources list in `LITERATURE.md` |
| B9 | Bash commands using shell expansion are auto-denied in this session (no approval surface) | worked around by using WebFetch; one folder-listing command was blocked and not retried |
| B10 | GDS Accessibility Tool Audit corpus unverified | free to check; recommended first action (§3a) |
