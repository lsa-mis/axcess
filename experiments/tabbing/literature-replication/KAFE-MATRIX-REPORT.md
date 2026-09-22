# KAFE matrix: report

Companion to `KAFE-MATRIX.md`. Generated 2026-09-19T15:36:51.760508+00:00.
Everything below is derived from `derived/kafe_matrix.jsonl`,
`derived/kafe_matrix_summary.json` and `derived/kafe_matrix_controls.json`;
no figure in this file is typed by hand.

## 1. What I could not close

### 1.1 The candidate universe is Axcess's own, and that flatters Axcess

`candidate_analysis.measure_candidate_page` raises unless its feature sweep
covers exactly the probe set, so `data-probe` could only be placed on elements
`audit.analyzer.keyboard.kbdiff.candidates.collect_candidates` had already
surfaced. Every one of the 48 rows is therefore scored on a shortlist that
Axcess's own collector drew. The upstream generators (`U-D*`) and every `C*`
combination are structurally unable to propose an element it missed, so their
recall is bounded by a competitor's recall. **This is the largest threat to
validity in the table and it is not closed.** Closing it needs a universe
defined independently of any detector under test — KAFE's own
`Size of All Visible Ctrl Nodes` is such a definition, but their node-selection
code was not published with the CSV, so it could not be reproduced here.

### 1.2 6 subjects replay to a document with no controls in it

- `indiegogo` — 12 elements, 0 focusable, KAFE label `True`
- `instagram` — 135 elements, 0 focusable, KAFE label `False`
- `mozilla` — 13 elements, 0 focusable, KAFE label `False`
- `sciencedirect` — 10 elements, 0 focusable, KAFE label `False`
- `whitepages` — 7 elements, 0 focusable, KAFE label `False`
- `capitalone` — 20 elements, 51 focusable, KAFE label `False`

These are counted as abstentions, never as negatives. That matters: some carry
a KAFE `TRUE` label, and scoring them as negatives would have manufactured a
false negative in all 48 rows off a replay defect. What is *not* closed is
**why** they replay empty — a capture that needs a live XHR, a script the
default-deny router refused, or a page that builds itself from state the capture
does not contain. The replayed document is not the document KAFE analysed, and
no result here describes those subjects.

### 1.3 7 subjects cap their tab walk

- `spotify` — cap 212 (12 focusable)
- `salesforce` — cap 238 (38 focusable)
- `raise` — cap 262 (62 focusable)
- `costco` — cap 269 (69 focusable)
- `dell` — cap 297 (97 focusable)
- `dpreview` — cap 294 (94 focusable)
- `cnn` — cap 483 (283 focusable)

The budget is `focusable + 200`, the convention
`tools/kafe_scored_run.py` established. A walk that still caps is an abstention
by the brief's own rule. Re-walked afterwards by `kafe_matrix capdiag` with a
4000-press ceiling, through the same discovery pass, the same
`data-probe` set and the same frozen walker the scored run uses, so the stop
counts below are the same measurement as `tab_stops` in the matrix:

- `cnn` — 67 named stops in 4000 presses; from press 167 focus leaves the page and re-enters on a 2-position orbit (`#el:body:119`, `#el:iframe:965`); **not decided** — see below
- `costco` — 37 named stops in 4000 presses; from press 39 focus leaves the page and re-enters on a 2-position orbit (`#el:iframe:355`, `#el:body:17`); **not decided** — see below
- `dell` — 32 named stops in 4000 presses; **focus trap** on a 1-position loop (`/343:a`) from press 36, with the page holding focus throughout
- `dpreview` — 92 named stops in 4000 presses; from press 95 focus leaves the page and re-enters on a 3-position orbit (`#el:iframe:368`, `#el:iframe:369`, `#el:body:47`); **not decided** — see below
- `raise` — 45 named stops in 4000 presses; from press 2531 focus leaves the page and re-enters on a 49-position orbit (`#el:a:217`, `#el:a:219`, `#el:a:222`, `#el:a:224` and 45 more); **not decided** — see below
- `salesforce` — 5 named stops in 4000 presses; from press 9 focus leaves the page and re-enters on a 2-position orbit (`#el:body:42`, `#el:iframe:131`); **not decided** — see below
- `spotify` — 7 named stops in 2645 presses; **completes** — terminates at 2645 presses; headroom was short by 2433

