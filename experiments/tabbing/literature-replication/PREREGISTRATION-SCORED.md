# Pre-registration: the scored run of the frozen Axcess detectors

Written by Claude Code on 2026-09-16, **before any part of this run executed**,
under `BRIEF-CLAUDE-SCORED-RUN-V2.md`. Nothing is committed. Nothing under
`src/audit/` is edited.

This file fixes the parameters, the predictions and the falsification criteria.
Anything decided after execution begins is a post-hoc choice and is marked as
such in `RESULTS.md`; the only parameter this file leaves open is the candidate
cap `N`, and it is bounded below by a rule stated in §4.3 that can only move it
**down**.

---

## 1. What is under test, and what it is not

**Under test:** the detectors at `src/audit/analyzer/keyboard/kbdiff/`,
**imported unmodified**. This resolves §6.1's question — the run *imports the
frozen detectors*; it does not reimplement their mechanism. Reading (a) of
`CHECKPOINT-SCORED-RUN.md` §3.3, as accepted by the brief.

Entry points imported:

| Symbol | Module |
| --- | --- |
| `DifferentialRunner` | `audit.analyzer.keyboard.kbdiff.differential` |
| `TrialConfig` | `audit.analyzer.keyboard.kbdiff.differential` |
| `collect_candidates` | `audit.analyzer.keyboard.kbdiff.candidates` |
| `Verdict`, `Uncertainty` | `audit.analyzer.keyboard.kbdiff.model` |

SHA-256 of the frozen sources as read at pre-registration time (re-verified and
re-recorded into `derived/manifest_scored.json` at run start; a mismatch aborts
the run):

```
80025d7b3d595b75051f9aac1bced56f16b5ca477dba9a94aec0b85a5add625d  candidates.py
5315645ccc7051d3cdd0231ecefa6d2a0dafd6107b3d4c775ddb11895b28ee49  channels.py
1a87accc0cce1d892b790fe4fd0805b524057971de3087691c635539fc3c9f84  coverage.py
59dd8f9804d2772f88092915118de83dcc9f31d01cda453c3d11bf72b3a0d822  detectors.py
b83ab078cb65ae56b0ba4619b30fb97c00ea950a8305a61ebca81813dd782067  differential.py
baebdc95d6064beacfc0efe50cc15debc4ec9531a4fbab8e0ce96f8f1ee0ed85  equivalence.py
b5f36f2b323911788043f1f6b2fdb92aa6e1b97ba30338bb10e9228514c11b42  __init__.py
870d0311802f629f8197f617d260494973900bde76f9d2961ed3142a5c742e9c  model.py
690230189bd04bd77bd9acb32c21c2d24db7cce61d963251422dd3e1484ba91c  score.py
69f08283ae5633b19b6771b7b4a0a9dbc7af0908b20bd4033a07aed7ae511489  taborder.py
```

`score.py` is hashed but **not imported**: the page-level projection in §5 is
harness arithmetic over `ProbeOutcome.verdict`, not a call into `score.py`.

