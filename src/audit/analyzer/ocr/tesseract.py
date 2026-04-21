"""Tesseract-backed OCR.

The :func:`run_tesseract` function is deliberately a module-level function (not
a method) so that it is picklable and can be dispatched to a ``ProcessPoolExecutor``
worker. Version detection happens lazily on first call.
"""

from __future__ import annotations

import functools
import io

import pytesseract
from PIL import Image

from audit.analyzer.ocr.base import OcrResult


@functools.lru_cache(maxsize=1)
def _tesseract_version() -> str:
    """Return the installed tesseract version string (cached per process)."""
    try:
        return str(pytesseract.get_tesseract_version())
    except pytesseract.TesseractNotFoundError:
        return "unknown"


def engine_version(lang: str) -> str:
    """Identifier used as part of ``analyses.model_versions_json``."""
    return f"tesseract-{_tesseract_version()}-{lang}"


def run_tesseract(image_bytes: bytes, lang: str = "eng") -> OcrResult:
    """Run Tesseract over ``image_bytes`` and return an aggregated :class:`OcrResult`.

    Uses ``image_to_data`` to get per-word confidences so we can compute a
    meaningful mean; the plain ``image_to_string`` only gives text.
    """
    with Image.open(io.BytesIO(image_bytes)) as opened:
        # Tesseract handles a lot of formats but converting to RGB up front
        # keeps us away from mode-specific surprises (palette GIFs, CMYK JPEGs).
        working = opened if opened.mode in ("RGB", "L") else opened.convert("RGB")
        data = pytesseract.image_to_data(
            working,
            lang=lang,
            output_type=pytesseract.Output.DICT,
        )

    words: list[tuple[str, float]] = []
    for raw_text, raw_conf in zip(data.get("text", []), data.get("conf", []), strict=False):
        text = (raw_text or "").strip()
        if not text:
            continue
        try:
            conf = float(raw_conf)
        except (TypeError, ValueError):
            continue
        if conf < 0:
            # Tesseract marks non-word layout blocks with conf=-1.
            continue
        words.append((text, conf))

    if not words:
        return OcrResult(
            text="",
            confidence=0.0,
            word_count=0,
            engine_version=engine_version(lang),
        )

    joined = " ".join(w for w, _ in words)
    mean_conf = sum(c for _, c in words) / len(words)
    return OcrResult(
        text=joined,
        confidence=round(mean_conf, 2),
        word_count=len(words),
        engine_version=engine_version(lang),
    )
