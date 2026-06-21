"""Tests for :class:`LinkPurposeInContextAnalyzer` (SC 2.4.4).

Three layers:

* **Prompt rendering** — deterministic string interpolation. Tests
  pin that every extracted link is represented and that the prompt
  remains a single complete string after formatting.
* **Response parsing** — the JSON-shape contract between the
  analyzer and the LLM. Tests cover well-formed responses, missing
  fields, bad indices, duplicates, and confidence normalization.
* **End-to-end** — analyzer driven through a respx-stubbed Ollama,
  asserting that the right SemanticFinding rows come out for a
  known stubbed model response.

Each test asserts ONE behavior so a future regression points at
the specific broken case.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from audit.analyzer.semantic.analyzers.sc_2_4_4 import (
    MAX_LINKS_PER_CALL,
    LinkPurposeInContextAnalyzer,
)
from audit.analyzer.semantic.base import AnalysisContext, SemanticFinding
from audit.analyzer.semantic.extractor import LinkRecord, extract_links
from audit.analyzer.semantic.ollama_text import OllamaTextProvider

BASE = "http://ollama-test.local"
MODEL = "qwen2.5:7b-instruct"


# --------------------------------------------------------------------
# Prompt rendering
# --------------------------------------------------------------------


def _make_analyzer() -> LinkPurposeInContextAnalyzer:
    """Build an analyzer with a no-op provider for prompt-only tests.

    The provider isn't called for the prompt-rendering tests — we
    just need a class instance so the prompt template loads.
    """

    class _NullProvider:
        """Stand-in that fulfills the type but raises if called."""

        async def generate_json(self, *_a: object, **_kw: object) -> object:
            raise AssertionError("not expected to be called in this test")

    return LinkPurposeInContextAnalyzer(_NullProvider())  # type: ignore[arg-type]


def test_prompt_includes_every_link_index() -> None:
    """Every link in the input list must appear by its numeric index."""
    analyzer = _make_analyzer()
    links = [
        LinkRecord(
            selector=f"a[ord={i}]",
            href=f"/p{i}",
            accessible_name=f"Link {i}",
            accessible_name_source="text",
            aria_label=None,
            title=None,
            ancestors=[],
            snippet=f"<a>Link {i}</a>",
        )
        for i in range(3)
    ]
    prompt = analyzer._render_prompt(links)
    for i in range(3):
        assert f"LINK {i}" in prompt
        assert f"Link {i}" in prompt


def test_prompt_renders_accessible_name_source_field() -> None:
    """The source label travels with the link so the model knows how
    a screen reader would derive the name."""
    analyzer = _make_analyzer()
    link = LinkRecord(
        selector="a[ord=0]",
        href="/x",
        accessible_name="search",
        accessible_name_source="aria-label",
        aria_label="search",
        title=None,
        ancestors=[],
        snippet="",
    )
    prompt = analyzer._render_prompt([link])
    assert "aria-label" in prompt
    assert "accessible_name_source: aria-label" in prompt


def test_prompt_includes_ancestors_when_present() -> None:
    analyzer = _make_analyzer()
    link = LinkRecord(
        selector="a[ord=0]",
        href="/r25.pdf",
        accessible_name="Read more",
        accessible_name_source="text",
        aria_label=None,
        title=None,
        ancestors=["Annual Report 2025", "Investor relations"],
        snippet="",
    )
    prompt = analyzer._render_prompt([link])
    assert "Annual Report 2025" in prompt
    assert "Investor relations" in prompt


def test_prompt_omits_redundant_aria_label_field() -> None:
    """If aria_label == accessible_name, including both wastes tokens."""
    analyzer = _make_analyzer()
    link = LinkRecord(
        selector="a[ord=0]",
        href="/x",
        accessible_name="search",
        accessible_name_source="aria-label",
        aria_label="search",  # same as accessible_name
        title=None,
        ancestors=[],
        snippet="",
    )
    prompt = analyzer._render_prompt([link])
    # aria_label key shouldn't be printed redundantly.
    assert prompt.count("aria_label:") == 0


def test_prompt_version_is_deterministic_across_instances() -> None:
    """Two analyzer instances loading the same prompt hash to the
    same prompt_version (pinned in analyses.model_versions_json)."""
    a = _make_analyzer()
    b = _make_analyzer()
    assert a.prompt_version == b.prompt_version
    assert a.prompt_version.startswith("v1-")


def test_prompt_version_changes_when_template_is_overridden() -> None:
    """Caller-supplied template produces a different content hash —
    so a tuning change shows up as a new prompt_version in the DB."""

    class _Null:
        async def generate_json(self, *_a: object, **_kw: object) -> object:
            return {}

    default = LinkPurposeInContextAnalyzer(_Null())  # type: ignore[arg-type]
    edited = LinkPurposeInContextAnalyzer(
        _Null(),  # type: ignore[arg-type]
        prompt_template="custom prompt with {elements}",
    )
    assert default.prompt_version != edited.prompt_version


# --------------------------------------------------------------------
# Response parsing
# --------------------------------------------------------------------


def _stub_links(n: int) -> list[LinkRecord]:
    """Helper: build n LinkRecord stubs for parser tests."""
    return [
        LinkRecord(
            selector=f"a[ord={i}]",
            href=f"/{i}",
            accessible_name=f"link {i}",
            accessible_name_source="text",
            aria_label=None,
            title=None,
            ancestors=[],
            snippet=f"<a>link {i}</a>",
        )
        for i in range(n)
    ]


def test_parser_well_formed_response_produces_findings() -> None:
    """The happy path: one violation, all fields populated."""
    analyzer = _make_analyzer()
    raw = {
        "violations": [
            {
                "index": 0,
                "reason": "Link reads 'click here' — no context.",
                "recommendation": "Use 'Download annual report 2025'.",
                "confidence": "high",
            }
        ]
    }
    findings = list(analyzer._parse_response(raw, _stub_links(2)))
    assert len(findings) == 1
    f = findings[0]
    assert isinstance(f, SemanticFinding)
    assert f.criterion_sc == "2.4.4"
    assert f.wcag_level == "A"
    assert f.impact == "serious"  # 'high' confidence → 'serious'
    assert "click here" in f.help
    assert "Download annual report" in f.failure_summary
    assert f.target_selector == "a[ord=0]"


def test_parser_low_confidence_maps_to_minor_impact() -> None:
    analyzer = _make_analyzer()
    raw = {"violations": [{"index": 0, "reason": "Maybe ambiguous", "confidence": "low"}]}
    findings = list(analyzer._parse_response(raw, _stub_links(1)))
    assert findings[0].impact == "minor"


def test_parser_medium_confidence_maps_to_moderate_impact() -> None:
    analyzer = _make_analyzer()
    raw = {"violations": [{"index": 0, "reason": "Possibly unclear", "confidence": "medium"}]}
    findings = list(analyzer._parse_response(raw, _stub_links(1)))
    assert findings[0].impact == "moderate"


def test_parser_unknown_confidence_defaults_to_medium() -> None:
    """Defensive: model invents 'definite' or returns int → moderate."""
    analyzer = _make_analyzer()
    raw = {"violations": [{"index": 0, "reason": "x", "confidence": "definite"}]}
    findings = list(analyzer._parse_response(raw, _stub_links(1)))
    assert findings[0].impact == "moderate"


def test_parser_missing_confidence_field_defaults_to_medium() -> None:
    analyzer = _make_analyzer()
    raw = {"violations": [{"index": 0, "reason": "x"}]}
    findings = list(analyzer._parse_response(raw, _stub_links(1)))
    assert findings[0].impact == "moderate"


def test_parser_empty_violations_returns_no_findings() -> None:
    """A clean response with no violations should produce no findings."""
    analyzer = _make_analyzer()
    findings = list(analyzer._parse_response({"violations": []}, _stub_links(5)))
    assert findings == []


def test_parser_drops_out_of_range_indices() -> None:
    """Hallucinated index 99 in a 3-link list is logged + skipped."""
    analyzer = _make_analyzer()
    raw = {
        "violations": [
            {"index": 0, "reason": "real one"},
            {"index": 99, "reason": "hallucinated"},
        ]
    }
    findings = list(analyzer._parse_response(raw, _stub_links(3)))
    assert len(findings) == 1
    assert findings[0].target_selector == "a[ord=0]"


def test_parser_drops_negative_indices() -> None:
    analyzer = _make_analyzer()
    raw = {"violations": [{"index": -1, "reason": "bad"}]}
    findings = list(analyzer._parse_response(raw, _stub_links(3)))
    assert findings == []


def test_parser_drops_non_integer_indices() -> None:
    """Model returns 'one' or a float we can't coerce → drop."""
    analyzer = _make_analyzer()
    raw = {"violations": [{"index": "one", "reason": "bad"}]}
    findings = list(analyzer._parse_response(raw, _stub_links(3)))
    assert findings == []


