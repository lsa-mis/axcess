# Literature and artifact recovery

Status: research only. No scoring, no detector edits, no measurement claims.
Baseline commit `fc5a1d5be193212c44f4b92b57a3fbb0679eb1eb`, branch `tabbing`.
Written 2026-09-14. Citation IDs refer to `sources.json`; URLs not yet in that
ledger are listed in [Pending sources](#pending-sources) for the manager to
register.

Every number below is either quoted from a primary text with a page/section
reference, or recomputed by this session from a named artifact. Recomputations
are marked **[recomputed]**. Nothing here is an Axcess measurement.

---

## 1. The two primary papers

### 1.1 KAFE — ESEC/FSE 2021 [1]

Chiou, Alotaibi, Halfond, *Detecting and Localizing Keyboard Accessibility
Failures in Web Applications*. Local copy: `3468264.3468581 (1).pdf` (13 pp.,
PDF CreationDate 2021-07-16).

Failure taxonomy (two types, scored separately):

- **IAF** — Inaccessible Functionality Failure: functionality a keyboard user
  cannot operate. This is **not** only unreachability. KAFE covers both
  functionality the Tab sequence never reaches *and* controls that are reached
  but cannot be actuated from the keyboard. Defining IAF as "unreachable" alone
  understates the construct, and an earlier draft of this file did so.
- **KTF** — Keyboard Trap Failure: a cycle the keyboard cannot leave.

Evaluation design (§5.1–5.3, pp. 8–9):

| Item | Value (primary text) |
| --- | --- |
| Detection unit | page × failure type, binary; IAF and KTF scored separately |
| Corpus | 60 captured subjects: 40 containing ≥1 KAF, 20 clean |
| Fault totals | 168 IAF, 28 KTF — explicitly *not* the detection denominators |
| Capture | complete page captured through an interactive HTTP proxy (mitmproxy) |
| Browser | Firefox 68.0 under Selenium WebDriver 3.141.5 |
| Viewport | 1920 × 1080 |
| Implementation | Java prototype; crawler + Selenium; fully automated |
| Host | AMD Ryzen Threadripper 2990WX, 64 GB, Ubuntu 18.04.4 LTS |
| Baselines | aria-check, tabindex-counter (Fona), QualWeb, WAVE |
| Localization | separate experiment (RQ2), effort metric, ranked edges |

Published Table 1 (p. 9):

| Tool | IAF DEP | IAF DER | IAF LOR | KTF DEP | KTF DER | KTF LOR | Avg min |
| --- | --- | --- | --- | --- | --- | --- | --- |
| KAFE | 92% | 100% | 94% | 90% | 100% | 89% | 19.22 |
| aria-check | 60% | 100% | n/a | 0% | 0% | n/a | 0.03 |
| tabindex-counter | 93% | 39% | n/a | 0% | 0% | n/a | 0.03 |
| QualWeb | 83% | 27% | 6% | 0% | 0% | 0% | 2 |
| WAVE | 68% | 70% | 16% | 0% | 0% | 0% | 0.1 |

Baseline-normalisation rule, quoted, because any same-corpus control must copy
it: for QualWeb and WAVE the authors "considered reports with any mention of
keyboard accessibility issues as a KAF detection for the corresponding web
page"; for tabindex-counter "any ratio less than 100%" is a detection; for
aria-check the failure of any of 23 scenario tests is a detection. They state
this was chosen to give each tool "the most favorable accuracy scores" (§5.3).

### 1.2 BAGEL — CHI 2023 [2]

Chiou, Alotaibi, Halfond, *BAGEL: An Approach to Automatically Detect
Navigation-Based Web Accessibility Barriers for Keyboard Users*. Local copy:
`3544548.3580749.pdf` (17 pp., CreationDate 2023-02-15). Honourable Mention.

**On the manager's misdescription warning.** That warning concerned how
*newer papers* characterise BAGEL, not Codex's preflight, and I previously
misread it as an invitation to correct Codex. No correction of the preflight is
offered here. Independently checked against §§6.1–6.3, pp. 10–11, the paper
states: faulty-*element* scoring, three KNF types, all elements of an offending FuncSet counted as
navigation-order faults, 20 failure-selected cached subjects, Firefox 92.0,
Selenium 3.141.5, 1920 × 1080, Java, iFix DBSCAN clustering, aShot, Ubuntu
18.04.4, Ryzen 7 2700X / 64 GB. The only thing worth adding is that the paper's
own acronym gloss is "keyBoard nAviGation failurE Locator", which reads as a
*localiser* while the title says *detect*; the evaluation is detection of faulty
elements, with no separate ranked-localisation RQ. Date is CHI '23,
April 2023 — not a newer paper.

Failure taxonomy: Unintuitive-Nav-Order, Unintuitive Change-Of-Context,
Unapparent-Focus. The Unapparent-Focus thresholds are **historical**: the paper
uses the then-draft SC 2.4.11 Focus Appearance minimum contrast (written "3.1",
i.e. 3:1) and SC 2.4.12 Focus Not Obscured (partial obscurity). These are not
interchangeable with today's published WCAG 2.2 numbering and must be preserved
separately if ever compared.

Subject selection is explicitly failure-selected ("repeated until we had 10
subjects from each source" containing ≥1 KNF) and contains **no** government or
education pages, because none exhibited KNFs. Published Table 1 aggregate:
BAGEL 85%/100% nav-order, 83%/83% change-of-context, 97%/92% unapparent-focus,
07:32 average runtime; Axe DevTools Pro, QualWeb, WAVE, Tenon Check and ARC
Toolkit all score 0% on change-of-context and unapparent-focus except WAVE
(100%/50% change-of-context). Table 2 gives per-subject precision/recall for all
20 named subjects with explicit `n/a` cells where a page lacks that KNF type —
**this table is itself a recoverable reproduction target even though the BAGEL
artifact folder was unreachable on 2026-09-14** (§2.2).

---

## 2. Artifact recovery

### 2.1 KAFE — recoverable, and independently verified

Project site [3] → evaluation page [10] → one Drive folder [12].

`curl -sS -o /dev/null -w '%{http_code}' -L` on the folder: **HTTP 200**,
350 930 bytes of listing HTML.

Top-level contents (all "Modified Oct 16, 2021", all publicly readable, all
"Shared"):

| Name | Drive ID | Type | Size |
| --- | --- | --- | --- |
| `KAFE_60_subjects` | `1pU6osxQUgAH6EfZ93sMcG9LPxgwstUYS` | folder | not reported |
| `KAFE_output` | `1hKV7KoaMA2Lsgzly9-3cwA-QTU4X-ZM4` | folder | not reported |
| `QualWeb_output` | `1v1Ar0S2fw5Mtae6Lyme4_ekF6saOTiJm` | folder | not reported |
| `WAVE_output` | `1PN9_NKEe7a3mLA8sGfCkpDgJXwRANXIm` | folder | not reported |
| `esecfse2021-paper-supplementary_material.pdf` | `14g3qBzRM52i5FWvf07mbypwFyha7FgOM` | PDF | 182 KB |
| `Results to Reproduce for FSE Artifact` | `1Hy9-lFflGnmm-8eztyM3Zz3hzwvAyWSF6wZlcpAb3LU` | Google Sheet | not reported |

**Ground-truth page labels: recoverable.** The 182 KB supplementary PDF is a
one-page appendix table listing, for each of the 60 subjects: SubjectID, URL,
`#Total` / `#Visible` / `#Ctrl` element counts, and the **per-subject IAF and
KTF fault counts**. **[recomputed]** from that table: 60 subjects, 20 with zero
faults, 40 with ≥1 fault, ΣIAF = 168, ΣKTF = 28 — an exact match to the paper's
§5.2 prose. Per-type positive subjects: 36 have ≥1 IAF, 9 have ≥1 KTF, union 40.

**Saved predictions and per-subject outcomes: recoverable.** The "Results to
Reproduce" sheet exports as CSV (14 545 bytes, 60 data rows + 7 blank trailing
rows). Columns include per-subject step timings and, per failure type,
`Detection Result`, `Detection Ground Truth`, `TP`, `FP`, `FN`, plus
localization recall and best/average/worst ranks. **[recomputed]** from that
sheet:

| Type | TP | FP | FN | TN | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- |
| Type 1 (IAF) | 36 | 3 | 0 | 21 | **92.3%** | **100%** |
| Type 2 (KTF) | 9 | 1 | 0 | 50 | **90.0%** | **100%** |

These reproduce Table 1's 92/100 and 90/100 exactly, from the authors' own
artifact, on a denominator of 60 pages. This is the strongest single recovery
result of this session: KAFE's headline detection numbers are independently
recomputable without running any tool.

**Per-subject saved predictions: recoverable, for KAFE and for both research
baselines.** `KAFE_output` holds one folder per subject. Full listing of
`KAFE_output/4shared` (`1Al21inWzaogPbQpGRZKMrDy_-JFlP0ku`):

| File | Size | Modified |
| --- | --- | --- |
| `localization/` | folder | 2021-10-16 |
| `KNFG_universe.json` | 229 KB | 2021-05-26 |
| `PCNFG_universe.json` | 49 KB | 2021-05-26 |
| `resultsDetection.csv` | 262 B | 2021-06-05 |
| `resultsL10n_revised.csv` | 763 B | 2021-06-05 |
| `resultsSubjectStats.csv` | 98 B | 2021-05-27 |
| `execTime.csv` | 433 B | 2021-05-26 |
| `execTimeDetection.csv` | 55 B | 2021-06-05 |
| `execTimeL10n_revised.csv` | 117 B | 2021-06-05 |

The KNFG/PCNFG JSON is KAFE's navigation model — its intermediate
representation, not just a verdict — so the *element/edge*-level output is
recoverable too, not only the page-level verdict. The `localization/`
sub-folder was **not opened**.

`WAVE_output` and `QualWeb_output` each report **60 items**, one folder per
subject, all modified 2021-10-16, sizes not reported at folder level. So the
two baseline tools' saved per-subject outputs are recoverable as well, which is
what a same-corpus control needs. Their per-file contents were **not checked**.

`KAFE_60_subjects` holds one opaque "Binary" file per subject plus five
sub-folders (`battlenet`, `canon`, `dmv_wc`, `gizmodo`, `speedway` — these five
are stored expanded rather than as single files). The listing paginates at 50
items; 45 files were enumerated, from 203 KB (tesla) to 3.8 MB (alexa),
totalling roughly 66 MB. The alphabetical tail (`tinyurl` onward) was **not
checked**. Scaling the observed ~1.5 MB mean to all 55 file-form subjects gives
an estimate near **80 MB**, plus the five expanded folders. Treat that as an
estimate, not a measurement.

**Licence: none found, and this is a blocker.** Neither the project site [3][10]
nor the Drive listing carries a licence, `LICENSE`, `README`, or terms file. The
content is third-party captured copies of live commercial sites (walmart, cnn,
instagram …), so the captures are not the authors' to relicense either. Not
checked: whether a licence file sits *inside* a subject archive. Until a licence
is identified, redistributing or checking in any KAFE subject bytes is not
something I will do, and downloading the full subject set needs explicit
permission.

### 2.2 BAGEL — artifact proved inaccessible

Project site [4] → evaluation page [11], whose only artifact link is Drive
folder [13], `1wogk0wcNb4eNJXxdSSGhOGPVM6bgMpDm`.

`curl -L` on that folder: **HTTP 404**, 1 652-byte error body. This shows the
folder was unavailable to that unauthenticated request on 2026-09-14. It does
**not** establish that BAGEL's artifacts are permanently gone: the folder could
be unshared, moved, or available by another route. The BAGEL
home page [4] HTML exposes no other outbound artifact link (all `href`s are
Google font/asset URLs; the Drive link is injected by script).

Alternates **not yet checked / blocked**:

- Internet Archive — `archive.org/wayback/available` and the CDX API both
  returned "Internet Archive services are temporarily offline" (and a 429 on
  first contact) at the time of this session. **Not checked, retryable.**
- ACM DL supplemental material for the DOI — `dl.acm.org` returned **HTTP 403**
  to this client. **Blocked, not disproved.**
- Author/lab pages (Halfond's USC software-quality-lab bibliography, Chiou's
  profile) surfaced in search but were **not yet fetched**.

Consequence: BAGEL could not be replicated on its original subjects *from the
routes checked on 2026-09-14*. Unchecked routes remain (archive, ACM
supplemental, author pages), so this is a current-access limitation, not a proof
of permanent loss. Its
*published* per-subject results (Table 2, 20 subjects × 3 KNF types) remain
usable as literature evidence, and only as literature evidence.

### 2.3 Newer leads — status

| Lead | Status |
| --- | --- |
| NavA11y repo [6] | not yet checked |
| SciTePress 150457 [5] | **read (pp. 1–2).** Saifullah, Zerin, Begum, Sakib (Institute of IT, University of Dhaka), *NavA11y: A Dynamic Analysis Approach for WCAG 2.4 Focus-Behavior Evaluation*, ENASE 2026, DOI `10.5220/0015045700004015`, **CC BY-NC-ND 4.0**. See below. |
| Survey arXiv 2411.19727 [7] | not yet checked |
| SATYA DOI 10.1145/3800424.3800426 [8] | not yet checked |
| arXiv 2609.09379 [9] | search snippets indicate "Agentic Web Accessibility Auditing: … Per-Criterion Worker Agents for WCAG", i.e. LLM-agent auditing. Title as returned by two different sources disagrees in wording; **not read**. Do not import its claims. |

Manager's caution stands: apart from NavA11y's first two pages, none of these
have been read, so none may be cited for a numeric claim yet.

**NavA11y, from its abstract and introduction.** Scope is all five WCAG 2.4
focus-behavior success criteria (SC 2.4.3 Focus Order, SC 2.4.7 Focus Visible,
and three further navigable criteria), analysed at page level (drive a real
browser, press Tab, record focus order) and element level (style attributes and
an obscuration ratio). Evaluation: a **22-page labelled dataset** built by
extending six focus-related pages from the **GDS Accessibility Tool Audit**
with 16 newly constructed test cases; NavA11y reports detecting all violations
with no false positives on it. Separately, 26 production websites, 2 947
reported violations, with manual verification on a *stratified sample*
confirming 90% true positives.

Two consequences for us. First, the manager's caution is confirmed: NavA11y's
construct is focus order / focus visibility / obscuration, **not** mouse-only
operability, so it does not overlap Axcess's `kbdiff` question any more than
BAGEL does. It is not a replication target. Second, the lead worth following is
the one *inside* it — the **GDS Accessibility Tool Audit** is a public,
government-published, labelled fixture corpus with a clear licensing story,
which is the kind of independent labelled corpus M1 says this repo currently
lacks. That is a better candidate than NavA11y itself and has **not yet been
checked**. NavA11y's own 22-page dataset licence is unknown; the CC BY-NC-ND
4.0 notice covers the paper, and `ND` would in any case complicate reuse.

---

## 3. Scope mapping: what Axcess actually does versus these papers

Axcess's frozen `kbdiff` detectors do **not** all use one procedure, and an
earlier draft of this file wrongly implied they did:

- **D0, D2–D8 are candidate generators** scored through the subtraction
  `candidates − TabOrder` (`DetectorResult.reported`). These answer
  "does this look interactive and is it outside the Tab order", so they see the
  *unreachable* half of IAF only. The module docstring states the resulting
  hole explicitly: an element in the Tab order that does nothing when a key is
  pressed is removed by the subtraction regardless of which generator proposed
  it.
- **D9 is a behavioural differential**: it compares what the mouse achieves
  against what the keyboard achieves across observable channels. This is the
  only family that can in principle see the *reached-but-not-actionable* half
  of IAF.
- **D10 is a V8 coverage differential**, and the **C10–C16 rules are
  post-hoc heuristics** written against a visible error table (see M1).

So coverage of KAFE's IAF construct is partial and uneven across detectors, and
any scored arm must report per-detector which half of IAF it can reach.

| Paper construct | Axcess coverage | Verdict |
| --- | --- | --- |
| KAFE **IAF** | D0–D10 all target mouse-only operability | **Closest match.** The only defensible replication arm. |
| KAFE **KTF** (trap/cycle) | no cycle detection; `TabOrder` is a reachability set with a press cap | **Not supported.** |
| KAFE localization (ranked edges, RQ2) | no edge model, no ranking | **Not supported.** |
| BAGEL Unintuitive-Nav-Order | no FuncSet clustering, no entry-point analysis | **Not supported.** |
| BAGEL Change-Of-Context | no navigation-away monitoring on non-activation keys | **Not supported.** |
| BAGEL Unapparent-Focus | no focus-indicator contrast/obscurity measurement | **Not supported.** |

Unit mismatch that any protocol must state: KAFE scores **page × type, binary**;
Axcess scores **per element** (`truth.json` maps probe id → label). An
element→page projection (page positive iff any element reported) is the only
honest bridge, and it discards Axcess's finer resolution rather than adding to
it. Confirming M3: the current fresh-context, independent-key trial design is
not KAFE's graph exploration and not BAGEL's FuncSet clustering.

Current corpus, for the record (`experiments/tabbing/fixtures/truth.json`):
19 pages, 95 probes — 39 `violation`, 31 `ok`, 15 `decoy`, 10 `excluded`;
cohorts `upstream` 60 / `holdout` 35; viewports desktop 1280 × 900, mobile
390 × 844.

---

## 4. Replication fidelity

Green = matched. Amber = substitutable with a stated caveat. Red = cannot be
matched with what is on this machine.

| Dimension | KAFE 2021 | This machine | Fidelity |
| --- | --- | --- | --- |
| Subjects | 60 proxy captures | recoverable but unlicensed, ~100 MB, undownloaded | Amber — permission + licence |
| Page-level labels | appendix table | **recovered and verified** | Green |
| Reference predictions | Results-to-Reproduce sheet | **recovered and verified** | Green |
| Baseline tool outputs | WAVE_output, QualWeb_output | present, 60 per-subject folders each; per-file contents not inspected | Green-ish |
| KAFE intermediate model | KNFG/PCNFG per subject | present as JSON | Green |
| Browser | Firefox 68.0 | Chromium 145.0.7632.6 used. Playwright's *expected cache* paths for Firefox/WebKit are absent; this was not an exhaustive search for any Firefox on the system | **Red** |
| Driver | Selenium 3.141.5 | Playwright 1.58.0 | **Red** |
| Viewport | 1920 × 1080 | settable; repo corpus uses 1280 × 900 | Amber |
| Replay mechanism | mitmproxy replay of captured flows | `tools/flowfile.py` + `tools/replay.py` read the flow dumps and replay them; 12/12 sample runs loaded | **Green** — resolved, see FEASIBILITY.md |
| Element discovery | crawler over all page elements | `collect_candidates` already walks all elements; only the bake-off's `_SURVEY_JS` is `[data-probe]`-restricted. Stable identity supplied by a neutral census | Amber — see FEASIBILITY.md §5 |
| Language/host | Java, Ubuntu 18.04.4, Threadripper | Python 3.14.7, current Linux | Amber — affects timing only |

**Superseded.** An earlier version of this section claimed replay and element
discovery were both blocked, and that "download KAFE subjects, run the
detectors" was not executable. Both claims were wrong and are withdrawn.
`FEASIBILITY.md` demonstrates the captures replay (12/12 runs) and that
`collect_candidates` already enumerates untagged elements. The remaining
genuine gaps are the browser-engine mismatch and the unresolved licence.

---

## 5. Answers to Codex M1–M4

**M1 (High) — accepted, confirmed.**
`experiments/tabbing/results/detector-matrix.results.md:110-115` reads: "The
C10–C16 rules were written after reading C9's error table on this corpus, with
the labels visible. They are development results, not measured accuracy, and R2,
R3, R6 and R7 each fire on exactly one probe. C16's 100% precision in particular
should never be quoted as an accuracy figure." Disposition: the existing corpus
is development/regression evidence. No arm in `PROTOCOL.md` treats it as an
unseen benchmark; the KAFE appendix labels are the only genuinely
oracle-independent labels identified so far, and they were authored in 2021 by
third parties with no knowledge of Axcess.

**M2 (High) — accepted, confirmed at all three locations.**
`detectors.py` `_SURVEY_JS` skips any element without a `data-probe` attribute
(`const probe = el.getAttribute && el.getAttribute('data-probe'); if (!probe)
continue;`). `score.py` `score_outcomes` states "A probe missing from `truth` is
skipped entirely rather than guessed at" and `continue`s. `runner/bakeoff.py`
raises `RuntimeError(f"{name} returned a probe outside {page_path}")` and the
analogous error for proposals. Disposition: end-to-end precision on real pages
is **not measurable by the current harness**, and this is a scope limit rather
than a defect to patch under a frozen-detector rule. `PROTOCOL.md` handles
unexpected outputs through an out-of-band adjudication ledger that never edits
`score.py`.

**M3 (High) — accepted.** `UPSTREAM.md` documents Harry's synthetic
a11y-crawler study (commit `6c40f7c…`, Apache-2.0, 60 targets / 26 violations /
34 negatives), not KAFE or BAGEL. §3 above gives the construct map, the
supported failure class (IAF only), and the unit bridge; §4 gives the budgets
and environment gaps.

**M4 (Medium) — accepted.** Upstream labels stay frozen in `truth.json`,
including the disputed p33 hover-only tooltip negative described in
`UPSTREAM.md`; any reinterpretation is reported as a separate sensitivity
column, never folded into the primary score. Amortised per-candidate runtime is
not comparable to KAFE's 19.22 min or BAGEL's 07:32 full-page figures, and no
timing comparison is proposed.

---

## Pending sources

New URLs used in this document, not yet in `sources.json`. Registering them
requires the ledger script, which is outside the commands available to this
session; manager to add.

| Proposed | URL | Note |
| --- | --- | --- |
| P1 | `https://drive.google.com/drive/folders/1pU6osxQUgAH6EfZ93sMcG9LPxgwstUYS` | KAFE_60_subjects |
| P2 | `https://drive.google.com/drive/folders/1hKV7KoaMA2Lsgzly9-3cwA-QTU4X-ZM4` | KAFE_output |
| P3 | `https://drive.google.com/drive/folders/1v1Ar0S2fw5Mtae6Lyme4_ekF6saOTiJm` | QualWeb_output |
| P4 | `https://drive.google.com/drive/folders/1PN9_NKEe7a3mLA8sGfCkpDgJXwRANXIm` | WAVE_output |
| P5 | `https://drive.google.com/file/d/14g3qBzRM52i5FWvf07mbypwFyha7FgOM/view` | KAFE supplementary appendix PDF, 182 KB |
| P6 | `https://docs.google.com/spreadsheets/d/1Hy9-lFflGnmm-8eztyM3Zz3hzwvAyWSF6wZlcpAb3LU` | Results to Reproduce for FSE Artifact |
| P7 | `https://viterbi-web.usc.edu/~halfond/bibtexbrowser.php?key=chiou23chi&bib=softwarequalitylab.bib` | alternate BAGEL artifact lead, unfetched |
| P8 | `https://doi.org/10.5220/0015045700004015` | NavA11y, ENASE 2026, CC BY-NC-ND 4.0 (canonical DOI for [5]) |
| P9 | GDS Accessibility Tool Audit (URL to be resolved) | public labelled focus-behaviour fixture corpus cited by NavA11y; **unchecked**, but the most promising independently labelled corpus found |
