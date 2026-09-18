"""Score C10-C16 for any corpus, from that corpus's own probe observations.

C10-C16 are not in `bakeoff.py`. They are dismissal and promotion rules layered
on C9, scored offline by `probes/score_new.py` (C10-C13) and `probes/score_new2.py`
(C14-C16) from four saved observation files. Both of those scorers hard-code the
fixtures artifact and the fixtures truth, so the rules have only ever been
scored on fixtures. This states the same rules against whichever corpus it is
pointed at, so the matrix can carry C10-C16 everywhere the observations exist.

The rule bodies below are transcribed from `score_new.py` and `score_new2.py`
unchanged -- same predicates, same order, same scoring -- so that running this
against fixtures reproduces `CHEAP_DETECTOR_REVIEW.md` exactly. No detector or
scoring code is imported; the answer key is read only to score, never to decide.

    uv run --offline --no-sync python -m tools.run_probe_rules \\
        --corpus fixtures --artifact .../bakeoff-fixtures-closed.json \\
        --observations experiments/tabbing/probes
"""

from __future__ import annotations

import argparse
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[4]
HERE = pathlib.Path(__file__).resolve().parent.parent

CORPUS_ROOTS = {
    "fixtures": REPO / "experiments" / "tabbing" / "fixtures",
    "edgecases": REPO / "experiments" / "tabbing" / "edgecases",
    "gds": HERE / "artifacts" / "gds-corpus",
    "ma11y": HERE / "artifacts" / "ma11y",
}

OBSERVATIONS = ("containment", "composite", "effect", "effect2")


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def labels_of(truth: dict) -> dict[str, str]:
    return {
        probe: row.get("labels_by_viewport", {}).get("desktop", row["label"])
        for probe, row in truth["probes"].items()
    }


def rule_sets(c9: set[str], universe: set[str], features: dict, obs: dict) -> dict[str, set[str]]:
    """R1, R2, R3, R5-R9 exactly as `score_new.py` and `score_new2.py` state them."""
    con, comp, eff, eff2 = (obs[k] for k in OBSERVATIONS)

    # R1 redundant click surface: the lead wraps, or sits inside, a keyboard-
    #    reachable native control, so the same action already has a tab stop.
    r1 = {p for p in c9 if con.get(p, {}).get("contains_focusable")
          or con.get(p, {}).get("inside_focusable")}
    # R2 roving tabindex: an ARIA item role inside a composite container whose
    #    sibling holds the tab stop -- the APG arrow-key pattern, not a defect.
    r2 = {p for p in c9 if comp.get(p, {}).get("owner_role")
          and comp.get(p, {}).get("sibling_tabbable")
          and (comp.get(p, {}).get("own_tabindex") or "") == "-1"}
    # R3 declared shortcut: aria-keyshortcuts, or a chord such as "Alt+K" in the
    #    element's own accessible text, names a keyboard path to the same action.
    r3 = {p for p in c9 if comp.get(p, {}).get("aria_keyshortcuts")
          or comp.get(p, {}).get("chord_in_text")}
    # R5 no action path at all: nothing observed can carry out an action, so
    #    there is no keyboard operation to be missing.
    r5 = {p for p in c9 if eff.get(p, {}).get("own_activation") == []
          and not features.get(p, {}).get("delegated_types")
          and not features.get(p, {}).get("label_toggle")
          and eff.get(p, {}).get("hover_reveal") is False}
    c13 = c9 - r1 - r2 - r3 - r5
    # R6 name twin: a visible, Tab-reachable native control carries the same
    #    accessible name, so the action already has a keyboard route.
    r6 = {p for p in c13 if eff2.get(p, {}).get("name_twin")}
    # R7 framework props beat delegation.
    r7 = {p for p in c13 if eff2.get(p, {}).get("framework")
          and eff2.get(p, {}).get("framework_activation") is False}
    # R8 no click effect: a real click changes nothing rendered.
    r8 = {p for p in c13 if eff2.get(p, {}).get("click_effect") is False}
    # R9 divergent key effect -- a PROMOTION, not a dismissal.
    r9 = {p for p in universe if eff2.get(p, {}).get("click_effect")
          and eff2.get(p, {}).get("key_effect")
          and eff2.get(p, {}).get("same_effect") is False}
    return {"R1": r1, "R2": r2, "R3": r3, "R5": r5, "R6": r6, "R7": r7, "R8": r8, "R9": r9,
            "C13": c13}


