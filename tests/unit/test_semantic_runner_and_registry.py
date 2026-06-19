"""Tests for the semantic runner + analyzer registry.

These pin the *infrastructure* contracts that sit between the
per-criterion analyzers and the orchestrator:

* Runner: failure isolation across analyzers, empty-list handling.
* Registry: typo tolerance, dedupe, model-pick wiring.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from audit.analyzer.semantic.base import (
    AnalysisContext,
    SemanticFinding,
)
from audit.analyzer.semantic.registry import build_analyzers, supported_criteria
from audit.analyzer.semantic.runner import analyze_page


def _finding(sc: str, *, hash_suffix: str = "x") -> SemanticFinding:
    return SemanticFinding(
        criterion_sc=sc,
        wcag_level="A",
        impact="serious",
        help="x",
        target_selector="a",
        failure_summary="x",
        html_snippet="<a>x</a>",
        target_hash=f"h-{hash_suffix}",
    )


class _StubAnalyzer:
    """Minimal SemanticAnalyzer used for runner tests."""

    def __init__(
        self,
        criterion_sc: str,
        *,
        findings: Sequence[SemanticFinding] = (),
        raise_exc: BaseException | None = None,
    ) -> None:
        self.criterion_sc = criterion_sc
        self._findings = list(findings)
        self._raise = raise_exc
        self.call_count = 0

    async def analyze(self, ctx: AnalysisContext) -> list[SemanticFinding]:
        self.call_count += 1
        if self._raise:
            raise self._raise
        return list(self._findings)


# --------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_with_no_analyzers_returns_empty() -> None:
    """No analyzers configured → no call, no findings."""
    findings = await analyze_page(AnalysisContext(body=b""), [])
    assert findings == []


@pytest.mark.asyncio
async def test_runner_concatenates_findings_across_analyzers() -> None:
    """Two analyzers, each producing findings → flat union."""
    a = _StubAnalyzer("2.4.4", findings=[_finding("2.4.4", hash_suffix="1")])
    b = _StubAnalyzer(
        "1.3.1",
        findings=[
            _finding("1.3.1", hash_suffix="2"),
            _finding("1.3.1", hash_suffix="3"),
        ],
    )
    findings = await analyze_page(AnalysisContext(body=b""), [a, b])
    assert len(findings) == 3
    assert {f.criterion_sc for f in findings} == {"2.4.4", "1.3.1"}


@pytest.mark.asyncio
async def test_runner_isolates_per_analyzer_exceptions() -> None:
    """One analyzer raising must NOT take down the others."""
    a = _StubAnalyzer("2.4.4", findings=[_finding("2.4.4")])
    b = _StubAnalyzer("1.3.1", raise_exc=RuntimeError("boom"))
    c = _StubAnalyzer("4.1.2", findings=[_finding("4.1.2")])
    findings = await analyze_page(AnalysisContext(body=b""), [a, b, c])
    # Two analyzers succeeded; the failing one contributed zero.
    assert len(findings) == 2
    assert {f.criterion_sc for f in findings} == {"2.4.4", "4.1.2"}
    # Every analyzer was actually called (the exception didn't
    # short-circuit later ones).
    assert all(x.call_count == 1 for x in (a, b, c))


@pytest.mark.asyncio
async def test_runner_handles_analyzer_returning_empty() -> None:
    """An analyzer with no findings → contributes nothing, doesn't error."""
    a = _StubAnalyzer("2.4.4", findings=[])
    b = _StubAnalyzer("1.3.1", findings=[_finding("1.3.1")])
    findings = await analyze_page(AnalysisContext(body=b""), [a, b])
    assert len(findings) == 1
    assert findings[0].criterion_sc == "1.3.1"


@pytest.mark.asyncio
async def test_runner_preserves_per_analyzer_order() -> None:
    """The output order matches the analyzer list order, which
    matches the operator's --semantic-criteria input."""
    a = _StubAnalyzer(
        "first",
        findings=[
            _finding("first", hash_suffix="A1"),
            _finding("first", hash_suffix="A2"),
        ],
    )
    b = _StubAnalyzer("second", findings=[_finding("second", hash_suffix="B1")])
    findings = await analyze_page(AnalysisContext(body=b""), [a, b])
    # asyncio.gather preserves submission order, so we know the order
    # is deterministic.
    assert [f.criterion_sc for f in findings] == ["first", "first", "second"]


# --------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------


class _ProbeProvider:
    """Records constructor args from build_analyzers without an HTTP call."""

    pass


def test_supported_criteria_includes_pilot_sc() -> None:
    """SC 2.4.4 must be in the registry by the end of Phase 9.1."""
    assert "2.4.4" in supported_criteria()


def test_build_analyzers_instantiates_known_criterion() -> None:
    provider = _ProbeProvider()
    analyzers = build_analyzers(["2.4.4"], provider)  # type: ignore[arg-type]
    assert len(analyzers) == 1
    assert analyzers[0].criterion_sc == "2.4.4"


def test_build_analyzers_skips_unknown_criterion() -> None:
    """A typo or unimplemented SC is logged + skipped; never raises."""
    provider = _ProbeProvider()
    analyzers = build_analyzers(["2.4.4", "9.9.9"], provider)  # type: ignore[arg-type]
    # Known one instantiated; unknown one silently dropped.
    assert len(analyzers) == 1
    assert analyzers[0].criterion_sc == "2.4.4"


def test_build_analyzers_dedupes_repeat_criteria() -> None:
    """`--semantic-criteria 2.4.4,2.4.4` shouldn't double-bill the LLM."""
    provider = _ProbeProvider()
    analyzers = build_analyzers(["2.4.4", "2.4.4"], provider)  # type: ignore[arg-type]
    assert len(analyzers) == 1


def test_build_analyzers_ignores_empty_strings() -> None:
    """Whitespace / empty entries in the CSV are tolerated."""
    provider = _ProbeProvider()
    analyzers = build_analyzers(["", "  ", "2.4.4"], provider)  # type: ignore[arg-type]
    assert len(analyzers) == 1
    assert analyzers[0].criterion_sc == "2.4.4"


def test_build_analyzers_empty_input_returns_empty_list() -> None:
    provider = _ProbeProvider()
    assert build_analyzers([], provider) == []  # type: ignore[arg-type]
