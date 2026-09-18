"""Assemble the cross-environment detector matrix from the bakeoff outputs.

One row per detector per environment, carrying every column
`CHEAP_DETECTOR_REVIEW.md` and `results/detector-matrix.results.md` carry:
TP, FP, FN, **unknown positives and unknown negatives separately**, precision,
**strict** recall, F1, **ms per button and ms per target**, and an `ms covers`
note saying what the figure includes and whether it was measured on that row or
priced at the arm that produced it.

Two units, both kept. `ms/button` divides measured browser work by the probes
the detector actually decided: the unit the 300 ms cap is stated in, the cost of
deciding one button. `ms/target` divides the same work by every target in the
corpus: the throughput figure the published tables quote. Neither is a
substitute for the other, so neither replaces the other here.

Nothing is left blank. A cell that cannot be measured carries a reason string.

Reads only what the bakeoff and the probe scorers wrote. Recomputing from the
raw artifacts is the point: a summary checked against itself proves nothing.

Usage:
    uv run --offline --no-sync python -m tools.assemble_matrix [--label closed]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[4]
HERE = pathlib.Path(__file__).resolve().parent.parent
OUT = HERE / "derived" / "matrix.json"
MARKDOWN = HERE / "MATRIX-RESULTS.md"

CAP_MS = 300

CORPORA = {
    "gds": (
        HERE / "artifacts" / "gds-corpus" / "results",
        "GDS Accessibility Tool Audit (MIT, Crown Copyright 2017); 6 IAF cases + 2 controls",
        "all 13 audited tools score 0/6",
    ),
    "fixtures": (
        REPO / "experiments" / "tabbing" / "fixtures" / "results",
        "blind-authored synthetic; 95 probes, 39 defects",
        "none; the suite's own baseline",
    ),
    "ma11y": (
        HERE / "artifacts" / "ma11y" / "results",
        "Ma11y-generated mutants; 1 verified fault, 6 controls",
        "no published reference; ground truth by construction",
    ),
    "edgecases": (
        REPO / "experiments" / "tabbing" / "edgecases" / "results",
        "shared-author development corpus; NO unbiased accuracy claim",
        "none; shared-author, so no unbiased accuracy claim",
    ),
}

# --- what each row's cost is composed of ------------------------------------
#
# A bare method call is meaningless without the shared work it reads, so the
# shared work is added in. These are the compositions `results_matrix.py` used
# to produce the published table, transcribed so the two agree by construction.
SURVEY = ("survey (shared DOM walk)",)
CAND = (
    "candidate setup and navigation",
    "candidate Tab traversal",
    "candidate visibility",
    "candidate pierced resolution",
)
FEAT = ("candidate feature evidence",)
SETS = ("candidate variant set operations",)

OURS_PREFIXES = ("D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8")

U_D2b = "U-D2b upstream mouse handler properties"
U_D4 = "U-D4 upstream CSS and class tokens"
U_D5 = "U-D5 upstream direct CDP listeners"
U_D6 = "U-D6 upstream registration shim"
U_D7 = "U-D7 upstream React mouse props"
U_D8 = "U-D8 upstream pixel hover difference"

# C1-C9 are unions of the upstream generators; a combination costs what its
# inputs cost, since they share one candidate pass.
COMBO_PARTS = {
    "C1": (U_D4, U_D5, U_D6),
    "C2": (U_D4, U_D5, U_D6, U_D8),
    "C3": (U_D4, U_D5, U_D6, *FEAT),
    "C4": (U_D4, U_D5, U_D6, *FEAT),
    "C5": (U_D5, U_D6, U_D2b, U_D7, *FEAT),
    "C6": FEAT,
    "C7": FEAT,
    "C8": (U_D4, U_D5, U_D6, U_D2b, U_D7, *FEAT),
    "C9": (U_D4, U_D5, U_D6, U_D2b, U_D7, *FEAT),
}

# Only four arms are separately timed. The rest are re-scorings of one of those
# runs -- a different filter over the same measured trial -- so they are priced
# at the arm that produced their input rather than left blank. Transcribed from
# the `ms covers` column of `results/detector-matrix.results.md`.
ARM = {
    "D9 ": "D9 behavioural differential",
    "D9-noS4": "D9 behavioural differential",
    "D9+S4ours": "D9 behavioural differential",
    "D9+S4u": "D9+S4u differential with upstream Stage 4 (coverage-exact)",
    "D9u+S4u": "D9u upstream-style differential (8 channels, keys in sequence)",
    "D9u ": "D9u upstream-style differential (8 channels, keys in sequence)",
    "D10": "D10a coverage differential (Enter only, no baseline subtraction)",
}

# D1 and D1x are two scorings of one axe-core measurement.
TIMING_ALIASES = {
    "D1 axe-core (keyboard rules)": "D1 axe-core",
    "D1x axe-core (any rule, unsound)": "D1 axe-core",
}


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def num(value: float | None, reason: str) -> str:
    return reason if value is None else f"{value:.1f}"


def totals(payload: dict) -> dict[str, float]:
    acc: dict[str, float] = {}
    for page in (payload.get("page_timings_ms") or {}).values():
        for name, ms in page.items():
            acc[name] = acc.get(name, 0.0) + ms
    return acc


def cost_of(name: str, timings: dict[str, float]) -> tuple[float | None, str, str | None]:
    """Total measured ms for one row, what it covers, and why if it is missing."""
    stem = name.split(" ")[0]

    def have(*keys: str) -> float | None:
        missing = [k for k in keys if k not in timings]
        if missing:
            return None
        return sum(timings[k] for k in keys)

    if name.startswith("U-"):
        # An upstream generator with no key of its own read the shared candidate
        # pass and did nothing else measurable; the published table charges it
        # the shared cost alone, and that convention is kept here so the two
        # tables agree.
        own = timings.get(name)
        base = have(*CAND)
        if base is None:
            return None, "shared + method", "not measured: no candidate-pass timing in this run"
        return base + (own or 0.0), "shared + method", None

    if stem in COMBO_PARTS:
        base = have(*CAND, *SETS)
        parts = have(*COMBO_PARTS[stem])
        if base is None or parts is None:
            return None, "shared + components", "not measured: component timings absent"
        return base + parts, "shared + components", None

    if name.startswith(("D9", "D10")):
        if name in timings:
            return timings[name], "measured", None
        arm = next((v for k, v in ARM.items() if name.startswith(k)), None)
        if arm and arm in timings:
            return timings[arm], "priced at its arm", None
        return None, "priced at its arm", "not measured: its arm did not run in this corpus"

    if name.startswith(OURS_PREFIXES):
        key = TIMING_ALIASES.get(name, name)
        own = timings.get(key)
        base = have(*SURVEY)
        if base is None:
            return None, "survey + method", "not measured: no survey timing in this run"
        if own is None:
            return None, "survey + method", "not measured: no timing key for this detector"
        return base + own, "survey + method", None

    return None, "unknown composition", "not measured: unrecognised detector name"


def load_corpus(results_dir: pathlib.Path, corpus: str, label: str) -> tuple[dict, dict, list[str]]:
    """The two files of one named run. No glob: a stale run must not clobber."""
    wanted = [
        (results_dir / f"bakeoff-{corpus}-{label}.json", "cheap"),
        (results_dir / f"bakeoff-{corpus}-{label}-full.json", "full"),
    ]
    rows: dict[str, dict] = {}
    notes: list[str] = []
    meta: dict = {}
    for path, kind in wanted:
        if not path.exists():
            notes.append(f"{path.name} absent")
            continue
        payload = json.loads(path.read_text())
        timings = totals(payload)
        meta.setdefault("probes", payload.get("probes") or 0)
        meta.setdefault("corpus_caveat", payload.get("caveat"))
        meta.setdefault("artifacts", []).append(path.name)
        meta.setdefault("pages_timed", {})[path.name] = len(payload.get("page_timings_ms") or {})
        if not payload.get("scores"):
            notes.append(f"{path.name} produced no scores")
        for row in payload.get("scores") or []:
            name = row.get("detector")
            if not name:
                continue
            if name in rows:
                # Both files score the cheap tier. They must agree; if they do
                # not, that is a finding, not something to silently resolve.
                previous = rows[name]
                same = all(previous[k] == row.get(k) for k in ("tp", "fp", "fn", "unknown"))
                if not same:
                    notes.append(
                        f"{name}: {previous['source']} and {path.name} disagree "
                        f"({previous['tp']}/{previous['fp']}/{previous['fn']} vs "
                        f"{row.get('tp')}/{row.get('fp')}/{row.get('fn')})"
                    )
                continue
            total, covers, reason = cost_of(name, timings)
            decided = row.get("decided") or 0
            probes = payload.get("probes") or 0
            # A detector that decided nothing has a measured cost but no
            # per-button cost: the denominator is zero, not small. Say that
            # rather than leave the cell empty; the per-target figure still
            # holds and is reported beside it.
            button_reason = reason
            if reason is None and total is not None and not decided:
                button_reason = f"n/a: decided 0 of {probes}"
            rows[name] = {
                "tp": row.get("tp"),
                "fp": row.get("fp"),
                "fn": row.get("fn"),
                "tn": row.get("tn"),
                "unknown": row.get("unknown"),
                "unknown_positive": row.get("unknown_positive"),
                "unknown_negative": row.get("unknown_negative"),
                "precision": row.get("precision"),
                # `recall` is strict: TP over every labelled defect, undecided
                # ones included. `recall_conditional` divides by decided defects
                # only. The published tables quote the strict one, so it is the
                # one carried here, under its real name.
                "recall_strict": row.get("recall"),
                "recall_conditional": row.get("recall_conditional"),
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
                "ms_covers": covers,
                "ms_reason": reason,
                "ms_button_reason": button_reason,
                "source": path.name,
                "kind": kind,
            }
    return rows, meta, notes


def merge_probe_rules(rows: dict[str, dict], corpus: str, notes: list[str]) -> None:
    """Fold C10-C16 in from `run_probe_rules.py`, priced on top of C9.

    A corpus may be scored under more than one behavioural lead set -- R9 can
    only promote what was actually observed, so C16's published 100% precision
    is a property of the 42-probe set it looked at, not of the rule. Where two
    lead sets disagree about a row, both rows are emitted and labelled with the
    set observed. Where they agree, one row is emitted; suffixing identical
    numbers would imply a difference that is not there.
    """
    scored = sorted((HERE / "derived" / "probe-rules").glob(f"{corpus}-*.json"))
    if not scored:
        notes.append("C10–C16 absent: no probe-rule scoring on disk for this corpus")
        return
    payloads = [json.loads(p.read_text()) for p in scored]
    c9 = next((r for n, r in rows.items() if n.startswith("C9")), None)

    names = [n for n in payloads[0]["rows"]]
    for name in names:
        variants = [(p, p["rows"][name]) for p in payloads if name in p["rows"]]
        keys = {(v["tp"], v["fp"], v["fn"], v["unknown"]) for _, v in variants}
        split = len(keys) > 1
        for payload, row in variants:
            lead_set = payload.get("lead_set_observed") or "unrecorded"
            observed = payload.get("probes_observed")
            targets = payload.get("targets") or 0
            key = name
            if split:
                seen = f"{observed} of {targets}" if observed is not None else lead_set
                key = f"{name} [observed {seen}: {lead_set}]"
            added = row.get("ms_per_target_added")
            if c9 is None or c9.get("ms_total") is None:
                total, reason = None, "not measured: C9's own cost is unmeasured here"
            elif added is None:
                total, reason = None, "not measured: probe observation timings not recorded"
            else:
                total, reason = c9["ms_total"] + added * targets, None
            decided = row.get("decided") or 0
            rows[key] = {
                "tp": row["tp"], "fp": row["fp"], "fn": row["fn"], "tn": None,
                "unknown": row["unknown"],
                "unknown_positive": row["unknown_positive"],
                "unknown_negative": row["unknown_negative"],
                "precision": row["precision"],
                "recall_strict": row["recall"],
                "recall_conditional": None,
                "f1": row["f1"],
                "decided": decided,
                "probes": targets,
                "ms_total": None if total is None else round(total, 1),
                "ms_per_button": (
                    None if not total or not decided else round(total / decided, 1)
                ),
                "ms_per_target": (
                    None if not total or not targets else round(total / targets, 1)
                ),
                "ms_covers": f"C9 {row['ms_covers']}",
                "ms_reason": reason,
                "source": scored[payloads.index(payload)].name,
                "kind": "probe-rules",
                "lead_set_observed": lead_set,
                "probes_observed": observed,
            }


def order_key(name: str) -> tuple:
    """Group the table the way the published one does, not alphabetically."""
    stem = name.split(" ")[0]
    if name.startswith("U-"):
        group = 1
    elif stem.startswith("C"):
        group = 2
    elif name.startswith(("D9", "D10")):
        group = 3
    else:
        group = 0
    # Only the family number, not every digit in the name: "D9+S4ours" is D9,
    # not D94, and must sort before D10 rather than after it.
    match = re.match(r"^[A-Za-z-]*(\d+)", stem)
    return (group, int(match.group(1)) if match else 0, stem, name)


def table(rows: dict[str, dict], names: list[str]) -> str:
    head = ("| detector | TP | FP | FN | unk pos | unk neg | precision | strict recall "
            "| F1 | ms/button | ms/target | ms covers |")
    rule = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
    body = []
    for name in names:
        r = rows[name]
        reason = r.get("ms_reason") or "—"
        button_reason = r.get("ms_button_reason") or reason
        cells = [
            name,
            str(r["tp"]), str(r["fp"]), str(r["fn"]),
            str(r["unknown_positive"]), str(r["unknown_negative"]),
            pct(r["precision"]), pct(r["recall_strict"]), pct(r["f1"]),
            num(r["ms_per_button"], button_reason), num(r["ms_per_target"], reason),
            r["ms_covers"],
        ]
        # C1's own name contains "D4|D5|D6"; a bare pipe would split the row.
        body.append("| " + " | ".join(c.replace("|", r"\|") for c in cells) + " |")
    return "\n".join([head, rule] + body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="closed",
                        help="the bakeoff --label whose run to assemble")
    args = parser.parse_args()

    matrix: dict[str, dict[str, dict]] = {}
    meta: dict[str, dict] = {}

    for corpus, (results_dir, caveat, reference) in CORPORA.items():
        if not results_dir.exists():
            meta[corpus] = {"status": "not run yet", "caveat": caveat}
            matrix[corpus] = {}
            continue
        rows, info, notes = load_corpus(results_dir, corpus, args.label)
        merge_probe_rules(rows, corpus, notes)
        matrix[corpus] = rows
        meta[corpus] = {
            "status": f"{len(rows)} detectors",
            "caveat": caveat,
            "reference": reference,
            "notes": notes,
            **info,
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"label": args.label, "meta": meta, "matrix": matrix},
                              indent=2) + "\n")

    blanks = [
        (corpus, name, column)
        for corpus, rows in matrix.items()
        for name, r in rows.items()
        for column, value, why in (
            ("ms/button", r["ms_per_button"], r.get("ms_button_reason") or r.get("ms_reason")),
            ("ms/target", r["ms_per_target"], r.get("ms_reason")),
        )
        if value is None and not why
    ]

    for corpus, info in meta.items():
        print(f"{corpus:<12}{info['status']:<18}{info.get('caveat', '')[:52]}")
        for note in info.get("notes", []):
            print(f"{'':<12}note: {note}")
    print()
    print(f"unexplained blank cells: {len(blanks)}")
    for corpus, name, column in blanks:
        print(f"  {corpus} / {name} / {column}")

    write_markdown(matrix, meta, args.label)
    print(f"\nwrote {OUT}\nwrote {MARKDOWN}")
    return 1 if blanks else 0


def headline(matrix: dict) -> str:
    """The GDS environment: the only corpus here with a published competitor result.

    Built from the data rather than transcribed, because the cost model changed
    and a hand-carried number would now be a stale one.
    """
    rows = matrix.get("gds") or {}
    hits = [(n, r) for n, r in rows.items() if (r["tp"] or 0) > 0]
    hits.sort(key=lambda pair: (pair[1]["ms_per_button"] is None,
                                pair[1]["ms_per_button"] or 0.0))
    if not hits:
        return ("No detector scores a true positive on the GDS corpus in this run.\n")
    body = ["| detector | TP | FP | abst. | precision | ms/button |",
            "|---|---:|---:|---:|---:|---:|"]
    for name, r in hits:
        body.append(
            f"| {name.replace('|', chr(92) + '|')} | {r['tp']} | {r['fp']} | "
            f"{r['unknown']} | {pct(r['precision'])} | "
            f"{num(r['ms_per_button'], r.get('ms_reason') or '—')} |"
        )
    best = max(r["tp"] for _, r in hits)
    cheap = [n for n, r in hits
             if r["tp"] == best and (r["ms_per_button"] or 1e9) <= CAP_MS]
    defects = next((r["tp"] + r["fn"] + r["unknown_positive"] for _, r in hits), 0)
    return "\n".join(body) + (
        f"\n\n{len(cheap)} detectors find **{best} of {defects} under the "
        f"{CAP_MS} ms/button cap**, at zero false positives where precision reads "
        "100%. Against a published 0/6 for all 13 tools GDS audited, that is a "
        f"real gain — and **{best}/{defects} is not {defects}/{defects}**. The "
        "cases nobody in the suite finds are still missed.\n"
    )


def abstention_finding(matrix: dict) -> str:
    """C8/C9 abstaining on GDS on exactly the cases their own inputs find."""
    rows = matrix.get("gds") or {}
    inputs = ["D4 CSS + lexical", "D5 CDP getEventListeners", "D6 addEventListener shim"]
    unions = [n for n in rows if n.startswith(("C8", "C9"))]
    if not unions or not all(n in rows for n in inputs):
        return ""
    found = {n: rows[n]["tp"] for n in inputs}
    union = {n: (rows[n]["tp"], rows[n]["unknown"]) for n in unions}
    if not all(v > 0 for v in found.values()) or any(tp > 0 for tp, _ in union.values()):
        return ""
    lines = ", ".join(f"{n.split(' ')[0]} finds {v}" for n, v in found.items())
    detail = "; ".join(f"{n.split(' ')[0]} returns {tp} TP with {unk} abstentions"
                       for n, (tp, unk) in union.items())
    return (
        "## The finding that costs the suite its best number\n\n"
        f"**C8/C9 abstain on GDS on exactly the cases their own inputs find.** {lines}; "
        f"{detail}. The union's filter stages (`inert`, `pointer-events:none`, "
        "blocked-centre) cannot resolve those elements on a real page, so a safety "
        "filter suppresses true positives its own components had already found. The "
        "cheap rules the combinations were built to improve on beat them here.\n"
    )


def write_markdown(matrix: dict, meta: dict, label: str) -> None:
    sections = []
    for corpus, rows in matrix.items():
        if not rows:
            reason = "; ".join(meta[corpus].get("notes") or ["no run on disk"])
            sections.append(f"### {corpus}\n\nNo rows: {reason}.\n")
            continue
        names = sorted(rows, key=order_key)
        info = meta[corpus]
        head = (f"### {corpus} — {info['caveat']}\n\n"
                f"Published reference: {info.get('reference') or 'none'}. "
                f"{info.get('probes', 0)} targets; "
                f"artifacts: {', '.join(info.get('artifacts', []))}.\n")
        notes = info.get("notes") or []
        if notes:
            head += "\n" + "\n".join(f"- Note: {n}" for n in notes) + "\n"
        sections.append(head + "\n" + table(rows, names) + "\n")

    timed = []
    for corpus, rows in matrix.items():
        if not rows:
            continue
        have = [r for r in rows.values() if r["ms_per_button"] is not None]
        under = [r for r in have if r["ms_per_button"] <= CAP_MS]
        timed.append(f"| {corpus} | {len(have)} | {len(under)} | "
                     f"{len(rows) - len(have)} |")

    body = f"""# The full detector matrix across four environments

