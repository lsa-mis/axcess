"""Content-addressed image blob storage.

Layout: ``<root>/<aa>/<full_sha256>.<ext>``, first two hex chars are used as a
bucket so no single directory grows without bound. Writes are idempotent: if a
file already exists at the target path we assume the content is already ours
(SHA-256 collisions are not realistic for our purposes).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_MIME_TO_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "image/bmp": "bmp",
    "image/avif": "avif",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
}


def ext_from_mime(mime: str | None) -> str:
    """Map a Content-Type value to a lowercase extension. Falls back to ``bin``."""
    if not mime:
        return "bin"
    base = mime.split(";", 1)[0].strip().lower()
    return _MIME_TO_EXT.get(base, "bin")


class BlobStore:
    """Keyed-by-content-hash file store rooted at ``root``."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def store(self, data: bytes, mime: str | None) -> tuple[str, str]:
        """Write ``data`` if not already present. Returns ``(content_hash, rel_path)``."""
        content_hash = hashlib.sha256(data).hexdigest()
        rel = self._rel_path(content_hash, ext_from_mime(mime))
        full = self.root / rel
        if not full.exists():
            full.parent.mkdir(parents=True, exist_ok=True)
            # Write-and-rename keeps the store consistent if the process dies mid-write.
            tmp = full.with_suffix(full.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(full)
        return content_hash, rel

    def path_for(self, rel_path: str) -> Path:
        return self.root / rel_path

    def exists(self, content_hash: str, mime: str | None) -> bool:
        return (self.root / self._rel_path(content_hash, ext_from_mime(mime))).exists()

    @staticmethod
    def _rel_path(content_hash: str, ext: str) -> str:
        return f"{content_hash[:2]}/{content_hash}.{ext}"
