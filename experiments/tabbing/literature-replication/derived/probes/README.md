# Per-corpus probe observations

Written by `experiments/tabbing/probes/probe_*.py` under `PROBE_CORPUS`, one
directory per corpus, so no corpus reads another's evidence. Scored into
`../probe-rules/` by `tools/run_probe_rules.py`.

`fixtures-c12` observes only the 42-probe C12 lead set (`probes/c12.json`), the
scope the published C16 = 100% precision came from. `fixtures-all` observes all
95. Both are carried into the matrix, each labelled with the set it saw.
