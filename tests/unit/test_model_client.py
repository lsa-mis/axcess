"""The local model client and its two backends, against fake servers.

No real Ollama or ``llama-server`` runs here. The llama.cpp request and
response shapes come from the server README (see the comment block in
``audit.ai.model_client``); these tests pin that reading of it, they do not
prove a real server agrees. The UNIX-socket tests do use a real socket, with
a tiny HTTP responder in place of the server.
"""

from __future__ import annotations

import asyncio
import base64
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from audit.ai.model_client import (
    GenerateRequest,
    HealthState,
    LlamaCppClient,
    ModelEndpoint,
    ModelResponseError,
    ModelStatusError,
    ModelTimeoutError,
    ModelUnreachableError,
    OllamaClient,
    ServedModel,
    endpoint_from_settings,
    llama_cpp_generate_body,
    make_model_client,
    ollama_generate_body,
    open_model_http_client,
)
from audit.config import Settings

BASE = "http://model.test"
IMAGE = b"\x89PNG\r\n\x1a\nfake-image"
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"label": {"type": "string"}},
    "required": ["label"],
}

Handler = Callable[[httpx.Request], httpx.Response]


def _http(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _recording(
    response: httpx.Response | Callable[[], httpx.Response],
) -> tuple[Handler, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response() if callable(response) else response

    return handler, seen


# ---------------------------------------------------------------------------
# Typed request
# ---------------------------------------------------------------------------


def test_request_rejects_schema_and_json_mode_together() -> None:
    with pytest.raises(ValueError):
        GenerateRequest(model="m", prompt="p", json_schema=SCHEMA, json_mode=True)


@pytest.mark.parametrize("field", ["context_tokens", "max_tokens"])
def test_request_rejects_non_positive_bounds(field: str) -> None:
    with pytest.raises(ValueError):
        GenerateRequest(model="m", prompt="p", **{field: 0})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------


def test_ollama_body_full_shape() -> None:
    body = ollama_generate_body(
        GenerateRequest(
            model="m",
            prompt="p",
            image=IMAGE,
            image_mime="image/png",
            json_schema=SCHEMA,
            temperature=0,
            seed=7,
            context_tokens=8192,
            max_tokens=100,
            keep_alive="10m",
        )
    )
    assert body == {
        "model": "m",
        "prompt": "p",
        "images": [base64.b64encode(IMAGE).decode("ascii")],
        "stream": False,
        "format": SCHEMA,
        "keep_alive": "10m",
        "options": {"temperature": 0, "seed": 7, "num_ctx": 8192, "num_predict": 100},
    }
    # The MIME type is never sent to Ollama, and temperature keeps its type.
    assert "image_mime" not in json.dumps(body)
    assert json.dumps(body["options"]["temperature"]) == "0"


def test_ollama_body_minimal_and_json_mode() -> None:
    assert ollama_generate_body(GenerateRequest(model="m", prompt="p")) == {
        "model": "m",
        "prompt": "p",
        "stream": False,
        "options": {"temperature": 0.0},
    }
    body = ollama_generate_body(GenerateRequest(model="m", prompt="p", json_mode=True))
    assert body["format"] == "json"


async def test_ollama_generate_posts_body_and_returns_response_text() -> None:
    handler, seen = _recording(httpx.Response(200, json={"response": '{"a": 1}'}))
    async with _http(handler) as http:
        client = OllamaClient(http, base_url=BASE + "/")
        out = await client.generate(GenerateRequest(model="m", prompt="p", json_mode=True))
    assert out == '{"a": 1}'
    assert seen[0].method == "POST"
    assert str(seen[0].url) == f"{BASE}/api/generate"
    assert json.loads(seen[0].content)["format"] == "json"


async def test_ollama_missing_response_field_is_empty_text() -> None:
    handler, _ = _recording(httpx.Response(200, json={"done": True}))
    async with _http(handler) as http:
        assert await OllamaClient(http, base_url=BASE).send({}) == ""


@pytest.mark.parametrize(
    ("status", "transient"), [(400, False), (404, False), (408, True), (429, True), (503, True)]
)
async def test_status_errors_carry_status_and_transience(status: int, transient: bool) -> None:
    handler, _ = _recording(httpx.Response(status, text="nope " * 100))
    async with _http(handler) as http:
        with pytest.raises(ModelStatusError) as caught:
            await OllamaClient(http, base_url=BASE).send({})
    assert caught.value.status_code == status
    assert caught.value.transient is transient
    assert len(caught.value.detail) == 200


async def test_timeout_and_connection_errors_are_distinct() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    for backend_cls in (OllamaClient, LlamaCppClient):
        async with _http(timeout) as http:
            with pytest.raises(ModelTimeoutError):
                await backend_cls(http, base_url=BASE).send({})
        async with _http(refused) as http:
            with pytest.raises(ModelUnreachableError):
                await backend_cls(http, base_url=BASE).send({})


@pytest.mark.parametrize("content", [b"not json", b"\xff\xfe\xfa", b"[1, 2]", b'"text"'])
async def test_ollama_malformed_envelope(content: bytes) -> None:
    handler, _ = _recording(httpx.Response(200, content=content))
    async with _http(handler) as http:
        with pytest.raises(ModelResponseError):
            await OllamaClient(http, base_url=BASE).send({})


async def test_per_call_timeout_reaches_the_request() -> None:
    handler, seen = _recording(httpx.Response(200, json={"response": "x"}))
    async with _http(handler) as http:
        await OllamaClient(http, base_url=BASE).send({}, timeout_s=3.5)
    assert seen[0].extensions["timeout"]["read"] == 3.5


async def test_response_cap_streams_and_rejects_oversized_answers() -> None:
    big = {"response": "x" * 5000}
    handler, _ = _recording(httpx.Response(200, json=big))
    async with _http(handler) as http:
        with pytest.raises(ModelResponseError, match="larger than"):
            await OllamaClient(http, base_url=BASE, max_response_bytes=1024).send({})
        small = OllamaClient(http, base_url=BASE, max_response_bytes=10_000)
        assert await small.send({}) == "x" * 5000


async def test_response_cap_does_not_read_a_failed_body() -> None:
    handler, _ = _recording(httpx.Response(500, text="x" * 10_000))
    async with _http(handler) as http:
        with pytest.raises(ModelStatusError) as caught:
            await OllamaClient(http, base_url=BASE, max_response_bytes=10).send({})
    assert caught.value.status_code == 500


async def test_ollama_list_models_and_has_model() -> None:
    tags = {
        "models": [
            {"name": "qwen3-vl:2b-instruct", "size": 1_900_000_000},
            {"name": "no-size"},
            {"name": ""},
            "not-a-dict",
            {"size": 5},
        ]
    }
    handler, seen = _recording(httpx.Response(200, json=tags))
    async with _http(handler) as http:
        client = OllamaClient(http, base_url=BASE)
        assert await client.list_models() == [
            ServedModel("qwen3-vl:2b-instruct", 1_900_000_000),
            ServedModel("no-size", None),
        ]
        assert await client.has_model("qwen3-vl:2b-instruct", timeout_s=5.0)
        assert not await client.has_model("other")
    assert str(seen[0].url) == f"{BASE}/api/tags"


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(200, content=b"<html>"), httpx.Response(404)],
)
async def test_has_model_is_false_on_any_failure(response: httpx.Response) -> None:
    handler, _ = _recording(response)
    async with _http(handler) as http:
        assert not await OllamaClient(http, base_url=BASE).has_model("m")


