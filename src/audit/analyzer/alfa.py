"""Bounded local adapter for the Siteimprove Alfa ACT-rule engine.

Alfa is deliberately not folded into :mod:`audit.analyzer.axe`: it is an
independent rule engine with a different outcome vocabulary. The small Node
runner in ``audit/alfa_runner`` uses Alfa's maintained Playwright integration,
then this module validates and normalizes its bounded JSON result for the
Python-owned crawler and SQLite evidence store.

No package is downloaded at scan time. Operators install the pinned runner
dependencies explicitly with ``make alfa-install``. A selected-but-unavailable
Alfa engine is rejected before a web scan starts; a per-page runner failure is
recorded as a limitation instead of being mistaken for a clean result.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from audit.logging import get_logger

log = get_logger(__name__)

Outcome = Literal["failed", "cant_tell"]
_MAX_INPUT_BYTES = 1_500_000
_MAX_STDOUT_BYTES = 1_500_000
_MAX_STDERR_BYTES = 64 * 1024
_PIPE_READ_CHUNK_BYTES = 16 * 1024
_RUNNER_STOP_TIMEOUT_S = 5.0
_RUNNER_DIR = Path(__file__).resolve().parents[1] / "alfa_runner"
_RUNNER_PATH = _RUNNER_DIR / "runner.mjs"
_PACKAGE_PATH = _RUNNER_DIR / "package.json"
_PROTECTED_RUNNER_FAILURE = "The protected Alfa engine could not complete this page."


class AlfaError(RuntimeError):
    """The optional local Alfa engine could not return usable evidence."""


class _AlfaPipeLimitError(RuntimeError):
    """A runner pipe exceeded its explicit, in-memory output bound."""


@dataclass(frozen=True, slots=True)
class AlfaAvailability:
    available: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class AlfaFinding:
    """One actionable Alfa outcome, normalized for ``page_a11y_findings``."""

    rule_id: str
    rule_uri: str
    outcome: Outcome
    mode: str
    wcag_sc: str | None
    wcag_scs: str | None
    wcag_level: str | None
    help: str
    failure_summary: str
    target_hint: str
    evidence_json: str

    @property
    def target_hash(self) -> str:
        h = hashlib.sha256()
        for value in (self.rule_id, self.outcome, self.target_hint):
            h.update(value.encode("utf-8", errors="replace"))
            h.update(b"\x00")
        return h.hexdigest()

    @property
    def impact(self) -> str | None:
        # Alfa's ACT outcomes intentionally do not provide axe-style impact.
        # Keeping this NULL avoids inventing a severity. The issue queue still
        # gives the group a conservative, visible default priority.
        return None


@dataclass(frozen=True, slots=True)
class AlfaResult:
    url: str
    status: int
    findings: tuple[AlfaFinding, ...]
    failed_total: int
    cant_tell_total: int
    truncated: bool
    authentication_required: bool = False


def availability() -> AlfaAvailability:
    """Return whether the pinned, local runner can be started.

    This is intentionally a fast filesystem/process preflight, not a browser
    launch. Browser launch remains part of each selected page evaluation.
    """
    if _node_executable() is None:
        return AlfaAvailability(False, "Node.js 22 or later is not available.")
    if not _RUNNER_PATH.is_file() or not _PACKAGE_PATH.is_file():
        return AlfaAvailability(False, "The bundled Alfa runner is missing.")
    if not (_RUNNER_DIR / "node_modules" / "@siteimprove" / "alfa-act").is_dir():
        return AlfaAvailability(
            False,
            "Alfa's local dependencies are not installed. Run `make alfa-install`.",
        )
    return AlfaAvailability(True)


class AlfaAnalyzer:
    """Run the local Alfa adapter with a bounded subprocess per page."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_s: float = 75.0,
        concurrency: int = 1,
        chromium_path: str | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_s = timeout_s
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._chromium_path = chromium_path

    async def run(
        self,
        url: str,
        *,
        level: str,
        storage_state: Mapping[str, Any] | None = None,
        allowed_origins: Sequence[str] = (),
        target_origins: Sequence[str] = (),
        egress_proxy: str | None = None,
    ) -> AlfaResult:
        """Evaluate one already in-scope page with Alfa.

        The adapter is intentionally serialized by default: Alfa's browser
        capture is a second snapshot of the page, and one local Chromium at a
        time protects laptop resources while Axcess' own crawler workers run.
        """
        if level not in {"A", "AA", "AAA"}:
            raise AlfaError(f"Unsupported Alfa WCAG level: {level}")
        state = availability()
        if not state.available:
            raise AlfaError(state.reason or "Alfa is unavailable.")
        # Do not inherit application secrets into the companion-side Node
        # process.  The runner only needs PATH and, optionally, Chromium's
        # already-installed executable path.  Authenticated browser state is
        # supplied through an inherited stdin pipe, never arguments, env, or
        # a file.
        node_executable = _node_executable()
        if node_executable is None:
            raise AlfaError("Node.js 22 or later is not available.")
        env = {"PATH": os.environ.get("PATH", "")}
        if os.environ.get("AUDIT_NODE_RUN_AS_NODE") == "1":
            # A packaged Electron executable can provide its embedded Node
            # runtime to the bundled Alfa runner without requiring a separate
            # system installation. No application secrets are forwarded.
            env["ELECTRON_RUN_AS_NODE"] = "1"
        if os.environ.get("AUDIT_RUNTIME_VERIFICATION_DIAGNOSTICS") == "1":
            # Only the fixed, local desktop build fixture enables this. Normal
            # scans keep browser diagnostics generic because exception text can
            # contain target-controlled URLs or page content.
            env["ALFA_RUNTIME_VERIFICATION_DIAGNOSTICS"] = "1"
        if self._chromium_path:
            env["ALFA_CHROMIUM_PATH"] = self._chromium_path
        # The page URL can itself contain a protected path/record identifier.
        # Send all runner input through the one-use stdin pipe, not argv,
        # environment, a file, or process-list-visible command arguments.
        args = [node_executable, str(_RUNNER_PATH), "--input-stdin"]
        runner_input: dict[str, Any] = {
            "url": url,
            "level": level,
            "user_agent": self._user_agent,
        }
        if storage_state is not None:
            runner_input.update(
                {
                    "storage_state": storage_state,
                    "allowed_origins": list(allowed_origins),
                    # A CDN may be needed for subresources but must never
                    # become an authenticated document/iframe destination.
                    "target_origins": list(target_origins),
                    "egress_proxy": egress_proxy or "",
                }
            )
        input_bytes = json.dumps(runner_input, separators=(",", ":")).encode("utf-8")
        if len(input_bytes) > _MAX_INPUT_BYTES:
            raise AlfaError("Authenticated browser state exceeds the safe runner bound.")
        # Supplying a browser state is the protected-scan bridge.  Never
        # surface Node/Chromium diagnostics for that path: runner stderr can
        # contain a URL, a redirect location, or target-controlled content.
        protected_run = storage_state is not None
        process: asyncio.subprocess.Process | None = None
        tasks: tuple[asyncio.Task[Any], ...] = ()
        async with self._semaphore:
            try:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    cwd=str(_RUNNER_DIR),
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                if process.stdin is None or process.stdout is None or process.stderr is None:
                    raise AlfaError("Alfa runner did not expose the required local pipes.")
                stdout_reader = asyncio.create_task(
                    _read_runner_pipe(process.stdout, limit=_MAX_STDOUT_BYTES)
                )
                stderr_reader = asyncio.create_task(
                    _read_runner_pipe(process.stderr, limit=_MAX_STDERR_BYTES)
                )
                stdin_writer = asyncio.create_task(_write_runner_input(process.stdin, input_bytes))
                waiter = asyncio.create_task(process.wait())
                tasks = (stdout_reader, stderr_reader, stdin_writer, waiter)
                stdout, stderr, _, _ = await asyncio.wait_for(
                    asyncio.gather(stdout_reader, stderr_reader, stdin_writer, waiter),
                    self._timeout_s,
                )
            except TimeoutError as exc:
                await _stop_runner_process(process, tasks)
                raise AlfaError(f"Alfa timed out after {self._timeout_s:.0f} seconds.") from exc
            except _AlfaPipeLimitError as exc:
                await _stop_runner_process(process, tasks)
                raise AlfaError(
                    "Alfa returned more output than Axcess can safely retain for one page."
                ) from exc
            except asyncio.CancelledError:
                await _stop_runner_process(process, tasks)
                raise
            except OSError as exc:
                await _stop_runner_process(process, tasks)
                if protected_run:
                    raise AlfaError(_PROTECTED_RUNNER_FAILURE) from exc
                raise AlfaError(f"Could not start Alfa: {exc}") from exc
            except AlfaError:
                await _stop_runner_process(process, tasks)
                raise
            except Exception as exc:
                await _stop_runner_process(process, tasks)
                if protected_run:
                    raise AlfaError(_PROTECTED_RUNNER_FAILURE) from exc
                raise
        if process is None:  # pragma: no cover - guarded by subprocess creation above
            raise AlfaError("Could not start Alfa.")
        if process.returncode != 0:
            if protected_run:
                raise AlfaError(_PROTECTED_RUNNER_FAILURE)
            message = stderr.decode("utf-8", errors="replace").strip()
            raise AlfaError(message or f"Alfa runner exited with code {process.returncode}.")
        return _parse_result(stdout)


