"""Confirmed host-side model downloads for the private llama.cpp service.

Each model is one or two GGUF files pinned in ``catalog.json`` by Hugging
Face repository, commit, size and SHA-256. A file is downloaded over HTTPS
to ``<name>.part`` (resuming a partial file), checked against its pinned
size and SHA-256, and only then renamed into place. The model service never
downloads anything itself: it runs with no network.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import httpx

from audit.ai.catalog import GgufFile, ModelEntry
from audit.ai.runtime import CHUNK, PausedError, RuntimeSetupError, sha256_of


def file_path(models: Path, entry: GgufFile) -> Path:
    """Where a pinned file lives: one folder per repository and commit."""
    owner, name = entry.repo.split("/", 1)
    return models / f"{owner}--{name}" / entry.revision[:12] / entry.file


def _verified_marker(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def file_present(models: Path, entry: GgufFile) -> bool:
    """True when the file is in place with its pinned size and was checked.

    The full SHA-256 is computed once, when the download finishes; the
    marker beside the file records it so a start does not read gigabytes.
    """
    path = file_path(models, entry)
    try:
        return (
            path.is_file()
            and path.stat().st_size == entry.size
            and _verified_marker(path).read_text(encoding="ascii").strip() == entry.sha256
        )
    except OSError:
        return False


def model_present(models: Path, model: ModelEntry) -> bool:
    return all(file_present(models, f) for f in model.files)


def model_remaining(models: Path, model: ModelEntry) -> int:
    """Bytes still to download for ``model``, counting partial files."""
    remaining = 0
    for entry in model.files:
        if file_present(models, entry):
            continue
        part = file_path(models, entry).with_name(entry.file + ".part")
        done = part.stat().st_size if part.exists() else 0
        remaining += max(0, entry.size - min(done, entry.size))
    return remaining


def _https_only(request: httpx.Request) -> None:
    if request.url.scheme != "https":
        raise RuntimeSetupError("AI files can only be downloaded over a secure connection.")


def _download_file(
    http: httpx.Client,
    models: Path,
    entry: GgufFile,
    progress: Callable[[int], None],
    cancel: threading.Event,
) -> None:
    target = file_path(models, entry)
    if file_present(models, entry):
        progress(entry.size)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > entry.size:
        partial.unlink()
        offset = 0
    if offset < entry.size:
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        with http.stream("GET", entry.url, headers=headers) as response:
            if response.status_code == 200 and offset:
                # The server ignored the range; start the file again.
                partial.unlink()
                offset = 0
            elif response.status_code not in (200, 206):
                raise RuntimeSetupError(
                    f"The AI model download failed (HTTP {response.status_code})."
                )
            with partial.open("ab") as fh:
                for chunk in response.iter_bytes(CHUNK):
                    if cancel.is_set():
                        raise PausedError
                    offset += len(chunk)
                    if offset > entry.size:
                        fh.close()
                        partial.unlink(missing_ok=True)
                        raise RuntimeSetupError("The AI model download is larger than expected.")
                    fh.write(chunk)
                    progress(offset)
    if offset != entry.size or sha256_of(partial) != entry.sha256:
        partial.unlink(missing_ok=True)
        raise RuntimeSetupError(
            "The AI model download did not match its published checksum, so it was "
            "deleted. Try again."
        )
    partial.replace(target)
    marker = _verified_marker(target)
    marker.write_text(entry.sha256 + "\n", encoding="ascii")
    progress(entry.size)


def download_model(
    models: Path,
    model: ModelEntry,
    progress: Callable[[int, int], None],
    cancel: threading.Event,
    client: httpx.Client | None = None,
) -> None:
    """Download and check every file of ``model``; resumes partial files."""
    if cancel.is_set():
        raise PausedError
    own = client is None
    http = client or httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(30),
        event_hooks={"request": [_https_only]},
    )
    total = sum(f.size for f in model.files)
    try:
        base = 0
        for entry in model.files:
            if cancel.is_set():
                raise PausedError

            def report(done: int, start: int = base) -> None:
                progress(start + done, total)

            _download_file(http, models, entry, report, cancel)
            base += entry.size
    except httpx.HTTPError as exc:
        raise RuntimeSetupError("The AI model download stopped. Try again.") from exc
    finally:
        if own:
            http.close()
