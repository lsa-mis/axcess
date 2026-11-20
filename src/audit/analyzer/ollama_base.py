"""Shared model-service plumbing, the bit both VLM and text analyzers need.

Two analyzers talk to the same local model service:

* :class:`~audit.analyzer.vlm.ollama.OllamaProvider`, the image-of-text
  classifier (VLM, the 1.4.5 pipeline). Already in production.
* :class:`~audit.analyzer.semantic.ollama_text.OllamaTextProvider`, the
  per-criterion text analyzer added in Phase 9. Generic
  ``generate(prompt) -> str``; the caller owns the prompt template.

Both want the same machinery: shared semaphore (so one global
``concurrency`` knob caps total in-flight calls to the service), retry
with exponential backoff on 408/429/5xx, a ``healthy()`` probe,
``temperature=0`` for determinism, and JSON output for
structured-output reliability.

We factor that machinery here so neither subclass owns the HTTP
layer. Subclasses describe each call as a typed
:class:`~audit.ai.model_client.GenerateRequest`; the model client
(:mod:`audit.ai.model_client`) turns it into the selected backend's
request. The default backend is Ollama, which receives exactly the
requests it always did. The class names keep "Ollama" because other code
and tests import them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Mapping
from typing import Any

import httpx

from audit.ai.model_client import (
    DEFAULT_BACKEND,
    GenerateRequest,
    ModelClient,
    ModelResponseError,
    ModelStatusError,
    ModelTimeoutError,
    ModelTransportError,
    make_model_client,
)
from audit.logging import get_logger

log = get_logger(__name__)
_httpx_log = logging.getLogger("httpx")
_httpx_log.setLevel(logging.WARNING)  # /api/generate is chatty at INFO


class OllamaError(Exception):
    """Raised when the model service cannot return a usable response.

    The name predates the llama.cpp backend; it is raised for either.

    The VLM module re-exports this as ``VlmError`` for back-compat with
    callers that imported the older name; new code should use
    ``OllamaError``.
    """


def _tag(name: str) -> str | None:
    """The tag after the last colon, or None when the name has no tag.

    A colon followed by a slash belongs to a registry address with a port
    (``registry.local:5000/llava``), not to a tag; a tag never has a slash.
    """
    _, colon, tag = name.strip().rpartition(":")
    return tag if colon and "/" not in tag else None


def is_cloud_model(name: str) -> bool:
    """True for an Ollama cloud model, such as ``gpt-oss:120b-cloud``.

    Ollama runs these on its own servers even when asked through the local
    daemon, so the prompt, page text and images would leave the computer.
    Ollama marks them with a tag that is ``cloud`` or ends in ``-cloud``.
    Every Axcess model call refuses them: no AI feature sends scan data off
    the computer unless an administrator chooses a remote address
    (AGENTS.md, "Context construction and privacy").
    """
    # No tag means the default (":latest"), a local model, even when the name
    # itself ends in "-cloud".
    tag = _tag(name.lower())
    return tag is not None and (tag == "cloud" or tag.endswith("-cloud"))


def _names(name: str) -> set[str]:
    """A model's name as Ollama may list it: with no tag it is ``:latest``."""
    name = name.strip()
    return {name} if _tag(name) is not None else {name, f"{name}:latest"}


async def model_list(client: httpx.AsyncClient, tags_url: str) -> tuple[set[str], set[str]] | None:
    """``(local, remote)`` model names from the daemon's ``/api/tags``.

    Ollama lists ``remote_host`` and ``remote_model`` only for a model that
    runs on another host (https://docs.ollama.com/api/tags). That catches a
    cloud model copied to a local-looking name (``ollama cp``), which
    :func:`is_cloud_model` cannot see. ``None`` when the list cannot be read
    or any entry is not the shape Ollama documents (an object with a name):
    then no model is known to be local.
    """
    try:
        resp = await client.get(tags_url, timeout=5.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError):
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return None
    local: set[str] = set()
    remote: set[str] = set()
    for entry in models:
        if not isinstance(entry, dict):
            return None
        names = {entry[key] for key in ("name", "model") if isinstance(entry.get(key), str)}
        names = {name for name in names if name.strip()}
        if not names:
            return None
        (remote if entry.get("remote_host") or entry.get("remote_model") else local).update(names)
    return local, remote


async def why_not_local(client: httpx.AsyncClient, tags_url: str, model: str) -> str | None:
    """Why ``model`` may not run on this computer, or ``None`` when it does.

    Fails closed: a model is local only when its tag is not a cloud tag and
    the daemon's own list was read, is well formed, and lists the model
    without marking it remote. Every caller refuses to send anything when
    this returns a reason.
    """
    if is_cloud_model(model):
        return f"{model} is an Ollama cloud model, which runs off this computer."
    listed = await model_list(client, tags_url)
    if listed is None:
        return f"Axcess could not confirm that {model} runs on this computer."
    local, remote = listed
    names = _names(model)
    if names & remote:
        return f"{model} is an Ollama cloud model, which runs off this computer."
    if not names & local:
        return f"Axcess could not confirm that {model} runs on this computer."
    return None


