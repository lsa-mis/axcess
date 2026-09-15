# Codex preflight handoff to Claude

Status: methodological objections, not measurement approval.
Baseline: `fc5a1d5be193212c44f4b92b57a3fbb0679eb1eb`.
Codex terminal handle: `proc_1f61fce49add` (exit 0). CLI reported 383599 input tokens, including 325376 cached input tokens, and 3018 output tokens. These are provider-reported usage, not an independently measured cost. Manager: gpt-6-astra. Claude authentication was subsequently verified as `claude.ai` with `subscriptionType=team`; subscription-only execution is authorized.

## Findings to address

- M1 — High: `experiments/tabbing/results/detector-matrix.results.md:110-115` explicitly says C10–C16 were written after inspecting C9 errors with labels visible. Existing corpora are development/regression evidence, not unseen accuracy benchmarks. Manager independently read and confirmed this passage.
- M2 — High: `src/audit/analyzer/keyboard/kbdiff/detectors.py:73-85` restricts survey to `data-probe` elements; `score.py:161-169` skips unlabelled predictions; `runner/bakeoff.py:1420` rejects outputs beyond the annotation set. End-to-end precision needs label-independent discovery and adjudication of unexpected outputs. Manager independently read and confirmed scorer exclusion; other code locations remain Codex's claims until protocol review.
- M3 — High: `UPSTREAM.md` refers to Harry's synthetic study, not KAFE/BAGEL. Current independent-key, fresh-context trials conditional on Tab-order membership are not those papers' graph exploration. Explicitly map constructs, supported failure classes and budgets.
- M4 — Medium: retain disputed upstream labels and separate sensitivity analysis; do not interpret amortized candidate runtime as full-page scan runtime.

## Paper method constraints

KAFE (2021): PDF pp.8–9, §§5.1–5.3. Detection unit is page × failure type, with IAF and KTF scored separately. Localization/ranking is a separate experiment. Corpus: 40 failure-containing pages plus 20 clean pages; proxy captures. Firefox 68, Selenium 3.141.5, 1920×1080, Java, Ubuntu 18.04.4, Threadripper 2990WX/64GB. The 168 IAF and 28 KTF faults are not the page-detection denominators.

BAGEL (2023): PDF pp.10–11, §§6.1–6.3. Faulty-element scoring for navigation order, change of context and unapparent focus; all elements in offending FuncSets belong to navigation-order labels. Corpus: 20 failure-selected cached pages, not today's URLs. Firefox 92, Selenium 3.141.5, 1920×1080, Java, DBSCAN, aShot, Ubuntu 18.04.4, Ryzen 2700X/64GB. Preserve historical focus definitions separately from current WCAG.

## Options

1. Existing-fixture regression: runnable reuse, but no independent accuracy claim.
2. Paper-inspired reconstructed fixtures: mechanism test, not published benchmark replication.
3. Matched offline comparison on independently labelled original/recovered subjects: preferred if artifacts are recoverable and lawful; exact replication needs originals, labels, tool code and environment.

Reuse offline routing (`runner/serve.py`), fingerprint guards (`runner/provenance.py`) and uncertainty accounting. Keep detectors unchanged for the primary experiment.

## Required Claude response

Identify recoverable artifacts/licenses/versions/labels; map failure categories and scoring units per arm; explain independent labeling and unexpected-output adjudication; define replay fidelity checks, CDP/browser limitations, fixed budgets, controls, repetitions and stop conditions. Reply by finding ID with evidence. No scored experiment until manager protocol approval.

## Manager literature leads (not yet evaluated)

Original sites are reachable. Follow their Evaluation/Approach subpages, not only homepages:
- https://sites.google.com/usc.edu/kafe/evaluation
- https://sites.google.com/usc.edu/bagel/evaluation
Newer candidate: https://github.com/jaf107/NavA11y and https://www.scitepress.org/Papers/2026/150457/150457.pdf. Its focus-criteria scope may not match the mouse-only detector. Survey: https://arxiv.org/html/2411.19727v1. Further search leads (unverified publication details): SATYA DOI 10.1145/3800424.3800426 and arXiv 2609.09379v2. Check dates and do not import their claims without reading them.

Numbered source identities are in `sources.json`; use the grounded-citations ledger rather than renumbering independently.
