# Session handover — KAFE literature-replication experiment

> **Gate-3 update — manager gpt-6-astra:** §5's rewrite and single bounded Codex
> review are complete. Codex closed **R1/R2/R7 at the protocol-document level**
> but reopened **R3** (missing arm metadata accepted) and **R4** (closed-shadow
> identity collapse). The manager independently reproduced both new defects
> twice with controls; no §4 verified results were rerun. **Scoring stays
> BLOCKED**, including separate R6 clearance/decision. Read
> `MANAGER_REVIEW-GATE3.md` and `CODEX_REVIEW-GATE3.md` for current disposition
> before acting on the historical status/next-task text below. Claude Code owns
> the new code corrections; no follow-up implementation or second review has
> been launched. The remainder of this handover is retained as its original
> session record.

Written 2026-09-14 by Opus 5 (claude-opus-5) acting as manager. Give this file
to the next session as its starting context. It is written to be read cold.

Repository `/var/home/me/Development/axcess`, branch `tabbing`, baseline commit
`fc5a1d5be193212c44f4b92b57a3fbb0679eb1eb`. **Nothing is committed.** All work
is untracked under `experiments/tabbing/literature-replication/`.

---

## 1. What this experiment is trying to answer

Do the frozen Axcess keyboard/mouse differential detectors do better than the
published KAFE detectors (ESEC/FSE 2021), measured on the *original* subjects
rather than on invented fixtures?

The honest short answer so far: a fair comparison is **feasible but weaker than
a replication**, and the headline claim has to be stated conditionally. KAFE's
published reference recall is already 100%, so recall can be matched or lost,
never beaten.

Two root PDFs sit untracked in the repo root: `3468264.3468581 (1).pdf` (KAFE,
ESEC/FSE 2021) and `3544548.3580749.pdf` (BAGEL, CHI 2023).

## 2. Who does what

Four agents, and the split earned its keep — see §6 for the numbers.

| Agent | Role | Auth |
| --- | --- | --- |
| Opus 5 (Hermes) | Manager: planning, protocol, verification, user interface | — |
| Claude Code | Bulk implementation from a written brief | `claude.ai`, Team |
| Codex (`gpt-6-astra`) | Independent review only; never reviews its own work | ChatGPT |
| Copilot CLI | Mechanical few-call jobs; auto-model only, ~0.5 credits/call | GitHub, harryg02 |

The one rule that has demonstrably paid for itself: **whoever writes the code
never grades it.** Every defect but two was found by someone other than its
author.

`COORDINATION.md` holds the full contract. Handoffs are compact files in the
experiment directory, never replayed transcripts — that is what keeps the token
cost bounded.

## 3. State of play

Three review gates have run. Gate 2 **blocked** the scored arm; the blocking
findings assigned to agents are now closed, and three remain with the manager.

| Finding | Owner | Status |
| --- | --- | --- |
| M1 method-blind router | Opus 5 | closed — verified |
| M2 focus-probe control gap | Opus 5 | closed, then reopened as R4 |
| R4 shadow-path identity collapse | Claude Code | **closed** — behavioral browser tests |
| R3 adjudicator had no validity gate | Claude Code | **closed** — 8/8 seeded defects caught |
| R1 scoring formulas retrofittable | **Opus 5 / manager** | **OPEN — next task** |
| R2 abstention buckets and denominators | **Opus 5 / manager** | **OPEN — next task** |
| R7 claim strength vs historical KAFE | **Opus 5 / manager** | **OPEN — next task** |
| R6 brotli fidelity unvalidated | unassigned | **OPEN — needs a user decision** |
| R5 request matching ignores bodies | deferred | revisit before interactive subjects |

**Scoring is not approved and must not be run until R1, R2 and R7 are closed and
Codex has re-reviewed.**

## 4. Verified facts — do not re-derive these

Everything here was confirmed by running it, not by reading a report.

- Environment: Python 3.14.7, Playwright 1.58.0, Chromium 145.0.7632.6, offline.
  Always invoke as `uv run --offline --no-sync ...`. Playwright Firefox and
  WebKit are **not** installed, so the historical Firefox 68 condition cannot be
  reproduced — this is a permanent fidelity caveat, not a to-do.
- `experiments/tabbing/literature-replication/tests/` — **87 passed**.
- Repository `tests/unit` — **849 passed** in ~120 s. (An earlier brief said
  "121"; that was four hand-picked kbdiff files, wrongly described as the
  directory. Corrected.)
- Replay works: 12/12 runs load, 0 essential resources missing.
- G1c disposition: **H0 NOT FALSIFIED** under the strict adjudicator. Tagging is
  inert for DOM signature *and* focus order on these three subjects.
- The G1c validity gate catches **8/8 seeded defects** — see
  `tests/test_seeded_gate.py`, which is the answer-key check, not a self-report.
- `artifacts/` is git-ignored and holds ~1.8 MB of third-party captures.
  **Licence is unresolved; do not commit or redistribute those bytes.**

## 5. The next task, concretely

Rewrite `FEASIBILITY.md` §6 to close R1, R2 and R7. Codex's exact objections are
quoted in `MANAGER_REVIEW-GATE2.md`; read that file before touching anything.

1. **R1** — "strict dominance" currently overlaps "non-inferiority", and the
   rounded 92.3% precision threshold could classify *equality* with the
   reference as an improvement. Freeze mutually exclusive outcome buckets,
   separate page-level and element-level formulas, and state repeat aggregation
   and undecidable-label handling.
2. **R2** — define which buckets count as abstentions, bucket precedence when
   two failures coincide, and how positive and negative subjects enter the
   confusion matrix. Reconcile the 60-page denominator with the current
   three-subject authorization.
3. **R7** — downgrade the headline. Historical Firefox 68 outputs versus a
   current Chromium replay cannot support a published-style precision/recall
   claim. The defensible framing is *equal recall with higher precision,
   conditional on replay fidelity*, reported beside the runnable same-replay
   baselines rather than as a replication.

Then send **one** bounded Codex review covering the §6 rewrite *and* Claude's
R4/R3 work. Give it an explicit file list and a command budget; an open-ended
brief cost 383,599 input tokens, a bounded one 123,947 for a harder question.

## 6. Measurement of the agent system itself

A defect log runs across sessions at `~/.hermes/logs/agent-defects.jsonl`, with
the `agent-defect-log` skill. At n=10: self-catch rate **20%**, escape rate
**10%**. Log every defect at discovery, including your own — entries where the
author is the logger are the most informative ones.

The single escaped defect is a **fabricated fact**: an AI turned Harry's
question "what is IAAP CPACC?" into a biographical claim that he was pursuing
the certification, and it spread into LinkedIn and cover-letter drafts before he
caught it. No agent gate catches this class. **Verify any biographical or
credential claim against his own words** — the `claude-archive` skill searches
his history, and `--sender human` is the flag that separates what he said from
what an assistant said about him.

## 7. Standing constraints

No installs, no network beyond explicitly approved research reads, no live
crawls, no listeners, no nested agents, no permission-bypass flags, no sudo, no
commits without asking. Detectors elsewhere in the repo stay frozen. Do not
expand past the three authorized subjects without a fresh decision from Harry.
Keep every raw run, including failures; `derived/feasibility.pre-focus-fix.json`
is a superseded run kept deliberately.

Report to Harry one line per task: what ran, what it cost, what changed, and
which parts are verified versus claimed.
