"""One client for the local model service, with two backends.

Every place in Axcess that asks a local model a question (the image-of-text
check, the vision and AI wording checks, AI fix suggestions, the protected
helper app and the scan form's readiness check) goes through this module.
It has a small interface:

* :meth:`ModelClient.generate`: text from a prompt, optionally with one
  image and either a JSON schema or plain-JSON mode, at a fixed
  temperature, seed and context size.
* :meth:`ModelClient.health`: is the service up, still loading, or gone.
* :meth:`ModelClient.list_models`, :meth:`ModelClient.ready_models` and
  :meth:`ModelClient.has_model`: which models it serves.

Two backends sit behind it (``docs/internal/llama-cpp-plan.md``, Phase 1):

* :class:`OllamaClient`: Ollama's native API (``/api/generate``,
  ``/api/tags``, ``/api/version``). This is the default and sends the same
  requests the call sites sent before this module existed (same keys,
  values and value types; see :func:`ollama_generate_body`).
* :class:`LlamaCppClient`: ``llama-server`` from llama.cpp, over TCP or a
  UNIX socket (:func:`open_model_http_client`). Built from the server
  README; the main paths were then run against one real ``llama-server``
  build. The comment above :func:`llama_cpp_generate_body` lists what was
  run and what still rests on the README alone.

What this module does not do, on purpose:

* Retries and the concurrency cap stay with the callers that own them
  (:class:`audit.analyzer.ollama_base.OllamaBase` for scan-time checks), so
  one call here is exactly one HTTP request.
* Model output is untrusted. This module returns the model's text and never
  parses, validates or acts on it; each caller keeps its own parsing,
  validation and prompt-injection defences.
* These are the scan-analysis and fix-suggestion models. A future chat
  feature (AGENTS.md, "Per-report MCP conversation") must get its own
  provider setting so changing it cannot change how a report was produced.
"""

from __future__ import annotations

import base64
import enum
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, get_args

import httpx

if TYPE_CHECKING:
    from audit.config import Settings

Backend = Literal["ollama", "llama_cpp"]
BACKENDS: tuple[Backend, ...] = get_args(Backend)
DEFAULT_BACKEND: Backend = "ollama"

# A short request to a local service. Callers that need a different bound
# pass their own; nothing here waits forever.
DEFAULT_PROBE_TIMEOUT_S = 5.0


# ---------------------------------------------------------------------------
# Errors. One call can fail in four ways, and callers tell people different
# things for each (fix suggestions: "not running" vs "took too long" vs
# "model not installed" vs "bad answer"), so they stay distinct types.
# ---------------------------------------------------------------------------


class ModelServiceError(Exception):
    """The model service could not give a usable answer."""


class ModelTransportError(ModelServiceError):
    """The request did not complete (connection refused, reset, timeout)."""


class ModelTimeoutError(ModelTransportError):
    """The request took longer than its timeout."""


class ModelUnreachableError(ModelTransportError):
    """The service could not be reached or dropped the connection."""


