"""Find, download, start and stop the Ollama program used for AI features.

Only Axcess's checksum-verified private copy is managed here. The model
service runs offline inside an OS sandbox; confirmed downloads are separate.
"""

from __future__ import annotations

import contextlib
import hashlib
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx

from audit.ai.catalog import Catalog, RuntimeAsset, platform_key
from audit.ai.sandbox import IsolationError, build_sandbox, test_network_boundary
from audit.ai.state import SYSTEM_OLLAMA_URL

Progress = Callable[[int, int], None]
CHUNK = 1024 * 1024


class RuntimeSetupError(Exception):
    """A plain-language reason the Ollama program could not be set up."""


class PausedError(Exception):
    """The person paused the download; the partial file is kept."""


def ollama_version(base_url: str, timeout: float = 2.0) -> str | None:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/version", timeout=timeout)
        response.raise_for_status()
        return str(response.json().get("version") or "") or None
    except (httpx.HTTPError, ValueError, AttributeError):
        return None


def system_ollama() -> str | None:
    """The version of an Ollama already running on port 11434, if any."""
    return ollama_version(SYSTEM_OLLAMA_URL)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def _safe_extract_zip(archive: Path, dest: Path) -> None:
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if not target.is_relative_to(root):
                raise RuntimeSetupError("The Ollama download has an unsafe file path.")
        zf.extractall(dest)  # noqa: S202 - every member path checked above