async def test_list_models_raises_typed_errors() -> None:
    handler, _ = _recording(httpx.Response(500))
    async with _http(handler) as http:
        with pytest.raises(ModelStatusError):
            await OllamaClient(http, base_url=BASE).list_models()
    handler, _ = _recording(httpx.Response(200, content=b"nope"))
    async with _http(handler) as http:
        with pytest.raises(ModelResponseError):
            await OllamaClient(http, base_url=BASE).list_models()


async def test_ollama_health_uses_version() -> None:
    handler, seen = _recording(httpx.Response(200, json={"version": "0.33.0"}))
    async with _http(handler) as http:
        health = await OllamaClient(http, base_url=BASE).health()
    assert health.ready and health.version == "0.33.0"
    assert seen[0].url.path == "/api/version"

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    async with _http(down) as http:
        health = await OllamaClient(http, base_url=BASE).health()
    assert health.state is HealthState.UNAVAILABLE


# ---------------------------------------------------------------------------
# llama.cpp backend (shapes from the README; see module docstring)
# ---------------------------------------------------------------------------


def _chat_reply(content: object) -> dict[str, Any]:
    return {"choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]}


def test_llama_cpp_body_carries_schema_and_image_in_one_call() -> None:
    body = llama_cpp_generate_body(
        GenerateRequest(
            model="vision:test",
            prompt="Describe it.",
            image=IMAGE,
            image_mime="image/png",
            json_schema=SCHEMA,
            temperature=0,
            seed=42,
            context_tokens=8192,
            max_tokens=300,
            keep_alive="10m",
        )
    )
    assert body == {
        "model": "vision:test",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + base64.b64encode(IMAGE).decode()
                        },
                    },
                    {"type": "text", "text": "Describe it."},
                ],
            }
        ],
        "stream": False,
        "temperature": 0,
        "seed": 42,
        "max_tokens": 300,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "axcess_answer", "strict": True, "schema": SCHEMA},
        },
    }
    # Launch options on llama-server, never request fields.
    assert "num_ctx" not in json.dumps(body)
    assert "keep_alive" not in body


