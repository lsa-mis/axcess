"""No AI feature sends scan data to an Ollama cloud model.

Ollama runs a model tagged ``cloud`` or ``...-cloud`` on its own servers,
even when Axcess asks the local daemon. Each call path refuses such a model
before any request is made, so the page text and images stay on this
computer.
"""

from __future__ import annotations

import httpx
import pytest

from audit.analyzer.ollama_base import OllamaError, is_cloud_model, why_not_local
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
        # No tag means ":latest", a local model, even if the name ends in -cloud.
        ("campus-cloud", False),
        ("campus-cloud:latest", False),
        ("campus-cloud:7b-cloud", True),
        # A registry with a port: the colon before the slash is not a tag.
        ("registry.local:5000/llava", False),
        ("registry.local:5000/campus-cloud", False),
        ("registry.local:5000/llava:7b", False),
        ("registry.local:5000/gpt-oss:120b-cloud", True),
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
    assert raised.value.code == "model_not_local"
    assert calls == []


@pytest.mark.asyncio
async def test_sign_in_scan_ai_refuses_a_cloud_model() -> None:
    calls: list[httpx.Request] = []
    async with protected_local_ai.ProtectedLocalOllama(
        base_url="http://127.0.0.1:11434", model=CLOUD, transport=_refusing_transport(calls)
    ) as local:
        assert await local.assess_image(bytearray(b"signed-in page image")) is None
    assert calls == []


# A cloud model copied to a local-looking name (``ollama cp
# gpt-oss:120b-cloud campus-model``) has no "cloud" tag. Ollama's own model
# list still marks it with remote_host and remote_model.
ALIAS = "campus-model"


