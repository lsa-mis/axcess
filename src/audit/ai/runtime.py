"""Find, download, start and stop the private llama.cpp model service.

The desktop app ships a pinned ``llama-server`` build beside the backend
(``AUDIT_LLAMA_SERVER_DIR``, laid out by ``desktop/scripts/bundle-llama-server.py``).
A copy run from source downloads the same pinned build once, checked
against its SHA-256 in ``catalog.json``. Model files come from
``audit.ai.downloader``.

One ``llama-server`` runs in router mode inside the OS sandbox, listening
only on a UNIX socket in the sandbox's scratch folder. A preset file names
the two models of the chosen size under their catalog tags, so the rest of
Axcess asks for the same model names it uses with Ollama. The router loads
each model in its own child process. Inside the Linux sandbox there is no
network at all except a private loopback, where the router reaches its
children; nothing outside the sandbox can reach that loopback.

Why one router and not one process per model: one socket and one address
for the whole app, so the scan, fix-suggestion and readiness code keep one
model endpoint, as they have with Ollama. The router's children use
loopback TCP, which a Windows AppContainer blocks; Windows will need one
process per model (``docs/internal/llama-cpp-plan.md``).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict

import httpx

from audit.ai import hardware
from audit.ai.catalog import Catalog, ModelEntry, RuntimeAsset, platform_key
from audit.ai.sandbox import IsolationError, build_sandbox, test_network_boundary
from audit.ai.state import SOCKET_BASE_URL
from audit.ai.windows_launcher import (
    LAUNCHER_NAME,
    LauncherModelError,
    LauncherService,
    ModelProcess,
    note,
    private_copy,
    require_windows_sandbox,
    run_check,
    run_devices,
    with_launcher,
)

Progress = Callable[[int, int], None]
CHUNK = 1024 * 1024
# The context every model starts with. Fix suggestions ask for 8192 tokens;
# llama.cpp sets the context when a model loads, not per request.
CONTEXT_TOKENS = 8192
SOCKET_NAME = "llama.sock"
# AF_UNIX paths are limited to 108 bytes on Linux and 104 on macOS,
# including the final NUL byte.
MAX_SOCKET_PATH = 103
SERVER_NAMES = ("llama-server", "llama-server.exe")


class RuntimeSetupError(Exception):
    """A plain-language reason the AI service could not be set up."""


class NotEnoughMemoryError(RuntimeSetupError):
    """A size for 16 GB or more on a computer with 8 GB or less; nothing started."""


# Memory a running model needs beyond its file: the 8,192-token context
# (its KV cache) and compute buffers. About 1-2.5 GB for the catalogue's
# models by their published shapes; 1.5 GB per model plus a 1 GB margin.
# Since 2026-11-18 this only decides whether to warn that memory is low;
# it no longer stops a start (see LlamaRuntime._note_memory).
WORKING_BYTES_PER_MODEL = 1_500_000_000
MEMORY_MARGIN_BYTES = 1_000_000_000
# How long a start waits for memory to come back before it warns.
MEMORY_SETTLE_S = 10.0
# The service's process group, kept so a later start can end what an
# earlier run left behind (a crash, a killed app).
GROUP_FILE = "service.group"


def memory_needed(models: Iterable[ModelEntry], *, gpu_memory: int = 0) -> int:
    """Free memory the service needs to start ``models`` without swapping.

    A separate graphics card holds as much of the model files as fits in
    its own memory (``gpu_memory``, llama.cpp's ``--fit``); the rest is in
    the computer's memory. Apple chips and built-in graphics share the
    computer's memory, so for them ``gpu_memory`` is 0.
    """
    models = list(models)
    files = max(0, sum(m.size for m in models) - gpu_memory)
    return files + WORKING_BYTES_PER_MODEL * len(models) + MEMORY_MARGIN_BYTES


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _end_group(pgid: int, process: subprocess.Popen[bytes] | None = None) -> None:
    """End a process group: politely, then for sure.

    The group holds the service and every per-model server it started, so
    none of them keeps a model in memory after a stop.
    """
    for sig, wait_s in ((signal.SIGTERM, 10.0), (signal.SIGKILL, 5.0)):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, sig)
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if process is not None:
                process.poll()
            if not _group_alive(pgid):
                return
            time.sleep(0.1)


def _group_runs_llama(pgid: int) -> bool:
    """True when a process in group ``pgid`` is a llama-server (POSIX ``ps``)."""
    try:
        out = subprocess.run(
            ["ps", "-axo", "pgid=,comm="],  # noqa: S607 - system tool, fixed argv
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    for line in out.splitlines():
        group, _, command = line.strip().partition(" ")
        if group == str(pgid) and "llama-server" in command:
            return True
    return False


class PausedError(Exception):
    """The person paused the download; the partial file is kept."""


def _safe_extract_zip(archive: Path, dest: Path) -> None:
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if not target.is_relative_to(root):
                raise RuntimeSetupError("The AI program download has an unsafe file path.")
        zf.extractall(dest)  # noqa: S202 - every member path checked above


def extract(archive: Path, dest: Path, name: str) -> None:
    if name.endswith((".tgz", ".tar.gz")):
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest, filter="data")
    elif name.endswith(".zip"):
        _safe_extract_zip(archive, dest)
    else:
        raise RuntimeSetupError(f"Unknown AI program download type: {name}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def find_server(folder: Path) -> Path | None:
    """The ``llama-server`` executable anywhere under ``folder``.

    Release archives differ: the Linux and macOS ones unpack into a
    ``llama-<build>`` folder, the Windows ones into the archive's root.
    """
    if not folder.is_dir():
        return None
    for name in SERVER_NAMES:
        for candidate in sorted(folder.rglob(name)):
            if candidate.is_file():
                return candidate
    return None


def gpu_layers(*, gpu: bool, gpu_only: bool) -> str | None:
    """llama-server's ``--n-gpu-layers`` for this start, or None to leave it unset.

    Unset on a graphics build, so llama.cpp's ``--fit`` (on by default in
    b12284) puts as many layers on the graphics card as fit, keeping 1 GB
    spare, and the rest in the computer's memory. It used to be 99 (every
    layer): a model bigger than the card then failed to load on it and ran
    on the processor alone (developer, 2026-11-19). "Run AI on the graphics
    card only" sets ``all``: faster when it fits, and no start otherwise.
    The processor build keeps 0.
    """
    if not gpu:
        return "0"
    return "all" if gpu_only else None


def preset_text(
    models: Iterable[tuple[ModelEntry, Path, Path | None]], *, gpu: bool, gpu_only: bool = False
) -> str:
    """The router's model preset: one section per model, named ``served_name``.

    Keys are llama-server options without their dashes (server README,
    "Model presets"). ``reasoning = off`` keeps thinking models from
    spending minutes on hidden reasoning. ``reasoning-format = none`` makes
    the JSON schema bind from the first word: with reasoning extraction on,
    Qwen3-4B-Instruct-2507 wrote a sentence of preamble before its JSON
    (filed as ``reasoning_content``), which used up short answer budgets
    and left the answer empty (b12284, 2026-11-12); with it off the answer
    was clean JSON, the same as without a schema. ``load-on-startup``
    loads both models when the service starts, so the first answer does
    not wait.
    """
    layers = gpu_layers(gpu=gpu, gpu_only=gpu_only)
    lines = [
        "version = 1",
        "",
        "[*]",
        f"c = {CONTEXT_TOKENS}",
        *([f"n-gpu-layers = {layers}"] if layers is not None else []),
        "reasoning = off",
        "reasoning-format = none",
        "load-on-startup = true",
    ]
    for entry, model, mmproj in models:
        if any(ch in entry.served_name for ch in "[]\n\r=;:"):
            raise RuntimeSetupError("An AI model name in the catalog is not usable.")
        lines += ["", f"[{entry.served_name}]", f"model = {model}"]
        if mmproj is not None:
            lines.append(f"mmproj = {mmproj}")
        for key, value in sorted((entry.sampling or {}).items()):
            lines.append(f"{key} = {value:g}")
    return "\n".join(lines) + "\n"


# Every service process starts from this one long-lived thread. Bubblewrap's
# ``--die-with-parent`` (Linux ``PR_SET_PDEATHSIG``) fires when the *thread*
# that started the process exits, not the program. Started from the setup's
# download thread, the service was killed the moment setup finished (seen
# 2026-11-12). A ThreadPoolExecutor worker stays alive while idle, so the
# service still dies with Axcess, and only with Axcess.
_LAUNCHER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="axcess-ai-launcher")


class ServiceFields(TypedDict):
    socket_path: str | None
    routes: dict[str, str] | None


class LlamaRuntime:
    """The private llama.cpp service kept in ``ai_dir``."""

    def __init__(
        self,
        ai_dir: Path,
        catalog: Catalog,
        *,
        bundled_dir: Path | None = None,
    ) -> None:
        self.ai_dir = ai_dir
        self.catalog = catalog
        self.bundled_dir = bundled_dir
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        # Set by stop() so a start still waiting for models gives up at once.
        self._abort = threading.Event()
        # True while a start loads its models (the app starts the service in
        # the background at launch), so the interface can say "starting".
        self.starting = False
        self.socket_path: str | None = None
        # Windows: model name -> the launcher's port for that model.
        self.routes: dict[str, str] | None = None
        self._windows: LauncherService | None = None
        self.accelerator: str | None = None
        self.isolated = False
        self.isolation_reason: str | None = None
        # Said while the service runs, when it started with little free memory.
        self.memory_warning: str | None = None
        # "Run AI on the graphics card only" (AIPreferences.gpu_only), set by
        # the manager before each start.
        self.gpu_only = False
        # Graphics devices, read once per program (``devices``).
        self._devices: tuple[Path, list[hardware.GpuDevice]] | None = None

    # -- the program -------------------------------------------------------

    @property
    def assets(self) -> tuple[RuntimeAsset, ...]:
        return self.catalog.llama_cpp.assets.get(platform_key(), ())

    @property
    def asset(self) -> RuntimeAsset | None:
        """The build this computer can use, or None (kept for the setup page)."""
        if self.bundled():
            return (
                self.assets[0]
                if self.assets
                else RuntimeAsset(name="bundled", size=0, sha256="0" * 64, accelerator="cpu")
            )
        return self.assets[0] if self.assets else None

    @property
    def download_dir(self) -> Path:
        return self.ai_dir / "runtime" / f"llama-{self.catalog.llama_cpp.version}"

    @property
    def models_dir(self) -> Path:
        return self.ai_dir / "gguf"

    @property
    def scratch(self) -> Path:
        return self.ai_dir / "scratch"

    def bundled(self) -> bool:
        return self.bundled_dir is not None and any(
            find_server(self.bundled_dir / a.accelerator) for a in self.assets
        )

    def builds(self) -> list[tuple[str, Path]]:
        """Installed builds to try, GPU first: (accelerator, executable)."""
        root = self.bundled_dir if self.bundled() else self.download_dir
        found: list[tuple[str, Path]] = []
        for asset in self.assets:
            server = find_server(root / asset.accelerator) if root else None
            if server is not None:
                found.append((asset.accelerator, server))
        return found

    def installed(self) -> bool:
        if not self.assets:
            return False
        if self.bundled():
            return True
        return all(find_server(self.download_dir / a.accelerator) for a in self.assets)

    def download_remaining(self) -> int:
        """Bytes still to download for the program (0 when it is ready)."""
        if self.installed():
            return 0
        remaining = 0
        for asset in self.assets:
            if find_server(self.download_dir / asset.accelerator):
                continue
            part = self.ai_dir / "downloads" / f"{asset.name}.part"
            done = part.stat().st_size if part.exists() else 0
            remaining += max(0, asset.size - min(done, asset.size))
        return remaining

    def download(
        self,
        progress: Progress,
        cancel: threading.Event,
        client: httpx.Client | None = None,
    ) -> None:
        """Download, check and unpack the pinned builds; resumes partial files."""
        if not self.assets:
            raise RuntimeSetupError("Axcess has no AI program for this kind of computer.")
        if self.installed():
            return
        own_client = client is None
        http = client or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0))
        total = sum(a.size for a in self.assets)
        base = 0
        try:
            for asset in self.assets:
                if not find_server(self.download_dir / asset.accelerator):

                    def report(done: int, _total: int, start: int = base) -> None:
                        progress(start + done, total)

                    self._download_asset(http, asset, report, cancel)
                base += asset.size
                progress(base, total)
        finally:
            if own_client:
                http.close()

    def _download_asset(
        self,
        http: httpx.Client,
        asset: RuntimeAsset,
        progress: Progress,
        cancel: threading.Event,
    ) -> None:
        downloads = self.ai_dir / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        part = downloads / f"{asset.name}.part"
        done = part.stat().st_size if part.exists() else 0
        if done > asset.size:
            part.unlink()
            done = 0
        try:
            if done < asset.size:
                headers = {"Range": f"bytes={done}-"} if done else {}
                url = self.catalog.llama_cpp.download_url(asset)
                with http.stream("GET", url, headers=headers) as response:
                    if response.status_code == 200 and done:
                        done = 0  # Server ignored the range; start again.
                        part.unlink(missing_ok=True)
                    elif response.status_code not in (200, 206):
                        raise RuntimeSetupError(
                            f"The AI program download failed (HTTP {response.status_code})."
                        )
                    with part.open("ab") as fh:
                        for chunk in response.iter_bytes(CHUNK):
                            if cancel.is_set():
                                raise PausedError
                            fh.write(chunk)
                            done += len(chunk)
                            progress(done, asset.size)
        except httpx.HTTPError as exc:
            raise RuntimeSetupError(f"The AI program download stopped: {exc}") from exc
        if sha256_of(part) != asset.sha256:
            part.unlink(missing_ok=True)
            raise RuntimeSetupError(
                "The AI program download did not match its published checksum, so it was "
                "deleted. Try again."
            )
        dest = self.download_dir / asset.accelerator
        staging = dest.with_name(dest.name + ".unpacking")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        extract(part, staging, asset.name)
        server = find_server(staging)
        if server is None:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeSetupError("The AI program download has no llama-server in it.")
        if not sys.platform.startswith("win"):
            server.chmod(server.stat().st_mode | stat.S_IXUSR)
        shutil.rmtree(dest, ignore_errors=True)
        staging.rename(dest)
        part.unlink(missing_ok=True)

    # -- models ------------------------------------------------------------

    def devices(self) -> list[hardware.GpuDevice]:
        """The graphics devices the graphics build can use; [] when unknown.

        Runs ``llama-server -v --list-devices`` once per program, inside
        the same sandbox as the service, with no model and no network:
        Bubblewrap on Linux, the launcher's AppContainer on Windows (its
        ``devices`` command). Not on macOS, where the Apple chip shares the
        computer's memory and adds nothing.
        """
        windows = sys.platform.startswith("win")
        if not (windows or sys.platform.startswith("linux")):
            return []
        gpu_builds = [(a, s) for a, s in self.builds() if a != "cpu"]
        if not gpu_builds:
            return []
        accelerator, server = gpu_builds[0][0], gpu_builds[0][1].resolve()
        if self._devices is not None and self._devices[0] == server:
            return self._devices[1]
        found: list[hardware.GpuDevice] = []
        if windows:
            found = self._windows_devices(accelerator, server)
            self._devices = (server, found)
            return found
        try:
            self.models_dir.mkdir(parents=True, exist_ok=True)
            self.scratch.mkdir(parents=True, exist_ok=True)
            program_root = server.parent
            sandbox = build_sandbox(program_root, self.models_dir, self.scratch, gpu=True)
            scratch = str(self.scratch.resolve())
            result = subprocess.run(  # noqa: S603 - pinned binary in OS sandbox
                sandbox.command([str(server), "-v", "--list-devices"]),
                cwd=scratch,
                env={
                    "PATH": str(program_root),
                    "HOME": scratch,
                    "TMPDIR": scratch,
                    "LD_LIBRARY_PATH": str(program_root),
                },
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                stdin=subprocess.DEVNULL,
            )
            found = hardware.parse_devices(result.stdout + "\n" + result.stderr)
        except (OSError, subprocess.SubprocessError, IsolationError):
            logging.getLogger(__name__).warning("ai.list_devices_failed", exc_info=True)
        self._devices = (server, found)
        return found

    def _windows_devices(self, accelerator: str, server: Path) -> list[hardware.GpuDevice]:
        """``devices`` through the launcher, in the service's AppContainer."""
        launcher = self._launcher()
        try:
            require_windows_sandbox(launcher)
            if launcher is None:  # pragma: no cover - require_windows_sandbox raised
                return []
            self.scratch.mkdir(parents=True, exist_ok=True)
            program = server.parent
            # The launcher changes the folder's access list, which it cannot
            # do under Program Files: the same private copy a start uses.
            if not program.is_relative_to(self.ai_dir.resolve()):
                program = private_copy(program, self.download_dir / accelerator).resolve()
            scratch = self.scratch.resolve()
            output = run_devices(launcher, program, scratch, scratch / "devices.txt")
        except (OSError, subprocess.SubprocessError, IsolationError):
            logging.getLogger(__name__).warning("ai.list_devices_failed", exc_info=True)
            return []
        return hardware.parse_devices(output)

    def separate_gpu_memory(self) -> int:
        """Memory on separate graphics cards, in bytes; 0 for none or unknown."""
        return sum(d.total_bytes for d in self.devices() if not d.shared)

    def has_model(self, model: ModelEntry) -> bool:
        from audit.ai.downloader import model_present

        return model_present(self.models_dir, model)

    def _model_paths(
        self, models: Iterable[ModelEntry]
    ) -> list[tuple[ModelEntry, Path, Path | None]]:
        from audit.ai.downloader import file_path

        out = []
        for entry in models:
            model = file_path(self.models_dir, entry.gguf).resolve()
            mmproj = file_path(self.models_dir, entry.mmproj).resolve() if entry.mmproj else None
            out.append((entry, model, mmproj))
        return out

    # -- isolation and the service ----------------------------------------

    def _socket(self) -> Path:
        return (self.scratch / SOCKET_NAME).resolve()

    def _launcher(self) -> Path | None:
        return self.bundled_dir / LAUNCHER_NAME if self.bundled_dir else None

    def service_fields(self) -> ServiceFields:
        """Where the running service is, for the saved setup."""
        return {"socket_path": self.socket_path, "routes": self.routes}

    def require_isolation(self) -> None:
        """Raise unless this computer can run the service sandboxed."""
        if sys.platform.startswith("win"):
            require_windows_sandbox(self._launcher())
            return
        root = self.bundled_dir if self.bundled() else self.download_dir
        build_sandbox(root or self.download_dir, self.models_dir, self.scratch)
        if len(str(self._socket()).encode()) > MAX_SOCKET_PATH:
            raise IsolationError(
                "sandbox_unavailable",
                "The Axcess data folder path is too long for the AI service's private "
                "connection. AI was not started.",
            )

    def start(
        self,
        models: Iterable[ModelEntry],
        *,
        wait_s: float = 180.0,
    ) -> str:
        """Run the service sandboxed with ``models`` and return its socket path.

        Tries the GPU build first. If a model cannot load with it (for
        example no Vulkan driver), stops it and uses the CPU build.
        """
        # Each model once: one model can do both jobs (the Small size).
        models = list({m.served_name: m for m in models}.values())
        self.starting = True
        try:
            return self._start(models, wait_s)
        finally:
            self.starting = False

    def _start(self, models: list[ModelEntry], wait_s: float) -> str:
        with self._lock:
            if self.running() and (self.socket_path or self.routes):
                return self.socket_path or json.dumps(self.routes, sort_keys=True)
            try:
                self.require_isolation()
            except IsolationError as exc:
                self.isolation_reason = exc.reason
                raise
            builds = self.builds()
            if self.gpu_only:
                # No processor build to fall back to: "only" means only.
                builds = [(a, s) for a, s in builds if a != "cpu"]
            if not builds:
                if self.gpu_only and self.builds():
                    self.isolation_reason = "gpu_only_failed"
                    raise RuntimeSetupError("AI could not start on the graphics card alone.")
                raise RuntimeSetupError("The AI program is not installed yet.")
            if not all(self.has_model(m) for m in models):
                raise RuntimeSetupError("The AI models are not downloaded yet.")
            self._end_leftovers()
            self._note_memory(models)
            last: RuntimeSetupError | None = None
            start = (
                self._start_windows_locked if sys.platform.startswith("win") else self._start_locked
            )
            for accelerator, server in builds:
                try:
                    return start(accelerator, server, models, wait_s)
                except _ModelLoadError as exc:
                    last = RuntimeSetupError(str(exc))
                    continue
            self.isolation_reason = "gpu_only_failed" if self.gpu_only else "runtime_failed"
            raise last or RuntimeSetupError("The isolated AI service could not start.")

    def _start_windows_locked(
        self, accelerator: str, server: Path, models: list[ModelEntry], wait_s: float
    ) -> str:
        """Windows: one server per model, each in the launcher's AppContainer."""
        launcher = self._launcher()
        require_windows_sandbox(launcher)
        if launcher is None:  # pragma: no cover - require_windows_sandbox raised
            raise RuntimeSetupError("The isolated AI service could not start.")
        gpu = accelerator != "cpu"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.scratch.mkdir(parents=True, exist_ok=True)
        program = server.parent.resolve()
        if not program.is_relative_to(self.ai_dir.resolve()):
            program = private_copy(program, self.download_dir / accelerator).resolve()
        # The check runs a copy of the launcher inside the sandbox, which
        # may run programs only from the folder it is given.
        launcher = with_launcher(program, launcher)
        log = (self.ai_dir / "llama-server.log").resolve()
        scratch = self.scratch.resolve()
        models_dir = self.models_dir.resolve()
        try:
            run_check(launcher, program, models_dir, scratch, log, gpu=gpu)
        except IsolationError as exc:
            self.isolated = False
            self.isolation_reason = exc.reason
            raise
        processes = []
        for index, (entry, model, mmproj) in enumerate(self._model_paths(models)):
            sock = scratch / f"m{index}.sock"
            sock.unlink(missing_ok=True)
            argv = [str(program / "llama-server.exe"), "-m", str(model)]
            if mmproj is not None:
                argv += ["--mmproj", str(mmproj)]
            argv += [
                "--alias",
                entry.served_name,
                "-c",
                str(CONTEXT_TOKENS),
                "--reasoning",
                "off",
                "--reasoning-format",
                "none",
                "--host",
                str(sock),
                "--no-webui",
                "--offline",
            ]
            layers = gpu_layers(gpu=gpu, gpu_only=self.gpu_only)
            if layers is not None:
                argv += ["-ngl", layers]
            for key, value in sorted((entry.sampling or {}).items()):
                argv += [f"--{key}", f"{value:g}"]
            processes.append(ModelProcess(entry.served_name, sock, argv))
        service = LauncherService(launcher)
        self._windows = service
        try:
            routes = _LAUNCHER.submit(
                lambda: service.start(processes, program, models_dir, scratch, log, gpu=gpu)
            ).result()
            service.wait_ready(self._abort, wait_s)
        except LauncherModelError as exc:
            self._stop_locked()
            note(log, f"a model's server stopped while loading ({exc}); trying the next build")
            raise _ModelLoadError(
                "The AI service could not load its models with this computer's graphics driver."
            ) from exc
        except IsolationError as exc:
            self._stop_locked()
            note(log, f"start failed: {exc}")
            self.isolation_reason = exc.reason
            raise RuntimeSetupError(str(exc)) from exc
        note(log, f"started; every model answered (process {os.getpid()})")
        self.routes = routes
        self.socket_path = None
        self.accelerator = accelerator
        self.isolated = True
        self.isolation_reason = None
        return json.dumps(routes, sort_keys=True)

    def _start_locked(
        self, accelerator: str, server: Path, models: list[ModelEntry], wait_s: float
    ) -> str:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.scratch.mkdir(parents=True, exist_ok=True)
        program_root = server.parent.resolve()
        try:
            sandbox = build_sandbox(
                program_root, self.models_dir, self.scratch, gpu=accelerator != "cpu"
            )
            test_network_boundary(sandbox)
        except IsolationError as exc:
            self.isolated = False
            self.isolation_reason = exc.reason
            raise
        sock = self._socket()
        sock.unlink(missing_ok=True)
        preset = (self.scratch / "models.ini").resolve()
        preset.write_text(
            preset_text(
                self._model_paths(models), gpu=accelerator != "cpu", gpu_only=self.gpu_only
            ),
            encoding="utf-8",
        )
        scratch = str(self.scratch.resolve())
        env = {
            "PATH": str(program_root),
            "HOME": scratch,
            "TMPDIR": scratch,
            "LLAMA_CACHE": str(self.scratch.resolve() / "cache"),
            # The release's shared libraries sit beside the executable.
            "LD_LIBRARY_PATH": str(program_root),
        }
        argv = [
            str(server.resolve()),
            "--models-preset",
            str(preset),
            "--models-max",
            str(len(models)),
            "--host",
            str(sock),
            "--no-webui",
            "--offline",
        ]
        log_path = self.ai_dir / "llama-server.log"
        with log_path.open("ab") as log:
            log.write(f"\n--- starting {accelerator} build {time.ctime()} ---\n".encode())
            log.flush()
            try:
                command = sandbox.command(argv)
                self._process = _LAUNCHER.submit(
                    lambda: subprocess.Popen(  # noqa: S603 - pinned binary in OS sandbox
                        command,
                        cwd=scratch,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        # Its own process group, which a stop ends whole.
                        start_new_session=True,
                    )
                ).result()
                (self.scratch / GROUP_FILE).write_text(str(self._process.pid), encoding="ascii")
            except OSError as exc:
                self.isolation_reason = "runtime_failed"
                raise RuntimeSetupError("The isolated AI service could not start.") from exc
        try:
            self._wait_ready(sock, [m.served_name for m in models], wait_s)
        except _ModelLoadError:
            self._stop_locked()
            raise
        except RuntimeSetupError:
            self._stop_locked()
            self.isolation_reason = "runtime_failed"
            raise
        self.socket_path = str(sock)
        self.accelerator = accelerator
        self.isolated = True
        self.isolation_reason = None
        return self.socket_path

    def _wait_ready(self, sock: Path, tags: list[str], wait_s: float) -> None:
        deadline = time.monotonic() + wait_s
        transport = httpx.HTTPTransport(uds=str(sock))
        with httpx.Client(transport=transport, base_url=SOCKET_BASE_URL, timeout=2.0) as http:
            while time.monotonic() < deadline:
                if self._abort.is_set():
                    raise RuntimeSetupError("The AI service was stopped while it was starting.")
                process = self._process
                if process is None or process.poll() is not None:
                    raise RuntimeSetupError(
                        "The isolated AI service stopped while starting. Check the application log."
                    )
                if not tags:
                    # No models to wait for: the router's own health is enough.
                    if sock.exists() and _healthy(http):
                        return
                    time.sleep(0.25)
                    continue
                states = _model_states(http) if sock.exists() else {}
                failed = [t for t in tags if states.get(t) == "failed"]
                if failed:
                    raise _ModelLoadError(
                        "The AI service could not load its models with this computer's "
                        "graphics driver."
                    )
                if states and all(states.get(t) == "loaded" for t in tags):
                    return
                time.sleep(0.5)
        raise RuntimeSetupError("The isolated AI service did not start in time.")

    def running(self) -> bool:
        if self._windows is not None:
            return self._windows.running() and self.isolated
        return self._process is not None and self._process.poll() is None and self.isolated

    def stop(self) -> None:
        self.memory_warning = None
        self._abort.set()
        with self._lock:
            try:
                self._stop_locked()
            finally:
                # Inside the lock: a start waiting for the lock must not
                # see this stop's abort once the stop has finished.
                self._abort.clear()

    def _stop_locked(self) -> None:
        process, self._process = self._process, None
        windows, self._windows = self._windows, None
        self.socket_path = None
        self.routes = None
        self.isolated = False
        if windows is not None:
            windows.stop()
        if process is not None:
            # The whole group, even when its first process already ended:
            # the per-model servers can outlive it.
            _end_group(process.pid, process)
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=5)
            with contextlib.suppress(OSError):
                (self.scratch / GROUP_FILE).unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            self._socket().unlink(missing_ok=True)

    def _end_leftovers(self) -> None:
        """End a service an earlier run of Axcess left running.

        A crash or a killed app skips the stop. The group it ran in is kept
        in scratch; if a llama-server still runs in that group, it is ended
        before a new service starts, so two never hold models at once.
        Windows ends the job's processes itself when the launcher exits.
        """
        if sys.platform.startswith("win") or self._process is not None:
            return
        marker = self.scratch / GROUP_FILE
        try:
            pgid = int(marker.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return
        if pgid > 1 and _group_alive(pgid) and _group_runs_llama(pgid):
            note(self.ai_dir / "llama-server.log", f"ending a service left running (group {pgid})")
            _end_group(pgid)
        with contextlib.suppress(OSError):
            marker.unlink(missing_ok=True)

    def _note_memory(self, models: list[ModelEntry]) -> None:
        """Warn, without stopping the start, when free memory looks too low.

        This used to refuse the start (2026-11-17). On an 8 GB MacBook Air it
        refused even Small, though macOS makes room by compressing other
        programs' memory. The developer chose, on 2026-11-18, to warn and let
        the operating system manage memory. The one refusal left is a size
        for 16 GB or more on a computer with 8 GB or less
        (AIManager._require_size_fits, hardware.size_refused).
        """
        need = memory_needed(models, gpu_memory=self.separate_gpu_memory())
        # Memory a model just stopped holds comes back over a few seconds
        # (integrated graphics frees its part late), so a switch measured at
        # once would warn with room to spare (end-to-end test, 2026-11-17).
        deadline = time.monotonic() + MEMORY_SETTLE_S
        while True:
            free = hardware.available_memory_bytes()
            if free is None or free >= need:
                self.memory_warning = None
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(0.5)
        note(
            self.ai_dir / "llama-server.log",
            f"starting with little memory: the models need about {need / 1e9:.1f} GB of "
            f"free memory, {free / 1e9:.1f} GB is free",
        )
        self.memory_warning = (
            f"Memory was low when AI started: the models need about {need / 1e9:.1f} GB, "
            f"and {free / 1e9:.1f} GB was free. AI may answer slowly. Closing other "
            "programs helps."
        )

    def remove(self) -> None:
        """Stop the service and delete the downloaded program and models.

        Also removes the private Ollama files that versions before
        llama.cpp kept here (``models`` and ``runtime``).
        """
        self.stop()
        for name in ("runtime", "models", "gguf", "downloads", "scratch"):
            shutil.rmtree(self.ai_dir / name, ignore_errors=True)

    def remove_legacy_ollama(self) -> None:
        """Delete the private Ollama program and models older versions kept.

        Only Axcess's own copies inside its data folder; an Ollama the
        person installed is never touched.
        """
        shutil.rmtree(self.ai_dir / "models", ignore_errors=True)
        runtime = self.ai_dir / "runtime"
        if runtime.is_dir():
            for child in runtime.iterdir():
                if child.is_dir() and not child.name.startswith("llama-"):
                    shutil.rmtree(child, ignore_errors=True)
        with contextlib.suppress(OSError):
            (self.ai_dir / "ollama.log").unlink(missing_ok=True)


class _ModelLoadError(RuntimeSetupError):
    """A model could not load with this build; another build may work."""


def _healthy(http: httpx.Client) -> bool:
    try:
        return http.get("/health").status_code == 200
    except httpx.HTTPError:
        return False


def _model_states(http: httpx.Client) -> dict[str, str]:
    """Each preset model's state from the router's ``GET /models``.

    "loaded", "loading", "unloaded", or "failed" for an unloaded model
    whose status says ``"failed": true`` (server README, "GET /models").
    """
    try:
        response = http.get("/models")
        if response.status_code != 200:
            return {}
        data = response.json().get("data", [])
    except (httpx.HTTPError, ValueError, AttributeError):
        return {}
    states: dict[str, str] = {}
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        status = entry.get("status")
        if not isinstance(status, dict):
            continue
        value = str(status.get("value", ""))
        states[entry["id"]] = "failed" if status.get("failed") else value
    return states


__all__ = [
    "CONTEXT_TOKENS",
    "SOCKET_BASE_URL",
    "LlamaRuntime",
    "PausedError",
    "RuntimeSetupError",
    "find_server",
    "preset_text",
    "sha256_of",
]