1 of these (`spotify`) completes the walk at the higher ceiling and was an abstention only because the `focusable + 200` budget was too tight; 6 still cap. The published numbers are unchanged either way — they were measured at the derived budget, and this diagnosis is not a re-score.

The diagnosis was run 3 times over independent page loads, because one reading cannot separate a property of the subject from a property of the load. 5 gave the same answer in all 3 (`costco`, `dell`, `dpreview`, `salesforce`, `spotify`) — which is agreement across these runs, not a guarantee. `cnn`, `raise` agreed on capping and on the shape of the walk but not on how many of its stops carry a probe id — the same identity instability §1.4 records. Every run's output, earlier ones whose JSON a later run overwrote included, is in `derived/capdiag-runs.log`.

5 of them (`cnn`, `costco`, `dpreview`, `raise`, `salesforce`) share one mechanism, and it is **not** a page defect. Their walk settles into a loop in which `document.hasFocus()` is false: Tab steps out of the page to the browser's own UI, and the next Tab re-enters at the position it left from rather than at the first stop. `compute_tab_order` means to end a walk exactly there — its comment calls it "focus left the document (browser chrome)" — but it detects that as `document.activeElement === null`, and `activeElement` falls back to `<body>` instead of going null, so the branch never fires and the budget runs out. These subjects are abstentions for an instrument reason, and **nothing here says whether the site traps a keyboard user**. Deciding that needs a walker whose termination test is `document.hasFocus()` rather than a null `activeElement`, which is a change to a frozen detector and out of scope for this run.

Where a terminal loop is named, the walk was observed a second time on
a fresh page with the walker's own focus reader, and the loop is the positions
it repeated to the end of the budget. That observation explains the cap; it
never overrides it — `capped` always comes from the frozen walker.

### 1.4 Element identity is not perfectly stable across page loads

Every trial addresses elements by a census id minted at `load` in its own fresh
context. Subjects where fewer than 95% of the discovered ids reappear on a
second load:

- `godaddy` — 19% of probe ids reappeared
- `wendys` — 4% of probe ids reappeared

Where this bites, `measure_candidate_page` raises
`candidate feature coverage differs from page probes` and its 19 rows abstain
for that subject. It is recorded, not repaired: making identity stable would
mean freezing the page, and a page that renders differently on two loads is a
fact about the subject, not about the detectors.

### 1.5 Arm failures on otherwise-scored subjects

- ValueError: candidate feature coverage differs from page probes: godaddy — 1 subject(s): godaddy
- ValueError: candidate feature coverage differs from page probes: thefreedictionary — 1 subject(s): thefreedictionary
- ValueError: candidate feature coverage differs from page probes: wendys — 1 subject(s): wendys
- no C9 lead set: the candidate arm failed — 3 subject(s): godaddy, thefreedictionary, wendys

Each failure abstains exactly the rows that arm produced and leaves the other
arms' verdicts standing.

### 1.6 Scope limits stated rather than solved

- **Coverage origin.** The D9/D10 coverage rules filter executed functions to
  the entry document's origin, which is upstream's own rule. A subject whose
  handlers live on a CDN has those functions filtered out, so its coverage sets
  are narrower than the page's real behaviour.
- **No `#baseline-target`.** Upstream's handler-free coverage floor is measured
  by clicking `#baseline-target`, which exists only in their fixtures. On every
  KAFE subject that resolves to `absent: no #baseline-target on this page`, i.e.
  an empty floor — the documented "absent", not a failed read, so the coverage
  rows still decide.
- **Candidates are top-frame only.** `collect_candidates` evaluates in the main
  frame, so a control inside an iframe is outside the universe on every row.
- **Upstream Stage 4's witness pool is one subject.** `bakeoff` runs it once
  over a whole corpus; here one subject is one page, so `D9u+S4u` searches a
  smaller pool for an equivalent control than it would on a multi-page corpus,
  and will dismiss less.
- **Not KAFE's browser.** KAFE ran Firefox 68 through Selenium; this is headless
  Chromium under Playwright 1.58.0 on
  Python 3.14.7. The ms columns are not comparable as
  hardware benchmarks, only as orders of magnitude, and every Axcess figure is
  wall time on one shared machine.

