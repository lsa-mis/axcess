"""Playwright-driven responsive / zoom / text-spacing probe.

Three checks, all impossible from static HTML and absent from axe-core:

1. **Reflow at 320 px (SC 1.4.10)**, resize the viewport to 320x900 and
   check whether the document needs a horizontal scrollbar. WCAG's
   reflow criterion says content must be usable at 320 CSS px without
   two-dimensional scrolling. The probe also walks the DOM for the
   widest offending elements so the finding names the culprit, not just
   the symptom.

2. **Text clipping at ~200% zoom (SC 1.4.4)**, 640x450 viewport is the
   standard automation proxy for 200% zoom at a 1280 desktop width.
   Leaf elements with ``overflow: hidden`` whose ``scrollWidth`` exceeds
   their ``clientWidth`` are losing characters. ``text-overflow:
   ellipsis`` elements are skipped, designed truncation is a judgment
   call for a human, and flagging it would bury real failures in noise.

3. **Text-spacing override (SC 1.4.12)**, inject the canonical WCAG
   spacing CSS (line-height 1.5, letter-spacing 0.12 em, word-spacing
   0.16 em, paragraph spacing 2 em) and re-run the clipping detector.
   Sites that hard-code container heights clip when users apply their
   own readability stylesheets; this is exactly the technique our own
   UI gate (tests/ui/test_accessibility_text_spacing.py) uses.

Checks 2 and 3 share one detector, and both are a comparison, not a single
reading. SC 1.4.4 is about content lost *by resizing* and SC 1.4.12 about
content lost *by the spacing*, so text counts only when:

* it is cut off under the test condition (the zoom viewport, or the
  spacing override); and
* the same element shows the same text, uncut and visible, without that
  condition (the crawl's normal viewport, or no override).

Text that is hidden from sight on purpose is never reported: the
visually-hidden pattern for screen-reader text (``.sr-only``: a 1px box
with ``overflow: hidden`` and ``clip: rect(0 0 0 0)`` or ``clip-path:
inset(50%)``), ``opacity: 0``, ``visibility: hidden``, and closed panels.
Such text paints no pixel at any size, so neither criterion applies to it,
and a single reading used to report it as "content 262px in a 1px box".
Text that is already cut off before the test condition is not reported by
these two checks either: resizing or spacing did not cause it. Limit: text
that only exists in the narrow layout (for example a mobile-only label) has
nothing at the normal viewport to compare with, so it is not judged.

Ordering contract: the probe MUTATES the page (viewport size, injected
CSS). It must run LAST in ``JsFetcher.fetch``, after the HTML capture,
after axe, after the keyboard probe, and it restores the original
viewport before returning so any later consumer isn't surprised.

Safety: same posture as the keyboard probe. Every check is wrapped, a
failure logs at WARNING and contributes zero findings; element walks are
capped (``_MAX_ELEMENTS_SCANNED``, ``_MAX_OFFENDERS_PER_CHECK``) so a
pathological page can't stall the crawl.
"""

# This module builds JS snippets with ``%``-formatting (str.format would
# collide with the JS ``{}`` braces). UP031 is intentional throughout.
# ruff: noqa: UP031

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
    from playwright.async_api import JSHandle, Page

log = logging.getLogger(__name__)

# Viewports. 320 is WCAG 1.4.10's literal number; 640x450 is the
# accepted 200%-zoom-at-1280 proxy used by most automated checkers.
_REFLOW_VIEWPORT = {"width": 320, "height": 900}
_ZOOM_VIEWPORT = {"width": 640, "height": 450}

# Horizontal slop allowed before "needs a horizontal scrollbar" fires.
# Scrollbar-width rounding and 1-2px subpixel overflows are not real
# reflow failures.
_OVERFLOW_TOLERANCE_PX = 8

# Walk caps, bound the per-check JS work on pathological pages.
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

