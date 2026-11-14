"""The private AI service on Windows, run through ``axcess-ai-launcher.exe``.

Windows has no Bubblewrap or sandbox-exec. The launcher (C source in
``desktop/ai-launcher``) puts each ``llama-server`` in a Windows
AppContainer of the stricter "less privileged" kind (LPAC) with no network
capability, inside a job object, and lets it read only the program and
model folders and write only the scratch folder. Each server listens on a
UNIX socket file in scratch. Python on Windows cannot open those sockets,
so the launcher relays each one to a 127.0.0.1 port and accepts a
connection only from this Axcess process (it checks the connecting
process ID). Closing the launcher's input stops everything; if the
launcher dies, Windows ends the job and the servers with it.

The launcher's ``check`` command proves the boundary before every start:
an outside connection fails with an operating-system denial, the program
folder cannot be written, and a socket made inside can be reached from
outside. Any failure means AI does not start. Design and sources:
``docs/internal/windows-ai-sandbox.md``.

Unlike Linux and macOS, there is one server per model, not llama.cpp's
router: the router reaches its per-model servers over loopback, which an
AppContainer blocks. ``ModelRoutingTransport`` sends each request to its
model's port.
"""

from __future__ import annotations

import contextlib
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

from audit.ai.sandbox import IsolationError

LAUNCHER_NAME = "axcess-ai-launcher.exe"
# AppContainer process mitigations and AF_UNIX both need Windows 10 1809.
MIN_WINDOWS_BUILD = 17763
CHECK_LINES = ("AXCESS_NETWORK_BLOCKED", "AXCESS_FILES_LIMITED", "AXCESS_SOCKET_OK")
# The launcher is a console program. Started from the desktop app, which has
# no console, Windows would open a black console window for it that stays
# while AI runs (and closing it would stop AI). It talks only through pipes.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LauncherModelError(Exception):
    """A model's server exited while starting; another build may work."""


@dataclass(frozen=True)
class ModelProcess:
    """One server: the name it answers to, its socket, and its argv."""

    name: str
    socket: Path
    argv: Sequence[str]


def _argv0(launcher: Path) -> list[str]:
    """How to run the launcher (tests swap in a stand-in script)."""
    return [str(launcher)]


def windows_build() -> int:
    getter = getattr(sys, "getwindowsversion", None)
    return int(getter().build) if getter else 0


def require_windows_sandbox(launcher: Path | None) -> None:
    if windows_build() < MIN_WINDOWS_BUILD:
        raise IsolationError(
            "sandbox_unavailable",
            "AI needs Windows 10 version 1809 or later to keep the AI service isolated. "
            "AI was not started. Saved results still work.",
        )
    if launcher is None or not launcher.is_file():
        raise IsolationError(
            "sandbox_unavailable",
            "This copy of Axcess does not include the program that isolates the AI "
            "service. AI was not started. Saved results still work.",
        )


def private_copy(source: Path, dest: Path) -> Path:
    """Copy a bundled build into the data folder, which the user owns.

    The launcher grants the AppContainer read access to the program's
    folder; an install under Program Files cannot have its permissions
    changed without administrator rights.
    """
    if not (dest / "llama-server.exe").is_file():
        staging = dest.with_name(dest.name + ".copying")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(source, staging)
        shutil.rmtree(dest, ignore_errors=True)
        staging.rename(dest)
    return dest


def with_launcher(program: Path, launcher: Path) -> Path:
    """The launcher, copied into the program folder it will sandbox.

    Its ``check`` starts a copy of itself inside the sandbox, which may run
    programs only from that folder. Copied again when the app's launcher
    changes (a new Axcess version).
    """
    target = program / LAUNCHER_NAME
    if launcher.resolve() == target.resolve():
        return target
    source = launcher.stat()
    try:
        current = target.stat()
        same = current.st_size == source.st_size and current.st_mtime >= source.st_mtime
    except OSError:
        same = False
    if not same:
        shutil.copy2(launcher, target)
    return target


def _common(runtime: Path, models: Path, scratch: Path, log: Path, gpu: bool) -> list[str]:
    args = [
        "--scratch",
        str(scratch),
        "--runtime",
        str(runtime),
        "--models",
        str(models),
        "--log",
        str(log),
    ]
    return [*args, "--gpu"] if gpu else args


