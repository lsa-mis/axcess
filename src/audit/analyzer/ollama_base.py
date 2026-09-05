"""Shared Ollama HTTP plumbing, the bit both VLM and text analyzers need.

Two analyzers talk to the same local Ollama daemon:

* :class:`~audit.analyzer.vlm.ollama.OllamaProvider`, the image-of-text
  classifier (VLM, the 1.4.5 pipeline). Already in production.
* :class:`~audit.analyzer.semantic.ollama_text.OllamaTextProvider`, the
  per-criterion text analyzer added in Phase 9. Generic
  ``generate(prompt) -> str``; the caller owns the prompt template.

Both want the same machinery: shared semaphore (so one global
``concurrency`` knob caps total in-flight calls to the daemon), retry
with exponential backoff on 408/429/5xx, a ``healthy()`` probe,
``temperature=0`` for determinism, and ``format=json`` for
structured-output reliability.

We factor that machinery here so neither subclass owns the HTTP
layer. Subclasses build their own payload shape on top.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

import httpx

from audit.logging import get_logger

log = get_logger(__name__)
_httpx_log = logging.getLogger("httpx")
_httpx_log.setLevel(logging.WARNING)  # /api/generate is chatty at INFO


class OllamaError(Exception):
    """Raised when the Ollama daemon cannot return a usable response.

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
    """Shared HTTP plumbing for any Ollama-backed analyzer.

    Subclasses build their own payload (image classify / text generate /
    embeddings / etc.) and call :meth:`_post_with_retries` to talk to
    ``/api/generate``. Everything that can be shared is shared:
    semaphore, retry policy, timeout, healthy() probe.
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
    ) -> None:
        self._client = client
        self._model = model
        self._base_url = base_url.rstrip("/")
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
        """The Ollama model tag this provider was constructed with."""
        return self._model

    async def healthy(self, model: str | None = None) -> bool:
        """Return True if the Ollama daemon is reachable and knows the model.

        ``model`` overrides the instance default, useful when one
        provider switches between models per call (the semantic runner
        may use ``qwen2.5:7b-instruct`` for most criteria but swap to
        the 14B for SC 2.5.3).
        """
        target = model or self._model
        try:
            resp = await self._client.get(f"{self._base_url}/api/tags", timeout=5.0)
        except httpx.HTTPError:
            return False
        if resp.status_code != 200:
            return False
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return False
        tags = {m.get("name") for m in data.get("models", [])}
        return target in tags

    async def _post_with_retries(self, payload: dict[str, Any]) -> str:
        """POST to ``/api/generate``, retrying on transient failures.

        Returns the model's ``response`` body field as a string —
        subclasses decide whether to parse JSON or use the raw text.
        Raises :class:`OllamaError` on permanent failures (4xx that
        aren't 408/429, exhausted retries, malformed Ollama envelope).
        """
        url = f"{self._base_url}/api/generate"
        backoff = 1.0
        last_error: Exception | None = None
        async with self._sem:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    resp = await self._client.post(url, json=payload, timeout=self._timeout)
                except httpx.HTTPError as exc:
                    last_error = exc
                    log.warning("ollama.http_error", attempt=attempt, error=str(exc))
                else:
                    if resp.status_code == 200:
                        try:
                            return str(resp.json().get("response", ""))
                        except json.JSONDecodeError as exc:
                            raise OllamaError(f"non-JSON envelope from Ollama: {exc}") from exc
                    if resp.status_code in (408, 429) or resp.status_code >= 500:
                        last_error = OllamaError(f"HTTP {resp.status_code}")
                        log.warning(
                            "ollama.transient_status",
                            attempt=attempt,
                            status=resp.status_code,
                        )
                    else:
                        raise OllamaError(
                            f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}"
                        )

                if attempt < self._max_attempts:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 10.0)
            raise OllamaError(f"exhausted retries: {last_error}")


__all__ = ["OllamaBase", "OllamaError", "prompt_content_version"]
