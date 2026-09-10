"""The twelve detectors, reimplemented in Python for a like-for-like bake-off.

Upstream scored twelve ways of finding "mouse-operable but not keyboard-operable"
elements and published the table. This reimplements all twelve so we can put our
own oracle beside them on identical pages, and so the cheap detectors can be
measured on edge cases upstream's corpus does not contain.

| id   | detector                          | what it asks |
|------|-----------------------------------|--------------|
| D0   | axcess's own clickable collector  | what this repo ships today |
| D1   | axe-core                          | does a general scanner see it at all |
| D2   | inline ``onclick=`` attribute     | is a handler visible in the markup |
| D2b  | ``el.onclick`` **property**       | is a handler assigned to the property |
| D3   | tabindex / ARIA structure         | does it claim to be interactive |
| D4   | CSS ``cursor`` + class lexicon    | does it *look* clickable |
| D5   | CDP ``getEventListeners``         | is a listener actually bound to it |
| D6   | ``addEventListener`` shim         | was a listener registered after load |
| D7   | React fiber props                 | did a framework bind a handler |
| D8   | hover-diff                        | does hovering change the rendering |
| D9   | behavioural differential          | does the mouse do something the keyboard cannot |
| D10  | V8 coverage differential          | did the mouse run code the keyboard did not |

**The subtraction is deliberate and is itself a finding.** D0 and D2-D8 are
candidate *generators*: they answer "does this look interactive", not "is it
broken". Upstream converted each into a detector by reporting ``candidates - T``
— everything proposed that is not in the tab order. That convention is
reproduced faithfully here, because changing it would make our numbers
incomparable to theirs. It also has a permanent hole, which the scoring makes
visible: an element that *is* in the tab order but does nothing when you press a
key is removed by the subtraction no matter which generator proposed it.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import CDPSession, Page

from audit.analyzer.keyboard.kbdiff.taborder import TabOrder
from audit.logging import get_logger

log = get_logger(__name__)

# axe.min.js already ships in this repo for the workbench's own baseline scan.
AXE_BUNDLE = Path(__file__).resolve().parents[3] / "web" / "static" / "axe.min.js"

# The WCAG tag set upstream scored D1 against.
AXE_TAGS = ("wcag2a", "wcag2aa", "wcag21aa")


@dataclass(frozen=True)
class DetectorResult:
    """One detector's raw output on one page."""

    detector: str
    proposed: set[str]  # probe ids the detector surfaced, before subtraction
    ms: float = 0.0
    note: str | None = None

    def reported(self, order: TabOrder) -> set[str]:
        """``candidates - T``: upstream's convention for turning a generator into
        a detector. Kept identical so the comparison means something."""
        return {pid for pid in self.proposed if not order.contains(pid)}


# --------------------------------------------------------------------------
# Shared JS
# --------------------------------------------------------------------------

# Walks the document and every open shadow root, returning one record per
# element carrying a data-probe, with everything the cheap detectors need. One
# round trip rather than twelve.
_SURVEY_JS = """
(lexicon) => {
  const out = [];
  const scan = (root) => {
    let els;
    try { els = root.querySelectorAll('*'); } catch (e) { return; }
    for (const el of els) {
      if (el.shadowRoot) scan(el.shadowRoot);
      const probe = el.getAttribute && el.getAttribute('data-probe');
      if (!probe) continue;

      let cursor = '', cls = '';
      try { cursor = getComputedStyle(el).cursor; } catch (e) {}
      try {
        const raw = el.className;
        cls = (raw && typeof raw === 'string') ? raw.toLowerCase() : '';
      } catch (e) {}

      let onclickProp = false;
      try { onclickProp = typeof el.onclick === 'function'; } catch (e) {}

      // React attaches props under a __reactProps$<hash> key on the DOM node.
      let reactHandler = false;
      try {
        for (const k of Object.keys(el)) {
          if (k.startsWith('__reactProps$')) {
            const p = el[k];
            if (p && typeof p.onClick === 'function') { reactHandler = true; break; }
          }
        }
      } catch (e) {}

      const role = el.getAttribute('role') || '';
      out.push({
        probe,
        tag: el.tagName.toLowerCase(),
        onclickAttr: el.hasAttribute('onclick'),
        onclickProp,
        reactHandler,
        cursorPointer: cursor === 'pointer',
        lexicon: !!cls && lexicon.some(w => cls.includes(w)),
        role,
        hasTabindex: el.hasAttribute('tabindex'),
        tabindex: el.getAttribute('tabindex'),
        nativeInteractive: ['a','button','input','select','textarea','summary','details']
          .includes(el.tagName.toLowerCase()),
        ariaInteractive: ['button','link','menuitem','tab','checkbox','switch','option']
          .includes(role),
        hasHref: el.hasAttribute('href'),
      });
    }
  };
  scan(document);
  return out;
}
"""

