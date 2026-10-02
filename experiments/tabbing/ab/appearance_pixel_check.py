"""Round 6: an independent pixel check of every focus-appearance-insufficient lead.

WCAG 2.4.13 Focus Appearance (AAA) asks for a focus indicator whose area is at
least that of a 2 CSS px thick perimeter of the unfocused control, with 3:1
contrast between the same pixels focused and unfocused. This measures exactly
that from screenshots (8 px around the control, twice before focus to measure
noise, once after): it counts the pixels whose colours before and after have
>= 3:1 contrast, and compares them with 4 * (width + height), the area of a 2 px
ring. A lead the pixels say passes is a false positive of the style-based rule.

    uv run python experiments/tabbing/ab/appearance_pixel_check.py FOCUS.jsonl
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for extra in (REPO, REPO / "src", REPO / "experiments/tabbing/literature-replication"):
    sys.path.insert(0, str(extra))

from PIL import Image  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402


def _lum(rgb: tuple[int, int, int]) -> float:
    def f(x: float) -> float:
        x /= 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrasting(a: bytes, b: bytes) -> int:
    ia = Image.open(io.BytesIO(a)).convert("RGB")
    ib = Image.open(io.BytesIO(b)).convert("RGB")
    if ia.size != ib.size:
        return -1
    n = 0
    for p, q in zip(ia.getdata(), ib.getdata(), strict=True):
        if p == q:
            continue
        x, y = sorted((_lum(p), _lum(q)), reverse=True)
        if (x + 0.05) / (y + 0.05) >= 3:
            n += 1
    return n


async def main(path: Path) -> None:
    from tools import flowfile, kafe_matrix, replay

    rows = [json.loads(line) for line in path.open()]
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        for row in rows:
            sels = [
                sel for rule, sel, _ in row.get("f", []) if rule == "focus-appearance-insufficient"
            ]
            if not sels:
                continue
            index = flowfile.load_exchanges(kafe_matrix.capture_path(row["s"]).read_bytes())
            ctx = await browser.new_context(
                viewport=kafe_matrix.VIEWPORT, service_workers="block", reduced_motion="reduce"
            )
            await replay.ReplayRouter(index).attach(ctx)
            page = await ctx.new_page()
            await page.goto(kafe_matrix.entry_url(index), wait_until="load", timeout=60_000)
            await page.wait_for_timeout(3000)
            await page.keyboard.press("Shift")
            for sel in sels:
                rec: dict = {"s": row["s"], "sel": sel}
                try:
                    loc = page.locator(sel).first
                    await loc.scroll_into_view_if_needed(timeout=2000)
                    box = await loc.bounding_box()
                    clip = {
                        "x": max(box["x"] - 8, 0),
                        "y": max(box["y"] - 8, 0),
                        "width": box["width"] + 16,
                        "height": box["height"] + 16,
                    }
                    a = await page.screenshot(clip=clip)
                    await page.wait_for_timeout(300)
                    a2 = await page.screenshot(clip=clip)
                    await loc.focus()
                    await page.wait_for_timeout(500)
                    b = await page.screenshot(clip=clip)
                    await loc.evaluate("e => e.blur()")
                    need = 4 * (box["width"] + box["height"])
                    got = _contrasting(a2, b)
                    rec.update(
                        noise=_contrasting(a, a2), area=got, need=round(need), passes=got >= need
                    )
                except Exception as exc:
                    rec["err"] = str(exc)[:80]
                print(json.dumps(rec), flush=True)
            await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
