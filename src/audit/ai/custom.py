"""Your own model: a GGUF file a person chose, run by the private AI service.

For trying models the catalogue does not offer. The browser sends the file
to Axcess, which writes it into the AI folder the sandbox may read, the same
layout the catalogue's downloads use (``downloader.file_path`` under the
made-up repository ``local/my-models``), with the SHA-256 computed while it
arrives and kept in the same ``.sha256`` marker. From then on it is an
ordinary pinned file: the private service starts it with no network, and a
changed file no longer matches its marker.

Axcess cannot check where such a file came from, what licence it has, or
whether it is any good. llama.cpp reads it inside the sandbox, so a file
built to attack the reader still cannot reach the internet or files outside
the AI folder.

A model file and, optionally, its image add-on (mmproj). Without an add-on
the model answers text only: image questions fall back to text, as they do
when an image model is missing.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import struct
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from audit.ai.catalog import GgufFile, ModelEntry, SamplingKey
from audit.ai.downloader import file_path, file_present

FileKind = Literal["model", "image_addon"]

REPO = "local/my-models"
FOLDER = "local--my-models"
# A sanity cap, not a promise that such a model runs: the largest catalogue
# size is 15 GB.
MAX_FILE_BYTES = 200 * 1024**3
# Room left on the disk after the copy, as the catalogue downloads keep.
DISK_MARGIN = 3 * 1024**3
_HEADER_BYTES = 4 * 1024 * 1024
_GGUF_STRING = 8
_GGUF_ARRAY = 9
_SCALAR_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


class MyModelError(Exception):
    """The file cannot be used; the message says why in plain words."""


class MyModelFile(BaseModel):
    """One file copied in, as the setup page lists it."""

    sha256: str
    file: str
    size: int
    kind: FileKind
    # ``general.name`` from the file, when it has one; else the file name.
    name: str
    # An image add-on: the model it was copied with, so that model can be
    # chosen again later with its add-on.
    for_model: str | None = None


def safe_file_name(name: str) -> str:
    """A file name the catalogue's rules accept, from what the person chose."""
    stem = Path(name.replace("\\", "/")).name
    if stem.lower().endswith(".gguf"):
        stem = stem[: -len(".gguf")]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")[:100]
    return f"{stem or 'model'}.gguf"


def _incoming(models: Path) -> Path:
    return models / FOLDER / ".incoming"


def _sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".json")


def read_header(head: bytes) -> dict[str, str]:
    """String metadata from the start of a GGUF file (architecture, name).

    Reads only what fits in ``head`` and gives up quietly on anything
    unexpected: the result only labels the file and catches an image
    add-on chosen as the model. llama.cpp checks the whole file.
    """
    out: dict[str, str] = {}
    if len(head) < 24 or head[:4] != b"GGUF":
        return out
    pos = 4
    try:
        (version,) = struct.unpack_from("<I", head, pos)
        if version < 2:
            return out
        _, kv_count = struct.unpack_from("<QQ", head, pos + 4)
        pos += 20

        def string() -> str:
            nonlocal pos
            (length,) = struct.unpack_from("<Q", head, pos)
            pos += 8
            if length > 65536 or pos + length > len(head):
                raise ValueError("string too long")
            value = head[pos : pos + length].decode("utf-8", "replace")
            pos += length
            return value

        def skip(kind: int) -> None:
            nonlocal pos
            if kind == _GGUF_STRING:
                string()
            elif kind == _GGUF_ARRAY:
                (item, count) = struct.unpack_from("<IQ", head, pos)
                pos += 12
                if item == _GGUF_STRING:
                    for _ in range(count):
                        string()
                elif item in _SCALAR_SIZES:
                    pos += _SCALAR_SIZES[item] * count
                else:
                    raise ValueError("array type")
            elif kind in _SCALAR_SIZES:
                pos += _SCALAR_SIZES[kind]
            else:
                raise ValueError("value type")
            if pos > len(head):
                raise ValueError("past the header")

        for _ in range(min(kv_count, 512)):
            key = string()
            (kind,) = struct.unpack_from("<I", head, pos)
            pos += 4
            if kind == _GGUF_STRING and key in ("general.architecture", "general.name"):
                out[key] = string()[:200]
            else:
                skip(kind)
            if len(out) == 2:
                break
    except (struct.error, ValueError):
        pass
    return out


