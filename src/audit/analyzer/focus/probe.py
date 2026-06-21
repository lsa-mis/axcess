"""SC 2.4.11 — Focus Not Obscured (Minimum) probe.

Deterministic, no model. In one ``page.evaluate`` it focuses each focusable
element and checks whether the element's centre is covered by a
``position:fixed`` / ``sticky`` overlay (the classic "focus disappears
behind the sticky header" failure). Conservative on purpose — it samples
the centre point, so it flags elements that are substantially obscured, not
ones merely clipped at an edge. Edge cases (transforms, partial overlap)
still need a human; the coverage matrix marks this ``partial``.
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

# Cap how many focusable elements we test per page — bounds the worst case
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
# overrides DOM order. Deterministic + high-confidence — return every
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


@dataclass
class FocusProbe:
    """Runs the SC 2.4.11 focus-obscured check against a live page."""

    max_focusable: int = MAX_FOCUSABLE

    async def run(self, page: Page) -> list[FocusFinding]:
        """Run both focus checks. Never raises — each check is isolated so
        one failing doesn't lose the other's findings."""
        findings: list[FocusFinding] = []
        try:
            findings.extend(await self._check_obscured(page))
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("focus.obscured_failed", error=str(exc))
        try:
            findings.extend(await self._check_positive_tabindex(page))
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("focus.tabindex_failed", error=str(exc))
        return findings

    async def _check_obscured(self, page: Page) -> list[FocusFinding]:
        """SC 2.4.11 — elements hidden behind a sticky/fixed overlay."""
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
                        "Keep focused elements visible — add scroll-margin / "
                        "scroll-padding so they aren't hidden behind sticky headers, "
                        "or reduce the sticky element's height."
                    ),
                )
            )
        return findings

    async def _check_positive_tabindex(self, page: Page) -> list[FocusFinding]:
        """SC 2.4.3 (WCAG F44) — positive tabindex forces a manual tab order."""
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
