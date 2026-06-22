"""SC 1.3.2 — Meaningful Sequence probe (VLM).

Screenshots the rendered page and lists its text content in DOM/source
order (the order a screen reader reads). A local vision model judges whether
the *visual* reading order in the screenshot matches that source order — CSS
(flex/grid ``order``, floats, absolute positioning) can make them diverge so
a screen-reader user hears a different, confusing sequence than a sighted
user sees.

Page-level: at most one finding per page. No-op (returns ``[]``) when no
vision provider is available, so a crawl without Ollama just skips it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from audit.analyzer.ollama_base import OllamaError
from audit.analyzer.visual.base import (
    RULE_MEANINGFUL_SEQUENCE,
    RULE_MOTION_NO_PAUSE,
    VisualFinding,
)
from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Page

    from audit.analyzer.vlm.vision import OllamaVisionProvider

log = get_logger(__name__)

# Block-level, text-bearing elements, in document order = the screen-reader
# reading sequence. Capped so a huge page can't blow the prompt.
_DOM_ORDER_JS = """
(cap) => {
  const out = [];
  const els = document.querySelectorAll(
    'h1,h2,h3,h4,h5,h6,p,li,blockquote,figcaption,td,th,dt,dd'
  );
  for (const el of els) {
    if (out.length >= cap) break;
    const t = (el.innerText || '').trim().replace(/\\s+/g, ' ');
    if (t) out.push(t.slice(0, 120));
  }
  return out;
}
"""

# SC 2.2.2 (deterministic): auto-moving content with no pause mechanism.
# High-confidence signals only — autoplay <video>/<audio> without a controls
# attribute (no built-in pause) and <marquee> (auto-scrolls, no pause). CSS
# animations / carousels are deliberately NOT flagged here: most are short or
# decorative, so flagging them would bury the real failures (a human checks
# those). Returns {selector, html, detail} per offender.
_MOTION_JS = """
() => {
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
  for (const v of document.querySelectorAll('video[autoplay], audio[autoplay]')) {
    if (!v.hasAttribute('controls')) {
      out.push({
        selector: cssPath(v),
        html: (v.outerHTML || '').slice(0, 240),
        detail: v.tagName.toLowerCase() + ' autoplays with no controls (no pause mechanism)',
      });
    }
  }
  for (const m of document.querySelectorAll('marquee')) {
    out.push({
      selector: cssPath(m),
      html: (m.outerHTML || '').slice(0, 240),
      detail: '<marquee> auto-scrolls with no pause/stop control',
    });
  }
  return out;
}
"""

_PROMPT = """You are a WCAG 2.2 specialist evaluating SC 1.3.2 Meaningful Sequence (Level A).

The attached screenshot shows a rendered web page. Below is that page's text content listed in
DOM / source order — the order a screen reader reads it.

Question: does the VISUAL reading order in the screenshot (top-to-bottom, then
left-to-right) match this source order? A FAILURE is when CSS (flex/grid `order`,
floats, absolute positioning, RTL) makes the visual order differ from the source
order, so a screen-reader user hears content in a different, confusing sequence
than a sighted user sees.

Only report a mismatch when the divergence would affect MEANING or comprehension.
Trivial differences, or content you can't clearly correlate, are NOT failures.
When unsure, report no mismatch.

Source order:
{blocks}

Return ONLY this JSON (no prose):
{{"mismatch": <true|false>, "reason": "<one sentence>", "confidence": "<high|medium|low>"}}
"""

_MAX_BLOCKS = 60


@dataclass
class VisualProbe:
    """Runs the visual-pipeline checks on a live page.

    - SC 2.2.2 (deterministic): auto-moving content with no pause mechanism.
      Always runs — no model needed.
    - SC 1.3.2 (VLM): visual reading order vs DOM order. Only runs when a
      vision ``provider`` is supplied; no-ops otherwise.
    """

    provider: OllamaVisionProvider | None = None
    max_blocks: int = _MAX_BLOCKS

    async def run(self, page: Page) -> list[VisualFinding]:
        """Run both checks. Never raises — each is isolated."""
        findings: list[VisualFinding] = []
        try:
            findings.extend(await self._check_motion(page))
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("visual.motion_failed", error=str(exc))
        try:
            findings.extend(await self._check_meaningful_sequence(page))
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("visual.sequence_failed", error=str(exc))
        return findings

    async def _check_motion(self, page: Page) -> list[VisualFinding]:
        """SC 2.2.2 — autoplay media without controls / <marquee>."""
        raw: Any = await page.evaluate(_MOTION_JS)
        findings: list[VisualFinding] = []
        seen: set[str] = set()
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            selector = str(item.get("selector") or "").strip()
            if not selector or selector in seen:
                continue
            seen.add(selector)
            detail = str(item.get("detail") or "auto-moving content with no pause control")
            findings.append(
                VisualFinding(
                    rule_id=RULE_MOTION_NO_PAUSE,
                    target_selector=selector,
                    failure_summary=(
                        f"{detail}. Content that moves for more than 5 seconds must have a "
                        f"way to pause, stop, or hide it."
                    ),
                    html_snippet=str(item.get("html") or ""),
                    help=(
                        "Add a visible pause/stop control (e.g. the <video controls> "
                        "attribute), or don't autoplay; replace <marquee> with static "
                        "or user-controlled motion."
                    ),
                    criterion_sc="2.2.2",
                    wcag_level="A",
                )
            )
        return findings

    async def _check_meaningful_sequence(self, page: Page) -> list[VisualFinding]:
        """SC 1.3.2 — visual reading order vs DOM order (VLM)."""
        if self.provider is None:
            return []
        blocks: Any = await page.evaluate(_DOM_ORDER_JS, self.max_blocks)
        if not blocks:
            return []
        screenshot = await page.screenshot()

        numbered = "\n".join(f"{i}. {b}" for i, b in enumerate(blocks))
        prompt = _PROMPT.format(blocks=numbered)
        try:
            raw = await self.provider.describe_json(screenshot, prompt)
        except OllamaError as exc:
            log.warning("visual.vlm_failed", error=str(exc))
            return []

        if not raw.get("mismatch"):
            return []

        reason = raw.get("reason")
        reason = reason.strip()[:500] if isinstance(reason, str) else ""
        confidence = raw.get("confidence")
        confidence = confidence.strip().lower() if isinstance(confidence, str) else "medium"
        impact = {"high": "serious", "medium": "moderate", "low": "minor"}.get(
            confidence, "moderate"
        )
        return [
            VisualFinding(
                rule_id=RULE_MEANINGFUL_SEQUENCE,
                target_selector="body",
                failure_summary=(
                    reason
                    or "The visual reading order doesn't match the DOM order, so screen-reader "
                    "users get a different sequence than sighted users."
                ),
                html_snippet="",
                help=(
                    "Make the DOM/source order match the intended reading order; use CSS for "
                    "visual placement rather than reordering content out of its logical sequence "
                    "(avoid flex/grid `order` that diverges from meaning)."
                ),
                impact=impact,
            )
        ]
