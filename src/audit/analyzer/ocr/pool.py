"""Async OCR dispatch on top of :class:`ProcessPoolExecutor`.

Tesseract is CPU-bound and releases the GIL poorly, so using a process pool
lets multiple images be OCR'd while the crawler's I/O continues. The pool
is optional: if ``max_workers <= 0`` or the caller passes ``in_process=True``,
we run synchronously on the event loop for deterministic tests.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from types import TracebackType
from typing import Self

from audit.analyzer.ocr.base import OcrResult
from audit.analyzer.ocr.tesseract import run_tesseract


class OcrPool:
    """Async-friendly wrapper around Tesseract OCR."""

    def __init__(
        self,
        *,
        lang: str = "eng",
        max_workers: int = 2,
        in_process: bool = False,
    ) -> None:
        self._lang = lang
        self._in_process = in_process or max_workers <= 0
        self._executor: ProcessPoolExecutor | None = None
        if not self._in_process:
            self._executor = ProcessPoolExecutor(max_workers=max_workers)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None

    async def run(self, image_bytes: bytes) -> OcrResult:
        """Run OCR on ``image_bytes``. Raises on worker crash or unreadable image."""
        if self._executor is None:
            # In-process path — keeps tests hermetic.
            return run_tesseract(image_bytes, self._lang)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, run_tesseract, image_bytes, self._lang)