CLICKABLE_LEXICON = (
    "btn",
    "button",
    "click",
    "card",
    "tile",
    "toggle",
    "menu",
    "nav-item",
    "dropdown",
    "accordion",
    "tab",
    "close",
    "expand",
    "collapse",
    "select",
)

# D6: records every addEventListener registration, with the stack that made it.
# Installed at document-start. Upstream measured this as the weakest of the three
# listener routes (65.4% recall) but noted its real value is the stack trace,
# which is the one thing here no other detector produces.
LISTENER_SHIM_JS = """
(() => {
  if (window.__kbShim) return;
  const seen = [];
  window.__kbShim = seen;
  const orig = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type, fn, opts) {
    try {
      if (type === 'click' || type === 'mousedown' || type === 'mouseup') {
        const stack = (new Error()).stack || '';
        seen.push({
          type,
          probe: (this && this.getAttribute) ? this.getAttribute('data-probe') : null,
          isDocument: this === document || this === window,
          tag: (this && this.tagName) ? this.tagName.toLowerCase() : String(this),
          stack: stack.split('\\n').slice(1, 3).join(' | ').slice(0, 200),
        });
      }
    } catch (e) {}
    return orig.call(this, type, fn, opts);
  };
})();
"""


async def survey(page: Page) -> list[dict[str, Any]]:
    """One pass collecting every cheap signal for every probe on the page."""
    result: list[dict[str, Any]] = await page.evaluate(_SURVEY_JS, list(CLICKABLE_LEXICON))
    return result


# --------------------------------------------------------------------------
# D0-D4, D7: pure survey detectors
# --------------------------------------------------------------------------


def d0_axcess_clickables(rows: list[dict[str, Any]]) -> DetectorResult:
    """What axcess ships today, as an equivalent of upstream's ``collectClickables``.

    Mirrors the interaction probe's control selector: native interactive tags,
    interactive ARIA roles, ``[onclick]``, ``summary``, ``[aria-expanded]``,
    gated on ``cursor: pointer``. It was written to find things worth clicking
    during a crawl, not to find keyboard defects, and is measured out of scope —
    same caveat upstream attached to their own D0.
    """
    proposed = {
        r["probe"]
        for r in rows
        if (r["nativeInteractive"] or r["ariaInteractive"] or r["onclickAttr"])
        and r["cursorPointer"]
    }
    return DetectorResult("D0 axcess collectClickables", proposed)


def d2_inline_attribute(rows: list[dict[str, Any]]) -> DetectorResult:
    """HTML_CodeSniffer-style: only what is written in the markup.

    Upstream measured 3.8% recall — one probe in twenty-six — at 100% precision.
    Almost nothing carries an inline handler any more; what does is certain.
    """
    return DetectorResult(
        "D2 inline onclick attribute", {r["probe"] for r in rows if r["onclickAttr"]}
    )


