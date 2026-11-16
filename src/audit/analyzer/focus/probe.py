"""SC 2.4.11 Focus Not Obscured (Minimum), Level AA, and SC 2.4.3 probe.

Deterministic, no model.

What SC 2.4.11 asks (WCAG 2.2, normative text): "When a user interface
component receives keyboard focus, the component is not entirely hidden due
to author-created content." Two words in it decide how this check works:

* **"receives keyboard focus"**. The check judges each element at the moment
  focus lands on it, after the browser has scrolled it into view the way it
  does for the Tab key. It does not judge wherever an earlier check happened
  to leave the page. It walks the page twice, each time from the top, the
  two ways a keyboard user can go after the page loads: forward (Tab), and
  backward (Shift+Tab, which goes to the last element first and works up).
  A sticky header usually hides focus on the way back up and a sticky footer
  on the way down, so one direction alone would miss half the cases.
  Starting from the top also means a person can repeat it: load the page and
  press the key. Focus is moved with ``element.focus()``, not with key
  presses. On the fixtures that leaves each element exactly where real Tab
  and Shift+Tab presses leave it in Chromium, ``scroll-padding`` included
  (tests/integration/test_focus_probe.py presses the real keys and compares).

  A page's own code often changes the bar when the page scrolls: it turns
  from clear to solid, shrinks, or slides in. A keyboard user sees the bar
  after that change, so after each focus move that scrolls the page the
  check waits two frames for the page's code to run, and then for any short
  change to content that stays in place to finish. Without the wait, the
  bar would be judged as it looked when the check began, which again
  depends on where an earlier check left the page.

* **"entirely hidden"**. The check reports only when every point it samples
  on the element is covered by solid content that stays in place while the
  page scrolls (``position: fixed`` or ``sticky``). An element that is only
  partly covered is not reported. That is SC 2.4.12 Focus Not Obscured
  (Enhanced), Level AAA ("no part of the component is hidden by
  author-created content"), which this check does not test.

Not reported, on purpose:

* content you can see through (a transparent or part-transparent bar). The
  WCAG Understanding document for 2.4.11 says a semi-transparent or blurring
  overlay may not fully hide the item, so it can still pass, and points to
  SC 1.4.11 Non-text Contrast for it instead (paraphrase,
  https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html);
* an element that paints nothing of its own, such as a visually hidden
  ``.sr-only`` link, because the bar is not what hides it;
* an element with no part inside the viewport after the browser's scroll.

Limits a human still has to cover: the first ``MAX_FOCUSABLE`` elements only,
and fewer if the walks run out of time (``_WALK_BUDGET_MS``; logged when it
happens); DOM order stands in for tab order; a bar whose code reacts to
scrolling later than two frames (a handler on a timer), or changes for
longer than ``_OVERLAY_SETTLE_MS``, is judged before it has finished;
overlays opened by a click are not tested here. The check restores the
scroll position and focus it found, so later checks see the page as this
one received it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page

from audit.analyzer.focus.base import (
    RULE_FOCUS_OBSCURED,
    RULE_POSITIVE_TABINDEX,
    FocusFinding,
)
from audit.logging import get_logger

log = get_logger(__name__)

# Cap how many focusable elements we test per page, bounds the worst case
# on a 500-link page. Most pages have far fewer interactive elements.
MAX_FOCUSABLE = 150

# How long the two walks may take on one page, and how long the check waits
# for a bar that is changing (fading in, sliding in) to finish. The walk
# waits two frames after each focus move that scrolls the page, so a page
# with 150 controls spread down a long page takes about 10 seconds at worst.
_WALK_BUDGET_MS = 15_000
_OVERLAY_SETTLE_MS = 600

# One round-trip. Starting from the top of the page each time, walks the
# focusable elements forward and then backward, focusing each one so the
# browser scrolls it into view, lets the page react to that scroll, and
# returns {items: [{selector, html, coverTag, directions}], complete} with an
# item for each element that is then entirely covered by solid fixed/sticky
# content. ``complete`` is false when the time budget ran out before every
# element was tried. See the module docstring for the reasoning.
#
# ``paintsNothing`` has a twin in audit/analyzer/responsive/probe.py
# (``hiddenOnPurpose``). Keep the two in step.
_OBSCURED_JS = """
async ([cap, budgetMs, settleMs]) => {
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, [tabindex]';
  const cssPath = (el) => {
    if (el.id) return el.tagName.toLowerCase() + '#' + el.id;
    let p = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const c = el.className.trim().split(/\\s+/)[0];
      if (c) p += '.' + c;
    }
    return p;
  };

  // --- Is the element hidden by its own CSS (or an ancestor's)? ----------
  // clip: rect(top, right, bottom, left) with no area, as in the
  // visually-hidden pattern's rect(0, 0, 0, 0).
  const emptyClipRect = (value) => {
    const m = /^rect\\(([^)]*)\\)$/.exec(value || '');
    if (!m) return false;
    const p = m[1].split(/[\\s,]+/).filter(Boolean).map(parseFloat);
    if (p.length !== 4 || p.some(Number.isNaN)) return false;
    return p[2] - p[0] <= 0 || p[1] - p[3] <= 0;
  };
  // clip-path: inset(50%) and its relatives that leave no area.
  const emptyClipPath = (value) => {
    const m = /^inset\\(([^)]*)\\)$/.exec(value || '');
    if (!m) return false;
    const parts = m[1].split(/\\s+round\\s+/)[0].trim().split(/\\s+/);
    if (!parts.length || !parts.every((x) => /%$/.test(x))) return false;
    const n = parts.map(parseFloat);
    const top = n[0];
    const right = n.length > 1 ? n[1] : top;
    const bottom = n.length > 2 ? n[2] : top;
    const left = n.length > 3 ? n[3] : right;
    return top + bottom >= 100 || left + right >= 100;
  };
  const paintsNothing = (el) => {
    if (getComputedStyle(el).visibility !== 'visible') return true;
    for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
      const cs = getComputedStyle(cur);
      if (cs.display === 'none') return true;
      if (parseFloat(cs.opacity) === 0) return true;
      if ((cs.position === 'absolute' || cs.position === 'fixed')
          && emptyClipRect(cs.clip)) return true;
      if (emptyClipPath(cs.clipPath)) return true;
      // A box of 1px or less that cuts off its content: the rest of the
      // visually-hidden pattern, and collapsed panels.
      if (cur instanceof HTMLElement
          && cs.display !== 'inline' && cs.display !== 'contents'
          && cs.overflowX !== 'visible' && cs.overflowY !== 'visible'
          && cur.getClientRects().length
          && (cur.clientWidth <= 1 || cur.clientHeight <= 1)) return true;
    }
    return false;
  };

  // --- What covers a point? ---------------------------------------------
  const alphaOf = (color) => {
    if (!color || color === 'transparent') return 0;
    const slash = /\\/\\s*([\\d.]+)(%?)\\s*\\)\\s*$/.exec(color);
    if (slash) return parseFloat(slash[1]) / (slash[2] ? 100 : 1);
    const legacy = /^(?:rgba|hsla)\\([^,]+,[^,]+,[^,]+,\\s*([\\d.]+)(%?)\\s*\\)$/.exec(color);
    if (legacy) return parseFloat(legacy[1]) / (legacy[2] ? 100 : 1);
    return 1;
  };
  // A background image counts as solid unless it is a gradient that names
  // a see-through colour.
  const solidImage = (image) => {
    if (!image || image === 'none') return false;
    if (!/gradient\\(/.test(image)) return true;
    if (/transparent/.test(image)) return false;
    const colors = image.match(/(?:rgba?|hsla?|oklch|oklab|lab|lch|color)\\([^()]*\\)/g) || [];
    return colors.every((c) => alphaOf(c) >= 0.99);
  };
  const REPLACED = new Set(['IMG', 'VIDEO', 'CANVAS', 'IFRAME', 'OBJECT', 'EMBED']);
  // The nearest thing around `node` (or `node` itself) that stays in place
  // while the page scrolls.
  const overlayOf = (node) => {
    for (let cur = node; cur && cur.nodeType === 1 && cur !== document.body
         && cur !== document.documentElement; cur = cur.parentElement) {
      const pos = getComputedStyle(cur).position;
      if (pos === 'fixed' || pos === 'sticky') return cur;
    }
    return null;
  };
  // Answers are kept for one element's test only: a bar can change between
  // one focused element and the next.
  const coverCache = new Map();
  // For the element hit at a point: its overlay, and whether what the
  // overlay paints there is solid.
  const coverOf = (hit) => {
    if (coverCache.has(hit)) return coverCache.get(hit);
    const overlay = overlayOf(hit);
    let solid = false;
    if (overlay) {
      for (let cur = hit; cur; cur = cur.parentElement) {
        const cs = getComputedStyle(cur);
        if (REPLACED.has(cur.tagName) || alphaOf(cs.backgroundColor) >= 0.99
            || solidImage(cs.backgroundImage)) { solid = true; break; }
        if (cur === overlay) break;
      }
      if (solid) {
        for (let cur = hit; cur && cur.nodeType === 1; cur = cur.parentElement) {
          if (parseFloat(getComputedStyle(cur).opacity) < 0.99) { solid = false; break; }
        }
      }
    }
    const res = { overlay: overlay, solid: solid };
    coverCache.set(hit, res);
    return res;
  };

  // Five positions along one side of a box: just inside each edge, and the
  // quarter points. A sliver left showing at an edge counts as visible.
  const steps = (start, size) => {
    if (size < 4) return [start + size / 2];
    return [start + 1, start + size * 0.25, start + size * 0.5,
            start + size * 0.75, start + size - 1];
  };
  // Returns the fixed/sticky element that hides ALL of `el`, else null.
  // One visible point anywhere on the element, or on what is inside it,
  // ends the test: the element is then not "entirely hidden".
  const hiddenBy = (el) => {
    coverCache.clear();
    const boxes = Array.from(el.getClientRects()).slice(0, 6);
    for (const d of Array.from(el.querySelectorAll('*')).slice(0, 12)) {
      boxes.push(d.getBoundingClientRect());
    }
    const vw = document.documentElement.clientWidth;
    const vh = document.documentElement.clientHeight;
    let tested = 0;
    let cover = null;
    for (const r of boxes) {
      if (r.width < 1 || r.height < 1) continue;
      for (const y of steps(r.top, r.height)) {
        for (const x of steps(r.left, r.width)) {
          if (x < 0 || y < 0 || x >= vw || y >= vh) continue;
          const hit = document.elementFromPoint(x, y);
          if (!hit) continue;
          tested += 1;
          // The element itself shows here, or it is cut off by its own
          // container rather than covered: either way, not hidden by a bar.
          if (hit === el || el.contains(hit) || hit.contains(el)) return null;
          const c = coverOf(hit);
          // Not something that stays in place, see-through, or part of the
          // same fixed layer as the element (layering inside one bar or
          // dialog is not this failure).
          if (!c.overlay || !c.solid || c.overlay.contains(el)) return null;
          if (!cover) cover = c.overlay;
        }
      }
    }
    return tested > 0 ? cover : null;
  };

  // --- Leave the page as we found it ------------------------------------
  // Focusing scrolls the window and any scroll container around the
  // element. Remember each one's position the first time we meet it, and
  // turn off smooth scrolling there so the scroll finishes before we look.
  const touched = new Map();
  const prepare = (el) => {
    for (let cur = el.parentElement; cur; cur = cur.parentElement) {
      if (touched.has(cur)) break;  // its ancestors are recorded too
      const rec = { top: cur.scrollTop, left: cur.scrollLeft, smooth: null };
      if (getComputedStyle(cur).scrollBehavior === 'smooth') {
        rec.smooth = {
          hadAttr: cur.hasAttribute('style'),
          value: cur.style.getPropertyValue('scroll-behavior'),
          priority: cur.style.getPropertyPriority('scroll-behavior'),
        };
        cur.style.setProperty('scroll-behavior', 'auto', 'important');
      }
      touched.set(cur, rec);
    }
  };
  const restore = (startX, startY, startActive) => {
    try {
      if (startActive && startActive !== document.body && startActive.isConnected
          && typeof startActive.focus === 'function') {
        startActive.focus({ preventScroll: true });
      } else if (document.activeElement && document.activeElement !== document.body
                 && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
      }
    } catch (e) { /* focus is best-effort */ }
    for (const [node, rec] of touched) {
      if (node.scrollTop !== rec.top) node.scrollTop = rec.top;
      if (node.scrollLeft !== rec.left) node.scrollLeft = rec.left;
    }
    window.scrollTo({ left: startX, top: startY, behavior: 'instant' });
    for (const [node, rec] of touched) {
      if (!rec.smooth) continue;
      if (rec.smooth.value) {
        node.style.setProperty('scroll-behavior', rec.smooth.value, rec.smooth.priority);
      } else {
        node.style.removeProperty('scroll-behavior');
        if (!rec.smooth.hadAttr && node.getAttribute('style') === '') {
          node.removeAttribute('style');
        }
      }
    }
  };

  // --- Let the page react, as it does between two key presses ------------
  // A page's own code runs when the page scrolls: a bar may turn solid,
  // shrink, or slide in. A keyboard user sees the bar after that, so the
  // check waits for it before it looks. Two frames lets scroll handlers,
  // observers and a re-render run. The timer is for a page that is not
  // being drawn and so gets no frames.
  const nextFrames = () => new Promise((resolve) => {
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    requestAnimationFrame(() => requestAnimationFrame(finish));
    setTimeout(finish, 150);
  });
  // The CSS properties whose change can cover or uncover something.
  const COVER_PROPS = new Set([
    'background-color', 'opacity', 'visibility', 'display', 'clip-path',
    'transform', 'translate', 'top', 'bottom', 'left', 'right',
    'height', 'max-height', 'width', 'max-width',
  ]);
  // Wait until content that stays in place has finished changing. Counts
  // only short changes that end: a CSS transition of a property above on
  // or inside such content, or any other animation of the fixed/sticky
  // element itself. Never the focused element's own focus styling, and
  // never an animation that loops.
  const overlaysSettled = async (el) => {
    let running = [];
    try {
      running = document.getAnimations().filter((a) => {
        const target = a.effect && a.effect.target;
        if (!target || target.nodeType !== 1 || a.playState !== 'running') return false;
        if (el && (target === el || el.contains(target))) return false;
        const overlay = overlayOf(target);
        if (!overlay) return false;
        if (typeof a.transitionProperty === 'string') {
          if (!COVER_PROPS.has(a.transitionProperty)) return false;
        } else if (overlay !== target) {
          return false;
        }
        const left = a.effect.getComputedTiming().endTime - (Number(a.currentTime) || 0);
        return Number.isFinite(left) && left <= settleMs;
      });
    } catch (e) { return; }
    if (!running.length) return;
    await Promise.race([
      Promise.allSettled(running.map((a) => a.finished)),
      new Promise((resolve) => setTimeout(resolve, settleMs)),
    ]);
  };

  // --- The two walks -----------------------------------------------------
  const els = Array.from(document.querySelectorAll(sel)).slice(0, cap).filter((el) => {
    if (el.disabled) return false;
    if (typeof el.tabIndex === 'number' && el.tabIndex < 0) return false;
    return el.getClientRects().length > 0;
  });
  if (!els.length) return { items: [], complete: true };

  const startX = window.scrollX;
  const startY = window.scrollY;
  const startActive = document.activeElement;
  const deadline = performance.now() + budgetMs;
  let complete = true;
  const found = new Map();
  const scrolledTo = () => window.scrollX + ',' + window.scrollY;
  const walk = async (list, direction) => {
    // Each walk starts where a freshly loaded page starts: at the top, with
    // the page settled there. Shift+Tab from there goes to the last element,
    // and the browser scrolls only as far as it needs to show it.
    window.scrollTo({ left: 0, top: 0, behavior: 'instant' });
    await nextFrames();
    await overlaysSettled(null);
    for (const el of list) {
      if (performance.now() > deadline) { complete = false; return; }
      if (!el.isConnected) continue;
      prepare(el);
      const before = scrolledTo();
      // No preventScroll: the browser brings the element into view exactly
      // as it does when Tab moves focus to it.
      try { el.focus(); } catch (e) { continue; }
      if (document.activeElement !== el) continue;   // could not take focus
      if (scrolledTo() !== before) await nextFrames();
      await overlaysSettled(el);
      // The page may have moved focus on, or removed the element, meanwhile.
      if (document.activeElement !== el || !el.isConnected) continue;
      if (paintsNothing(el)) continue;               // not hidden by a bar
      const cover = hiddenBy(el);
      if (!cover) continue;
      const rec = found.get(el);
      if (rec) { rec.directions.push(direction); continue; }
      found.set(el, {
        selector: cssPath(el),
        html: (el.outerHTML || '').slice(0, 300),
        coverTag: (cover.tagName || '').toLowerCase(),
        directions: [direction],
      });
    }
  };
  try {
    prepare(els[0]);
    await walk(els, 'forward');
    await walk(els.slice().reverse(), 'backward');
  } finally {
    restore(startX, startY, startActive);
    // Let the page settle where we put it back, for the checks that follow.
    await nextFrames();
    await overlaysSettled(null);
  }
  // Report in page order, whichever walk found the element first.
  return {
    items: els.filter((el) => found.has(el)).map((el) => found.get(el)),
    complete: complete,
  };
}
"""


# SC 2.4.3 (WCAG F44): positive tabindex forces a manual tab order that
# overrides DOM order. Deterministic + high-confidence, return every
# element whose tabindex attribute parses to a value > 0.
_POSITIVE_TABINDEX_JS = """
(cap) => {
  const cssPath = (el) => {
    if (el.id) return el.tagName.toLowerCase() + '#' + el.id;
    let p = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const c = el.className.trim().split(/\\s+/)[0];
      if (c) p += '.' + c;
    }
    return p;
  };
  const out = [];
  const els = Array.from(document.querySelectorAll('[tabindex]')).slice(0, cap);
  for (const el of els) {
    const ti = parseInt(el.getAttribute('tabindex'), 10);
    if (!Number.isFinite(ti) || ti <= 0) continue;
    out.push({
      selector: cssPath(el),
      html: (el.outerHTML || '').slice(0, 300),
      tabindex: ti,
    });
  }
  return out;
}
"""

# How the stored summary names the walk that found the element. The words
# say what the check did (it moved focus itself, in the order the key
# would), not that a person pressed the key.
_DIRECTION_PHRASES = {
    ("forward",): ("forward through the page, as the Tab key does", "Tab"),
    ("backward",): ("backward through the page, as Shift+Tab does", "Shift+Tab"),
    ("forward", "backward"): (
        "through the page in both directions, as Tab and Shift+Tab do",
        "Tab or Shift+Tab",
    ),
}


def _direction_phrases(raw: Any) -> tuple[str, str]:
    """(how the check moved focus, the key a reviewer presses to confirm)."""
    seen = [d for d in ("forward", "backward") if isinstance(raw, list) and d in raw]
    return _DIRECTION_PHRASES.get(tuple(seen), _DIRECTION_PHRASES[("forward", "backward")])


@dataclass
class FocusProbe:
    """Runs the SC 2.4.11 focus-obscured check against a live page."""

    max_focusable: int = MAX_FOCUSABLE
    # The protected companion must not log browser exception text because it
    # can include an authenticated route or page-provided diagnostic.
    suppress_diagnostics: bool = False

    async def run(self, page: Page) -> list[FocusFinding]:
        """Run both focus checks. Never raises, each check is isolated so
        one failing doesn't lose the other's findings."""
        findings: list[FocusFinding] = []
        try:
            findings.extend(await self._check_obscured(page))
        except Exception as exc:  # pragma: no cover - defensive
            self._log_failure("obscured", exc)
        try:
            findings.extend(await self._check_positive_tabindex(page))
        except Exception as exc:  # pragma: no cover - defensive
            self._log_failure("tabindex", exc)
        return findings

    def _log_failure(self, check: str, exc: Exception) -> None:
        if self.suppress_diagnostics:
            log.warning("focus.probe_failed_in_protected_context", check=check)
        else:
            log.warning(f"focus.{check}_failed", error=str(exc))

    async def _check_obscured(self, page: Page) -> list[FocusFinding]:
        """SC 2.4.11: elements entirely hidden behind fixed/sticky content
        at the moment they receive keyboard focus."""
        raw: Any = await page.evaluate(
            _OBSCURED_JS, [self.max_focusable, _WALK_BUDGET_MS, _OVERLAY_SETTLE_MS]
        )
        result = raw if isinstance(raw, dict) else {}
        if result.get("complete") is False:
            # Not an error: what was found is still true. But the rest of the
            # page was not tried, and a clean result must not hide that.
            log.warning("focus.obscured_ran_out_of_time", budget_ms=_WALK_BUDGET_MS)
        findings: list[FocusFinding] = []
        seen: set[str] = set()
        for item in result.get("items") or []:
            if not isinstance(item, dict):
                continue
            selector = str(item.get("selector") or "").strip()
            if not selector or selector in seen:
                continue
            seen.add(selector)
            cover = str(item.get("coverTag") or "overlay")
            moved, key = _direction_phrases(item.get("directions"))
            findings.append(
                FocusFinding(
                    rule_id=RULE_FOCUS_OBSCURED,
                    target_selector=selector,
                    failure_summary=(
                        f"All of this element is hidden when it gets keyboard focus. "
                        f"Content that stays in place while the page scrolls (a "
                        f"fixed or sticky <{cover}>) covers it. A keyboard user "
                        f"cannot see what they have focused. The check moved focus "
                        f"{moved}. It let the browser scroll the element into view, "
                        f"then tested points across the element and found every one "
                        f"covered. To confirm, press {key} on the live page until "
                        f"focus reaches this element."
                    ),
                    html_snippet=str(item.get("html") or ""),
                    # Unchanged on purpose: with no rule metadata for this
                    # rule, the Issues table shows ``help`` as the issue
                    # type's title (audit/web/issues.py).
                    help=(
                        "Keep focused elements visible, add scroll-margin / "
                        "scroll-padding so they aren't hidden behind sticky headers, "
                        "or reduce the sticky element's height."
                    ),
                )
            )
        return findings

    async def _check_positive_tabindex(self, page: Page) -> list[FocusFinding]:
        """SC 2.4.3 (WCAG F44), positive tabindex forces a manual tab order."""
        raw: Any = await page.evaluate(_POSITIVE_TABINDEX_JS, self.max_focusable)
        findings: list[FocusFinding] = []
        seen: set[str] = set()
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            selector = str(item.get("selector") or "").strip()
            if not selector or selector in seen:
                continue
            seen.add(selector)
            ti = item.get("tabindex")
            findings.append(
                FocusFinding(
                    rule_id=RULE_POSITIVE_TABINDEX,
                    target_selector=selector,
                    failure_summary=(
                        f'This element has tabindex="{ti}", forcing a manual tab '
                        f"order that overrides the natural DOM order (WCAG failure "
                        f"F44). Positive tab orders are fragile and usually break "
                        f"the reading/operation sequence."
                    ),
                    html_snippet=str(item.get("html") or ""),
                    help=(
                        'Remove the positive tabindex. Use tabindex="0" (or rely on '
                        "the natural order) and reorder the DOM/CSS so source order "
                        "matches visual order."
                    ),
                    criterion_sc="2.4.3",
                    wcag_level="A",
                )
            )
        return findings
