"""Which GDS "Keyboard access" cases does any Axcess check flag?

Runs, on the GDS Accessibility Tool Audit page (the gitignored
``literature-replication/artifacts/gds-corpus`` build, served offline), every
check a default scan runs that can speak to keyboard access: axe-core at AAA
(WCAG 2.2), the focus probe, and the keyboard check (traps, plus Standard and
Advanced mouse-only controls). Each finding is attributed to the GDS example
it sits in (the ``div.example`` after each case heading), so the output is one
row per case: which checks flagged something inside it.

This is a coverage map, not a precision score: GDS labels a case, not the
elements in it.

    uv run python experiments/tabbing/ab/gds_coverage.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for extra in (REPO, REPO / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from playwright.async_api import async_playwright  # noqa: E402

from audit.analyzer.axe import AxeAnalyzer  # noqa: E402
from audit.analyzer.focus import FocusProbe  # noqa: E402
from audit.analyzer.interaction import InteractionProbe  # noqa: E402
from audit.analyzer.keyboard import KeyboardOperabilityProbe, KeyboardProbe  # noqa: E402
from experiments.tabbing.runner.bakeoff import CORPORA  # noqa: E402
from experiments.tabbing.runner.serve import ContextFactory, page_url  # noqa: E402

# Tag each GDS example with its case id, so a finding's element can say
# which case it belongs to.
_TAG_JS = """
() => {
  let current = null;
  for (const el of document.querySelectorAll('h3[id], div.example')) {
    if (el.tagName === 'H3') current = el.id;
    else if (current) {
      // Every element, not just the box: a script can move one out of its
      // example (GDS appends the "focus far" lightbox to <body>).
      for (const node of [el, ...el.querySelectorAll('*')]) {
        if (!node.hasAttribute('data-gds-case')) node.setAttribute('data-gds-case', current);
      }
    }
  }
}
"""
_CASE_OF_JS = """
(selector) => {
  let el = null;
  try { el = document.querySelector(selector); } catch (e) { return null; }
  const box = el && el.closest('[data-gds-case]');
  return box ? box.getAttribute('data-gds-case') : null;
}
"""


async def main() -> None:
    root = CORPORA["gds"][0]
    cases: dict[str, set[str]] = {}
    # Findings outside the keyboard cases: the other 126 GDS cases test other
    # criteria, so a hit there is either another real problem or noise.
    elsewhere: dict[str, list[str]] = {}
    clicks: dict[str, object] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        factory = ContextFactory(browser, {"width": 1280, "height": 900}, root)
        for name in ("axe", "focus", "keyboard", "keyboard-advanced", "click-through"):
            context = await factory()
            page = await context.new_page()
            await page.goto(page_url("pages/test-cases.html"), wait_until="load")
            await page.wait_for_timeout(120)
            await page.evaluate(_TAG_JS)
            ids = await page.evaluate(
                "() => [...document.querySelectorAll('h3[id^=keyboard-access]')].map(h => h.id)"
            )
            for case in ids:
                cases.setdefault(case, set())
            found: list[tuple[str, str]] = []
            if name == "axe":
                axe = AxeAnalyzer.from_bundled()
                for v in await axe.run(page, level="AAA", version="2.2"):
                    found.append((f"axe:{v.rule_id}", v.target_selector))
            elif name == "focus":
                for f in await FocusProbe().run(page):
                    found.append((f"focus:{f.rule_id}", f.target_selector))
            elif name == "click-through":
                # Click-Through at a scan's default bounds, with the dialog
                # checks a scan turns on alongside the keyboard check.
                interaction = InteractionProbe(
                    axe=AxeAnalyzer.from_bundled(), level="AA", dialog_checks=True
                )
                result = await interaction.run(page)
                found += [
                    (f"{name}:{f.rule_id}", f.target_selector) for f in result.keyboard_findings
                ]
                clicks[name] = (result.clicks_succeeded, sorted(result.limits))
            else:
                probe = KeyboardProbe(
                    operability=KeyboardOperabilityProbe(advanced=name == "keyboard-advanced")
                )
                for f in await probe.run(page):
                    found.append((f"{name}:{f.rule_id}", f.target_selector))
            # Advanced reloads the page between trials, which drops the tags.
            await page.evaluate(_TAG_JS)
            for rule, selector in found:
                if rule.startswith("axe:color-contrast"):
                    continue  # contrast, on every case; not a keyboard result
                case = await page.evaluate(_CASE_OF_JS, selector)
                if case in cases:
                    cases[case].add(rule)
                elif name in ("focus", "keyboard", "click-through"):
                    elsewhere.setdefault(rule, []).append(case or "(outside any example)")
            await context.close()
        await browser.close()
    print(json.dumps({case: sorted(rules) for case, rules in cases.items()}, indent=1))
    print(json.dumps({"outside keyboard cases": elsewhere}, indent=1))
    print(json.dumps({"click-through clicks and limits": clicks}))


if __name__ == "__main__":
    asyncio.run(main())