async def receive(
    models: Path,
    chunks: AsyncIterator[bytes],
    *,
    file_name: str,
    kind: FileKind,
    declared_size: int | None,
    for_model: str | None = None,
) -> MyModelFile:
    """Write an arriving GGUF file into the AI folder and check it.

    Raises :class:`MyModelError` for a file that is not GGUF, is the wrong
    kind, is too large, or does not fit on the disk. A partial file is
    deleted. The same file sent twice is kept once.
    """
    name = safe_file_name(file_name)
    incoming = _incoming(models)
    incoming.mkdir(parents=True, exist_ok=True)
    if declared_size is not None:
        if declared_size > MAX_FILE_BYTES:
            raise MyModelError("This file is larger than Axcess accepts for a model (200 GB).")
        if shutil.disk_usage(incoming).free < declared_size + DISK_MARGIN:
            raise MyModelError("There is not enough free disk space to copy this file.")
    part = incoming / f"{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    head = bytearray()
    size = 0
    try:
        with part.open("wb") as fh:
            async for chunk in chunks:
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise MyModelError(
                        "This file is larger than Axcess accepts for a model (200 GB)."
                    )
                if len(head) < _HEADER_BYTES:
                    head.extend(chunk[: _HEADER_BYTES - len(head)])
                    if len(head) >= 4 and bytes(head[:4]) != b"GGUF":
                        raise MyModelError(
                            "This is not a GGUF model file. Choose a file that ends in .gguf."
                        )
                digest.update(chunk)
                fh.write(chunk)
        if size < 24 or bytes(head[:4]) != b"GGUF":
            raise MyModelError("This is not a GGUF model file. Choose a file that ends in .gguf.")
        if declared_size is not None and size != declared_size:
            raise MyModelError("The file did not arrive whole. Try again.")
        header = read_header(bytes(head))
        is_addon = header.get("general.architecture") == "clip"
        if kind == "model" and is_addon:
            raise MyModelError(
                "This file is an image add-on (mmproj), not a model. Choose it as the "
                "image add-on instead."
            )
        if kind == "image_addon" and header and not is_addon:
            raise MyModelError(
                "This file is a model, not an image add-on (mmproj). Choose it as the model."
            )
        sha = digest.hexdigest()
        entry = GgufFile(repo=REPO, revision=sha[:40], file=name, size=size, sha256=sha)
        target = file_path(models, entry)
        if file_present(models, entry):
            part.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            part.replace(target)
            target.with_name(target.name + ".sha256").write_text(sha, encoding="ascii")
        info = MyModelFile(
            sha256=sha,
            file=name,
            size=size,
            kind=kind,
            name=header.get("general.name") or name.removesuffix(".gguf"),
            for_model=for_model if kind == "image_addon" else None,
        )
        _sidecar(target).write_text(info.model_dump_json(), encoding="utf-8")
        return info
    finally:
        part.unlink(missing_ok=True)


def list_files(models: Path) -> list[MyModelFile]:
    """The files copied in before and still whole, newest first."""
    root = models / FOLDER
    found: list[tuple[float, MyModelFile]] = []
    if not root.is_dir():
        return []
    for sidecar in root.glob("*/*.gguf.json"):
        try:
            info = MyModelFile.model_validate_json(sidecar.read_text(encoding="utf-8"))
            entry = _gguf(info)
            if file_path(models, entry) == sidecar.with_suffix("") and file_present(models, entry):
                found.append((sidecar.stat().st_mtime, info))
        except (OSError, ValueError):
            continue
    return [info for _, info in sorted(found, key=lambda pair: -pair[0])]


def _gguf(info: MyModelFile) -> GgufFile:
    return GgufFile(
        repo=REPO, revision=info.sha256[:40], file=info.file, size=info.size, sha256=info.sha256
    )


def find(models: Path, sha256: str, kind: FileKind) -> MyModelFile:
    for info in list_files(models):
        if info.sha256 == sha256 and info.kind == kind:
            return info
    raise MyModelError("That file is no longer in the AI folder. Choose it again.")


def model_entry(
    model: MyModelFile,
    addon: MyModelFile | None,
    sampling: dict[SamplingKey, float] | None = None,
) -> ModelEntry:
    """The catalogue-shaped entry the private service runs.

    Its name is made from the file's name and checksum, with no colon
    (llama-server renames a model whose name has one).
    """
    slug = re.sub(r"[^a-z0-9.-]+", "-", model.name.lower()).strip("-.")[:48] or "model"
    gguf = _gguf(model)
    mmproj = _gguf(addon) if addon else None
    return ModelEntry(
        tag=f"my-{slug}-{model.sha256[:8]}",
        size=gguf.size + (mmproj.size if mmproj else 0),
        licence="unknown",
        gguf=gguf,
        mmproj=mmproj,
        sampling=sampling or None,
    )


__all__ = [
    "FOLDER",
    "REPO",
    "FileKind",
    "MyModelError",
    "MyModelFile",
    "find",
    "list_files",
    "model_entry",
    "read_header",
    "receive",
    "safe_file_name",
]