async def why_not_local_service(
    service: ModelClient, client: httpx.AsyncClient, model: str
) -> str | None:
    """:func:`why_not_local` for the service in use, or ``None``.

    Only Ollama has cloud models. A llama.cpp server runs the GGUF files it
    was started with, on the machine it runs on: the desktop app's private
    service is on this computer by construction, and a server's
    ``llama_cpp_url`` is the address an administrator chose.
    """
    if service.backend != "ollama":
        return None
    return await why_not_local(client, f"{service.base_url}/api/tags", model)


def prompt_content_version(prompt_text: str) -> str:
    """Short content hash used as a ``prompt_version`` tag.

    Same function the VLM module used to call ``prompt_version()``.
    Pulled here so semantic analyzers get the same versioning shape
    without re-importing from the VLM module.
    """
    return "v1-" + hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:12]


class OllamaBase:
    """Shared plumbing for any analyzer backed by the local model service.

    Subclasses build a :class:`GenerateRequest` and call :meth:`_generate`.
    Everything that can be shared is shared: semaphore, retry policy,
    timeout, healthy() probe.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
        base_url: str = "http://localhost:11434",
        concurrency: int = 1,
        max_attempts: int = 3,
        timeout_s: float = 120.0,
        backend: str = DEFAULT_BACKEND,
        retry_timeouts: bool = True,
    ) -> None:
        self._client = client
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._model_client: ModelClient = make_model_client(
            backend, client, base_url=self._base_url
        )
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._max_attempts = max_attempts
        self._timeout = timeout_s
        # False: a request that ran out of time is not sent again. At
        # temperature 0 the same prompt gives the same long answer, so a
        # retry only repeats the wait (the wording checks, 2026-11-19:
        # three 2-minute timeouts on one page). Connection errors and
        # busy answers are still retried.
        self._retry_timeouts = retry_timeouts
        # `model_version` is a plain attribute (not a property) because
        # the existing :class:`VlmProvider` protocol declares it as a
        # settable attribute. A read-only property here would break
        # LSP / structural-subtyping compatibility with that protocol.
        self.model_version = model

    @property
    def model(self) -> str:
        """The model name this provider was constructed with."""
        return self._model

    async def healthy(self, model: str | None = None) -> bool:
        """Return True if the model service is reachable and serves the model.

        ``model`` overrides the instance default, useful when one
        provider switches between models per call (the semantic runner
        may use ``qwen2.5:7b-instruct`` for most criteria but swap to
        the 14B for SC 2.5.3).
        """
        return await self._model_client.has_model(model or self._model, timeout_s=5.0)

    async def _generate(self, request: GenerateRequest) -> str:
        """Run ``request`` with the shared semaphore and retry policy."""
        return await self._post_with_retries(self._model_client.generate_body(request))

    async def _post_with_retries(self, payload: Mapping[str, Any]) -> str:
        """POST a backend request body, retrying on transient failures.

        ``payload`` is the selected backend's own JSON body (for Ollama,
        the ``/api/generate`` body), as built by :meth:`_generate`. It stays
        a separate step so tests can see exactly what goes on the wire.

        Returns the model's text as a string; subclasses decide whether
        to parse JSON or use the raw text. Raises :class:`OllamaError` on
        permanent failures (4xx that aren't 408/429, exhausted retries,
        malformed response envelope).
        """
        label = self._model_client.label
        model = str(payload.get("model") or self._model)
        backoff = 1.0
        last_error: Exception | None = None
        async with self._sem:
            for attempt in range(1, self._max_attempts + 1):
                # Checked right before each send, retries included, and after
                # waiting for the semaphore: a model can be replaced by a
                # cloud copy under the same name (``ollama cp``) at any time.
                # Reading the local list takes milliseconds; a model call
                # takes seconds.
                reason = await why_not_local_service(self._model_client, self._client, model)
                if reason is not None:
                    raise OllamaError(f"{reason} Choose a local model.")
                try:
                    return await self._model_client.send(payload, timeout_s=self._timeout)
                except ModelTimeoutError as exc:
                    log.warning("ollama.timeout", attempt=attempt, timeout_s=self._timeout)
                    if not self._retry_timeouts:
                        raise OllamaError(
                            f"{label} did not answer within {self._timeout:g} seconds"
                        ) from exc
                    last_error = exc
                except ModelTransportError as exc:
                    last_error = exc
                    log.warning("ollama.http_error", attempt=attempt, error=str(exc))
                except ModelStatusError as exc:
                    if not exc.transient:
                        raise OllamaError(
                            f"{label} returned HTTP {exc.status_code}: {exc.detail}"
                        ) from exc
                    last_error = OllamaError(f"HTTP {exc.status_code}")
                    log.warning(
                        "ollama.transient_status",
                        attempt=attempt,
                        status=exc.status_code,
                    )
                except ModelResponseError as exc:
                    raise OllamaError(str(exc)) from exc

                if attempt < self._max_attempts:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 10.0)
            raise OllamaError(f"exhausted retries: {last_error}")


__all__ = [
    "OllamaBase",
    "OllamaError",
    "prompt_content_version",
    "why_not_local",
    "why_not_local_service",
]
