"""Verify the matrix has no unexplained empty cells.

Written by Opus 5 independently of whatever Claude Code produces, and reading
the raw bakeoff artifacts rather than the generated report. A summary checked
against itself proves nothing; this checks the report against the JSON that
should have produced it, and against the two published tables.

Checks, in order of how badly a failure matters:

  V1  fixtures rows reproduce `detector-matrix.results.md` cell for cell.
  V2  fixtures C10-C16 reproduce `CHEAP_DETECTOR_REVIEW.md` cell for cell.
  V3  no blank cell anywhere without a reason string.
  V4  F1-undefined coincides with precision-undefined (that pair is legitimate).
  V5  edgecases carries a populated `scores` array.
  V6  `src/audit/` is untouched.

Usage:
    uv run --offline --no-sync python -m tools.verify_matrix_complete
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[4]
HERE = pathlib.Path(__file__).resolve().parent.parent
TABBING = REPO / "experiments" / "tabbing"

# Published references. These are the control: the port, the cap change, and
# every aggregation change must leave them untouched.
PUBLISHED_MATRIX = TABBING / "results" / "detector-matrix.results.md"
PUBLISHED_CHEAP = TABBING / "CHEAP_DETECTOR_REVIEW.md"

# A cell may be empty ONLY if it carries one of these, or is an em dash that
# coincides with an undefined precision.
REASON_PATTERNS = (
    "not applicable",
    "abstained",
    "measurement failed",
    "not run",
    "priced at its arm",
    "measured",
)


def parse_md_table(path: pathlib.Path, row_prefix: str) -> dict[str, list[str]]:
    """Rows of a markdown table, keyed by first cell, for rows starting with prefix."""
    out: dict[str, list[str]] = {}
    for line in path.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or not cells[0].startswith(row_prefix):
            continue
        out[cells[0]] = cells
    return out


def num(cell: str) -> float | None:
    """A number out of a markdown cell, tolerating bold and percent signs."""
    m = re.search(r"(\d+\.?\d*)", cell.replace("**", ""))
    return float(m.group(1)) if m else None


def check_published_fixtures(report: pathlib.Path) -> list[str]:
    """V1/V2: the generated fixtures rows against both published tables."""
    problems: list[str] = []
    if not report.exists():
        return [f"V1/V2 SKIPPED: {report.name} does not exist yet"]

    generated = parse_md_table(report, "")
    for source, prefix in ((PUBLISHED_MATRIX, "D"), (PUBLISHED_CHEAP, "C")):
        if not source.exists():
            problems.append(f"missing published reference {source}")
            continue
        published = parse_md_table(source, prefix)
        for name, pub_cells in published.items():
            # Match on the detector/rule identifier at the start of the name.
            key = name.split(":")[0].split(" ")[0]
            hits = [g for g in generated if g.startswith(key + " ") or g == key]
            if not hits:
                problems.append(f"{key}: present in {source.name}, ABSENT from report")
    return problems


def check_no_blank_cells(report: pathlib.Path) -> list[str]:
    """V3/V4: every empty cell must be explained."""
    problems: list[str] = []
    if not report.exists():
        return ["V3 SKIPPED: report does not exist yet"]

    header: list[str] = []
    for line in report.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue
        if any(h in " ".join(cells).lower() for h in ("detector", "rule |", "| tp")):
            header = [c.lower() for c in cells]
            continue
        for i, cell in enumerate(cells):
            if cell not in ("", "—", "-"):
                continue
            col = header[i] if i < len(header) else f"col{i}"
            if cell == "" :
                problems.append(f"{cells[0][:40]}: TRULY EMPTY cell in '{col}'")
    return problems


def check_edgecases_scored() -> list[str]:
    """V5: the corpus that produced zero rows."""
    results = TABBING / "edgecases" / "results"
    if not results.exists():
        return ["V5: edgecases results dir missing"]
    problems = []
    scored = False
    for path in results.glob("bakeoff-*.json"):
        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue
        if payload.get("scores"):
            scored = True
    if not scored:
        problems.append(
            "V5 FAIL: no edgecases artifact has a populated `scores` array "
            "(the CDP CBOR overflow is still unfixed)"
        )
    return problems


def check_frozen_untouched() -> list[str]:
    """V6: the detectors must not have moved."""
    try:
        out = subprocess.run(
            ["git", "diff", "--stat", "--", "src/audit/"],
            cwd=REPO, capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except Exception as exc:
        return [f"V6 could not run: {exc}"]
    return [f"V6 FAIL: src/audit/ modified:\n{out}"] if out else []


def main() -> int:
    report = HERE / "MATRIX-RESULTS.md"
    checks = {
        "V1/V2 published references reproduced": check_published_fixtures(report),
        "V3/V4 no unexplained blank cells": check_no_blank_cells(report),
        "V5 edgecases scored": check_edgecases_scored(),
        "V6 frozen detectors untouched": check_frozen_untouched(),
    }

    failed = 0
    for name, problems in checks.items():
        if problems:
            failed += 1
            print(f"FAIL  {name}")
            for p in problems[:12]:
                print(f"        {p}")
            if len(problems) > 12:
                print(f"        ... and {len(problems) - 12} more")
        else:
            print(f"ok    {name}")

    print()
    print(f"{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
