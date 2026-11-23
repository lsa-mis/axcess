"""Alfa on the crawler's own tab: snapshots in the page, rules in one worker.

Before this module, Alfa opened its own browser for every page and checked
the page as it loaded. It could not see the page states Click-Through opens,
because those states exist only in the crawler's tab, and it saw a different
copy of the page from axe's.

Now Alfa works like axe:

1. :meth:`AlfaWorker.snapshot` runs Alfa's own serializer inside a page or
   frame the crawler already has open (at load, and in each state a click
   opens). That takes about 0.6 s and returns one JSON string.
2. :meth:`AlfaWorker.evaluate` sends the snapshot to one Node process that
   runs for the whole scan (``alfa_runner/worker.mjs``) and returns an
   :class:`~audit.analyzer.alfa.AlfaResult`. The rules take about 1.5 s per
   snapshot, so callers start evaluation as a task and let the tab move on.

Every limit here is explicit: snapshot size, how many snapshots may wait,
the time per snapshot, and how often the worker may be restarted. Each
failure is an :class:`~audit.analyzer.alfa.AlfaError` with a reason a
person can read, never a silent empty result.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from audit.analyzer.alfa import (
    _RUNNER_DIR,
    AlfaError,
    AlfaResult,
    _node_executable,
    _parse_payload,
    availability,
    runner_environment,
)
from audit.logging import get_logger
from audit.wcag_version import LEGACY_WCAG_VERSION, is_wcag_version

log = get_logger(__name__)

_WORKER_PATH = _RUNNER_DIR / "worker.mjs"
# A real content page's snapshot measured 0.98 MB (a11yproject.com's
# checklist, 2026-11-23). Large application pages run several times that.
MAX_SNAPSHOT_BYTES = 8_000_000
# A result is at most 200 bounded findings (evidence.mjs).
_MAX_RESPONSE_BYTES = 4_000_000
_HANDSHAKE_TIMEOUT_S = 30.0
_SNAPSHOT_TIMEOUT_S = 20.0
DEFAULT_EVALUATE_TIMEOUT_S = 75.0
# Snapshots waiting for the worker. Each is held in memory (about 1 MB), so
# the queue is bounded; a caller waits for room rather than being dropped.
DEFAULT_MAX_PENDING = 24
# After this many unexpected exits the worker is not started again in this
# scan, and every later snapshot fails with the reason.
MAX_RESTARTS = 3


class Snapshottable(Protocol):
    """A Playwright ``Page`` or ``Frame``: anything that can run a script."""

    async def evaluate(self, expression: str, arg: Any = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class AlfaSnapshot:
    """One page state as Alfa's serializer saw it, as a JSON string."""

    url: str
    payload: str