# How many cut-off elements the detector carries from the test condition
# to the comparison. Higher than ``_MAX_OFFENDERS_PER_CHECK`` because some
# will turn out to be cut off without the condition too, and those must not
# use up the report's five places.
_MAX_CLIP_CANDIDATES = 200

# Helpers shared by the two halves of the clipped-text detector.
#
# ``hiddenOnPurpose`` has a twin in audit/analyzer/focus/probe.py
# (``paintsNothing``). Keep the two in step.
_CLIP_HELPERS_JS = """
  const sel = (el) => {
    const tag = el.tagName.toLowerCase();
    if (el.id) return tag + '#' + el.id;
    if (el.className && typeof el.className === 'string') {
      const cls = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
      if (cls) return tag + '.' + cls;
    }
    return tag;
  };
  // Is the element's own box cutting off its text, and in which direction?
  // Ellipsis elements never count (designed truncation, human judgment).
  const clipState = (el) => {
    const cs = getComputedStyle(el);
    const hidesX = cs.overflowX === 'hidden' || cs.overflow === 'hidden';
    const hidesY = cs.overflowY === 'hidden' || cs.overflow === 'hidden';
    if ((!hidesX && !hidesY) || cs.textOverflow === 'ellipsis') {
      return { clipX: false, clipY: false };
    }
    return {
      clipX: hidesX && el.scrollWidth > el.clientWidth + 4,
      clipY: hidesY && el.scrollHeight > el.clientHeight + 4,
    };
  };
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
  // Is this text kept out of sight on purpose, by the element or anything
  // around it?  Always: not displayed, visibility hidden, opacity 0, a clip
  // that leaves no area, or a box of at most 1px by 1px that cuts off its
  // content (the visually-hidden pattern).  With `closedCounts`, a box
  // collapsed to 1px or less in ONE direction counts too (a closed panel).
  // That stricter test is only for "is it visible at the normal size":
  // under the test condition a box squeezed to nothing is the very loss
  // these checks exist to find.
  const hiddenOnPurpose = (el, closedCounts) => {
    if (getComputedStyle(el).visibility !== 'visible') return true;
    for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
      const cs = getComputedStyle(cur);
      if (cs.display === 'none') return true;
      if (parseFloat(cs.opacity) === 0) return true;
      if ((cs.position === 'absolute' || cs.position === 'fixed')
          && emptyClipRect(cs.clip)) return true;
      if (emptyClipPath(cs.clipPath)) return true;
      if (cur instanceof HTMLElement
          && cs.display !== 'inline' && cs.display !== 'contents'
          && cs.overflowX !== 'visible' && cs.overflowY !== 'visible'
          && cur.getClientRects().length) {
        const w = cur.clientWidth;
        const h = cur.clientHeight;
        if (w <= 1 && h <= 1) return true;
        if (closedCounts && (w <= 1 || h <= 1)) return true;
      }
    }
    return false;
  };
"""

# First half, run UNDER the test condition (zoom viewport, or spacing
# override): leaf elements whose text their own box cuts off, leaving out
# text hidden on purpose. Returns records that keep the element itself, so
# it must be called with ``evaluate_handle``.
_CLIP_CANDIDATES_JS = """
(maxCandidates) => {
%(helpers)s
  const out = [];
  const els = document.querySelectorAll('body *');
  const limit = Math.min(els.length, %(scan_cap)d);
  for (let i = 0; i < limit && out.length < maxCandidates; i++) {
    const el = els[i];
    if (el.children.length > 0) continue;            // leaf nodes only
    const text = (el.innerText || '').trim();
    if (!text) continue;
    const c = clipState(el);
    if (!c.clipX && !c.clipY) continue;
    if (hiddenOnPurpose(el, false)) continue;        // paints no pixel
    out.push({
      el: el,
      clipX: c.clipX,
      clipY: c.clipY,
      contentW: el.scrollWidth,
      boxW: el.clientWidth,
      contentH: el.scrollHeight,
      boxH: el.clientHeight,
      text: text.slice(0, 40),
      selector: sel(el),
      html: (el.outerHTML || '').slice(0, 240),
    });
  }
  return out;
}
""" % {"helpers": _CLIP_HELPERS_JS, "scan_cap": _MAX_ELEMENTS_SCANNED}