### 1.7 The comparison runs in one direction only

All 48 rows are Axcess detectors scored on KAFE's corpus. KAFE's detector was
never scored on ours. Its row here is their **published output** —
`artifacts/kafe_results_to_reproduce.csv`, their tool's real result on their own
60 subjects, reconciled against their paper's Table 1 by Control 1 below — and
not a local execution: their Java / Selenium 3.141.5 / Firefox 68 stack was not
rebuilt, and by decision it will not be. The reverse direction is out of scope
for this work, not queued behind it.

One part of it could not be closed even if it were in scope. KAFE emits
page-level labels; `fixtures`, `gds` and `ma11y` label elements. Running their
binary against those corpora would still need a projection invented between two
different units of truth, and that projection — not their detector — would
decide the result.

The asymmetry is not neutral, and it cuts both ways. Measuring our detectors on
someone else's corpus against their published numbers is the harder and more
exposed direction, and that is the direction taken. But it means nothing in this
work independently validates **our** corpora: `edgecases` is shared-author and
already carries no unbiased accuracy claim, and `fixtures` was authored here
too. No outside tool has been scored on either.

## 2. Controls

### Control 1 — KAFE reproduction: PASS

```json
{
  "n": 60,
  "tp": 36,
  "fp": 3,
  "fn": 0,
  "tn": 21,
  "precision": 0.9230769230769231,
  "recall": 1.0,
  "f1": 0.9600000000000001,
  "precision_pct": 92.3,
  "recall_pct": 100.0
}
```

Their published Table 1 reports 92% / 100%; recomputing from
`artifacts/kafe_results_to_reproduce.csv` gives 36/3/0/21 at 92.3% / 100.0% over
n=60. Their timing reproduces too:

```json
{
  "ms_per_subject_median": 1087.5,
  "ms_per_subject_mean": 995.2,
  "subjects_under_300ms": 8,
  "ms_per_button_median": 25.8,
  "ms_per_button_mean": 46.7,
  "ms_per_button_pooled": 20.0,
  "buttons_under_300ms_cap": "60/60",
  "detection_ms_total": 59711.0,
  "ctrl_nodes_total": 2992
}
```

### Control 2 — denominator: PASS

- KAFE's corpus: **60** subjects.
- Judged replayable beforehand: **53**.
- Attempted here: **52**. Scored: **39**.
  Whole-subject abstentions: **13**.

Excluded before the run ever started:

- `4shared` — capture parses to no HTML entry document
- `battlenet` — folder-form on Drive; no flow dump fetched
- `canon` — folder-form on Drive; no flow dump fetched
- `dmv_fl` — capture parses to no HTML entry document
- `dmv_wc` — folder-form on Drive; no flow dump fetched
- `gizmodo` — folder-form on Drive; no flow dump fetched
- `speedway` — folder-form on Drive; no flow dump fetched

Abstained during the run:

- `indiegogo` — the frozen candidate collector surfaced no addressable element (12 elements in the replayed document, 0 focusable): no button to decide about, so this is an abstention and not a negative
- `instagram` — the frozen candidate collector surfaced no addressable element (135 elements in the replayed document, 0 focusable): no button to decide about, so this is an abstention and not a negative
- `mozilla` — the frozen candidate collector surfaced no addressable element (13 elements in the replayed document, 0 focusable): no button to decide about, so this is an abstention and not a negative
- `sciencedirect` — the frozen candidate collector surfaced no addressable element (10 elements in the replayed document, 0 focusable): no button to decide about, so this is an abstention and not a negative
- `whitepages` — the frozen candidate collector surfaced no addressable element (7 elements in the replayed document, 0 focusable): no button to decide about, so this is an abstention and not a negative
- `spotify` — tab walk capped at 212 with 12 focusable elements
- `salesforce` — tab walk capped at 238 with 38 focusable elements
- `raise` — tab walk capped at 262 with 62 focusable elements
- `capitalone` — the frozen candidate collector surfaced no addressable element (20 elements in the replayed document, 51 focusable): no button to decide about, so this is an abstention and not a negative
- `costco` — tab walk capped at 269 with 69 focusable elements
- `dell` — tab walk capped at 297 with 97 focusable elements
- `dpreview` — tab walk capped at 294 with 94 focusable elements
- `cnn` — tab walk capped at 483 with 283 focusable elements

