"""Identify what a downloaded KAFE subject file actually is.

This is the feasibility question the whole phase turns on: if the captures are
a container we can read with the standard library, an offline replay adapter is
buildable; if they are a mitmproxy flow stream, they are not, without new
tooling. Reports evidence, and does not guess.
"""

from __future__ import annotations

import gzip
import json
import tarfile
import zipfile
from pathlib import Path

ARTIFACTS = Path(__file__).resolve().parent.parent / "artifacts"

MAGICS = {
    b"PK\x03\x04": "zip",
    b"\x1f\x8b": "gzip",
    b"SQLi": "sqlite",
    b"%PDF": "pdf",
    b"\x37\x7a\xbc\xaf": "7z",
    b"ustar": "tar(offset257)",
}


def sniff(path: Path) -> dict[str, object]:
    head = path.read_bytes()[:512]
    magic = next((n for m, n in MAGICS.items() if head.startswith(m)), None)
    if magic is None and len(head) > 262 and head[257:262] == b"ustar":
        magic = "tar"

    out: dict[str, object] = {
        "file": path.name,
        "bytes": path.stat().st_size,
        "magic": magic,
        "head_hex": head[:24].hex(),
        "head_printable": head[:80].decode("latin-1").replace("\n", "\\n"),
    }

    if magic == "zip":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            out["member_count"] = len(names)
            out["members_sample"] = names[:25]
            out["uncompressed_bytes"] = sum(i.file_size for i in archive.infolist())
    elif magic == "gzip":
        try:
            with gzip.open(path) as handle:
                inner = handle.read(512)
            out["gzip_inner_head"] = inner[:80].decode("latin-1").replace("\n", "\\n")
            out["gzip_inner_is_tar"] = len(inner) > 262 and inner[257:262] == b"ustar"
        except OSError as exc:
            out["gzip_error"] = str(exc)
    elif magic in {"tar", "tar(offset257)"}:
        with tarfile.open(path) as archive:
            names = archive.getnames()
            out["member_count"] = len(names)
            out["members_sample"] = names[:25]
    else:
        # mitmproxy .flow is a stream of tnetstrings: "<len>:<payload>,".
        prefix = head.split(b":", 1)[0]
        out["looks_like_tnetstring"] = prefix.isdigit() and len(prefix) <= 10
        out["has_http_tokens"] = any(
            token in head for token in (b"HTTP/", b"GET ", b"Host:", b"200")
        )

    return out


if __name__ == "__main__":
    report = [sniff(p) for p in sorted(ARTIFACTS.glob("subject_*.bin"))]
    print(json.dumps(report, indent=2)[:4000])
