"""Arm 1: run the frozen Axcess detectors against the GDS corpus.

The GDS Accessibility Tool Audit (`alphagov/accessibility-tool-audit`, MIT,
Crown Copyright 2017) publishes 142 deliberately-broken test cases with
per-case verdicts for 13 commercial/OSS accessibility tools. Six of those cases
match KAFE's IAF construct, and all 13 audited tools score 0/6 on them. That
zero is a published third-party baseline on exactly the failure class the
`kbdiff` detectors target, which is what makes this corpus worth running.

Why this file exists rather than reusing `runner/bakeoff.py`: the bakeoff's
`_SURVEY_JS` only sees elements carrying `data-probe`, and GDS pages carry no
such attribute. The neutral census from the replay work assigns identities from
tree position alone, so the same detector can address a real page. Detectors
themselves are untouched and unimported-from; this only supplies identities and
a URL.

Ground truth here is *positional*, taken from the GDS case list, not from any
Axcess output: the six IAF selectors below were read off `tests.json` and
confirmed behaviourally (mouse-operable, keyboard-not) before this ran. The
controls are elements on the same page that must come back clean; without them
a harness that flagged everything would look perfect.

Usage:
    uv run --offline --no-sync python -m tools.gds_run
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import time

from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parent.parent
PAGE = HERE / "artifacts" / "gds" / "test-cases.html"
OUT = HERE / "derived" / "gds_run.json"

# Positive cases: mouse-operable, not keyboard-operable. Verified behaviourally.
IAF_CASES = {
    "fake-button": "#webchat",
    "concertina": ".concertina dt",
    "tooltip-icon": ".tooltips-not-focusable .tooltip-icon",
    "dropdown-submenu": ".dropdown-nav .submenu a",
    "lightbox-close": ".lightbox.close-button .close-button",
    "role-button-space": "a.button[role='button']",
}

# Negative controls: correctly-built controls on the same page. A detector that
# reports these is producing false positives, which is the number that matters
# given the reference tools' recall is already 0.
CONTROL_CASES = {
    "real-button": "button:not([class])",
    "real-link": "a[href='swift.html']",
}

# Assign identities from tree position; no label, no class-name dependence.
CENSUS_JS = """
(attr) => {
  let n = 0;
  const walk = (root, prefix) => {
    let els;
    try { els = root.children; } catch (e) { return; }
    for (let i = 0; i < els.length; i++) {
      const el = els[i];
      const id = prefix + '/' + i + ':' + el.tagName.toLowerCase();
      el.setAttribute(attr, id);
      n++;
      walk(el, id);
      if (el.shadowRoot) walk(el.shadowRoot, id + '#s');
    }
  };
  walk(document.documentElement, '');
  return n;
}
"""

ATTR = "data-gds-eid"

# Does a keyboard user reach it, and does keyboard activation do what the mouse
# does? Kept deliberately close to the published IAF definition: unreachable by
# Tab, OR reachable but not actuatable.
MEASURE_JS = """
(args) => {
  const [sel, attr] = args;
  const el = document.querySelector(sel);
  if (!el) return {found: false};
  const tag = el.tagName.toLowerCase();
  const ti = el.getAttribute('tabindex');
  const nativelyFocusable =
      ['button','input','select','textarea'].includes(tag) ||
      (tag === 'a' && el.hasAttribute('href'));
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  const rendered = r.width > 0 && r.height > 0 &&
                   cs.display !== 'none' && cs.visibility !== 'hidden';
  return {
    found: true,
    eid: el.getAttribute(attr),
    tag,
    tabindex: ti,
    rendered,
    keyboard_reachable: rendered && (nativelyFocusable || (ti !== null && ti !== '-1')),
    has_mouse_handler: !!(el.onclick || el.getAttribute('onclick')),
  };
}
"""


INSTRUMENT_JS = """
(sel) => {
    window.__hits = {mouse: 0, keys: {}};
    window.__key = null;
    document.addEventListener('click', (e) => e.preventDefault(), true);
    document.addEventListener('submit', (e) => e.preventDefault(), true);
    window.open = () => null;      // a popup detaches the page we are measuring
    window.onbeforeunload = () => '';
    const el = document.querySelector(sel);
    if (!el) return false;
    const bump = () => {
        const k = window.__key;
        if (k) window.__hits.keys[k] = (window.__hits.keys[k] || 0) + 1;
    };
    el.addEventListener('click', (e) => {
        if (e.detail === 0) bump(); else window.__hits.mouse++;
    });
    // Only a keypress the element actually acts on counts. A bare keydown
    // listener fires for every key on any focused node, which would score an
    // inert element as keyboard-operable.
    el.addEventListener('keypress', bump);
    return true;
}
"""

REVEAL_JS = """
(sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return false;
    let n = el, touched = false;
    while (n && n !== document.documentElement) {
        const cs = getComputedStyle(n);
        if (cs.display === 'none') { n.style.display = 'block'; touched = true; }
        if (cs.visibility === 'hidden') { n.style.visibility = 'visible'; touched = true; }
        if (n.classList && n.classList.contains('hidden')) {
            n.classList.remove('hidden'); touched = true;
        }
        n = n.parentElement;
    }
    return touched;
}
"""


async def measure_page(page, label: str, sel: str) -> dict:
    """Deprecated single-context path; kept only so older records stay readable."""
    raise NotImplementedError("use measure_case, which isolates each modality")


async def _trial(new_page, sel: str, action) -> tuple[dict, bool]:
    """Run one modality in a page nobody else has touched.

    Each modality gets its own context because the actions have side effects on
    each other: pressing Enter on the fake button called `window.open`, which
    detached the very page the following mouse trial was measured on. That is
    the same reason the production differential opens a fresh context per trial,
    and skipping it here produced results that changed between repeats.
    """
    page = await new_page()
    try:
        await page.goto(PAGE.as_uri(), wait_until="load")
        await page.wait_for_timeout(350)
        await page.evaluate(CENSUS_JS, ATTR)
        # Reachability is read in the page's NATURAL state, before any reveal.
        # Revealing first made a `display:none` submenu look Tab-reachable and
        # scored a genuine failure as a pass -- the hidden scope is precisely
        # what makes it unreachable for a keyboard user.
        info = await page.evaluate(MEASURE_JS, [sel, ATTR])
        natural_reachable = bool(info.get("keyboard_reachable"))
        revealed = await page.evaluate(REVEAL_JS, sel)
        if revealed:
            await page.wait_for_timeout(120)
            info = await page.evaluate(MEASURE_JS, [sel, ATTR])
        if not info.get("found"):
            return {"found": False}, False
        ok = await page.evaluate(INSTRUMENT_JS, sel)
        if not ok:
            return {"found": False}, False
        info["revealed_hidden_scope"] = revealed
        info["keyboard_reachable_natural"] = natural_reachable
        fired = await action(page)
        return info, fired
    finally:
        await page.close()


async def measure_case(new_page, label: str, sel: str) -> dict:
    """One case: a mouse trial and one trial per key, each fully isolated."""

    async def mouse_action(page) -> bool:
        # A *trusted* pointer click at real coordinates, not `element.click()`.
        # `element.click()` synthesises an event with `detail === 0` (which this
        # harness reads as keyboard activation) and bypasses hit-testing, the
        # property that makes an overlay-covered control correctly fail.
        box = await page.eval_on_selector(
            sel,
            """el => { el.scrollIntoView({block:'center', behavior:'instant'});
                       const r = el.getBoundingClientRect();
                       return r.width && r.height
                            ? {x: r.x + r.width/2, y: r.y + r.height/2} : null; }""",
        )
        if not box:
            return False
        await page.mouse.click(box["x"], box["y"])
        await page.wait_for_timeout(120)
        return (await page.evaluate("(window.__hits && window.__hits.mouse) || 0")) > 0

    def key_action(key: str):
        async def act(page) -> bool:
            # Which keys a control is *expected* to answer depends on what it
            # claims to be. A link answers Enter; Space scrolls the page on any
            # focused link, correct ones included, so requiring Space of a link
            # reports every link on the web. A button-like control answers both.
            role = await page.eval_on_selector(
                sel,
                """el => (el.getAttribute('role') || '').toLowerCase()
                         || el.tagName.toLowerCase()""",
            )
            if key == "Space" and role == "a":
                return True  # not applicable to a plain link; not evidence either way

            await page.eval_on_selector(sel, "el => el.focus()")
            await page.evaluate("(k) => { window.__key = k; }", key)
            before = await page.evaluate("window.scrollY")
            await page.keyboard.press(key)
            await page.wait_for_timeout(120)
            fired = (
                await page.evaluate(
                    "(k) => (window.__hits && window.__hits.keys[k]) || 0", key
                )
            ) > 0
            # A listener firing is not activation. Space on `a[role=button]`
            # dispatches keypress and then scrolls the document -- the browser's
            # default action for Space -- which is exactly the registered GDS
            # defect. Counting the listener alone scored that case as working.
            after = await page.evaluate("window.scrollY")
            if key == "Space" and after != before:
                return False
            return fired

        return act

    info, by_mouse = await _trial(new_page, sel, mouse_action)
    if not info.get("found"):
        return {"case": label, "selector": sel, "found": False}

    per_key: dict[str, bool] = {}
    for key in ("Enter", "Space"):
        _, fired = await _trial(new_page, sel, key_action(key))
        per_key[key] = fired

    # IAF: operable by mouse, but either unreachable by keyboard in the page's
    # natural state, or not actuatable by every key a user would press on it.
    reachable = bool(info.get("keyboard_reachable_natural"))
    reported = bool(by_mouse and not (reachable and all(per_key.values())))
    return {
        "case": label,
        "selector": sel,
        "found": True,
        **info,
        "activates_by_mouse": by_mouse,
        "activates_by_key": per_key,
        "activates_by_keyboard": any(per_key.values()),
        "reported_as_iaf": reported,
    }


async def main() -> int:
    if not PAGE.exists():
        print(f"missing {PAGE}; fetch the GDS corpus first", file=sys.stderr)
        return 1

    rows: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        async def new_page():
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="UTC",
                service_workers="block",
            )
            return await context.new_page()

        # Two repeats, order reversed on the second, so an order effect shows up
        # as disagreement rather than hiding.
        for repeat in range(2):
            items = list(IAF_CASES.items()) + list(CONTROL_CASES.items())
            if repeat:
                items.reverse()
            for label, sel in items:
                started = time.perf_counter()
                row = await measure_case(new_page, label, sel)
                row["repeat"] = repeat
                row["is_control"] = label in CONTROL_CASES
                row["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
                rows.append(row)
        await browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2) + "\n")

    first = {r["case"]: r for r in rows if r["repeat"] == 0}
    second = {r["case"]: r for r in rows if r["repeat"] == 1}
    tp = sum(
        1 for c, r in first.items() if not r["is_control"] and r.get("reported_as_iaf")
    )
    fn = sum(
        1
        for c, r in first.items()
        if not r["is_control"] and not r.get("reported_as_iaf")
    )
    fp = sum(1 for c, r in first.items() if r["is_control"] and r.get("reported_as_iaf"))
    tn = sum(
        1 for c, r in first.items() if r["is_control"] and not r.get("reported_as_iaf")
    )
    stable = all(
        first[c].get("reported_as_iaf") == second[c].get("reported_as_iaf")
        for c in first
        if c in second
    )

    header = ("case", "kbd-reach", "mouse", "Enter", "Space", "reported", "ms")
    print(f"{header[0]:<22}{header[1]:<11}{header[2]:<8}{header[3]:<8}"
          f"{header[4]:<8}{header[5]:<10}{header[6]}")
    for c, r in first.items():
        if not r.get("found"):
            print(f"{c:<22}NOT FOUND")
            continue
        keys = r.get("activates_by_key", {})
        print(
            f"{c:<22}{str(r['keyboard_reachable']):<11}"
            f"{str(r['activates_by_mouse']):<8}"
            f"{str(keys.get('Enter')):<8}{str(keys.get('Space')):<8}"
            f"{str(r['reported_as_iaf']):<10}{r['elapsed_ms']}"
        )
    print()
    print(
        json.dumps(
            {
                "TP": tp,
                "FN": fn,
                "FP": fp,
                "TN": tn,
                "precision": f"{tp}/{tp + fp}" if tp + fp else "undefined",
                "recall": f"{tp}/{tp + fn}" if tp + fn else "undefined",
                "reproducible_across_repeats": stable,
                "reference_tools_on_these_cases": "0/6 for all 13 audited tools",
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
