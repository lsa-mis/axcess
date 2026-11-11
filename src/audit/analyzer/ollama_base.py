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
        backoff = 1.0
        last_error: Exception | None = None
        async with self._sem:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    return await self._model_client.send(payload, timeout_s=self._timeout)
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


__all__ = ["OllamaBase", "OllamaError", "prompt_content_version"]
