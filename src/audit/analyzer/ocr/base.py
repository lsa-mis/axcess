"""OCR result type shared by all backends."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OcrResult:
    """One OCR pass over an image blob."""

    text: str
    """Concatenated recognized text, single-spaced."""

    confidence: float
    """Mean per-word confidence, 0 to 100. ``0.0`` for no-text images."""

    word_count: int
    """Number of words with non-negative confidence."""

    engine_version: str
    """Identifier suitable for ``analyses.model_versions_json`` — e.g. ``"tesseract-5.5.2-eng"``."""

    def is_text_candidate(self, *, min_confidence: float, min_word_count: int) -> bool:
        """Apply the Phase 3 text-candidate gate."""
        return self.confidence >= min_confidence and self.word_count >= min_word_count
