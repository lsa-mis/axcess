"""Measure the ARIA composite-widget shape for every probe.

A roving-tabindex composite (menubar, tablist, listbox, radiogroup, tree,
grid, toolbar) deliberately keeps exactly one child in the tab order and
moves focus between the rest with the arrow keys. That is the pattern the
ARIA Authoring Practices prescribe, so a `tabindex="-1"` child of such a
container is not evidence of a keyboard defect -- the container is the tab
stop. Pure attribute reading: no layout, no execution.

Also records `aria-keyshortcuts`, the declared-shortcut attribute, and
whether the accessible text advertises a chord such as "Alt+K".
"""
import asyncio, json, os, sys, pathlib, time
sys.path.insert(0, "src"); sys.path.insert(0, ".")
from playwright.async_api import async_playwright
from experiments.tabbing.runner.serve import ContextFactory, page_url
from experiments.tabbing.runner.bakeoff import VIEWPORT

JS = r"""
() => {
  const ITEM = new Set(['menuitem','menuitemcheckbox','menuitemradio','tab','option',
                        'radio','treeitem','gridcell','row','columnheader','rowheader']);
  const OWNER = new Set(['menubar','menu','tablist','listbox','radiogroup','tree',
                         'treegrid','grid','table','toolbar','group']);
  const CHORD = /\b(alt|ctrl|control|cmd|command|shift|meta)\s*[+\-]\s*\S/i;
  const out = {};
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) walk(el.shadowRoot);
      const id = el.getAttribute && el.getAttribute('data-probe');
      if (!id) continue;
      const role = (el.getAttribute('role') || '').toLowerCase();
      let owner = null, sibling_tabbable = false;
      if (ITEM.has(role)) {
        let p = el.parentElement;
        while (p) {
          const r = (p.getAttribute('role') || '').toLowerCase();
          if (OWNER.has(r)) { owner = r; break; }
          p = p.parentElement;
        }
        if (owner) {
          const scope = el.closest('[role="' + owner + '"]');
          for (const sib of scope.querySelectorAll('[role]')) {
            if (sib === el) continue;
            if (!ITEM.has((sib.getAttribute('role') || '').toLowerCase())) continue;
            const ti = sib.getAttribute('tabindex');
            if (ti !== null && parseInt(ti, 10) >= 0) { sibling_tabbable = true; break; }
          }
        }
      }
      const text = (el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '')
                 + ' ' + (el.getAttribute('title') || '');
      out[id] = {
        role, owner_role: owner, sibling_tabbable,
        own_tabindex: el.getAttribute('tabindex'),
        aria_keyshortcuts: el.getAttribute('aria-keyshortcuts'),
        chord_in_text: CHORD.test(text),
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
    # Only the observation is timed; see the note in probe_containment.py.
    observed_ms = 0.0
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
                        t0 = time.monotonic()
                        found = await frame.evaluate(JS)
                        observed_ms += (time.monotonic() - t0) * 1000
                        results.update(found)
                    except Exception:
                        pass
            finally:
                await ctx.close(); await factory.close_open_contexts()
        await browser.close()
    pathlib.Path(out_path).write_text(json.dumps(results, indent=1))
    pathlib.Path(str(out_path) + ".timing.json").write_text(
        json.dumps({"probe": "composite", "corpus": str(root),
                    "observation_ms": round(observed_ms, 1),
                    "pages": len(truth["pages"])}, indent=1) + "\n"
    )
    print(f"observed {len(results)} probes in {observed_ms:.1f} ms -> {out_path}")

asyncio.run(main(sys.argv[1]))