def test_parser_deduplicates_repeat_indices() -> None:
    """Model flagged the same link twice → keep first, drop the rest."""
    analyzer = _make_analyzer()
    raw = {
        "violations": [
            {"index": 0, "reason": "first call"},
            {"index": 0, "reason": "second call"},
        ]
    }
    findings = list(analyzer._parse_response(raw, _stub_links(2)))
    assert len(findings) == 1
    assert "first call" in findings[0].help


def test_parser_rejects_non_object_top_level() -> None:
    """Model returned a JSON array instead of an object → drop all."""
    analyzer = _make_analyzer()
    # Cast through Any: signature accepts dict|list but reject case
    # is the list path.
    findings = list(analyzer._parse_response(["nope"], _stub_links(1)))  # type: ignore[arg-type]
    assert findings == []


def test_parser_rejects_missing_violations_key() -> None:
    """Model returned {"other": ...} → no violations array → drop all."""
    analyzer = _make_analyzer()
    findings = list(analyzer._parse_response({"other": "x"}, _stub_links(1)))
    assert findings == []


def test_parser_rejects_violations_wrong_type() -> None:
    """Model returned {"violations": "yes"} → drop, log."""
    analyzer = _make_analyzer()
    findings = list(
        analyzer._parse_response({"violations": "yes"}, _stub_links(1))  # type: ignore[dict-item]
    )
    assert findings == []