Every detector in the suite, run by `experiments/tabbing/runner/bakeoff.py` — the
real harness, importing the frozen detectors from
`src/audit/analyzer/keyboard/kbdiff/`. Nothing here is a reimplementation.
C10–C16 are not in `bakeoff.py`; they are scored from each corpus's own saved
probe observations by `tools/run_probe_rules.py`, which states the same rules
`probes/score_new.py` and `probes/score_new2.py` state.

Assembled by `tools/assemble_matrix.py` from the `{label}` run. **No cell is
blank.** A cost that could not be measured carries the reason in place of a
number.

## What each column means

- **unk pos / unk neg** — abstentions, split. A probe the detector declined to
  decide, never scored as a negative, separated into labelled defects and
  labelled negatives. Reporting a budget limit as "no violation found" is the
  failure mode these columns exist to prevent.
- **strict recall** — true positives over **all** labelled defects, undecided
  ones included, so an abstention on a defect counts against the detector. This
  is `bakeoff.py`'s `recall`; its `recall_conditional`, which divides by decided
  defects only, is kept in `derived/matrix.json` but is not what the published
  tables quote and is not shown here.
- **ms/button** — measured browser work divided by the probes the detector
  **decided**. This is the unit the 300 ms cap is stated in: the cost of
  deciding one button.