class ModelStatusError(ModelServiceError):
    """The service answered with an HTTP status other than success."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        super().__init__(f"HTTP {status_code}" + (f": {detail}" if detail else ""))
        self.status_code = status_code
        self.detail = detail

    @property
    def transient(self) -> bool:
        """408, 429 and 5xx are worth retrying; other statuses are not."""
        return self.status_code in (408, 429) or self.status_code >= 500


class ModelResponseError(ModelServiceError):
    """The service answered, but not in the documented envelope shape."""


# ---------------------------------------------------------------------------
# Typed request / response.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GenerateRequest:
    """One prompt for one model.

    ``temperature`` is sent exactly as given (``0`` and ``0.0`` serialize
    differently in JSON, and the Ollama payloads must not change).
    ``context_tokens`` and ``keep_alive`` are per-request on Ollama; on
    ``llama-server`` they are launch options (``-c``) and are not sent.
    """

    model: str
    prompt: str
    image: bytes | None = None
    # Only llama.cpp uses it (to build a ``data:`` URL); Ollama reads the
    # format from the bytes.
    image_mime: str | None = None
    # A JSON schema the output must follow. Takes precedence over json_mode.
    json_schema: Mapping[str, Any] | None = None
    # Constrain output to any JSON object (Ollama ``format: "json"``).
    json_mode: bool = False
    temperature: float = 0.0
    seed: int | None = None
    context_tokens: int | None = None
    max_tokens: int | None = None
    keep_alive: str | int | None = None

    def __post_init__(self) -> None:
        if self.json_schema is not None and self.json_mode:
            raise ValueError("Use json_schema or json_mode, not both.")
        if self.context_tokens is not None and self.context_tokens <= 0:
            raise ValueError("context_tokens must be positive.")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive.")


@dataclass(frozen=True, slots=True)
class ServedModel:
    name: str
    size_bytes: int | None = None


class HealthState(enum.StrEnum):
    READY = "ready"
    LOADING = "loading"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class Health:
    state: HealthState
    version: str | None = None
    detail: str | None = None

    @property
    def ready(self) -> bool:
        return self.state is HealthState.READY


# ---------------------------------------------------------------------------
# Where the service is.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModelEndpoint:
    """Backend plus address. ``socket_path`` set means a UNIX socket.

    With a socket, ``base_url`` only supplies the HTTP ``Host`` header and
    path prefix; httpx connects through the socket whatever the host says.
    """

    backend: Backend
    base_url: str
    socket_path: str | None = None
    # Model name -> base URL of the server that runs only that model. Set on
    # Windows, where the private service runs one llama-server per model
    # (a Windows AppContainer blocks the loopback a router needs);
    # :class:`ModelRoutingTransport` sends each request to its model's
    # server. Sorted pairs so the endpoint stays hashable.
    routes: tuple[tuple[str, str], ...] = ()


def endpoint_from_settings(settings: Settings) -> ModelEndpoint:
    """The scan-analysis / fix-suggestion model service from settings."""
    if settings.model_backend == "llama_cpp":
        socket = settings.llama_cpp_socket
        return ModelEndpoint(
            backend="llama_cpp",
            base_url=settings.llama_cpp_url,
            socket_path=str(socket) if socket else None,
            routes=tuple(sorted((settings.llama_cpp_routes or {}).items())),
        )
    return ModelEndpoint(backend="ollama", base_url=settings.ollama_base_url)


class ModelRoutingTransport(httpx.AsyncBaseTransport):
    """Send each request to the server that runs its model.

    The model comes from the JSON body's ``model`` (POST) or the ``model``
    query parameter (GET), as llama-server's own router reads it. Requests
    that name no model are answered for all servers together: ``/health``
    is ready only when every server is; the model lists are joined.
    """

    def __init__(
        self,
        routes: Mapping[str, str],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not routes:
            raise ValueError("A routing transport needs at least one model route.")
        self._routes = {name: httpx.URL(url) for name, url in routes.items()}
        self._inner = transport or httpx.AsyncHTTPTransport()

    def _target(self, request: httpx.Request, base: httpx.URL) -> httpx.Request:
        url = request.url.copy_with(scheme=base.scheme, host=base.host, port=base.port)
        headers = httpx.Headers(request.headers)
        headers["host"] = url.netloc.decode("ascii")
        return httpx.Request(
            request.method,
            url,
            headers=headers,
            stream=request.stream,
            extensions=request.extensions,
        )

    @staticmethod
    def _model_of(request: httpx.Request) -> str | None:
        named = request.url.params.get("model")
        if named:
            return str(named)
        if request.method != "POST":
            return None
        try:
            body = json.loads(request.content or b"null")
        except (ValueError, httpx.RequestNotRead):
            return None
        value = body.get("model") if isinstance(body, dict) else None
        return value if isinstance(value, str) else None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        model = self._model_of(request)
        if model is not None:
            base = self._routes.get(model)
            if base is None:
                return httpx.Response(
                    404,
                    json={"error": {"code": 404, "message": "model not found"}},
                    request=request,
                )
            return await self._inner.handle_async_request(self._target(request, base))
        # No model named: ask every server.
        replies: list[httpx.Response] = []
        for base in self._routes.values():
            reply = await self._inner.handle_async_request(self._target(request, base))
            await reply.aread()
            replies.append(reply)
        failed = next((r for r in replies if r.status_code != 200), None)
        if failed is not None:
            return httpx.Response(
                failed.status_code,
                headers=failed.headers,
                content=failed.content,
                request=request,
            )
        if request.url.path.rstrip("/") in {"/v1/models", "/models"}:
            joined: list[Any] = []
            for reply in replies:
                data = reply.json().get("data") if reply.content else None
                joined.extend(data if isinstance(data, list) else [])
            return httpx.Response(200, json={"object": "list", "data": joined}, request=request)
        first = replies[0]
        return httpx.Response(200, headers=first.headers, content=first.content, request=request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def open_model_http_client(endpoint: ModelEndpoint, **kwargs: Any) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` that can reach ``endpoint``.

    For a TCP endpoint this is exactly ``httpx.AsyncClient(**kwargs)``, so
    existing callers build the same client they always did. For a UNIX
    socket it adds ``httpx.AsyncHTTPTransport(uds=...)`` (httpx's documented
    way to speak HTTP over a socket). The caller owns and closes the client.
    """
    if endpoint.routes:
        if "transport" in kwargs:
            raise ValueError("A routed endpoint chooses its own transport.")
        kwargs["transport"] = ModelRoutingTransport(dict(endpoint.routes))
    elif endpoint.socket_path:
        if "transport" in kwargs:
            raise ValueError("A UNIX-socket endpoint chooses its own transport.")
        kwargs["transport"] = httpx.AsyncHTTPTransport(uds=endpoint.socket_path)
    return httpx.AsyncClient(**kwargs)


