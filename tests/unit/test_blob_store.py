"""Unit tests for content-hashed blob storage."""

from __future__ import annotations

import hashlib
from pathlib import Path

from audit.blob_store import BlobStore, ext_from_mime


def test_ext_from_mime_common_types() -> None:
    assert ext_from_mime("image/png") == "png"
    assert ext_from_mime("image/jpeg") == "jpg"
    assert ext_from_mime("image/svg+xml") == "svg"
    assert ext_from_mime("image/webp") == "webp"


def test_ext_from_mime_handles_params_and_case() -> None:
    assert ext_from_mime("IMAGE/PNG; charset=binary") == "png"


def test_ext_from_mime_unknown_returns_bin() -> None:
    assert ext_from_mime(None) == "bin"
    assert ext_from_mime("") == "bin"
    assert ext_from_mime("application/octet-stream") == "bin"


def test_store_returns_hash_and_writes_file(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    data = b"\x89PNG\r\n\x1a\n\x00\x00hello"

    content_hash, rel = store.store(data, "image/png")

    assert content_hash == hashlib.sha256(data).hexdigest()
    assert rel.startswith(f"{content_hash[:2]}/")
    assert rel.endswith(".png")
    full = store.path_for(rel)
    assert full.exists()
    assert full.read_bytes() == data


def test_store_is_idempotent(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    data = b"same bytes"

    h1, rel1 = store.store(data, "image/png")
    h2, rel2 = store.store(data, "image/png")

    assert h1 == h2
    assert rel1 == rel2
    # There should be exactly one file in the bucket directory.
    bucket = tmp_path / h1[:2]
    assert len(list(bucket.iterdir())) == 1


def test_store_preserves_file_even_if_mime_mismatches(tmp_path: Path) -> None:
    """If the same bytes are stored under two mime types, first one wins."""
    store = BlobStore(tmp_path)
    data = b"tiny image"
    h1, rel1 = store.store(data, "image/png")
    h2, rel2 = store.store(data, "image/jpeg")
    # Different extensions produce different rel paths — both files exist.
    # The SECOND call writes to a new path, but the first file still exists.
    assert h1 == h2
    assert rel1.endswith(".png")
    assert rel2.endswith(".jpg")
    assert store.path_for(rel1).exists()
    assert store.path_for(rel2).exists()


def test_store_does_not_leave_tmp_files(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    store.store(b"abc", "image/png")
    assert not any(p.name.endswith(".tmp") for p in tmp_path.rglob("*"))


def test_exists_checks_path(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    data = b"hi"
    assert store.exists("0" * 64, "image/png") is False
    h, _ = store.store(data, "image/png")
    assert store.exists(h, "image/png") is True
