"""Ask the local Ollama model for a fix and check its answer is safe to show.

This talks to Ollama directly rather than through
:class:`audit.analyzer.ollama_base.OllamaBase`: that class folds every
failure into one ``OllamaError`` string, and the person asking needs to be
told which of "Ollama is not running", "the model is not installed" and
"it took too long" happened, because each has a different fix.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from audit.analyzer.ollama_base import prompt_content_version
from audit.suggest.context import EvidenceBundle
from audit.suggest.models import ErrorCode, ModelAnswer

ANSWER_SCHEMA: dict[str, Any] = ModelAnswer.model_json_schema()
KEEP_ALIVE = "10m"
CONTEXT_TOKENS = 8192
MAX_ANSWER_TOKENS = 1536
PROMPT_PATH = Path(__file__).parent / "prompts" / "suggest_fix_v1.txt"
_EVIDENCE_OPEN = "<<<EVIDENCE"
_EVIDENCE_CLOSE = "EVIDENCE>>>"

# Markup the interface must never show as a suggestion. It is displayed as
# escaped text, never run, but a person may paste it into their site.
_UNSAFE_MARKUP = re.compile(
    r"<\s*(script|iframe|object|embed)\b|\bon[a-z]+\s*=|javascript\s*:|<\s*meta\b[^>]*http-equiv",
    re.IGNORECASE,
)


class SuggestionError(Exception):
    def __init__(self, code: ErrorCode, detail: str | None = None) -> None:
        super().__init__(detail or code)
        self.code: ErrorCode = code
        self.detail = detail


@lru_cache(maxsize=1)
def prompt_text() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def prompt_version() -> str:
    return prompt_content_version(prompt_text())


def _neutralise(text: str) -> str:
    # Scanned content cannot close the evidence block early.
    return text.replace(_EVIDENCE_CLOSE, "EVIDENCE>>]").replace(_EVIDENCE_OPEN, "<<[EVIDENCE")


def build_prompt(bundle: EvidenceBundle, *, with_image: bool = True) -> str:
    lines = [
        prompt_text().strip(),
        "",
        "The problem Axcess found (trusted, from Axcess):",
        f"- Issue: {bundle.issue_title}",
        f"- WCAG success criterion: {bundle.wcag_sc or 'not mapped'}",
        f"- Check that found it: {bundle.pipeline} ({bundle.rule_id})",
    ]
    if bundle.fix_steps:
        lines.append("- Axcess's general fix steps for this issue:")
        lines.extend(f"  * {step}" for step in bundle.fix_steps)
    if with_image and bundle.image_bytes is not None:
        lines.append("- An image is attached: the element or image as the scan saw it.")
    evidence: list[str] = [f"Page address: {bundle.page_url}", f"What failed: {bundle.problem}"]
    if bundle.selector:
        evidence.append(f"Element locator (CSS selector): {bundle.selector}")
    if bundle.snippet:
        evidence.append(f"Element markup:\n{bundle.snippet}")
    for label, value in bundle.image_facts.items():
        evidence.append(f"{label}: {value}")
    if bundle.nearby_text:
        evidence.append(f"Text near the element: {bundle.nearby_text}")
    lines += ["", _EVIDENCE_OPEN, _neutralise("\n".join(evidence)), _EVIDENCE_CLOSE, ""]
    lines.append("Reply with the JSON object only.")
    return "\n".join(lines)


def unsafe_fields(answer: ModelAnswer) -> list[str]:
    fields = {
        "developer.after_html": answer.developer.after_html or "",
        "developer.css": answer.developer.css or "",
    }
    for i, item in enumerate(answer.editor.paste_text):
        fields[f"editor.paste_text[{i}]"] = item.value
    return [name for name, value in fields.items() if _UNSAFE_MARKUP.search(value)]


def parse_answer(raw: str) -> ModelAnswer:
    try:
        answer = ModelAnswer.model_validate_json(raw)
    except ValidationError as exc:
        raise SuggestionError(
            "bad_answer", f"The answer was not in the expected shape: {exc.error_count()} problems."
        ) from exc
    bad = unsafe_fields(answer)
    if bad:
        raise SuggestionError(
            "bad_answer", "The answer contained code that could run: " + ", ".join(bad)
        )
    return answer


@dataclass(frozen=True)
class ModelChoice:
    model: str
    uses_vision: bool


def choose_model(bundle: EvidenceBundle, *, text_model: str, vision_model: str) -> ModelChoice:
    if bundle.image_bytes is not None:
        return ModelChoice(vision_model, True)
    return ModelChoice(text_model, False)


class Provider(Protocol):
    async def generate(self, prompt: str, *, model: str, image: bytes | None) -> str: ...

    async def installed_models(self) -> set[str]: ...


class OllamaSuggestionProvider:
    def __init__(self, client: httpx.AsyncClient, *, base_url: str, timeout_s: float) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s

    async def installed_models(self) -> set[str]:
        try:
            resp = await self._client.get(f"{self._base_url}/api/tags", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise SuggestionError("model_unavailable", str(exc)[:200]) from exc
        return {str(m.get("name")) for m in data.get("models", []) if m.get("name")}

    async def generate(self, prompt: str, *, model: str, image: bytes | None) -> str:
        payload: dict[str, object] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            # Ollama constrains the output to this schema (structured
            # outputs), so the answer cannot drift from the shape Axcess
            # checks. With "json" alone the model sometimes wrote
            # ``"paste_text": null`` and the suggestion failed.
            "format": ANSWER_SCHEMA,
            # Stays loaded between clicks, then frees the memory.
            "keep_alive": KEEP_ALIVE,
            "options": {
                "temperature": 0,
                # Room for the largest evidence bundle plus the answer, so a
                # long prompt is never cut off silently.
                "num_ctx": CONTEXT_TOKENS,
                # Caps the time a runaway answer can take.
                "num_predict": MAX_ANSWER_TOKENS,
            },
        }
        if image is not None:
            payload["images"] = [base64.b64encode(image).decode("ascii")]
        try:
            resp = await self._client.post(
                f"{self._base_url}/api/generate", json=payload, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise SuggestionError("timeout") from exc
        except httpx.HTTPError as exc:
            raise SuggestionError("model_unavailable", str(exc)[:200]) from exc
        if resp.status_code == 404:
            raise SuggestionError("model_missing", model)
        if resp.status_code != 200:
            raise SuggestionError("model_unavailable", f"HTTP {resp.status_code}")
        try:
            return str(resp.json().get("response", ""))
        except json.JSONDecodeError as exc:
            raise SuggestionError("bad_answer", "Ollama did not return JSON.") from exc
