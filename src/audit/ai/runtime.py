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
import shutil
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

import httpx

from audit.ai.catalog import Catalog, ModelEntry, RuntimeAsset, platform_key
from audit.ai.sandbox import IsolationError, build_sandbox, test_network_boundary
from audit.ai.state import SOCKET_BASE_URL

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


def preset_text(models: Iterable[tuple[ModelEntry, Path, Path | None]], *, gpu: bool) -> str:
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
    lines = [
        "version = 1",
        "",
        "[*]",
        f"c = {CONTEXT_TOKENS}",
        f"n-gpu-layers = {99 if gpu else 0}",
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
    return "\n".join(lines) + "\n"


# Every service process starts from this one long-lived thread. Bubblewrap's
# ``--die-with-parent`` (Linux ``PR_SET_PDEATHSIG``) fires when the *thread*
# that started the process exits, not the program. Started from the setup's
# download thread, the service was killed the moment setup finished (seen
# 2026-11-12). A ThreadPoolExecutor worker stays alive while idle, so the
# service still dies with Axcess, and only with Axcess.
_LAUNCHER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="axcess-ai-launcher")


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
        self.socket_path: str | None = None
        self.accelerator: str | None = None
        self.isolated = False
        self.isolation_reason: str | None = None

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

    def require_isolation(self) -> None:
        """Raise unless this computer can run the service sandboxed."""
        if sys.platform.startswith("win"):
            # The Windows AppContainer launcher is not built yet, and
            # Python on Windows has no UNIX sockets to reach the service.
            raise IsolationError(
                "sandbox_unavailable",
                "This computer cannot isolate the AI service yet. AI was not started. "
                "Saved results still work.",
            )
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
        models = list(models)
        with self._lock:
            if self.running() and self.socket_path:
                return self.socket_path
            try:
                self.require_isolation()
            except IsolationError as exc:
                self.isolation_reason = exc.reason
                raise
            builds = self.builds()
            if not builds:
                raise RuntimeSetupError("The AI program is not installed yet.")
            if not all(self.has_model(m) for m in models):
                raise RuntimeSetupError("The AI models are not downloaded yet.")
            last: RuntimeSetupError | None = None
            for accelerator, server in builds:
                try:
                    return self._start_locked(accelerator, server, models, wait_s)
                except _ModelLoadError as exc:
                    last = RuntimeSetupError(str(exc))
                    continue
            self.isolation_reason = "runtime_failed"
            raise last or RuntimeSetupError("The isolated AI service could not start.")

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
            preset_text(self._model_paths(models), gpu=accelerator != "cpu"), encoding="utf-8"
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
                    )
                ).result()
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
        return self._process is not None and self._process.poll() is None and self.isolated

    def stop(self) -> None:
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
        self.socket_path = None
        self.isolated = False
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        with contextlib.suppress(OSError):
            self._socket().unlink(missing_ok=True)

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
