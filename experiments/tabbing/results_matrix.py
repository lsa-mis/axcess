"""Emit one table of every detector and rule: precision, recall, F1, and ms.

Reads the two published bake-off artifacts plus the standalone probe
observations, and writes a generated results file. Scores come from the
artifacts unchanged; C10-C16 are rebuilt here from saved observations the same
way `probes/score_new*.py` rebuild them, without importing detector or scoring
code.

    python experiments/tabbing/results_matrix.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHEAP = ROOT / "fixtures/results/bakeoff-fixtures-cheap-study-v1.json"
FULL = ROOT / "fixtures/results/bakeoff-fixtures-candidate-reviewed.json"
OBS = ROOT / "probes"
OUT = ROOT / "results/detector-matrix.results.md"

# What each family needs on the page before its own method call can run. The
# ms column is meaningless without this: D4 costs 0.37 ms, but only after the
# 36 ms of setup, Tab traversal, visibility and resolution it reads.
SURVEY = ("survey (shared DOM walk)",)
CAND = ("candidate setup and navigation", "candidate Tab traversal",
        "candidate visibility", "candidate pierced resolution")
FEAT = ("candidate feature evidence",)
SETS = ("candidate variant set operations",)


def totals(artifact: dict) -> tuple[Counter, int]:
    acc: Counter = Counter()
    for page in artifact["page_timings_ms"].values():
        acc.update(page)
    return acc, artifact["probes"]


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def main() -> None:
    cheap = json.loads(CHEAP.read_text())
    full = json.loads(FULL.read_text())
    truth = json.loads((ROOT / "fixtures/truth.json").read_text())
    labels = {p: r.get("labels_by_viewport", {}).get("desktop", r["label"])
              for p, r in truth["probes"].items()}
    universe = set(labels)
    positive = {p for p, label in labels.items() if label == "violation"}
    negative = universe - positive

    ct, n = totals(cheap)
    ft, fn_probes = totals(full)
    assert n == fn_probes == len(universe) == 95

    def ms(acc: Counter, *keys: str) -> float:
        return sum(acc[k] for k in keys) / n

    # --- rows carried straight from the artifacts ---------------------------
    cheap_scores = {s["detector"]: s for s in cheap["scores"]}
    full_scores = {s["detector"]: s for s in full["scores"]}

    def row(name: str, scores: dict, cost: float, note: str) -> list[str]:
        s = scores[name]
        return [name, str(s["tp"]), str(s["fp"]), str(s["fn"]),
                f'{s["unknown_positive"]}/{s["unknown_negative"]}',
                pct(s["precision"]), pct(s["recall"]), pct(s["f1"]),
                f"{cost:.1f}", note]

    ours, upstream, expensive, combos = [], [], [], []
    for name in cheap_scores:
        if name.startswith("U-"):
            key = name if name in ct else None
            cost = ms(ct, *CAND) + (ms(ct, key) if key else 0.0)
            upstream.append(row(name, cheap_scores, cost, "shared + method"))
        elif name.startswith(("D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8")):
            key = name if name in ct else ("D1 axe-core" if name.startswith("D1") else None)
            cost = ms(ct, *SURVEY) + (ms(ct, key) if key else 0.0)
            ours.append(row(name, cheap_scores, cost, "survey + method"))

    # Only four arms are separately timed; the rest are filters applied to one
    # of those runs, so they are priced at the arm that produced their input.
    ARM = {
        "D9 ": "D9 behavioural differential",
        "D9-noS4": "D9 behavioural differential",
        "D9+S4ours": "D9 behavioural differential",
        "D9+S4u": "D9+S4u differential with upstream Stage 4 (coverage-exact)",
        "D9u+S4u": "D9u upstream-style differential (8 channels, keys in sequence)",
        "D9u ": "D9u upstream-style differential (8 channels, keys in sequence)",
        "D10": "D10a coverage differential (Enter only, no baseline subtraction)",
    }
    for name in full_scores:
        if not name.startswith(("D9", "D10")):
            continue
        key = name if name in ft else next(
            (v for k, v in ARM.items() if name.startswith(k)), None)
        assert key in ft, name
        expensive.append(row(name, full_scores, ft[key] / n,
                             "measured" if name in ft else "priced at its arm"))

    base = ms(ct, *CAND) + ms(ct, *SETS)
    D4, D5, D6 = (ms(ct, f"U-D{x} upstream " + t) for x, t in
                  (("4", "CSS and class tokens"), ("5", "direct CDP listeners"),
                   ("6", "registration shim")))
    D2b = ms(ct, "U-D2b upstream mouse handler properties")
    D7 = ms(ct, "U-D7 upstream React mouse props")
    D8 = ms(ct, "U-D8 upstream pixel hover difference")
    feat = ms(ct, *FEAT)
    combo_cost = {
        "C1": base + D4 + D5 + D6, "C2": base + D4 + D5 + D6 + D8,
        "C3": base + D4 + D5 + D6 + feat, "C4": base + D4 + D5 + D6 + feat,
        "C5": base + D5 + D6 + D2b + D7 + feat, "C6": base + feat, "C7": base + feat,
        "C8": base + D4 + D5 + D6 + D2b + D7 + feat,
        "C9": base + D4 + D5 + D6 + D2b + D7 + feat,
    }
    for name, s in cheap_scores.items():
        stem = name.split(" ")[0]
        if stem in combo_cost:
            combos.append(row(name, cheap_scores, combo_cost[stem], "shared + components"))

    # --- C10-C16, rebuilt here from the saved probe observations ------------
    con = json.loads((OBS / "containment.json").read_text())
    comp = json.loads((OBS / "composite.json").read_text())
    eff = json.loads((OBS / "effect.json").read_text())
    eff2 = json.loads((OBS / "effect2.json").read_text())
    feats = {p: f for ev in cheap["candidate_evidence"].values()
             for p, f in ev["features"].items()}
    c9_name = next(k for k in cheap["reported"] if k.startswith("C9"))
    c9 = set(cheap["reported"][c9_name])
    unknown = set(cheap["unobservable"][c9_name])

    r1 = {p for p in c9 if con.get(p, {}).get("contains_focusable")
          or con.get(p, {}).get("inside_focusable")}
    r2 = {p for p in c9 if comp.get(p, {}).get("owner_role")
          and comp.get(p, {}).get("sibling_tabbable")
          and (comp.get(p, {}).get("own_tabindex") or "") == "-1"}
    r3 = {p for p in c9 if comp.get(p, {}).get("aria_keyshortcuts")
          or comp.get(p, {}).get("chord_in_text")}
    r5 = {p for p in c9 if eff.get(p, {}).get("own_activation") == []
          and not feats.get(p, {}).get("delegated_types")
          and not feats.get(p, {}).get("label_toggle")
          and eff.get(p, {}).get("hover_reveal") is False}
    c13 = c9 - r1 - r2 - r3 - r5
    r6 = {p for p in c13 if eff2.get(p, {}).get("name_twin")}
    r7 = {p for p in c13 if eff2.get(p, {}).get("framework")
          and eff2.get(p, {}).get("framework_activation") is False}
    r8 = {p for p in c13 if eff2.get(p, {}).get("click_effect") is False}
    r9 = {p for p in universe if eff2.get(p, {}).get("click_effect")
          and eff2.get(p, {}).get("key_effect")
          and eff2.get(p, {}).get("same_effect") is False}

    # Measured against a navigate-only baseline over the same 19 pages.
    R1_MS, R23_MS, R5_MS, R67_MS = 0.35, 0.57, 104.0, 0.0
    behavioural = sum(v["ms"] for v in eff2.values() if v.get("ms")) / n
    c9_cost = combo_cost["C9"]
    later = [
        ("C10 = C9 minus redundant click surfaces (R1)", c9 - r1, unknown,
         c9_cost + R1_MS, "+ R1"),
        ("C11 = C10 minus roving-tabindex items (R2)", c9 - r1 - r2, unknown,
         c9_cost + R1_MS + R23_MS, "+ R2"),
        ("C12 = C11 minus declared shortcuts (R3)", c9 - r1 - r2 - r3, unknown,
         c9_cost + R1_MS + R23_MS, "+ R3, same pass"),
        ("C13 = C12 minus leads with no action path (R5)", c9 - r1 - r2 - r3 - r5,
         unknown, c9_cost + R1_MS + R23_MS + R5_MS, "+ R5"),
        ("C14 = C13 minus name-twinned leads (R6)", c13 - r6, unknown,
         c9_cost + R1_MS + R23_MS + R5_MS + R67_MS, "+ R6, free"),
        ("C15 = C14 minus leads with no click effect (R7, R8)", c13 - r6 - r7 - r8,
         unknown, c9_cost + R1_MS + R23_MS + R5_MS + behavioural, "+ behavioural pass"),
        ("C16 = C15 plus divergent-key-effect promotions (R9)",
         (c13 - r6 - r7 - r8) | r9, unknown - r9,
         c9_cost + R1_MS + R23_MS + R5_MS + behavioural, "+ R9, same pass"),
    ]
    for name, reported, unk, cost, note in later:
        reported = reported - unk
        tp, fp = len(reported & positive), len(reported & negative)
        miss = len(positive - reported - unk)
        p = tp / (tp + fp) if tp + fp else None
        r = tp / len(positive)
        f1 = 2 * p * r / (p + r) if p and r else None
        combos.append([name, str(tp), str(fp), str(miss),
                       f"{len(unk & positive)}/{len(unk & negative)}",
                       pct(p), pct(r), pct(f1), f"{cost:.1f}", note])

    head = ("| method | TP | FP | FN | unknown pos/neg | precision | strict recall "
            "| F1 | ms/target | ms covers |")
    rule = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"

    def table(rows: list[list[str]]) -> str:
        # C1's name contains "D4|D5|D6"; a bare pipe would split the row.
        body = ["| " + " | ".join(c.replace("|", r"\|") for c in r) + " |" for r in rows]
        return "\n".join([head, rule] + body)

    run = cheap["run"]
    body = f"""# Every detector and rule — scores and speed

