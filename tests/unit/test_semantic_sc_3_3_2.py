"""Tests for the SC 3.3.2 (labels or instructions) analyzer.

Deterministic layers — no live model: extractor, prompt rendering,
response parsing + a stubbed-provider end-to-end run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audit.analyzer.semantic.analyzers.sc_3_3_2 import (
    LabelsOrInstructionsAnalyzer,
    _format_fields,
)
from audit.analyzer.semantic.base import AnalysisContext, SemanticFinding
from audit.analyzer.semantic.extractor import extract_form_fields

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "sc_3_3_2"


class _FakeProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.calls = 0

    async def generate_json(self, prompt: str, *, model: str | None = None) -> dict[str, Any]:
        self.calls += 1
        return self._payload


# ---- extractor -----------------------------------------------------------


def test_extract_form_fields_resolves_label_sources() -> None:
    fields = extract_form_fields((_FIXTURES / "unlabelled_form.html").read_bytes())
    controls = [(f.control, f.label, f.label_source, f.placeholder) for f in fields]
    assert controls[0] == ("input[type=text]", "", "none", "Search")  # placeholder-only
    assert controls[1] == ("input[type=text]", "", "none", "")  # bare
    assert controls[2][1:3] == ("Field", "label-for")  # vague label
    assert controls[3][1:3] == ("ZIP code", "label-for")  # good label


def test_extract_form_fields_skips_buttons_and_hidden() -> None:
    html = b"<input type=hidden><input type=submit><button>Go</button><input type=text>"
    fields = extract_form_fields(html)
    assert [f.control for f in fields] == ["input[type=text]"]


def test_extract_form_fields_captures_describedby_instruction() -> None:
    fields = extract_form_fields((_FIXTURES / "clean_form.html").read_bytes())
    dob = next(f for f in fields if f.control == "input[type=text]")
    assert "MM/DD/YYYY" in dob.described_by


# ---- prompt rendering ----------------------------------------------------


def test_format_fields_includes_control_and_sources() -> None:
    rendered = _format_fields(extract_form_fields((_FIXTURES / "clean_form.html").read_bytes()))
    assert "---- FIELD 0 ----" in rendered
    assert "control: input[type=email]" in rendered
    assert "label_source:" in rendered
    assert "aria-describedby" in rendered


# ---- analyze (stubbed provider) ------------------------------------------


def _analyzer(payload: dict[str, Any]) -> tuple[LabelsOrInstructionsAnalyzer, _FakeProvider]:
    provider = _FakeProvider(payload)
    return (
        LabelsOrInstructionsAnalyzer(provider, prompt_template="{elements}"),  # type: ignore[arg-type]
        provider,
    )


@pytest.mark.asyncio
async def test_analyze_flags_unlabelled_fields() -> None:
    html = (_FIXTURES / "unlabelled_form.html").read_bytes()
    payload = {
        "violations": [
            {"index": 0, "reason": "placeholder-only label", "confidence": "high"},
            {"index": 1, "reason": "no label at all", "confidence": "high"},
        ]
    }
    analyzer, provider = _analyzer(payload)
    findings = await analyzer.analyze(AnalysisContext(body=html, page=None, page_url="http://x/"))
    assert provider.calls == 1
    assert len(findings) == 2
    f0 = findings[0]
    assert isinstance(f0, SemanticFinding)
    assert f0.criterion_sc == "3.3.2"
    assert f0.wcag_level == "A"
    assert f0.impact == "serious"
    assert f0.target_selector == extract_form_fields(html)[0].selector


@pytest.mark.asyncio
async def test_analyze_no_fields_returns_nothing() -> None:
    analyzer, provider = _analyzer({"violations": []})
    findings = await analyzer.analyze(
        AnalysisContext(body=b"<p>no form here</p>", page=None, page_url="http://x/")
    )
    assert findings == []
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_analyze_is_defensive() -> None:
    html = (_FIXTURES / "unlabelled_form.html").read_bytes()
    payload = {"violations": [{"index": 99}, {"index": "bad"}, {"index": 1, "confidence": "low"}]}
    analyzer, _ = _analyzer(payload)
    findings = await analyzer.analyze(AnalysisContext(body=html, page=None, page_url="http://x/"))
    assert len(findings) == 1
    assert findings[0].impact == "minor"
