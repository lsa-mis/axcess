"""Diagnostic: why does `kafe_matrix capdiag` record `distinct_stops: 0`?

Throwaway instrument for the capdiag investigation. It does not write any
published artefact. Two modes.

`compare` (default) — for one subject it runs the tab walk twice:

* **arm A** — exactly what `cap_diagnosis()` does today: a context built with
  ``ReplayFactory(..., allow=[])``, so no element ever receives ``data-probe``.
* **arm B** — what the scored path (`measure_subject`) does: a discovery pass
  that censuses the document and lets the frozen candidate collector choose
  ``probe_ids``, then a fresh context built with ``allow=probe_ids``.

Both arms also replay the walk locally with the *same* JS the frozen walker
uses, so the raw marker sequence is visible. That is what separates "focus never
moved" from "focus moved but nothing it landed on was named".

`loop` — walks the tagged page and describes the elements the walk ends up
cycling between, plus what the replay router served and denied. `capdiag`'s
verdict names the loop by marker only; this says what those markers *are*, which
is what decides whether a loop is the page's own behaviour or an artefact of
replaying it offline.

Usage:
    uv run --offline --no-sync python -u -m tools.capdiag_probe spotify --ceiling 400
    uv run --offline --no-sync python -u -m tools.capdiag_probe spotify --mode loop
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright
from tools import flowfile, replay

# `kafe_matrix` puts the repository and `src` on `sys.path` as a side effect of
# import, so it has to come before the `audit.*` import below.
from tools.kafe_matrix import (
    DISCOVERY_TAG_JS,
    FRAMED_CENSUS_JS,
    ReplayFactory,
    capture_path,
    collect_candidates,
    entry_url,
    terminal_period,
)

from audit.analyzer.keyboard.kbdiff.taborder import (
    _ACTIVE_PROBE_JS,
    _active_marker,
    compute_tab_order,
)


async def raw_walk(page, budget: int) -> dict:
    """The frozen walk's loop, re-run only to expose the marker sequence."""
    seen: list[str] = []
    named = 0
    for _ in range(budget):
        await page.keyboard.press("Tab")
        marker = await page.evaluate(_ACTIVE_PROBE_JS)
        if marker is None:
            seen.append("<null: focus left the document>")
            break
        if not marker.startswith("#el:"):
            named += 1
        seen.append(marker)
        if len(seen) > 1 and seen[-1] == seen[0]:
            break
    return {
        "presses": len(seen),
        "distinct_markers": len(set(seen)),
        "named_markers": named,
        "first_12": seen[:12],
    }


