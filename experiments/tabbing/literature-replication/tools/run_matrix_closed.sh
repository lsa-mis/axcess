#!/usr/bin/env bash
# Re-run the full matrix after the pierced-tree paging fix, under a new label.
#
# Same two stages and same order as `run_matrix.sh`; only the label differs, so
# the pre-fix `matrix` artifacts stay on disk to be diffed against. Every corpus
# is re-run rather than just edgecases: the fix touches the traversal that every
# corpus uses, so fixtures reproducing its published numbers *after* the change
# is the control that the change moved nothing it should not have.
set -u
REPO=/var/home/me/Development/axcess
RUN="uv run --offline --no-sync --directory $REPO python experiments/tabbing/runner/bakeoff.py"
LOG=$REPO/experiments/tabbing/literature-replication/derived/matrix-closed-run.log
: > "$LOG"

say() { echo "=== $* ===" | tee -a "$LOG"; }

for corpus in fixtures edgecases gds ma11y; do
  say "A cheap+C1-C9 $corpus"
  $RUN --corpus "$corpus" --cheap-only --candidate-study \
       --label closed --timeout-seconds 3600 >>"$LOG" 2>&1
  echo "  exit=$? $corpus" | tee -a "$LOG"
done

for corpus in fixtures edgecases gds ma11y; do
  say "B D9/D10 arms $corpus"
  $RUN --corpus "$corpus" --candidate-study \
       --label closed-full --timeout-seconds 14400 >>"$LOG" 2>&1
  echo "  exit=$? $corpus" | tee -a "$LOG"
done

say "DONE"
