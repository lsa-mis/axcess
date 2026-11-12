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
            # The service's own UNIX socket, in the scratch folder only.
            f"(allow network-bind network-inbound (local unix-socket (subpath "
            f"{path(scratch.resolve())})))",
            # The llama.cpp router reaches its per-model children on
            # loopback. macOS has no private network namespace, so loopback
            # is the narrowest network the router can use.
            '(allow network-inbound (local ip "localhost:*"))',
            '(allow network-outbound (remote ip "localhost:*"))',
            '(allow network-bind (local ip "localhost:*"))',
        ]
    )


# Read-only system folders a GPU build needs to find the graphics card inside
# Bubblewrap (checked 2026-11-12 with llama.cpp's Vulkan build on Intel Iris
# Xe and Mesa): without them Vulkan reports no device and the model runs on
# the CPU. Device information only; nothing here opens a network path.
_LINUX_GPU_READS = ("/sys/dev/char", "/sys/devices", "/sys/bus/pci")


def build_sandbox(
    runtime: Path,
    models: Path,
    scratch: Path,
    *,
    platform: str | None = None,
    gpu: bool = False,
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
            # The executable's own folder too: in the packaged app it holds
            # the backend that runs the network probe, and PyInstaller's
            # ``sys.base_prefix`` is only its ``_internal`` subfolder.
            for p in (
                "/usr",
                "/lib",
                "/lib64",
                sys.base_prefix,
                str(Path(sys.executable).resolve().parent),
                str(runtime.resolve()),
            ):
                if Path(p).exists():
                    args += ["--ro-bind", p, p]
            if gpu:
                # The graphics devices: /dev/dri (Mesa: Intel, AMD) and the
                # NVIDIA driver's device files when they exist.
                args += ["--dev-bind-try", "/dev/dri", "/dev/dri"]
                for name in ("nvidiactl", "nvidia-uvm", "nvidia0", "nvidia1"):
                    args += ["--dev-bind-try", f"/dev/{name}", f"/dev/{name}"]
                for p in _LINUX_GPU_READS:
                    args += ["--ro-bind-try", p, p]
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

# The packaged desktop backend is a PyInstaller executable, not a Python
# interpreter: it ignores ``-I -S -c`` and starts the server's argument
# parser, which exits with a usage error, so the probe could never pass.
# It answers this flag instead (``desktop/backend_entry.py``).
NETWORK_PROBE_FLAG = "--axcess-network-probe"


def run_network_probe() -> None:
    """Run the probe in this process and exit; for the packaged backend."""
    exec(compile(_PROBE, "<axcess-network-probe>", "exec"), {"__name__": "__probe__"})  # noqa: S102 - fixed constant
    sys.exit(1)


def _probe_argv() -> list[str]:
    executable = str(Path(sys.executable).resolve())
    if getattr(sys, "frozen", False):
        return [executable, NETWORK_PROBE_FLAG]
    return [executable, "-I", "-S", "-c", _PROBE]


def test_network_boundary(sandbox: Sandbox) -> None:
    """A timeout or broken probe is not proof: only an OS denial passes."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed probe inside the selected OS sandbox
            sandbox.command(_probe_argv()),
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
