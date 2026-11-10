"""Confirmed host-side registry downloads. Never call Ollama's pull API."""

from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Callable
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from audit.ai.runtime import CHUNK, PausedError, RuntimeSetupError, sha256_of

REGISTRY = "https://registry.ollama.ai"
_DIGEST = re.compile(r"sha256:[a-f0-9]{64}\Z")


class Descriptor(BaseModel):
    digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    size: int = Field(ge=0, le=100_000_000_000)


class Manifest(BaseModel):
    schema_version: int = Field(alias="schemaVersion")
    config: Descriptor
    layers: list[Descriptor] = Field(max_length=100)


def model_path(models: Path, tag: str) -> tuple[Path, str, str]:
    match = re.fullmatch(r"([a-zA-Z0-9][a-zA-Z0-9_.-]*):([a-zA-Z0-9][a-zA-Z0-9_.-]*)", tag)
    if match is None:
        raise RuntimeSetupError("The AI model name is not supported by the private downloader.")
    name, version = match.groups()
    return models / "manifests" / "registry.ollama.ai" / "library" / name / version, name, version


def model_present(models: Path, tag: str) -> bool:
    try:
        path, _, _ = model_path(models, tag)
        manifest = Manifest.model_validate_json(path.read_bytes())
        return all(
            (models / "blobs" / d.digest.replace(":", "-")).is_file()
            and (models / "blobs" / d.digest.replace(":", "-")).stat().st_size == d.size
            for d in [manifest.config, *manifest.layers]
        )
    except (OSError, ValueError, RuntimeSetupError):
        return False


def download_model(
    models: Path,
    tag: str,
    progress: Callable[[int, int], None],
    cancel: threading.Event,
    client: httpx.Client | None = None,
) -> None:
    """Verify the registry manifest and every blob before publishing an offline model.

    A verified manifest is pinned locally so retries never switch model contents.
    The catalogue currently pins tags, not manifest digests; HTTPS and the registry's
    content digest authenticate first acquisition, not an independent release pin.
    """
    path, name, version = model_path(models, tag)
    if cancel.is_set():
        raise PausedError
    own = client is None

    def https_only(request: httpx.Request) -> None:
        if request.url.scheme != "https":
            raise RuntimeSetupError("AI files can only be downloaded over a secure connection.")

    http = client or httpx.Client(
        follow_redirects=True, timeout=httpx.Timeout(30), event_hooks={"request": [https_only]}
    )
    try:
        pin = path.with_name(path.name + ".verified")
        if pin.exists():
            body = pin.read_bytes()
        else:
            response = http.get(
                f"{REGISTRY}/v2/library/{name}/manifests/{version}",
                headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
            )
            response.raise_for_status()
            body = response.content
            digest = response.headers.get("Docker-Content-Digest", "")
            if (
                len(body) > 1_000_000
                or not _DIGEST.fullmatch(digest)
                or hashlib.sha256(body).hexdigest() != digest[7:]
            ):
                raise RuntimeSetupError(
                    "The AI model list did not match its checksum. Nothing was installed."
                )
            Manifest.model_validate_json(body)
            path.parent.mkdir(parents=True, exist_ok=True)
            staged_pin = pin.with_suffix(pin.suffix + ".ready")
            staged_pin.write_bytes(body)
            staged_pin.replace(pin)
        manifest = Manifest.model_validate_json(body)
        descriptors = {d.digest: d for d in [manifest.config, *manifest.layers]}
        total = sum(d.size for d in descriptors.values())
        done = 0
        blobs = models / "blobs"
        blobs.mkdir(parents=True, exist_ok=True)
        for d in descriptors.values():
            if cancel.is_set():
                raise PausedError
            target = blobs / d.digest.replace(":", "-")
            if (
                target.exists()
                and target.stat().st_size == d.size
                and sha256_of(target) == d.digest[7:]
            ):
                done += d.size
                progress(done, total)
                continue
            partial = target.with_suffix(".part")
            offset = partial.stat().st_size if partial.exists() else 0
            if offset == d.size and partial.exists():
                if sha256_of(partial) == d.digest[7:]:
                    partial.replace(target)
                    done += d.size
                    progress(done, total)
                    continue
                partial.unlink()
                offset = 0
            if offset > d.size:
                partial.unlink()
                offset = 0
            with http.stream(
                "GET",
                f"{REGISTRY}/v2/library/{name}/blobs/{d.digest}",
                headers={"Range": f"bytes={offset}-"} if offset else {},
            ) as response:
                response.raise_for_status()
                if response.status_code == 200 and offset:
                    partial.unlink()
                    offset = 0
                if response.status_code not in (200, 206):
                    raise RuntimeSetupError("The AI model download could not resume safely.")
                with partial.open("ab") as fh:
                    for chunk in response.iter_bytes(CHUNK):
                        if cancel.is_set():
                            raise PausedError
                        offset += len(chunk)
                        if offset > d.size:
                            partial.unlink(missing_ok=True)
                            raise RuntimeSetupError(
                                "The AI model download is larger than expected."
                            )
                        fh.write(chunk)
                        progress(done + offset, total)
            if offset != d.size or sha256_of(partial) != d.digest[7:]:
                partial.unlink(missing_ok=True)
                raise RuntimeSetupError(
                    "The AI model download did not match its checksum. It was deleted."
                )
            partial.replace(target)
            done += d.size
        staged = path.with_name(path.name + ".ready")
        staged.write_bytes(body)
        staged.replace(path)
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeSetupError("The AI model download could not be checked. Try again.") from exc
    finally:
        if own:
            http.close()