@pytest.mark.parametrize("mime", [None, "image/*", "application/octet-stream"])
def test_llama_cpp_unknown_image_type_is_sent_as_raw_base64(mime: str | None) -> None:
    body = llama_cpp_generate_body(
        GenerateRequest(model="m", prompt="p", image=IMAGE, image_mime=mime)
    )
    part = body["messages"][0]["content"][0]
    assert part["image_url"]["url"] == base64.b64encode(IMAGE).decode()


def test_llama_cpp_text_only_and_json_mode() -> None:
    body = llama_cpp_generate_body(GenerateRequest(model="m", prompt="p", json_mode=True))
    assert body == {
        "model": "m",
        "messages": [{"role": "user", "content": "p"}],
        "stream": False,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    plain = llama_cpp_generate_body(GenerateRequest(model="m", prompt="p"))
    assert "response_format" not in plain


async def test_llama_cpp_generate_reads_message_content() -> None:
    handler, seen = _recording(httpx.Response(200, json=_chat_reply('{"label": "logo"}')))
    async with _http(handler) as http:
        out = await LlamaCppClient(http, base_url=BASE).generate(
            GenerateRequest(model="m", prompt="p", json_schema=SCHEMA), timeout_s=30.0
        )
    assert out == '{"label": "logo"}'
    assert str(seen[0].url) == f"{BASE}/v1/chat/completions"


async def test_llama_cpp_null_content_is_empty_text() -> None:
    handler, _ = _recording(httpx.Response(200, json=_chat_reply(None)))
    async with _http(handler) as http:
        assert await LlamaCppClient(http, base_url=BASE).send({}) == ""


@pytest.mark.parametrize(
    "envelope",
    [{}, {"choices": []}, {"choices": [{}]}, {"choices": [{"message": {"content": 3}}]}, [1]],
)
async def test_llama_cpp_malformed_envelope(envelope: object) -> None:
    handler, _ = _recording(httpx.Response(200, json=envelope))
    async with _http(handler) as http:
        with pytest.raises(ModelResponseError):
            await LlamaCppClient(http, base_url=BASE).send({})


@pytest.mark.parametrize(
    ("response", "state"),
    [
        (httpx.Response(200, json={"status": "ok"}), HealthState.READY),
        (
            httpx.Response(
                503,
                json={
                    "error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}
                },
            ),
            HealthState.LOADING,
        ),
        (httpx.Response(500), HealthState.UNAVAILABLE),
        (httpx.Response(200, json={"status": "starting"}), HealthState.UNAVAILABLE),
        (httpx.Response(200, content=b"ok"), HealthState.UNAVAILABLE),
    ],
)
async def test_llama_cpp_health_states(response: httpx.Response, state: HealthState) -> None:
    handler, seen = _recording(response)
    async with _http(handler) as http:
        health = await LlamaCppClient(http, base_url=BASE).health()
    assert health.state is state
    assert seen[0].url.path == "/health"


async def test_llama_cpp_health_unreachable() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    async with _http(down) as http:
        health = await LlamaCppClient(http, base_url=BASE).health()
    assert health.state is HealthState.UNAVAILABLE


def _llama_server(health_status: int = 200) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            if health_status == 503:
                return httpx.Response(503, json={"error": {"message": "Loading model"}})
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"id": "text:test", "object": "model", "meta": {"size": 4_000}},
                        {"id": "bare", "object": "model"},
                        {"object": "model"},
                    ],
                },
            )
        return httpx.Response(404)

    return handler


async def test_llama_cpp_lists_models_and_checks_readiness() -> None:
    async with _http(_llama_server()) as http:
        client = LlamaCppClient(http, base_url=BASE)
        assert await client.list_models() == [
            ServedModel("text:test", 4_000),
            ServedModel("bare", None),
        ]
        assert await client.has_model("text:test")
        assert not await client.has_model("other")
    async with _http(_llama_server(health_status=503)) as http:
        # Listed, but still loading: not usable yet.
        assert not await LlamaCppClient(http, base_url=BASE).has_model("text:test")