def test_parser_drops_non_dict_violation_entries() -> None:
    analyzer = _make_analyzer()
    raw = {"violations": ["a string", {"index": 0, "reason": "real"}, 42]}
    findings = list(analyzer._parse_response(raw, _stub_links(2)))
    assert len(findings) == 1
    assert "real" in findings[0].help


def test_parser_truncates_overlong_reason() -> None:
    """Defensive: 5000-char reason gets clipped before persistence."""
    analyzer = _make_analyzer()
    raw = {"violations": [{"index": 0, "reason": "x" * 5000}]}
    findings = list(analyzer._parse_response(raw, _stub_links(1)))
    assert len(findings[0].help) <= 600  # extractor caps at 500


def test_parser_target_hash_is_deterministic_for_same_link() -> None:
    """Re-parsing the same response yields the same target_hash —
    so the DB upsert collapses repeated runs into one row."""
    analyzer = _make_analyzer()
    raw = {"violations": [{"index": 0, "reason": "x"}]}
    a = list(analyzer._parse_response(raw, _stub_links(1)))
    b = list(analyzer._parse_response(raw, _stub_links(1)))
    assert a[0].target_hash == b[0].target_hash


def test_parser_target_hash_differs_across_links() -> None:
    """Two links flagged in one response get two distinct hashes."""
    analyzer = _make_analyzer()
    raw = {
        "violations": [
            {"index": 0, "reason": "x"},
            {"index": 1, "reason": "y"},
        ]
    }
    findings = list(analyzer._parse_response(raw, _stub_links(2)))
    assert findings[0].target_hash != findings[1].target_hash


# --------------------------------------------------------------------
# End-to-end through a respx-stubbed Ollama
# --------------------------------------------------------------------


def _ollama_response(payload: dict[str, object]) -> dict[str, str]:
    """Ollama envelope for a model that returned `payload` as JSON."""
    return {"response": json.dumps(payload)}


@pytest.mark.asyncio
@respx.mock
async def test_analyze_happy_path_produces_findings() -> None:
    """Plain page with 'click here' → analyzer flags it via the model."""
    respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json=_ollama_response(
                {
                    "violations": [
                        {
                            "index": 0,
                            "reason": "Link text 'click here' tells the user nothing.",
                            "recommendation": "Use the destination name.",
                            "confidence": "high",
                        }
                    ]
                }
            ),
        )
    )
    body = b'<a href="/foo">click here</a>'
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        analyzer = LinkPurposeInContextAnalyzer(provider)
        findings = await analyzer.analyze(AnalysisContext(body=body, page_url="http://x/"))
    assert len(findings) == 1
    assert findings[0].criterion_sc == "2.4.4"
    assert "click here" in findings[0].help