- **ms/target** — the same work divided by **every** target in the corpus. It
  amortises per-page setup, so it is a throughput figure, not a promise about
  any single button. This is the column `detector-matrix.results.md` and
  `CHEAP_DETECTOR_REVIEW.md` quote. Both are kept because they answer different
  questions; neither replaces the other.
- **ms covers** — what the figure includes. A bare method call is meaningless
  without the shared work it reads, so that is added in. `measured` means the
  row has its own timing; `priced at its arm` means the row is a re-scoring of
  another arm's single measured trial, so it costs what that arm cost.
- **precision `—`** means the detector flagged nothing at all, so precision is
  undefined rather than missing; **F1 `—` follows from it** and is likewise
  correct, not a gap. Both are reported as `—` deliberately.

## Environments

| corpus | what it is | published reference |
|---|---|---|
| **fixtures** | blind-authored synthetic, 95 probes / 39 defects | none; the suite's own baseline |
| **edgecases** | shared-author development corpus | none; **no unbiased accuracy claim** |
| **gds** | GDS Accessibility Tool Audit (MIT, Crown Copyright 2017), 6 IAF cases + 2 controls | **all 13 audited tools score 0/6** |
| **ma11y** | Ma11y-generated mutants of the GDS page, ground truth by construction *and* verified behaviourally | none |

