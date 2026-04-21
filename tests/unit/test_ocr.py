"""Unit tests for the OCR layer.

The Tesseract path is exercised against real tesseract when the binary is
available; the pool and threshold logic are tested with in-memory generated
images to keep the suite hermetic.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from audit.analyzer.ocr.base import OcrResult
from audit.analyzer.ocr.pool import OcrPool
from audit.analyzer.ocr.tesseract import run_tesseract

_HAS_TESSERACT = shutil.which("tesseract") is not None
requires_tesseract = pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract binary not installed")


def _text_png(text: str, size: tuple[int, int] = (400, 120)) -> bytes:
    """Produce a PNG with the given text rendered large-ish for tesseract."""
    img = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(img)
    font = _pick_font(48)
    draw.text((20, 20), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pick_font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _blank_png(size: tuple[int, int] = (100, 100)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(180, 180, 180)).save(buf, format="PNG")
    return buf.getvalue()


def test_is_text_candidate_respects_both_thresholds() -> None:
    base = OcrResult(text="hi there", confidence=75.0, word_count=5, engine_version="v")
    assert base.is_text_candidate(min_confidence=60.0, min_word_count=3)
    # Below confidence cutoff.
    assert not base.is_text_candidate(min_confidence=80.0, min_word_count=3)
    # Below word-count cutoff.
    assert not base.is_text_candidate(min_confidence=60.0, min_word_count=10)


def test_is_text_candidate_treats_equal_threshold_as_inclusive() -> None:
    r = OcrResult(text="a b c", confidence=60.0, word_count=3, engine_version="v")
    assert r.is_text_candidate(min_confidence=60.0, min_word_count=3)


@requires_tesseract
def test_run_tesseract_detects_known_text() -> None:
    png = _text_png("BUY NOW TODAY")
    result = run_tesseract(png)
    assert result.word_count >= 2
    assert result.confidence > 40.0
    # Tesseract may vary in case/spelling; at least one expected token should land.
    lowered = result.text.lower()
    assert any(tok in lowered for tok in ("buy", "now", "today"))


@requires_tesseract
def test_run_tesseract_blank_image_returns_empty() -> None:
    result = run_tesseract(_blank_png())
    assert result.text == ""
    assert result.word_count == 0
    assert result.confidence == 0.0


@requires_tesseract
def test_run_tesseract_engine_version_identifies_lang() -> None:
    result = run_tesseract(_blank_png())
    assert result.engine_version.startswith("tesseract-")
    assert result.engine_version.endswith("-eng")


@requires_tesseract
@pytest.mark.asyncio
async def test_pool_in_process_mode_runs_ocr() -> None:
    async with OcrPool(in_process=True) as pool:
        result = await pool.run(_text_png("HELLO WORLD"))
    assert result.word_count >= 1


@requires_tesseract
@pytest.mark.asyncio
async def test_pool_process_mode_runs_ocr() -> None:
    async with OcrPool(max_workers=1) as pool:
        result = await pool.run(_text_png("HELLO WORLD"))
    assert result.word_count >= 1
