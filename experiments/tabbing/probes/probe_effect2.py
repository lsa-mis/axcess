"""Four further observations aimed at the errors C12 still makes.

C12's four remaining false alarms and its one miss all share a shape that
static inspection cannot reach: a handler is registered but does nothing
useful (`h123`, `p22`, `p55`), a separate control already does the job
(`h140`), or a key handler exists but does something *different* from the
click (`h102`). Three of those need the page to run; one does not.

  name_twin      a visible, Tab-reachable native control on the page carries
                 the same accessible name -- the `h140` shape.
  framework_act  the element has framework (React) props but no activation
                 prop among them, so a root delegation listener is not
                 evidence about *this* element -- the `p55` shape.
  click_effect   dispatching a real click changes the rendered document.
  key_effect     focusing and pressing Enter, then Space, changes it.
  same_effect    the two changes are equal.

Each target gets its own freshly navigated page, so one probe's side effects
cannot leak into the next. That is the cost of asking what code *does*.
"""
import asyncio, json, os, sys, pathlib, time
sys.path.insert(0, "src"); sys.path.insert(0, ".")
from playwright.async_api import async_playwright
from experiments.tabbing.runner.serve import ContextFactory, page_url
from experiments.tabbing.runner.bakeoff import VIEWPORT

NATIVE = "a[href], button, input, select, textarea, summary"

IDS_JS = """
() => { const o=[]; const w=r=>{ for(const e of r.querySelectorAll('*')){
  if(e.shadowRoot) w(e.shadowRoot);
  const i=e.getAttribute&&e.getAttribute('data-probe'); if(i) o.push(i); } };
  w(document); return o; }
"""

# Static: same accessible name as a Tab-reachable native control; framework props.
STATIC_JS = r"""
(native) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const name = el => norm(el.getAttribute('aria-label') || el.getAttribute('title')
                          || el.value || el.textContent);
  const tabbable = el => {
    if (el.disabled) return false;
    const t = el.getAttribute('tabindex');
    if (t !== null && parseInt(t, 10) < 0) return false;
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const twins = new Set();
  for (const el of document.querySelectorAll(native)) if (tabbable(el)) twins.add(name(el));
  const actProps = /^on(Click|MouseDown|MouseUp|PointerDown|PointerUp|KeyDown|KeyUp|KeyPress)$/;
  const out = {};
  const walk = r => { for (const el of r.querySelectorAll('*')) {
    if (el.shadowRoot) walk(el.shadowRoot);
    const id = el.getAttribute && el.getAttribute('data-probe'); if (!id) continue;
    const n = name(el);
    let fiber = null, hasAct = null;
    for (const k of Object.keys(el)) {
      if (!k.startsWith('__reactProps$') && !k.startsWith('__reactFiber$')) continue;
      const props = k.startsWith('__reactProps$') ? el[k] : (el[k] && el[k].memoizedProps);
      if (!props) continue;
      fiber = true;
      hasAct = Object.keys(props).some(p => actProps.test(p));
      if (hasAct) break;
    }
    out[id] = { name: n, name_twin: n.length > 0 && twins.has(n),
                framework: fiber, framework_activation: hasAct };
  } };
  walk(document); return out;
}
"""

# A digest of everything a user could notice: rendered text and rendered-ness.
DIGEST_JS = r"""
() => {
  // Pierces shadow roots: a control whose only effect is inside a shadow tree
  // is still an effect, and reading only the light DOM scores it as dead.
  const parts = [], text = [];
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      const shown = r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
      parts.push(shown ? '1' : '0');
      if (el.shadowRoot) walk(el.shadowRoot);
      for (const n of el.childNodes)
        if (n.nodeType === 3 && n.nodeValue.trim()) text.push(n.nodeValue.replace(/\s+/g, ' ').trim());
    }
  };
  walk(document);
  // Side channels. A control whose whole job is fetch(), localStorage, canvas
  // or console is still a control; e-nodom.html is built to catch a DOM-only
  // oracle calling all five of them dead.
  const store = [];
  for (const s of [localStorage, sessionStorage]) {
    try { for (let i = 0; i < s.length; i++) store.push(s.key(i) + '=' + s.getItem(s.key(i))); }
    catch (e) { store.push('?'); }
  }
  const canvases = [];
  for (const c of document.querySelectorAll('canvas')) {
    try { canvases.push(c.toDataURL().length + ':' + c.toDataURL().slice(-64)); }
    catch (e) { canvases.push('?'); }
  }
  return parts.join('') + '|' + text.join('\u0001') + '|' + location.hash
         + '|' + store.sort().join(';') + '|' + canvases.join(';');
}
"""

FIND_JS = """
(id) => { const f=r=>{ const d=r.querySelector('[data-probe="'+id+'"]'); if(d) return d;
  for(const e of r.querySelectorAll('*')) if(e.shadowRoot){const h=f(e.shadowRoot); if(h) return h;}
  return null; }; const el=f(document); if(!el) return false;
  el.focus({preventScroll:true}); return document.activeElement === el
    || (el.getRootNode().activeElement === el); }
"""


SETTLE_MS, SETTLE_STEP = 900, 60