def _node_executable() -> str | None:
    """Resolve the explicitly supplied desktop Node runtime or system Node."""

    configured = os.environ.get("AUDIT_NODE_EXECUTABLE", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        return None
    return shutil.which("node")


async def _read_runner_pipe(reader: asyncio.StreamReader, *, limit: int) -> bytes:
    """Read a runner pipe without accumulating unbounded child output."""

    content = bytearray()
    while True:
        chunk = await reader.read(_PIPE_READ_CHUNK_BYTES)
        if not chunk:
            return bytes(content)
        content.extend(chunk)
        if len(content) > limit:
            content.clear()
            raise _AlfaPipeLimitError


async def _write_runner_input(writer: asyncio.StreamWriter, content: bytes) -> None:
    """Send one bounded JSON request and always close the inherited pipe."""

    try:
        writer.write(content)
        await writer.drain()
    except (BrokenPipeError, ConnectionResetError):
        # A runner that exits before reading its request is reported from its
        # return code.  Do not mask that result with a transport detail.
        return
    finally:
        writer.close()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            await writer.wait_closed()


async def _stop_runner_process(
    process: asyncio.subprocess.Process | None,
    tasks: tuple[asyncio.Task[Any], ...],
) -> None:
    """Kill a failed runner and discard all still-pending pipe data."""

    if process is not None and process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(process.wait(), _RUNNER_STOP_TIMEOUT_S)
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        with contextlib.suppress(Exception):
            await asyncio.gather(*tasks, return_exceptions=True)


async def chromium_executable_path() -> str | None:
    """Return Axcess' already-installed Playwright Chromium, if present.

    The Node runner receives the path explicitly so the optional Alfa package
    does not download a second browser runtime. Starting Playwright here only
    discovers the path; it does not launch a browser.
    """
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            path = Path(pw.chromium.executable_path)
        return str(path) if path.exists() else None
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("alfa.chromium_path_unavailable", error=str(exc))
        return None


def _parse_result(raw: bytes) -> AlfaResult:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AlfaError("Alfa returned malformed JSON evidence.") from exc
    if not isinstance(payload, dict) or payload.get("protocol_version") != 1:
        raise AlfaError("Alfa returned an unsupported evidence protocol.")
    if payload.get("engine") != "alfa":
        raise AlfaError("Alfa runner identified an unexpected engine.")
    counts = payload.get("outcome_counts")
    if not isinstance(counts, dict):
        raise AlfaError("Alfa response omitted outcome counts.")
    findings_raw = payload.get("findings")
    if not isinstance(findings_raw, list):
        raise AlfaError("Alfa response omitted findings.")
    findings = tuple(_parse_finding(item) for item in findings_raw[:200])
    return AlfaResult(
        url=_bounded_text(payload.get("url"), 4096),
        status=_as_int(payload.get("status")),
        findings=findings,
        failed_total=_as_int(counts.get("failed")),
        cant_tell_total=_as_int(counts.get("cantTell")),
        truncated=bool(payload.get("findings_truncated")),
        authentication_required=payload.get("authentication_required") is True,
    )


def _parse_finding(value: Any) -> AlfaFinding:
    if not isinstance(value, dict):
        raise AlfaError("Alfa returned an invalid finding.")
    raw_outcome = value.get("outcome")
    if raw_outcome == "cantTell":
        outcome: Outcome = "cant_tell"
    elif raw_outcome == "failed":
        outcome = "failed"
    else:
        raise AlfaError("Alfa returned a non-actionable outcome as a finding.")
    rule_id = _bounded_text(value.get("rule_id"), 128)
    if not rule_id:
        raise AlfaError("Alfa finding omitted its rule id.")
    scs_raw = value.get("wcag_scs")
    scs = [
        _bounded_text(sc, 32)
        for sc in (scs_raw if isinstance(scs_raw, list) else [])
        if _bounded_text(sc, 32)
    ]
    return AlfaFinding(
        rule_id=rule_id,
        rule_uri=_bounded_text(value.get("rule_uri"), 4096),
        outcome=outcome,
        mode=_bounded_text(value.get("mode"), 32),
        wcag_sc=_bounded_text(value.get("wcag_sc"), 32) or None,
        wcag_scs=",".join(dict.fromkeys(scs)) or None,
        wcag_level=_bounded_text(value.get("wcag_level"), 8) or None,
        help=_bounded_text(value.get("help"), 2000) or f"Alfa ACT rule {rule_id}",
        failure_summary=_bounded_text(value.get("failure_summary"), 8000),
        target_hint=_bounded_text(value.get("target_hint"), 4000)
        or "Alfa target unavailable; see the stored evidence.",
        evidence_json=_bounded_text(value.get("evidence"), 12000),
    )


def _bounded_text(value: Any, maximum: int) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:maximum]


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
