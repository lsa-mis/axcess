"""Aggregate the feasibility runs into the numbers FEASIBILITY.md quotes.

Nothing is recomputed by hand: every figure in the report comes from here.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.census_flows import APPENDIX

HERE = Path(__file__).resolve().parent.parent
DERIVED = HERE / "derived"

runs = json.loads((DERIVED / "feasibility.json").read_text())
by_subject: dict[str, list[dict]] = {}
for run in runs:
    by_subject.setdefault(run["subject"], []).append(run)

summary = {}
print(f"{'subject':>13} {'appx#T':>7} {'obs#T':>7} {'ratioT':>7} "
      f"{'appx#V':>7} {'obs#V':>7} {'ratioV':>7} {'tagStable':>10} {'tagInert':>9}")

for subject, subject_runs in sorted(by_subject.items()):
    tagged = [r for r in subject_runs if r["tagged"] and r.get("ok")]
    untagged = [r for r in subject_runs if not r["tagged"] and r.get("ok")]
    appendix = APPENDIX[subject]

    totals = {r["signature"]["total"] for r in subject_runs if r.get("ok")}
    visibles = {r["signature"]["visible"] for r in subject_runs if r.get("ok")}

    # G1a: are the neutral ids identical across fresh contexts?
    id_sets = [tuple(r["census_ids"]) for r in tagged]
    stable = len(set(id_sets)) == 1 and bool(id_sets)

    # G1b: does tagging change the page at all?
    inert = (
        {(r["signature"]["total"], r["signature"]["visible"]) for r in tagged}
        == {(r["signature"]["total"], r["signature"]["visible"]) for r in untagged}
        and {json.dumps(r["signature"]["tags"], sort_keys=True) for r in tagged}
        == {json.dumps(r["signature"]["tags"], sort_keys=True) for r in untagged}
    )

    obs_total = max(totals)
    obs_visible = max(visibles)
    summary[subject] = {
        "appendix": appendix,
        "observed_total": obs_total,
        "observed_visible": obs_visible,
        "ratio_total": round(obs_total / appendix["total"], 4),
        "ratio_visible": round(obs_visible / appendix["visible"], 4),
        "total_spread": max(totals) - min(totals),
        "visible_spread": max(visibles) - min(visibles),
        "runs_ok": sum(1 for r in subject_runs if r.get("ok")),
        "runs": len(subject_runs),
        "served": sorted({r["served"] for r in subject_runs}),
        "denied": sorted({r["denied"] for r in subject_runs}),
        "essential_missing": sorted(
            {len(r["denial_report"]["essential"]) for r in subject_runs}
        ),
        "denied_urls": sorted(
            {u for r in subject_runs for u in r["denied_urls"]}
        ) if any("denied_urls" in r for r in subject_runs) else sorted(
            {u for r in subject_runs for b in r["denial_report"].values() for u in b}
        ),
        "tagged_elements": sorted({r.get("tagged_elements") for r in tagged}),
        "census_ids_stable_across_contexts": stable,
        "tagging_is_dom_inert": inert,
        "distinct_focus_stops_tagged": sorted(
            {r["distinct_focus_stops"] for r in tagged}
        ),
        "page_errors": sorted({e for r in subject_runs for e in r["page_errors"]})[:5],
        "console_errors": sorted(
            {e for r in subject_runs for e in r["console_errors"]}
        )[:5],
    }
    s = summary[subject]
    print(f"{subject:>13} {appendix['total']:>7} {obs_total:>7} "
          f"{s['ratio_total']:>7.3f} {appendix['visible']:>7} {obs_visible:>7} "
          f"{s['ratio_visible']:>7.3f} {str(stable):>10} {str(inert):>9}")

(DERIVED / "feasibility_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

print("\nper-subject detail:")
for subject, s in summary.items():
    print(f"  {subject}: runs_ok={s['runs_ok']}/{s['runs']} "
          f"served={s['served']} denied={s['denied']} "
          f"essential_missing={s['essential_missing']} "
          f"spread(total)={s['total_spread']} spread(vis)={s['visible_spread']} "
          f"tagged_elements={s['tagged_elements']} "
          f"focus_stops={s['distinct_focus_stops_tagged']}")
    if s["denied_urls"]:
        print(f"      denied: {s['denied_urls']}")
    if s["page_errors"]:
        print(f"      page_errors: {s['page_errors']}")
