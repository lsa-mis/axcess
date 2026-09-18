"""The controls for the gap-closure work, run against the artifacts, not the prose.

Four checks, each one the control a task is allowed to claim:

1. **fixtures vs `results/detector-matrix.results.md`** — every row the published
   table carries must reproduce, cell for cell, from the re-run matrix.
2. **fixtures vs `CHEAP_DETECTOR_REVIEW.md`** — the same for the rule table,
   including C10-C16 and the `Unknown defects / negatives` split.
3. **D9 and D9+S4u keep their own measured ms**, and the seven re-scored
   variants are priced at their arm rather than left blank.
4. **No cell in `MATRIX-RESULTS.md` is blank without a reason string**, and an
   F1 of `—` occurs only where precision is `—`.

Percentages are compared on the underlying fraction to a tenth of a point: the
two published documents already disagree by one ulp on C3/C4 (82.0% against
82.1% for 32/39), which is a rounding artifact and not a measurement difference.

    uv run --offline --no-sync python -m tools.check_controls
"""

from __future__ import annotations

import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[4]
HERE = pathlib.Path(__file__).resolve().parent.parent
MATRIX = HERE / "derived" / "matrix.json"
PUBLISHED = REPO / "experiments" / "tabbing" / "results" / "detector-matrix.results.md"
REVIEW = REPO / "experiments" / "tabbing" / "CHEAP_DETECTOR_REVIEW.md"
GENERATED = HERE / "MATRIX-RESULTS.md"

TOLERANCE = 0.11  # percentage points


def cells(line: str) -> list[str]:
    guard = line.replace(r"\|", "\x00")
    return [c.strip().replace("\x00", "|") for c in guard.strip().strip("|").split("|")]


def as_pct(text: str) -> float | None:
    text = text.strip().replace("**", "")
    if text in {"—", "-", ""}:
        return None
    return float(text.rstrip("%"))


def close(got: float | None, want: float | None) -> bool:
    if got is None or want is None:
        return got is None and want is None
    return abs(got - want) <= TOLERANCE


def published_rows() -> dict[str, list[str]]:
    rows = {}
    for line in PUBLISHED.read_text().splitlines():
        if not line.startswith("| ") or line.startswith("|---"):
            continue
        c = cells(line)
        if len(c) != 10 or c[0] in {"method", "field"}:
            continue
        rows[c[0]] = c
    return rows


def review_rows() -> dict[str, list[str]]:
    rows = {}
    for line in REVIEW.read_text().splitlines():
        if not line.startswith("| C") or "|---" in line:
            continue
        c = cells(line)
        if len(c) != 9:
            continue
        stem = c[0].split(":")[0].strip()
        rows[stem] = c
    return rows


def failures_for(name: str, row: dict, want_tp: str, want_fp: str, want_fn: str,
                 want_unk: str, want_p: str, want_r: str, want_f1: str) -> list[str]:
    out = []
    # `CHEAP_DETECTOR_REVIEW.md` bolds its headline cells: `**4**`, `**90.2%**`.
    def plain(text: str) -> str:
        return text.replace("**", "").strip()

    for field, got, want in (("TP", row["tp"], int(plain(want_tp))),
                             ("FP", row["fp"], int(plain(want_fp))),
                             ("FN", row["fn"], int(plain(want_fn)))):
        if got != want:
            out.append(f"{name}: {field} {got} != published {want}")
    up, un = (x.strip() for x in plain(want_unk).replace("/", " ").split())
    if str(row["unknown_positive"]) != up or str(row["unknown_negative"]) != un:
        out.append(f"{name}: unknown pos/neg {row['unknown_positive']}/"
                   f"{row['unknown_negative']} != published {up}/{un}")
    for field, got, want in (("precision", row["precision"], as_pct(want_p)),
                             ("strict recall", row["recall_strict"], as_pct(want_r)),
                             ("F1", row["f1"], as_pct(want_f1))):
        got_pct = None if got is None else got * 100
        if not close(got_pct, want):
            out.append(f"{name}: {field} "
                       f"{'—' if got_pct is None else f'{got_pct:.1f}%'} "
                       f"!= published {'—' if want is None else f'{want:.1f}%'}")
    return out