# ---------------------------------------------------------------------------
# The client.
# ---------------------------------------------------------------------------


class ModelClient(ABC):
    """One local model service. One method call is one HTTP request.

    ``http`` is borrowed, never closed here: the crawl shares one client
    across checks, and tests pass mock transports through it.

    ``max_response_bytes`` set: the generate response is streamed and
    abandoned once larger than the limit (the protected helper app keeps
    model output small and in memory). Unset: a plain request, as before.
    """

    backend: ClassVar[Backend]
    label: ClassVar[str]
    generate_path: ClassVar[str]
    models_path: ClassVar[str]

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str,
        max_response_bytes: int | None = None,
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._max_response_bytes = max_response_bytes

    @property
    def base_url(self) -> str:
        return self._base_url

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    # -- generate -----------------------------------------------------------

    @abstractmethod
    def generate_body(self, request: GenerateRequest) -> dict[str, Any]:
        """The JSON body this backend sends for ``request``. Pure."""

    @abstractmethod
    def _response_text(self, envelope: Any) -> str:
        """Pull the model's text out of the decoded response envelope."""

    async def generate(self, request: GenerateRequest, *, timeout_s: float | None = None) -> str:
        """Run one prompt; return the model's raw text (untrusted)."""
        return await self.send(self.generate_body(request), timeout_s=timeout_s)

    async def send(self, body: Mapping[str, Any], *, timeout_s: float | None = None) -> str:
        """POST an already-built generate body once and return the model text.

        ``timeout_s`` None uses the http client's own timeout.

        Raises :class:`ModelTimeoutError`, :class:`ModelUnreachableError`,
        :class:`ModelStatusError` (any status but 200, as before) or
        :class:`ModelResponseError`.
        """
        extra: dict[str, Any] = {} if timeout_s is None else {"timeout": timeout_s}
        url = self._url(self.generate_path)
        content = bytearray()
        try:
            try:
                if self._max_response_bytes is None:
                    response = await self._http.post(url, json=body, **extra)
                    if response.status_code != 200:
                        raise ModelStatusError(response.status_code, response.text[:200])
                    content.extend(response.content)
                else:
                    limit = self._max_response_bytes
                    async with self._http.stream("POST", url, json=body, **extra) as response:
                        if response.status_code != 200:
                            raise ModelStatusError(response.status_code)
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > limit:
                                raise ModelResponseError(
                                    f"response larger than {limit} bytes from {self.label}"
                                )
            except httpx.TimeoutException as exc:
                raise ModelTimeoutError(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise ModelUnreachableError(str(exc)) from exc
            envelope = _decode_json(content, self.label, what="envelope")
            return self._response_text(envelope)
        finally:
            # The response can quote the evidence; do not keep a copy.
            content.clear()

    # -- models and health ----------------------------------------------------

    async def _get_json(self, path: str, timeout_s: float | None) -> Any:
        extra: dict[str, Any] = {} if timeout_s is None else {"timeout": timeout_s}
        try:
            response = await self._http.get(self._url(path), **extra)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ModelStatusError(exc.response.status_code) from exc
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ModelUnreachableError(str(exc)) from exc
        try:
            return response.json()
        except ValueError as exc:
            raise ModelResponseError(f"non-JSON reply from {self.label}: {exc}") from exc

    @abstractmethod
    def _parse_models(self, data: Any) -> list[ServedModel]: ...

    async def list_models(self, *, timeout_s: float | None = None) -> list[ServedModel]:
        """Models the service serves. Raises :class:`ModelServiceError`."""
        return self._parse_models(await self._get_json(self.models_path, timeout_s))

    async def ready_models(self, *, timeout_s: float | None = None) -> list[ServedModel]:
        """Models the service can answer with now. Raises :class:`ModelServiceError`."""
        return await self.list_models(timeout_s=timeout_s)

    async def has_model(self, model: str, *, timeout_s: float | None = None) -> bool:
        """True when the service is ready and serves ``model``. Never raises."""
        try:
            return any(m.name == model for m in await self.ready_models(timeout_s=timeout_s))
        except ModelServiceError:
            return False

    @abstractmethod
    async def health(self, *, timeout_s: float | None = DEFAULT_PROBE_TIMEOUT_S) -> Health:
        """Is the service up? Never raises."""


def _decode_json(content: bytes | bytearray, label: str, *, what: str) -> Any:
    try:
        return json.loads(bytes(content))
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
        raise ModelResponseError(f"non-JSON {what} from {label}: {exc}") from exc


# ---------------------------------------------------------------------------
# Ollama (native API).
# ---------------------------------------------------------------------------


def ollama_generate_body(request: GenerateRequest) -> dict[str, Any]:
    """Ollama ``/api/generate`` body. Same keys, values and types as before.

    Key order is fixed here (model, prompt, images, stream, format,
    keep_alive, options). Before this module each call site wrote its own
    order; Ollama decodes the body into a struct, so order has no effect.
    """
    body: dict[str, Any] = {"model": request.model, "prompt": request.prompt}
    if request.image is not None:
        # Ollama reads the image type from the bytes; no MIME type is sent.
        body["images"] = [base64.b64encode(request.image).decode("ascii")]
    body["stream"] = False
    if request.json_schema is not None:
        # Structured outputs: the same schema object, so it serializes the
        # same way it always did.
        body["format"] = request.json_schema
    elif request.json_mode:
        body["format"] = "json"
    if request.keep_alive is not None:
        body["keep_alive"] = request.keep_alive
    options: dict[str, Any] = {"temperature": request.temperature}
    if request.seed is not None:
        options["seed"] = request.seed
    if request.context_tokens is not None:
        options["num_ctx"] = request.context_tokens
    if request.max_tokens is not None:
        options["num_predict"] = request.max_tokens
    body["options"] = options
    return body


class OllamaClient(ModelClient):
    backend = "ollama"
    label = "Ollama"
    generate_path = "/api/generate"
    models_path = "/api/tags"

    def generate_body(self, request: GenerateRequest) -> dict[str, Any]:
        return ollama_generate_body(request)

    def _response_text(self, envelope: Any) -> str:
        if not isinstance(envelope, dict):
            raise ModelResponseError(f"unexpected envelope from {self.label}")
        return str(envelope.get("response", ""))

    def _parse_models(self, data: Any) -> list[ServedModel]:
        models = data.get("models", []) if isinstance(data, dict) else []
        out: list[ServedModel] = []
        for entry in models if isinstance(models, list) else []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            out.append(ServedModel(name=name.strip(), size_bytes=_size(entry.get("size"))))
        return out

    async def health(self, *, timeout_s: float | None = DEFAULT_PROBE_TIMEOUT_S) -> Health:
        """``GET /api/version``. Ollama has no separate "loading" state."""
        try:
            data = await self._get_json("/api/version", timeout_s)
        except ModelServiceError as exc:
            return Health(HealthState.UNAVAILABLE, detail=str(exc)[:200])
        version = data.get("version") if isinstance(data, dict) else None
        return Health(HealthState.READY, version=str(version) if version else None)


# ---------------------------------------------------------------------------
# llama.cpp (llama-server).
#
# Source for everything below: tools/server/README.md in ggml-org/llama.cpp
# (master, read 2026-11-11):
# https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
#
# Request shape: "POST /v1/chat/completions: OpenAI-compatible Chat
# Completions API". It is the documented shape that carries BOTH a JSON
# schema (``response_format``: "The `response_format` parameter supports both
# plain JSON output (e.g. `{"type": "json_object"}`) and schema-constrained
# JSON", and "The OpenAI wrapper form `{"type": "json_schema", "json_schema":
# {"name": ..., "strict": ..., "schema": {...}}}` is also accepted") AND an
# image (content part ``type == "image_url"``; "`image_url.url` can be a
# remote URL, base64 (raw or URI-encoded via `data:image/...;base64`)").
#
# Rejected: ``POST /completion`` with ``json_schema`` and ``{"prompt_string",
# "multimodal_data"}``. It also carries both, but it is a raw completion: it
# does not apply the model's chat template, while Ollama's /api/generate,
# which every prompt here was written for, does. It also needs a media
# marker in the prompt matching each image, and the README says a client
# "must not" send multimodal_data unless the server has that capability.
#
# Not sent: context size (``-c, --ctx-size`` is a launch option; no request
# field sets it) and keep_alive (the server keeps its model loaded). The
# launcher (Phase 2) must start the server with a context at least as large
# as the largest ``context_tokens`` a caller asks for.
#
# Run against a real llama-server (release b12284, CPU build, one
# Qwen3-VL-2B-Instruct model with its mmproj, context 4096, UNIX socket; see
# tests/integration/test_llama_cpp_live.py, opt-in with AXCESS_LLAMA_SOCKET):
# /health 200 {"status": "ok"}; the /v1/models shape (``id`` is the model
# file path when no ``--alias`` is set; ``meta.size`` is an integer); chat
# completions with a JSON schema and an image (data: URL and raw base64) in
# one call, a JSON schema without an image, and ``json_object`` mode; the
# same answer twice at temperature 0 with a fixed seed; and a real crawl
# reaching it through the socket.
#
# Still README only: /health's 503 "Loading model" state, router mode (the
# ``model`` field routing: "The router uses the `"model"` field in the JSON
# body", and the model list there), how ``--alias`` changes the listed id,
# that ``max_tokens`` stops a long answer, and the error statuses and bodies
# llama-server returns.
# ---------------------------------------------------------------------------

LLAMA_CPP_SCHEMA_NAME = "axcess_answer"


def llama_cpp_generate_body(request: GenerateRequest) -> dict[str, Any]:
    """``llama-server`` ``/v1/chat/completions`` body for ``request``."""
    content: str | list[dict[str, Any]]
    if request.image is not None:
        encoded = base64.b64encode(request.image).decode("ascii")
        mime = request.image_mime or ""
        # A specific image type becomes a data: URL; otherwise raw base64,
        # which the README also accepts.
        url = (
            f"data:{mime};base64,{encoded}"
            if mime.startswith("image/") and "*" not in mime
            else encoded
        )
        content = [
            {"type": "image_url", "image_url": {"url": url}},
            {"type": "text", "text": request.prompt},
        ]
    else:
        content = request.prompt
    body: dict[str, Any] = {
        # Ignored by a single-model server; picks the model in router mode.
        "model": request.model,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        "temperature": request.temperature,
    }
    if request.seed is not None:
        body["seed"] = request.seed
    if request.max_tokens is not None:
        body["max_tokens"] = request.max_tokens
    if request.json_schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": LLAMA_CPP_SCHEMA_NAME,
                "strict": True,
                "schema": request.json_schema,
            },
        }
    elif request.json_mode:
        body["response_format"] = {"type": "json_object"}
    return body


