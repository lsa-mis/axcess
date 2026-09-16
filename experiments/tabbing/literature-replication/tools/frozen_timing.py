"""Per-button cost of the frozen differential, against the 300 ms cap.

Harry's constraint: 300 ms is a cap one button's detection must not exceed, not
a number to report as a win. Nothing in this experiment has measured it -- the
feasibility runs recorded no wall clock at all, and an earlier figure (33.6 ms
for 15 Tab presses) measured a different unit and is retracted.

The unit here is one `run_probe` call: the full mouse trial plus one keyboard
trial per configured key, each in its own fresh context, which is what the
frozen `DifferentialRunner` does per candidate.

Pre-registered before running:
  H-cap: median per-probe time EXCEEDS 300 ms, because each probe opens
  multiple fresh browser contexts and a context launch alone costs tens of ms.
  Falsified if the median is under 300 ms.
  Control: `tab_order()` is timed separately and excluded from the per-probe
  figure -- it is a once-per-page cost, not a per-button one, and folding it in
  would inflate every probe by the same constant.
  N=3 probes x 2 repeats, all runs reported, no run dropped.

Reference for context, recomputed from KAFE's own artifact: its Detection phase
averages 995 ms per subject (not the published 19.22 min, which is
proxy/crawl/extract infrastructure). That is a per-*page* figure and is NOT
comparable to a per-probe number; it is quoted only to keep the scales visible.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import statistics
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from playwright.async_api import async_playwright  # noqa: E402

from audit.analyzer.keyboard.kbdiff.differential import (  # noqa: E402
    DifferentialRunner,
    TrialConfig,
)

HERE = pathlib.Path(__file__).resolve().parent.parent
PAGE = HERE / "artifacts" / "gds" / "test-cases.html"
OUT = HERE / "derived" / "frozen_timing.json"

PROBES = [
    ("t-fake-button", "#webchat"),
    ("t-real-button", "button:not([class])"),
    ("t-tooltip", ".tooltips-not-focusable .tooltip-icon"),
]

CAP_MS = 300


async def main() -> int:
    pairs = [[p, s] for p, s in PROBES]
    rows: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        async def make_context():
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="UTC",
                service_workers="block",
            )
            await context.add_init_script(
                f"""
                document.addEventListener('DOMContentLoaded', () => {{
                    for (const [probe, sel] of {json.dumps(pairs)}) {{
                        const el = document.querySelector(sel);
                        if (el) el.setAttribute('data-probe', probe);
                    }}
                }});
                """
            )
            return context

        # Cap set from the page's own focusable count, not inherited. 306
        # focusable elements against the 300 default is what made the earlier
        # run abstain; see PREMISE-CORRECTION.md.
        config = TrialConfig(url=PAGE.as_uri(), viewport="1920x1080", max_tabs=1200)
        runner = DifferentialRunner(make_context, config)

        t0 = time.perf_counter()
        order = await runner.tab_order()
        tab_ms = (time.perf_counter() - t0) * 1000

        for repeat in range(2):
            items = list(PROBES) if repeat == 0 else list(reversed(PROBES))
            for probe, sel in items:
                started = time.perf_counter()
                outcome = await runner.run_probe(probe, "gds", order)
                elapsed = (time.perf_counter() - started) * 1000
                rows.append(
                    {
                        "probe": probe,
                        "repeat": repeat,
                        "ms": round(elapsed, 1),
                        "verdict": str(outcome.verdict),
                        "keys": list(config.keys),
                    }
                )
        await browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "tab_order_ms_once_per_page": round(tab_ms, 1),
                "keys_per_probe": list(TrialConfig(url="", viewport="").keys),
                "cap_ms": CAP_MS,
                "runs": rows,
            },
            indent=2,
        )
        + "\n"
    )

    per_probe = [r["ms"] for r in rows]
    median = statistics.median(per_probe)
    print(f"tab_order (once per page, excluded from per-probe): {tab_ms:,.0f} ms")
    print(f"keys per probe: {list(TrialConfig(url='', viewport='').keys)}")
    print()
    for r in rows:
        print(f"  {r['probe']:<16} repeat={r['repeat']}  {r['ms']:>9,.1f} ms  {r['verdict']}")
    print()
    print(
        json.dumps(
            {
                "n_runs": len(per_probe),
                "median_ms": round(median, 1),
                "min_ms": round(min(per_probe), 1),
                "max_ms": round(max(per_probe), 1),
                "spread_ms": round(max(per_probe) - min(per_probe), 1),
                "cap_ms": CAP_MS,
                "runs_over_cap": sum(1 for m in per_probe if m > CAP_MS),
                "H-cap_falsified": median < CAP_MS,
                "verdict": (
                    f"median {median:,.0f} ms EXCEEDS the {CAP_MS} ms per-button cap"
                    if median > CAP_MS
                    else f"median {median:,.0f} ms is within the {CAP_MS} ms cap"
                ),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
