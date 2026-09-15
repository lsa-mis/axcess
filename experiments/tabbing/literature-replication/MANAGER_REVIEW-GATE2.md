# Gate 2: Codex independent review — BLOCKED

Reviewer: Codex (`gpt-6-astra`), read-only, 2026-09-14. Verdict as issued:
**GATE 2: BLOCKED ON R1, R2, R4, R6, R7**. Usage 123,947 input / 2,140 output.

Manager (Opus 5) has independently confirmed R4 and R3 by reading the cited
lines. Codex's findings are reproduced verbatim below in condensed form; where
the manager adds anything it is marked MANAGER.

## Ownership of the remaining work

| Findings | Owner | Why |
| --- | --- | --- |
| R4, R3 | Claude Code | Code and test defects; needs a real browser fixture |
| R1, R2, R7 | Opus 5 (manager) | Protocol design and claim strength, not code |
| R6 | deferred, needs a decision | See note below |
| R5 | deferred to expansion | Codex: "M1 is sufficient for its narrow defect" |

Do not work on findings you do not own. Scoring remains **not approved**.

---

## R4 | blocking | assigned to Claude Code

Codex, verified: "M2 removes census-dependent identity, but `replay.py:264–281`
omits the identity/index of a shadow-root child when crossing to its host."
Inferred counterexample: "two buttons directly inside one shadow root receive
the same path. Frames are not descended despite the comment.
`test_focus_probe.py:20–51` checks source strings, not behavior."

Required change, as issued: "Add behavioral identity and perturbation controls
for sibling shadow children, nested roots and frames; implement distinct
identities or explicitly exclude unsupported scopes. The replacement fixes the
original collapse but remains insufficient."

MANAGER: confirmed by reading `tools/replay.py:266-269` — the `!parent` branch
pushes `'#s'` and reassigns `node = root.host` without pushing the child's own
index first. This is the same identity collapse M2 was written to remove, in a
narrower scope. No shadow DOM appears in the three authorized captures, so no
recorded result is affected; this is a latent defect, like M1 was.

MANAGER: the deeper failure is the tests. Opus 5 wrote five assertions against
the *source text* of `FOCUS_PROBE_JS`. They passed while the defect was present
and would pass again after a regression. A test that cannot fail when the
behavior is wrong is not evidence. This is the same class of error the manager
had flagged in earlier work one step before repeating it.

## R3 | major | assigned to Claude Code

Codex, verified: "`PREREGISTRATION-G1c.md:28–46` risks rejection... 
`adjudicate_g1c.py:33–60` compares actual trails and can print 'H0 FALSIFIED';
it is **not constructed to pass**. However, it silently overwrites duplicate
records (`:14–16`), lacks exact subject/run/15-step validation, and prints H0
survival even when reproducibility fails."

Required change, as issued: "Validate the complete registered matrix and emit
one validity-gated disposition. Limit survival to the first 15 presses;
chronology and the empirical survival claim are not independently verified
here."

MANAGER: confirmed at `tools/adjudicate_g1c.py:30-60` — P1, P2 and P3 are
computed and printed independently, with no gate making the H0 disposition
conditional on P1 and P3 passing. The pre-registration says a P3 failure voids
the run; the adjudicator does not enforce it.

## R6 | blocking | NOT assigned — awaiting decision

Codex, verified: "brotli remains encoded with its header (`replay.py:100–123`),
but its test uses 'brotli-ish' bytes and never verifies browser decoding
(`test_replay.py:166–172`). Degradation checks only denied URLs (`:174–176`);
`FEASIBILITY.md:125–135` therefore overclaims functional fidelity."
Causation for the coronavirus parse error: "**undecidable from these files**."

MANAGER: resolving this may require a brotli decoder, which is an install and
therefore a user decision. Do not install anything. Do not attempt R6.

## R1, R2, R7 | manager-owned, do not touch

R1: page-level scoring versus an element adjudication ledger; "strict dominance"
overlaps "non-inferiority"; the rounded 92.3% threshold could classify equality
with the reference as improvement; repeat aggregation and undecidable labels
undefined.

R2: abstention buckets, bucket precedence, concurrent failure resolution, and
the 60-page denominator versus the current three-sample limit.

R7: historical Firefox 68 outputs versus current Chromium replay cannot support
a published-style precision/recall claim; recall at 100% "permits matching or
loss, never improvement."

## R5 | major | deferred

Request matching ignores bodies and state-bearing headers and repeats the last
response indefinitely. Codex: "M1 is sufficient for its narrow defect." Revisit
before any interactive subject is scored, not now.
