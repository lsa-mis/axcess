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
from audit.analyzer.visual.base import RULE_MEANINGFUL_SEQUENCE, VisualFinding
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
class MeaningfulSequenceProbe:
    """SC 1.3.2 probe. Construct with a vision provider; ``run`` per page."""

    provider: OllamaVisionProvider | None = None
    max_blocks: int = _MAX_BLOCKS

    async def run(self, page: Page) -> list[VisualFinding]:
        """Return at most one finding. Never raises; no-op without a provider."""
        if self.provider is None:
            return []
        try:
            blocks: Any = await page.evaluate(_DOM_ORDER_JS, self.max_blocks)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("visual.dom_order_failed", error=str(exc))
            return []
        if not blocks:
            return []
        try:
            screenshot = await page.screenshot()
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("visual.screenshot_failed", error=str(exc))
            return []

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
