"""Unit tests for OllamaProvider.

All tests use respx to stub the Ollama HTTP API; no live daemon is required.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx

from audit.analyzer.vlm.base import ClassifyContext, VlmLabel
from audit.analyzer.vlm.ollama import (
    OllamaProvider,
    VlmError,
    _parse_model_output,
    load_prompt,
    prompt_version,
)

BASE = "http://ollama-test.local"
MODEL = "qwen2-vl:2b"


def _ctx(ocr: str = "BUY NOW TODAY") -> ClassifyContext:
    return ClassifyContext(
        alt_text="Banner",
        figcaption=None,
        context_snippet="A banner ad",
        ocr_text=ocr,
    )


def _model_reply(label: str, rationale: str = "plain text in the image") -> dict[str, object]:
    return {"response": json.dumps({"label": label, "rationale": rationale})}


def test_load_prompt_has_placeholders() -> None:
    text = load_prompt()
    for placeholder in ("{alt}", "{figcaption}", "{snippet}", "{ocr}"):
        assert placeholder in text


def test_prompt_version_is_deterministic() -> None:
    assert prompt_version("hello") == prompt_version("hello")
    assert prompt_version("hello") != prompt_version("bye")
    assert prompt_version("hello").startswith("v1-")


def test_parse_model_output_valid() -> None:
    label, rationale = _parse_model_output('{"label": "essential", "rationale": "it is text"}')
    assert label is VlmLabel.ESSENTIAL
    assert rationale == "it is text"


def test_parse_model_output_unknown_label_raises() -> None:
    with pytest.raises(VlmError, match="unknown label"):
        _parse_model_output('{"label": "mystery", "rationale": "x"}')


def test_parse_model_output_non_json_raises() -> None:
    with pytest.raises(VlmError, match="valid JSON"):
        _parse_model_output("definitely not json")


def test_parse_model_output_missing_label_raises() -> None:
    with pytest.raises(VlmError, match="missing string"):
        _parse_model_output('{"rationale": "x"}')


@pytest.mark.asyncio
@respx.mock
async def test_classify_happy_path_sends_base64_and_uses_json_format() -> None:
    route = respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(200, json=_model_reply("logo"))
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaProvider(client, model=MODEL, base_url=BASE)
        result = await provider.classify(b"\x89PNG\r\nfake", "image/png", _ctx())

    assert result.label is VlmLabel.LOGO
    assert result.model_version == MODEL
    assert result.prompt_version.startswith("v1-")

    assert route.call_count == 1
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == MODEL
    assert sent["format"] == "json"
    assert sent["stream"] is False
    assert sent["images"] == [base64.b64encode(b"\x89PNG\r\nfake").decode("ascii")]
    # Context fields made it into the prompt.
    assert "Banner" in sent["prompt"]
    assert "BUY NOW TODAY" in sent["prompt"]


@pytest.mark.asyncio
@respx.mock
async def test_classify_retries_on_5xx_then_succeeds() -> None:
    route = respx.post(f"{BASE}/api/generate").mock(
        side_effect=[
            httpx.Response(503, text="busy"),
            httpx.Response(200, json=_model_reply("decorative")),
        ]
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaProvider(client, model=MODEL, base_url=BASE, max_attempts=3)
        result = await provider.classify(b"x", "image/png", _ctx(""))

    assert result.label is VlmLabel.DECORATIVE
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_classify_4xx_other_than_throttle_raises_immediately() -> None:
    route = respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(400, text="bad req")
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaProvider(client, model=MODEL, base_url=BASE, max_attempts=3)
        with pytest.raises(VlmError, match="HTTP 400"):
            await provider.classify(b"x", "image/png", _ctx(""))
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_classify_exhausted_retries_raises() -> None:
    respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(503, text="busy"),
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaProvider(client, model=MODEL, base_url=BASE, max_attempts=2)
        with pytest.raises(VlmError, match="exhausted retries"):
            await provider.classify(b"x", "image/png", _ctx(""))


@pytest.mark.asyncio
@respx.mock
async def test_healthy_returns_true_when_model_listed() -> None:
    respx.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": MODEL}, {"name": "other"}]})
    )
    async with httpx.AsyncClient() as client:
        assert await OllamaProvider(client, model=MODEL, base_url=BASE).healthy()


@pytest.mark.asyncio
@respx.mock
async def test_healthy_returns_false_when_model_missing() -> None:
    respx.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "other"}]})
    )
    async with httpx.AsyncClient() as client:
        assert not await OllamaProvider(client, model=MODEL, base_url=BASE).healthy()


@pytest.mark.asyncio
@respx.mock
async def test_healthy_returns_false_when_daemon_unreachable() -> None:
    respx.get(f"{BASE}/api/tags").mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient() as client:
        assert not await OllamaProvider(client, model=MODEL, base_url=BASE).healthy()
