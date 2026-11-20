"""General vision→JSON provider for the visual analyzers.

Distinct from :class:`audit.analyzer.vlm.ollama.OllamaProvider`, which is
tied to the image-of-text *classify* prompt and the ``Classification``
return shape. The visual analyzers (SC 1.3.2 Meaningful Sequence, SC 2.2.2
Pause/Stop/Hide) hand this provider a page **screenshot** plus a
per-criterion prompt and get back the model's raw JSON object to interpret
themselves.

Reuses the shared HTTP plumbing (semaphore, retry, ``healthy()`` probe,
timeouts) from :class:`~audit.analyzer.ollama_base.OllamaBase`.
"""

from __future__ import annotations

import json
from typing import Any

from audit.ai.model_client import GenerateRequest
from audit.analyzer.ollama_base import OllamaBase, OllamaError

__all__ = ["OllamaVisionProvider"]


class OllamaVisionProvider(OllamaBase):
    """Send a screenshot + prompt to a local vision model → JSON dict."""

    async def describe_json(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        mime: str = "image/png",
    ) -> dict[str, Any]:
        """Run one vision query. Returns the parsed JSON object the model
        emitted. Raises :class:`OllamaError` on transport failure or if the
        model returns non-JSON / a non-object.
        """
        raw = await self._generate(
            GenerateRequest(
                model=self._model,
                prompt=prompt,
                image=image_bytes,
                # Ollama infers the format from the bytes; llama.cpp gets a
                # data: URL.
                image_mime=mime,
                json_mode=True,
                temperature=0.0,
            )
        )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"vision model did not return valid JSON: {raw[:200]}") from exc
        if not isinstance(parsed, dict):
            raise OllamaError(f"expected a JSON object, got {type(parsed).__name__}")
        return parsed
