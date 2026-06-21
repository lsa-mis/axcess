"""Tests for the SC 1.2.1 (audio transcript presence) analyzer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audit.analyzer.semantic.analyzers.sc_1_2_1 import (
    AudioTranscriptAnalyzer,
    _format_media,
)
from audit.analyzer.semantic.base import AnalysisContext, SemanticFinding
from audit.analyzer.semantic.extractor import extract_media

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "sc_1_2_1"


class _FakeProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.calls = 0

    async def generate_json(self, prompt: str, *, model: str | None = None) -> dict[str, Any]:
        self.calls += 1
        return self._payload


# ---- extractor -----------------------------------------------------------


def test_extract_media_captures_kind_src_and_nearby_links() -> None:
    media = extract_media((_FIXTURES / "with_transcript.html").read_bytes())
    assert len(media) == 1
    m = media[0]
    assert m.kind == "audio"
    assert m.src == "ep12.mp3"
    assert any("transcript" in link.lower() for link in m.nearby_links)


def test_extract_media_handles_source_child_and_video() -> None:
    html = b"<video><source src='v.webm'></video><audio><source src='a.ogg'></audio>"
    media = extract_media(html)
    kinds = {m.kind: m.src for m in media}
    assert kinds == {"video": "v.webm", "audio": "a.ogg"}


# ---- prompt rendering ----------------------------------------------------


def test_format_media_lists_audio_with_cues() -> None:
    rendered = _format_media(extract_media((_FIXTURES / "no_transcript.html").read_bytes()))
    assert "---- AUDIO 0 ----" in rendered
    assert "src: 'ep13.mp3'" in rendered
    assert "nearby_links" in rendered


# ---- analyze (stubbed provider) ------------------------------------------


def _analyzer(payload: dict[str, Any]) -> tuple[AudioTranscriptAnalyzer, _FakeProvider]:
    provider = _FakeProvider(payload)
    return (
        AudioTranscriptAnalyzer(provider, prompt_template="{elements}"),  # type: ignore[arg-type]
        provider,
    )


@pytest.mark.asyncio
async def test_analyze_flags_audio_without_transcript() -> None:
    html = (_FIXTURES / "no_transcript.html").read_bytes()
    payload = {
        "violations": [
            {"index": 0, "reason": "no transcript reachable", "confidence": "medium"},
        ]
    }
    analyzer, provider = _analyzer(payload)
    findings = await analyzer.analyze(AnalysisContext(body=html, page=None, page_url="http://x/"))
    assert provider.calls == 1
    assert len(findings) == 1
    f0 = findings[0]
    assert isinstance(f0, SemanticFinding)
    assert f0.criterion_sc == "1.2.1"
    assert f0.wcag_level == "A"
    assert f0.impact == "moderate"


@pytest.mark.asyncio
async def test_analyze_ignores_video_only_pages() -> None:
    # A page with only <video> (no <audio>) → 1.2.1-audio scope is empty.
    html = b"<video src='v.mp4' controls></video>"
    analyzer, provider = _analyzer({"violations": []})
    findings = await analyzer.analyze(AnalysisContext(body=html, page=None, page_url="http://x/"))
    assert findings == []
    assert provider.calls == 0  # no audio → never calls the model


@pytest.mark.asyncio
async def test_analyze_no_media_returns_nothing() -> None:
    analyzer, provider = _analyzer({"violations": []})
    findings = await analyzer.analyze(
        AnalysisContext(body=b"<p>silent page</p>", page=None, page_url="http://x/")
    )
    assert findings == []
    assert provider.calls == 0