def main() -> int:
    data = json.loads(MATRIX.read_text())
    fixtures = data["matrix"]["fixtures"]
    problems: dict[str, list[str]] = {}

    # --- control 1: the published detector matrix ---------------------------
    fails, checked, absent = [], 0, []
    for name, c in published_rows().items():
        row = fixtures.get(name)
        if row is None:
            # C16 may be split by lead set; match the published (filtered) one.
            row = next((r for k, r in fixtures.items()
                        if k.startswith(name) and "c12" in k), None)
        if row is None:
            absent.append(name)
            continue
        checked += 1
        fails += failures_for(name, row, c[1], c[2], c[3], c[4], c[5], c[6], c[7])
    if absent:
        fails.append(f"rows absent from the re-run: {absent}")
    problems["1. fixtures vs detector-matrix.results.md"] = fails
    print(f"control 1: {checked} published rows checked, {len(fails)} problems")

    # --- control 2: the cheap detector review -------------------------------
    fails, checked = [], 0
    by_stem = {}
    for name, row in fixtures.items():
        stem = name.split(" ")[0]
        if stem.startswith("C") and stem[1:].isdigit():
            # Prefer the published lead set where a row is split.
            if stem not in by_stem or "c12" in row.get("source", ""):
                by_stem[stem] = (name, row)
    for stem, c in review_rows().items():
        if stem not in by_stem:
            fails.append(f"{stem}: absent from the re-run")
            continue
        name, row = by_stem[stem]
        checked += 1
        fails += failures_for(stem, row, c[1], c[2], c[3], c[4], c[5], c[6], c[7])
    problems["2. fixtures vs CHEAP_DETECTOR_REVIEW.md"] = fails
    print(f"control 2: {checked} review rows checked, {len(fails)} problems")

    # --- control 3: Gap A's own control -------------------------------------
    fails = []
    measured = ["D9 behavioural differential",
                "D9+S4u differential with upstream Stage 4 (coverage-exact)"]
    variants = ["D9-noS4", "D9+S4ours", "D9u+S4u", "D10b ", "D10a+base", "D10a-u", "D10b-u"]
    for corpus, rows in data["matrix"].items():
        for name in measured:
            row = rows.get(name)
            if row is None:
                continue
            if row["ms_covers"] != "measured":
                fails.append(f"{corpus}/{name}: ms covers is {row['ms_covers']!r}, "
                             "not its own measurement")
            if row["ms_per_button"] is None:
                fails.append(f"{corpus}/{name}: lost its measured ms")
        for prefix in variants:
            hits = [(n, r) for n, r in rows.items() if n.startswith(prefix.strip())
                    and n not in measured]
            for n, r in hits:
                why = r.get("ms_button_reason") or r.get("ms_reason")
                if r["ms_per_button"] is None and not why:
                    fails.append(f"{corpus}/{n}: still blank with no reason")
                if r["ms_per_target"] is None and not r.get("ms_reason"):
                    fails.append(f"{corpus}/{n}: ms/target blank with no reason")
    problems["3. measured arms keep their own ms; variants priced at their arm"] = fails
    print(f"control 3: {len(fails)} problems")

    # --- control 4: no unexplained blank in the generated table --------------
    fails = []
    # A cell is acceptable if it is a number, an em dash, or one of the reason
    # strings the brief allows in place of a number.
    reason_like = re.compile(
        r"^(—|\d|n/a|not applicable|abstained|not measured|measurement failed)"
    )
    for line in GENERATED.read_text().splitlines():
        if not line.startswith("| ") or line.startswith("|---") or "| TP |" in line:
            continue
        c = cells(line)
        if len(c) != 12:
            continue
        name = c[0]
        for index, column in ((9, "ms/button"), (10, "ms/target")):
            if not c[index] or not reason_like.match(c[index]):
                fails.append(f"{name}: {column} is {c[index]!r}")
        precision_undefined = c[6] == "—"
        f1_undefined = c[8] == "—"
        if f1_undefined and not precision_undefined and as_pct(c[7]) not in (0.0, None):
            fails.append(f"{name}: F1 is — but precision is {c[6]} and recall {c[7]}")
        for index, column in ((1, "TP"), (2, "FP"), (3, "FN"),
                              (4, "unk pos"), (5, "unk neg")):
            if not c[index]:
                fails.append(f"{name}: {column} is empty")
    problems["4. no unexplained blank in MATRIX-RESULTS.md"] = fails
    print(f"control 4: {len(fails)} problems")

    print()
    total = 0
    for title, fails in problems.items():
        total += len(fails)
        mark = "PASS" if not fails else f"FAIL ({len(fails)})"
        print(f"{mark:<10}{title}")
        for line in fails[:40]:
            print(f"    {line}")
        if len(fails) > 40:
            print(f"    ... and {len(fails) - 40} more")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
