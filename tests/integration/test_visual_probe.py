"""Tests for the SC 1.3.2 visual (VLM) probe.

The vision model is stubbed (a fake provider), so these stay offline. The
no-op-without-a-provider path needs no browser; the real screenshot + DOM
extraction path uses Playwright with a fake provider returning canned JSON.
"""

from __future__ import annotations

from typing import Any

import pytest

from audit.analyzer.ollama_base import OllamaError
from audit.analyzer.visual import VisualProbe
from audit.analyzer.visual.base import (
    RULE_AUTOPLAY_AUDIO_NO_CONTROL,
    RULE_MEANINGFUL_SEQUENCE,
    RULE_MOTION_NO_PAUSE,
    VisualFinding,
)


class _FakeVision:
    """Stands in for OllamaVisionProvider."""

    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self._result = result
        self.calls = 0

    async def describe_json(
        self, image_bytes: bytes, prompt: str, *, mime: str = "image/png"
    ) -> dict[str, Any]:
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


# ---- no-op / dataclass (no browser) --------------------------------------


def test_finding_repo_kwargs_pipeline_is_visual() -> None:
    f = VisualFinding(
        rule_id=RULE_MEANINGFUL_SEQUENCE,
        target_selector="body",
        failure_summary="x",
        html_snippet="",
        help="y",
    )
    kw = f.to_repo_kwargs()
    assert kw["pipeline"] == "visual"
    assert kw["criterion_sc"] == "1.3.2"
    assert kw["wcag_level"] == "A"
    assert "meaningful-sequence" in f.help_url


# ---- live page + stubbed provider ----------------------------------------

playwright = pytest.importorskip("playwright.async_api")

_HTML = """<!doctype html><html lang=en><head><meta charset=utf-8></head><body>
<h1>Checkout</h1><p>Enter your shipping address below.</p>
<p>Then choose a payment method.</p><p>Finally, review and submit.</p>
</body></html>"""


@pytest.fixture
async def page():  # type: ignore[no-untyped-def]
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        try:
            p = await ctx.new_page()
            await p.set_content(_HTML)
            yield p
        finally:
            await browser.close()
    finally:
        await pw.stop()


@pytest.mark.asyncio
async def test_reports_mismatch(page) -> None:  # type: ignore[no-untyped-def]
    provider = _FakeVision(
        {"mismatch": True, "reason": "submit before fields", "confidence": "high"}
    )
    findings = await VisualProbe(provider=provider).run(page)  # type: ignore[arg-type]
    assert provider.calls == 1  # it screenshotted + extracted blocks + asked
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == RULE_MEANINGFUL_SEQUENCE
    assert f.criterion_sc == "1.3.2"
    assert f.impact == "serious"  # high confidence
    assert "submit before fields" in f.failure_summary
    assert f.to_repo_kwargs()["pipeline"] == "visual"


@pytest.mark.asyncio
async def test_no_finding_when_order_is_fine(page) -> None:  # type: ignore[no-untyped-def]
    provider = _FakeVision({"mismatch": False, "reason": "", "confidence": "high"})
    findings = await VisualProbe(provider=provider).run(page)  # type: ignore[arg-type]
    assert findings == []
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_vlm_error_is_swallowed(page) -> None:  # type: ignore[no-untyped-def]
    provider = _FakeVision(OllamaError("daemon down"))
    findings = await VisualProbe(provider=provider).run(page)  # type: ignore[arg-type]
    assert findings == []


# ---- SC 2.2.2 motion check (deterministic, no provider needed) -----------

_MOTION_HTML = """<!doctype html><html lang=en><body>
<video autoplay src="bg.mp4"></video>
<video autoplay controls src="ok.mp4"></video>
<marquee>breaking news</marquee>
</body></html>"""


@pytest.mark.asyncio
async def test_motion_flags_autoplay_and_marquee(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content(_MOTION_HTML)
    # provider=None: the deterministic 2.2.2 check still runs (no VLM needed).
    findings = await VisualProbe(provider=None).run(page)
    motion = [f for f in findings if f.rule_id == RULE_MOTION_NO_PAUSE]
    # Neither missing video resource played. Only marquee remains as a review lead.
    assert len(motion) == 1
    assert motion[0].target_selector == "marquee"
    assert all(f.criterion_sc == "2.2.2" for f in motion)
    assert all(f.to_repo_kwargs()["pipeline"] == "visual" for f in motion)


class _RuntimeMediaPage:
    async def evaluate(self, _script: str, *_args: object) -> list[dict[str, str]]:
        return [
            {
                "kind": "video",
                "selector": "video#hero",
                "html": '<video id="hero" autoplay></video>',
                "detail": (
                    "Runtime playback measurement: video currentTime advanced 0.34 seconds; "
                    "duration is 12.00 seconds"
                ),
            },
            {
                "kind": "audio",
                "selector": "audio#intro",
                "html": '<audio id="intro" autoplay></audio>',
                "detail": (
                    "Runtime playback measurement: audio currentTime advanced 0.35 seconds; "
                    "duration is 8.00 seconds"
                ),
            },
        ]


@pytest.mark.asyncio
async def test_runtime_media_uses_distinct_wcag_criteria() -> None:
    findings = await VisualProbe(provider=None)._check_motion(_RuntimeMediaPage())  # type: ignore[arg-type]
    assert [(finding.rule_id, finding.criterion_sc) for finding in findings] == [
        (RULE_MOTION_NO_PAUSE, "2.2.2"),
        (RULE_AUTOPLAY_AUDIO_NO_CONTROL, "1.4.2"),
    ]
    assert all("Runtime playback measurement:" in finding.failure_summary for finding in findings)


@pytest.mark.asyncio
async def test_motion_clean_page_no_findings(page) -> None:  # type: ignore[no-untyped-def]
    # The default fixture (_HTML) has no autoplay/marquee → no motion findings.
    findings = await VisualProbe(provider=None).run(page)
    assert findings == []