def d2b_handler_property(rows: list[dict[str, Any]]) -> DetectorResult:
    """``typeof el.onclick === 'function'``.

    Upstream's own correction to their survey: React 19 assigns this property
    directly, so three lines of stable web-platform code find React handlers and
    a version-fragile fiber adapter is unnecessary.
    """
    return DetectorResult("D2b onclick property", {r["probe"] for r in rows if r["onclickProp"]})


def d3_tabindex_aria(rows: list[dict[str, Any]]) -> DetectorResult:
    """Structural claim of interactivity without native semantics.

    An element that says ``role="button"`` or carries a ``tabindex`` is asserting
    it is a control; if it is not natively one, that assertion is worth checking.
    """
    proposed = {
        r["probe"]
        for r in rows
        if (r["ariaInteractive"] or r["hasTabindex"]) and not r["nativeInteractive"]
    }
    return DetectorResult("D3 tabindex / ARIA", proposed)


def d4_css_lexical(rows: list[dict[str, Any]]) -> DetectorResult:
    """Does it *look* clickable: ``cursor: pointer`` or a button-ish class name.

    Upstream's best cheap route for recall (84.6%) and its worst for precision
    (71.0%). It cannot tell a handler from a hover style, which is exactly what
    the decoys in this corpus are built from.
    """
    proposed = {
        r["probe"]
        for r in rows
        if (r["cursorPointer"] or r["lexicon"]) and not r["nativeInteractive"]
    }
    return DetectorResult("D4 CSS + lexical", proposed)


def d7_react_props(rows: list[dict[str, Any]]) -> DetectorResult:
    """Framework-prop extraction: ``__reactProps$*.onClick``.

    Returns nothing on a page with no React, which is a real result and not an
    error — it is the shape of upstream's 7.7% recall. The only thing this route
    uniquely answers is *which prop* was bound, not *whether* one exists.
    """
    proposed = {r["probe"] for r in rows if r["reactHandler"]}
    note = None if proposed else "no React on this page"
    return DetectorResult("D7 React fiber props", proposed, note=note)


# --------------------------------------------------------------------------
# D5, D6: listener routes
# --------------------------------------------------------------------------


async def d5_cdp_listeners(page: Page, cdp: CDPSession, probe_ids: list[str]) -> DetectorResult:
    """CDP ``DOMDebugger.getEventListeners``, the authoritative listener route.

    Sees listeners bound directly to an element, including inside closed shadow
    roots — the capability our Playwright-only locator lacks. Blind to
    delegation, because a listener on ``document`` is not bound to the element.
    """
    proposed: set[str] = set()
    for probe_id in probe_ids:
        try:
            handle = await cdp.send(
                "Runtime.evaluate",
                {
                    "expression": (
                        "(() => { const find = (root) => {"
                        " const d = root.querySelector('[data-probe=\"" + probe_id + "\"]');"
                        " if (d) return d;"
                        " for (const el of root.querySelectorAll('*'))"
                        "  if (el.shadowRoot) { const h = find(el.shadowRoot); if (h) return h; }"
                        " return null; }; return find(document); })()"
                    )
                },
            )
            object_id = handle.get("result", {}).get("objectId")
            if not object_id:
                continue
            listeners = await cdp.send(
                "DOMDebugger.getEventListeners", {"objectId": object_id, "depth": 1, "pierce": True}
            )
            for entry in listeners.get("listeners", []):
                if entry.get("type") in ("click", "mousedown", "mouseup", "dblclick"):
                    proposed.add(probe_id)
                    break
        except Exception as exc:
            log.debug("kbdiff.d5_failed", probe=probe_id, error=str(exc)[:120])
    return DetectorResult("D5 CDP getEventListeners", proposed)


