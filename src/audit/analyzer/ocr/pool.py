"""Async OCR dispatch on top of :class:`ProcessPoolExecutor`.

Tesseract is CPU-bound and releases the GIL poorly, so using a process pool
lets multiple images be OCR'd while the crawler's I/O continues. The pool
is optional: if ``max_workers <= 0`` or the caller passes ``in_process=True``,
we run synchronously on the event loop for deterministic tests.

Two rules keep one image from stopping a scan:

* **Fresh helper processes ("spawn") on every platform.** Python 3.11's
  default on Linux copies the running server ("fork"), and a copy inherits
  every lock as it was, with only the copying thread to release them. The
  desktop server's parent watch (``desktop_server.exit_when_input_closes``)
  keeps a thread blocked reading standard input, which holds that stream's
  lock; a forked helper starts by closing its standard input
  (``multiprocessing``'s bootstrap), waits for the lock, and sleeps forever.
  Report 77 (2026-11-24) stalled that way twice on Linux, and the same scan
  hung again when the server was started with ``--exit-with-parent`` and
  finished without it. Windows and macOS already spawn, so this makes Linux
  behave like them, and no other lock a thread holds can do the same. The
  packaged app calls ``freeze_support`` (``desktop/backend_entry.py``) and
  the servers guard ``__main__``, which spawned helpers need.
* **A time limit per image.** The limit counts only the time a helper works
  on the image, not the wait for a free helper (``_slots``), so a page with
  many images does not time out its last ones. A helper past the limit is
  stopped and the pool replaced, so the next image gets a working one; the
  caller logs the image as not read, with the reason.
"""

from __future__ import annotations

import asyncio
import contextlib
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from types import TracebackType
from typing import Self

from audit.analyzer.ocr.base import OcrResult
from audit.analyzer.ocr.tesseract import run_tesseract
from audit.logging import get_logger

log = get_logger(__name__)

#: Seconds a helper may spend on one image. Tesseract reads a typical web
#: image in well under a second; the first image also pays for starting a
#: fresh helper (a few seconds while it imports Axcess).
DEFAULT_TIMEOUT_S = 60.0

#: Seconds to wait for a helper to finish when the pool closes, before it is
#: stopped. A helper that is stuck would otherwise keep the scan from ending.
_CLOSE_WAIT_S = 5.0


class OcrTimeoutError(RuntimeError):
    """A helper took longer than the time limit to read one image."""


class OcrPool:
    """Async-friendly wrapper around Tesseract OCR."""

    def __init__(
        self,
        *,
        lang: str = "eng",
        max_workers: int = 2,
        in_process: bool = False,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._lang = lang
        self._in_process = in_process or max_workers <= 0
        self._max_workers = max(1, max_workers)
        self._timeout_s = timeout_s
        self._slots = asyncio.Semaphore(self._max_workers)
        self._executor: ProcessPoolExecutor | None = None
        if not self._in_process:
            self._executor = self._new_executor()

    def _new_executor(self) -> ProcessPoolExecutor:
        return ProcessPoolExecutor(
            max_workers=self._max_workers,
            mp_context=multiprocessing.get_context("spawn"),
        )

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
            _close(self._executor, wait_s=_CLOSE_WAIT_S)
            self._executor = None

    async def run(self, image_bytes: bytes) -> OcrResult:
        """Run OCR on ``image_bytes``.

        Raises :class:`OcrTimeoutError` past the time limit, and the pool's
        own error on a helper crash or an unreadable image.
        """
        if self._executor is None:
            # In-process path, keeps tests hermetic.
            return run_tesseract(image_bytes, self._lang)
        async with self._slots:
            executor = self._executor
            if executor is None:  # closed while this image waited
                raise RuntimeError("The text-reading helpers were closed.")
            future = executor.submit(run_tesseract, image_bytes, self._lang)
            try:
                return await asyncio.wait_for(asyncio.wrap_future(future), self._timeout_s)
            except TimeoutError as exc:
                self._replace(executor)
                raise OcrTimeoutError(
                    f"Reading text took longer than {self._timeout_s:.0f} seconds, so "
                    "Axcess stopped the helper and skipped this image."
                ) from exc

    def _replace(self, stuck: ProcessPoolExecutor) -> None:
        """Stop a pool with a stuck helper and start a fresh one."""
        if self._executor is not stuck:
            return  # another image already replaced it
        log.warning("ocr.helper_restarted", timeout_s=self._timeout_s)
        self._executor = self._new_executor()
        _close(stuck, wait_s=0.0)


def _close(executor: ProcessPoolExecutor, *, wait_s: float) -> None:
    """Close ``executor`` without waiting forever on a stuck helper.

    ``shutdown(wait=True)`` waits for every helper to exit, so one stuck
    helper would hang the scan's end. Instead: stop new work, give each
    helper ``wait_s`` seconds, and stop the ones still running.
    """
    # The executor does not expose its processes; read them before shutdown
    # clears the table.
    processes = list((getattr(executor, "_processes", None) or {}).values())
    executor.shutdown(wait=False, cancel_futures=True)
    for process in processes:
        with contextlib.suppress(Exception):
            process.join(wait_s)
            if process.is_alive():
                process.kill()
                process.join(1.0)
