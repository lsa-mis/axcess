# Manager gate 1: corrections and artifact-inspection authorization

Reviewer: gpt-6-astra. Claude drafts LITERATURE.md and PROTOCOL.md were read through tool output. Status: **scored evaluation NOT approved**. Read this before continuing.

## User approval

Harry explicitly approved: **staged local downloads up to 150 MB; no redistribution**. Start with the three named KAFE subjects (`citiprogram`, `craigslist`, `coronavirus`), then expand only if replay is feasible. Store downloaded captured content under this experiment's `artifacts/` directory, ignored via a new `.gitignore` confined to this experiment. Do not change root ignore rules. No installs, uploads, publishing, production DB access, live crawls, sudo or bypass grants. Source evidence and compact derived metadata may be retained with the report; third-party captured website bytes must not be committed.

## Review findings

G1 — BLOCKING: `data-probe` requirement is not established as a permanent need to edit detector rules. Consider a harness-side, label-independent neutral ID census across all DOM elements (and existing supported shadow/frame scopes). Freeze the detector implementation; tag every element, not labelled targets. Evaluate whether adding the attribute changes selectors, scripts, DOM-signature effects or behavior using tagged vs untagged controls. If stable IDs cannot be reproduced across fresh contexts, abstain with evidence. This is a hypothesis to test, not an approved workaround. Existing `collect_candidates` also returns unannotated candidates; do not conflate it with the matrix-only survey.

G2 — BLOCKING: Defining IAF solely as unreachable is incomplete: KAFE also covers non-actionable reachable controls. Correct LITERATURE.md. Distinguish cheap candidate-minus-Tab detectors from D9 behavioral differentials and C16 heuristics; do not state all use the same procedure.

G3 — BLOCKING: Main scoring proposal must test improvement vs KAFE on matched units, not replace the question with arbitrary 80% precision/90% recall or improvement vs WAVE only. Strict dominance in precision AND recall, noninferiority plus a gain, and no improvement must be distinguishable. With reference recall already 100%, recall cannot exceed it; make this ceiling explicit. KAFE's published headline/reference CSV are historical observations, not a newly rerun same-browser control. Browser effects and replay drift limit attribution. Include a runnable simple/current baseline on the same replay alongside historical KAFE outputs.

G4 — BLOCKING: Align prediction thresholds and falsification thresholds; current 5% expectation/20% falsification and 1%/5% spread leave confusing gaps. Define exhaustive outcome buckets. Total DOM counts do not establish functional replay fidelity. Include representative known functionality, asset availability, errors, frame coverage and safe interactions with egress blocked. Some blocked analytics requests do not prove the capture unusable; classify essential-resource failures vs benign denied requests instead of declaring every abort invalid.

G5 — BLOCKING: 404 proves this folder was unavailable to that request, not that BAGEL artifacts are permanently gone. Missing expected Playwright paths does not prove no other Firefox exists. Stop calling these permanent constraints. The manager's misdescription warning concerned newer papers' accounts of BAGEL, not Codex; remove the invented correction of the preflight.

G6 — BLOCKING: Claude's recovered-label metrics need source-backed machine-readable evidence and independent manager recomputation. Recover authors' small supplementary PDF/CSV into authorized artifact storage, retain exact URLs/hashes and parsed per-subject labels. Do not rely on previous /tmp files or claims alone. Register pending source URLs with the existing ledger, and finish newer-literature review before the final report.

G7 — SCOPE: Do not pivot to GDS as a substitute for the user's original-paper environments without first establishing KAFE feasibility. Do not tune detectors to retrieved labels. Do not run the entire existing synthetic corpus simply to fill a report with scores irrelevant to the requested comparison.

## Next bounded phase — approved

1. Fix the substantive draft errors above.
2. Fetch the three authorized samples and small label/reference artifacts with aggregate byte accounting and exact source IDs/hashes; inspect format. No bulk recursive downloads yet.
3. Check already installed parsers/dependencies. A compact standard-library parser for the actual recovered format is acceptable if justified and unit tested; do not declare replay impossible merely because existing serve.py handles directories only. No new services/compilers/installations.
4. Implement the minimum isolated offline format/route adapter and neutral-census feasibility control in this experiment directory, with tests written first. Test localhost-free Playwright routing, default-deny HTTP/WebSocket, service-worker blocking, path traversal/duplicate request handling, source fingerprints and retention of failures. Start with in-memory known positive/negative controls; no detector accuracy scoring on KAFE yet.
5. Inspect the three samples in the existing browser under the proposed fidelity conditions, record all results and failures. These are feasibility observations, not precision/recall. Report whether safe real execution is possible and what state/resource coverage is missing.
6. Write a concise feasibility handoff and revised executable scoring protocol. Manager approves scoring only after reviewing it. Do not expand past the sample until that handoff unless only small metadata is needed.

## Budget and reporting

Read the latest COORDINATION.md: Astra/Codex allowance is scarce. No extra agents or Codex runs. Resume existing Claude context; implement/research independently within scope. Save progress at meaningful checkpoints, not only at the final turn. Return <=500 words with paths, blocker IDs, exact next command and total downloaded bytes. Agent completion claims require independent manager verification.
