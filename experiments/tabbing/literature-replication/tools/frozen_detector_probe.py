"""Can the FROZEN Axcess detectors run against a real page?

Arm 1 answered the wrong question. `tools/gds_run.py` imports only Playwright;
`kbdiff` appears in its docstring and nowhere in its code. Its 6/6 therefore
measured a reimplementation of the differential idea, not the shipped detectors
-- which is not what the objective asks. Claude Code caught this by challenging
the brief's premise; no control here would have.

This script establishes the one fact that decides the rest of the experiment:
whether `DifferentialRunner` -- unmodified, imported from `src/audit/` -- can
produce a verdict on a GDS case whose answer is already known.

Pre-registered before running:
  H-run: the frozen runner returns VIOLATION for `#webchat` (a div with a click
  handler, mouse-operable and not keyboard-operable) and NO_LEAD for the real
  `<button>` on the same page.
  Falsified if it errors, returns UNKNOWN for both, or cannot address the
  elements at all.
  Control: the real `<button>` is the negative. A runner that returns VIOLATION
  for everything would score perfect recall and be worthless.

The detectors are imported, never edited. `score.py` is not touched.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from playwright.async_api import async_playwright  # noqa: E402

from audit.analyzer.keyboard.kbdiff.differential import (  # noqa: E402
    DifferentialRunner,
    TrialConfig,
)
from audit.analyzer.keyboard.kbdiff.candidates import collect_candidates  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
PAGE = HERE / "artifacts" / "gds" / "test-cases.html"

# The detectors address elements by `data-probe`. GDS pages carry no such
# attribute, so the harness supplies one -- this is the identity-supply step the
# census exists for, not a change to what the detectors do.
TAG_JS = """
(pairs) => {
    const out = {};
    for (const [probe, sel] of pairs) {
        const el = document.querySelector(sel);
        if (el) { el.setAttribute('data-probe', probe); out[probe] = true; }
        else { out[probe] = false; }
    }
    return out;
}
"""

CASES = [
    ("gds-fake-button", "#webchat", "positive"),
    ("gds-real-button", "button:not([class])", "negative (control)"),
]


async def main() -> int:
    if not PAGE.exists():
        print(f"missing {PAGE}", file=sys.stderr)
        return 1

    pairs = [[probe, sel] for probe, sel, _ in CASES]
    rows = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        async def make_context():
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="UTC",
                service_workers="block",
            )
            # Tag at document start so every fresh trial context addresses the
            # same elements; the runner opens its own contexts per trial.
            await context.add_init_script(
                f"""
                document.addEventListener('DOMContentLoaded', () => {{
                    const pairs = {json.dumps(pairs)};
                    for (const [probe, sel] of pairs) {{
                        const el = document.querySelector(sel);
                        if (el) el.setAttribute('data-probe', probe);
                    }}
                }});
                """
            )
            return context

        config = TrialConfig(url=PAGE.as_uri(), viewport="1920x1080")
        runner = DifferentialRunner(make_context, config)

        # Candidate generation on the real page, using the frozen collector.
        context = await make_context()
        page = await context.new_page()
        await page.goto(PAGE.as_uri(), wait_until="load")
        await page.wait_for_timeout(500)
        tagged = await page.evaluate(TAG_JS, pairs)
        candidates = await collect_candidates(page)
        named = {c.probe_id for c in candidates if c.probe_id}
        await context.close()

        order = await runner.tab_order()

        for probe, sel, kind in CASES:
            outcome = await runner.run_probe(probe, "gds/test-cases.html", order)
            rows.append(
                {
                    "probe": probe,
                    "selector": sel,
                    "kind": kind,
                    "tagged": tagged.get(probe),
                    "proposed_by_candidate_generator": probe in named,
                    "verdict": str(outcome.verdict),
                    "in_tab_order": outcome.in_tab_order,
                }
            )
        await browser.close()

    print(f"frozen candidate generator proposed {len(candidates)} elements")
    print()
    for r in rows:
        print(json.dumps(r))

    pos = next(r for r in rows if r["kind"] == "positive")
    neg = next(r for r in rows if r["kind"].startswith("negative"))
    print()
    print(
        json.dumps(
            {
                "frozen_detectors_ran": True,
                "positive_verdict": pos["verdict"],
                "control_verdict": neg["verdict"],
                "H-run_falsified": not (
                    "violation" in pos["verdict"].lower()
                    and "violation" not in neg["verdict"].lower()
                ),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
