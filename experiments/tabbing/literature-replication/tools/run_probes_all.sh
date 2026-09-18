#!/usr/bin/env bash
# Observe the four probe files, and score C10-C16, for every corpus.
#
# The probe scripts have always accepted PROBE_CORPUS; they had simply never
# been pointed anywhere but fixtures, which is why C10-C16 appeared in no other
# environment. Each corpus gets its own observation directory so no corpus reads
# another's evidence.
#
# fixtures is observed twice on purpose. The published C16 = 100% precision was
# produced by observing only the 42-probe C12 lead set (`probes/c12.json`); R9
# promotes from the whole universe but can only promote what it looked at. The
# unfiltered pass observes all 95. Both are scored and both are carried into the
# matrix, each labelled with the set it saw.
set -u
REPO=/var/home/me/Development/axcess
LR=$REPO/experiments/tabbing/literature-replication
OBS=$LR/derived/probes
SCORED=$LR/derived/probe-rules
LOG=$LR/derived/probe-run.log
RUN="uv run --offline --no-sync --directory $REPO python"
mkdir -p "$OBS" "$SCORED"
: > "$LOG"

say() { echo "=== $* ===" | tee -a "$LOG"; }

observe() {  # observe <corpus-root> <outdir> [effect2-filter]
  local root=$1 out=$2 filter=${3:-}
  mkdir -p "$out"
  for probe in containment composite effect; do
    PROBE_CORPUS="$root" $RUN experiments/tabbing/probes/probe_${probe}.py \
      "$out/${probe}.json" >>"$LOG" 2>&1
    echo "  ${probe} exit=$?" | tee -a "$LOG"
  done
  # shellcheck disable=SC2086
  PROBE_CORPUS="$root" $RUN experiments/tabbing/probes/probe_effect2.py \
    "$out/effect2.json" $filter >>"$LOG" 2>&1
  echo "  effect2 exit=$?" | tee -a "$LOG"
}

score() {  # score <corpus> <artifact> <obsdir> <tag>
  $RUN experiments/tabbing/literature-replication/tools/run_probe_rules.py \
    --corpus "$1" --artifact "$2" --observations "$3" \
    --out "$SCORED/$1-$4.json" 2>&1 | tee -a "$LOG"
}

say "fixtures, C12 lead set (the published scope)"
observe experiments/tabbing/fixtures "$OBS/fixtures-c12" experiments/tabbing/probes/c12.json
score fixtures "$REPO/experiments/tabbing/fixtures/results/bakeoff-fixtures-closed.json" \
      "$OBS/fixtures-c12" c12

say "fixtures, every probe"
observe experiments/tabbing/fixtures "$OBS/fixtures-all"
score fixtures "$REPO/experiments/tabbing/fixtures/results/bakeoff-fixtures-closed.json" \
      "$OBS/fixtures-all" all

say "edgecases, every probe"
observe experiments/tabbing/edgecases "$OBS/edgecases-all"
score edgecases "$REPO/experiments/tabbing/edgecases/results/bakeoff-edgecases-closed.json" \
      "$OBS/edgecases-all" all

say "gds, every probe"
observe experiments/tabbing/literature-replication/artifacts/gds-corpus "$OBS/gds-all"
score gds "$LR/artifacts/gds-corpus/results/bakeoff-gds-closed.json" "$OBS/gds-all" all

say "ma11y, every probe"
observe experiments/tabbing/literature-replication/artifacts/ma11y "$OBS/ma11y-all"
score ma11y "$LR/artifacts/ma11y/results/bakeoff-ma11y-closed.json" "$OBS/ma11y-all" all

say "DONE"
