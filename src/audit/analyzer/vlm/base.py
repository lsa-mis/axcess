"""VLM classification protocol and value types.

A :class:`VlmProvider` takes the image bytes plus a small :class:`ClassifyContext`
(alt text, caption, OCR output, surrounding snippet) and returns a
:class:`Classification` with a label, a short rationale, and version tags so
the :mod:`audit.db.repo` layer can record exactly what produced the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class VlmLabel(StrEnum):
    """Outcome of classification per prompt ``classify_v1``."""

    ESSENTIAL = "essential"
    """Image of text that conveys unique, load-bearing information."""

    INFORMATIONAL = "informational"
    """Image with text that meaningfully enriches the surrounding content."""

    LOGO = "logo"
    """Brand logo or wordmark."""

    DECORATIVE = "decorative"
    """Text is stylistic only — same info is available in the page text."""

    NO_MEANINGFUL_TEXT = "no_meaningful_text"
    """OCR false positive: no intentional text in the image."""


@dataclass(frozen=True)
class ClassifyContext:
    """Everything besides the bytes that the VLM needs in its prompt."""

    alt_text: str | None
    figcaption: str | None
    context_snippet: str | None
    ocr_text: str


@dataclass(frozen=True)
class Classification:
    """One VLM classification result."""

    label: VlmLabel
    rationale: str
    model_version: str
    """Identifier e.g. ``"qwen3-vl:2b-instruct"``; stored with the analysis."""
    prompt_version: str
    """Short content hash of the prompt template used."""


class VlmProvider(Protocol):
    """Async classifier interface implemented by the Ollama backend (and mocks)."""

    model_version: str
    prompt_version: str

    async def classify(
        self,
        image_bytes: bytes,
        mime: str,
        context: ClassifyContext,
    ) -> Classification: ...