@pytest.mark.asyncio
@respx.mock
async def test_analyze_empty_page_skips_llm_call() -> None:
    """A page with zero links should not waste an LLM call."""
    route = respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(200, json=_ollama_response({"violations": []}))
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        analyzer = LinkPurposeInContextAnalyzer(provider)
        findings = await analyzer.analyze(AnalysisContext(body=b"<p>no links</p>", page_url="x"))
    assert findings == []
    assert route.call_count == 0  # contract: no LLM call when no candidates


@pytest.mark.asyncio
@respx.mock
async def test_analyze_swallows_llm_error_and_returns_empty() -> None:
    """An unhealthy Ollama mid-crawl shouldn't crash the page."""
    respx.post(f"{BASE}/api/generate").mock(return_value=httpx.Response(500, text="model crashed"))
    body = b'<a href="/x">click here</a>'
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE, max_attempts=1)
        analyzer = LinkPurposeInContextAnalyzer(provider)
        findings = await analyzer.analyze(AnalysisContext(body=body, page_url="x"))
    assert findings == []  # logged + skipped, not raised


@pytest.mark.asyncio
@respx.mock
async def test_analyze_caps_links_at_max_per_call() -> None:
    """A page with MAX_LINKS_PER_CALL + 5 links sends only the first N."""
    big_body_parts = [f'<a href="/p{i}">link {i}</a>' for i in range(MAX_LINKS_PER_CALL + 5)]
    body = "".join(big_body_parts).encode()
    route = respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(200, json=_ollama_response({"violations": []}))
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        analyzer = LinkPurposeInContextAnalyzer(provider)
        await analyzer.analyze(AnalysisContext(body=body, page_url="x"))

    # The prompt sent to Ollama mentions LINK 0 through LINK 49 — not 50+.
    sent = json.loads(route.calls[0].request.content)
    prompt = sent["prompt"]
    assert f"LINK {MAX_LINKS_PER_CALL - 1}" in prompt
    assert f"LINK {MAX_LINKS_PER_CALL}" not in prompt


@pytest.mark.asyncio
@respx.mock
async def test_analyze_model_response_with_indices_out_of_range_drops_them() -> None:
    """Index 99 on a 1-link page: drop silently, don't crash."""
    respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json=_ollama_response({"violations": [{"index": 99, "reason": "ghost"}]}),
        )
    )
    body = b'<a href="/x">x</a>'
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        analyzer = LinkPurposeInContextAnalyzer(provider)
        findings = await analyzer.analyze(AnalysisContext(body=body, page_url="x"))
    assert findings == []


# --------------------------------------------------------------------
# Sanity-link to the extractor: the analyzer + extractor agree on
# what gets sent to the model.
# --------------------------------------------------------------------


def test_analyzer_input_to_prompt_matches_extractor_output() -> None:
    """Each extracted link gets its own LINK-N block in the prompt.

    Skipped links (fragment-only, javascript:, mailto:) don't get
    their own LINK-N blocks. We DON'T assert their text is absent
    entirely — ancestor-context capture in the extractor pulls
    surrounding text, which can include text from sibling anchors
    we chose to skip. That's correct behavior for SC 2.4.4 ("context
    is the programmatically determined surrounding text").
    """
    body = b"""
    <a href="#skip-frag">a</a>
    <a href="javascript:void(0)">b</a>
    <a href="mailto:a@b.co">c</a>
    <a href="/real-1">d</a>
    <a href="/real-2">e</a>
    """
    extracted = extract_links(body)
    analyzer = _make_analyzer()
    prompt = analyzer._render_prompt(extracted)
    # Exactly two extracted links → exactly two LINK blocks in prompt.
    assert len(extracted) == 2
    assert prompt.count("---- LINK ") == 2
    assert "LINK 0" in prompt
    assert "LINK 1" in prompt
    assert "LINK 2" not in prompt
    # Real hrefs make it through. The skipped hrefs (the bare ones)
    # never appear as a `href:` field value in any LINK block.
    assert "'/real-1'" in prompt
    assert "'/real-2'" in prompt
    assert "javascript:void" not in prompt
    assert "mailto:" not in prompt
