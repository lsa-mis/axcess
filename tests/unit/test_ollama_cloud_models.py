"""No AI feature sends scan data to an Ollama cloud model.

Ollama runs a model tagged ``cloud`` or ``...-cloud`` on its own servers,
even when Axcess asks the local daemon. Each call path refuses such a model
before any request is made, so the page text and images stay on this
computer.
"""

from __future__ import annotations

import httpx
import pytest

from audit.analyzer.ollama_base import OllamaError, is_cloud_model
from audit.analyzer.semantic.ollama_text import OllamaTextProvider
from audit.protected import local_ai as protected_local_ai
from audit.suggest.provider import OllamaSuggestionProvider, SuggestionError

CLOUD = "gpt-oss:120b-cloud"


@pytest.mark.parametrize(
    ("name", "cloud"),
    [
        ("gpt-oss:120b-cloud", True),
        ("qwen3-vl:235b-cloud", True),
        ("some-model:cloud", True),
        ("Some-Model:CLOUD", True),
        ("qwen3-vl:2b-instruct", False),
        ("llava:7b", False),
        ("llava", False),
        # "cloud" in the model's name, not its tag, is a local model.
        ("cloudy-vision:7b", False),
    ],
)
def test_is_cloud_model(name: str, cloud: bool) -> None:
    assert is_cloud_model(name) is cloud


def _refusing_transport(calls: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"response": "{}"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_scan_analysis_refuses_a_cloud_model() -> None:
    calls: list[httpx.Request] = []
    async with httpx.AsyncClient(transport=_refusing_transport(calls)) as client:
        provider = OllamaTextProvider(client, model=CLOUD, base_url="http://127.0.0.1:11434")
        with pytest.raises(OllamaError, match="cloud model"):
            await provider._post_with_retries({"model": CLOUD, "prompt": "page text"})
    assert calls == []


@pytest.mark.asyncio
async def test_fix_suggestions_refuse_a_cloud_model() -> None:
    calls: list[httpx.Request] = []
    async with httpx.AsyncClient(transport=_refusing_transport(calls)) as client:
        provider = OllamaSuggestionProvider(client, base_url="http://127.0.0.1:11434", timeout_s=30)
        with pytest.raises(SuggestionError) as raised:
            await provider.generate("evidence", model=CLOUD, image=None)
    assert raised.value.code == "model_unavailable"
    assert calls == []


@pytest.mark.asyncio
async def test_sign_in_scan_ai_refuses_a_cloud_model() -> None:
    calls: list[httpx.Request] = []
    async with protected_local_ai.ProtectedLocalOllama(
        base_url="http://127.0.0.1:11434", model=CLOUD, transport=_refusing_transport(calls)
    ) as local:
        assert await local.assess_image(bytearray(b"signed-in page image")) is None
    assert calls == []