## Headline: the GDS environment

The GDS corpus is the only one here with a published competitor result, and it
is a hard one: **every one of the 13 tools GDS audited scores 0 of 6.**

{headline(matrix)}
{abstention_finding(matrix)}
## Full matrix

{chr(10).join(sections)}
## Cost against the 300 ms/button cap

| corpus | detectors timed | at or under 300 ms/button | not timed (reason given in the row) |
|---|---:|---:|---:|
{chr(10).join(timed)}

## Corrections carried into this document

1. **C16's published 100% precision is a property of the lead set that was
   observed, not of the rule.** The saved `effect2.json` observed 42 of 95
   probes — the C12 lead set. R9 promotes from the whole universe but can only
   promote what it looked at. Both scopes are scored here and, where they
   disagree, both rows appear, each labelled with the set observed.

2. **The harness capped the tab walk at 300 presses on a 306-element page.**
   `bakeoff.py` called `compute_tab_order()` with the frozen default, so 5 of 6
   GDS violations came back `unknown` — a budget limit reported as absence of
   evidence. The cap is now derived per page; the frozen detector's own default
   is untouched, and fixtures reproduces its published numbers unchanged.

3. **Ma11y yields one verified fault, not four.** F59 does not exist in Ma11y
   (404). F54 is inapplicable to the GDS page, which has zero inline `onclick`
   attributes — the exact attribute Ma11y's own `applicable()` requires. F42's
   generated span never fires on a trusted click, so it is not an IAF and was
   **excluded rather than labelled**, since a violation nobody can detect
   penalises every detector for missing a fault that is not there.

