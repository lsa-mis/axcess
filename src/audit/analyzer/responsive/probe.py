"""Playwright-driven responsive / zoom / text-spacing probe.

Three checks, all impossible from static HTML and absent from axe-core:

1. **Reflow at 320 px (SC 1.4.10)** — resize the viewport to 320x900 and
   check whether the document needs a horizontal scrollbar. WCAG's
   reflow criterion says content must be usable at 320 CSS px without
   two-dimensional scrolling. The probe also walks the DOM for the
   widest offending elements so the finding names the culprit, not just
   the symptom.

2. **Text clipping at ~200% zoom (SC 1.4.4)** — 640x450 viewport is the
   standard automation proxy for 200% zoom at a 1280 desktop width.
   Leaf elements with ``overflow: hidden`` whose ``scrollWidth`` exceeds
   their ``clientWidth`` are losing characters. ``text-overflow:
   ellipsis`` elements are skipped — designed truncation is a judgment
   call for a human, and flagging it would bury real failures in noise.

3. **Text-spacing override (SC 1.4.12)** — inject the canonical WCAG
   spacing CSS (line-height 1.5, letter-spacing 0.12 em, word-spacing
   0.16 em, paragraph spacing 2 em) and re-run the clipping detector.
   Sites that hard-code container heights clip when users apply their
   own readability stylesheets; this is exactly the technique our own
   UI gate (tests/ui/test_accessibility_text_spacing.py) uses.

Ordering contract: the probe MUTATES the page (viewport size, injected
CSS). It must run LAST in ``JsFetcher.fetch`` — after the HTML capture,
after axe, after the keyboard probe — and it restores the original
viewport before returning so any later consumer isn't surprised.

Safety: same posture as the keyboard probe. Every check is wrapped, a
failure logs at WARNING and contributes zero findings; element walks are
capped (``_MAX_ELEMENTS_SCANNED``, ``_MAX_OFFENDERS_PER_CHECK``) so a
pathological page can't stall the crawl.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from audit.analyzer.responsive.base import (
    RULE_REFLOW,
    RULE_SPACING_CLIPPED,
    RULE_TEXT_CLIPPED,
    ResponsiveFinding,
)

if TYPE_CHECKING:
    from playwright.async_api import Page

log = logging.getLogger(__name__)

# Viewports. 320 is WCAG 1.4.10's literal number; 640x450 is the
# accepted 200%-zoom-at-1280 proxy used by most automated checkers.
_REFLOW_VIEWPORT = {"width": 320, "height": 900}
_ZOOM_VIEWPORT = {"width": 640, "height": 450}

# Horizontal slop allowed before "needs a horizontal scrollbar" fires.
# Scrollbar-width rounding and 1-2px subpixel overflows are not real
# reflow failures.
_OVERFLOW_TOLERANCE_PX = 8

# Walk caps — bound the per-check JS work on pathological pages.
_MAX_ELEMENTS_SCANNED = 2000
_MAX_OFFENDERS_PER_CHECK = 5

# The canonical SC 1.4.12 override stylesheet, verbatim from the
# Understanding doc's test procedure.
_TEXT_SPACING_CSS = """
* {
  line-height: 1.5 !important;
  letter-spacing: 0.12em !important;
  word-spacing: 0.16em !important;
}
p {
  margin-bottom: 2em !important;
}
"""

# Shared JS: find leaf elements whose text is clipped by overflow:hidden.
# Returns up to `max` {selector, html, detail} records. Ellipsis elements
# are skipped (designed truncation — human judgment, not an auto-fail).
_CLIPPED_TEXT_JS = """
(maxOffenders) => {
  const out = [];
  const els = document.querySelectorAll('body *');
  const limit = Math.min(els.length, %(scan_cap)d);
  const sel = (el) => {
    const tag = el.tagName.toLowerCase();
    if (el.id) return tag + '#' + el.id;
    if (el.className && typeof el.className === 'string') {
      const cls = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
      if (cls) return tag + '.' + cls;
    }
    return tag;
  };
  for (let i = 0; i < limit && out.length < maxOffenders; i++) {
    const el = els[i];
    if (el.children.length > 0) continue;            // leaf nodes only
    const text = (el.innerText || '').trim();
    if (!text) continue;
    const cs = getComputedStyle(el);
    const hidesX = cs.overflowX === 'hidden' || cs.overflow === 'hidden';
    const hidesY = cs.overflowY === 'hidden' || cs.overflow === 'hidden';
    if (!hidesX && !hidesY) continue;
    if (cs.textOverflow === 'ellipsis') continue;    // designed truncation
    const clipX = hidesX && el.scrollWidth > el.clientWidth + 4;
    const clipY = hidesY && el.scrollHeight > el.clientHeight + 4;
    if (!clipX && !clipY) continue;
    out.push({
      selector: sel(el),
      html: (el.outerHTML || '').slice(0, 240),
      detail: (clipX ? 'clipped horizontally' : 'clipped vertically')
        + ': content ' + (clipX ? el.scrollWidth : el.scrollHeight) + 'px'
        + ' in a ' + (clipX ? el.clientWidth : el.clientHeight) + 'px box'
        + '; text starts "' + text.slice(0, 40) + '"',
    });
  }
  return out;
}
""" % {"scan_cap": _MAX_ELEMENTS_SCANNED}  # noqa: UP031 — JS braces break str.format

# Reflow detector: does the document need a horizontal scrollbar at the
# current (320px) viewport, and which elements are wider than it?
_REFLOW_JS = (
    """