def run_check(
    launcher: Path, runtime: Path, models: Path, scratch: Path, log: Path, *, gpu: bool
) -> None:
    """The launcher's boundary check; only an exact pass lets AI start."""
    try:
        result = subprocess.run(  # noqa: S603 - bundled launcher, fixed arguments
            [*_argv0(launcher), "check", *_common(runtime, models, scratch, log, gpu)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IsolationError(
            "network_test_failed", "The AI isolation check could not finish. AI was not started."
        ) from exc
    seen = {line.split()[0] for line in result.stdout.splitlines() if line.strip()}
    if result.returncode != 0 or not all(line in seen for line in CHECK_LINES):
        detail = next(
            (ln for ln in result.stdout.splitlines() if ln.startswith("AXCESS_CHECK_FAILED")), ""
        )
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"isolation check failed ({result.returncode}): {detail}\n{result.stderr}\n")
        raise IsolationError(
            "network_test_failed",
            "The AI isolation check did not prove that outside connections are blocked. "
            "AI was not started.",
        )


def note(log: Path, text: str) -> None:
    """One "axcess:" line in the launcher's log, so one file tells the story."""
    with contextlib.suppress(OSError), log.open("a", encoding="utf-8") as fh:
        fh.write(f"axcess {time.strftime('%H:%M:%S')}: {text}\n")


def spec_text(processes: Sequence[ModelProcess]) -> str:
    blocks = []
    for proc in processes:
        lines = [f"MODEL {proc.name}", f"SOCKET {proc.socket}"]
        for arg in proc.argv:
            if "\n" in arg or "\r" in arg:
                raise ValueError("A server argument cannot contain a line break.")
            lines.append(f"ARG {arg}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


class LauncherService:
    """One ``launcher serve`` process and the ports it relays."""

    def __init__(self, launcher: Path) -> None:
        self.launcher = launcher
        self.process: subprocess.Popen[str] | None = None
        self.routes: dict[str, str] = {}
        self._lines: queue.Queue[str | None] = queue.Queue()
        self.exited: list[str] = []

    def start(
        self,
        processes: Sequence[ModelProcess],
        runtime: Path,
        models: Path,
        scratch: Path,
        log: Path,
        *,
        gpu: bool,
    ) -> dict[str, str]:
        spec = scratch / "models.spec"
        spec.write_text(spec_text(processes), encoding="utf-8")
        argv = [
            *_argv0(self.launcher),
            "serve",
            *_common(runtime, models, scratch, log, gpu),
            "--client-pid",
            str(os.getpid()),
            "--spec",
            str(spec),
        ]
        self.process = subprocess.Popen(  # noqa: S603 - bundled launcher, fixed arguments
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=NO_WINDOW,
        )
        reader = threading.Thread(target=self._read, daemon=True, name="axcess-ai-launcher-out")
        reader.start()
        deadline = time.monotonic() + 30
        last = "no answer within 30 s"
        while time.monotonic() < deadline:
            line = self._next(deadline)
            if line is None:
                last = "the launcher closed its output"
                break
            last = line
            parts = line.split()
            if parts[:1] == ["PORT"] and len(parts) == 3 and parts[2].isdigit():
                self.routes[parts[1]] = f"http://127.0.0.1:{int(parts[2])}"
            elif parts[:1] == ["READY"]:
                if set(self.routes) == {p.name for p in processes}:
                    return dict(self.routes)
                break
            elif parts[:1] in (["AXCESS_ERROR"], ["EXIT"]):
                break
        code = self.process.poll()
        self.stop()
        note(log, f"the launcher did not report its ports ({last}; exit code {code})")
        raise IsolationError(
            "runtime_failed", "The isolated AI service could not start. Check the application log."
        )

    def _read(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            self._lines.put(None)
            return
        for line in process.stdout:
            line = line.strip()
            if line.startswith("EXIT "):
                self.exited.append(line.split()[1] if len(line.split()) > 1 else "?")
            self._lines.put(line)
        self._lines.put(None)

    def _next(self, deadline: float) -> str | None:
        try:
            return self._lines.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            return None

    def wait_ready(self, abort: threading.Event, wait_s: float) -> None:
        """Until every model's server answers ``/health`` with 200."""
        deadline = time.monotonic() + wait_s
        with httpx.Client(timeout=2.0, trust_env=False) as http:
            while time.monotonic() < deadline:
                if abort.is_set():
                    raise IsolationError(
                        "runtime_failed", "The AI service was stopped while it was starting."
                    )
                if self.exited:
                    raise LauncherModelError(", ".join(self.exited))
                if not self.running():
                    raise IsolationError(
                        "runtime_failed",
                        "The isolated AI service stopped while starting. Check the "
                        "application log.",
                    )
                ready = 0
                for url in self.routes.values():
                    with contextlib.suppress(httpx.HTTPError):
                        ready += http.get(f"{url}/health").status_code == 200
                if ready == len(self.routes):
                    return
                time.sleep(0.5)
        raise IsolationError("runtime_failed", "The isolated AI service did not start in time.")

    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None and not self.exited

    def stop(self) -> None:
        process, self.process = self.process, None
        self.routes = {}
        if process is None:
            return
        if process.stdin is not None:
            with contextlib.suppress(OSError):
                process.stdin.close()  # The launcher ends the job and exits.
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
