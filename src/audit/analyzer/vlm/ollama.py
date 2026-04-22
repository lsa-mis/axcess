"""Ollama-backed :class:`VlmProvider`.

Talks to a local Ollama daemon over HTTP (no official Python SDK required).
The prompt template is loaded once, content-hashed for the ``prompt_version``
tag, and filled with per-image context before each request. We request JSON
output from the model and parse the result into a :class:`Classification`.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from importlib import resources
from typing import Any

import httpx

from audit.analyzer.vlm.base import Classification, ClassifyContext, VlmLabel
from audit.logging import get_logger

log = get_logger(__name__)
_httpx_log = logging.getLogger("httpx")
_httpx_log.setLevel(logging.WARNING)  # /api/generate requests can be chatty at INFO

_PROMPT_PACKAGE = "audit.analyzer.vlm.prompts"
DEFAULT_PROMPT_NAME = "classify_v1.txt"


class VlmError(Exception):
    """Raised when the VLM cannot return a usable classification."""


def load_prompt(name: str = DEFAULT_PROMPT_NAME) -> str:
    """Read a prompt template from the packaged ``prompts/`` directory."""
    return (resources.files(_PROMPT_PACKAGE) / name).read_text(encoding="utf-8")


def prompt_version(prompt_text: str) -> str:
    """Short content hash used as the ``prompt_version`` tag."""
    return "v1-" + hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:12]


class OllamaProvider:
    """VLM classifier that dispatches to a local Ollama ``/api/generate`` endpoint."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
        base_url: str = "http://localhost:11434",
        prompt_name: str = DEFAULT_PROMPT_NAME,
        concurrency: int = 1,
        max_attempts: int = 3,
        timeout_s: float = 120.0,
    ) -> None:
        self._client = client
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._prompt_template = load_prompt(prompt_name)
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._max_attempts = max_attempts
        self._timeout = timeout_s
        self.model_version = model
        self.prompt_version = prompt_version(self._prompt_template)

    async def healthy(self) -> bool:
        """Return True if the Ollama daemon is reachable and knows the model."""
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
        return self._model in tags

    async def classify(
        self,
        image_bytes: bytes,
        mime: str,
        context: ClassifyContext,
    ) -> Classification:
        """Run one classification. Retries on transient HTTP errors with backoff."""
        _ = mime  # Ollama infers format from the base64 payload
        filled = self._prompt_template.format(
            alt=_for_prompt(context.alt_text),
            figcaption=_for_prompt(context.figcaption),
            snippet=_for_prompt(context.context_snippet),
            ocr=_for_prompt(context.ocr_text or None),
        )
        payload = {
            "model": self._model,
            "prompt": filled,
            "images": [base64.b64encode(image_bytes).decode("ascii")],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        raw = await self._post_with_retries(payload)
        label, rationale = _parse_model_output(raw)
        return Classification(
            label=label,
            rationale=rationale,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
        )

    async def _post_with_retries(self, payload: dict[str, Any]) -> str:
        """POST to ``/api/generate``, retrying on transient failures."""
        url = f"{self._base_url}/api/generate"
        backoff = 1.0
        last_error: Exception | None = None
        async with self._sem:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    resp = await self._client.post(url, json=payload, timeout=self._timeout)
                except httpx.HTTPError as exc:
                    last_error = exc
                    log.warning("vlm.http_error", attempt=attempt, error=str(exc))
                else:
                    if resp.status_code == 200:
                        try:
                            return str(resp.json().get("response", ""))
                        except json.JSONDecodeError as exc:
                            raise VlmError(f"non-JSON body from Ollama: {exc}") from exc
                    if resp.status_code in (408, 429) or resp.status_code >= 500:
                        last_error = VlmError(f"HTTP {resp.status_code}")
                        log.warning(
                            "vlm.transient_status",
                            attempt=attempt,
                            status=resp.status_code,
                        )
                    else:
                        raise VlmError(
                            f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}"
                        )

                if attempt < self._max_attempts:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 10.0)
            raise VlmError(f"exhausted retries: {last_error}")


def _for_prompt(value: str | None) -> str:
    """Format context fields for prompt interpolation."""
    if not value:
        return "(none)"
    collapsed = " ".join(value.split())
    return collapsed[:500]


def _parse_model_output(raw: str) -> tuple[VlmLabel, str]:
    """Parse the JSON body the model emitted. Raises :class:`VlmError` on bad output."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VlmError(f"model did not return valid JSON: {raw[:200]}") from exc
    if not isinstance(parsed, dict):
        raise VlmError(f"expected JSON object, got {type(parsed).__name__}")
    label_raw = parsed.get("label")
    if not isinstance(label_raw, str):
        raise VlmError(f"missing string 'label' in: {parsed}")
    try:
        label = VlmLabel(label_raw.strip().lower())
    except ValueError as exc:
        raise VlmError(f"unknown label: {label_raw!r}") from exc
    rationale_raw = parsed.get("rationale", "")
    rationale = rationale_raw.strip() if isinstance(rationale_raw, str) else ""
    return label, rationale[:500]
