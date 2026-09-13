"""Separate a cosmetic hover from a functional hover reveal, per probe.

The existing hover arm asks "did pixels change", which cannot tell
`.btnish:hover { background: #d3e2fb }` from `.menu:hover .panel { display:block }`.
This asks the structural question instead: does hovering make a
previously-unrendered element in the probe's own subtree, or in its parent's
subtree, become rendered? That is what a disclosure actually does.

Also records whether any activation listener is bound directly to the element
(CDP, depth 0), so "no handler evidence at all" can be stated precisely rather
than inferred from the two flags the saved features happen to carry.
"""
import asyncio, json, os, sys, pathlib
sys.path.insert(0, "src"); sys.path.insert(0, ".")
from playwright.async_api import async_playwright
from experiments.tabbing.runner.serve import ContextFactory, page_url
from experiments.tabbing.runner.bakeoff import VIEWPORT

ACTIVATION = {"click", "mousedown", "mouseup", "dblclick", "pointerdown", "pointerup",
              "keydown", "keypress", "keyup"}

IDS_JS = """
() => {
  const out = [];
  const walk = (r) => { for (const el of r.querySelectorAll('*')) {
    if (el.shadowRoot) walk(el.shadowRoot);
    const id = el.getAttribute && el.getAttribute('data-probe');
    if (id) out.push(id); } };
  walk(document); return out;
}
"""

# Snapshot which elements in the probe's neighbourhood are rendered at all.
SHOT_JS = r"""
(id) => {
  const find = (root) => {
    const d = root.querySelector('[data-probe="' + id + '"]');
    if (d) return d;
    for (const el of root.querySelectorAll('*'))
      if (el.shadowRoot) { const h = find(el.shadowRoot); if (h) return h; }
    return null; };
  const el = find(document);
  if (!el) return null;
  const scope = el.parentElement || el;
  const seen = [];
  let i = 0;
  for (const node of scope.querySelectorAll('*')) {
    const r = node.getBoundingClientRect();
    const s = getComputedStyle(node);
    const rendered = r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
    seen.push((i++) + ':' + (rendered ? '1' : '0'));
  }
  return seen.join(',');
}
"""

async def own_listeners(cdp, probe_id):
    try:
        handle = await cdp.send("Runtime.evaluate", {"expression":
            "(() => { const find = (root) => {"
            " const d = root.querySelector('[data-probe=\"" + probe_id + "\"]');"
            " if (d) return d;"
            " for (const el of root.querySelectorAll('*'))"
            "  if (el.shadowRoot) { const h = find(el.shadowRoot); if (h) return h; }"
            " return null; }; return find(document); })()"})
        oid = handle.get("result", {}).get("objectId")
        if not oid:
            return None
        got = await cdp.send("DOMDebugger.getEventListeners", {"objectId": oid, "depth": 0})
        return sorted({e.get("type") for e in got.get("listeners", [])} & ACTIVATION)
    except Exception:
        return None

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
                cdp = await ctx.new_cdp_session(pg)
                for frame in pg.frames:
                    try:
                        ids = await frame.evaluate(IDS_JS)
                    except Exception:
                        continue
                    for pid in ids:
                        row = {"own_activation": None, "hover_reveal": None}
                        row["own_activation"] = await own_listeners(cdp, pid)
                        try:
                            before = await frame.evaluate(SHOT_JS, pid)
                            loc = frame.locator(f'[data-probe="{pid}"]').first
                            await loc.hover(timeout=1500, force=True)
                            await pg.wait_for_timeout(90)
                            after = await frame.evaluate(SHOT_JS, pid)
                            if before is not None and after is not None:
                                b = before.split(",") if before else []
                                a = after.split(",") if after else []
                                gained = sum(1 for x, y in zip(b, a)
                                             if x.endswith(":0") and y.endswith(":1"))
                                row["hover_reveal"] = gained > 0
                            await pg.mouse.move(0, 0)
                            await pg.wait_for_timeout(40)
                        except Exception:
                            pass
                        results[pid] = row
            finally:
                await ctx.close(); await factory.close_open_contexts()
        await browser.close()
    pathlib.Path(out_path).write_text(json.dumps(results, indent=1))
    print(f"observed {len(results)} probes -> {out_path}")

asyncio.run(main(sys.argv[1]))
