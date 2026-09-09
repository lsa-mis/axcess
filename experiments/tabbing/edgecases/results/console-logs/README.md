# Console output from superseded bake-off runs

**These are transcripts, not results.** `bakeoff.py` has no `--label` flag and
writes to a fixed path, so each run overwrote the previous JSON. The scored
tables printed to stdout are all that survives of the earlier runs; the per-probe
evidence in those JSON files is gone.

That is a real gap in the harness and it is recorded here rather than papered
over. The main experiment (`runner/main.py`) does not have this problem — it
refuses to overwrite and takes `--label`.

| log | corpus | what it captured |
|---|---|---|
| `bakeoff1.log` | edgecases | first run; axe mis-credited via ancestor containment |
| `bakeoff2.log` | edgecases | after axe exact-node fix and the `Math.random()` fixture fix |
| `bakeoff3.log` | edgecases | after the overlay-overflow and sub-pixel aim fixes |
| `bakeoff4.log` | edgecases | after unknowns were preserved through scoring |
| `bakeoff-fixtures.log` | fixtures (frozen) | first twelve-detector run on the blind corpus |
| `bakeoff-fix2.log` | fixtures (frozen) | after unknown preservation; supersedes the above |

Only `bakeoff4.log` and `bakeoff-fix2.log` correspond to JSON still on disk.