4. **The ma11y arm is a sanity check, not a benchmark.** One violation and six
   controls cannot support a precision/recall comparison, and its rows should be
   read as "does this detector fire on a known-good fault" only.

5. **edgecases is a shared-author corpus.** Its rows are included for
   completeness and carry **no unbiased accuracy claim**.

6. **The edgecases CDP failure is fixed, and it was not the page the log
   suggested.** `DOM.getDocument` with `depth: -1, pierce: true` returned a
   response Chromium's CBOR encoder could not serialise. The cause is
   `pages/scale.html`, nested 154 elements deep with only 284 elements in it:
   `depth: 148` encodes in 73 KB and `depth: 150` fails, so it is a nesting
   limit and not a size limit. `runner/upstream_candidates.py` now keeps the
   unbounded call as its primary path and falls back to fetching the tree in
   bounded slices only when that call raises, so every corpus that already
   worked is unaffected.

7. **A stale-artifact merge, not a measurement failure, blanked most of the
   earlier `ms` column.** The previous assembler globbed every `bakeoff-*.json`
   in a results directory and let later names overwrite earlier ones; `-` sorts
   before `.`, so `bakeoff-fixtures.json` — an old run carrying no
   `page_timings_ms` at all — sorted last and overwrote every row it contained.
   That is where the earlier table's `D10 coverage differential` row, its
   duplicate `D9-noS4` row and its 22/19/15 `D6` came from. This assembler reads
   exactly the two files of one named run.

## Reproducing

```
uv run --offline --no-sync python -m tools.build_gds_corpus
uv run --offline --no-sync python -m tools.build_ma11y_corpus
uv run --offline --no-sync python -m tools.verify_ma11y_corpus
bash tools/run_matrix_closed.sh
bash tools/run_probes_all.sh
uv run --offline --no-sync python -m tools.assemble_matrix --label {label}
```
"""
    MARKDOWN.write_text(body)


if __name__ == "__main__":
    raise SystemExit(main())
