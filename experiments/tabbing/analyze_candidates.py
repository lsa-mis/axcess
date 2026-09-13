# ruff: noqa: S101 - this is an assertion-based artifact audit; -O is rejected below.
"""Independently audit candidate-study JSON and print a reviewable error table.

This script uses saved observations and the frozen answer key. It deliberately
does not import the detector or scoring implementation that produced the data.
Run with Python and one or more bakeoff JSON paths; stdout is Markdown.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if not __debug__:
    raise SystemExit("Run without -O: this artifact audit requires assertions")


def audit(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    truth = json.loads((ROOT / "fixtures/truth.json").read_text())
    labels = {
        pid: row.get("labels_by_viewport", {}).get("desktop", row["label"])
        for pid, row in truth["probes"].items()
    }
    universe = set(labels)
    positive = {pid for pid, label in labels.items() if label == "violation"}
    negative = universe - positive
    assert data["run"]["valid"] and not data["run"]["errors"]
    assert data["run"]["source_sha256_before"] == data["run"]["source_sha256_after"]
    assert data["run"]["corpus_sha256"] == data["run"]["corpus_sha256_after"]
    manifest = json.loads((ROOT / "fixtures/frozen-manifest.json").read_text())
    assert data["run"]["corpus_sha256"] == manifest["corpus_sha256"]
    for relative, digest in manifest["files"].items():
        assert hashlib.sha256((ROOT / "fixtures" / relative).read_bytes()).hexdigest() == digest
    assert data["probes"] == len(universe) == 95 and len(positive) == 39
    assert set(data["candidate_evidence"]) == set(truth["pages"])
    names = {name.split(" ", 1)[0]: name for name in data["reported"] if name.startswith("C")}
    expected_reported: dict[str, set[str]] = {name: set() for name in names}
    expected_proposed: dict[str, set[str]] = {name: set() for name in names}
    expected_unknown: dict[str, set[str]] = {name: set() for name in names}
    upstream_raw: dict[str, set[str]] = {}
    upstream_reported: dict[str, set[str]] = {}
    for page, evidence in data["candidate_evidence"].items():
        features = evidence["features"]
        assert set(features) == set(truth["pages"][page])
        raw = {name: set(ids) for name, ids in evidence["upstream_proposals"].items()}
        tab = set(evidence["tab_order"]["index"])
        # These frozen pages all completed their Tab walk. If a future run caps,
        # review its uncertainty handling before reusing this independent audit.
        assert not evidence["tab_order"]["capped"]
        for family, ids in raw.items():
            upstream_raw.setdefault(family, set()).update(ids)
            upstream_reported.setdefault(family, set()).update(ids if family == "D1" else ids - tab)
        base = raw["D4"] | raw["D5"] | raw["D6"]
        available = {
            pid
            for pid, f in features.items()
            if f["visible"] and not f["inert"] and not f["pointer_events_none"]
        }
        unobstructed = {pid for pid in available if features[pid]["center_hit"] is not False}
        custom = {
            pid
            for pid in (raw["D5"] | raw["D6"] | raw["D2b"] | raw["D7"]) & tab & available
            if not features[pid]["native"]
        }
        no_key = {pid for pid in custom if not features[pid]["has_key_handler"]}
        labels_proposed = {
            pid
            for pid in available
            if features[pid]["label_toggle"] and not features[pid]["control_disabled"]
        }
        missing_control = {pid for pid in labels_proposed if not features[pid]["control_probe"]}
        bad_label = {
            pid
            for pid in labels_proposed - missing_control
            if features[pid]["control_probe"] not in tab
        }
        delegated = {
            pid
            for pid in available
            if not features[pid]["native"] and features[pid]["delegated_types"]
        }
        proposed = {
            "C1": base,
            "C2": base | raw["D8"],
            "C3": base & available,
            "C4": base & unobstructed,
            "C5": custom,
            "C6": labels_proposed,
            "C7": delegated,
            "C8": (base & available) | custom | labels_proposed | delegated,
        }
        proposed["C9"] = proposed["C8"] & unobstructed
        reported = {key: proposed[key] - tab for key in ("C1", "C2", "C3", "C4", "C7")}
        reported.update(C5=no_key, C6=bad_label)
        reported["C8"] = reported["C3"] | no_key | bad_label | reported["C7"]
        reported["C9"] = reported["C8"] & unobstructed
        opaque = {pid for pid, f in features.items() if f["closed_shadow"] and pid not in tab}
        for key in names:
            unknown = set() if key in ("C1", "C2") else opaque & proposed[key]
            if key in ("C6", "C8", "C9"):
                unknown |= missing_control & proposed[key]
            expected_proposed[key].update(proposed[key])
            expected_reported[key].update(reported[key] - unknown)
            expected_unknown[key].update(unknown)
    for key, name in names.items():
        assert set(data["proposed"][name]) == expected_proposed[key], name
        assert set(data["reported"][name]) == expected_reported[key], name
        assert set(data["unobservable"].get(name, [])) == expected_unknown[key], name
    for family, ids in upstream_raw.items():
        name = next(n for n in data["reported"] if n.startswith(f"U-{family} "))
        assert set(data["proposed"][name]) == ids
        assert set(data["reported"][name]) == upstream_reported[family]

    for score in data["scores"]:
        name = score["detector"]
        unknown = set(data["unobservable"].get(name, []))
        reported = set(data["reported"][name]) - unknown
        assert (unknown | reported) <= universe
        tp, fp = len(reported & positive), len(reported & negative)
        fn = len(positive - reported - unknown)
        tn = len(negative - reported - unknown)
        expected = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "unknown": len(unknown),
            "unknown_positive": len(unknown & positive),
            "unknown_negative": len(unknown & negative),
            "decided": len(universe - unknown),
            "total": len(universe),
        }
        for key, value in expected.items():
            assert score[key] == value, (name, key, score[key], value)
        assert set(score["false_positives"]) == reported & negative
        assert set(score["false_negatives"]) == positive - reported - unknown
        assert set(score["undecided"]) == unknown
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / len(positive)
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
        for key, value in {"precision": precision, "recall": recall, "f1": f1}.items():
            assert score[key] == (None if value is None else round(value, 4)), (name, key)
    for name, ids in data["proposed"].items():
        queue = set(ids)
        row = data["proposal_coverage"][name]
        assert row["candidates"] == len(queue)
        assert row["positive_candidates"] == len(queue & positive)
        assert row["positive_total"] == len(positive)
        assert set(row["missing_positive_candidates"]) == positive - queue
    return data


def display(path: Path, data: dict[str, Any]) -> None:
    print(f"\nArtifact: `{path.name}`; SHA256 `{hashlib.sha256(path.read_bytes()).hexdigest()}`.\n")
    print(
        "Verified all score counts, strict recall, candidate queues, "
        "and C1-C9 feature-derived sets.\n"
    )
    print(
        "| Method | TP | FP | FN | Unknown (+/-) | Precision | Recall | F1 | "
        "Queue | Defects in queue |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    def pct(value: float | None) -> str:
        return "—" if value is None else f"{100 * value:.1f}%"

    for score in data["scores"]:
        name = score["detector"]
        if not name.startswith(("C", "U-")):
            continue
        queue = data["proposal_coverage"][name]

        escaped_name = name.replace("|", "\\|")
        print(
            f"| {escaped_name} | {score['tp']} | {score['fp']} | {score['fn']} | "
            f"{score['unknown_positive']}/{score['unknown_negative']} | "
            f"{pct(score['precision'])} | "
            f"{pct(score['recall'])} | {pct(score['f1'])} | {queue['candidates']}/95 | "
            f"{queue['positive_candidates']}/39 |"
        )
    c9 = next(s for s in data["scores"] if s["detector"].startswith("C9 "))
    print(f"\nC9 false positives: {', '.join(c9['false_positives'])}.")
    print(
        f"\nC9 false negatives: {', '.join(c9['false_negatives'])}; "
        f"undecided: {', '.join(c9['undecided'])}."
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python analyze_candidates.py ARTIFACT.json [REPEAT.json]")
    results = [(Path(value), audit(Path(value))) for value in sys.argv[1:]]
    for path, data in results:
        display(path, data)
    if len(results) > 1:
        first = results[0][1]
        for _, other in results[1:]:
            for key in ("reported", "unobservable", "proposed"):
                common = set(first[key]) & set(other[key])
                changed = [name for name in common if first[key][name] != other[key][name]]
                print(f"\nRepeat differences in {key}: {', '.join(sorted(changed)) or 'none'}.")