def _daemon(calls: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": f"{ALIAS}:latest",
                            "model": f"{ALIAS}:latest",
                            "remote_model": "gpt-oss:120b",
                            "remote_host": "https://ollama.com:443",
                        },
                        {"name": "llava:7b", "model": "llava:7b"},
                    ]
                },
            )
        calls.append(request)
        return httpx.Response(200, json={"response": "{}"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_scan_analysis_refuses_a_cloud_model_under_a_local_name() -> None:
    calls: list[httpx.Request] = []
    async with httpx.AsyncClient(transport=_daemon(calls)) as client:
        provider = OllamaTextProvider(client, model=ALIAS, base_url="http://127.0.0.1:11434")
        with pytest.raises(OllamaError, match="cloud model"):
            await provider._post_with_retries({"model": ALIAS, "prompt": "page text"})
        # A local model on the same daemon still works.
        local = OllamaTextProvider(client, model="llava:7b", base_url="http://127.0.0.1:11434")
        await local._post_with_retries({"model": "llava:7b", "prompt": "page text"})
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_fix_suggestions_refuse_a_cloud_model_under_a_local_name() -> None:
    calls: list[httpx.Request] = []
    async with httpx.AsyncClient(transport=_daemon(calls)) as client:
        provider = OllamaSuggestionProvider(client, base_url="http://127.0.0.1:11434", timeout_s=30)
        with pytest.raises(SuggestionError):
            await provider.generate("evidence", model=ALIAS, image=None)
    assert calls == []


@pytest.mark.asyncio
async def test_sign_in_scan_ai_refuses_a_cloud_model_under_a_local_name() -> None:
    calls: list[httpx.Request] = []
    async with protected_local_ai.ProtectedLocalOllama(
        base_url="http://127.0.0.1:11434", model=ALIAS, transport=_daemon(calls)
    ) as local:
        assert await local.assess_image(bytearray(b"signed-in page image")) is None
    assert calls == []


@pytest.mark.parametrize(
    "tags",
    [
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, json=["not", "an", "object"]),
        # Malformed entries inside the list.
        httpx.Response(200, json={"models": [None]}),
        httpx.Response(200, json={"models": [{"remote_host": "https://ollama.com:443"}]}),
        httpx.Response(200, json={"models": [{"name": ""}]}),
        httpx.Response(200, json={"models": [{"name": 7}]}),
        # Well formed, but the model is not in the list.
        httpx.Response(200, json={"models": [{"name": "other:1b"}]}),
        httpx.Response(200, json={"models": []}),
    ],
)
@pytest.mark.asyncio
async def test_every_path_refuses_when_the_model_list_cannot_be_read(
    tags: httpx.Response,
) -> None:
    # Fails closed: no model is trusted as local without Ollama's own list.
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return tags
        calls.append(request)
        return httpx.Response(200, json={"response": "{}"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OllamaTextProvider(client, model="llava:7b", base_url="http://127.0.0.1:11434")
        with pytest.raises(OllamaError, match="could not confirm"):
            await provider._post_with_retries({"model": "llava:7b", "prompt": "page text"})
        suggestions = OllamaSuggestionProvider(
            client, base_url="http://127.0.0.1:11434", timeout_s=30
        )
        with pytest.raises(SuggestionError):
            await suggestions.generate("evidence", model="llava:7b", image=None)
    async with protected_local_ai.ProtectedLocalOllama(
        base_url="http://127.0.0.1:11434", model="llava:7b", transport=transport
    ) as local:
        assert await local.assess_image(bytearray(b"signed-in page image")) is None
    assert calls == []


@pytest.mark.asyncio
async def test_a_timeout_reading_the_model_list_refuses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            raise httpx.ReadTimeout("slow", request=request)
        raise AssertionError("nothing may be sent")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaTextProvider(client, model="llava:7b", base_url="http://127.0.0.1:11434")
        with pytest.raises(OllamaError, match="could not confirm"):
            await provider._post_with_retries({"model": "llava:7b", "prompt": "page text"})


@pytest.mark.asyncio
async def test_a_model_replaced_by_a_cloud_copy_is_refused_on_the_next_call() -> None:
    # ``ollama cp gpt-oss:120b-cloud llava:7b`` during a scan: the next
    # request reads the list again and sends nothing.
    replaced = False
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            entry: dict[str, str] = {"name": "llava:7b"}
            if replaced:
                entry |= {"remote_host": "https://ollama.com:443", "remote_model": "gpt-oss:120b"}
            return httpx.Response(200, json={"models": [entry]})
        calls.append(request)
        return httpx.Response(200, json={"response": "{}"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaTextProvider(client, model="llava:7b", base_url="http://127.0.0.1:11434")
        await provider._post_with_retries({"model": "llava:7b", "prompt": "page one"})
        replaced = True
        with pytest.raises(OllamaError, match="cloud model"):
            await provider._post_with_retries({"model": "llava:7b", "prompt": "page two"})
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_model_replaced_between_retries_is_refused_on_the_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The first send fails with a 503; the model is swapped for a cloud copy
    # before the retry, which reads the list again and sends nothing more.
    monkeypatch.setattr("audit.analyzer.ollama_base.asyncio.sleep", _no_wait)
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            entry: dict[str, str] = {"name": "llava:7b"}
            if sends:
                entry |= {"remote_host": "https://ollama.com:443", "remote_model": "gpt-oss:120b"}
            return httpx.Response(200, json={"models": [entry]})
        sends.append(request)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaTextProvider(
            client, model="llava:7b", base_url="http://127.0.0.1:11434", max_attempts=3
        )
        with pytest.raises(OllamaError, match="cloud model"):
            await provider._post_with_retries({"model": "llava:7b", "prompt": "page text"})
    assert len(sends) == 1


async def _no_wait(_seconds: float) -> None:
    return None


@pytest.mark.parametrize(
    ("model", "listed"),
    [
        ("registry.local:5000/llava", "registry.local:5000/llava:latest"),
        ("registry.local:5000/llava:7b", "registry.local:5000/llava:7b"),
        ("llava", "llava:latest"),
    ],
)
@pytest.mark.asyncio
async def test_a_model_from_a_registry_with_a_port_matches_its_listed_name(
    model: str, listed: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": listed, "model": listed}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await why_not_local(client, "http://127.0.0.1:11434/api/tags", model) is None


async def test_the_check_runs_for_ollama_and_not_for_llama_cpp() -> None:
    """Only Ollama has cloud models. A llama.cpp server runs the files it was
    started with, so asking it for Ollama's model list would only fail."""
    from audit.ai.model_client import make_model_client
    from audit.analyzer.ollama_base import why_not_local_service

    asked: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return httpx.Response(200, json={"models": [{"name": "text:local"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        ollama = make_model_client("ollama", http, base_url="http://127.0.0.1:11434")
        llama = make_model_client("llama_cpp", http, base_url="http://localhost")
        assert await why_not_local_service(ollama, http, "text:local") is None
        assert await why_not_local_service(ollama, http, "gpt-oss:120b-cloud") is not None
        assert await why_not_local_service(llama, http, "text-local") is None
    assert asked == ["/api/tags"]
