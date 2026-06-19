"""Unit tests for the text-only Ollama provider.

Mirrors the respx pattern from ``test_vlm_ollama.py`` so the same
HTTP stubbing semantics apply: every test stubs ``/api/generate`` and
verifies the wire payload. No live daemon required.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from audit.analyzer.ollama_base import OllamaError
from audit.analyzer.semantic.ollama_text import OllamaTextProvider

BASE = "http://ollama-test.local"
MODEL = "qwen2.5:7b-instruct"


def _reply(body: object) -> dict[str, object]:
    """Build a fake Ollama envelope. Body is what the model "said"."""
    if isinstance(body, str):
        return {"response": body}
    return {"response": json.dumps(body)}


@pytest.mark.asyncio
@respx.mock
async def test_generate_sends_json_mode_and_temperature_zero() -> None:
    """Defaults: format=json, temperature=0, keep_alive=-1."""
    route = respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(200, json=_reply({"ok": True}))
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        out = await provider.generate("any prompt")

    assert out == json.dumps({"ok": True})
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == MODEL
    assert sent["format"] == "json"
    assert sent["stream"] is False
    assert sent["keep_alive"] == -1
    assert sent["options"]["temperature"] == 0.0
    # Critically, no `images` field — this is the text path.
    assert "images" not in sent


@pytest.mark.asyncio
@respx.mock
async def test_generate_per_call_model_override() -> None:
    """The runner switches models per criterion via the `model=` kwarg."""
    route = respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(200, json=_reply({"ok": True}))
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        await provider.generate("p", model="qwen2.5:14b-instruct")

    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "qwen2.5:14b-instruct"
    # Provider's default `_model` should not have been mutated.
    assert provider.model == MODEL


@pytest.mark.asyncio
@respx.mock
async def test_generate_force_json_false_drops_format_key() -> None:
    """Free-form mode skips the format=json constraint."""
    route = respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(200, json=_reply("free-form prose"))
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        out = await provider.generate("p", force_json=False)

    assert out == "free-form prose"
    sent = json.loads(route.calls[0].request.content)
    assert "format" not in sent


@pytest.mark.asyncio
@respx.mock
async def test_generate_json_parses_and_returns_object() -> None:
    """The JSON-parsing convenience returns a dict directly."""
    respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(200, json=_reply({"violations": ["a", "b"]}))
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        result = await provider.generate_json("p")

    assert isinstance(result, dict)
    assert result == {"violations": ["a", "b"]}


@pytest.mark.asyncio
@respx.mock
async def test_generate_json_raises_on_empty_response() -> None:
    """Empty Ollama body = model probably crashed; raise rather than
    returning a misleading empty dict."""
    respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(200, json={"response": ""})
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        with pytest.raises(OllamaError, match="empty"):
            await provider.generate_json("p")


@pytest.mark.asyncio
@respx.mock
async def test_generate_json_raises_on_invalid_json() -> None:
    """format=json should prevent this, but defensive parse still raises."""
    respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(200, json=_reply("not { valid json"))
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        with pytest.raises(OllamaError, match="valid JSON"):
            await provider.generate_json("p")


@pytest.mark.asyncio
@respx.mock
async def test_generate_retries_on_5xx_then_succeeds() -> None:
    """The shared retry policy is inherited from OllamaBase."""
    route = respx.post(f"{BASE}/api/generate").mock(
        side_effect=[
            httpx.Response(503, text="model is loading"),
            httpx.Response(200, json=_reply({"ok": True})),
        ]
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(
            client, model=MODEL, base_url=BASE, max_attempts=3
        )
        out = await provider.generate("p")

    assert out == json.dumps({"ok": True})
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_healthy_probes_api_tags() -> None:
    """OllamaBase.healthy() works the same for text + image providers."""
    respx.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": MODEL}]})
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        assert await provider.healthy() is True


@pytest.mark.asyncio
@respx.mock
async def test_healthy_returns_false_when_model_not_pulled() -> None:
    """Daemon up but the model tag missing → False, not raise."""
    respx.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "other"}]})
    )
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        assert await provider.healthy() is False
