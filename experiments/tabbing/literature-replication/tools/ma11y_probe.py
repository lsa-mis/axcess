"""Arm 2: does Ma11y's F54 operator manufacture a real IAF with known truth?

Arms 1 and 3 are both capped by how many labelled failures somebody else
happened to build: GDS has 6, KAFE has 36 positives across 60 pages. Mutation
analysis removes that ceiling -- faults are *generated*, so ground truth is
known by construction and N is bounded by compute rather than by a corpus.

Ma11y (`mahantaf/web-a11y-tool-analyzer`, MIT) implements 31 WCAG
failure-technique operators. F54 is the one that matters here: it moves an
element's `onclick` handler to `onmousedown`, which is precisely
mouse-operable-but-not-keyboard-operable -- KAFE's IAF construct.

This script does not run Ma11y. It reimplements F54's single mutation against a
local fixture to answer one question before any further investment: does the
mutation actually produce the fault class it claims to? A generator that emits
equivalent (non-faulty) mutants would quietly inflate recall on a corpus nobody
hand-checked.

Pre-registered before running:
  H-mut: after F54, the element activates by mouse but not by keyboard.
  Falsified if the mutated element still activates by keyboard, or if the
  mutation does not apply.
  Control: the SAME element, unmutated, must stay keyboard-operable. Without
  it, an element that was already broken would look like a successful mutation.
  N=2 per condition, order alternated.
"""

from __future__ import annotations

import asyncio
import json

from playwright.async_api import async_playwright

# A correctly-built control: a real button with a real click handler. Keyboard
# and mouse both work here, which is what makes it a usable mutation target.
FIXTURE = """
<!doctype html><html><body>
  <button id="target" onclick="window.__fired = (window.__fired||0)+1">Save</button>
  <p id="out">unclicked</p>
</body></html>
"""

# F54, transcribed from Ma11y's operator source (arm2/F54.js).
F54_APPLY = """
() => {
    const el = document.getElementById('target');
    const handler = el.getAttribute('onclick');
    if (!handler) return false;
    el.setAttribute('onmousedown', handler);
    el.removeAttribute('onclick');
    return true;
}
"""


async def probe(page) -> dict:
    """Activate by keyboard, then by trusted mouse, counting each separately."""
    await page.evaluate("() => { window.__fired = 0; }")

    await page.eval_on_selector("#target", "el => el.focus()")
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(80)
    await page.keyboard.press("Space")
    await page.wait_for_timeout(80)
    by_key = await page.evaluate("window.__fired || 0")

    await page.evaluate("() => { window.__fired = 0; }")
    box = await page.eval_on_selector(
        "#target",
        """el => { const r = el.getBoundingClientRect();
                   return {x: r.x + r.width/2, y: r.y + r.height/2}; }""",
    )
    # Trusted pointer input, not element.click(): the latter synthesises an
    # event that does not hit-test and reads as keyboard activation.
    await page.mouse.click(box["x"], box["y"])
    await page.wait_for_timeout(80)
    by_mouse = await page.evaluate("window.__fired || 0")

    return {"activates_by_keyboard": by_key > 0, "activates_by_mouse": by_mouse > 0}


async def main() -> int:
    rows: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for repeat in range(2):
            conditions = ["control", "mutated"]
            if repeat:
                conditions.reverse()
            for condition in conditions:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content(FIXTURE)
                applied = False
                if condition == "mutated":
                    applied = await page.evaluate(F54_APPLY)
                result = await probe(page)
                rows.append(
                    {
                        "condition": condition,
                        "repeat": repeat,
                        "mutation_applied": applied,
                        **result,
                    }
                )
                await context.close()
        await browser.close()

    for row in rows:
        print(json.dumps(row))

    control = [r for r in rows if r["condition"] == "control"]
    mutated = [r for r in rows if r["condition"] == "mutated"]

    control_ok = all(
        r["activates_by_keyboard"] and r["activates_by_mouse"] for r in control
    )
    is_iaf = all(
        r["activates_by_mouse"] and not r["activates_by_keyboard"] for r in mutated
    )
    applied = all(r["mutation_applied"] for r in mutated)
    stable = (
        len({(r["activates_by_keyboard"], r["activates_by_mouse"]) for r in mutated})
        == 1
    )

    print()
    print(
        json.dumps(
            {
                "control_keyboard_and_mouse_both_work": control_ok,
                "mutation_applied": applied,
                "mutated_is_mouse_only": is_iaf,
                "H-mut_falsified": not (applied and is_iaf),
                "reproducible": stable,
                "verdict": (
                    "F54 manufactures a genuine IAF with known ground truth"
                    if (control_ok and applied and is_iaf and stable)
                    else "F54 did NOT produce the claimed fault class here"
                ),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