Never attempted:

- `craigslist`

The scored denominator in `KAFE-MATRIX.md` is **39**,
which is exactly the number of subjects that replayed and produced a verdict.

### Control 3 — negative control: PASS

15 subjects KAFE labels
`FALSE` were scored: `tinyurl`, `dmv_ca`, `bbc`, `venmo`, `coronavirus`, `bowiestate`, `walmart`, `roblox`, `ask`, `ancestry`, `ssa`, `ed`, `telegram`, `live`, `wiktionary`.

```json
{
  "subject": "tinyurl",
  "kafe_label": false,
  "detectors_recording_a_true_negative": 31,
  "detectors_abstaining": 0,
  "detectors_flagging": 17,
  "example_true_negatives": [
    "C10 = C9 minus redundant click surfaces (R1)",
    "C11 = C10 minus roving-tabindex items (R2)",
    "C12 = C11 minus declared shortcuts (R3)",
    "C13 = C12 minus leads with no action path (R5)",
    "C14 = C13 minus name-twinned leads (R6)"
  ]
}
```

The point of this control is that a detector which flags nothing on a genuinely
clean page records a **true negative**, not an abstention. The witness above
shows detectors doing exactly that.

### Control 4 — frozen code: PASS

```json
{
  "kbdiff package": "/var/home/me/Development/axcess/src/audit/analyzer/keyboard/kbdiff/__init__.py",
  "detectors": "/var/home/me/Development/axcess/src/audit/analyzer/keyboard/kbdiff/detectors.py",
  "differential": "/var/home/me/Development/axcess/src/audit/analyzer/keyboard/kbdiff/differential.py",
  "taborder": "/var/home/me/Development/axcess/src/audit/analyzer/keyboard/kbdiff/taborder.py"
}
```

Every module resolves under
`/var/home/me/Development/axcess/src/audit/analyzer/keyboard/kbdiff`. Nothing under
`src/audit/` was edited; `git diff --stat src/audit/` is empty and
`git status --porcelain` reports no change there, nor under
`experiments/tabbing/runner/` or `experiments/tabbing/probes/`. Nothing was
committed.

## 3. What the run found

- **39 subjects scored** of 52 attempted, of 60 in KAFE's corpus:
  24 KAFE-positive, 15 KAFE-negative.
- **4707 controls probed** in total across those subjects.
- On the same subjects, KAFE itself scores
  {"tp": 24, "fp": 1, "fn": 0, "tn": 14}.

Read the precision column with the page-level caveat in front of it. A page with
hundreds of candidates makes "flagged at least one element" nearly free, so a
row sitting at the corpus base rate has demonstrated almost nothing. The rows
worth attention are the ones that are *below* it — a detector that manages to be
worse than always saying yes — and the ms columns, which are measured and mean
what they say.

## 4. Strict versus permissive projection

`KAFE-MATRIX.md` uses the strict rule: a page is negative only where the
detector flagged nothing **and** left no candidate undecided. The permissive
rule lets any decided candidate license a negative. Rows where the two disagree:

