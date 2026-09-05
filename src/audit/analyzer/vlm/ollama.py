"""Ollama-backed :class:`VlmProvider` for the image-of-text pipeline.

Thin layer on top of :class:`~audit.analyzer.ollama_base.OllamaBase`.
This module owns *only* the image-specific bits: loading the
classify-prompt template, sending the base64-encoded image bytes,
and parsing the model's JSON response into a :class:`Classification`.

The shared HTTP plumbing (semaphore, retry, healthy() probe, timeouts)
lives in :mod:`audit.analyzer.ollama_base` so the semantic text
provider can share it without forking copy-pasted code.

Backward compatibility: ``OllamaProvider`` and ``VlmError`` are still
importable from this module verbatim, call sites in the orchestrator
and extractor.pipeline don't need to change.
"""

from __future__ import annotations

import base64
import json
from importlib import resources

import httpx

from audit.analyzer.ollama_base import (
    OllamaBase,
    OllamaError,
    prompt_content_version,
)
from audit.analyzer.vlm.base import Classification, ClassifyContext, VlmLabel

_PROMPT_PACKAGE = "audit.analyzer.vlm.prompts"
DEFAULT_PROMPT_NAME = "classify_v1.txt"


# Back-compat alias. Existing callers in extractor/pipeline.py and the
# integration tests import ``VlmError`` from here; we keep that name
# stable. New code should use ``OllamaError`` from ``ollama_base``.
VlmError = OllamaError


def load_prompt(name: str = DEFAULT_PROMPT_NAME) -> str:
    """Read a prompt template from the packaged ``prompts/`` directory."""
    return (resources.files(_PROMPT_PACKAGE) / name).read_text(encoding="utf-8")


def prompt_version(prompt_text: str) -> str:
    """Short content hash used as the ``prompt_version`` tag.

    Kept here for back-compat with callers that import this symbol.
    Delegates to the canonical implementation in :mod:`ollama_base`.
    """
    return prompt_content_version(prompt_text)


class OllamaProvider(OllamaBase):
    """VLM classifier that dispatches to a local Ollama ``/api/generate`` endpoint.

    Inherits the shared HTTP plumbing from :class:`OllamaBase`. The
    image-specific bits, prompt template loading, base64 image
    encoding, classification-response parsing, stay here.
    """

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
        super().__init__(
            client,
            model=model,
            base_url=base_url,
            concurrency=concurrency,
            max_attempts=max_attempts,
            timeout_s=timeout_s,
        )
        self._prompt_template = load_prompt(prompt_name)
        self.prompt_version = prompt_version(self._prompt_template)

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


__all__ = [
    "DEFAULT_PROMPT_NAME",
    "OllamaProvider",
    "VlmError",
    "load_prompt",
    "prompt_version",
]
