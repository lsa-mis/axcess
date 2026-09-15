# Three-arm status — GDS complete, KAFE corpus acquired

Manager: Opus 5 (claude-opus-5). Written after running arms 1 and 3's
acquisition. Supersedes the N=3 framing in `HANDOVER.md` and the falsified
target hypothesis in `FEASIBILITY.md` §6.7.

## Why the experiment changed shape

The northstar is unchanged: replicate the published tabbing/clicking
differential environment, run the frozen Axcess detectors on it, and find out
whether they do better. Two facts recovered this session changed how that can
be answered.

**KAFE scores a perfect 1.0/1.0 on the three previously authorized subjects.**
Recomputed from the authors' own `kafe_results_to_reproduce.csv` (control: the
full-corpus recompute reproduces the verified TP=36 FP=3 FN=0 TN=21):

| Subject | GT | KAFE result | TP | FP | FN |
| --- | --- | --- | --- | --- | --- |
| citiprogram | TRUE | TRUE | 1 | 0 | 0 |
| craigslist | TRUE | TRUE | 1 | 0 | 0 |
| coronavirus | FALSE | FALSE | 0 | 0 | 0 |

All three of KAFE's IAF false positives (`bowiestate`, `dell`, `dmv_wc`) sit
outside that set. At N=3 a precision comparison can only tie or lose, which
**falsifies the "equal recall with higher precision" target** frozen into §6.7
one session earlier. That target is withdrawn.

**The 19.22 min figure is not detection.** Reading the artifact's phase columns
as milliseconds reproduces the published mean to 0.54% (19.12 vs 19.22), and
that total is proxy setup, node extraction and crawling. KAFE's *Detection*
phase alone averages 995 ms, and 8 of 60 subjects already finish under 300 ms.
Any "faster than KAFE" claim built on 19 minutes would be beating
infrastructure, not a detector.

Harry's clarification: **300 ms is a per-button cap the detector must not
exceed, not a number to report as a win.** An earlier floor measurement in this
session (33.6 ms for 15 Tab presses) measured the wrong unit and is retracted as
a per-button figure; the per-press cost within it was 2.1 ms.

## Arm 1 — GDS: RETRACTED as a detector result, see `PREMISE-CORRECTION.md`

> **The 6/6 below did not test the frozen Axcess detectors.** `tools/gds_run.py`
> imports only Playwright; `kbdiff` appears in its docstring and nowhere in its
> code. The result measured a reimplementation of the differential idea written
> for this experiment, so it is not evidence about the shipped detectors and does
> not answer the objective. Claude Code caught this by challenging the brief's
> premise; none of the five negative controls below could have, because every one
> tested whether the harness read *the page* correctly and all five passed.
>
> Running the **frozen** detectors on the same case returns `no_lead`, not
> `violation`: the GDS page has 306 focusable elements against a 300-press
> default tab cap, so the walk is capped and the detector correctly refuses to
> call an unproven absence a violation. At cap 1200 the walk completes and
> unreachability becomes certain. The reimplementation was more confident, not
> more correct. Arm 1 must be re-run through the frozen detectors before any GDS
> number is quoted again.

`alphagov/accessibility-tool-audit`, **MIT, Crown Copyright (GDS) 2017**,
archived 2021, 89 stars. Self-contained: `test-cases.html` plus jQuery and a
2.4 KB `main.js`. No licence blocker, no replay layer, servable as static files.

142 cases across 19 categories; 16 under "Keyboard Access"; **6 match KAFE's IAF
construct** (5 unreachable-half, 1 reached-but-not-actionable). Every one of the
**13 audited tools scores 0/6** on them — axe, WAVE, Tenon, SortSite,
Siteimprove and the rest — a published third-party baseline of zero on exactly
this failure class.

Result after four harness corrections (`tools/gds_run.py`):

```
case                  kbd-reach  mouse   Enter   Space   reported
fake-button           False      True    False   False   True
concertina            False      True    False   False   True
tooltip-icon          False      True    False   False   True
dropdown-submenu      True       True    True    True    True
lightbox-close        False      True    False   False   True
role-button-space     True       True    True    False   True
real-button  CONTROL  True       True    True    True    False
real-link    CONTROL  True       True    True    True    False
```

**TP=6 FN=0 FP=0 TN=2 — precision 6/6, recall 6/6, reproducible across repeats
with order reversed.** Both negative controls stay clean, which is what makes
the six meaningful: a harness that flagged everything would score the same
recall and fail here.

Scope limits, stated plainly: these are 6 hand-built snippets on one page, not
production pages, and only one exercises the reached-but-not-actionable half.
This validates mechanism, not real-world accuracy. The 0/6 baseline is quoted
from GDS's own published results, not re-run here.

### Four harness defects, each caught by a control rather than by reading code

Logged because every one would have produced a confident wrong number:

1. **`element.click()` synthesises `detail === 0`**, which the harness read as
   keyboard activation. Every case came back mouse-negative and *nothing could
   ever be reported* — the first run scored 0/6. Fixed with trusted pointer
   input at real coordinates, which also restores hit-testing.
2. **Navigation destroyed the counter.** Enter on a real link committed a
   navigation and wiped `window.__hits`, throwing rather than reporting.
3. **Modality cross-contamination.** Pressing Enter on the fake button called
   `window.open`, detaching the page the following mouse trial measured. This
   produced results that changed between repeats. Fixed by giving every
   modality its own context — the same reason the production `DifferentialRunner`
   opens a fresh context per trial.
4. **The reveal step created a false pass.** Force-showing hidden scopes so
   there was a box to click also made a `display:none` submenu look
   Tab-reachable. Reachability is now read in the page's natural state, before
   any reveal. Confirmed by `tools/gds_diagnose.py`: `display:none`,
   `rendered:false`, not Tab-reachable naturally.

