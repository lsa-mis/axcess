"""Measure two DOM relations for every probe, as a candidate cheap rule.

Does the element CONTAIN a keyboard-reachable native control, or sit INSIDE
one? Both are the classic redundant-click-surface shape: a card wrapping a
link, a decorative span inside a button. Pure DOM queries, no layout, no
execution -- the cheapest class of signal there is.

Writes its observations to JSON so the rule can be scored offline against the
frozen labels, exactly as analyze_candidates.py does.
"""
import asyncio, json, os, sys, pathlib
sys.path.insert(0, "src"); sys.path.insert(0, ".")
from playwright.async_api import async_playwright
from experiments.tabbing.runner.serve import ContextFactory, page_url
from experiments.tabbing.runner.bakeoff import VIEWPORT

FOCUSABLE = ("a[href], button, input, select, textarea, summary, "
             '[tabindex]:not([tabindex="-1"])')

JS = """
(sel) => {
  const out = {};
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) walk(el.shadowRoot);
      const id = el.getAttribute && el.getAttribute('data-probe');
      if (!id) continue;
      const inner = el.querySelector(sel);
      const outer = el.parentElement ? el.parentElement.closest(sel) : null;
      const self_native = el.matches(sel);
      out[id] = {
        contains_focusable: !!inner && !self_native,
        contained_probe: inner ? (inner.getAttribute('data-probe') || null) : null,
        inside_focusable: !!outer,
        ancestor_probe: outer ? (outer.getAttribute('data-probe') || null) : null,
        self_native,
      };
    }
  };
  walk(document);
  return out;
}
"""

async def main(out_path):
    root = pathlib.Path(os.environ.get("PROBE_CORPUS",
                        "experiments/tabbing/fixtures"))
    truth = json.loads((root / "truth.json").read_text())
    results = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        factory = ContextFactory(browser, VIEWPORT, root)
        for page_path in sorted(truth["pages"]):
            ctx = await factory()
            try:
                pg = await ctx.new_page()
                await pg.goto(page_url(page_path), wait_until="load")
                await pg.wait_for_timeout(120)
                for frame in pg.frames:
                    try:
                        results.update(await frame.evaluate(JS, FOCUSABLE))
                    except Exception:
                        pass
            finally:
                await ctx.close(); await factory.close_open_contexts()
        await browser.close()
    pathlib.Path(out_path).write_text(json.dumps(results, indent=1))
    print(f"observed {len(results)} probes -> {out_path}")

asyncio.run(main(sys.argv[1]))