class LlamaCppClient(ModelClient):
    backend = "llama_cpp"
    label = "llama.cpp server"
    generate_path = "/v1/chat/completions"
    models_path = "/v1/models"

    def generate_body(self, request: GenerateRequest) -> dict[str, Any]:
        return llama_cpp_generate_body(request)

    def _response_text(self, envelope: Any) -> str:
        try:
            content = envelope["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelResponseError(f"unexpected envelope from {self.label}") from exc
        if content is None:
            return ""
        if not isinstance(content, str):
            raise ModelResponseError(f"unexpected message content from {self.label}")
        return content

    def _parse_models(self, data: Any) -> list[ServedModel]:
        # README: OpenAI shape, {"object": "list", "data": [{"id": ...,
        # "meta": {...}}]}; "The returned list always has one single
        # element" outside router mode. ``meta.size`` is read when present.
        entries = data.get("data", []) if isinstance(data, dict) else []
        out: list[ServedModel] = []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("id")
            if not isinstance(name, str) or not name.strip():
                continue
            meta = entry.get("meta")
            size = _size(meta.get("size")) if isinstance(meta, dict) else None
            out.append(ServedModel(name=name.strip(), size_bytes=size))
        return out

    async def health(self, *, timeout_s: float | None = DEFAULT_PROBE_TIMEOUT_S) -> Health:
        """README "GET /health": 503 while the model loads, 200 {"status":"ok"}."""
        extra: dict[str, Any] = {} if timeout_s is None else {"timeout": timeout_s}
        try:
            response = await self._http.get(self._url("/health"), **extra)
        except httpx.HTTPError as exc:
            return Health(HealthState.UNAVAILABLE, detail=str(exc)[:200])
        if response.status_code == 503:
            return Health(HealthState.LOADING, detail="Loading model")
        if response.status_code != 200:
            return Health(HealthState.UNAVAILABLE, detail=f"HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError:
            return Health(HealthState.UNAVAILABLE, detail="non-JSON health reply")
        if isinstance(data, dict) and data.get("status") == "ok":
            return Health(HealthState.READY)
        return Health(HealthState.UNAVAILABLE, detail="unexpected health reply")

    async def ready_models(self, *, timeout_s: float | None = None) -> list[ServedModel]:
        """Served models, but only once ``/health`` says the server is ready.

        A server still loading its model lists it but cannot answer yet.
        Outside router mode the one model is listed under its ``--alias``
        (or file path); the launcher must set the alias to the name Axcess
        asks for.
        """
        health = await self.health(timeout_s=timeout_s)
        if health.state is HealthState.LOADING:
            raise ModelStatusError(503, "Loading model")
        if not health.ready:
            raise ModelUnreachableError(health.detail or "not ready")
        return await self.list_models(timeout_s=timeout_s)


def _size(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, int(value))


def make_model_client(
    backend: str,
    http: httpx.AsyncClient,
    *,
    base_url: str,
    max_response_bytes: int | None = None,
) -> ModelClient:
    """The client for ``backend`` ("ollama" or "llama_cpp")."""
    if backend == "ollama":
        return OllamaClient(http, base_url=base_url, max_response_bytes=max_response_bytes)
    if backend == "llama_cpp":
        return LlamaCppClient(http, base_url=base_url, max_response_bytes=max_response_bytes)
    raise ValueError(f"Unknown model backend {backend!r}; expected one of {BACKENDS}.")


__all__ = [
    "BACKENDS",
    "DEFAULT_BACKEND",
    "Backend",
    "GenerateRequest",
    "Health",
    "HealthState",
    "LlamaCppClient",
    "ModelClient",
    "ModelEndpoint",
    "ModelResponseError",
    "ModelRoutingTransport",
    "ModelServiceError",
    "ModelStatusError",
    "ModelTimeoutError",
    "ModelTransportError",
    "ModelUnreachableError",
    "OllamaClient",
    "ServedModel",
    "endpoint_from_settings",
    "llama_cpp_generate_body",
    "make_model_client",
    "ollama_generate_body",
    "open_model_http_client",
]
