"""SC 2.4.11, Focus Not Obscured (Minimum) probe.

Deterministic, no model. In one ``page.evaluate`` it focuses each focusable
element and checks whether the element's centre is covered by a
``position:fixed`` / ``sticky`` overlay (the classic "focus disappears
behind the sticky header" failure). Conservative on purpose, it samples
the centre point, so it flags elements that are substantially obscured, not
ones merely clipped at an edge. Edge cases (transforms, partial overlap)
still need a human; the coverage matrix marks this ``partial``.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page

from audit.analyzer.focus.base import (
    RULE_FOCUS_NOT_VISIBLE,
    RULE_FOCUS_OBSCURED,
    RULE_NON_INTERACTIVE_STOP,
    RULE_POSITIVE_TABINDEX,
    RULE_VISUAL_ORDER,
    FocusFinding,
)
from audit.logging import get_logger

log = get_logger(__name__)

# Cap how many focusable elements we test per page, bounds the worst case
# on a 500-link page. Most pages have far fewer interactive elements.
MAX_FOCUSABLE = 150

# One round-trip: enumerate focusable elements, focus each, and report any
# whose centre point is covered by a fixed/sticky overlay. Returns a list of
# {selector, html, coverTag} for the obscured ones.
_OBSCURED_JS = """
(cap) => {
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
  const overlayAncestor = (node) => {
    let cur = node;
    while (cur && cur !== document.body) {
      const pos = getComputedStyle(cur).position;
      if (pos === 'fixed' || pos === 'sticky') return cur;
      cur = cur.parentElement;
    }
    return null;
  };
  const out = [];
  const els = Array.from(document.querySelectorAll(sel)).slice(0, cap);
  for (const el of els) {
    if (el.disabled) continue;
    if (typeof el.tabIndex === 'number' && el.tabIndex < 0) continue;
    const rects = el.getClientRects();
    if (!rects.length) continue;
    try { el.focus({ preventScroll: true }); } catch (e) { continue; }
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    if (cx < 0 || cy < 0 || cx > window.innerWidth || cy > window.innerHeight) continue;
    const top = document.elementFromPoint(cx, cy);
    if (!top || top === el || el.contains(top) || top.contains(el)) continue;
    const overlay = overlayAncestor(top);
    if (!overlay) continue;
    out.push({
      selector: cssPath(el),
      html: (el.outerHTML || '').slice(0, 300),
      coverTag: (overlay.tagName || '').toLowerCase(),
    });
  }
  return out;
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


# Findings of one shape (tag + first class) are reported this many times per
# page at most: a site-wide style with no focus indicator is one fix.
_MAX_PER_RULE = 10
# Controls read per page by the newer checks. Focusing one costs a style
# recalculation, so the visibility check stops sooner than the order check,
# which only reads geometry.
MAX_FOCUS_VISIBLE = 400
MAX_ORDER_SCAN = 2000

# SC 2.4.7: focus each control and compare every style a focus indicator can
# use, on the control, its ::before/::after, the parent and grandparent (a
# :focus-within style), its siblings and its labels (a visually hidden input
# whose label shows focus). Transitions are frozen for the duration, so a
# fading ring is read at its end state, and removed afterwards.
_NOT_VISIBLE_JS = """
(cap) => {
  // A unique path (nth-of-type chain from the nearest unique id), so the
  // screenshot pass and a person both find this element and not a namesake.
  const cssPath = (el) => {
    const parts = [];
    for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
      const tag = cur.tagName.toLowerCase();
      if (cur.id && /^[A-Za-z][\\w-]*$/.test(cur.id) &&
          document.querySelectorAll('#' + cur.id).length === 1) {
        parts.unshift(tag + '#' + cur.id);
        break;
      }
      const parent = cur.parentElement;
      if (!parent) { parts.unshift(tag); break; }
      let n = 1;
      for (let sib = cur.previousElementSibling; sib; sib = sib.previousElementSibling) {
        if (sib.tagName === cur.tagName) n += 1;
      }
      parts.unshift(tag + ':nth-of-type(' + n + ')');
    }
    return parts.join(' > ');
  };
  const PROPS = ['boxShadow', 'backgroundColor', 'backgroundImage', 'color',
    'textDecorationLine', 'textDecorationColor', 'textDecorationThickness', 'fontWeight',
    'transform', 'opacity', 'filter'];
  // An outline or border counts only when it can draw: the UA stylesheet
  // moves outline-offset on focus even when the outline is none.
  const drawn = (s) => {
    const parts = [];
    if (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) {
      parts.push(s.outlineStyle, s.outlineWidth, s.outlineColor, s.outlineOffset);
    }
    for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
      if (s['border' + side + 'Style'] !== 'none' && parseFloat(s['border' + side + 'Width']) > 0) {
        parts.push(side, s['border' + side + 'Width'], s['border' + side + 'Color']);
      }
    }
    return parts.join('|');
  };
  const sig = (el) => {
    if (!el || el.nodeType !== 1) return '';
    const parts = [];
    for (const pseudo of [null, '::before', '::after']) {
      const s = getComputedStyle(el, pseudo);
      parts.push(PROPS.map((k) => s[k]).join('|'), drawn(s));
      if (pseudo) parts.push(s.content);
    }
    return parts.join('#');
  };
  const around = (el) => {
    const set = [el, el.parentElement, el.parentElement && el.parentElement.parentElement,
      el.previousElementSibling, el.nextElementSibling];
    for (const l of el.labels || []) set.push(l);
    return set;
  };
  const TEXT_ENTRY = 'textarea, input:not([type]), input[type=text], input[type=search], ' +
    'input[type=email], input[type=password], input[type=tel], input[type=url], ' +
    'input[type=number]';
  const freeze = document.createElement('style');
  freeze.textContent = '*,*::before,*::after{transition:none!important;animation:none!important}';
  document.documentElement.appendChild(freeze);
  const prev = document.activeElement;
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, summary, ' +
    '[tabindex]:not([tabindex="-1"])';
  const out = [];
  try {
    for (const el of Array.from(document.querySelectorAll(sel)).slice(0, cap)) {
      if (el.disabled || el.tabIndex < 0 || !el.getClientRects().length) continue;
      // A text field shows its caret when focused; that is an indicator.
      if (el.matches(TEXT_ENTRY) || el.isContentEditable) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility !== 'visible') continue;
      if (el.closest('[aria-hidden="true"],[inert]')) continue;
      const before = around(el).map(sig);
      try { el.focus({ preventScroll: true }); } catch (e) { continue; }
      if (document.activeElement !== el) continue;
      const after = around(el).map(sig);
      el.blur();
      if (before.every((v, i) => v === after[i])) {
        const cls = (el.getAttribute('class') || '').trim().split(/\\s+/)[0];
        out.push({ selector: cssPath(el), shape: el.tagName + '.' + cls,
                   html: (el.outerHTML || '').slice(0, 300) });
      }
    }
  } finally {
    freeze.remove();
    try { if (prev && prev.focus && prev !== document.body) prev.focus({ preventScroll: true }); }
    catch (e) {}
  }
  return out;
}
"""

# SC 2.4.3: a Tab stop on something that is not a control. Only elements with
# no role, no ARIA, no title, not scrollable (a scroll region needs one), not
# editable, and no handler of any kind (checked over CDP afterwards).
_NON_INTERACTIVE_JS = """
(cap) => {
  // A unique path (nth-of-type chain from the nearest unique id), so the
  // screenshot pass and a person both find this element and not a namesake.
  const cssPath = (el) => {
    const parts = [];
    for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
      const tag = cur.tagName.toLowerCase();
      if (cur.id && /^[A-Za-z][\\w-]*$/.test(cur.id) &&
          document.querySelectorAll('#' + cur.id).length === 1) {
        parts.unshift(tag + '#' + cur.id);
        break;
      }
      const parent = cur.parentElement;
      if (!parent) { parts.unshift(tag); break; }
      let n = 1;
      for (let sib = cur.previousElementSibling; sib; sib = sib.previousElementSibling) {
        if (sib.tagName === cur.tagName) n += 1;
      }
      parts.unshift(tag + ':nth-of-type(' + n + ')');
    }
    return parts.join(' > ');
  };
  const PLAIN = /^(DIV|SPAN|P|LI|SECTION|ARTICLE|HEADER|FOOTER|H[1-6]|TD|TH|DT|DD|STRONG|EM|B|I)$/;
  const out = [];
  for (const el of Array.from(document.querySelectorAll('[tabindex="0"]')).slice(0, cap)) {
    if (!PLAIN.test(el.tagName) || el.hasAttribute('role') || el.hasAttribute('title')) continue;
    if (Array.from(el.attributes).some((a) => a.name.startsWith('aria-'))) continue;
    if (el.isContentEditable || !el.getClientRects().length) continue;
    const cs = getComputedStyle(el);
    const scrolls = /(auto|scroll)/.test(cs.overflow + cs.overflowX + cs.overflowY) &&
      (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1);
    if (scrolls || cs.cursor === 'pointer') continue;
    // Named like a control: a broken control, not an extra stop (the
    // keyboard check's mouse-only rules speak to it).
    if (/(^|[-_ ])(btn|button|link|toggle|action|close|open|menu|tab)([-_ ]|$)/i
      .test(el.getAttribute('class') || '')) continue;
    if (typeof el.onclick === 'function' || typeof el.onkeydown === 'function') continue;
    const props = Object.keys(el).find((k) => k.startsWith('__reactProps$'));
    if (props && Object.keys(el[props] || {}).some((k) => /^on[A-Z]/.test(k))) continue;
    el.setAttribute('data-axcess-stop', String(out.length));
    out.push({ selector: cssPath(el), html: (el.outerHTML || '').slice(0, 300) });
  }
  return out;
}
"""

# SC 2.4.3: siblings on one line whose Tab order is not their visual order
# (floats, flex ``order`` or ``row-reverse``). One lead per container.
_VISUAL_ORDER_JS = """
(cap) => {
  // A unique path (nth-of-type chain from the nearest unique id), so the
  // screenshot pass and a person both find this element and not a namesake.
  const cssPath = (el) => {
    const parts = [];
    for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
      const tag = cur.tagName.toLowerCase();
      if (cur.id && /^[A-Za-z][\\w-]*$/.test(cur.id) &&
          document.querySelectorAll('#' + cur.id).length === 1) {
        parts.unshift(tag + '#' + cur.id);
        break;
      }
      const parent = cur.parentElement;
      if (!parent) { parts.unshift(tag); break; }
      let n = 1;
      for (let sib = cur.previousElementSibling; sib; sib = sib.previousElementSibling) {
        if (sib.tagName === cur.tagName) n += 1;
      }
      parts.unshift(tag + ':nth-of-type(' + n + ')');
    }
    return parts.join(' > ');
  };
  const FOC = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [tabindex]';
  const focusableIn = (el) => {
    const list = el.matches(FOC) ? [el] : Array.from(el.querySelectorAll(FOC));
    return list.filter((f) => f.tabIndex >= 0 && !f.disabled && f.getClientRects().length);
  };
  const out = [];
  const parents = new Set();
  for (const f of Array.from(document.querySelectorAll(FOC)).slice(0, cap)) {
    if (f.parentElement) parents.add(f.parentElement);
    const grand = f.parentElement && f.parentElement.parentElement;
    if (grand) parents.add(grand);
  }
  for (const p of parents) {
    if (out.length >= 10) break;
    const rtl = getComputedStyle(p).direction === 'rtl';
    const items = [];
    for (const c of p.children) {
      const cs = getComputedStyle(c);
      if (cs.position === 'absolute' || cs.position === 'fixed') continue;
      const fs = focusableIn(c);
      if (fs.length !== 1) continue;
      if (parseInt(fs[0].getAttribute('tabindex') || '0', 10) > 0) continue; // F44's rule
      const r = fs[0].getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      items.push({ r, el: fs[0] });
    }
    if (items.length < 3) continue;
    // Items sharing a line (vertical overlap over half the smaller height).
    let bad = null;
    for (let i = 0; i + 1 < items.length && !bad; i++) {
      for (let j = i + 1; j < items.length; j++) {
        const a = items[i].r, b = items[j].r;
        const overlap = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (overlap < Math.min(a.height, b.height) / 2) continue;
        const backwards = rtl ? b.left > a.right : b.right < a.left;
        if (backwards) { bad = [items[i].el, items[j].el]; break; }
      }
    }
    if (!bad) continue;
    out.push({
      selector: cssPath(p), html: (p.outerHTML || '').slice(0, 300),
      first: (bad[0].textContent || '').trim().slice(0, 40),
      second: (bad[1].textContent || '').trim().slice(0, 40),
    });
  }
  return out;
}
"""


@dataclass
class FocusProbe:
    """Runs the SC 2.4.11 focus-obscured check against a live page."""

    max_focusable: int = MAX_FOCUSABLE
    # The protected companion must not log browser exception text because it
    # can include an authenticated route or page-provided diagnostic.
    suppress_diagnostics: bool = False
    # SC 2.4.7 focus visible and the two further SC 2.4.3 order checks.
    focus_order_checks: bool = True

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
        if self.focus_order_checks:
            for name, check in (
                ("not_visible", self._check_not_visible),
                ("non_interactive", self._check_non_interactive_stop),
                ("visual_order", self._check_visual_order),
            ):
                try:
                    findings.extend(await check(page))
                except Exception as exc:  # pragma: no cover - defensive
                    self._log_failure(name, exc)
        return findings

    async def _check_not_visible(self, page: Page) -> list[FocusFinding]:
        """SC 2.4.7, focusing the control changes nothing that could show it."""
        # Focus-visible polyfills show a ring only after a keyboard event, and
        # a script focus() is not one. Shift alone does nothing on a page.
        with contextlib.suppress(Exception):
            await page.keyboard.press("Shift")
        raw: Any = await page.evaluate(_NOT_VISIBLE_JS, MAX_FOCUS_VISIBLE)
        return [
            FocusFinding(
                rule_id=RULE_FOCUS_NOT_VISIBLE,
                target_selector=item["selector"],
                failure_summary=(
                    "Measured: when this control has keyboard focus, none of its styles "
                    "that could show focus change (outline, shadow, border, background, "
                    "colour, underline), nor those of its parent, neighbours or label. A "
                    "keyboard user cannot see where focus is."
                ),
                html_snippet=str(item.get("html") or ""),
                help="Give every control a visible focus style, such as an outline.",
                criterion_sc="2.4.7",
                wcag_level="AA",
            )
            for item in _first_per_shape(raw)
        ]

    async def _check_non_interactive_stop(self, page: Page) -> list[FocusFinding]:
        """SC 2.4.3, tabindex="0" on plain content with no role or handler."""
        raw: Any = await page.evaluate(_NON_INTERACTIVE_JS, MAX_ORDER_SCAN)
        items = [i for i in (raw or []) if isinstance(i, dict)]
        if items:
            quiet = await _without_listeners(page, len(items))
            items = [item for index, item in enumerate(items) if index in quiet]
        return [
            FocusFinding(
                rule_id=RULE_NON_INTERACTIVE_STOP,
                target_selector=item["selector"],
                failure_summary=(
                    'This element has tabindex="0", so the Tab key stops on it, but it '
                    "has no role and no handler: it is not a control. Keyboard users "
                    "pass an extra stop that does nothing, and screen readers announce "
                    "no purpose for it."
                ),
                html_snippet=str(item.get("html") or ""),
                help='Remove tabindex="0", or make it a real control with a role and handlers.',
                criterion_sc="2.4.3",
                wcag_level="A",
                impact="moderate",
            )
            for item in _first_per_shape(items)
        ]

    async def _check_visual_order(self, page: Page) -> list[FocusFinding]:
        """SC 2.4.3, Tab order runs against the visual order of a row."""
        raw: Any = await page.evaluate(_VISUAL_ORDER_JS, MAX_ORDER_SCAN)
        return [
            FocusFinding(
                rule_id=RULE_VISUAL_ORDER,
                target_selector=item["selector"],
                failure_summary=(
                    f'In this group the Tab key reaches "{item.get("first", "")}" before '
                    f'"{item.get("second", "")}", but "{item.get("second", "")}" is shown '
                    "before it on the same line (the layout reorders them, for example "
                    "with float, flex order or row-reverse). Check that the order still "
                    "makes sense."
                ),
                html_snippet=str(item.get("html") or ""),
                help="Make the source order match the visual order.",
                criterion_sc="2.4.3",
                wcag_level="A",
                impact="moderate",
            )
            for item in _first_per_shape(raw)
        ]

    def _log_failure(self, check: str, exc: Exception) -> None:
        if self.suppress_diagnostics:
            log.warning("focus.probe_failed_in_protected_context", check=check)
        else:
            log.warning(f"focus.{check}_failed", error=str(exc))

    async def _check_obscured(self, page: Page) -> list[FocusFinding]:
        """SC 2.4.11, elements hidden behind a sticky/fixed overlay."""
        raw: Any = await page.evaluate(_OBSCURED_JS, self.max_focusable)
        findings: list[FocusFinding] = []
        seen: set[str] = set()
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            selector = str(item.get("selector") or "").strip()
            if not selector or selector in seen:
                continue
            seen.add(selector)
            cover = str(item.get("coverTag") or "overlay")
            findings.append(
                FocusFinding(
                    rule_id=RULE_FOCUS_OBSCURED,
                    target_selector=selector,
                    failure_summary=(
                        f"When focused, this element's centre is covered by a "
                        f"sticky/fixed <{cover}> overlay, so a keyboard user can't "
                        f"see what they've focused."
                    ),
                    html_snippet=str(item.get("html") or ""),
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


def _first_per_shape(raw: Any) -> list[dict[str, Any]]:
    """Up to ``_MAX_PER_RULE`` items, and one per tag-and-class shape."""
    out: list[dict[str, Any]] = []
    shapes: set[str] = set()
    for item in raw or []:
        if not isinstance(item, dict) or not str(item.get("selector") or "").strip():
            continue
        shape = str(item.get("shape") or item["selector"])
        if shape in shapes:
            continue
        shapes.add(shape)
        out.append(item)
        if len(out) >= _MAX_PER_RULE:
            break
    return out


async def _without_listeners(page: Page, count: int) -> set[int]:
    """Indexes of ``data-axcess-stop`` elements with no event listener at all."""
    session = await page.context.new_cdp_session(page)
    quiet: set[int] = set()
    try:
        for index in range(count):
            found = await session.send(
                "Runtime.evaluate",
                {"expression": f"document.querySelector('[data-axcess-stop=\"{index}\"]')"},
            )
            object_id = found.get("result", {}).get("objectId")
            if not object_id:
                continue
            listeners = await session.send(
                "DOMDebugger.getEventListeners", {"objectId": object_id, "depth": 0}
            )
            if not listeners.get("listeners"):
                quiet.add(index)
    finally:
        with contextlib.suppress(Exception):
            await page.evaluate(
                "() => document.querySelectorAll('[data-axcess-stop]')"
                ".forEach((el) => el.removeAttribute('data-axcess-stop'))"
            )
        with contextlib.suppress(Exception):
            await session.detach()
    return quiet