Environment: Python 3.14.7, Playwright 1.58.0, Linux 6.12.0 x86-64. Chromium
build string is read from the launched browser and written to the manifest.
Working tree: branch `tabbing`, HEAD reported as `8aa3577` by the session's git
snapshot (not independently re-verified — `git rev-parse` is outside this
session's permitted commands).

**The only harness code that touches the detectors' behaviour** is a subclass
`TimedRunner(DifferentialRunner)` that overrides `_mouse_trial` and `_key_trial`
solely to wrap `await super()...` in a `perf_counter` pair and append the elapsed
milliseconds to a list. It changes no argument, no ordering and no return value.
This is disclosed here because it is technically an override of a frozen method.

### Not under test, and not claimed

- No comparator is run. No axe-core, no `candidates − TabOrder`, no re-run of
  KAFE. §6.2's runnable same-replay comparators are **not** satisfied.
- The comparison against KAFE is a fidelity-conditional descriptive contrast on
  a named 53/60 subset (§6.1 claim ceiling). It is not a replication and not a
  corpus-wide claim.
- `tools/gds_run.py`'s 6/6 is retracted and is not evidence about these
  detectors. It is not cited as a result anywhere in `RESULTS.md`.

## 2. The §6.9 release gate is not met, and this run proceeds anyway

Stated here rather than discovered later. Of §6.9's five prerequisites:

| Gate item | Status entering this run |
| --- | --- |
| 1. Independent Codex disposition on §6 | **Not confirmed to me.** The brief forbids me reviewing my own §6 rewrite; whether Codex has signed off is not visible from here. |
| 2. R6 (brotli) clearance | **Open.** The brief says R6 is explicitly not mine. |
| 3. Frozen execution manifest per §6.2 | **Satisfied by this file + `derived/manifest_scored.json`.** |
| 4. Pre-registration with H1/P-A/P-B/P-C | **This file.** |
| 5. Manager approval in scope | **Treated as satisfied by `BRIEF-CLAUDE-SCORED-RUN-V2.md`,** which directs the run explicitly. |

Consequently **no result of this run may be reported as having cleared §6.9.**
It is a budgeted pilot with real numbers and an unmet gate, and `RESULTS.md`
says so in its headline, not its caveats.

## 3. Deviations from `FEASIBILITY.md` §6, registered in advance

Each is forced by the 90-minute budget in the brief, and each weakens a specific
§6 guarantee. None is a finding; all are limits.

| §6 requirement | This run | Guarantee lost |
| --- | --- | --- |
| §6.5: three repeats per subject per arm | **One repeat** for KAFE (deliverable B); two for GDS (deliverable A) | Within-subject stability is not established for B. `unstable` cannot be detected, so no B subject may be called stable. |
| §6.2: tagged **and** untagged detector arms, outputs compared | **Tagged arm only** | The tagged/untagged detector-output agreement control is not run. It is also not runnable as specified: the frozen detectors address elements by `data-probe`, so an untagged arm has nothing to address and produces no detector output to compare. Existing G1c focus-trail evidence is feasibility evidence, not this control. |
| §6.2: axe-core and `candidates − TabOrder` comparators | **Not run** | No same-replay baseline. KAFE's historical numbers are the only reference, and they are historical. |
| §6.3/§6.4: full disposition precedence and the `count-aligned` fidelity annotation | **Partially applied.** Dispositions are recorded (§5.3); the visible-count fidelity annotation is **not** computed | No fidelity-qualified stratum. Every number is reported on the unstratified set. |
| §6.8: element adjudication ledger | **Not written.** Scoring of elements is not authorized here | No element precision is reported at all. |

**A candidate cap (§4.3) is a further deviation from anything §6 contemplates.**
It is the single most important limit on recall in this run and is stated in the
headline of `RESULTS.md`, not in a footnote.

## 4. Frozen parameters

### 4.1 Detector configuration (`TrialConfig`)

| Field | Value | Why this and not the default |
| --- | --- | --- |
| `keys` | `("Enter", "Space")` | Default is `("Enter","Space","ArrowDown")`. Dropping `ArrowDown` removes 1 of 4 trials per probe (≈25% of the cost). It is a **recall-reducing** ablation: a control operable only by ArrowDown will now be reported as a violation. Registered as a bound, not hidden. |
| `include_hover` | `True` (default) | Unchanged. |
| `settle_ms` | `250` (default) | Unchanged. |
| `collect_coverage` | `False` (default) | Unchanged; keeps the run comparable to runs made before coverage existed. |
| `viewport` | `1920x1080` | KAFE §5.1. |
| `max_tabs` | **per subject**, see §4.2 | The brief's central correction: 300 is a default, not a parameter. |

### 4.2 The tab cap is derived per subject, before any probe runs

Measured on a fresh replayed page, after load + 3000 ms settle:

```
F = document.querySelectorAll(
      'a[href], button, input, select, textarea, summary, iframe,
       [tabindex], [contenteditable=""], [contenteditable="true"],
       audio[controls], video[controls]'
    ), counting only elements that are
      - not [tabindex="-1"]
      - not disabled
      - rendered (width>0 or height>0, display!=none, visibility!=hidden)
    plus the same count inside every open shadow root.
```

```
max_tabs = min(4000, max(300, 2 * F + 100))
```

`F` and `max_tabs` are recorded per subject in the raw output. The factor of two
plus a hundred is headroom for stops the selector does not predict (shadow DOM,
`tabindex` on non-listed elements, browser-inserted stops). The hard ceiling of
4000 bounds worst-case cost; a subject whose walk is still `capped` at 4000
**abstains** and is never scored negative.

**If `TabOrder.capped` is true after the derived cap, the whole subject
abstains.** This is the brief's non-negotiable and is checked before any probe.

### 4.3 Per-subject budget (deliverable B)

Registered because the brief authorizes a stated bound and forbids an
undisclosed one.

- **Candidate cap `N` = 12** probes per subject, plus up to **2 in-harness
  positive controls** (§6.2 layer 2), for at most 14 probes per subject.
- **Downward-only adjustment.** After the 2-subject smoke test, if measured
  per-subject cost implies the 53-subject run exceeds **75 minutes**, `N` is
  reduced — never increased — to the largest value that fits, and the new value
  is written to `derived/manifest_scored.json` **before** the 51-subject run
  starts. No ground-truth label may inform that choice, and none will: the
  adjustment reads only elapsed seconds.
- **Per-subject wall-clock timeout: 240 s.** On expiry the subject stops; probes
  not yet run are recorded as `not-run`, and the subject is scored on what
  completed (a violation already found still makes the page positive; a page with
  **no** completed probe abstains as `timeout`).
- **Repeats: 1.**

**Candidate ordering** — deterministic, label-blind, applied to the output of the
frozen `collect_candidates`, keeping only candidates that carry a `data-probe`:

| Tier | Rule |
| --- | --- |
| 0 | signals include `onclick-attr` or `onclick-prop` |
| 1 | signals include `aria-role` |
| 2 | tag ∉ {a, button, input, select, textarea, summary, details} **and** signals include any of `cursor-pointer`, `class-lexicon`, `tabindex` |
| 3 | everything else |

Sort by `(tier, document order)` ascending; take the first `N`. Document order is
the order `collect_candidates` returns, which is DOM order.

This ranking is **mine, not the detectors'**, it is a second recall ceiling
stacked on top of the candidate generator's own, and it is reported as such. It
is registered before the run and is not tuned afterwards.

**In-harness positive controls.** Up to 2 elements per subject chosen
structurally, never by label: the first two candidates in document order whose
tag is `button`, or `a` with an `href`, or `input`/`select`/`textarea`, **and**
which appear in the measured tab order. They are added to the probe set beyond
`N`. Their expected verdict is not `VIOLATION`. A control reported as
`VIOLATION` is recorded per subject and totalled; per §6.2 an over-reporting
harness voids a run, and if controls fail at scale `RESULTS.md` reports the run
as a harness failure presenting as a result (§6.7 bucket 1), not as accuracy.

### 4.4 Replay parameters (deliverable B)

- **Entry document** = the census entry for the subject in
  `derived/kafe_corpus_census.json` (the **first** HTTP 200 `text/html` response
  in capture order). This is the same field `tools/kafe_denominator.py` used to
  decide replayability, so the run and its denominator agree by construction.
  The largest-body heuristic in `tools/feasibility_run.py` is **not** used; both
  URLs are recorded per subject so the choice is auditable.
- **A fresh `ReplayRouter` per browser context.** The router holds a per-(url,
  method) cursor that advances on every request; sharing one across the
  detectors' per-trial contexts would serve trial 2 a different response from
  trial 1 and make the differential compare two different pages. Each trial gets
  its own router over the same immutable `ExchangeIndex`.
- **Default-deny.** Anything not in the capture is aborted and counted. No
  network. Served/denied counts and the essential-denial list are recorded per
  subject (aggregated across that subject's routers).
- **Element identity.** `data-probe` is assigned at document-start by an init
  script from **structural path alone** (`0:body/3:div/1:a`), never from a label,
  class or text. Assigned on `DOMContentLoaded` and again on `load`, idempotently
  (an element that already has one keeps it). Path identities are stable across
  fresh contexts in a way a global counter is not.
- `service_workers="block"`, `locale=en-US`, `timezone_id=UTC`.
- Navigation timeout 60 s; post-load settle 3000 s→ **3000 ms** for the survey
  page only. The detectors' own trials use their own frozen 80 ms + `settle_ms`.

### 4.5 Deliverable A (GDS) parameters

- Page: `artifacts/gds/test-cases.html`, loaded from `file://`. No replay router.
- The 8 cases are exactly those in `tools/gds_run.py`: 6 IAF positives
  (`fake-button`, `concertina`, `tooltip-icon`, `dropdown-submenu`,
  `lightbox-close`, `role-button-space`) and 2 negative controls (`real-button`,
  `real-link`).
- `data-probe` is set on the 8 target elements by an init script at document
  start, by the same CSS selectors `gds_run.py` uses. No other element is tagged
  — the GDS ground truth is positional and per-case, so the probe set is the case
  set.
- **No reveal step.** `gds_run.py` force-revealed `display:none` ancestors. The
  frozen detectors have no such step, and adding one outside them would be
  measuring my harness again. A case whose target is not rendered will produce
  `UNKNOWN`/`not_rendered` and is reported as an **abstention**, not as a miss
  and not as a catch.
- `max_tabs` from §4.2's formula on this page.
- **2 repeats**, case order reversed on the second. Disagreement between repeats
  is reported as instability, not resolved in favour of either.

## 5. Scoring rules, fixed in advance

### 5.1 Element level

The detectors' own `Verdict`, unmodified: `VIOLATION`, `NO_LEAD`, `UNKNOWN`
(with its `Uncertainty` reason retained).

### 5.2 Page projection (deliverable B)

KAFE's unit is the page. For a subject that did not abstain:

```
yhat = 1  iff  at least one non-control probe returned VIOLATION
yhat = 0  otherwise
```

A `UNKNOWN` probe never contributes a positive and never blocks a negative in the
**primary** matrix. It does in the sensitivity matrices (§5.4).

### 5.3 Abstention (the subject is scored in neither class)

Checked in this precedence, first match wins:

| # | Bucket | Trigger |
| --- | --- | --- |
| 1 | `unreadable-capture` | `ExchangeIndex.unreadable > 0` (this is `godaddy`, registered in §6.3 as expected) |
| 2 | `no-entry-document` | census `entry` is null |
| 3 | `replay-failed` | navigation raised, or HTTP status not 2xx/3xx |
| 4 | `tab-cap` | `TabOrder.capped` true at the derived cap |
| 5 | `timeout` | 240 s expired with zero completed probes |
| 6 | `no-candidates` | `collect_candidates` proposed zero tagged candidates |
| 7 | `all-unknown` | every non-control probe returned `UNKNOWN` |

Buckets 1 and 2 are known before execution: `godaddy` abstains on 1; `4shared`
and `dmv_fl` are already outside the 53 on 2. Predicting them here makes their
abstention a prediction rather than a discovery.

`essential-degraded` (§6.3 priority 4) is **recorded as a flag** — essential
denials are counted and listed per subject — but is **not** applied as an
abstention bucket in this run, because doing so on a 2021 capture replayed in
2026 would abstain nearly everything and the brief asks for numbers. That is a
deliberate, disclosed departure from §6.3 precedence and it makes the primary
matrix **more permissive** than §6.3 allows. The sensitivity in §5.4 shows what
applying it would do.

### 5.4 What is reported, always together

1. **Primary matrix** on the non-abstaining labelled set `E`: TP/FP/FN/TN,
   precision and recall as **exact fractions**, never rounded percentages.
2. **Coverage**: `|E|/|L|` with `|L| = 53`, positive and negative coverage
   separately, and `|E| + A+ + A− = |L|` checked.
3. **Pessimistic abstention sensitivity** (§6.6): `TPw=TP`, `TNw=TN`,
   `FNw=FN+A+`, `FPw=FP+A−`.
4. **Essential-denial sensitivity**: the primary matrix recomputed with every
   subject carrying ≥1 essential denial moved to abstention.
5. **Unknown-pessimistic sensitivity**: the primary matrix recomputed with every
   subject that has ≥1 `UNKNOWN` probe and 0 `VIOLATION` moved to abstention.
6. **Reference side by side**: KAFE recomputed on the same `E`, from
   `artifacts/kafe_results_to_reproduce.csv` via `derived/kafe_denominator.json`.
   Never against 36/39.

### 5.5 Timing

- **Unit: one keyboard actuation trial against one candidate** — one
  `_key_trial` call, covering the Tab walk to `position−1`, the final Tab, the
  key press, both settles and the snapshot read. This is the §6.4 unit.
- Reported as median / p95 / max **per corpus and per subject**, plus the count
  and identity of every trial over **300 ms**.
- The reportable outcome is `held` or `exceeded`. **No speed comparison against
  KAFE is made.** The 33.6 ms/15-Tab figure is not restated.
- Timing never changes a verdict.
- Mouse-trial ms and whole-probe ms are recorded separately and are **not**
  offered as per-button numbers.

**Registered expectation, so it is not spun afterwards:** the frozen
`_key_trial` contains three unconditional `settle_ms` waits of 250 ms each plus
`position−1` Tab presses. **I expect essentially every actuation trial to exceed
300 ms**, i.e. the cap to be **exceeded**, and I expect the excess to be
dominated by the detector's own deliberate settle waits rather than by anything
page-dependent. If that is what happens it is a fact about the frozen
configuration, not a defect discovered by this run, and `RESULTS.md` will say so
in exactly those terms.

## 6. Predictions and falsification criteria

Lifted from `FEASIBILITY.md` §6.7, restated against this run's actual bounds.

> **H1 (target).** On the common set `C`, `R_A = R_K` and `P_A > P_K`, with
> `R_K`, `P_K` recomputed on that same `C`.

On `C` = all 53 that means: report all 31 positives, and at most 1 false positive
across the 22 negatives. `bowiestate` and `dell` are the only two pages where
precision can be gained.

**H1 is falsified by** any of: one missed positive; two or more false positives;
an abstention pattern leaving either metric undefined.

- **P-A.** Axcess reports `bowiestate` = 0 and `dell` = 0.
  *Falsified if either is reported 1.* If either fails, the only available
  precision gain is gone and H1 is dead at that point.
- **P-B.** Axcess reports all 31 positives.
  ***This is the prediction I expect to fail.*** Registered as such before the
  run, as in §6.7: the detectors' `candidates − TabOrder` half sees only the
  unreachable form of IAF, and only the D9 behavioural differential sees the
  reached-but-not-actionable half. On production pages I expect misses in the
  second half. The candidate cap of §4.3 and the dropped `ArrowDown` key both
  push in the same direction, which makes a P-B failure **over-determined and
  therefore uninformative about the detectors alone** — a point `RESULTS.md`
  must make rather than claiming the detectors were measured on recall.
- **P-C.** Abstentions do not consume the comparison.
  *Falsified if `|E| < 40` of 53, or if either `bowiestate` or `dell` abstains.*
  Either makes the run inconclusive under §6.7 bucket 1 regardless of other cells.

### Additional predictions specific to this run

- **P-D (harness over-reporting).** The in-harness positive controls of §4.3
  return non-`VIOLATION` on at least 90% of subjects where at least one control
  ran. *Falsified below 90%.* A failure here means the harness reports correct
  native controls as defects, and under §6.2 the accuracy numbers are then void
  rather than merely caveated. **I consider this the most likely single point of
  failure in the run**, because the `dom` channel digests `body.innerHTML` and a
  replayed page with a timer, carousel or lazy-loading script mutates on its own
  between the before- and after-snapshots of *both* modalities, producing
  non-equal effects with no user action involved.
- **P-E (GDS, deliverable A).** The frozen detectors report ≥1 of the 6 GDS IAF
  cases as `VIOLATION` and 0 of the 2 controls. *Falsified if they report a
  control, or if all 6 positives come back `NO_LEAD`.* I do **not** predict 6/6:
  at least `dropdown-submenu` and `lightbox-close` target elements hidden behind
  `display:none` in the page's natural state, and the frozen `_LOCATE_JS` returns
  `not_rendered` for those, which is `UNKNOWN` — an abstention. The reference
  (all 13 audited tools score 0/6) is the comparison; an abstention is not a
  catch and is not counted as one.
- **P-F (tab cap).** With `max_tabs` from §4.2, the GDS walk completes
  (`capped = False`) where the 300 default capped it. *Falsified if it is still
  capped.*

## 7. Outputs

| File | Content |
| --- | --- |
| `derived/manifest_scored.json` | Frozen manifest: re-verified detector hashes, browser build, all §4 parameters including any downward `N` adjustment, subject list and run order |
| `derived/gds_frozen.json` | Every GDS case × repeat, raw, including failures |
| `derived/kafe_scored.jsonl` | One line per subject, **appended as each completes** |
| `RESULTS.md` | The tables of §5.4, timing of §5.5, and the verdict on each prediction of §6 |

Every raw run is kept, including failures. `RESULTS.md` separates **verified**
(I ran it, and the raw file reproduces it), **claimed** (a document asserts it)
and **assumed**. No number appears in `RESULTS.md` that the raw files cannot
reproduce.
