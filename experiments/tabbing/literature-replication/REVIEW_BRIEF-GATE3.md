# Gate 3 bounded review brief

Manager: gpt-6-astra (Hermes), taking over Opus 5's role. Reviewer: fresh Codex context, independent of this drafting session. Repository branch `tabbing`, baseline `fc5a1d5be193212c44f4b92b57a3fbb0679eb1eb`; experiment files are untracked. User explicitly requested one review of the manager's §6 rewrite plus Claude's R4/R3 work. No scoring authorization.

## Objective and hypotheses

Determine whether FEASIBILITY.md §6 closes R1/R2/R7 and whether Claude's R4/R3 implementation leaves a concrete blocker. H-close: those five findings are closed within their registered scope. H-open: at least one counterexample remains. Falsify closure with a specific conflicting rule, denominator leak, unsupported claim, or code path permitting an invalid result. Do not rubber-stamp the manager's rewrite.

## Exact read scope

Paths relative to this directory:
- `MANAGER_REVIEW-GATE2.md` (original objections).
- `FEASIBILITY.md` §6; §4/§5 only for directly referenced claim consistency.
- `tools/replay.py` only `OPAQUE_SCOPE` and `FOCUS_PROBE_JS`.
- `tools/adjudicate_g1c.py`.
- `tests/test_focus_probe_browser.py`, `tests/test_focus_probe.py`.
- `tests/test_adjudicate_g1c.py`, `tests/test_seeded_gate.py`.
- `PREREGISTRATION-G1c.md`.
- `LITERATURE.md` lines 124–145 only for already established reference counts.
- This brief; applicable repository AGENTS.md instructions.

No wider repository search, PDFs, captures, truth files, browser replay, network research, installs, source edits, commits, scoring or nested agents. R6 is unresolved and remains a separate blocker requiring Harry's decision: do not solve or waive it. R5 is deferred to interactive expansion. Only Codex inference via the existing ChatGPT login is authorized.

## Accepted evidence — do not re-derive

The handover explicitly marks the browser identity/perturbation tests, strict G1c result, 8/8 seeded defects, experiment suite 87 passed and repository unit suite 849 passed as verified. Accept those historical observations; do not rerun suites or replay subjects. Review whether the implementation has a missed counterexample, not whether those results existed. Chromium-only and unavailable historical Firefox are accepted constraints.

Manager's new synthetic protocol checks (not detector scores): two identical passes; each covered 256 exact metric pairs, 729 matrix/abstention combinations, four precedence cases and two repeat-agreement controls; zero assertions failed. Equality is the control; the old rounded threshold incorrectly treats 36/39 as a gain. These checks validate a transcription of the new rules, not a production scorer.

## Budget and output

Maximum **8 shell commands, 12,000 words of file output, 10 minutes**, no broad tests. Reserve the last command for at most one tiny in-memory counterexample if needed; no file writes or synthetic substitution for actual evidence. Stop at the limit and state incomplete review, not clearance. Emit concise checkpoint conclusions in the transcript after protocol and code inspection. If sandbox execution fails, report it; do not enable bypass.

Return at most 600 words: disposition per R1/R2/R7/R4/R3; findings as `ID | severity | file:line | counterexample | required change`; separate observed evidence, accepted handover evidence, and inference. Conclude `SCOPED REVIEW: CLEARED` or `BLOCKED`, then separately state the overall scoring gate (still blocked on R6/manifest/approval). Give commands used and usage if available. Do not assert executable readiness from a documentation pass.

If any premise in this brief turns out to be wrong or impossible, stop and report that instead of working around it.