Generated by `experiments/tabbing/results_matrix.py` from the published
artifacts. Do not edit. Interpretation lives in [REPORT.md](../REPORT.md),
[CHEAP_DETECTOR_REVIEW.md](../CHEAP_DETECTOR_REVIEW.md) and
[PROBES.md](../PROBES.md).

## What the columns mean

**Strict recall** divides true positives by all {len(positive)} labelled defects, so an
undecided defect counts against the detector. `unknown pos/neg` is how many
positives and negatives the detector declined to judge. **Precision** divides
true positives by everything flagged.

**ms/target** is measured browser work divided by the {n} targets in the corpus.
It amortises per-page setup, so it is a throughput figure and not a promise
about any single button. The last column says what the figure includes: a bare
method call is meaningless without the shared work it reads, so that is added
in. C15 and C16 are the rows where amortising hides the most — they run a
behavioural pass on only 42 of 95 targets, at a median of 442 ms and a maximum
of 1580 ms each, while the other 53 cost nothing.

## Run

| field | value |
|---|---|
| corpus | `fixtures` ({n} targets, {len(positive)} defects) |
| corpus sha256 | `{run["corpus_sha256"][:32]}…` |
| chromium | {run["versions"]["chromium"]} |
| playwright | {run["versions"]["playwright"]} |
| python | {run["versions"]["python"]} |
| viewport | {run["settings"]["viewport"]["width"]}x{run["settings"]["viewport"]["height"]} |

