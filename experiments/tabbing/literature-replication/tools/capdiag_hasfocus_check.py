"""Does `document.hasFocus()` in the top document stay true when focus is inside
a child iframe?

`CAPDIAG-REPORT.md` §1.3 reads `hasFocus() === false` at a `#el:body:*` position
as "focus left the page", and concludes from that that six of the seven capped
subjects cap for an instrument reason rather than a page defect. If instead
`hasFocus()` went false merely because focus had moved into an iframe, that
conclusion would be wrong and those six could be real traps. This settles it on
the same Chromium build, with no network.

    uv run --offline --no-sync python -u -m tools.capdiag_hasfocus_check
"""

from __future__ import annotations

import asyncio
import json

from playwright.async_api import async_playwright

PARENT = (
    "<!doctype html><body><button id=a>a</button>"
    '<iframe id=f srcdoc="&lt;button id=inner&gt;inner&lt;/button&gt;"></iframe>'
    "<button id=b>b</button></body>"
)


async def main_async() -> int:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content(PARENT)
            frame = page.frames[1]

            await frame.evaluate("() => document.getElementById('inner').focus()")
            inside = {
                "top_activeElement": await page.evaluate("() => document.activeElement.tagName"),
                "top_hasFocus": await page.evaluate("() => document.hasFocus()"),
                "frame_activeElement": await frame.evaluate("() => document.activeElement.id"),
            }

            await page.evaluate("() => document.activeElement.blur()")
            await frame.evaluate("() => document.activeElement.blur()")
            nothing = {
                "top_activeElement": await page.evaluate("() => document.activeElement.tagName"),
                "top_activeElement_is_null": await page.evaluate(
                    "() => document.activeElement === null"
                ),
                "top_hasFocus": await page.evaluate("() => document.hasFocus()"),
            }
        finally:
            await browser.close()

    print(json.dumps({"focus_inside_iframe": inside, "nothing_focused": nothing}, indent=2))
    ok = inside["top_hasFocus"] is True and nothing["top_activeElement"] == "BODY"
    print("hasFocus distinguishes 'in an iframe' from 'left the page':", ok)
    print(
        "activeElement falls back to <body> rather than null:",
        not nothing["top_activeElement_is_null"],
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
