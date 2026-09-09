"""Run the frozen keyboard experiment and preserve a distinct result.

    uv run python -m experiments.tabbing.runner --label my-run

Every invocation verifies the frozen inputs. Output files are created
exclusively; choose a fresh label to repeat a run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from experiments.tabbing.runner.provenance import (  # noqa: E402
    bounded_int,
    require_new_outputs,
    safe_label,
    source_sha256,
    write_new,
)

# Capture before importing the measured code, and check again before execution.
IMPORT_FINGERPRINT = source_sha256()

from experiments.tabbing.runner import report  # noqa: E402
from experiments.tabbing.runner.corpus import load_corpus  # noqa: E402
from experiments.tabbing.runner.run import (  # noqa: E402
    VIEWPORTS,
    candidate_recall,
    resolve_paths,
    run_corpus,
    score_run,
    serialize_outcome,
)


async def _main(args: argparse.Namespace) -> int:
    fixtures_root, default_out = resolve_paths(REPO_ROOT)
    out_dir = Path(args.out) if args.out else default_out
    raw_path = out_dir / (f"{args.label}.raw.json" if args.label else "raw.json")
    md_path = out_dir / (f"{args.label}.results.md" if args.label else "results.md")
    require_new_outputs(raw_path, md_path)
    print(f"verifying frozen corpus at {fixtures_root} ...", flush=True)
    corpus = load_corpus(fixtures_root)
    print(f"  {len(corpus.probes)} probes, {len(corpus.pages)} pages; {corpus.corpus_sha256}")
    viewports = list(dict.fromkeys(args.viewports or VIEWPORTS))
    before = source_sha256()
    if before != IMPORT_FINGERPRINT:
        raise RuntimeError("source changed after import; restart the command before measuring")
    started = datetime.now(UTC).isoformat()
    state = await run_corpus(
        corpus,
        viewports=viewports,
        headless=not args.headed,
        max_tabs=args.max_tabs,
        settle_ms=args.settle_ms,
        probe_timeout_s=args.probe_timeout,
        run_timeout_s=args.run_timeout,
    )
    complete = not state.errors and len(state.outcomes) == len(corpus.probes) * len(viewports)
    scores = score_run(corpus, state, viewports)
    after = source_sha256()
    invalid: list[str] = []
    if before != after:
        invalid.append("detector or runner source changed during measurement")
    try:
        if load_corpus(fixtures_root).corpus_sha256 != corpus.corpus_sha256:
            invalid.append("corpus fingerprint changed during measurement")
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        invalid.append(f"corpus verification failed after measurement: {exc}")
    payload: dict[str, Any] = {
        "schema_version": 2,
        "run": {
            "valid": not invalid,
            "invalid_reasons": invalid,
            "complete": complete,
            "started_utc": started,
            "finished_utc": datetime.now(UTC).isoformat(),
            "label": args.label or "first",
            "first_run": not args.label,
            "corpus_sha256": corpus.corpus_sha256,
            "detector_sha256": before["detector"],
            "runner_sha256": before["runner"],
            "source_before": before,
            "source_after": after,
            "command": sys.argv,
            "settings": {
                "viewports": viewports,
                "max_tabs": args.max_tabs,
                "settle_ms": args.settle_ms,
                "probe_timeout_s": args.probe_timeout,
                "run_timeout_s": args.run_timeout,
                "headless": not args.headed,
            },
            "versions": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "playwright": version("playwright"),
                "chromium": state.browser_version,
            },
            "wall_seconds": state.timings.get("wall_seconds"),
            "errors": state.errors,
            "request_counters": {k: v for k, v in state.timings.items() if k != "wall_seconds"},
        },
        "viewports": viewports,
        "tab_orders": state.tab_orders,
        "candidates_by_page": {
            f"{page}@{vp}": state.candidates_by_page.get(f"{page}@{vp}")
            for vp in viewports
            for page in corpus.pages
        },
        "candidate_recall": [candidate_recall(corpus, state, v) for v in viewports],
        "dismissals": state.dismissals,
        "probes": [serialize_outcome(o) for o in state.outcomes],
        "candidate_gated_probes": [serialize_outcome(o) for o in state.candidate_outcomes],
        "scores": [] if invalid else [s.to_json() for s in scores],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    write_new(raw_path, json.dumps(payload, indent=2) + "\n")
    write_new(md_path, report.render(payload))
    print(f"\nwrote {raw_path}\nwrote {md_path}\n")
    print(report.render(payload))
    return 1 if invalid or state.errors else 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--out", help="output directory (default experiments/tabbing/results)")
    result.add_argument("--label", type=safe_label, help="unique name for this run")
    result.add_argument("--headed", action="store_true", help="show the browser")
    result.add_argument("--max-tabs", type=bounded_int(1, 3000), default=300)
    result.add_argument("--settle-ms", type=bounded_int(0, 3000), default=250)
    result.add_argument(
        "--probe-timeout",
        type=bounded_int(1, 300),
        default=60,
        help="seconds per probe or discovery stage",
    )
    result.add_argument(
        "--run-timeout",
        type=bounded_int(1, 7200),
        default=1800,
        help="seconds for the complete browser measurement",
    )
    result.add_argument(
        "--viewport",
        action="append",
        dest="viewports",
        choices=sorted(VIEWPORTS),
        help="window size (repeatable)",
    )
    return result


def main() -> int:
    try:
        return asyncio.run(_main(parser().parse_args()))
    except (FileExistsError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