() => {
  const doc = document.scrollingElement || document.documentElement;
  const overflow = doc.scrollWidth - doc.clientWidth;
  if (overflow <= %(tolerance)d) return null;
  const out = [];
  const els = document.querySelectorAll('body *');
  const limit = Math.min(els.length, %(scan_cap)d);
  const sel = (el) => {
    const tag = el.tagName.toLowerCase();
    if (el.id) return tag + '#' + el.id;
    if (el.className && typeof el.className === 'string') {
      const cls = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
      if (cls) return tag + '.' + cls;
    }
    return tag;
  };
  for (let i = 0; i < limit && out.length < %(max_offenders)d; i++) {
    const el = els[i];
    const r = el.getBoundingClientRect();
    // An offender is wider than the viewport itself. Prefer shallow
    // containers (the widest leaf-ish culprit) over wrappers that
    // merely inherit the overflow.
    if (r.width > doc.clientWidth + %(tolerance)d && el.children.length < 10) {
      out.push({
        selector: sel(el),
        html: (el.outerHTML || '').slice(0, 240),
        width: Math.round(r.width),
      });
    }
  }
  return { overflow: overflow, viewport: doc.clientWidth, offenders: out };
}
"""
    % {  # noqa: UP031 — JS braces break str.format
        "tolerance": _OVERFLOW_TOLERANCE_PX,
        "scan_cap": _MAX_ELEMENTS_SCANNED,
        "max_offenders": _MAX_OFFENDERS_PER_CHECK,
    }
)


@dataclass
class ResponsiveProbe:
    """Reusable probe. Construct once per crawl, call :meth:`run` per page."""

    base_viewport_width: int = 1440
    base_viewport_height: int = 900

    async def run(self, page: Page) -> list[ResponsiveFinding]:
        """Probe ``page``; returns findings, never raises.

        Restores the original viewport on exit regardless of failures —
        the page object may still be inspected by a caller afterwards.
        """
        findings: list[ResponsiveFinding] = []
        try:
            findings.extend(await self._check_reflow(page))
        except Exception as exc:
            log.warning("responsive.reflow_failed: %s", exc)
        try:
            findings.extend(await self._check_zoom_clipping(page))
        except Exception as exc:
            log.warning("responsive.zoom_clipping_failed: %s", exc)
        try:
            findings.extend(await self._check_text_spacing(page))
        except Exception as exc:
            log.warning("responsive.text_spacing_failed: %s", exc)
        # Always restore the crawl's standard viewport.
        with contextlib.suppress(Exception):
            await page.set_viewport_size(
                {"width": self.base_viewport_width, "height": self.base_viewport_height}
            )
        return findings

    # -----------------------------------------------------------------
    # Check 1 — reflow at 320 px (SC 1.4.10).
    # -----------------------------------------------------------------

    async def _check_reflow(self, page: Page) -> list[ResponsiveFinding]:
        await page.set_viewport_size(_REFLOW_VIEWPORT)  # type: ignore[arg-type]
        # Give responsive CSS a beat to settle (media queries, JS resize
        # handlers). 150ms is enough for CSS; deliberately not waiting
        # for JS frameworks — a page that needs seconds to reflow has
        # bigger problems and we'd rather under- than over-wait.
        await page.wait_for_timeout(150)
        result: dict[str, Any] | None = await page.evaluate(_REFLOW_JS)
        if not result:
            return []
        offenders = result.get("offenders") or []
        if not offenders:
            # The document overflows but no single element stood out
            # (e.g. accumulated margins). Still a real reflow failure —
            # report it once against the document.
            offenders = [
                {
                    "selector": "html",
                    "html": "",
                    "width": result["viewport"] + result["overflow"],
                }
            ]
        return [
            ResponsiveFinding(
                rule_id=RULE_REFLOW,
                criterion_sc="1.4.10",
                impact="serious",
                target_selector=str(o.get("selector", "html")),
                failure_summary=(
                    f"At a 320px viewport this element is {o.get('width', '?')}px wide, "
                    f"forcing {result['overflow']}px of horizontal scrolling. WCAG 1.4.10 "
                    "requires content to reflow to 320 CSS px without two-dimensional "
                    "scrolling."
                ),
                html_snippet=str(o.get("html", "")),
                help="Content must reflow to a 320px-wide viewport without horizontal scrolling.",
            )
            for o in offenders
        ]

    # -----------------------------------------------------------------
    # Check 2 — text clipping at the 200% zoom proxy (SC 1.4.4).
    # -----------------------------------------------------------------

    async def _check_zoom_clipping(self, page: Page) -> list[ResponsiveFinding]:
        await page.set_viewport_size(_ZOOM_VIEWPORT)  # type: ignore[arg-type]
        await page.wait_for_timeout(150)
        clipped: list[dict[str, str]] = await page.evaluate(
            _CLIPPED_TEXT_JS, _MAX_OFFENDERS_PER_CHECK
        )
        return [
            ResponsiveFinding(
                rule_id=RULE_TEXT_CLIPPED,
                criterion_sc="1.4.4",
                impact="serious",
                target_selector=str(c.get("selector", "(unknown)")),
                failure_summary=(
                    f"At ~200% zoom (640px viewport proxy) text is {c.get('detail', 'clipped')}. "
                    "WCAG 1.4.4 requires text to remain readable when resized up to 200%."
                ),
                html_snippet=str(c.get("html", "")),
                help="Text must stay visible and readable at 200% zoom.",
            )
            for c in clipped
        ]

    # -----------------------------------------------------------------
    # Check 3 — WCAG text-spacing override (SC 1.4.12).
    # -----------------------------------------------------------------

    async def _check_text_spacing(self, page: Page) -> list[ResponsiveFinding]:
        # Run at the crawl's standard viewport — spacing failures are
        # about hard-coded boxes, not narrow screens, and running at
        # 320px would double-report what the reflow check already saw.
        await page.set_viewport_size(
            {"width": self.base_viewport_width, "height": self.base_viewport_height}
        )
        handle = await page.add_style_tag(content=_TEXT_SPACING_CSS)
        try:
            await page.wait_for_timeout(100)
            clipped: list[dict[str, str]] = await page.evaluate(
                _CLIPPED_TEXT_JS, _MAX_OFFENDERS_PER_CHECK
            )
        finally:
            # Remove the injected sheet so the page is clean if anything
            # inspects it later in the fetch lifecycle.
            with contextlib.suppress(Exception):
                await handle.evaluate("el => el.remove()")
        return [
            ResponsiveFinding(
                rule_id=RULE_SPACING_CLIPPED,
                criterion_sc="1.4.12",
                impact="serious",
                target_selector=str(c.get("selector", "(unknown)")),
                failure_summary=(
                    "With WCAG's text-spacing override applied (line-height "
                    "1.5, letter-spacing 0.12em, word-spacing 0.16em) text is "
                    f"{c.get('detail', 'clipped')}. Users who apply their own "
                    "readability stylesheets lose this content."
                ),
                html_snippet=str(c.get("html", "")),
                help="Content must not clip when users override text spacing.",
            )
            for c in clipped
        ]