class AlfaWorker:
    """One Node process for the whole scan, checking snapshots in order.

    Safe to share between crawler workers: requests are written and answered
    one at a time. Start it with :meth:`start` (or let the first call do it)
    and end it with :meth:`close`.
    """

    def __init__(
        self,
        *,
        evaluate_timeout_s: float = DEFAULT_EVALUATE_TIMEOUT_S,
        max_pending: int = DEFAULT_MAX_PENDING,
        chromium_path: str | None = None,
    ) -> None:
        self._evaluate_timeout_s = evaluate_timeout_s
        self._pending = asyncio.Semaphore(max(1, max_pending))
        self._turn = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._env = runner_environment(chromium_path=chromium_path)
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail = bytearray()
        self._snapshot_script: str | None = None
        self._next_id = 0
        self._restarts = 0
        self._gave_up: str | None = None
        self._closed = False

    @property
    def snapshot_script(self) -> str | None:
        return self._snapshot_script

    async def start(self) -> None:
        """Start the worker and read its handshake, once."""
        async with self._start_lock:
            if self._closed:
                raise AlfaError("Alfa was already stopped for this scan.")
            if self._process is not None and self._process.returncode is None:
                return
            if self._gave_up:
                raise AlfaError(self._gave_up)
            if self._process is not None:
                # It was running and exited: count it.
                self._restarts += 1
                if self._restarts > MAX_RESTARTS:
                    self._gave_up = (
                        f"The Alfa worker stopped unexpectedly {self._restarts} times, so "
                        "Alfa was not started again for the rest of this scan. "
                        f"Last error output: {self._stderr_text() or 'none'}"
                    )
                    log.warning("alfa.worker_gave_up", restarts=self._restarts)
                    raise AlfaError(self._gave_up)
                log.warning(
                    "alfa.worker_restart",
                    restarts=self._restarts,
                    exit_code=self._process.returncode,
                    stderr=self._stderr_text(),
                )
            await self._spawn()

    async def _spawn(self) -> None:
        state = availability()
        if not state.available:
            raise AlfaError(state.reason or "Alfa is unavailable.")
        if not _WORKER_PATH.is_file():
            raise AlfaError("The bundled Alfa worker (worker.mjs) is missing.")
        node = _node_executable()
        if node is None:
            raise AlfaError("Node.js 22 or later is not available.")
        try:
            process = await asyncio.create_subprocess_exec(
                node,
                str(_WORKER_PATH),
                cwd=str(_RUNNER_DIR),
                env=self._env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=max(MAX_SNAPSHOT_BYTES, _MAX_RESPONSE_BYTES) + 1024,
            )
        except OSError as exc:
            raise AlfaError(f"Could not start the Alfa worker: {exc}") from exc
        self._process = process
        self._stderr_tail.clear()
        self._stderr_task = asyncio.create_task(self._drain_stderr(process))
        try:
            line = await asyncio.wait_for(self._readline(process), _HANDSHAKE_TIMEOUT_S)
        except (TimeoutError, AlfaError) as exc:
            await self._kill()
            raise AlfaError(
                "The Alfa worker did not start within "
                f"{_HANDSHAKE_TIMEOUT_S:.0f} seconds. Error output: {self._stderr_text() or 'none'}"
            ) from exc
        try:
            hello = json.loads(line)
        except json.JSONDecodeError as exc:
            await self._kill()
            raise AlfaError("The Alfa worker's first message was not JSON.") from exc
        script = hello.get("snapshot_script") if isinstance(hello, dict) else None
        if not (hello.get("ready") is True and hello.get("protocol_version") == 1 and script):
            await self._kill()
            raise AlfaError("The Alfa worker spoke an unexpected protocol.")
        self._snapshot_script = str(script)
        log.info("alfa.worker_started", pid=process.pid, restarts=self._restarts)

    async def snapshot(self, target: Snapshottable) -> AlfaSnapshot:
        """Take Alfa's snapshot of ``target`` (a page or frame) as it is now."""
        await self.start()
        script = self._snapshot_script
        if script is None:  # pragma: no cover - start() sets it or raises
            raise AlfaError("The Alfa worker did not send its snapshot script.")
        started = time.perf_counter()
        try:
            text = await asyncio.wait_for(target.evaluate(script), _SNAPSHOT_TIMEOUT_S)
        except TimeoutError as exc:
            raise AlfaError(
                "Taking Alfa's snapshot of the page took longer than "
                f"{_SNAPSHOT_TIMEOUT_S:.0f} seconds."
            ) from exc
        except Exception as exc:
            # A Playwright error: the page navigated or closed mid-snapshot.
            raise AlfaError(
                f"Alfa's snapshot script failed in the page ({type(exc).__name__})."
            ) from exc
        if not isinstance(text, str):
            raise AlfaError("Alfa's snapshot script returned no snapshot.")
        size = len(text.encode("utf-8"))
        if size > MAX_SNAPSHOT_BYTES:
            raise AlfaError(
                f"The page is too large for Alfa: its snapshot is {size / 1e6:.1f} MB, "
                f"over the {MAX_SNAPSHOT_BYTES / 1e6:.0f} MB limit."
            )
        # The string comes from the page, which can replace JSON.stringify.
        # Parse it here so it is exactly one JSON object: anything else (a
        # second line smuggled into the worker's input, a truncated value)
        # is refused before it reaches the worker.
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AlfaError("Alfa's snapshot of the page was not valid JSON.") from exc
        if not (
            isinstance(decoded, dict)
            and isinstance(decoded.get("node"), dict)
            and isinstance(decoded.get("device"), dict)
        ):
            raise AlfaError("Alfa's snapshot of the page had an unexpected shape.")
        if "\n" in text or "\r" in text:
            # json.loads accepts raw newlines as whitespace between tokens;
            # the worker reads one line per request.
            text = json.dumps(decoded, separators=(",", ":"))
        log.debug("alfa.snapshot", bytes=size, ms=int((time.perf_counter() - started) * 1000))
        return AlfaSnapshot(url=str(getattr(target, "url", "") or ""), payload=text)

    async def submit(
        self,
        target: Snapshottable,
        *,
        level: str,
        version: str = LEGACY_WCAG_VERSION,
    ) -> asyncio.Task[AlfaResult]:
        """Snapshot ``target`` now and check it in the background.

        Returns once the snapshot is taken, so the tab can move on (the next
        click) while the rules run. Waits first when ``max_pending``
        snapshots are already held, which bounds memory and slows the tab
        rather than dropping a page state unchecked. Await the returned task
        for the result or the :class:`AlfaError` that explains why there is
        none.
        """
        await self._pending.acquire()
        try:
            snap = await self.snapshot(target)
        except BaseException:
            self._pending.release()
            raise

        async def check() -> AlfaResult:
            try:
                return await self.evaluate(snap, level=level, version=version)
            finally:
                self._pending.release()

        return asyncio.create_task(check())

    async def evaluate(
        self,
        snapshot: AlfaSnapshot,
        *,
        level: str,
        version: str = LEGACY_WCAG_VERSION,
    ) -> AlfaResult:
        """Check one snapshot with the Alfa rules for ``level`` and ``version``."""
        if level not in {"A", "AA", "AAA"}:
            raise AlfaError(f"Unsupported Alfa WCAG level: {level}")
        if not is_wcag_version(version):
            raise AlfaError(f"Unsupported Alfa WCAG version: {version}")
        async with self._turn:
            await self.start()
            process = self._process
            if process is None or process.stdin is None:  # pragma: no cover
                raise AlfaError("The Alfa worker is not running.")
            self._next_id += 1
            request_id = self._next_id
            head = json.dumps(
                {"id": request_id, "level": level, "version": version},
                separators=(",", ":"),
            )
            request = f'{head[:-1]},"snapshot":{snapshot.payload}}}\n'.encode()
            try:
                process.stdin.write(request)
                await process.stdin.drain()
                line = await asyncio.wait_for(self._readline(process), self._evaluate_timeout_s)
            except TimeoutError as exc:
                # The worker is stuck in this snapshot; stop it so the
                # next snapshot gets a fresh one.
                await self._kill()
                raise AlfaError(
                    f"Alfa took longer than {self._evaluate_timeout_s:.0f} seconds "
                    "to check this page state."
                ) from exc
            except (BrokenPipeError, ConnectionResetError) as exc:
                raise AlfaError(
                    "The Alfa worker stopped while checking a page state. "
                    f"Error output: {self._stderr_text() or 'none'}"
                ) from exc
        return _parse_response(line, request_id)

    async def close(self) -> None:
        """End the worker; safe to call more than once."""
        self._closed = True
        process = self._process
        if process is None:
            return
        if process.stdin is not None:
            with contextlib.suppress(Exception):
                process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 5.0)
        except TimeoutError:
            await self._kill()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with contextlib.suppress(BaseException):
                await self._stderr_task

    async def _readline(self, process: asyncio.subprocess.Process) -> bytes:
        if process.stdout is None:  # pragma: no cover
            raise AlfaError("The Alfa worker has no output pipe.")
        try:
            line = await process.stdout.readline()
        except (ValueError, asyncio.LimitOverrunError) as exc:
            await self._kill()
            raise AlfaError(
                "Alfa returned more output for one page state than Axcess can keep."
            ) from exc
        if not line:
            await asyncio.sleep(0)  # let the stderr drain catch the reason
            raise AlfaError(
                "The Alfa worker stopped unexpectedly. "
                f"Error output: {self._stderr_text() or 'none'}"
            )
        return line

    async def _drain_stderr(self, process: asyncio.subprocess.Process) -> None:
        if process.stderr is None:
            return
        while chunk := await process.stderr.read(16 * 1024):
            self._stderr_tail.extend(chunk)
            del self._stderr_tail[: max(0, len(self._stderr_tail) - 4096)]

    def _stderr_text(self) -> str:
        return " ".join(self._stderr_tail.decode("utf-8", errors="replace").split())[-1000:]

    async def _kill(self) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(process.wait(), 5.0)


def _parse_response(line: bytes, request_id: int) -> AlfaResult:
    if len(line) > _MAX_RESPONSE_BYTES:
        raise AlfaError("Alfa returned more output for one page state than Axcess can keep.")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise AlfaError("The Alfa worker returned malformed JSON.") from exc
    if not isinstance(payload, Mapping) or payload.get("id") != request_id:
        raise AlfaError("The Alfa worker answered a different request.")
    if "error" in payload:
        raise AlfaError(f"Alfa could not check this page state: {payload.get('error')}")
    return _parse_payload(payload)
