"""Score Axcess's keyboard and focus checks on NavA11y's 22-page dataset.

See PREREGISTRATION.md for the rules. The dataset is the git-ignored clone in
``literature-replication/artifacts/nava11y`` (MIT); labels are in
``ground_truth.json`` beside this file.

    uv run python experiments/tabbing/ab/nava11y/score_nava11y.py --label NAME
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DATA = (
    REPO / "experiments/tabbing/literature-replication/artifacts/nava11y"
    / "dataset/focus-behavior-dataset"
)
for extra in (REPO, REPO / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from playwright.async_api import async_playwright  # noqa: E402

from audit.analyzer.axe import AxeAnalyzer  # noqa: E402
from audit.analyzer.focus import FocusProbe  # noqa: E402
from audit.analyzer.interaction import InteractionProbe  # noqa: E402
from audit.analyzer.keyboard import KeyboardOperabilityProbe, KeyboardProbe  # noqa: E402

STRICT = {
    "2.4.7": {"focus-not-visible"},
    "2.4.3": {
        "focus-order-positive-tabindex",
        "focus-order-non-interactive-stop",
        "focus-order-visual-mismatch",
        "keyboard-dialog-focus-not-moved",
        "keyboard-dialog-focus-escapes",
    },
    "2.4.11": {"focus-not-obscured"},
    "2.4.12": {"focus-not-obscured"},
    "2.4.13": set(),
}
TRAPS = {"keyboard-trap-stuck", "keyboard-dialog-no-keyboard-exit"}


async def rules_on(browser, path: Path) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    found: list[tuple[str, str]] = []
    for step in ("keyboard", "focus", "click-through"):
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        await page.goto(path.as_uri(), wait_until="load")
        await page.wait_for_timeout(120)
        if step == "keyboard":
            probe = KeyboardProbe(operability=KeyboardOperabilityProbe())
            found += [(f.rule_id, f.target_selector) for f in await probe.run(page)]
        elif step == "focus":
            found += [(f.rule_id, f.target_selector) for f in await FocusProbe().run(page)]
        else:
            result = await InteractionProbe(
                axe=AxeAnalyzer.from_bundled(), level="AA", dialog_checks=True
            ).run(page)
            found += [(f.rule_id, f.target_selector) for f in result.keyboard_findings]
        await ctx.close()
    return found


def score(rows: list[dict], defect_level: bool) -> dict:
    per: dict[str, dict[str, int]] = {}
    for row in rows:
        fired = {rule for rule, _ in row["found"]}
        for sc, expected in row["expected"].items():
            rules = STRICT[sc] | (TRAPS if defect_level and sc == "2.4.3" else set())
            actual = "FAIL" if fired & rules else "PASS"
            cell = per.setdefault(sc, {"TP": 0, "TN": 0, "FP": 0, "FN": 0})
            key = {("FAIL", "FAIL"): "TP", ("PASS", "PASS"): "TN", ("PASS", "FAIL"): "FP"}
            cell[key.get((expected, actual), "FN")] += 1
            row.setdefault("verdicts", {})[("defect:" if defect_level else "") + sc] = actual
    tot = {k: sum(c[k] for c in per.values()) for k in ("TP", "TN", "FP", "FN")}
    p = tot["TP"] / (tot["TP"] + tot["FP"]) if tot["TP"] + tot["FP"] else None
    r = tot["TP"] / (tot["TP"] + tot["FN"]) if tot["TP"] + tot["FN"] else None
    f1 = 2 * p * r / (p + r) if p and r else None
    return {"total": tot, "precision": p, "recall": r, "f1": f1, "per_sc": per}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    out = HERE / f"results-{args.label}.json"
    if out.exists():
        raise SystemExit(f"{out} exists; pick a new --label")
    truth = json.loads((HERE / "ground_truth.json").read_text())
    rows = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        for case in truth:
            found = await rules_on(browser, DATA / case["file"])
            rows.append({**case, "found": found})
        await browser.close()
    report = {"rows": rows}
    for name, subset in (("all", rows), ("contributed", [r for r in rows if r["category"] == "contributed"]),
                         ("original", [r for r in rows if r["category"] == "original"])):
        report[name] = {"strict": score(subset, False), "defect": score(subset, True)}
    report["freeze"] = {
        p: hashlib.sha256((REPO / p).read_bytes()).hexdigest()
        for p in ("src/audit/analyzer/focus/probe.py", "src/audit/analyzer/keyboard/operability.py",
                  "src/audit/analyzer/interaction/dialogs.py", "src/audit/analyzer/interaction/probe.py")
    }
    out.write_text(json.dumps(report, indent=1) + "\n")
    for name in ("all", "contributed", "original"):
        for kind in ("strict", "defect"):
            s = report[name][kind]
            print(f"{name:12s} {kind:7s} {s['total']} P={s['precision']} R={s['recall']} F1={s['f1']}")
    print(json.dumps(report["all"]["strict"]["per_sc"]))
    for row in rows:
        print(row["id"], row["category"][:4], row["file"].split("/")[-1][:60], row["expected"],
              {k: v for k, v in row["verdicts"].items() if not k.startswith("defect")},
              sorted({r for r, _ in row["found"]}))
    print(f"wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