- `D0 axcess collectClickables` — strict 17/9/5/5 (16 abst.), permissive 17/9/7/5 (14 abst.)
- `D1 axe-core (keyboard rules)` — strict 2/1/20/12 (17 abst.), permissive 2/1/22/13 (14 abst.)
- `D1x axe-core (any rule, unsound)` — strict 22/11/1/2 (16 abst.), permissive 22/11/2/3 (14 abst.)
- `D2 inline onclick attribute` — strict 5/2/17/11 (17 abst.), permissive 5/2/19/12 (14 abst.)
- `D2b onclick property` — strict 12/3/10/10 (17 abst.), permissive 12/3/12/11 (14 abst.)
- `D3 tabindex / ARIA` — strict 9/1/13/12 (17 abst.), permissive 9/1/15/13 (14 abst.)
- `D5 CDP getEventListeners` — strict 20/5/2/8 (17 abst.), permissive 20/5/4/9 (14 abst.)
- `D6 addEventListener shim` — strict 2/0/20/13 (17 abst.), permissive 2/0/22/14 (14 abst.)
- `D7 React fiber props` — strict 0/0/22/13 (17 abst.), permissive 0/0/24/14 (14 abst.)
- `D8 hover-diff` — strict 17/9/5/5 (16 abst.), permissive 17/9/7/5 (14 abst.)
- `C6 visible label for a toggle absent from Tab` — strict 0/1/20/13 (18 abst.), permissive 0/1/21/14 (16 abst.)
- `C15 = C14 minus leads with no click effect (R7, R8)` — strict 18/4/3/10 (17 abst.), permissive 18/4/3/11 (16 abst.)
- `C16 = C15 plus divergent-key-effect promotions (R9)` — strict 18/4/3/10 (17 abst.), permissive 18/4/3/11 (16 abst.)
- `D9 behavioural differential` — strict 22/8/0/0 (22 abst.), permissive 22/8/2/6 (14 abst.)
- `D9+S4ours coverage-armed differential, our payload Stage 4` — strict 23/8/0/0 (21 abst.), permissive 23/8/1/6 (14 abst.)
- `D9+S4u differential with upstream Stage 4 (coverage-exact)` — strict 24/12/0/0 (16 abst.), permissive 24/12/0/2 (14 abst.)
- `D9-noS4 coverage-armed differential, no equivalence filter` — strict 24/12/0/0 (16 abst.), permissive 24/12/0/2 (14 abst.)
- `D9u upstream-style differential (8 channels, keys in sequence)` — strict 19/12/0/0 (21 abst.), permissive 19/12/5/3 (13 abst.)
- `D9u+S4u upstream differential with upstream Stage 4 (1:1)` — strict 19/12/0/0 (21 abst.), permissive 19/12/5/3 (13 abst.)
- `D10a-u upstream coverage presence (sequential keys, baselined)` — strict 14/8/1/0 (29 abst.), permissive 14/8/10/7 (13 abst.)
- `D10b-u upstream coverage set-difference (sequential keys, baselined)` — strict 17/10/0/0 (25 abst.), permissive 17/10/7/5 (13 abst.)

Full permissive numbers: `derived/kafe_matrix_summary_permissive.json`.

## 5. Method notes

- **Seams, not re-implementations.** The cheap tier runs through
  `bakeoff.run_page`; `U-D*` and `C1`–`C9` through
  `candidate_analysis.measure_candidate_page`; `D9`/`D10` through
  `bakeoff.run_behavioural`; `C10`–`C16` from the four
  `experiments/tabbing/probes` observations fed to
  `tools.run_probe_rules.rule_sets`. The probe scripts call `asyncio.run` at
  module level and cannot be imported, so their observation JS is lifted out of
  their own AST rather than transcribed.
- **The brief named two seams; four were needed.** `run_page` and
  `run_behavioural` cover 22 of the 48 rows. The other 26 (`U-D0`–`U-D8`,
  `C1`–`C16`) live in `candidate_analysis` and the probe scripts, and are driven
  through those.
- **What the adapter changes.** Three module-level names are pointed at the
  subject for the duration of its measurement — `bakeoff.page_url` and
  `candidate_analysis.page_url` to the capture's entry URL, `bakeoff.BASE_URL`
  to its origin, and `TrialConfig`/`compute_tab_order` to this subject's derived
  tab budget. No detector body is touched; only arguments the frozen functions
  already accept.
- **Two adapter defects found and fixed before the measured run.**
  `replay.NEUTRAL_CENSUS_JS` numbers each document from zero, so an iframe's
  `<html>` and the top document's `<html>` both minted `/0:html`; sub-frame ids
  are now namespaced by document URL. And discovery originally re-censused three
  seconds after `load` while every trial censused at `load`, so the two
  disagreed about identity — on `fandango` that made 12 of 13 probes
  unobservable to every survey detector. Identity is now fixed at `load`
  everywhere. The pre-fix checkpoints are kept as
  `derived/kafe_matrix.pre-frame-fix.jsonl` and
  `derived/kafe_matrix.pre-identity-fix.jsonl`.
- **Milliseconds.** Composed by `tools/assemble_matrix.cost_of`, so the
  `ms covers` conventions match the existing matrix by construction.
  `ms/button` divides by the candidates that subject probed; `ms/subject` by the
  subjects measured. KAFE's two figures come from their `Detection` column over
  their `Size of All Visible Ctrl Nodes`, pooled the same way.
