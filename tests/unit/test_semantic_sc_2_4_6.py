"""Tests for the SC 2.4.6 (headings descriptiveness) analyzer.

Three deterministic layers — no live model:
  1. extractor: which headings + section text we feed the model.
  2. prompt rendering: the numbered-list contract.
  3. response parsing + a stubbed-provider end-to-end run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audit.analyzer.semantic.analyzers.sc_2_4_6 import (
    HeadingsAndLabelsAnalyzer,
    _format_headings,
)
from audit.analyzer.semantic.base import AnalysisContext, SemanticFinding
from audit.analyzer.semantic.extractor import extract_headings

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "sc_2_4_6"


class _FakeProvider:
    """Stands in for OllamaTextProvider — returns a canned JSON dict."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.calls = 0

    async def generate_json(self, prompt: str, *, model: str | None = None) -> dict[str, Any]:
        self.calls += 1
        return self._payload


# ---- extractor -----------------------------------------------------------


def test_extract_headings_captures_text_and_following_content() -> None:
    html = (_FIXTURES / "vague_headings.html").read_bytes()
    headings = extract_headings(html)
    assert [h.text for h in headings] == ["Welcome", "Section", "More", "Stuff"]
    # The 'Section' heading must carry the refund content it introduces.
    section = headings[1]
    assert section.level == 2
    assert "refund" in section.following_text.lower()
    # The next heading's content must NOT bleed into this one.
    assert "shipping" not in section.following_text.lower()


def test_extract_headings_skips_empty() -> None:
    html = b"<h1></h1><h2>  </h2><h3>Real Heading</h3><p>content</p>"
    headings = extract_headings(html)
    assert [h.text for h in headings] == ["Real Heading"]


# ---- prompt rendering ----------------------------------------------------


def test_format_headings_is_numbered_and_includes_context() -> None:
    html = (_FIXTURES / "clean.html").read_bytes()
    rendered = _format_headings(extract_headings(html))
    assert "---- HEADING 0 (h1) ----" in rendered
    assert "heading_text:" in rendered
    assert "introduces_content:" in rendered
    assert "Refund Policy" in rendered


def test_format_headings_marks_empty_section_do_not_flag() -> None:
    html = b"<h2>Lonely</h2>"  # no following content
    rendered = _format_headings(extract_headings(html))
    assert "do not flag" in rendered


# ---- response parsing ----------------------------------------------------


def _analyzer(payload: dict[str, Any]) -> tuple[HeadingsAndLabelsAnalyzer, _FakeProvider]:
    provider = _FakeProvider(payload)
    return HeadingsAndLabelsAnalyzer(provider, prompt_template="{elements}"), provider  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_analyze_flags_vague_headings() -> None:
    html = (_FIXTURES / "vague_headings.html").read_bytes()
    payload = {
        "violations": [
            {
                "index": 1,
                "reason": "'Section' describes nothing.",
                "recommendation": "Refund Policy",
                "confidence": "high",
            },
            {
                "index": 2,
                "reason": "'More' is generic.",
                "recommendation": "Shipping Times",
                "confidence": "medium",
            },
        ]
    }
    analyzer, provider = _analyzer(payload)
    findings = await analyzer.analyze(AnalysisContext(body=html, page=None, page_url="http://x/"))
    assert provider.calls == 1
    assert len(findings) == 2
    f0 = findings[0]
    assert isinstance(f0, SemanticFinding)
    assert f0.criterion_sc == "2.4.6"
    assert f0.wcag_level == "AA"
    assert f0.impact == "serious"  # high confidence → serious
    assert "Refund Policy" in f0.failure_summary
    assert f0.target_selector == extract_headings(html)[1].selector


@pytest.mark.asyncio
async def test_analyze_is_defensive_against_bad_rows() -> None:
    html = (_FIXTURES / "vague_headings.html").read_bytes()
    payload = {
        "violations": [
            {"index": 99, "reason": "out of range"},  # dropped
            {"index": "x", "reason": "bad index"},  # dropped
            {"index": 1, "reason": "real", "confidence": "low"},  # kept
            {"index": 1, "reason": "dupe"},  # dropped (dupe)
            "not a dict",  # dropped
        ]
    }
    analyzer, _ = _analyzer(payload)
    findings = await analyzer.analyze(AnalysisContext(body=html, page=None, page_url="http://x/"))
    assert len(findings) == 1
    assert findings[0].impact == "minor"  # low confidence → minor


@pytest.mark.asyncio
async def test_analyze_empty_page_returns_nothing() -> None:
    analyzer, provider = _analyzer({"violations": []})
    findings = await analyzer.analyze(
        AnalysisContext(body=b"<p>no headings</p>", page=None, page_url="http://x/")
    )
    assert findings == []
    assert provider.calls == 0  # no headings → never calls the model


@pytest.mark.asyncio
async def test_analyze_handles_malformed_response() -> None:
    html = (_FIXTURES / "clean.html").read_bytes()
    analyzer, _ = _analyzer({"wrong_key": []})
    findings = await analyzer.analyze(AnalysisContext(body=html, page=None, page_url="http://x/"))
    assert findings == []