## Our ports of the twelve families

{table(ours)}

## Upstream's generators, transcribed

{table(upstream)}

## Combination rules

C1–C9 are scored in the artifact. C10–C16 are rebuilt here from the saved probe
observations in [probes/](../probes/), the same way `score_new.py` and
`score_new2.py` rebuild them, without importing detector or scoring code.

{table(combos)}

## The behavioural and coverage arms

These are the oracles the cheap rules exist to avoid running on every target.

{table(expensive)}

## Reading this table honestly

The C10–C16 rules were written after reading C9's error table on this corpus,
with the labels visible. They are development results, not measured accuracy,
and R2, R3, R6 and R7 each fire on exactly one probe. C16's 100% precision in
particular should never be quoted as an accuracy figure. The rules are
predeclared in `LLMTalk` so a fresh corpus can measure rather than confirm
them; the first contact with new pages already found a gap, in R2.

D1's local axe engine is 4.10.2 against upstream's locked 4.11.1, and the
harness differs from upstream in Tab traversal, state isolation, method
ordering and failure handling. See
[UPSTREAM_PARITY_REVIEW.md](../UPSTREAM_PARITY_REVIEW.md) before describing any
row here as an exact replication.
"""
    OUT.write_text(body)
    print(f"wrote {OUT} ({len(ours)} ours, {len(upstream)} upstream, "
          f"{len(combos)} combination, {len(expensive)} oracle rows)")


if __name__ == "__main__":
    main()
