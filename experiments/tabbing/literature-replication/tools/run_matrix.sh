#!/usr/bin/env bash
# Steps 3-6 of PLAN-FULL-MATRIX.md: every detector, every environment.
#
# Ordered cheap-first so the fast rows land early and a failure late in the run
# still leaves most of the matrix on disk. Each stage writes its own JSON;
# nothing is held in memory across stages.
#
# The expensive stage (D9 x6, D10 x5) is the multi-hour part. It runs last and
# per corpus, so an interruption costs one corpus rather than the run.
set -u
cd /var/home/me/Development/axcess

RUN="uv run --offline --no-sync python experiments/tabbing/runner/bakeoff.py"
LOG=experiments/tabbing/literature-replication/derived/matrix-run.log
: > "$LOG"

say() { echo "=== $* ===" | tee -a "$LOG"; }

# Stage A: cheap tier + candidate study (C1-C9) on every corpus.
for corpus in fixtures edgecases gds ma11y; do
  say "A cheap+C1-C9 $corpus"
  $RUN --corpus "$corpus" --cheap-only --candidate-study \
       --label matrix --timeout-seconds 3600 >>"$LOG" 2>&1
  echo "  exit=$? $corpus" | tee -a "$LOG"
done

# Stage B: the expensive behavioural and coverage arms, same corpora.
for corpus in fixtures edgecases gds ma11y; do
  say "B D9/D10 arms $corpus"
  $RUN --corpus "$corpus" --candidate-study \
       --label matrix-full --timeout-seconds 14400 >>"$LOG" 2>&1
  echo "  exit=$? $corpus" | tee -a "$LOG"
done

say "DONE"
