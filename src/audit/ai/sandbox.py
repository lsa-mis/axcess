"""Fail-closed OS isolation for the private, offline model service."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

IsolationReason = Literal[
    "sandbox_unavailable", "network_test_failed", "namespace_unreachable", "runtime_failed"
]


class IsolationError(Exception):
    def __init__(self, reason: IsolationReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class Sandbox:
    prefix: list[str]

    def command(self, argv: list[str]) -> list[str]:
        return [*self.prefix, *argv]


def macos_profile(runtime: Path, models: Path, scratch: Path) -> str:
    """Allow system libraries and explicit service paths, never outside networking."""

    def path(value: Path | str) -> str:
        return json.dumps(str(value))

    # Python is allowed only for the preflight; -I -S excludes user site packages.
    reads = [
        runtime.resolve(),
        models.resolve(),
        scratch.resolve(),
        Path(sys.base_prefix),
        Path(sys.executable).resolve().parent,
        Path("/System/Library"),
        Path("/usr/lib"),
        Path("/Library/Apple/System/Library"),
        Path("/dev/null"),
        Path("/dev/urandom"),
    ]
    return "\n".join(
        [
            "(version 1)",
            "(deny default)",
            "(allow process-fork)",
            f"(allow process-exec (subpath {path(runtime.resolve())}) "
            f"(literal {path(Path(sys.executable).resolve())}))",
            "(allow sysctl-read)",
            '(allow file-read* (literal "/"))',
            "(allow file-read* " + " ".join(f"(subpath {path(p)})" for p in reads) + ")",
            f"(allow file-write* (subpath {path(models.resolve())}) "
            f'(subpath {path(scratch.resolve())}) (literal "/dev/null"))',
            # Metal (Mac GPU) only: the Apple graphics driver clients and the
            # shader compiler. Without these, model loading crashes. Neither
            # opens a network path; no general mach-lookup or iokit-open.
            "(allow iokit-open (iokit-user-client-class "
            '"AGXDeviceUserClient" "AGXSharedUserClient" "IOSurfaceRootUserClient" '
            '"IOAccelerator"))',
            '(allow mach-lookup (global-name "com.apple.MTLCompilerService"))',
            '(allow network-inbound (local ip "localhost:*"))',
            '(allow network-outbound (remote ip "localhost:*"))',
            '(allow network-bind (local ip "localhost:*"))',
        ]
    )


def build_sandbox(
    runtime: Path, models: Path, scratch: Path, *, platform: str | None = None
) -> Sandbox:
    platform = platform or sys.platform
    if platform == "darwin":
        tool = shutil.which("sandbox-exec")
        if tool:
            return Sandbox([tool, "-p", macos_profile(runtime, models, scratch)])
    elif platform.startswith("linux"):
        tool = shutil.which("bwrap")
        if tool:
            args = [
                tool,
                "--unshare-net",
                "--die-with-parent",
                "--new-session",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
            ]
            for p in ("/usr", "/lib", "/lib64", sys.base_prefix, str(runtime.resolve())):
                if Path(p).exists():
                    args += ["--ro-bind", p, p]
            args += [
                "--bind",
                str(models.resolve()),
                str(models.resolve()),
                "--bind",
                str(scratch.resolve()),
                str(scratch.resolve()),
                "--",
            ]
            return Sandbox(args)
        tool = shutil.which("unshare")
        if tool:
            # A network namespace alone does not restrict filesystem access.
            # Refuse rather than silently weaken the filesystem boundary.
            raise IsolationError(
                "sandbox_unavailable",
                "This computer needs Bubblewrap to keep AI files and networking separate. "
                "AI was not started.",
            )
    raise IsolationError(
        "sandbox_unavailable",
        "This computer cannot isolate the AI service. AI was not started. "
        "Saved results still work.",
    )


_PROBE = """import errno,socket,sys
try:
 s=socket.socket();s.settimeout(1);s.connect(('1.1.1.1',443))
except OSError as e:
 if e.errno in (errno.EPERM,errno.EACCES,errno.ENETUNREACH,errno.EHOSTUNREACH):
  print('AXCESS_NETWORK_BLOCKED');sys.exit(0)
sys.exit(1)
"""


def test_network_boundary(sandbox: Sandbox) -> None:
    """A timeout or broken probe is not proof: only an OS denial passes."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed probe inside the selected OS sandbox
            sandbox.command([str(Path(sys.executable).resolve()), "-I", "-S", "-c", _PROBE]),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IsolationError(
            "network_test_failed", "The AI isolation check could not finish. AI was not started."
        ) from exc
    if result.returncode != 0 or result.stdout.strip() != "AXCESS_NETWORK_BLOCKED":
        raise IsolationError(
            "network_test_failed",
            "The AI isolation check did not prove that outside connections are blocked. "
            "AI was not started.",
        )
