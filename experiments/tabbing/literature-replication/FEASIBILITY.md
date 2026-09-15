# Feasibility: offline replay of original KAFE subjects

Phase output for manager gate 2. **No detector was run, no page was scored, no
truth file was read.** Every number below is a feasibility observation produced
by code in `tools/`, aggregated programmatically into `derived/`.

Baseline `fc5a1d5be193212c44f4b92b57a3fbb0679eb1eb`, branch `tabbing`.
Executed 2026-09-14. Browser Chromium 145.0.7632.6, Playwright 1.58.0,
Python 3.14.7.

---

## 1. Headline

The premise that blocked the previous phase was wrong, and so was one of my own
claims. Both are corrected here.

| Question | Answer | Evidence |
| --- | --- | --- |
| Are the KAFE captures readable? | **Yes** — mitmproxy flow dumps, readable with the standard library | `derived/capture_census.json` |
| Do they replay offline in Chromium 145? | **Yes** — 12/12 runs loaded | `derived/feasibility.json` |
| Is anything essential missing? | **No** — 0 essential denials on all three | `derived/feasibility_summary.json` |
| Is a label-independent element census stable? | **Yes** on all three | G1 below |
| Does tagging perturb the page? | **No** measurable change on all three | G1 below |
| Does keyboard interaction work offline? | **Yes** — 11–15 distinct focus stops | §4 |

**So a scored arm on original KAFE subjects is feasible.** It is not yet
approved, and §6 gives the revised protocol for that decision.

---

## 2. What was downloaded

Total **1,901,962 B** (1.81 MB) against the authorized 150 MB cap. Enforced in
code by `ByteBudget`, which refuses a spend before bytes move. Nothing was
fetched recursively. All bytes live under `artifacts/`, excluded by this
experiment's own `.gitignore`; only derived metadata is committed.

| File | Source | Bytes | SHA-256 (first 16) |
| --- | --- | --- | --- |
| `kafe_supplementary_appendix.pdf` | Drive `14g3qBzRM52i5FWvf07mbypwFyha7FgOM` | 186,545 | `83e600f3ede9735f` |
| `kafe_results_to_reproduce.csv` | Sheet `1Hy9-lFflGnmm-8eztyM3Zz3hzwvAyWSF6wZlcpAb3LU` | 14,545 | `6cb9582c921a1b7a` |
| `subject_citiprogram.bin` | Drive `1ECmdsdNts4ESRiCMOwAOInqygpxLkKEb` | 355,234 | `a189e020e42e1d7d` |
| `subject_craigslist.bin` | Drive `1lqexuhi9YWfX3tX9FUs5bl7evqX-7_zk` | 290,887 | `a001a96fc7d455f7` |
| `subject_coronavirus.bin` | Drive `1RusN8l55kKtkvxCVkJqHa4ML5xkfGtvJ` | 1,054,751 | `2827425aee17ba7a` |

Full records with final URLs and complete hashes: `artifacts/MANIFEST.json`.
Subject Drive ids for all 50 listed items: `derived/kafe_subjects_index.json`.

**Licence is still unresolved.** Nothing in the folder states one, and the
captures are of third-party commercial sites. These bytes are held locally for
inspection and are not redistributed or committed. That constraint has not
changed and is not something this phase could clear.

---

## 3. Format — verified, not assumed