# Second half, run WITHOUT the test condition on the records from the first
# half. Keeps a record only when the same element is still on the page,
# visible, and not cut off in the direction it was cut off before. Returns
# up to `max` {selector, html, detail}.
_CLIP_CONFIRM_JS = """
([candidates, maxOffenders]) => {
%(helpers)s
  const out = [];
  for (const c of candidates) {
    if (out.length >= maxOffenders) break;
    const el = c.el;
    if (!el || !el.isConnected) continue;            // gone, e.g. a status message
    if (!el.getClientRects().length) continue;       // not shown at all here
    if (!(el.innerText || '').trim()) continue;
    if (hiddenOnPurpose(el, true)) continue;         // not visible here
    const now = clipState(el);
    const newX = c.clipX && !now.clipX;
    const newY = c.clipY && !now.clipY;
    if (!newX && !newY) continue;                    // cut off here as well
    out.push({
      selector: c.selector,
      html: c.html,
      detail: (newX ? 'clipped horizontally' : 'clipped vertically')
        + ': content ' + (newX ? c.contentW : c.contentH) + 'px'
        + ' in a ' + (newX ? c.boxW : c.boxH) + 'px box'
        + '; text starts "' + c.text + '"',
    });
  }
  return out;
}
""" % {"helpers": _CLIP_HELPERS_JS}

# Reflow detector: does the document need a horizontal scrollbar at the
# current (320px) viewport, and which elements are wider than it?
_REFLOW_JS = """
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
""" % {
    "tolerance": _OVERFLOW_TOLERANCE_PX,
    "scan_cap": _MAX_ELEMENTS_SCANNED,
    "max_offenders": _MAX_OFFENDERS_PER_CHECK,
}


