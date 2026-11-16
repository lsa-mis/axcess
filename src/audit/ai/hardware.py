"""What this computer can run, and which model tier to suggest.

Standard library only: memory from the operating system, free disk from the
data folder's drive, and a GPU hint from the vendor tools being installed.
The hint only raises the suggestion; the person can always pick another
tier.
"""

from __future__ import annotations

import ctypes
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from audit.ai.catalog import Catalog, Tier

GB = 1_000_000_000
# Room left on the disk after everything is downloaded, so the computer and
# the reports database are not starved.
DISK_MARGIN = 3 * GB


@dataclass(frozen=True)
class Hardware:
    memory_bytes: int
    free_disk_bytes: int
    apple_silicon: bool
    gpu: str | None
    os: str
    arch: str

    @property
    def accelerated(self) -> bool:
        return self.apple_silicon or self.gpu is not None


def _platform() -> str:
    # A plain str, so type checkers do not treat the other branches as dead.
    return str(sys.platform)


def _memory_bytes() -> int:
    platform = _platform()
    try:
        if platform == "darwin":
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],  # noqa: S607 - system tool, fixed argv
                capture_output=True,
                text=True,
                timeout=5,
            )
            return int(out.stdout.strip())
        if platform.startswith("linux"):
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        if platform.startswith("win"):

            class _Status(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _Status()
            status.dwLength = ctypes.sizeof(_Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
                return int(status.ullTotalPhys)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return 0


def _gpu() -> str | None:
    platform = _platform()
    if platform == "darwin":
        return None
    if shutil.which("nvidia-smi"):
        return "NVIDIA"
    if shutil.which("rocminfo") or Path("/dev/kfd").exists():
        return "AMD"
    return None


def probe(data_dir: Path) -> Hardware:
    data_dir.mkdir(parents=True, exist_ok=True)
    machine = platform.machine().lower()
    return Hardware(
        memory_bytes=_memory_bytes(),
        free_disk_bytes=shutil.disk_usage(data_dir).free,
        apple_silicon=sys.platform == "darwin" and machine == "arm64",
        gpu=_gpu(),
        os=sys.platform,
        arch=machine,
    )


def fits(hardware: Hardware, tier: Tier, extra_bytes: int = 0) -> bool:
    """Enough memory to run the tier and enough disk to download it."""
    enough_memory = hardware.memory_bytes >= tier.min_memory_gb * GB * 0.95
    enough_disk = hardware.free_disk_bytes >= tier.size + extra_bytes + DISK_MARGIN
    return enough_memory and enough_disk


def recommend(hardware: Hardware, catalog: Catalog, extra_bytes: int = 0) -> Tier | None:
    """The largest tier that fits; without a GPU or Apple chip, at most the smallest.

    Larger models on the processor alone answer too slowly to be useful,
    so they are offered but not suggested.
    """
    candidates = [t for t in catalog.tiers if fits(hardware, t, extra_bytes)]
    if not hardware.accelerated:
        candidates = candidates[:1]
    return candidates[-1] if candidates else None
