"""Text-only Ollama client for per-criterion semantic analyzers.

Generic ``generate(prompt) -> str`` over a local Ollama daemon. The
shared HTTP plumbing — semaphore, retry, healthy() probe, timeouts —
lives in :class:`audit.analyzer.ollama_base.OllamaBase`; this class
adds only the text-payload shape and a parsed-JSON convenience.

Per-criterion analyzers own their prompts (one ``.txt`` template per
SC) and the parsing of the model's JSON response. Keeping the client
prompt-agnostic means a new SC analyzer is a prompt file + a parser
function, not a new HTTP client.

Model swapping: the constructor takes a *default* model, but
:meth:`generate` accepts a per-call ``model`` override. Useful for
the runner switching between ``qwen2.5:7b-instruct`` (most criteria)
and ``qwen2.5:14b-instruct`` (SC 2.5.3 reasoning) without spawning
two providers.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from audit.analyzer.ollama_base import OllamaBase, OllamaError


class OllamaTextProvider(OllamaBase):
    """Local Ollama text-completion client. JSON output by default.

    Defaults align with the GenA11y paper's findings: ``temperature=0``
    for determinism, ``format=json`` for reliable structured output
    (Ollama's ``format=json`` mode constrains decoding to valid JSON;
    a malformed payload from the model becomes the empty string
    instead of a parser-killing token salad).

    The caller passes the fully-rendered prompt — we do not interpolate
    anything here. The runner reads the per-criterion prompt template,
    fills it with the extracted elements, and hands the result to
    :meth:`generate`. That keeps this class one-job-only.
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
        keep_alive: str | int = -1,
    ) -> None:
        super().__init__(
            client,
            model=model,
            base_url=base_url,
            concurrency=concurrency,
            max_attempts=max_attempts,
            timeout_s=timeout_s,
        )
        # keep_alive=-1 -> model stays resident in Ollama between calls.
        # At 10k pages x 10 criteria, we'd otherwise pay the ~5s model
        # warm-up tax repeatedly. -1 means "keep loaded until the
        # daemon is asked to unload"; pass an integer (seconds) or
        # string ("5m") to override.
        self._keep_alive = keep_alive

    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        force_json: bool = True,
        temperature: float = 0.0,
    ) -> str:
        """Call ``/api/generate`` once. Returns the raw ``response`` field.

        ``model`` overrides the constructor default — useful for the
        runner switching models per criterion without spawning a
        second provider.

        ``force_json=True`` (the default) tells Ollama to constrain
        decoding to valid JSON. Set ``False`` only if the prompt
        intentionally elicits free-form text.

        Errors:
        * :class:`OllamaError` on HTTP failures, exhausted retries, or
          a malformed Ollama envelope. **Does NOT** raise on a model
          producing valid-JSON-but-wrong-schema output — the caller
          owns that parse step.
        """
        payload: dict[str, Any] = {
            "model": model or self._model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {"temperature": temperature},
        }
        if force_json:
            payload["format"] = "json"
        return await self._post_with_retries(payload)

    async def generate_json(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any] | list[Any]:
        """Call :meth:`generate` and parse the response as JSON.

        Raises :class:`OllamaError` if the response isn't valid JSON
        (shouldn't happen with ``format=json`` but the daemon can
        return an empty string on a model crash; we'd rather raise
        than return ``None``).
        """
        raw = await self.generate(prompt, model=model, temperature=temperature)
        if not raw.strip():
            raise OllamaError("model returned an empty response body")
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"model did not return valid JSON: {raw[:200]}") from exc
        if not isinstance(parsed, (dict, list)):
            raise OllamaError(f"expected JSON object or array, got {type(parsed).__name__}")
        return parsed


__all__ = ["OllamaTextProvider"]
