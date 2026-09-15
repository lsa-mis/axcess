"""Derive the real scoring denominator for the 53 replayable KAFE subjects.

`FEASIBILITY.md` §6 previously assumed a three-subject denominator. 53 subjects
are now on disk and replayable, which changes every count in the protocol and
changes the reference threshold the target hypothesis is stated against.

This tool recomputes, from the two artifacts and nothing else:

* which of the 60 published subjects are in the replayable set, and why each
  excluded one is excluded;
* the Type 1 (IAF) label distribution on that set;
* KAFE's own confusion matrix **restricted to that same set**, because a
  precision comparison against 36/39 would be comparing metrics computed on
  different retained subsets (§6.6 forbids exactly that).

Two controls run before anything is reported, because a subset arithmetic bug
produces a plausible-looking table rather than an error:

* P1 the full-corpus recompute must reproduce the published TP=36 FP=3 FN=0
  TN=21. If the reader disagrees with the authors on all 60, its subset is
  worthless.
* P2 the excluded rows must account for exactly the difference between the
  full-corpus and subset counts, per label class.

Neither control reads a detector output; this is reference bookkeeping only.

Usage:
    uv run --offline --no-sync python -m tools.kafe_denominator
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
RESULTS = HERE / "artifacts" / "kafe_results_to_reproduce.csv"
CENSUS = HERE / "derived" / "kafe_corpus_census.json"
OUT = HERE / "derived" / "kafe_denominator.json"

# Present on Drive as expanded asset directories, not single flow dumps, so no
# capture was fetched for them. Recorded by name so the exclusion is auditable
# rather than implied by absence.
FOLDER_FORM = {"battlenet", "canon", "dmv_wc", "gizmodo", "speedway"}

RESULT_COL = "Type 1 Detection Result: "
TRUTH_COL = "Type 1 Detection Ground Truth: "


def _bool(cell: str) -> bool | None:
    """TRUE/FALSE only. Anything else is undecidable and must not become False."""
    text = (cell or "").strip().upper()
    if text == "TRUE":
        return True
    if text == "FALSE":
        return False
    return None


def load_reference() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with RESULTS.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            subject = (row.get("Subject") or "").strip()
            if not subject:
                continue  # the sheet carries blank trailing rows and a totals block
            rows[subject] = {
                "y": _bool(row[TRUTH_COL]),
                "yhat": _bool(row[RESULT_COL]),
            }
    return rows


def load_census() -> dict[str, dict]:
    return {r["subject"]: r for r in json.loads(CENSUS.read_text(encoding="utf-8"))}


def matrix(items: list[dict]) -> dict:
    tp = sum(1 for r in items if r["y"] and r["kafe_yhat"])
    fp = sum(1 for r in items if r["y"] is False and r["kafe_yhat"])
    fn = sum(1 for r in items if r["y"] and r["kafe_yhat"] is False)
    tn = sum(1 for r in items if r["y"] is False and r["kafe_yhat"] is False)
    return {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "n": tp + fp + fn + tn,
        # Exact rationals. §6.7 compares fractions, never rounded percentages.
        "precision": f"{tp}/{tp + fp}" if tp + fp else "undefined",
        "recall": f"{tp}/{tp + fn}" if tp + fn else "undefined",
    }


def main() -> int:
    reference = load_reference()
    census = load_census()

    records = []
    for subject, ref in sorted(reference.items()):
        seen = census.get(subject)
        if subject in FOLDER_FORM:
            status, reason = "excluded", "folder-form on Drive; no flow dump fetched"
        elif seen is None:
            status, reason = "excluded", "not present in the capture census"
        elif seen.get("entry") is None:
            status, reason = "excluded", "capture parses to no HTML entry document"
        else:
            status, reason = "replayable", ""
        records.append(
            {
                "subject": subject,
                "status": status,
                "exclusion_reason": reason,
                "y": ref["y"],
                "kafe_yhat": ref["yhat"],
                "flows": (seen or {}).get("flows"),
                "unreadable_flows": (seen or {}).get("unreadable"),
                "entry": (seen or {}).get("entry"),
            }
        )

    replayable = [r for r in records if r["status"] == "replayable"]
    excluded = [r for r in records if r["status"] == "excluded"]

    full = matrix(records)
    subset = matrix(replayable)

    # P1: the reader must agree with the authors on all 60 before its subset
    # arithmetic is worth reading.
    published = {"TP": 36, "FP": 3, "FN": 0, "TN": 21}
    p1 = all(full[k] == v for k, v in published.items())

    # P2: excluded rows must account for the whole difference, per label class.
    excluded_pos = sum(1 for r in excluded if r["y"] is True)
    excluded_neg = sum(1 for r in excluded if r["y"] is False)
    p2 = (
        full["TP"] + full["FN"] - (subset["TP"] + subset["FN"]) == excluded_pos
        and full["FP"] + full["TN"] - (subset["FP"] + subset["TN"]) == excluded_neg
    )

    payload = {
        "controls": {
            "P1_full_corpus_reproduces_published": p1,
            "P1_published": published,
            "P1_observed": {k: full[k] for k in published},
            "P2_exclusions_account_for_difference": p2,
            "valid": p1 and p2,
        },
        "full_corpus": full,
        "replayable_subset": subset,
        "counts": {
            "published_subjects": len(records),
            "replayable": len(replayable),
            "excluded": len(excluded),
            "replayable_positive": sum(1 for r in replayable if r["y"] is True),
            "replayable_negative": sum(1 for r in replayable if r["y"] is False),
            "replayable_label_unknown": sum(1 for r in replayable if r["y"] is None),
            "excluded_positive": excluded_pos,
            "excluded_negative": excluded_neg,
        },
        "kafe_false_positives_in_subset": sorted(
            r["subject"] for r in replayable if r["y"] is False and r["kafe_yhat"]
        ),
        "partial_read_subjects": sorted(
            r["subject"] for r in replayable if r["unreadable_flows"]
        ),
        "excluded_subjects": [
            {"subject": r["subject"], "reason": r["exclusion_reason"], "y": r["y"]}
            for r in excluded
        ],
        "subjects": records,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")

    print(json.dumps(payload["controls"], indent=1))
    print(json.dumps(payload["counts"], indent=1))
    print("full corpus   ", json.dumps(full))
    print("replayable 53 ", json.dumps(subset))
    print("KAFE FPs in subset:", payload["kafe_false_positives_in_subset"])
    print("partial-read subjects:", payload["partial_read_subjects"])

    if not payload["controls"]["valid"]:
        print("CONTROL FAILED - denominator not usable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