# ---------------------------------------------------------------------------
# Endpoint, factory and UNIX socket
# ---------------------------------------------------------------------------


def test_endpoint_from_settings() -> None:
    assert endpoint_from_settings(Settings()) == ModelEndpoint(
        "ollama", "http://localhost:11434", None
    )
    llama = Settings(
        model_backend="llama_cpp",
        llama_cpp_url="http://llama",
        llama_cpp_socket=Path("/run/axcess/llama.sock"),
    )
    assert endpoint_from_settings(llama) == ModelEndpoint(
        "llama_cpp", "http://llama", "/run/axcess/llama.sock"
    )
    tcp = Settings(model_backend="llama_cpp")
    assert endpoint_from_settings(tcp) == ModelEndpoint("llama_cpp", "http://127.0.0.1:8080")


def test_settings_reject_unknown_backend() -> None:
    with pytest.raises(ValueError):
        Settings(model_backend="openai")  # type: ignore[arg-type]


async def test_make_model_client_picks_backend() -> None:
    async with httpx.AsyncClient() as http:
        assert isinstance(make_model_client("ollama", http, base_url=BASE), OllamaClient)
        assert isinstance(make_model_client("llama_cpp", http, base_url=BASE), LlamaCppClient)
        with pytest.raises(ValueError):
            make_model_client("nope", http, base_url=BASE)


async def test_open_client_tcp_is_a_plain_client(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[dict[str, Any]] = []

    def fake(**kwargs: Any) -> str:
        made.append(kwargs)
        return "client"

    monkeypatch.setattr(httpx, "AsyncClient", fake)
    open_model_http_client(ModelEndpoint("ollama", BASE), timeout=2.0)
    assert made == [{"timeout": 2.0}]


async def test_open_client_unix_socket_builds_uds_transport() -> None:
    endpoint = ModelEndpoint("llama_cpp", "http://llama", "/run/axcess/llama.sock")
    async with open_model_http_client(endpoint, timeout=2.0) as http:
        transport = http._transport
        assert isinstance(transport, httpx.AsyncHTTPTransport)
        assert transport._pool._uds == "/run/axcess/llama.sock"
    with pytest.raises(ValueError):
        open_model_http_client(endpoint, transport=httpx.MockTransport(lambda r: r))  # type: ignore[arg-type,return-value]


async def test_llama_cpp_over_a_real_unix_socket() -> None:
    """A real socket and a tiny HTTP responder stand in for llama-server."""
    requests: list[tuple[str, bytes]] = []

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        request_line = head.split(b"\r\n", 1)[0].decode()
        length = 0
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            if name.strip().lower() == b"content-length":
                length = int(value.strip())
        body = await reader.readexactly(length) if length else b""
        requests.append((request_line, body))
        path = request_line.split(" ")[1]
        reply = (
            {"status": "ok"}
            if path == "/health"
            else {"data": [{"id": "text:test"}]}
            if path == "/v1/models"
            else _chat_reply('{"ok": true}')
        )
        payload = json.dumps(reply).encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode()
            + payload
        )
        await writer.drain()
        writer.close()

    # Short directory: UNIX socket paths are limited to about 100 bytes.
    with tempfile.TemporaryDirectory(prefix="axcess-") as tmp:
        sock = str(Path(tmp) / "llama.sock")
        server = await asyncio.start_unix_server(serve, path=sock)
        try:
            endpoint = ModelEndpoint("llama_cpp", "http://llama-server", sock)
            async with open_model_http_client(endpoint, timeout=5.0) as http:
                client = make_model_client(endpoint.backend, http, base_url=endpoint.base_url)
                assert (await client.health()).ready
                assert await client.has_model("text:test")
                out = await client.generate(
                    GenerateRequest(model="text:test", prompt="p", json_mode=True)
                )
        finally:
            server.close()
            await server.wait_closed()
    assert out == '{"ok": true}'
    assert [line for line, _ in requests] == [
        "GET /health HTTP/1.1",
        "GET /health HTTP/1.1",
        "GET /v1/models HTTP/1.1",
        "POST /v1/chat/completions HTTP/1.1",
    ]
    assert json.loads(requests[-1][1])["response_format"] == {"type": "json_object"}