def score(reported: set[str], unknown: set[str], positive: set[str],
          negative: set[str]) -> dict:
    reported = reported - unknown
    tp, fp = len(reported & positive), len(reported & negative)
    fn = len(positive - reported - unknown)
    precision = tp / (tp + fp) if tp + fp else None
    # Strict recall: TP over ALL labelled defects, undecided ones included. This
    # is what `bakeoff.py` publishes as `recall`; its `recall_conditional`
    # divides by decided defects only.
    recall = tp / len(positive) if positive else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else None)
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "unknown": len(unknown),
        "unknown_positive": len(unknown & positive),
        "unknown_negative": len(unknown & negative),
        "decided": len(positive | negative) - len(unknown),
        "precision": precision, "recall": recall, "f1": f1,
        "reported": sorted(reported),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", choices=sorted(CORPUS_ROOTS), required=True)
    parser.add_argument("--artifact", required=True,
                        help="a bakeoff run with --candidate-study, for the C9 lead set")
    parser.add_argument("--observations", required=True,
                        help="directory holding containment/composite/effect/effect2 .json")
    parser.add_argument("--out", help="where to write the scored rows")
    args = parser.parse_args()

    root = CORPUS_ROOTS[args.corpus]
    artifact = load(pathlib.Path(args.artifact))
    truth = load(root / "truth.json")
    obs_dir = pathlib.Path(args.observations)

    missing = [n for n in OBSERVATIONS if not (obs_dir / f"{n}.json").exists()]
    if missing:
        print(f"{args.corpus}: cannot score C10-C16 — missing observations: "
              f"{', '.join(missing)}")
        return 3
    obs = {name: load(obs_dir / f"{name}.json") for name in OBSERVATIONS}
    timings = {name: (load(obs_dir / f"{name}.json.timing.json")
                      if (obs_dir / f"{name}.json.timing.json").exists() else None)
               for name in OBSERVATIONS}

    labels = labels_of(truth)
    universe = set(labels)
    positive = {p for p, label in labels.items() if label == "violation"}
    negative = universe - positive

    c9_name = next((k for k in artifact.get("reported", {}) if k.startswith("C9")), None)
    if c9_name is None:
        print(f"{args.corpus}: cannot score C10-C16 — the artifact has no C9 lead set; "
              "re-run bakeoff.py with --candidate-study")
        return 3
    c9 = set(artifact["reported"][c9_name])
    unknown = set(artifact.get("unobservable", {}).get(c9_name, []))
    features = {p: f for ev in artifact.get("candidate_evidence", {}).values()
                for p, f in ev.get("features", {}).items()}

    sets = rule_sets(c9, universe, features, obs)
    r1, r2, r3, r5 = sets["R1"], sets["R2"], sets["R3"], sets["R5"]
    r6, r7, r8, r9 = sets["R6"], sets["R7"], sets["R8"], sets["R9"]
    c13 = sets["C13"]

    targets = artifact.get("probes") or len(universe)

    def ms(name: str) -> float | None:
        row = timings.get(name)
        return None if row is None else row["observation_ms"]

    # Each rule is priced at what its own observation cost, on top of C9. The
    # C9 base itself is priced by the matrix assembler from the same run's
    # `page_timings_ms`; carrying it here too would double-count it.
    con_ms, comp_ms, eff_ms, eff2_ms = (ms(n) for n in OBSERVATIONS)

    def added(*parts: float | None) -> float | None:
        present = [p for p in parts if p is not None]
        if len(present) != len(parts):
            return None
        return round(sum(present) / targets, 1) if targets else None

    rows = [
        ("C10 = C9 minus redundant click surfaces (R1)", c9 - r1, unknown,
         added(con_ms), "+ R1"),
        ("C11 = C10 minus roving-tabindex items (R2)", c9 - r1 - r2, unknown,
         added(con_ms, comp_ms), "+ R2"),
        ("C12 = C11 minus declared shortcuts (R3)", c9 - r1 - r2 - r3, unknown,
         added(con_ms, comp_ms), "+ R3, same pass"),
        ("C13 = C12 minus leads with no action path (R5)", c13, unknown,
         added(con_ms, comp_ms, eff_ms), "+ R5"),
        ("C14 = C13 minus name-twinned leads (R6)", c13 - r6, unknown,
         added(con_ms, comp_ms, eff_ms), "+ R6, free"),
        ("C15 = C14 minus leads with no click effect (R7, R8)", c13 - r6 - r7 - r8,
         unknown, added(con_ms, comp_ms, eff_ms, eff2_ms), "+ behavioural pass"),
        ("C16 = C15 plus divergent-key-effect promotions (R9)",
         (c13 - r6 - r7 - r8) | r9, unknown - r9,
         added(con_ms, comp_ms, eff_ms, eff2_ms), "+ R9, same pass"),
    ]

    lead_set = (timings["effect2"] or {}).get("lead_set", "unrecorded")
    observed = (timings["effect2"] or {}).get("observed")
    out: dict[str, dict] = {}
    for name, reported, unk, cost, covers in rows:
        row = score(reported, unk, positive, negative)
        row["ms_per_target_added"] = cost
        row["ms_covers"] = covers
        row["lead_set_observed"] = lead_set
        row["probes_observed"] = observed
        out[name] = row

    payload = {
        "corpus": args.corpus,
        "artifact": str(args.artifact),
        "observations": str(obs_dir),
        "c9_row": c9_name,
        "targets": targets,
        "defects": len(positive),
        "lead_set_observed": lead_set,
        "probes_observed": observed,
        "observation_ms": {n: ms(n) for n in OBSERVATIONS},
        "rule_fires": {k: sorted(v) for k, v in sets.items() if k != "C13"},
        "rows": out,
    }
    if args.out:
        path = pathlib.Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"{args.corpus}: {len(positive)} defects of {targets} targets; C9 from {c9_name}; "
          f"behavioural lead set = {lead_set} ({observed} observed)")
    print(f"{'rule':<52}{'TP':>4}{'FP':>4}{'FN':>4}{'unk p/n':>9}{'prec':>8}"
          f"{'strict rec':>12}{'F1':>8}{'+ms/target':>12}")
    for name, row in out.items():
        def pct(v):
            return "—" if v is None else f"{v * 100:.1f}%"
        cost = "—" if row["ms_per_target_added"] is None else f"{row['ms_per_target_added']:.1f}"
        print(f"{name[:51]:<52}{row['tp']:>4}{row['fp']:>4}{row['fn']:>4}"
              f"{str(row['unknown_positive']) + '/' + str(row['unknown_negative']):>9}"
              f"{pct(row['precision']):>8}{pct(row['recall']):>12}{pct(row['f1']):>8}{cost:>12}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
