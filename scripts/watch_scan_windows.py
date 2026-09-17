"""Watch what the operating system actually shows while a login scan runs.

A login scan opens a headed Chromium for manual sign-in and is then supposed to
stay out of the auditor's way. Whether it does is a fact about the window
server, not about what Chromium reports over CDP: a window can claim to be
minimized and still be drawn. This probe asks the OS directly.

It follows only the Chromium that Axcess launched, identified by the ephemeral
profile directory on its command line, and reports how much of any of its
windows intersects a display. It reads geometry only: never a window title,
page content, or pixels, so it needs no Screen Recording permission.

    uv run python scripts/watch_scan_windows.py            # until Ctrl-C
    uv run python scripts/watch_scan_windows.py --duration 120 --json trace.json
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

# The directory name `_create_ephemeral_profile_dir` builds the profile under.
PROFILE_MARKER = "axcess-protected-browser"


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def intersection_area(self, other: Rect) -> float:
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.x + self.width, other.x + other.width)
        bottom = min(self.y + self.height, other.y + other.height)
        if right <= left or bottom <= top:
            return 0.0
        return (right - left) * (bottom - top)


@dataclass(frozen=True)
class WindowSample:
    pid: int
    window_id: int
    bounds: Rect
    # The window server has the window ordered in: not minimized, not hidden.
    ordered_in: bool
    # Pixels of this window that land on any display while ordered in.
    visible_area: float


def browser_pids(marker: str = PROFILE_MARKER) -> set[int]:
    """Processes of the Chromium that Axcess launched for a login scan."""

    if sys.platform == "win32":
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | ForEach-Object "
            '{ "$($_.ProcessId) $($_.CommandLine)" }',
        ]
    else:
        command = ["ps", "-axo", "pid=,command="]
    try:
        listing = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    pids: set[int] = set()
    for line in listing.splitlines():
        head, _, rest = line.strip().partition(" ")
        if marker in rest and head.isdigit():
            pids.add(int(head))
    return pids


def sample_windows(pids: set[int]) -> list[WindowSample]:
    """Every normal-layer window owned by ``pids``, with its on-display area."""

    if not pids:
        return []
    if sys.platform == "darwin":
        return _sample_macos(pids)
    if sys.platform == "win32":
        return _sample_windows_os(pids)
    raise RuntimeError("The window probe supports macOS and Windows only.")


def total_visible_area(samples: list[WindowSample]) -> float:
    return sum(sample.visible_area for sample in samples)


# --------------------------------------------------------------------------
# macOS: CoreGraphics window list
# --------------------------------------------------------------------------


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [("origin", _CGPoint), ("size", _CGSize)]


_K_CF_STRING_ENCODING_UTF8 = 0x08000100
_K_CF_NUMBER_SINT64 = 4
_K_CF_NUMBER_FLOAT64 = 6
_K_CG_WINDOW_LIST_ALL_NO_DESKTOP = 16  # OptionAll | ExcludeDesktopElements

_mac_libs: tuple[Any, Any] | None = None


def _mac() -> tuple[Any, Any]:
    global _mac_libs
    if _mac_libs is not None:
        return _mac_libs
    cf_path = ctypes.util.find_library("CoreFoundation")
    cg_path = ctypes.util.find_library("CoreGraphics")
    if cf_path is None or cg_path is None:
        raise RuntimeError("CoreGraphics is unavailable.")
    cf = ctypes.CDLL(cf_path)
    cg = ctypes.CDLL(cg_path)
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
    cf.CFBooleanGetValue.restype = ctypes.c_bool
    cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
    cf.CFRelease.restype = None
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    cg.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
    cg.CGRectMakeWithDictionaryRepresentation.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_CGRect),
    ]
    cg.CGGetActiveDisplayList.restype = ctypes.c_int32
    cg.CGGetActiveDisplayList.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    cg.CGDisplayBounds.restype = _CGRect
    cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
    _mac_libs = (cf, cg)
    return _mac_libs


def _mac_displays() -> list[Rect]:
    _, cg = _mac()
    ids = (ctypes.c_uint32 * 16)()
    count = ctypes.c_uint32(0)
    if cg.CGGetActiveDisplayList(16, ids, ctypes.byref(count)) != 0:
        return []
    displays = []
    for index in range(count.value):
        rect = cg.CGDisplayBounds(ids[index])
        displays.append(Rect(rect.origin.x, rect.origin.y, rect.size.width, rect.size.height))
    return displays


def _sample_macos(pids: set[int]) -> list[WindowSample]:
    cf, cg = _mac()
    displays = _mac_displays()
    keys = {
        name: cf.CFStringCreateWithCString(None, name.encode(), _K_CF_STRING_ENCODING_UTF8)
        for name in (
            "kCGWindowOwnerPID",
            "kCGWindowNumber",
            "kCGWindowBounds",
            "kCGWindowIsOnscreen",
            "kCGWindowLayer",
            "kCGWindowAlpha",
        )
    }

    def integer(entry: int, key: str) -> int | None:
        ref = cf.CFDictionaryGetValue(entry, keys[key])
        if not ref:
            return None
        value = ctypes.c_int64(0)
        if not cf.CFNumberGetValue(ref, _K_CF_NUMBER_SINT64, ctypes.byref(value)):
            return None
        return value.value

    def real(entry: int, key: str) -> float | None:
        ref = cf.CFDictionaryGetValue(entry, keys[key])
        if not ref:
            return None
        value = ctypes.c_double(0)
        if not cf.CFNumberGetValue(ref, _K_CF_NUMBER_FLOAT64, ctypes.byref(value)):
            return None
        return value.value

    samples: list[WindowSample] = []
    listing = cg.CGWindowListCopyWindowInfo(_K_CG_WINDOW_LIST_ALL_NO_DESKTOP, 0)
    try:
        if not listing:
            return []
        for index in range(cf.CFArrayGetCount(listing)):
            entry = cf.CFArrayGetValueAtIndex(listing, index)
            pid = integer(entry, "kCGWindowOwnerPID")
            if pid is None or pid not in pids:
                continue
            # Layer 0 is where application windows live; menus, the Dock tile
            # and status items sit on other layers and are not browser windows.
            if integer(entry, "kCGWindowLayer") != 0:
                continue
            bounds_ref = cf.CFDictionaryGetValue(entry, keys["kCGWindowBounds"])
            rect = _CGRect()
            if not bounds_ref or not cg.CGRectMakeWithDictionaryRepresentation(
                bounds_ref, ctypes.byref(rect)
            ):
                continue
            bounds = Rect(rect.origin.x, rect.origin.y, rect.size.width, rect.size.height)
            onscreen_ref = cf.CFDictionaryGetValue(entry, keys["kCGWindowIsOnscreen"])
            ordered_in = bool(onscreen_ref) and bool(cf.CFBooleanGetValue(onscreen_ref))
            alpha = real(entry, "kCGWindowAlpha")
            drawn = ordered_in and (alpha is None or alpha > 0)
            area = sum(bounds.intersection_area(d) for d in displays) if drawn else 0.0
            samples.append(
                WindowSample(
                    pid=pid,
                    window_id=integer(entry, "kCGWindowNumber") or 0,
                    bounds=bounds,
                    ordered_in=ordered_in,
                    visible_area=area,
                )
            )
    finally:
        if listing:
            cf.CFRelease(listing)
        for ref in keys.values():
            cf.CFRelease(ref)
    return samples


# --------------------------------------------------------------------------
# Windows: user32 top-level windows. Not exercised on the macOS development
# machine; kept deliberately small so it can be checked by reading.
# --------------------------------------------------------------------------


def _sample_windows_os(pids: set[int]) -> list[WindowSample]:
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    # Handles are pointer-sized. Left to ctypes' default they are passed as a
    # C int, which only works while a handle happens to fit in 32 bits.
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    dwmwa_cloaked = 14
    displays: list[Rect] = []

    monitor_proc = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.RECT),
        ctypes.c_void_p,
    )

    def on_monitor(_monitor: int, _dc: int, rect: Any, _data: int) -> int:
        r = rect.contents
        displays.append(Rect(r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    user32.EnumDisplayMonitors(None, None, monitor_proc(on_monitor), 0)

    samples: list[WindowSample] = []
    window_proc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

    def on_window(hwnd: int, _data: int) -> int:
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return 1
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return 1
        bounds = Rect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
        if bounds.width <= 0 or bounds.height <= 0:
            return 1
        # A cloaked window (another virtual desktop, a suspended app) is
        # "visible" to user32 and drawn nowhere.
        cloaked = wintypes.DWORD(0)
        dwmapi.DwmGetWindowAttribute(
            hwnd, dwmwa_cloaked, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        ordered_in = (
            bool(user32.IsWindowVisible(hwnd))
            and not bool(user32.IsIconic(hwnd))
            and not cloaked.value
        )
        area = sum(bounds.intersection_area(d) for d in displays) if ordered_in else 0.0
        samples.append(
            WindowSample(
                pid=int(pid.value),
                window_id=int(hwnd or 0),
                bounds=bounds,
                ordered_in=ordered_in,
                visible_area=area,
            )
        )
        return 1

    user32.EnumWindows(window_proc(on_window), 0)
    return samples


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _describe(samples: list[WindowSample]) -> str:
    if not samples:
        return "no Axcess browser window"
    parts = []
    for sample in samples:
        b = sample.bounds
        # Chromium owns a dozen slivers that are never drawn (one per display
        # edge, a 1x1 helper). They count towards the area; they are not news.
        if sample.visible_area == 0 and (b.width < 100 or b.height < 100):
            continue
        state = "shown" if sample.visible_area > 0 else "hidden"
        parts.append(
            f"#{sample.window_id} {state} {int(b.width)}x{int(b.height)}"
            f"@{int(b.x)},{int(b.y)} area={int(sample.visible_area)}"
        )
    return " | ".join(parts) or "no browser window of any size"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--interval", type=float, default=0.25, help="seconds between samples")
    parser.add_argument("--duration", type=float, default=0.0, help="stop after N seconds")
    parser.add_argument("--json", dest="json_path", help="write the full trace here")
    args = parser.parse_args()

    started = time.monotonic()
    trace: list[dict[str, Any]] = []
    last = ""
    shown_samples = 0
    total_samples = 0
    print("Watching for the Axcess login-scan browser. Ctrl-C to stop.", flush=True)
    pids: set[int] = set()
    pids_read = float("-inf")
    try:
        while True:
            elapsed = time.monotonic() - started
            if args.duration and elapsed >= args.duration:
                break
            # Listing processes is slow (over a second through PowerShell), and
            # the browser's pid does not change under a running scan.
            if not pids or elapsed - pids_read > 5:
                pids, pids_read = browser_pids(), elapsed
            samples = sample_windows(pids)
            if not samples:
                pids = set()
            area = total_visible_area(samples)
            if samples:
                total_samples += 1
                shown_samples += 1 if area > 0 else 0
            trace.append(
                {
                    "t": round(elapsed, 3),
                    "visible_area": area,
                    "windows": [asdict(sample) for sample in samples],
                }
            )
            line = _describe(samples)
            if line != last:
                print(f"{elapsed:8.2f}s  {line}", flush=True)
                last = line
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    print(
        f"\n{shown_samples} of {total_samples} samples with a browser running "
        "had a window on a display.",
        flush=True,
    )
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(trace, handle, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