Each subject file is a **mitmproxy flow dump**: a concatenation of
tnetstring-encoded dicts. Every sample begins
`<len>:7:version;1:7#4:mode;11:transparent;`, i.e. flow format version 7,
transparent mode. This matches KAFE §5.2 ("captured a complete version of each
subject web page using an interactive HTTP proxy").

`tools/flowfile.py` reads it with the standard library only — no install. One
detail differs from the published tnetstring spec and matters: mitmproxy uses
`;` for unicode strings and `,` for raw bytes.

| Subject | Flows | Unique URLs | Hosts | HTML 200s | Body bytes | Unreadable |
| --- | --- | --- | --- | --- | --- | --- |
| citiprogram | 21 | 21 | 6 | 1 | 209,450 | 0 |
| coronavirus | 24 | 24 | 8 | 1 | 879,352 | 0 |
| craigslist | 13 | 13 | 4 | 2 | 158,427 | 0 |

Every flow carried a response; nothing was responseless; no stream had an
unreadable tail. The entry documents recovered from the captures are
`https://www.citiprogram.org/index.cfm?pageID=14`,
`https://www.coronavirus.gov/` and `https://losangeles.craigslist.org/` —
consistent with the appendix URLs.

### A real bug, found and fixed

The first replay attempt reported every page loading "successfully" with 4–8
elements. That was **my harness bug, not a capture defect**: mitmproxy stores
*raw* bodies, and I was stripping `content-encoding` and serving compressed
bytes, which Chromium rendered as text. Encoding counts are citiprogram
br=2/gzip=6, coronavirus gzip=14/br=2, craigslist gzip=11/br=1.

`prepare_response` now decodes gzip and deflate in Python and passes brotli
through with its header for Chromium to decode (the standard library has no
brotli, and installing one is out of scope). Both the broken and fixed runs are
preserved; §4 reports only the fixed run, and says so.

---

## 4. Replay results

Conditions: viewport 1920×1080 (KAFE §5.1), `wait_until="load"` + 3 s settle,
60 s navigation cap, service workers blocked, default-deny routing, fresh
context per run, 2 repeats × {untagged, tagged} × 3 subjects = 12 runs.

**12/12 loaded. Spread across repeats was exactly 0 elements on every subject.**

| Subject | Appendix #Total | Observed | ratio | Appendix #Visible | Observed | ratio | Essential missing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| citiprogram | 57 | 80 | 1.403 | 43 | 35 | 0.814 | 0 |
| coronavirus | 121 | 164 | 1.355 | 118 | 119 | **1.008** | 0 |
| craigslist | 1522 | 1540 | **1.012** | 851 | 829 | **0.974** | 0 |

craigslist — the largest and most structurally complex of the three — replays
within 1.2% on total elements and 2.6% on visible elements. That is the
strongest single fidelity signal available, because a broken replay of a
1,522-element page would not land that close by accident.

The citiprogram and coronavirus `#Total` ratios near 1.36–1.40 are **not
explained yet**. The most likely cause is a counting-definition difference
(KAFE's Java crawler may exclude `html`/`head`/`script`/`meta` nodes that
`querySelectorAll('*')` includes), not a replay failure — coronavirus's
*visible* count matches to within 0.8%, which would be a remarkable coincidence
if the page were rendering wrongly. This is a hypothesis; §6 makes it a
pre-registered check rather than an assumption.

### Denied requests, classified (G4)

Only citiprogram denied anything: **4 Google Analytics `/r/collect` beacons**,
correctly classified `benign_tracking`. coronavirus and craigslist denied
nothing at all. No subject lost an essential resource, so none is functionally
degraded. This is exactly the distinction G4 asked for: egress blocking working
as intended is not a broken capture.

### Errors observed and retained

- coronavirus: one page error, `Invalid or unexpected token` — a script parse
  failure. Possibly a brotli passthrough Chromium rejected, possibly a capture
  artefact. **Unexplained; flagged, not dismissed.**
- craigslist: `Blocked a frame with origin "https://www.craigslist.org" from
  accessing a cross-origin frame` — ordinary same-origin policy against an
  iframe, expected.

### Safe interaction with egress blocked

15 `Tab` presses per run, no clicks and no form submission. Distinct focus
stops: citiprogram 11, coronavirus 15, craigslist 15 — **in both arms**.
Keyboard navigation works on replayed captures.

**Superseded figures.** An earlier version of this section reported these same
11/15/15 counts without noting they were tagged-only; the untagged arm then
recorded 3/1/1. That gap was a probe defect, not a page difference: the probe
read the census attribute and fell back to `tagName` when it was absent, so the
untagged arm was counting distinct tag names. The 3/1/1 figures are retracted.
`replay.FOCUS_PROBE_JS` now identifies elements by structural path in both arms.
Raw runs from before the fix are kept at `derived/feasibility.pre-focus-fix.json`.

**Identity scope (gate-2 finding R4).** The structural probe still collapsed
identities in two scopes: every direct child of one shadow root received the
host's path, and focus inside a frame reported the frame element, so every stop
inside it shared one string. Both are now identified — a shadow child carries
its index within its root, a same-origin frame is descended and the crossing is
kept in the path. A frame this context may not read cannot be identified from
here at all; it now returns `replay.OPAQUE_SCOPE` instead of a value that looks
like an ordinary stop, and `tools/adjudicate_g1c.py` refuses to adjudicate a
trail containing it. Verified by executing the probe against real DOMs in
Chromium 145 (`tests/test_focus_probe_browser.py`), not by reading its source.

The counts above are **unchanged** after that fix and a full re-run: none of the
three captures puts a focus stop inside a shadow root or a frame within 15
presses, and no trail contains an unsupported-scope marker. The defect was
latent here, as it would not have been on a page using web components.

---

## 5. G1 — the neutral census hypothesis, tested

G1 asked me to treat harness-side tagging as a falsifiable possibility rather
than a guaranteed fix. Two predictions were registered and both held:

- **G1a, stability.** The census assigns ids from tree position only
  (`NEUTRAL_CENSUS_JS`; a test asserts the script contains no `data-probe`,
  `truth`, `violation` or `decoy` token, so it cannot prefer a known element).
  Prediction: identical id sets across fresh contexts. Observed: **identical on
  all three subjects**, 80 / 164 / 1540 ids.
- **G1b, inertness.** Prediction: tagged and untagged runs produce identical
  DOM signatures. Observed: **identical total, visible and per-tag counts on
  all three subjects**.

Scope of the claim: this shows the census is stable and DOM-inert *on these
three captures, in this browser, under these conditions*. It does not show
tagging is harmless in general, and it does not show the frozen detectors
behave identically with it — that is a separate control in §6.

- **G1c, focus-order inertness.** Registered in `PREREGISTRATION-G1c.md` before
  the run, because G1b covered DOM signature only and said nothing about focus
  order — the dimension a keyboard detector actually depends on. Prediction:
  tagged and untagged focus trails identical, element for element. Observed:
  **identical on all three subjects**, 11 / 15 / 15 stops in both arms, with
  within-arm spread 0 across repeats. Control (P3): the probe discriminated on
  3/3 subjects, so H0 did not pass by a probe returning a constant.

  H0 was falsifiable and survived. Had any trail diverged, the census would be
  rejected for focus-dependent measurement and the scored arm stopped.
  Adjudicated by `tools/adjudicate_g1c.py`, which reports every prediction.

  **Re-adjudicated after R3/R4 (2026-09-14).** The adjudicator now validates the
  registered matrix — 3 subjects x 2 arms x 2 repeats, one record per cell,
  exactly 15 presses, every run `ok` — and emits a single validity-gated
  disposition: a P1 or P3 failure yields VOID, and H0 survival cannot be printed
  for a run the pre-registration voids. Duplicate records are a validity failure
  instead of a silent overwrite, and comparisons read only the first 15 presses.
  Re-run under the fixed probe and the stricter adjudicator, the matrix is valid,
  P1 holds, P3 discriminates 3/3 and the disposition is unchanged:
  **H0 NOT FALSIFIED**, 11 / 15 / 15 stops in both arms.

**I also withdraw my earlier claim** that the frozen detectors cannot enumerate
candidates without `data-probe`. `collect_candidates` in
`src/audit/analyzer/kbdiff/candidates.py` already walks
`root.querySelectorAll('*')` and records `probe: probe || null`. G1 was right
and my previous blocker B2 was wrong. The real limitation is narrower: an
untagged candidate has no stable identity across runs, which is what the census
supplies.

---

## 6. Scoring protocol for the 53-subject run

Rewritten 2026-09-14 by Claude Code against the real corpus. This supersedes the
previous §6 (manager revision by gpt-6-astra for R1/R2/R7) and the scoring
proposal in `PROTOCOL.md`; it does not supersede any retained raw observation.

Two things forced the rewrite, and both are recorded rather than quietly folded
in. **The previous target hypothesis is falsified as stated**, because it was
written against a three-subject denominator on which it was arithmetically
unreachable (§6.7). **The denominator itself changed**, from 3 authorized
subjects to 53 replayable ones (§6.1). What survives unchanged from the previous
revision is the part that was sound: the exclusive outcome buckets and their
precedence (§6.3), repeat aggregation (§6.5), the undefined-denominator rule and
abstention sensitivity (§6.6), and the page-versus-element separation (§6.8).

Detectors under `src/audit/analyzer/keyboard/kbdiff/` and `score.py` stay frozen.
A protocol edit authorizes no download, no crawl and no corpus expansion. R6
(brotli fidelity) is **unresolved and not waived here**; R5 (request matching
ignores bodies) stays deferred until interactive subjects.

### 6.1 Scope, denominator and claim ceiling

**IAF only**, at **page × IAF, binary**: functionality unreachable by keyboard,
or reachable but not keyboard-actionable. KTF, localization and BAGEL KNF
classes remain out of scope. A proxy for keyboard problems is not silently
relabelled as a complete IAF detector.

#### The inventory, and why it is 53 and not 60

All 60 published subjects stay in the inventory. Seven are excluded from
execution, each for a stated, auditable reason, and none becomes an implicit
true negative:

| Exclusion | Subjects | n | y=1 | y=0 |
| --- | --- | --- | --- | --- |
| Folder-form on Drive; expanded asset directories, no flow dump exists | `battlenet`, `canon`, `dmv_wc`, `gizmodo`, `speedway` | 5 | 4 | 1 |
| Capture parses to no HTML entry document (corrupt length prefix on record 0) | `4shared`, `dmv_fl` | 2 | 1 | 1 |
| **Total excluded** | | **7** | **5** | **2** |

`dmv_wc` is one of the two excluded negatives and is also one of KAFE's three IAF
false positives, which is why the reference precision denominator changes below.

A magic scan recovers 52/74 and 15/30 exchanges from `4shared` and `dmv_fl`, but
neither yields an entry document, so neither is replayable at any effort this
protocol authorizes.

**So N = 53 executable pages, all of them labelled: 31 IAF-positive, 22
IAF-negative, 0 label-unknown.** Derived by `tools/kafe_denominator.py` from
`artifacts/kafe_results_to_reproduce.csv` and `derived/kafe_corpus_census.json`,
gated on two controls: the full-corpus recompute must reproduce the published
TP=36 FP=3 FN=0 TN=21, and the excluded rows must account for exactly the
per-class difference between the full and subset counts.

**The exclusion is label-correlated, and that is a limitation, not a footnote.**
Five of the seven excluded subjects are IAF-positive (71%, against a corpus base
rate of 60%). The positive rate moves from
36/60 = 60.0% to 31/53 = 58.5%, which is small, but the mechanism — whatever made
those captures folder-form or corrupt — is not known to be independent of page
complexity, and page complexity is plausibly correlated with having a keyboard
failure. No result on the 53 may be described as a result on KAFE's corpus. It is
a result on a 53/60 subset whose exclusions are enumerated above.

#### The reference threshold, recomputed on this exact subset

§6.6 forbids comparing metrics computed on different retained subsets, and that
rule binds the reference as hard as it binds Axcess. KAFE's published 36/39 is
**not** the threshold for this run. Restricted to the same 53:

| | TP | FP | FN | TN | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- |
| KAFE, full 60 (published) | 36 | 3 | 0 | 21 | 36/39 | 36/36 |
| **KAFE, replayable 53** | **31** | **2** | **0** | **20** | **31/33** | **31/31** |

Only two of KAFE's three IAF false positives — `bowiestate` and `dell` — survive
into the 53; `dmv_wc` is folder-form. Those two pages are the entire source of
precision room in this comparison. If Axcess is clean on both and complete
everywhere else, it wins; there is no third page where it can gain.

**Claim ceiling.** Historical Firefox 68 outputs against a current Chromium
replay confound browser, capture fidelity and detector, and the two are not
separable by anything in this protocol. This is a fidelity-conditional
descriptive contrast on a named subset. It is not a replication, not evidence of
corpus-wide improvement, and not a published-style claim that Axcess beats KAFE.
Reference recall on this subset is 31/31: it can be matched or lost, never
improved.

#### What "Axcess" names in this comparison must be frozen before the run

The comparison is only meaningful if the thing compared is identified. The
manifest of §6.2 must name the exact detector entry point, module path and
version under test, and state whether the scored run **imports the frozen
detectors** or **reimplements their mechanism in harness code**. These are not
the same claim and must never be reported as if they were. Arm 1's
`tools/gds_run.py` is the second kind — its own docstring says the detectors are
"untouched and unimported-from" — so arm 1's 6/6 validates a *mechanism*, not the
shipped detectors, and cannot be cited as evidence about them. If the scored run
is also a reimplementation, every result in it inherits that same limit and the
report must say so in its headline, not its caveats.

### 6.2 Freeze and controls before a scored run

Freeze a manifest of subject IDs, artifact/source hashes, browser/environment,
the detector entry point and version under test (§6.1), the IAF output mapping
for each method, exact axe keyboard-rule IDs, candidate and TabOrder
definitions, action/termination budgets, and the run order **before predictions
or labels are used for scoring**. Missing manifest fields block execution rather
than permit post-hoc choices. An output mapping must distinguish an IAF
prediction, a proxy prediction, a completed negative, and UNKNOWN. No truth
label may guide candidate discovery, budget selection or threshold choice — and
the labels for all 53 are already known to this session, so the manifest is the
only thing standing between that knowledge and a retrofitted result. Freeze it
first; that is the whole point of freezing it.

Retain two runnable same-replay comparators: axe-core as shipped with the
frozen keyboard-rule list, and `candidates − TabOrder` with its frozen rule.
They are proxy baselines, not claims to cover the entire IAF construct. Run all
methods on the same captures, browser, viewport and registered interaction
budget; document any method-specific action differences. Report historical
KAFE/WAVE/QualWeb outputs separately, never as same-replay controls.

Use tagged and untagged detector runs in fresh contexts. Normalize identities
by the same label-independent structural scheme in both arms, not by a tag-only
fallback. If normalized outputs or completion/UNKNOWN states disagree, reject
the census and stop the scored arm; do not retain whichever arm scores better.
Existing G1c results remain accepted feasibility evidence, not a substitute for
this detector-output control.

#### Negative controls are mandatory, and the corpus does not supply them all

A harness that flags everything scores perfect recall and looks correct. Arm 1
found five defects, and **every one was caught by a control reading impossibly,
not by reading the code** — a synthesised `detail === 0` click that made nothing
reportable, a navigation that destroyed the counter, modality cross-contamination
through `window.open`, a reveal step that made a `display:none` element look
Tab-reachable, and a Space requirement that would have reported every link on the
web. Four of the five produced *confident wrong numbers* rather than errors. The
same five failure modes are available on these 53 subjects and this protocol
assumes they will recur.

Three control layers are required, and a failure in any of them voids the run
rather than being noted beside it:

1. **Corpus negatives.** The 22 IAF-negative subjects. These are the primary
   false-positive evidence and are not optional or subsettable after the fact.
2. **In-harness positive control.** At least one element per subject known to be
   correctly keyboard-operable — a native `button`, `a[href]`, or focusable
   form control found structurally, never by label. If the harness reports these,
   it is over-reporting and the run is void regardless of its confusion matrix.
3. **Mechanism controls.** Each of arm 1's five defects has a specific reading
   that proves it absent: trusted pointer input must produce `detail !== 0`;
   activation counters must survive the trial; each modality must run in its own
   fresh context; reachability must be read in the page's natural state before
   any reveal; expected keys must be role-dependent. Record the observed value
   for each, per subject. An unrecorded control is a failed control.

A run in which no subject is ever reported, or every subject is reported, is a
harness failure presenting as a result, and §6.7 bucket 1 applies.

### 6.3 Run dispositions and precedence (R2)

For each subject × method × tagging arm × repeat, keep every observed failure
flag, but assign exactly one primary disposition by the following precedence
(topmost applicable wins). “Not reached” cells after a stop are recorded too.

| Priority | Primary bucket | Rule | Abstention? |
| --- | --- | --- | --- |
| 1 | `unreadable-capture` | Capture cannot be decoded/parsed completely | yes |
| 2 | `no-entry-document` | Readable capture has no usable entry document | yes |
| 3 | `timeout` | Any registered run deadline exceeded | yes |
| 4 | `essential-degraded` | Essential resource denial or demonstrated functional break, including an unresolved script/decoding failure affecting validity | yes |
| 5 | `unsupported-scope` | Required identity/interaction scope cannot be observed, including an opaque focus marker | yes |
| 6 | `invalid-run` | Missing/duplicate/malformed record (other than an explicit planned `not-run` cell), detector error, incomplete attempted action budget or unclassified execution failure | yes |
| 7 | `unknown` | Method emits UNKNOWN or cannot complete a definite page decision | yes |
| 8 | `not-run` | Planned cell not attempted because the arm stopped | yes |
| 9 | `benign-degraded` | Completed run with only demonstrated nonessential denials | no |
| 10 | `ok` | Completed definite decision without any preceding condition | no |

Examples: timeout plus an essential denial is `timeout`, with the denial kept
as a secondary flag; an essential denial plus UNKNOWN is `essential-degraded`.
Any UNKNOWN relevant to IAF makes the run abstain even if other elements were
reported; retain those reports as diagnostic evidence. A negative requires a
completed observation, not an empty list returned after failure. Media is not
inherently benign: only a denial shown irrelevant to the registered IAF actions
can use `benign-degraded`. Uncertain functional validity is not promoted to ok.

For a planned three-repeat run, report disposition counts per method and arm
against **N × 3 = 159 cells per method per arm**, including stopped cells; never
pool arms or methods into independent page observations. Report the planned and
actually attempted counts separately. Failure flags are supplementary counts and
may overlap; primary buckets must sum to the planned denominator.

**Subjects already known to be at risk of abstaining**, registered here so that
their abstention is a prediction rather than a discovery. `godaddy` (y=1) parses
to 3 flows out of a 1.0 MB capture with `unreadable: 1`, so most of its stream is
not being read; it is the most likely `essential-degraded` or `count-misaligned`
page in the set. `ancestry`, `raise` and `tinyurl` carry 2 responseless flows
each, `stickermule` 7, `walmart` 1. `coronavirus` retains the unexplained
`Invalid or unexpected token` script error from §4 (B10) and cannot be promoted
to `ok` while that is open. None of these is excluded in advance — each is
executed and allowed to abstain on its own evidence.

### 6.4 Annotations that are not correctness: fidelity and timing

Both quantities in this subsection are recorded *beside* the accuracy verdict.
Neither is an accuracy result, and neither may be promoted to a headline.

#### Replay fidelity (R7)

Retain the visible-count diagnostic: `count-aligned` iff
`0.90 ≤ observed #Visible / appendix #Visible ≤ 1.10`, otherwise
`count-misaligned`; a missing/zero reference gives `count-unassessable`.
The `Size of All Visible Nodes` column of
`artifacts/kafe_results_to_reproduce.csv` supplies a reference count for all 53,
so `count-unassessable` should not occur; if it does, that is a bug in the
lookup and not a property of the page.
Use the worst annotation across repeats (unassessable before misaligned before
aligned). This is distinct from execution disposition. Report each stratum
separately, including its abstentions; count misalignment alone does not erase
a completed prediction. Only count-aligned pages without unresolved functional
fidelity questions may enter a fidelity-qualified comparison.

Neither matching element counts nor zero essential *denials* proves functional
fidelity. This explicitly supersedes the functional-fidelity inference in §4
(“none is functionally degraded”); its recorded load/denial counts are retained.
R6's brotli behavior and the unexplained coronavirus script error remain
unresolved, not a successful fidelity control. Do not attempt R6 or install a
decoder under this task. Scoring requires its decision/clearance separately.

`#Total` is not an eligibility gate. Retain the prospective diagnostic that
excluding `html/head/script/meta/link/style/title` brings citiprogram and
coronavirus within ±10% of appendix `#Total`; failure means unexplained counting
difference, not permission to change the exclusions or dismiss fidelity risk.

#### Timing: 300 ms is a per-button cap, not a result

Harry's constraint, recorded here because it governs how timing may be reported:
**300 ms is a ceiling the detector must not exceed per button. It is not a number
to report as a win.** The measurement answers one question — does the cap hold? —
and the reportable outcome is `held` or `exceeded`, with the distribution given
for diagnosis.

- **Unit.** One button, meaning one keyboard actuation trial against one
  candidate element: focus, key press, settle, read. Not a page, not a run, not a
  press within a Tab sweep. Report the per-button distribution (median, p95, max)
  per subject, and the count and identity of every button exceeding 300 ms.
- **What is retracted.** The earlier figure of **33.6 ms for 15 Tab presses is
  withdrawn as a per-button figure** — it measured a whole Tab sweep, which is a
  different unit. The per-press cost inside it was 2.1 ms. Neither number may be
  restated as a per-button result.
- **No speed comparison against KAFE is authorized.** The published 19.22 min is
  reproduced to 0.54% by summing seven phase columns read as milliseconds
  (19.12 min), and that total is proxy setup, node extraction and crawling
  infrastructure, not detection. KAFE's Detection phase alone averages **995 ms**,
  and 8 of the 60 subjects already finish under 300 ms. A "faster than KAFE"
  headline built on the 19-minute figure would be beating infrastructure with a
  detector, and is forbidden by this protocol. The 995 ms figure is also not the
  cap's comparator: KAFE's Detection phase is per page, the cap is per button, and
  the two units are not interchangeable.
- **Exceeding the cap does not change any prediction.** A button over 300 ms is
  reported as over 300 ms; it is not reclassified, dropped, or turned into an
  abstention. Timing and accuracy are separate axes and stay separate.

### 6.5 Repeat aggregation and page labels (R1/R2)

Use **three repeats per subject per method per tagging arm**, fresh contexts;
retain individual outputs and within-condition spread. A repeat is not a new
subject. Register the run order before execution; perform one planned pass.
Any later rerun is a separately identified series alongside all original runs,
including failures, not a replacement or an opportunity to choose a winner.

Aggregate before scoring, first within each tagging arm: all three repeats
must be non-abstaining and have identical normalized IAF reported-element sets
and definite page decisions. After both arms pass and agree, use that one set
and decision once for the page-method, not once per arm. Do not vote, average
scores, or union different repeats. If any repeat abstains, the subject-method
abstains, with the highest-priority failing run bucket as its reason. Otherwise
any disagreement gives subject bucket `unstable` (also an abstention), even if
the page-positive bits happen to agree. Retain the tagged/untagged agreement
control separately; a failed control voids the arm, not just a convenient page.

For a completed subject-method, prediction `yhat = 1` iff its frozen IAF mapping
reports at least one element; else `yhat = 0`. Human element adjudication does
**not** remove a prediction or redefine page-positive. Reference page label
`y = 1` iff the appendix/sheet reports at least one IAF, and `y = 0` iff it
explicitly reports none. Conflicting, missing or undecidable page labels form
`label-unknown`: never infer a label from a detector or from missing data.
Keep these pages in the authorized-count/coverage table but outside labelled
confusion matrices, even when execution is complete. Report execution status
and label availability as separate axes to avoid double-counting.

### 6.6 Page confusion matrices, coverage and abstentions (R1/R2)

For each method and named stratum, let `L` be the known-label pages, `E` the
non-abstaining subset of L after repeat aggregation, and `A+` / `A-` the counts
of abstaining pages in L whose labels are positive / negative.

On this corpus **`N = |L| = 53`**, because every replayable subject carries an
explicit TRUE/FALSE Type 1 ground truth, so label availability `|L|/N = 53/53`
and `label-unknown = 0`. A `label-unknown` page appearing in the output is
therefore a reader bug — a cell that is neither `TRUE` nor `FALSE` must never be
coerced to `FALSE` — and not a property of the corpus. On E:

- `TP = count(y=1, yhat=1)`; `FN = count(y=1, yhat=0)`.
- `FP = count(y=0, yhat=1)`; `TN = count(y=0, yhat=0)`.
- `P = TP/(TP+FP)`; `R = TP/(TP+FN)`.
- `F1 = 2TP/(2TP+FP+FN)` when its denominator is nonzero.

A zero denominator is **undefined**, never 0 or 1 by convention. Report raw
counts, `|E|/|L|` labelled coverage, positive and negative coverage separately,
label-unknown count, and `|L|/N` label availability; any zero coverage denominator
is likewise undefined. Check `TP+FP+FN+TN = |E|` and
`|E|+A+ + A- = |L|`. Also report execution coverage on all N pages, separately
from labelled coverage. No dropped page disappears from the N-page inventory.

Report the complete-case matrix above beside a **pessimistic abstention
sensitivity**, not a claim that abstentions were observed predictions:
`TPw=TP`, `TNw=TN`, `FNw=FN+A+`, `FPw=FP+A-`.
Thus `Pw=TP/(TP+FP+A-)`, `Rw=TP/(TP+FN+A+)`, and
`F1w=2TP/(2TP+FP+FN+A+ + A-)`, subject to the same undefined rule.
A positive abstention is a hypothetical FN; a negative abstention is a
hypothetical FP, **never a FN or TN**. The sensitivity matrix sums to |L|.
Label-unknown pages cannot enter even this matrix; give their counts rather
than invent truth. This replaces “count every abstention as a miss”.

Paired method comparisons use one explicitly enumerated common set: known
labels, non-abstaining for both methods, count-aligned and no unresolved
functional-fidelity questions. Recompute both matrices on that same set and
report its coverage against N plus each method's own full inventory and
pessimistic sensitivity. Never compare precision computed on different retained
subsets. Empty/one-class sets or undefined metrics yield an inconclusive
comparison, not a favorable result.

### 6.7 The target hypothesis, and mutually exclusive comparison outcomes (R1/R7)

#### What was falsified

The previous §6.7 set the target as "equal recall with higher precision" against
a three-subject denominator of `citiprogram`, `craigslist`, `coronavirus`.
Recomputed from KAFE's own CSV, KAFE scores **TP=2, FP=0, FN=0, TN=1** on exactly
those three — **precision 1.0, recall 1.0**. All three of its IAF false positives
lie outside that set. So on the set the target was written for, "higher precision"
required exceeding 1.0 and the target could only tie or lose. **It was not a hard
target; it was an unreachable one, and a prediction that cannot succeed is as
uninformative as one that cannot fail.** It is withdrawn, not restated.

#### The target on the real denominator

On the 53 the target becomes reachable, and therefore worth registering.

> **H1 (target).** On the common set `C` of §6.6, `R_A = R_K` and `P_A > P_K`,
> where `R_K` and `P_K` are KAFE's recall and precision **recomputed on that same
> `C`** from `artifacts/kafe_results_to_reproduce.csv`.

H1 is stated against a recomputed reference, not against a fixed fraction,
because `C` is whatever survives abstention on both methods and §6.6 forbids
comparing metrics taken on different retained subsets. The fixed fractions
**31/33** and **31/31** are the values of `P_K` and `R_K` in the single best case
`C` = all 53; they are the target's expected shape, not its definition. If `C` is
smaller, both sides are recomputed on `C` and the threshold moves with it.

Stated in counts for the `C` = 53 case, because the fraction hides how narrow it
is: H1 requires Axcess to report **all 31 positive pages** — one miss and recall
is lost — while producing **at most 1 false positive across the 22 negatives**,
since `31/(31+2) = 31/33` is a tie, not a win. The only two pages where precision
can be gained are `bowiestate` and `dell`, KAFE's surviving false positives. H1
is falsified by any of: one missed positive, two or more false positives, or an
abstention pattern that leaves either metric undefined.

A consequence worth naming, because it makes H1 harder than it looks: since
`R_K = 1` on every subset of this corpus (KAFE has no false negatives anywhere in
the 60), `R_A = R_K` always means **perfect recall on `C`**, whatever `C` turns
out to be. Shrinking the common set never relaxes the recall half of the target.
It only shrinks the precision denominator, which makes the precision half more
brittle, not easier — hence P-C below.

Three things follow, and all three are predictions that can fail:

- **P-A.** Axcess reports `bowiestate` = 0 and `dell` = 0. If it reports either,
  the only available precision gain is gone and H1 is dead at that point. This is
  the single most informative pair of cells in the run.
- **P-B.** Axcess reports all 31 positives. Recall is the fragile half: the
  detectors cover KAFE's IAF construct only partially — D0 and D2–D8 see the
  *unreachable* half through `candidates − TabOrder`, and only the D9 behavioural
  differential can see the *reached-but-not-actionable* half (`LITERATURE.md` §3).
  On real production pages the second half is where I expect misses, so **P-B is
  the prediction I expect to fail**, and recording that expectation before the run
  is the point of recording it at all.
- **P-C.** Abstentions do not consume the comparison. If `|E|` on the common set
  falls below 40 of 53, or if either `bowiestate` or `dell` abstains, the run is
  inconclusive under bucket 1 regardless of the other cells, because a precision
  comparison resting on two pages cannot survive losing one of them.

Neither the accuracy target nor its falsification depends on the 300 ms cap
(§6.4). A run that holds the cap and misses a positive has still failed H1; a run
that exceeds the cap and satisfies H1 has satisfied H1 with a recorded cap
violation. They are not traded against each other.

#### Ordered outcome buckets

Apply these ordered buckets separately to each named comparator and fixed
common set, using exact integer counts/rational comparisons, never rounded
display percentages. These are descriptive outcomes, not statistical
non-inferiority tests or evidence of causal superiority.

1. **Inconclusive / not comparable**: a validity control fails; either metric
   is undefined; either label class is absent; or required paired labels,
   outputs or fidelity evidence are unavailable. A pilot cannot receive a
   corpus-wide historical improvement classification.
2. **Equal recall, higher precision — conditional**: `R_A = R_B` and `P_A > P_B`.
3. **Exact metric tie**: `R_A = R_B` and `P_A = P_B`.
4. **Recall loss**: `R_A < R_B`, regardless of any precision gain; report that
   tradeoff explicitly, never call it non-inferiority.
5. **Other tradeoff / no target gain**: all remaining defined cases, including
   higher recall against a runnable baseline or equal recall with lower precision.

H1 is bucket 2. A valid bucket 3–5 falsifies H1 on that set; bucket 1 leaves it
undecidable. Coverage and sensitivity always accompany the conditional result; a
selective complete-case gain cannot be promoted to a full-corpus claim.

**The threshold is 31/33, not 36/39.** The historical full-corpus counts in
`LITERATURE.md` (TP=36, FP=3, FN=0, TN=21, precision **36/(36+3)**, recall
**36/(36+0)**) are a 60-page result; comparing against them would compare metrics
computed on different retained subsets, which §6.6 forbids. The reference
recomputed on the 53 actually executed is **31/(31+2)** and **31/(31+0)**.
Equality with 31/33 is a tie, not an improvement over a rounded 92.3% or 93.9%;
comparisons use the exact fractions. A genuine full-corpus comparison would need
the 5 folder-form and 2 unparseable subjects, which are unavailable at any effort
this protocol authorizes. Even complete data would support only the
fidelity-conditional historical contrast, not a reproduction of Firefox 68
results. The old 97% margin and “strict dominance/non-inferiority” labels are
withdrawn, as is the three-page formulation of the target.

### 6.8 Element adjudication is a different estimand (R1)

Freeze and hash every raw reported element **before human adjudication**, with
subject, method, arm, repeat, normalized census/structural identity, IAF mapping
and evidence, in `artifacts/adjudication/<subject>.jsonl`. Do not write that
ledger until scoring is authorized. Preserve repeated raw rows but deduplicate
by `(subject, method, stable element identity, IAF)` for the aggregate ledger;
duplicate findings for the same element are not extra true positives. Failed or
unstable subjects' reports remain diagnostic and are tallied separately, not
silently added to the scored element denominator.

A human labels each scored reported element `true`, `false`, or `undecidable`
for the registered IAF construct. Let these counts be T, F and U:
`P_element_decidable = T/(T+F)`; adjudication coverage `(T+F)/(T+F+U)`;
precision bounds `[T/(T+F+U), (T+U)/(T+F+U)]`.
Every zero denominator is undefined. Report U prominently; never drop U and
present decidable-only precision as unconditional. The ledger only covers
reported elements: without a separately frozen exhaustive independent truth
universe, element FN/TN, recall and F1 are **not estimable**. Do not borrow page
fault totals to manufacture element recall. These element precision quantities
never replace page precision and are never compared with KAFE's page threshold.

### 6.9 Release gate

Before scoring:

1. Independent Codex disposition on this rewritten §6. **The author of this
   section does not review it** — that rule is why every defect but two in this
   experiment was found by someone other than its author.
2. Separate R6 (brotli fidelity) clearance or decision. Not waived here, and not
   this section's to waive.
3. A complete frozen execution manifest per §6.2, including the answer to §6.1's
   question about whether the run imports the frozen detectors or reimplements
   their mechanism.
4. A pre-registration file carrying H1, P-A, P-B and P-C with their falsification
   criteria, written before execution.
5. Explicit manager approval within Harry's authorized scope.

R5 stays deferred but must be revisited before interactive subjects are scored.
A passing documentation review alone does not satisfy these prerequisites.

### 6.10 Standing limits that no result in this section can clear

Recorded together so they are not rediscovered as caveats after a number exists.

| Limit | Status |
| --- | --- |
| Firefox 68 unavailable; Chromium 145 only | **Permanent.** Browser, capture fidelity and detector are confounded and not separable here. |
| Licence unresolved on `artifacts/` | **Permanent.** Local inspection only; never commit, publish or redistribute those bytes. Applies to every output derived from them. |
| R6 brotli passthrough unvalidated | **Open.** Not waived by this rewrite. |
| B10 `coronavirus` script parse error | **Open, unexplained.** Blocks `ok` on that subject. |
| 7 subjects unexecutable, 6 of them positive | **Permanent.** Label-correlated exclusion; see §6.1. |
| Detectors cover IAF only partially | **Structural.** D0/D2–D8 see the unreachable half; only D9 can see reached-but-not-actionable. |

---

## 7. Exact runnable commands

```bash
cd experiments/tabbing/literature-replication
uv run --offline --no-sync pytest tests/ -q                      # 52 passed
uv run --offline --no-sync python -m tools.fetch_kafe list       # Drive ids
uv run --offline --no-sync python -m tools.fetch_kafe labels     # 201,090 B
uv run --offline --no-sync python -m tools.fetch_kafe subjects   # 1,700,872 B
uv run --offline --no-sync python -m tools.inspect_format        # format proof
uv run --offline --no-sync python -m tools.census_flows          # capture census
uv run --offline --no-sync python -m tools.feasibility_run       # 12 browser runs
uv run --offline --no-sync python -m tools.analyze_feasibility   # summary table
```

## 8. Blockers

| ID | Status |
| --- | --- |
| B1 licence | **unresolved** — blocks expansion beyond the 3 samples |
| B2 `data-probe` | **withdrawn** — was my error; see §5 |
| B3 Firefox 68 unavailable | **open, permanent** — fidelity caveat, Chromium-only |
| B4 mitmproxy replay | **resolved** — `tools/flowfile.py` + `tools/replay.py` |
| B5 BAGEL folder 404 | unavailable to that request; alternates unchecked |
| B10 coronavirus script parse error | **open, unexplained** |
| M1 method-blind router | **fixed** by manager — `resolve()` ignored `method`, so a POST was answered with a GET's captured body. Latent on these three captures (GET-only, no duplicate URLs), a correctness bug at 60 subjects where forms are reached. 6 tests, RED then GREEN. |
| M2 focus-probe control gap | **partially fixed** — census-dependent identity removed, but the five tests asserted on the *source text* of `FOCUS_PROBE_JS` and could not fail when the behaviour was wrong. "5 tests, RED then GREEN" is retracted as evidence of correctness; the residual collapse is R4. |
| R4 focus-probe identity collapse | **fixed** — shadow-root children and frames, see §4. 4 behavioural tests in Chromium plus 1 perturbation control; the sibling-shadow and same-origin-frame tests were RED against the shipped probe. |
| R3 G1c adjudicator not validity-gated | **fixed** — registered-matrix validation and one gated disposition, see §5. 11 tests, 7 of them RED before the code that answers them existed. |
