"""Ask the local model to judge one image's alt text and suggest better text.

Used only by the report's Images tab, when a person asks for one image
(``POST /api/scans/{id}/images/{image_id}/alt-check``). It is not part of a
scan: the scan's own classifier is :mod:`audit.analyzer.vlm.ollama`, and its
model setting (``vlm_model``) is separate from this one
(``alt_check_model``), so changing the model here cannot change how a
completed scan was analysed.

The page's alt text, OCR text and nearby text come from a crawled site and
may hold prompt-injection text. The prompt puts them between ``<data>``
tags and tells the model to treat them as data; the answer is parsed as
strict JSON and every field is bounded, so a model that is led astray can
at worst return a poor suggestion, which the interface labels as needing a
person's check.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from audit.analyzer.ollama_base import OllamaBase, OllamaError, prompt_content_version
from audit.analyzer.vlm.ollama import load_prompt

DEFAULT_PROMPT_NAME = "alt_check_v1.txt"
SUGGESTION_LIMIT = 250
REASON_LIMIT = 300
_FIELD_LIMIT = 500

CheckVerdict = Literal["good", "needs_better"]


def is_cloud_model(name: str) -> bool:
    """True for an Ollama cloud model, such as ``gpt-oss:120b-cloud``.

    Ollama runs these on its own servers even when asked through the local
    daemon, so the image and page text would leave the computer. Ollama marks
    them with a tag that is ``cloud`` or ends in ``-cloud``.
    """
    _, _, tag = name.strip().lower().rpartition(":")
    return tag == "cloud" or tag.endswith("-cloud")


@dataclass(frozen=True)
class AltCheckInput:
    """What the model is told about the image besides its pixels."""

    alt_text: str | None
    image_text: str
    context_snippet: str | None


@dataclass(frozen=True)
class AltCheckResult:
    """The model's answer, bounded and checked."""

    verdict: CheckVerdict | None
    reason: str
    suggestion: str
    model: str
    prompt_version: str


class AltChecker(Protocol):
    """Anything that can check one image; tests pass a stub."""

    model: str
    prompt_version: str

    async def check(self, image_bytes: bytes, given: AltCheckInput) -> AltCheckResult: ...


class OllamaAltChecker(OllamaBase):
    """Alt text check through the local Ollama daemon."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout_s: float = 90.0,
    ) -> None:
        # One attempt: a person is waiting on the button, and the endpoint
        # has its own deadline.
        super().__init__(
            client, model=model, base_url=base_url, max_attempts=1, timeout_s=timeout_s
        )
        self._prompt_template = load_prompt(DEFAULT_PROMPT_NAME)
        self.prompt_version = prompt_content_version(self._prompt_template)

    async def check(self, image_bytes: bytes, given: AltCheckInput) -> AltCheckResult:
        if given.alt_text is None:
            alt = "(no alt attribute)"
        elif not given.alt_text.strip():
            alt = '(empty: alt="", marked decorative)'
        else:
            alt = _field(given.alt_text)
        filled = self._prompt_template.format(
            alt=alt,
            ocr=_field(given.image_text) or "(none)",
            snippet=_field(given.context_snippet) or "(none)",
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
        has_alt = bool(given.alt_text and given.alt_text.strip())
        return parse_answer(
            raw, has_alt=has_alt, model=self._model, prompt_version=self.prompt_version
        )


def _field(value: str | None) -> str:
    """One line, bounded, with the delimiter tags taken out."""
    if not value:
        return ""
    collapsed = " ".join(value.split())
    collapsed = collapsed.replace("<data>", "").replace("</data>", "")
    return collapsed[:_FIELD_LIMIT]


def _clean(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def parse_answer(raw: str, *, has_alt: bool, model: str, prompt_version: str) -> AltCheckResult:
    """Parse the model's JSON. Raises :class:`OllamaError` when it is unusable."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OllamaError("the model did not return valid JSON") from exc
    if not isinstance(parsed, dict):
        raise OllamaError("the model did not return a JSON object")
    suggestion = _clean(parsed.get("suggestion"), SUGGESTION_LIMIT)
    if not suggestion:
        raise OllamaError("the model returned no suggestion")
    verdict_raw = parsed.get("verdict")
    verdict: CheckVerdict | None = None
    if has_alt:
        if verdict_raw not in ("good", "needs_better"):
            raise OllamaError("the model returned no verdict for the alt text")
        verdict = verdict_raw
    return AltCheckResult(
        verdict=verdict,
        reason=_clean(parsed.get("reason"), REASON_LIMIT),
        suggestion=suggestion,
        model=model,
        prompt_version=prompt_version,
    )


__all__ = [
    "AltCheckInput",
    "AltCheckResult",
    "AltChecker",
    "OllamaAltChecker",
    "OllamaError",
    "parse_answer",
]
