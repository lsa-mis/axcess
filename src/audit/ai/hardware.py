"""What this computer can run, and which model tier to suggest.

Standard library only: memory from the operating system, free disk from the
data folder's drive, and a GPU hint from the vendor tools being installed.
The hint only raises the suggestion; the person can always pick another
tier.
"""

from __future__ import annotations

import ctypes
import platform
import re
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
    # Memory on separate graphics cards (not shared with the computer), as
    # llama.cpp reports it (``parse_devices``). 0 when there is none or it
    # is not known yet.
    gpu_memory_bytes: int = 0

    @property
    def accelerated(self) -> bool:
        return self.apple_silicon or self.gpu is not None or self.gpu_memory_bytes > 0

    @property
    def ai_memory_gb(self) -> int:
        """Memory the AI models can use: the computer's plus a separate card's.

        llama.cpp puts as much of a model as fits on the graphics card and
        the rest in the computer's memory, so both count (developer,
        2026-11-19: an 8 GB laptop with an 8 GB card can run Standard).
        0 when the computer's memory is unknown, which never refuses.
        """
        ram = memory_gb(self.memory_bytes)
        return ram + memory_gb(self.gpu_memory_bytes) if ram else 0


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


def _macos_available(vm_stat: str, total: int) -> int:
    """Memory a new program can have on macOS without swapping.

    The larger of two readings. Free, inactive, speculative and purgeable
    pages alone undercount: macOS keeps most spare memory as file cache
    (file-backed pages), which it gives back at once. So also everything
    that is not wired, compressed or held by programs (anonymous pages),
    as Activity Monitor's "Memory Used" leaves out (2026-11-17: the narrow
    reading refused Standard on a 16 GB Mac with room to spare).
    """
    page = int(vm_stat.split("page size of", 1)[1].split()[0])
    counts: dict[str, int] = {}
    for line in vm_stat.splitlines():
        key, _, value = line.partition(":")
        value = value.strip().rstrip(".")
        if value.isdigit():
            counts[key.strip()] = int(value)
    quick = sum(
        counts.get(k, 0)
        for k in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable")
    )
    held = sum(
        counts.get(k, 0)
        for k in ("Pages wired down", "Pages occupied by compressor", "Anonymous pages")
    )
    reclaimable = total - held * page if total else 0
    return max(quick * page, reclaimable)


# Memory sizes computers are sold with, in GB.
SOLD_MEMORY_GB = (4, 6, 8, 12, 16, 18, 24, 32, 36, 48, 64, 96, 128, 192, 256)


def memory_gb(memory_bytes: int) -> int:
    """Memory as computers are sold: 16, not the 15 the system reports.

    The system keeps some memory for itself, so a 16 GB computer reports
    about 15.3 GiB. A total within 10% below a sold size is that size;
    anything else is rounded. 0 when the memory is unknown. The AI features
    page shows this number next to each size's "for computers with 16 GB of
    memory or more", warns on a computer with less, and ``size_refused``
    uses it too, so all agree (developer, 2026-11-18: a 16 GB computer read
    "15 GB" and looked too small for Standard).
    """
    if memory_bytes <= 0:
        return 0
    gib = memory_bytes / 1024**3
    sold = next((size for size in SOLD_MEMORY_GB if size >= gib - 0.05), None)
    return sold if sold is not None and sold - gib <= sold * 0.1 else round(gib)


# The one memory refusal (developer, 2026-11-18: "only refuse to start 16 gb
# and above on a 8gb laptop"). A computer with this much memory or less is
# refused every size that is for 16 GB or more.
SMALL_COMPUTER_GB = 8
REFUSED_ON_SMALL_COMPUTER_GB = 16


def size_refused(memory_gb: int, tier: Tier) -> bool:
    """This size cannot be downloaded or started on this computer.

    Only an 8 GB (or smaller) computer and a size for 16 GB or more. Any
    other size bigger than the computer's memory is allowed with a warning,
    because the operating system makes room. ``memory_gb`` is
    ``Hardware.ai_memory_gb``: as computers are sold, with a separate
    graphics card's memory added, so 8 GB plus an 8 GB card is 16 and is
    not refused. 0 means unknown and never refuses.
    """
    return 0 < memory_gb <= SMALL_COMPUTER_GB and tier.min_memory_gb >= REFUSED_ON_SMALL_COMPUTER_GB


@dataclass(frozen=True)
class GpuDevice:
    """One graphics device llama.cpp can use."""

    name: str
    total_bytes: int
    free_bytes: int
    # Shares the computer's memory (built-in graphics, Apple chips), so its
    # memory is not extra room.
    shared: bool


# ``llama-server -v --list-devices`` (b12284). The Vulkan backend's debug
# line says whether a device shares the computer's memory ("uma: 1"); the
# list gives each device's memory. Checked 2026-11-19 on Intel Iris Xe:
#   ggml_vulkan: 0 = Intel(R) Iris(R) Xe Graphics (TGL GT2) (...) | uma: 1 | ...
#   Vulkan0: Intel(R) Iris(R) Xe Graphics (TGL GT2) (11771 MiB, 3664 MiB free)
_VULKAN_INFO = re.compile(r"ggml_vulkan: (\d+) = .*?\| uma: (\d)")
_DEVICE_LINE = re.compile(r"^\s*([A-Za-z]+)(\d+): (.+) \((\d+) MiB, (\d+) MiB free\)\s*$")


def parse_devices(output: str) -> list[GpuDevice]:
    """The devices in ``llama-server -v --list-devices`` output.

    A device counts as separate only when it is a Vulkan device whose
    debug line says "uma: 0". Anything else (Metal, a missing line) is
    treated as shared, so its memory is never counted twice.
    """
    uma = {int(m.group(1)): m.group(2) == "1" for m in _VULKAN_INFO.finditer(output)}
    devices = []
    for line in output.splitlines():
        match = _DEVICE_LINE.match(line)
        if not match:
            continue
        backend, index, name, total, free = match.groups()
        separate = backend == "Vulkan" and uma.get(int(index)) is False
        devices.append(
            GpuDevice(
                name=name.strip(),
                total_bytes=int(total) * 1024**2,
                free_bytes=int(free) * 1024**2,
                shared=not separate,
            )
        )
    return devices


def available_memory_bytes() -> int | None:
    """Memory free for a new program right now, or None when unknown.

    Linux: ``MemAvailable``. Windows: ``ullAvailPhys``. macOS: free,
    inactive, speculative and purgeable pages from ``vm_stat`` (the pages
    the system gives to a new program without swapping).
    """
    platform = _platform()
    try:
        if platform.startswith("linux"):
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
        elif platform == "darwin":
            out = subprocess.run(
                ["vm_stat"],  # noqa: S607 - system tool, fixed argv
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
            return _macos_available(out, _memory_bytes())
        elif platform.startswith("win"):

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
                return int(status.ullAvailPhys)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return None


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
    """Enough memory to run the tier and enough disk to download it.

    Used to suggest a size and to warn; a size that does not fit can still
    be chosen unless ``size_refused`` says otherwise.
    """
    # The same figure the page shows: the computer's memory plus a separate
    # graphics card's.
    enough_memory = hardware.ai_memory_gb >= tier.min_memory_gb
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
