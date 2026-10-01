"""Round 3: an independent check of every focus-not-visible lead.

Screenshots each flagged control (10 px around it) twice before focus, to
measure noise, and once after, and counts changed pixels. A lead the pixels
contradict (they change on focus) is a false positive of the style-based
rule. It cannot see an indicator drawn more than 10 px away. From the repo
root, on the output of ``focus_on_kafe.py``:

    uv run python experiments/tabbing/ab/focus_pixel_check.py focus.jsonl
"""

import asyncio
import io
import json
import sys

sys.path[:0] = [".", "src", "experiments/tabbing/literature-replication"]
from PIL import Image, ImageChops
from playwright.async_api import async_playwright
from tools import flowfile, kafe_matrix, replay


def diff(a, b):
    ia = Image.open(io.BytesIO(a)).convert("RGB")
    ib = Image.open(io.BytesIO(b)).convert("RGB")
    if ia.size != ib.size:
        return 10**6
    d = ImageChops.difference(ia, ib).convert("L").point(lambda v: 255 if v > 24 else 0)
    return sum(1 for v in d.getdata() if v)


async def main():
    rows = [json.loads(l) for l in open(sys.argv[1])]
    out = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for r in rows:
            sels = [sel for rule, sel, _ in r.get("f", []) if rule == "focus-not-visible"]
            if not sels:
                continue
            index = flowfile.load_exchanges(kafe_matrix.capture_path(r["s"]).read_bytes())
            url = kafe_matrix.entry_url(index)
            router = replay.ReplayRouter(index)
            ctx = await b.new_context(
                viewport=kafe_matrix.VIEWPORT, service_workers="block", reduced_motion="reduce"
            )
            await router.attach(ctx)
            pg = await ctx.new_page()
            await pg.goto(url, wait_until="load", timeout=60000)
            await pg.wait_for_timeout(3000)
            await pg.keyboard.press("Shift")
            for sel in sels:
                rec = {"s": r["s"], "sel": sel}
                try:
                    loc = pg.locator(sel).first
                    await loc.scroll_into_view_if_needed(timeout=2000)
                    box = await loc.bounding_box()
                    clip = {
                        "x": max(box["x"] - 10, 0),
                        "y": max(box["y"] - 10, 0),
                        "width": box["width"] + 20,
                        "height": box["height"] + 20,
                    }
                    a = await pg.screenshot(clip=clip)
                    await pg.wait_for_timeout(300)
                    a2 = await pg.screenshot(clip=clip)
                    await loc.focus()
                    await pg.wait_for_timeout(400)
                    fb = await pg.screenshot(clip=clip)
                    await loc.evaluate("e=>e.blur()")
                    rec.update(
                        noise=diff(a, a2),
                        change=diff(a2, fb),
                        area=int(clip["width"] * clip["height"]),
                    )
                except Exception as e:
                    rec["err"] = str(e)[:60]
                out.append(rec)
                print(json.dumps(rec), flush=True)
            await ctx.close()
        await b.close()


asyncio.run(main())