async def settle(pg, before):
    """Poll until the page changes, or the budget runs out.

    A control that does something resolves in one step; only a genuinely dead
    one pays the full wait. `h180` defers its effect by 700 ms, so a fixed
    short wait scores it as dead.
    """
    waited = 0
    while waited < SETTLE_MS:
        await pg.wait_for_timeout(SETTLE_STEP)
        waited += SETTLE_STEP
        now = await digest_all(pg)
        if now != before:
            return now
    return await digest_all(pg)


async def digest_all(pg):
    """Every frame's digest, so an effect in a child document still counts."""
    out = []
    for frame in pg.frames:
        try:
            out.append(await frame.evaluate(DIGEST_JS))
        except Exception:
            out.append("?")
    return "\u0002".join(out)


async def observe(factory, page_path, all_ids, probe_ids):
    """Static facts for every target on the page; effects only for probe_ids."""
    out = {}
    ctx = await factory()
    try:
        pg = await ctx.new_page()
        await pg.goto(page_url(page_path), wait_until="load")
        await pg.wait_for_timeout(120)
        statics = {}
        for frame in pg.frames:
            try:
                statics.update(await frame.evaluate(STATIC_JS, NATIVE))
            except Exception:
                pass
    finally:
        await ctx.close()
        await factory.close_open_contexts()
    for pid in all_ids:
        out[pid] = dict(statics.get(pid, {}))
        out[pid].update(click_effect=None, key_effect=None, same_effect=None)
    if not probe_ids:
        return out

    for pid in probe_ids:
        row = out[pid]
        t0 = time.monotonic()
        for mode in ("click", "key"):
            if mode == "key" and row.get("click_effect") is not True:
                continue  # nothing happened on click; there is no difference to find
            ctx = await factory()
            try:
                pg = await ctx.new_page()
                console_seen, net_seen = [], []
                pg.on("console", lambda m: console_seen.append(1))
                pg.on("request", lambda r: net_seen.append(1))
                await pg.goto(page_url(page_path), wait_until="load")
                await pg.wait_for_timeout(100)
                frame = None
                for candidate in pg.frames:
                    if await candidate.locator(f'[data-probe="{pid}"]').count():
                        frame = candidate
                        break
                if frame is None:
                    continue
                before = await digest_all(pg)
                console_mark, net_mark = len(console_seen), len(net_seen)
                if mode == "click":
                    try:
                        await frame.locator(f'[data-probe="{pid}"]').first.click(
                            timeout=1200, force=True)
                    except Exception:
                        continue
                else:
                    if not await frame.evaluate(FIND_JS, pid):
                        continue  # cannot focus it, so no key verdict is available
                    await pg.keyboard.press("Enter")
                    await pg.wait_for_timeout(60)
                    await pg.keyboard.press(" ")
                after = await settle(pg, before)
                chatter = len(console_seen) > console_mark or len(net_seen) > net_mark
                row[f"{mode}_effect"] = after != before or chatter
                row[f"{mode}_digest"] = after + ("|chatter" if chatter else "")
            except Exception:
                pass
            finally:
                await ctx.close()
                await factory.close_open_contexts()
        row["ms"] = round((time.monotonic() - t0) * 1000, 1)
        if row.get("click_effect") and row.get("key_effect"):
            row["same_effect"] = row.get("click_digest") == row.get("key_digest")
        row.pop("click_digest", None)
        row.pop("key_digest", None)
    return out


async def main(out_path, only_path):
    # Corpus root is overridable so this probe can observe a corpus other than
    # the fixtures it was written against. The other three probe scripts
    # already read PROBE_CORPUS; this one did not, which left C10-C16
    # unbuildable anywhere else. Default is unchanged, so existing invocations
    # and the published fixtures numbers are unaffected.
    root = pathlib.Path(os.environ.get("PROBE_CORPUS", "experiments/tabbing/fixtures"))
    truth = json.loads((root / "truth.json").read_text())
    only = set(json.loads(pathlib.Path(only_path).read_text())) if only_path else None
    results, started = {}, time.monotonic()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        factory = ContextFactory(browser, VIEWPORT, root)
        for page_path, ids in sorted(truth["pages"].items()):
            wanted = [p for p in ids if only is None or p in only]
            results.update(await observe(factory, page_path, list(ids), wanted))
        await browser.close()
    pathlib.Path(out_path).write_text(json.dumps(results, indent=1))
    # Which lead set was actually observed is the whole scope caveat on C16: R9
    # can only promote what it looked at. Recorded beside the observations so a
    # scorer states the lead set rather than inferring it.
    observed = [p for p, row in results.items() if row.get("ms")]
    pathlib.Path(str(out_path) + ".timing.json").write_text(
        json.dumps({"probe": "effect2", "corpus": str(root),
                    "observation_ms": round(sum(results[p]["ms"] for p in observed), 1),
                    "lead_set": pathlib.Path(only_path).name if only_path else "all probes",
                    "observed": len(observed), "universe": len(results),
                    "pages": len(truth["pages"])}, indent=1) + "\n"
    )
    print(f"observed {len(observed)}/{len(results)} probes in "
          f"{time.monotonic()-started:.1f}s -> {out_path}")

asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
