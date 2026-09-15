# Literature-replication experiment: coordination contract

## Ownership and scope

User: Harry. Overseer: gpt-6-astra in Hermes; directly accountable to Harry.
Repository: `/var/home/me/Development/axcess`, branch `tabbing`.
Starting commit: `fc5a1d5` (resolve full hash in experiment provenance).
Original untracked inputs, read-only: `3468264.3468581 (1).pdf` and `3544548.3580749.pdf`.

Goal: inspect the existing report and detectors, locate original and newer keyboard/mouse differential research and recoverable evaluation artifacts, evaluate frozen Axcess detectors on a defensibly comparable environment, and write an evidence-backed report. Improvement is a hypothesis, not an acceptance requirement. Normal scans, databases, existing fixture truth, and previous results are outside the edit scope.

## Roles considered and selected

Candidates: one agent does everything; two parallel implementers; one implementer plus an independent reviewer.
Selected: Claude Code owns implementation and report drafting; Codex owns bounded methodology and results reviews. This respects the user's stated lower Codex allowance and avoids simultaneous edits to the same artifact. It is an allocation decision, not a measured efficiency claim.

Claude must use the user's subscription only. After user-mediated reauthentication, the manager read `claude auth status`: `authMethod=claude.ai`, `subscriptionType=team`. Claude inference may proceed on that subscription; do not switch to API billing. Codex reports ChatGPT login. No API-funded fallback, permission bypass, sudo, publishing, external crawling, or external listeners. Reading public research/artifacts is within the requested research scope. Ask before installing missing dependencies or downloading large artifacts. Prefer existing offline/browser-route infrastructure.

## Communication: bounded artifact handoffs

The manager relays concise messages between the agents. No open-ended conversation, polling loops, nested agents, or duplicate broad repository exploration.

1. Initial Codex review: read existing reports, relevant detector/runner entry points, and the two PDFs; return methodological constraints and blockers. Do not modify files or run measurements.
2. Claude produces a proposed `PROTOCOL.md`, literature/source evidence and, if feasible, a narrowly scoped harness. No scored benchmark until protocol review.
3. Codex reviews the protocol and critical harness/scoring paths, returning only concrete defects, their evidence, and required checks.
4. Claude responds point-by-point and fixes accepted defects. The manager approves a frozen protocol before scoring.
5. Claude executes the agreed experiment, preserving raw results and unsuccessful runs, and drafts `REPORT.md`.
6. Codex reviews final evidence, scoring and claims. The manager independently runs relevant checks and recomputes reported metrics before delivery.

Each handoff should be at most 600 words, using:
- Scope/version: exact paths and commit/hash when available.
- Evidence: commands, artifact paths, source section/page, observed outputs.
- Findings: `ID | severity | evidence | requested change/check`.
- Questions/blockers: only decisions needed by the recipient.
- Disposition on response: accepted/fixed, rejected with evidence, or unresolved.

Use session resumption for tightly related follow-ups; do not resend entire papers or transcripts. Read only changed sections at subsequent gates. The manager writes compact review records alongside the report when they form part of its audit trail.

### Usage constraint — latest user steering

The user reports Astra has 43% of its five-hour allowance left, resetting in 4h49m from that message. Treat this as a shared scarce allowance for the Hermes manager and Codex, not two independent budgets. These are user-reported figures, not a live quota check.

Override the earlier two-review-gate default: reserve Codex for one final bounded independent review, unless a blocking methodological ambiguity requires earlier use. The manager handles the pre-measurement protocol gate using Codex's existing M1–M4 findings and actual artifacts. Claude retains research, harness implementation, execution and drafting; its own self-review does not count as independent verification. Keep managerial reads targeted, batch independent checks, use code to reduce outputs before model context, and rely on completion notifications rather than repeated polling. Do not launch duplicate Codex investigations or move heavy synthesis back to Astra. Preserve enough capacity for independent metric recomputation and an honest final report; if that cannot be assured, pause at a documented checkpoint rather than skip verification.

## Scientific constraints

- Keep paper-reported results, newly observed results, and assumptions separate.
- Recover original subjects/labels/tool versions where possible; explicitly assess archive and license availability.
- A current live page, reconstructed example, and original frozen subject are not interchangeable.
- Compare detectors on the same subjects, positive/negative labels, scoring unit, browser conditions and budgets. Separate page-level and element-level metrics.
- Do not relabel known development fixtures as independent holdouts or use labels to discover targets without marking oracle evaluation.
- Freeze hypotheses, falsification criteria, controls, denominators/abstentions, repetitions, stopping rule and source fingerprints before measurement.
- Retain controls and all runs. Repeated deterministic fixture runs assess reproducibility, not independent statistical samples.
- If original artifacts are missing, report the limitation; do not fabricate a replication or substitute synthetic scores for published real-world evidence.
- Keep existing detectors frozen for the primary evaluation. Any defect-driven detector change requires a separately identified follow-up, not replacement of the primary result.

## Completion evidence

Deliver a report with literature provenance, replication fidelity table, exact runnable commands and versions, raw per-case outputs, confusion matrices with denominators, coverage/abstentions, repeated-run spread, matched-control comparisons, independent review dispositions, and explicit limitations. If replication is blocked, identify precisely what is missing and which narrower tests were actually run.