def _extract(archive: Path, dest: Path, name: str) -> None:
    if name.endswith((".tgz", ".tar.gz")):
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest, filter="data")
    elif name.endswith(".zip"):
        _safe_extract_zip(archive, dest)
    elif name.endswith(".tar.zst"):
        # The standard library cannot read zstd; system tar can on Linux.
        if shutil.which("zstd") is None:
            raise RuntimeSetupError(
                "Unpacking Ollama needs the zstd tool. Install it (for example "
                "'sudo apt install zstd'), then try again."
            )
        result = subprocess.run(  # noqa: S603 - fixed argv, checksum-verified archive
            ["tar", "--zstd", "-xf", str(archive), "-C", str(dest), "--no-same-owner"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeSetupError(f"Could not unpack Ollama: {result.stderr.strip()[:300]}")
    else:
        raise RuntimeSetupError(f"Unknown Ollama download type: {name}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


class OllamaRuntime:
    """The private Ollama copy kept in ``ai_dir``."""

    def __init__(self, ai_dir: Path, catalog: Catalog) -> None:
        self.ai_dir = ai_dir
        self.catalog = catalog
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self.base_url: str | None = None
        self.isolated = False
        self.isolation_reason: str | None = None

    @property
    def asset(self) -> RuntimeAsset | None:
        return self.catalog.ollama.assets.get(platform_key())

    @property
    def install_dir(self) -> Path:
        return self.ai_dir / "runtime" / self.catalog.ollama.version

    @property
    def models_dir(self) -> Path:
        return self.ai_dir / "models"

    @property
    def binary(self) -> Path | None:
        asset = self.asset
        return None if asset is None else self.install_dir / asset.binary

    def installed(self) -> bool:
        binary = self.binary
        return binary is not None and binary.is_file()

    def download_remaining(self) -> int:
        """Bytes still to download for the program (0 when it is unpacked)."""
        asset = self.asset
        if asset is None or self.installed():
            return 0
        part = self.ai_dir / "downloads" / f"{asset.name}.part"
        done = part.stat().st_size if part.exists() else 0
        return max(0, asset.size - done)

    def download(
        self,
        progress: Progress,
        cancel: threading.Event,
        client: httpx.Client | None = None,
    ) -> None:
        """Download, check and unpack the pinned release; resumes a partial file."""
        asset = self.asset
        if asset is None:
            raise RuntimeSetupError("Axcess has no Ollama download for this kind of computer.")
        if self.installed():
            return
        downloads = self.ai_dir / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        part = downloads / f"{asset.name}.part"
        done = part.stat().st_size if part.exists() else 0
        if done > asset.size:
            part.unlink()
            done = 0
        own_client = client is None
        http = client or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0))
        try:
            if done < asset.size:
                headers = {"Range": f"bytes={done}-"} if done else {}
                url = self.catalog.ollama.download_url(asset)
                with http.stream("GET", url, headers=headers) as response:
                    if response.status_code == 200 and done:
                        done = 0  # Server ignored the range; start again.
                        part.unlink(missing_ok=True)
                    elif response.status_code not in (200, 206):
                        raise RuntimeSetupError(
                            f"The Ollama download failed (HTTP {response.status_code})."
                        )
                    with part.open("ab") as fh:
                        for chunk in response.iter_bytes(CHUNK):
                            if cancel.is_set():
                                raise PausedError
                            fh.write(chunk)
                            done += len(chunk)
                            progress(done, asset.size)
        except httpx.HTTPError as exc:
            raise RuntimeSetupError(f"The Ollama download stopped: {exc}") from exc
        finally:
            if own_client:
                http.close()
        if sha256_of(part) != asset.sha256:
            part.unlink(missing_ok=True)
            raise RuntimeSetupError(
                "The Ollama download did not match its published checksum, so it was "
                "deleted. Try again."
            )
        staging = self.install_dir.with_name(self.install_dir.name + ".unpacking")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        _extract(part, staging, asset.name)
        shutil.rmtree(self.install_dir, ignore_errors=True)
        staging.rename(self.install_dir)
        binary = self.binary
        if binary is not None and binary.exists() and not sys.platform.startswith("win"):
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        part.unlink(missing_ok=True)

    def require_isolation(self) -> None:
        build_sandbox(self.install_dir, self.models_dir, self.ai_dir / "scratch")
        if sys.platform.startswith("linux"):
            raise IsolationError(
                "namespace_unreachable",
                "Axcess cannot reach the AI service inside its private network on this computer. "
                "AI was not started.",
            )

    def start(self, preferred_url: str | None = None, wait_s: float = 30.0) -> str:
        """Run the private Ollama on 127.0.0.1 and return its address."""
        with self._lock:
            if self._process is not None and self._process.poll() is None and self.base_url:
                return self.base_url
            try:
                self.require_isolation()
            except IsolationError as exc:
                self.isolation_reason = exc.reason
                raise
            binary = self.binary
            if binary is None or not binary.is_file():
                raise RuntimeSetupError("The Ollama program is not installed yet.")
            port = _free_port()
            if preferred_url:
                with contextlib.suppress(ValueError):
                    old = int(preferred_url.rsplit(":", 1)[1])
                    if _port_free(old):
                        port = old
            self.models_dir.mkdir(parents=True, exist_ok=True)
            scratch = self.ai_dir / "scratch"
            scratch.mkdir(parents=True, exist_ok=True)
            try:
                sandbox = build_sandbox(self.install_dir, self.models_dir, scratch)
                test_network_boundary(sandbox)
            except IsolationError as exc:
                self.isolated = False
                self.isolation_reason = exc.reason
                raise
            env = {
                "PATH": str(self.install_dir.resolve()),
                "HOME": str(scratch.resolve()),
                "TMPDIR": str(scratch.resolve()),
                "OLLAMA_HOST": f"127.0.0.1:{port}",
                "OLLAMA_MODELS": str(self.models_dir.resolve()),
                "OLLAMA_NOPRUNE": "1",
                "OLLAMA_NO_CLOUD": "1",
            }
            log_path = self.ai_dir / "ollama.log"
            with log_path.open("ab") as log:
                try:
                    self._process = subprocess.Popen(  # noqa: S603 - checksum-verified binary in OS sandbox
                        sandbox.command([str(binary.resolve()), "serve"]),
                        cwd=str(self.install_dir),
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                    )
                except OSError as exc:
                    self.isolation_reason = "runtime_failed"
                    raise RuntimeSetupError("The isolated AI service could not start.") from exc
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + wait_s
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    self._stop_locked()
                    self.isolation_reason = "runtime_failed"
                    raise RuntimeSetupError(
                        "The isolated AI service could not start. Check the application log."
                    )
                if ollama_version(url, timeout=1.0):
                    self.base_url = url
                    self.isolated = True
                    self.isolation_reason = None
                    return url
                time.sleep(0.25)
            self._stop_locked()
            self.isolation_reason = "runtime_failed"
            raise RuntimeSetupError("The isolated AI service did not start in time.")

    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None and self.isolated

    def has_model(self, tag: str) -> bool:
        from audit.ai.downloader import model_present

        return model_present(self.models_dir, tag)

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        process, self._process = self._process, None
        self.base_url = None
        self.isolated = False
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def remove(self) -> None:
        """Stop the private copy and delete the program, models and downloads."""
        self.stop()
        for name in ("runtime", "models", "downloads"):
            shutil.rmtree(self.ai_dir / name, ignore_errors=True)
