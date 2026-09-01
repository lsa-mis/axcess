"""Safety contracts for optional companion-local protected AI."""

from __future__ import annotations

import json

import httpx
import pytest

from audit.analyzer.axe import AxeViolation
from audit.crawler.fetcher import FetchResult
from audit.protected import companion
from audit.protected import local_ai as protected_local_ai


@pytest.mark.asyncio
async def test_local_image_assessment_keeps_only_a_bounded_signal() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        payload = json.loads(request.content)
        captured["image_count"] = len(payload["images"])
        return httpx.Response(
            200,
            json={"response": json.dumps({"contains_meaningful_text": True, "impact": "serious"})},
        )

    transport = httpx.MockTransport(handler)
    async with protected_local_ai.ProtectedLocalOllama(
        base_url="http://127.0.0.1:11434", model="local-test", transport=transport
    ) as local:
        result = await local.assess_image(bytearray(b"not-a-real-image"))

    assert result is not None
    assert result.contains_meaningful_text is True
    assert result.impact == "serious"
    assert captured == {"path": "/api/generate", "image_count": 1}


@pytest.mark.asyncio
async def test_local_image_assessment_rejects_untrusted_model_shape() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": json.dumps(
                    {
                        "contains_meaningful_text": False,
                        "impact": "minor",
                        "rationale": "Do this unrelated thing",
                    }
                )
            },
        )

    async with protected_local_ai.ProtectedLocalOllama(
        base_url="http://127.0.0.1:11434",
        model="local-test",
        transport=httpx.MockTransport(handler),
    ) as local:
        assert await local.assess_image(bytearray(b"image")) is None


def test_companion_only_accepts_loopback_ollama_and_detects_login_forms() -> None:
    assert companion.is_loopback_ollama_url("http://127.0.0.1:11434")
    assert companion.is_loopback_ollama_url("http://[::1]:11434")
    assert not companion.is_loopback_ollama_url("http://localhost:11434")
    assert not companion.is_loopback_ollama_url("https://ollama.example.test")
    assert companion.looks_like_authentication_page(
        "https://app.example.test/dashboard", b'<input type="password" name="password">'
    )
    assert companion.looks_like_authentication_page(
        "https://app.example.test/sign-in", b"<main>signed out</main>"
    )
    assert not companion.looks_like_authentication_page(
        "https://app.example.test/dashboard", b"<main>Account overview</main>"
    )


def test_companion_indexes_each_axe_violation_once() -> None:
    """Protected aggregates must not inflate a source layer's count."""

    source = AxeViolation(
        rule_id="image-alt",
        impact="critical",
        help="Images must have alternative text",
        help_url="https://example.test/help",
        wcag_sc="1.1.1",
        wcag_scs="1.1.1",
        wcag_level="A",
        target_selector="img",
        failure_summary="Missing alternative text",
        html_snippet="<img>",
    )
    result = FetchResult(
        url="https://app.example.test/dashboard",
        status_code=200,
        content_type="text/html",
        body=b"<main></main>",
        retry_after=None,
        axe_violations=(source,),
    )

    indexed = companion._index_findings_from_result(result, index_hmac_key=bytes.fromhex("d" * 64))
    retried = companion._index_findings_from_result(result, index_hmac_key=bytes.fromhex("d" * 64))
    another_report = companion._index_findings_from_result(
        result, index_hmac_key=bytes.fromhex("e" * 64)
    )

    assert len(indexed) == 1
    assert indexed[0].pipeline.value == "axe"
    assert indexed[0].rule_id == "image-alt"
    # A retry/re-authentication handoff produces the same opaque occurrence
    # key, while a different report cannot correlate it or recover the URL.
    assert retried[0].occurrence_key == indexed[0].occurrence_key
    assert another_report[0].occurrence_key != indexed[0].occurrence_key
    assert len(indexed[0].occurrence_key) == 64
    assert "dashboard" not in indexed[0].occurrence_key


def test_companion_page_keys_are_stable_per_report_but_unlinkable_across_reports() -> None:
    first = companion._opaque_index_hmac(
        bytes.fromhex("d" * 64), "page", "https://app.example.test/dashboard"
    )
    retry = companion._opaque_index_hmac(
        bytes.fromhex("d" * 64), "page", "https://app.example.test/dashboard"
    )
    separate_report = companion._opaque_index_hmac(
        bytes.fromhex("e" * 64), "page", "https://app.example.test/dashboard"
    )

    assert first == retry
    assert first != separate_report
    assert len(first) == 64
