"""SC 1.3.2, Meaningful Sequence probe (VLM).

Screenshots the rendered page and lists its text content in DOM/source
order (the order a screen reader reads). A local vision model judges whether
the *visual* reading order in the screenshot matches that source order, CSS
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
    RULE_AUTOPLAY_AUDIO_NO_CONTROL,
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

# Runtime media check. Markup alone is not evidence that media played: a
# missing/blocked resource, browser autoplay policy, or a zero-length asset can
# all leave an ``autoplay`` element inert. Measure ``currentTime`` instead and
# apply the correct criterion: visible video motion is SC 2.2.2; audible audio
# is SC 1.4.2. Marquee remains a manual-review lead because its duration and
# any custom control still require page-context review.
_MOTION_JS = """
async () => {
  const cssPath = (el) => {
    if (el.id) return el.tagName.toLowerCase() + '#' + el.id;
    let p = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const c = el.className.trim().split(/\\s+/)[0];
      if (c) p += '.' + c;
    }
    return p;
  };
  const hasCustomControl = (media) => {
    if (media.controls || media.hasAttribute('controls')) return true;
    if (!media.id) return false;
    const escaped = (window.CSS && CSS.escape) ? CSS.escape(media.id) : media.id;
    const controls = document.querySelectorAll(`[aria-controls~="${escaped}"]`);
    return Array.from(controls).some((control) => {
      const label = [control.getAttribute('aria-label'), control.getAttribute('title'),
        control.textContent].filter(Boolean).join(' ').toLowerCase();
      return /\b(pause|stop|mute|audio|video|playback)\b/.test(label);
    });
  };
  const candidates = Array.from(
    document.querySelectorAll('video[autoplay], audio[autoplay]')
  ).filter((media) => !hasCustomControl(media)).map((media) => ({
    media,
    start: Number(media.currentTime || 0),
  }));
  await new Promise((resolve) => setTimeout(resolve, 350));
  const out = [];
  for (const {media, start} of candidates) {
    const end = Number(media.currentTime || 0);
    const advanced = end - start;
    const duration = Number(media.duration);
    const active = !media.paused && !media.ended && media.readyState >= 2 && advanced > 0.05;
    if (!active) continue;
    const tag = media.tagName.toLowerCase();
    const longEnough = !Number.isFinite(duration) || duration > (tag === 'audio' ? 3 : 5);
    if (!longEnough) continue;
    if (tag === 'video') {
      const rect = media.getBoundingClientRect();
      const style = getComputedStyle(media);
      const visible = rect.width > 2 && rect.height > 2 && style.display !== 'none' &&
        style.visibility !== 'hidden' && Number(style.opacity || 1) > 0;
      if (!visible) continue;
    } else if (media.muted || media.volume <= 0) {
      continue;
    }
    out.push({
      kind: tag === 'audio' ? 'audio' : 'video',
      selector: cssPath(media),
      html: (media.outerHTML || '').slice(0, 240),
      detail: `Runtime playback measurement: ${tag} currentTime advanced ` +
        `${advanced.toFixed(2)} seconds; duration is ` +
        `${Number.isFinite(duration) ? duration.toFixed(2) + ' seconds' : 'continuous'}`,
    });
  }
  for (const m of document.querySelectorAll('marquee')) {
    out.push({
      kind: 'motion_review',
      selector: cssPath(m),
      html: (m.outerHTML || '').slice(0, 240),
      detail: '<marquee> creates moving content; confirm that it lasts more than 5 seconds ' +
        'or repeats, and that no custom pause, stop, or hide control is available',
    });
  }
  return out;
}
"""

_PROMPT = """You are a WCAG 2.2 specialist evaluating SC 1.3.2 Meaningful Sequence (Level A).

The attached screenshot shows a rendered web page. Below is that page's text content listed in
DOM / source order, the order a screen reader reads it.

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

    - SC 1.4.2 / 2.2.2 (runtime): playing audio or moving video without controls.
      Always runs, no model needed.
    - SC 1.3.2 (VLM): visual reading order vs DOM order. Only runs when a
      vision ``provider`` is supplied; no-ops otherwise.
    """

    provider: OllamaVisionProvider | None = None
    max_blocks: int = _MAX_BLOCKS

    async def run(self, page: Page) -> list[VisualFinding]:
        """Run both checks. Never raises, each is isolated."""
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
        """SC 1.4.2 / 2.2.2, measured autoplay media and marquee leads."""
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
            kind = str(item.get("kind") or "motion_review")
            if kind == "audio":
                rule_id = RULE_AUTOPLAY_AUDIO_NO_CONTROL
                criterion_sc = "1.4.2"
                help_text = (
                    "Do not start audible audio automatically, or provide a visible way to "
                    "pause or stop it or control its volume independently of system volume."
                )
                criterion_note = (
                    "Audio that plays automatically for more than 3 seconds needs an "
                    "independent pause, stop, or volume control."
                )
            else:
                rule_id = RULE_MOTION_NO_PAUSE
                criterion_sc = "2.2.2"
                help_text = (
                    "Add a visible pause, stop, or hide control, or avoid automatic motion. "
                    "For video, native controls are acceptable when they expose that control."
                )
                criterion_note = (
                    "Moving content that lasts more than 5 seconds and appears alongside "
                    "other content needs a way to pause, stop, or hide it."
                )
            findings.append(
                VisualFinding(
                    rule_id=rule_id,
                    target_selector=selector,
                    failure_summary=f"{detail}. {criterion_note}",
                    html_snippet=str(item.get("html") or ""),
                    help=help_text,
                    criterion_sc=criterion_sc,
                    wcag_level="A",
                )
            )
        return findings

    async def _check_meaningful_sequence(self, page: Page) -> list[VisualFinding]:
        """SC 1.3.2, visual reading order vs DOM order (VLM)."""
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