A fifth was caught at the last step: keying on Space for *any* link reported
`real-link` as a false positive, because Space scrolls on every focused link
including correct ones. Expected keys are now role-dependent. Without the
control that FP would have shipped inside a clean-looking 6/6.

`tools/gds_diagnose.py` records the two diagnoses empirically: the submenu is
unreachable naturally, and Space on `a[role=button]` scrolled the document
945 px instead of activating — the registered GDS defect, invisible to
listener-counting.

## Arm 3 — KAFE full corpus: acquired, not yet scored

The paginated Drive listing capped at 50 items and had silently lost ten
subjects. Drive's `embeddedfolderview` endpoint returns all 60 in one response;
`tools/fetch_kafe_all.py` uses it and resolves **60/60 names to file IDs**.

| | Count |
| --- | --- |
| Fetched this session | 52 |
| Already held | 3 |
| **Single-file subjects on disk** | **55 / 60** |
| Folder-form, not fetched | 5 (`battlenet`, `canon`, `dmv_wc`, `gizmodo`, `speedway`) |
| Download errors | 0 |

82.0 MB against the authorized 157.3 MB cap; all 52 hashes unique; none
suspiciously small. Everything is under `artifacts/`, which this experiment's
`.gitignore` excludes — verified with `git check-ignore`.

`tools/kafe_corpus_census.py` parses all 55: **3,178 flows, 3,164 exchanges,
53/55 carry an HTML entry document.**

`4shared` and `dmv_fl` are excluded, and an earlier claim about them is
**corrected here**: they are *not* a different container format. Both carry the
identical mitmproxy magic (`<len>:7:version;1:7#4:mode;11:transparent;`) as
files that parse cleanly. The actual defect is a **corrupted length prefix on
record 0** — `4shared` declares 69,928 bytes when the next record starts at
69,725, overrunning by 203 — so the terminator lands mid-payload and the chain
breaks immediately. A magic scan finds 74 and 30 intact records respectively and
recovers 52/74 and 15/30 exchanges, but **neither yields an HTML entry
document**, so neither is replayable. Recorded, not silently dropped; the
replayable count stays 53.

**Licence, resolved as far as research can take it.** The paper carries only
"© 2021 Copyright held by the owner/author(s)" — ACM's author-retained notice,
covering the paper. No artifact badge, no Zenodo deposit, no terms file, and the
captures are third-party commercial sites the authors never owned. Harry
authorized local gitignored inspection; that authorization covers reading these
bytes and does **not** extend to committing, publishing, or redistributing them.
That constraint attaches to the outputs and stays attached.

## Arm 2 — Ma11y: mutation operator validated

`mahantaf/web-a11y-tool-analyzer`, **MIT**, Puppeteer, 31 WCAG
failure-technique mutation operators. Puppeteer 25.11.0 installed at
`arm2/node_modules` with Harry's approval.

**Its browser download was blocked and does not need unblocking.** npm refused
puppeteer's `postinstall` (not covered by `allowScripts`), so no Chrome was
fetched and `puppeteer.launch()` fails with "Could not find Chrome (ver.
153.0.8010.36)"; `~/.cache/puppeteer` is empty. Passing `executablePath` to the
Playwright Chromium already on disk launches successfully and reports
**Chrome/145.0.7632.6**, with F54 applying normally under it. So arm 2 needs no
second browser download, and it runs on the *same engine* as arms 1 and 3 --
which removes an engine confound rather than introducing one.

```
executablePath: ~/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome
```

This is the arm that breaks the small-N ceiling. Arms 1 and 3 are both capped by
how many labelled failures somebody else happened to build — 6 for GDS, 36
positives across 60 pages for KAFE. Mutation analysis *generates* faults, so
ground truth is known by construction and N is bounded by compute instead.

**F54 validated before further investment** (`tools/ma11y_probe.py`). The
operator moves an element's `onclick` handler to `onmousedown`, which is exactly
mouse-operable-but-not-keyboard-operable. Pre-registered: the mutation converts
a working control into a mouse-only one; falsified if the mutant still activates
by keyboard. Control: the same element unmutated must stay keyboard-operable —
without it, an already-broken element would look like a successful mutation.

| Condition | Mutation applied | Keyboard | Mouse |
| --- | --- | --- | --- |
| control | no | **yes** | yes |
| mutated | yes | **no** | yes |

N=2 per condition with order alternated, identical results both ways.
**H-mut not falsified: F54 manufactures a genuine IAF with known ground truth.**

A generator emitting equivalent (non-faulty) mutants would quietly inflate
recall on a corpus nobody hand-checked, which is why this was tested before
building on it. F42 (links emulated with script) is downloaded and unread.
Ma11y's own corpus is one site (`adp.com`); the framework is the asset, not its
subjects. Nothing beyond this single-operator validation has been run.


## What is verified vs claimed

**Verified by running it here:** the GDS 6/6 with controls and repeats; all five
harness defects and their fixes; the two FN diagnoses; 55/55 KAFE subjects parse
with per-subject flow counts; 60/60 name-to-ID resolution; the KAFE per-subject
recompute and its full-corpus control; the ms-unit reading of the timing columns.

**Claimed by the sources, not re-run:** GDS's 0/6 for 13 tools; KAFE's published
Table 1; Ma11y's operator behaviour beyond the two files read.

**Not established:** any Axcess-vs-KAFE accuracy comparison on real production
pages. That needs the 53 replayable subjects scored, which is a separate gate
with its own pre-registration — and §6 still needs rewriting first, since its
target hypothesis is falsified and the 300 ms cap is not recorded in it.
