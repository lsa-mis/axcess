"""Observe the four probe files for one corpus, into that corpus's own directory.

The probe scripts have always read `PROBE_CORPUS`; they had simply never been
pointed anywhere but fixtures, which is why C10-C16 existed in no other
environment. This drives all four in one process so a corpus is observed as a
unit, and so the corpus root is set once rather than repeated per invocation.

    uv run --offline --no-sync python -m tools.run_probes \\
        --corpus fixtures --out derived/probes/fixtures-c12 \\
        --only experiments/tabbing/probes/c12.json
"""

from __future__ import annotations

import argparse
import os
import pathlib
import runpy
import sys

REPO = pathlib.Path(__file__).resolve().parents[4]
HERE = pathlib.Path(__file__).resolve().parent.parent
PROBES = REPO / "experiments" / "tabbing" / "probes"

# Relative to the repo root: the probe scripts resolve the corpus themselves.
CORPUS_ROOTS = {
    "fixtures": "experiments/tabbing/fixtures",
    "edgecases": "experiments/tabbing/edgecases",
    "gds": "experiments/tabbing/literature-replication/artifacts/gds-corpus",
    "ma11y": "experiments/tabbing/literature-replication/artifacts/ma11y",
}

ORDER = ("containment", "composite", "effect", "effect2")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", choices=sorted(CORPUS_ROOTS), required=True)
    parser.add_argument("--out", required=True, help="directory for the observations")
    parser.add_argument("--only", help="JSON list of probe ids for the behavioural pass")
    parser.add_argument("--skip", nargs="*", default=[],
                        help="probe names to leave alone (already observed)")
    args = parser.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    os.environ["PROBE_CORPUS"] = CORPUS_ROOTS[args.corpus]

    saved = list(sys.argv)
    failures = []
    try:
        for name in ORDER:
            if name in args.skip:
                print(f"-- {name}: skipped")
                continue
            script = PROBES / f"probe_{name}.py"
            target = out / f"{name}.json"
            sys.argv = [str(script), str(target)]
            if name == "effect2" and args.only:
                sys.argv.append(args.only)
            print(f"-- {name} -> {target}")
            try:
                # Each probe script runs its work at import time, under a guard
                # of `asyncio.run(...)` at module level.
                runpy.run_path(str(script), run_name="__main__")
            except Exception as exc:
                failures.append(f"{name}: {type(exc).__name__}: {exc}")
                print(f"   FAILED {type(exc).__name__}: {exc}")
    finally:
        sys.argv = saved

    if failures:
        print(f"\n{len(failures)} probe(s) failed:")
        for line in failures:
            print(f"  {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
