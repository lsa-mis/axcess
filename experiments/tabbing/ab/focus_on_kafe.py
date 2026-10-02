"""Round 3: the focus probe's findings on KAFE subjects, one JSON line each.

Unlabelled for these criteria, so it measures volume and cost; precision of
focus-not-visible is checked by ``focus_pixel_check.py``. From the repo root:

    uv run python experiments/tabbing/ab/focus_on_kafe.py SUBJECT... > focus.jsonl
"""

import asyncio
import json
import sys
import time

sys.path[:0] = [".", "src", "experiments/tabbing/literature-replication"]
from playwright.async_api import async_playwright
from tools import flowfile, kafe_matrix, replay

from audit.analyzer.focus import FocusProbe


async def main(subjects):
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for subj in subjects:
            try:
                index = flowfile.load_exchanges(kafe_matrix.capture_path(subj).read_bytes())
                url = kafe_matrix.entry_url(index)
                router = replay.ReplayRouter(index)
                ctx = await b.new_context(viewport=kafe_matrix.VIEWPORT, service_workers="block")
                await router.attach(ctx)
                pg = await ctx.new_page()
                await pg.goto(url, wait_until="load", timeout=60000)
                await pg.wait_for_timeout(3000)
                t = time.perf_counter()
                fs = await FocusProbe(include_aaa="--aaa" in sys.argv).run(pg)
                ms = (time.perf_counter() - t) * 1000
                print(
                    json.dumps(
                        {
                            "s": subj,
                            "ms": round(ms),
                            "f": [[f.rule_id, f.target_selector, f.html_snippet[:160]] for f in fs],
                        }
                    ),
                    flush=True,
                )
                await ctx.close()
            except Exception as e:
                print(json.dumps({"s": subj, "err": str(e)[:100]}), flush=True)
        await b.close()


asyncio.run(main([a for a in sys.argv[1:] if a != "--aaa"]))