async def arm(browser, subject: str, ceiling: int, tagged: bool) -> dict:
    index = flowfile.load_exchanges(capture_path(subject).read_bytes())
    url = entry_url(index)
    router = replay.ReplayRouter(index)
    probe_ids: list[str] = []

    if tagged:
        discovery = ReplayFactory(browser, router, allow=None)
        context = await discovery()
        await context.add_init_script(
            f"""
            window.addEventListener('load', () => {{
                ({FRAMED_CENSUS_JS})('{replay.CENSUS_ATTR}');
                for (const el of document.querySelectorAll('[{replay.CENSUS_ATTR}]')) {{
                    el.setAttribute('data-probe',
                                    el.getAttribute('{replay.CENSUS_ATTR}'));
                }}
            }});
            """
        )
        page = await context.new_page()
        await page.goto(url, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(3_000)
        probe_ids = sorted({c.probe_id for c in await collect_candidates(page) if c.probe_id})
        await context.close()

    factory = ReplayFactory(browser, router, allow=probe_ids if tagged else [])

    # The frozen walker, on its own freshly navigated page.
    context = await factory()
    page = await context.new_page()
    await page.goto(url, wait_until="load", timeout=60_000)
    await page.wait_for_timeout(1_000)
    tags = await page.evaluate("() => document.querySelectorAll('[data-probe]').length")
    order = await compute_tab_order(page, max_tabs=ceiling)
    await context.close()

    # A second fresh page for the raw sequence: `compute_tab_order` requires an
    # unfocused page, so the two cannot share one.
    context = await factory()
    page = await context.new_page()
    await page.goto(url, wait_until="load", timeout=60_000)
    await page.wait_for_timeout(1_000)
    raw = await raw_walk(page, min(ceiling, 60))
    await context.close()

    return {
        "probe_ids": len(probe_ids),
        "data_probe_in_walk_context": tags,
        "frozen_index_size": len(order.index),
        "frozen_capped": order.capped,
        "frozen_presses": order.presses,
        "raw": raw,
    }


DESCRIBE_ACTIVE_JS = """
() => {
  const el = document.activeElement;
  if (!el) return null;
  const attrs = {};
  for (const name of ['id', 'class', 'src', 'title', 'tabindex', 'aria-hidden', 'name'])
    if (el.hasAttribute && el.hasAttribute(name)) attrs[name] = el.getAttribute(name);
  const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
  let index = -1;
  const all = document.querySelectorAll('*');
  for (let i = 0; i < all.length; i++) if (all[i] === el) { index = i; break; }
  return {
    tag: el.tagName ? el.tagName.toLowerCase() : 'unknown',
    document_index: index,
    // The discriminator that matters: `document.activeElement` falls back to
    // <body> when nothing in the document is focused, so a body marker alone
    // cannot tell "Tab landed on the body" from "focus left the page".
    document_has_focus: document.hasFocus(),
    attrs,
    rect: rect ? {w: Math.round(rect.width), h: Math.round(rect.height)} : null,
    frames_in_document: document.querySelectorAll('iframe').length,
  };
}
"""


async def loop_mode(browser, subject: str, ceiling: int) -> dict:
    """Walk the tagged page and describe the elements it ends up cycling between."""
    index = flowfile.load_exchanges(capture_path(subject).read_bytes())
    url = entry_url(index)
    router = replay.ReplayRouter(index)

    discovery = ReplayFactory(browser, router, allow=None)
    context = await discovery()
    await context.add_init_script(DISCOVERY_TAG_JS)
    page = await context.new_page()
    await page.goto(url, wait_until="load", timeout=60_000)
    await page.wait_for_timeout(3_000)
    probe_ids = sorted({c.probe_id for c in await collect_candidates(page) if c.probe_id})
    await context.close()

    factory = ReplayFactory(browser, router, allow=probe_ids)
    context = await factory()
    page = await context.new_page()
    await page.goto(url, wait_until="load", timeout=60_000)
    await page.wait_for_timeout(1_000)

    sequence: list[str] = []
    described: dict[str, Any] = {}
    for _ in range(ceiling):
        await page.keyboard.press("Tab")
        marker = await _active_marker(page)
        if marker is None:
            sequence.append("<null>")
            break
        sequence.append(marker)
        if marker not in described:
            described[marker] = await page.evaluate(DESCRIBE_ACTIVE_JS)
        if len(sequence) > 1 and sequence[-1] == sequence[0]:
            break

    period = terminal_period(sequence)
    out = {
        "subject": subject,
        "presses": len(sequence),
        "probe_ids": len(probe_ids),
        "distinct_positions": len(set(sequence)),
        "terminal_loop_period": period,
        "terminal_loop": [
            {"marker": m, **(described.get(m) or {})}
            for m in (sequence[-period:] if period else [])
        ],
        "router": {
            "served": router.served,
            "denied": router.denied,
            "functionally_degraded": router.is_functionally_degraded(),
        },
    }
    await context.close()
    return out


async def main_async(subject: str, ceiling: int, mode: str) -> int:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            if mode == "loop":
                out: dict[str, Any] = await loop_mode(browser, subject, ceiling)
            else:
                out = {
                    "subject": subject,
                    "ceiling": ceiling,
                    "A_untagged_as_capdiag_does": await arm(browser, subject, ceiling, False),
                    "B_tagged_as_scored_run_does": await arm(browser, subject, ceiling, True),
                }
        finally:
            await browser.close()
    print(json.dumps(out, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subject")
    parser.add_argument("--ceiling", type=int, default=400)
    parser.add_argument("--mode", choices=("compare", "loop"), default="compare")
    args = parser.parse_args()
    return asyncio.run(main_async(args.subject, args.ceiling, args.mode))


if __name__ == "__main__":
    raise SystemExit(main())
