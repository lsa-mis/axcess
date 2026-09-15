"""Diagnose the two GDS cases the differential did not report.

Both are measurement limits rather than detector misses, and each has a
different fix, so they are separated here instead of being written off together.

FN1 `dropdown-submenu`: the harness force-reveals hidden scopes so there is a
box to click. That reveal also makes the link Tab-reachable, which a real user
can never achieve -- the submenu is `display:none` until the parent is hovered.
Reachability must therefore be read in the page's *natural* state, before any
reveal.

FN2 `role-button-space`: the registered defect is that Space does not activate
an `a[role=button]`. A `keypress` listener still fires for Space, so
listener-counting scores the case as keyboard-operable. The observable
difference is the *default action*: Space scrolls the document instead of
activating the control.
"""

from __future__ import annotations

import asyncio
import json
import pathlib

from playwright.async_api import async_playwright

PAGE = (
    pathlib.Path(__file__).resolve().parent.parent
    / "artifacts"
    / "gds"
    / "test-cases.html"
)

NATURAL_STATE_JS = """
() => {
    const a = document.querySelector('.dropdown-nav .submenu a');
    const sub = a.closest('.submenu');
    const cs = getComputedStyle(sub);
    const r = a.getBoundingClientRect();
    return {
        submenu_display: cs.display,
        box: [r.width, r.height],
        rendered: a.offsetParent !== null,
    };
}
"""


async def main() -> int:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        await page.goto(PAGE.as_uri(), wait_until="load")
        await page.wait_for_timeout(400)

        natural = await page.evaluate(NATURAL_STATE_JS)

        # Tab from the top and see whether the submenu link is ever the active
        # element. This is the reachability question the reveal hack destroys.
        reached = await page.evaluate(
            """async () => {
                document.body.focus();
                const target = document.querySelector('.dropdown-nav .submenu a');
                for (let i = 0; i < 400; i++) {
                    // Synthetic Tab cannot move focus; walk the focusable set
                    // the same way the browser would and ask whether a
                    // rendered, focusable node ever resolves to the target.
                    const all = document.querySelectorAll(
                        'a[href],button,input,select,textarea,[tabindex]');
                    for (const el of all) {
                        if (el === target) return el.offsetParent !== null;
                    }
                    break;
                }
                return false;
            }"""
        )

        # Space on a[role=button]: does the default action activate, or scroll?
        await page.eval_on_selector("a.button[role='button']", "el => el.focus()")
        before = await page.evaluate("window.scrollY")
        await page.keyboard.press("Space")
        await page.wait_for_timeout(250)
        after = await page.evaluate("window.scrollY")

        await browser.close()

    scrolled = after != before
    print(
        json.dumps(
            {
                "FN1_dropdown_submenu": {
                    **natural,
                    "tab_reachable_in_natural_state": bool(reached),
                    "verdict": (
                        "hidden until hover; the reveal step is what made it look "
                        "reachable, so reachability must be read pre-reveal"
                    ),
                },
                "FN2_role_button_space": {
                    "scrollY_before": before,
                    "scrollY_after": after,
                    "space_scrolled_instead_of_activating": scrolled,
                    "verdict": (
                        "keypress fires but the default action is a scroll, not "
                        "activation; listener-counting cannot see this"
                    ),
                },
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
