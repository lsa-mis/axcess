"""Mutation benchmark: Ma11y's keyboard operators on the 53 replayed KAFE pages.

Ma11y (Tafreshipour et al., ISSTA 2024) injects a known accessibility fault
into a page. Three of its keyboard operators are local
(``literature-replication/arm2``); their transcriptions in
``tools/build_ma11y_corpus.py`` are applied here, at runtime, to real pages:

* F42: a link becomes ``<span onclick>`` (SC 2.1.1);
* F54: an inline ``onclick`` becomes ``onmousedown`` (SC 2.1.1/2.1.3);
* F55: a link gets ``onfocus="this.blur()"`` (SC 2.1.1);
* F44: every link in a list gets a positive tabindex, in reverse (SC 2.4.3);
* F78: a link that shows a focus outline gets ``outline: none !important``
  (SC 2.4.7).

F42, F54 and F55 are scored with the keyboard check; F44 and F78 with the
focus check. F44 and F78 are ported from upstream Ma11y
(``mahantaf/web-a11y-tool-analyzer``, MIT, ``src/mutant-generator``).

Targets follow Ma11y's ``applicable()`` rules (visible, inside the viewport,
not aria-hidden; F42 and F55 a link with text, F54 an ``[onclick]``), taking up
to the first ``PER_OPERATOR`` in document order rather than Ma11y's single
first. Each mutant gets a fresh page load. A detector scores a mutant when one
of its leads is on, or inside, the mutated element (``data-ma11y``). Leads on
the mutated page that the unmutated page did not have are counted as
collateral: the mutation should change nothing else.

    uv run python experiments/tabbing/ab/mutants.py --label NAME [--extended/--no-extended]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LITREP = REPO / "experiments" / "tabbing" / "literature-replication"
for extra in (REPO, REPO / "src", LITREP):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from playwright.async_api import async_playwright  # noqa: E402

from audit.analyzer.keyboard import KeyboardOperabilityProbe, KeyboardProbe  # noqa: E402

PER_OPERATOR = 3
OPERATORS = ("F42", "F54", "F55", "F44", "F78")
FOCUS_OPERATORS = {"F44": "focus-order-positive-tabindex", "F78": "focus-not-visible"}
OUT_DIR = Path(__file__).resolve().parent / "results"

# Ma11y's isVisibleAndAccessible, transcribed, plus its per-operator filter.
_TARGETS_JS = r"""
([op, cap]) => {
  const visible = (el) => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    if (el.getAttribute('aria-hidden') === 'true') return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    if (r.top < 0 || r.left < 0 || r.bottom > innerHeight || r.right > innerWidth) return false;
    for (let p = el.parentElement; p; p = p.parentElement) {
      const ps = getComputedStyle(p);
      if (ps.display === 'none' || ps.visibility === 'hidden' ||
          p.getAttribute('aria-hidden') === 'true') return false;
    }
    return true;
  };
  const pool = op === 'F54' ? document.querySelectorAll('[onclick]')
    : op === 'F44' ? Array.from(document.querySelectorAll('ul')).filter((ul) => {
        const items = ul.querySelectorAll('li');
        return items.length >= 2 && Array.from(items).every((li) => li.querySelector('a'));
      })
    : Array.from(document.querySelectorAll('a[href]')).filter((a) => {
        if (!a.textContent.trim()) return false;
        if (op !== 'F78') return true;
        // Ma11y's F78 applies to a link whose focused outline is not none.
        a.focus();
        const style = getComputedStyle(a).outlineStyle;
        a.blur();
        return style !== 'none';
      });
  const out = [];
  const all = Array.from(pool);
  for (let i = 0; i < all.length && out.length < cap; i++) if (visible(all[i])) out.push(i);
  return out;
}
"""

# The operators, from tools/build_ma11y_corpus.py, addressed by pool index.
_APPLY_JS = r"""
([op, index]) => {
  const pool = op === 'F54' ? Array.from(document.querySelectorAll('[onclick]'))
    : op === 'F44' ? Array.from(document.querySelectorAll('ul')).filter((ul) => {
        const items = ul.querySelectorAll('li');
        return items.length >= 2 && Array.from(items).every((li) => li.querySelector('a'));
      })
    : Array.from(document.querySelectorAll('a[href]')).filter((a) => {
        if (!a.textContent.trim()) return false;
        if (op !== 'F78') return true;
        a.focus();
        const style = getComputedStyle(a).outlineStyle;
        a.blur();
        return style !== 'none';
      });
  const el = pool[index];
  if (!el) return false;
  if (op === 'F42') {
    const span = document.createElement('span');
    for (const { name, value } of el.attributes) {
      if (name !== 'href') span.setAttribute(name, value);
      else span.setAttribute('onclick', `document.title='F42-activated'; window.location.href='${value}';`);
    }
    span.textContent = el.textContent;
    span.style.textDecoration = 'underline';
    span.style.cursor = 'pointer';
    span.style.color = 'blue';
    span.setAttribute('data-ma11y', 'F42');
    el.parentNode.replaceChild(span, el);
    return true;
  }
  if (op === 'F54') {
    // The marker makes "the mouse still works" observable, as the corpus
    // builder's F42 does with document.title.
    el.setAttribute('onmousedown', 'window.__ma11yF54 = 1;' + el.getAttribute('onclick'));
    el.removeAttribute('onclick');
    el.setAttribute('data-ma11y', 'F54');
    return true;
  }
  if (op === 'F44') {
    const items = Array.from(el.querySelectorAll('li'));
    let tabindex = items.length;
    for (const li of items) {
      li.querySelector('a').setAttribute('tabindex', String(tabindex));
      tabindex--;
    }
    el.setAttribute('data-ma11y', 'F44');
    return true;
  }
  if (op === 'F78') {
    const style = document.createElement('style');
    style.textContent = '.no_outline { outline: none !important; }';
    document.head.appendChild(style);
    el.classList.add('no_outline');
    el.setAttribute('data-ma11y', 'F78');
    return true;
  }
  el.setAttribute('onfocus', 'this.blur();');
  el.setAttribute('data-ma11y', 'F55');
  return true;
}
"""


# Ma11y's own verification step, cut down: the fault must be real on this
# page. A Content Security Policy that blocks inline handlers makes all three
# operators inert (the onfocus never blurs, the onclick never runs), and such
# a mutant is not a fault. Run after the detector, since F42's click navigates.
_VERIFY_JS = r"""
(op) => {
  const el = document.querySelector('[data-ma11y]');
  if (!el) return false;
  if (op === 'F44') return el.querySelectorAll('a[tabindex]').length >= 2;
  if (op === 'F78') return true; // checked from pixels, in Python
  if (op === 'F55') {
    el.focus();
    return document.activeElement !== el;
  }
  if (op === 'F54') {
    window.__ma11yF54 = 0;
    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    return window.__ma11yF54 === 1;
  }
  // F42's span must still be clickable: replacing a styled link can leave a
  // zero-size span no pointer can reach, which is no mouse-only control.
  const r = el.getBoundingClientRect();
  if (r.width < 1 || r.height < 1) return false;
  const before = document.title;
  window.addEventListener('beforeunload', (e) => { e.preventDefault(); }, { once: true });
  try { el.click(); } catch (e) {}
  return document.title === 'F42-activated' && before !== 'F42-activated';
}
"""


async def _open(browser, index, url):  # type: ignore[no-untyped-def]
    from tools import kafe_matrix, replay

    ctx = await browser.new_context(viewport=kafe_matrix.VIEWPORT, service_workers="block")
    await replay.ReplayRouter(index).attach(ctx)
    page = await ctx.new_page()
    await page.goto(url, wait_until="load", timeout=60_000)
    await page.wait_for_timeout(3000)
    return ctx, page


async def _leads(page, extended: bool):  # type: ignore[no-untyped-def]
    await KeyboardProbe().run(page)
    result = await KeyboardOperabilityProbe(extended=extended, annotate_attr="data-ma11y").analyze(
        page
    )
    return [lead for lead in result.leads if lead.verdict != "dismissed"], result.drops


async def _pixels_change_on_focus(page) -> int:  # type: ignore[no-untyped-def]
    """Changed pixels around the mutated link when it is focused (F78's check)."""
    import io

    from PIL import Image, ImageChops

    loc = page.locator("[data-ma11y]").first
    await loc.scroll_into_view_if_needed(timeout=2000)
    box = await loc.bounding_box()
    clip = {
        "x": max(box["x"] - 10, 0),
        "y": max(box["y"] - 10, 0),
        "width": box["width"] + 20,
        "height": box["height"] + 20,
    }
    await page.keyboard.press("Shift")
    a = await page.screenshot(clip=clip)
    await loc.focus()
    await page.wait_for_timeout(400)
    b = await page.screenshot(clip=clip)
    await loc.evaluate("e => e.blur()")
    # In colour: a change of hue can keep the same grey level, so a greyscale
    # comparison would call a colour-only focus style invisible.
    ia, ib = (Image.open(io.BytesIO(x)).convert("RGB") for x in (a, b))
    return sum(
        1 for px in ImageChops.difference(ia, ib).get_flattened_data() if max(px) > 24
    )


async def _focus_row(page, name: str, op: str, i: int, html: str) -> dict:  # type: ignore[no-untyped-def]
    """Score F44/F78 with the focus check; F78 is valid only if no pixel changes."""
    from audit.analyzer.focus import FocusProbe

    valid = True
    if op == "F78":
        valid = await _pixels_change_on_focus(page) == 0
    findings = [f for f in await FocusProbe().run(page) if f.rule_id == FOCUS_OPERATORS[op]]
    hit = False
    for f in findings:
        inside = await page.evaluate(
            "(sel) => { try { return [...document.querySelectorAll(sel)].some("
            "(el) => !!el.closest('[data-ma11y]')); } catch (e) { return false; } }",
            f.target_selector,
        )
        hit = hit or bool(inside)
    return {
        "s": name,
        "op": op,
        "index": i,
        "html": html[:200],
        "valid": valid,
        "detected": hit,
        "kinds": [FOCUS_OPERATORS[op]] if hit else [],
        "signals": [],
        "dropped": [],
        "collateral": [],
        "ms": 0,
    }


async def subject(browser, name: str, extended: bool, ops) -> list[dict]:  # type: ignore[no-untyped-def]
    from tools import flowfile, kafe_matrix

    index = flowfile.load_exchanges(kafe_matrix.capture_path(name).read_bytes())
    url = kafe_matrix.entry_url(index)
    rows: list[dict] = []
    ctx, page = await _open(browser, index, url)
    try:
        base = {lead.selector for lead in (await _leads(page, extended))[0]}
        targets = {op: await page.evaluate(_TARGETS_JS, [op, PER_OPERATOR]) for op in ops}
    finally:
        await ctx.close()
    for op, indexes in targets.items():
        for i in indexes:
            ctx, page = await _open(browser, index, url)
            try:
                if not await page.evaluate(_APPLY_JS, [op, i]):
                    continue
                html = await page.evaluate(
                    "() => (document.querySelector('[data-ma11y]') || {}).outerHTML || ''"
                )
                t = time.perf_counter()
                if op in FOCUS_OPERATORS:
                    rows.append(await _focus_row(page, name, op, i, html))
                    continue
                leads, drops = await _leads(page, extended)
                hit = [lead for lead in leads if lead.probe == op or lead.also_probe == op]
                valid = False
                with contextlib.suppress(Exception):
                    valid = bool(await page.evaluate(_VERIFY_JS, op))
                rows.append(
                    {
                        "s": name,
                        "op": op,
                        "index": i,
                        "html": html[:200],
                        "valid": valid,
                        "detected": bool(hit),
                        "kinds": sorted({lead.kind for lead in hit}),
                        "signals": sorted({s for lead in hit for s in lead.signals}),
                        # Why the mutant was not a lead, when it was a candidate.
                        "dropped": sorted({d["why"] for d in drops if d.get("probe") == op}),
                        "collateral": sorted(
                            {
                                lead.selector
                                for lead in leads
                                if lead not in hit and lead.selector not in base
                            }
                        )[:5],
                        "ms": round((time.perf_counter() - t) * 1000),
                    }
                )
            except Exception as exc:
                rows.append({"s": name, "op": op, "index": i, "err": str(exc)[:120]})
            finally:
                await ctx.close()
    return rows


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--extended", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--ops", nargs="*", default=list(OPERATORS))
    args = parser.parse_args()
    out = OUT_DIR / f"mutants-{args.label}.jsonl"
    if out.exists():
        raise SystemExit(f"{out} exists; pick a new --label")
    names = args.only or [
        json.loads(line)["subject"] for line in (LITREP / "derived" / "kafe_matrix.jsonl").open()
    ]
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        with out.open("w") as fh:
            for name in names:
                try:
                    rows = await subject(browser, name, args.extended, args.ops)
                except Exception as exc:
                    rows = [{"s": name, "err": f"subject: {exc}"[:160]}]
                for row in rows:
                    fh.write(json.dumps(row) + "\n")
                fh.flush()
                valid = [r for r in rows if r.get("valid")]
                print(
                    name,
                    sum(r["detected"] for r in valid),
                    "/",
                    len(valid),
                    "valid mutants",
                    flush=True,
                )
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