@dataclass
class ResponsiveProbe:
    """Reusable probe. Construct once per crawl, call :meth:`run` per page."""

    base_viewport_width: int = 1440
    base_viewport_height: int = 900
    # Protected browsers may surface URL/content fragments in an exception.
    # Keep logs terse when the companion asks for a private diagnostic mode.
    suppress_diagnostics: bool = False

    async def run(self, page: Page) -> list[ResponsiveFinding]:
        """Probe ``page``; returns findings, never raises.

        Restores the original viewport on exit regardless of failures —
        the page object may still be inspected by a caller afterwards.
        """
        findings: list[ResponsiveFinding] = []
        try:
            findings.extend(await self._check_reflow(page))
        except Exception as exc:
            self._log_failure("reflow", exc)
        try:
            findings.extend(await self._check_zoom_clipping(page))
        except Exception as exc:
            self._log_failure("zoom_clipping", exc)
        try:
            findings.extend(await self._check_text_spacing(page))
        except Exception as exc:
            self._log_failure("text_spacing", exc)
        # Always restore the crawl's standard viewport.
        with contextlib.suppress(Exception):
            await page.set_viewport_size(
                {"width": self.base_viewport_width, "height": self.base_viewport_height}
            )
        return findings

    def _log_failure(self, check: str, exc: Exception) -> None:
        if self.suppress_diagnostics:
            log.warning("responsive.%s_failed_in_protected_context", check)
        else:
            log.warning("responsive.%s_failed: %s", check, exc)

    # -----------------------------------------------------------------
    # Check 1, reflow at 320 px (SC 1.4.10).
    # -----------------------------------------------------------------

    async def _check_reflow(self, page: Page) -> list[ResponsiveFinding]:
        await page.set_viewport_size(_REFLOW_VIEWPORT)  # type: ignore[arg-type]
        # Give responsive CSS a beat to settle (media queries, JS resize
        # handlers). 150ms is enough for CSS; deliberately not waiting
        # for JS frameworks, a page that needs seconds to reflow has
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
    # Check 2, text clipping at the 200% zoom proxy (SC 1.4.4).
    # -----------------------------------------------------------------

    async def _check_zoom_clipping(self, page: Page) -> list[ResponsiveFinding]:
        await page.set_viewport_size(_ZOOM_VIEWPORT)  # type: ignore[arg-type]
        await page.wait_for_timeout(150)
        candidates = await page.evaluate_handle(_CLIP_CANDIDATES_JS, _MAX_CLIP_CANDIDATES)
        try:
            if not await candidates.evaluate("(c) => c.length"):
                return []
            # The comparison: back at the normal viewport, is the same text
            # visible and uncut? Only then did resizing lose it.
            await page.set_viewport_size(
                {"width": self.base_viewport_width, "height": self.base_viewport_height}
            )
            await page.wait_for_timeout(150)
            clipped: list[dict[str, str]] = await page.evaluate(
                _CLIP_CONFIRM_JS, [candidates, _MAX_OFFENDERS_PER_CHECK]
            )
        finally:
            with contextlib.suppress(Exception):
                await candidates.dispose()
        return [
            ResponsiveFinding(
                rule_id=RULE_TEXT_CLIPPED,
                criterion_sc="1.4.4",
                impact="serious",
                target_selector=str(c.get("selector", "(unknown)")),
                failure_summary=(
                    f"At ~200% zoom (640px viewport proxy) text is {c.get('detail', 'clipped')}. "
                    f"At the normal {self.base_viewport_width}px-wide viewport this element "
                    "does not cut off its text. "
                    "WCAG 1.4.4 requires text to remain readable when resized up to 200%."
                ),
                html_snippet=str(c.get("html", "")),
                help="Text must stay visible and readable at 200% zoom.",
            )
            for c in clipped
        ]

    # -----------------------------------------------------------------
    # Check 3, WCAG text-spacing override (SC 1.4.12).
    # -----------------------------------------------------------------

    async def _check_text_spacing(self, page: Page) -> list[ResponsiveFinding]:
        # Run at the crawl's standard viewport, spacing failures are
        # about hard-coded boxes, not narrow screens, and running at
        # 320px would double-report what the reflow check already saw.
        await page.set_viewport_size(
            {"width": self.base_viewport_width, "height": self.base_viewport_height}
        )
        handle = await page.add_style_tag(content=_TEXT_SPACING_CSS)
        try:
            await page.wait_for_timeout(100)
            candidates: JSHandle = await page.evaluate_handle(
                _CLIP_CANDIDATES_JS, _MAX_CLIP_CANDIDATES
            )
        finally:
            # Remove the injected sheet so the page is clean if anything
            # inspects it later in the fetch lifecycle. Removing it also sets
            # up the comparison: the same elements, without the override. If
            # the removal fails, every candidate is still cut off below and
            # nothing is reported, which is the safe way to be wrong.
            with contextlib.suppress(Exception):
                await handle.evaluate("el => el.remove()")
        try:
            if not await candidates.evaluate("(c) => c.length"):
                return []
            await page.wait_for_timeout(100)
            clipped: list[dict[str, str]] = await page.evaluate(
                _CLIP_CONFIRM_JS, [candidates, _MAX_OFFENDERS_PER_CHECK]
            )
        finally:
            with contextlib.suppress(Exception):
                await candidates.dispose()
        return [
            ResponsiveFinding(
                rule_id=RULE_SPACING_CLIPPED,
                criterion_sc="1.4.12",
                impact="serious",
                target_selector=str(c.get("selector", "(unknown)")),
                failure_summary=(
                    "With WCAG's text-spacing override applied (line-height "
                    "1.5, letter-spacing 0.12em, word-spacing 0.16em) text is "
                    f"{c.get('detail', 'clipped')}. Without the override this "
                    "element does not cut off its text. Users who apply their "
                    "own readability stylesheets lose this content."
                ),
                html_snippet=str(c.get("html", "")),
                help="Content must not clip when users override text spacing.",
            )
            for c in clipped
        ]