async def d6_listener_shim(page: Page) -> DetectorResult:
    """Reads what the document-start ``addEventListener`` shim recorded.

    Blind to three whole families, none of which is about injection timing:
    property assignment, inline attributes, and delegation (where the
    registration is real but its target is not the element).
    """
    try:
        records: list[dict[str, Any]] = await page.evaluate("() => window.__kbShim || []")
    except Exception as exc:
        return DetectorResult("D6 addEventListener shim", set(), note=f"unavailable: {exc}"[:120])

    proposed = {r["probe"] for r in records if r.get("probe")}
    delegated = sum(1 for r in records if r.get("isDocument"))
    return DetectorResult(
        "D6 addEventListener shim",
        proposed,
        note=f"{len(records)} registrations, {delegated} on document/window",
    )


# --------------------------------------------------------------------------
# D8: hover-diff
# --------------------------------------------------------------------------


async def d8_hover_diff(page: Page, probe_ids: list[str]) -> DetectorResult:
    """Hover each probe and see whether the rendering changes.

    Cheap, ML-free affordance signal, and the only cheap route that catches a
    pure-CSS ``:hover`` menu — which involves no JavaScript at all, so every
    listener route misses it by construction.
    """
    proposed: set[str] = set()
    digest_js = """
    () => {
      const parts = [];
      const sx = window.scrollX || 0, sy = window.scrollY || 0;
      const els = document.querySelectorAll('*');
      for (let i = 0; i < Math.min(els.length, 3000); i++) {
        const cs = getComputedStyle(els[i]);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const r = els[i].getBoundingClientRect();
        parts.push(i + ':' + Math.round(r.x + sx) + ',' + Math.round(r.y + sy) +
                   ',' + Math.round(r.width) + ',' + Math.round(r.height) +
                   ',' + cs.backgroundColor + ',' + cs.color);
      }
      let h = 0; const s = parts.join('|');
      for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
      return String(h);
    }
    """
    for probe_id in probe_ids:
        try:
            await page.mouse.move(0, 0)
            await page.wait_for_timeout(30)
            before = await page.evaluate(digest_js)

            # A short timeout on purpose. A probe sealed in a closed shadow root
            # is unreachable from a Playwright locator, and the default 30s wait
            # per such probe dominated the run -- ten minutes of waiting to
            # rediscover something the survey already reported as unobservable.
            box = await page.locator(f'[data-probe="{probe_id}"]').first.bounding_box(timeout=1000)
            if not box or box["width"] == 0 or box["height"] == 0:
                continue
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await page.wait_for_timeout(80)
            after = await page.evaluate(digest_js)

            if before != after:
                proposed.add(probe_id)
        except Exception as exc:
            log.debug("kbdiff.d8_failed", probe=probe_id, error=str(exc)[:120])
    return DetectorResult("D8 hover-diff", proposed)


# --------------------------------------------------------------------------
# D10: V8 coverage differential
# --------------------------------------------------------------------------


async def start_coverage(cdp: CDPSession) -> None:
    """Arm precise coverage, counting calls.

    ``callCount`` false makes V8 report each function as covered only once, so
    the second read of a handler that really ran comes back empty. See
    ``coverage.start`` for the measurement that establishes this.
    """
    with contextlib.suppress(Exception):
        await cdp.send("Profiler.enable")
        await cdp.send("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})


async def take_coverage(cdp: CDPSession) -> set[str]:
    """Executed-function identities since the last take.

    Upstream used this as an alternative state channel and as the basis for
    Stage-4 equivalence. Their own sweep showed why it is a poor equivalence
    signal: two different handlers inside a framework share almost every
    function they run, so only exact set equality worked.
    """
    executed: set[str] = set()
    try:
        result = await cdp.send("Profiler.takePreciseCoverage")
    except Exception:
        return executed
    for script in result.get("result", []):
        url = script.get("url", "")
        for func in script.get("functions", []):
            ranges = func.get("ranges", [])
            if any(r.get("count", 0) > 0 for r in ranges):
                name = func.get("functionName") or "?"
                start = ranges[0].get("startOffset", 0) if ranges else 0
                executed.add(f"{url}#{name}@{start}")
    return executed
