"""Assemble the cross-environment detector matrix from the bakeoff outputs.

One row per detector per environment: TP, FP, FN, abstentions, precision,
recall, F1, and **per-button milliseconds** -- the detector's measured browser
time divided by the probes it decided, which is the unit Harry's 300 ms cap is
stated in. The existing `detector-matrix.results.md` quotes `ms/target`
amortised over every target instead; that is a throughput figure, a different
number, and both are emitted here under distinct names rather than conflated.

Reads only what the bakeoff wrote (`scores`, `page_timings_ms`). Recomputing
from the raw artifacts is the point: a summary checked against itself proves
nothing.

Usage:
    uv run --offline --no-sync python -m tools.assemble_matrix
"""

from __future__ import annotations

import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[4]
HERE = pathlib.Path(__file__).resolve().parent.parent
OUT = HERE / "derived" / "matrix.json"

CAP_MS = 300

CORPORA = {
    "fixtures": (
        REPO / "experiments" / "tabbing" / "fixtures" / "results",
        "blind-authored synthetic; 95 probes, 39 defects",
        None,
    ),
    "edgecases": (
        REPO / "experiments" / "tabbing" / "edgecases" / "results",
        "shared-author development corpus; no unbiased accuracy claim",
        None,
    ),
    "gds": (
        HERE / "artifacts" / "gds-corpus" / "results",
        "GDS Accessibility Tool Audit (MIT); 6 IAF cases, 2 controls",
        "all 13 audited tools score 0/6",
    ),
    "ma11y": (
        HERE / "artifacts" / "ma11y" / "results",
        "Ma11y-generated mutants; 1 verified fault, 2 controls",
        "no published reference; ground truth by construction",
    ),
}

# `page_timings_ms` prices what actually ran. Two kinds of row have no key of
# their own and must be priced by composition, or the ms column silently goes
# blank on exactly the rules Harry's table leads with:
#   - D1/D1x are two scored rows built from one axe-core measurement.
#   - C1-C9 are unions of cheap detectors; a combination costs what its inputs
#     cost, since they share the one survey walk.
# Anything not listed here keeps its own measured key.
TIMING_ALIASES = {
    "D1 axe-core (keyboard rules)": ["D1 axe-core"],
    "D1x axe-core (any rule, unsound)": ["D1 axe-core"],
    "C1 upstream D4|D5|D6, minus Tab": [
        "D4 CSS + lexical", "D5 CDP getEventListeners", "D6 addEventListener shim",
    ],
    "C2 upstream D4|D5|D6|D8, minus Tab": [
        "D4 CSS + lexical", "D5 CDP getEventListeners", "D6 addEventListener shim",
        "D8 hover-diff",
    ],
    "C3 union, reject inert and pointer-events:none": [
        "D4 CSS + lexical", "D5 CDP getEventListeners", "D6 addEventListener shim",
        "D8 hover-diff",
    ],
    "C4 union, additionally reject blocked center": [
        "D4 CSS + lexical", "D5 CDP getEventListeners", "D6 addEventListener shim",
        "D8 hover-diff",
    ],
    "C5 focusable custom mouse control, no observed key handler": [
        "D5 CDP getEventListeners", "D6 addEventListener shim",
    ],
    "C6 visible label for a toggle absent from Tab": ["D4 CSS + lexical"],
    "C7 ancestor mouse listener, minus Tab": [
        "D5 CDP getEventListeners", "D6 addEventListener shim",
    ],
    "C8 union + focusable + label + ancestor leads": [
        "D4 CSS + lexical", "D5 CDP getEventListeners", "D6 addEventListener shim",
        "D8 hover-diff",
    ],
    "C9 combined leads, additionally reject blocked center": [
        "D4 CSS + lexical", "D5 CDP getEventListeners", "D6 addEventListener shim",
        "D8 hover-diff",
    ],
}


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def main() -> int:
    matrix: dict[str, dict[str, dict]] = {}
    meta: dict[str, dict] = {}

    for corpus, (results_dir, caveat, reference) in CORPORA.items():
        if not results_dir.exists():
            meta[corpus] = {"status": "not run yet", "caveat": caveat}
            continue

        merged: dict[str, dict] = {}
        files = sorted(results_dir.glob("bakeoff-*.json"))
        for path in files:
            try:
                payload = json.loads(path.read_text())
            except Exception:
                continue  # a run still writing its file is not an error here

            timings: dict[str, float] = {}
            shared = 0.0
            for page in (payload.get("page_timings_ms") or {}).values():
                for name, ms in page.items():
                    if name.startswith("survey"):
                        shared += ms
                    else:
                        timings[name] = timings.get(name, 0.0) + ms

            probes = payload.get("probes") or 0
            for row in payload.get("scores") or []:
                name = row.get("detector")
                if not name:
                    continue
                decided = row.get("decided") or 0
                parts = TIMING_ALIASES.get(name, [name])
                have = [timings[p] for p in parts if p in timings]
                own = sum(have) if have else None
                # Cheap detectors read one shared DOM walk; their own method
                # call is meaningless without it, so the shared cost is added
                # in. That matches how the published table prices them.
                total = None if own is None else own + shared
                merged[name] = {
                    "tp": row.get("tp"),
                    "fp": row.get("fp"),
                    "fn": row.get("fn"),
                    "tn": row.get("tn"),
                    "unknown": row.get("unknown"),
                    "unknown_positive": row.get("unknown_positive"),
                    "unknown_negative": row.get("unknown_negative"),
                    "precision": row.get("precision"),
                    "recall": row.get("recall"),
                    "f1": row.get("f1"),
                    "decided": decided,
                    "probes": probes,
                    "ms_total": None if total is None else round(total, 1),
                    "ms_per_button": (
                        None if not total or not decided else round(total / decided, 1)
                    ),
                    "ms_per_target": (
                        None if not total or not probes else round(total / probes, 1)
                    ),
                    "source": path.name,
                }

        matrix[corpus] = merged
        meta[corpus] = {
            "status": f"{len(merged)} detectors",
            "caveat": caveat,
            "reference": reference,
            "files": [p.name for p in files],
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"meta": meta, "matrix": matrix}, indent=2) + "\n")

    for corpus, info in meta.items():
        print(f"{corpus:<12}{info['status']:<18}{info.get('caveat','')[:48]}")
    print()

    names = sorted({n for rows in matrix.values() for n in rows})
    print(f"{len(names)} detectors across {len(matrix)} corpora\n")
    for corpus in matrix:
        rows = matrix[corpus]
        if not rows:
            continue
        print(f"--- {corpus}")
        print(f"{'detector':<50}{'TP':>4}{'FP':>4}{'FN':>4}{'unk':>5}"
              f"{'prec':>8}{'recall':>9}{'ms/btn':>9}")
        for name in sorted(rows):
            r = rows[name]
            ms = "—" if r["ms_per_button"] is None else f"{r['ms_per_button']:.1f}"
            print(
                f"{name[:49]:<50}{r['tp']:>4}{r['fp']:>4}{r['fn']:>4}"
                f"{r['unknown']:>5}{pct(r['precision']):>8}{pct(r['recall']):>9}{ms:>9}"
            )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
