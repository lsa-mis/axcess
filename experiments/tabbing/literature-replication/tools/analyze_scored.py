"""Recompute the scored run's headline numbers from raw per-subject records.

Checking a report against itself proves nothing, so this reads
`derived/kafe_scored.jsonl` -- the file the run appends to as it goes -- and
derives every figure independently. It works on a partial file, which is the
point: a run that is still going, or that died at subject 40, still yields a
defensible interim table with honest denominators.

Comparisons are against KAFE's reference **recomputed on the same retained
subset**, never the published 36/39. Comparing precision computed on different
retained subsets is the error `FEASIBILITY.md` section 6.6 exists to forbid.

Abstentions never become negatives. They are reported with their own
denominator and, separately, as a pessimistic sensitivity where every positive
abstention counts as a miss and every negative abstention as a false alarm.

Usage:
    uv run --offline --no-sync python -m tools.analyze_scored
"""

from __future__ import annotations

import json
import pathlib
import statistics
from fractions import Fraction

HERE = pathlib.Path(__file__).resolve().parent.parent
SCORED = HERE / "derived" / "kafe_scored.jsonl"
DENOM = HERE / "derived" / "kafe_denominator.json"
OUT = HERE / "derived" / "scored_summary.json"

CAP_MS = 300


def frac(num: int, den: int) -> str:
    """Exact fraction plus its decimal, or 'undefined' for a zero denominator."""
    if den == 0:
        return "undefined"
    return f"{num}/{den} = {float(Fraction(num, den)):.3f}"


def matrix(rows: list[dict]) -> dict:
    tp = sum(1 for r in rows if r["y"] and r["yhat"])
    fp = sum(1 for r in rows if not r["y"] and r["yhat"])
    fn = sum(1 for r in rows if r["y"] and not r["yhat"])
    tn = sum(1 for r in rows if not r["y"] and not r["yhat"])
    return {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "n": tp + fp + fn + tn,
        "precision": frac(tp, tp + fp),
        "recall": frac(tp, tp + fn),
        "f1": frac(2 * tp, 2 * tp + fp + fn),
    }


def main() -> int:
    if not SCORED.exists():
        print(f"no {SCORED.name} yet")
        return 1

    records = [json.loads(l) for l in SCORED.read_text().splitlines() if l.strip()]
    scored = [r for r in records if r.get("status") == "scored"]
    abstained = [r for r in records if r.get("status") != "scored"]

    denom = json.loads(DENOM.read_text())
    planned = denom["counts"]["replayable"]

    ours = matrix(scored)

    # KAFE's own result restricted to exactly the subjects we scored, so both
    # matrices are computed on one common set.
    labels = {s["subject"]: s for s in denom["subjects"]}
    common = [labels[r["subject"]] for r in scored if r["subject"] in labels]
    kafe = matrix(
        [{"y": s["y"], "yhat": 1 if s["kafe_yhat"] else 0} for s in common]
    )

    a_pos = sum(1 for r in abstained if r.get("y"))
    a_neg = sum(1 for r in abstained if r.get("y") is False)
    pess = {
        "TP": ours["TP"],
        "FP": ours["FP"] + a_neg,
        "FN": ours["FN"] + a_pos,
        "TN": ours["TN"],
        "precision": frac(ours["TP"], ours["TP"] + ours["FP"] + a_neg),
        "recall": frac(ours["TP"], ours["TP"] + ours["FN"] + a_pos),
    }

    med = [r["ms_median"] for r in scored if r.get("ms_median") is not None]
    allmax = [r["ms_max"] for r in scored if r.get("ms_max") is not None]
    timing = {
        "subjects_with_timing": len(med),
        "median_of_per_subject_medians_ms": round(statistics.median(med), 1) if med else None,
        "min_ms": round(min(med), 1) if med else None,
        "max_probe_ms_observed": round(max(allmax), 1) if allmax else None,
        "cap_ms": CAP_MS,
        "subjects_whose_median_is_within_cap": sum(1 for m in med if m <= CAP_MS),
        "total_probes": sum(r.get("addressable_candidates", 0) for r in scored),
        "total_probe_seconds": round(
            sum(r.get("ms_total", 0) for r in scored) / 1000, 1
        ),
    }

    summary = {
        "progress": {
            "planned": planned,
            "completed": len(records),
            "scored": len(scored),
            "abstained": len(abstained),
            "remaining": planned - len(records),
        },
        "axcess_frozen_detectors": ours,
        "kafe_same_common_set": kafe,
        "pessimistic_with_abstentions": pess,
        "abstentions": {
            "total": len(abstained),
            "positive_label": a_pos,
            "negative_label": a_neg,
            "reasons": sorted(
                {r.get("reason", "")[:60] for r in abstained}
            ),
        },
        "timing": timing,
    }
    OUT.write_text(json.dumps(summary, indent=2) + "\n")

    p = summary["progress"]
    print(f"progress: {p['scored']} scored + {p['abstained']} abstained "
          f"of {p['planned']} planned ({p['remaining']} remaining)")
    print()
    print(f"{'':<26}{'TP':>4}{'FP':>4}{'FN':>4}{'TN':>4}   precision            recall")
    for name, m in (("Axcess frozen detectors", ours), ("KAFE, same subjects", kafe)):
        print(f"{name:<26}{m['TP']:>4}{m['FP']:>4}{m['FN']:>4}{m['TN']:>4}   "
              f"{m['precision']:<20} {m['recall']}")
    print()
    print(f"abstentions: {len(abstained)} ({a_pos} positive, {a_neg} negative)")
    for reason in summary["abstentions"]["reasons"]:
        if reason:
            print(f"  - {reason}")
    print()
    print(f"per-probe median across subjects: {timing['median_of_per_subject_medians_ms']} ms "
          f"(cap {CAP_MS}); subjects within cap: "
          f"{timing['subjects_whose_median_is_within_cap']}/{timing['subjects_with_timing']}")
    print(f"total probes run: {timing['total_probes']:,} "
          f"in {timing['total_probe_seconds']:,.0f} s of probe time")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
