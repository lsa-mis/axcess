"""Read Google Drive folder listings and fetch authorized artifacts under a cap.

Standard library only. Nothing here is installed, and nothing listens. The two
jobs are deliberately separate:

* ``parse_listing`` is pure. It turns Drive's rendered folder HTML into
  ``(name, file_id, is_folder, size_text)`` records so a human can decide what
  to fetch *before* any byte is spent.
* ``fetch`` moves bytes, and refuses to move more than ``ByteBudget`` allows.

The byte cap is not decoration. Harry authorized staged local downloads up to
150 MB with no redistribution, so the cap is the mechanism that keeps a
mistaken loop from turning that into a bulk mirror.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Drive emits this sentinel on a non-item container.
_SENTINEL_ID = "_gd"

# One item's visible name, as Drive writes it into aria-label. The trailing
# word(s) describe the type rather than the file, so they are stripped.
_NAME_SUFFIXES = (
    " Shared folder",
    " Binary Shared",
    " PDF Shared",
    " CSV Shared",
    " Google Sheets Shared",
    " Unknown Shared",
    " Shared",
)

_TOKEN_RE = re.compile(r'(?:data-id="([^"]+)"|aria-label="([^"]*)")')
_SIZE_RE = re.compile(r"^Size:\s*([^\n\r]+)")


@dataclass(frozen=True)
class Entry:
    """One row of a Drive folder listing."""

    name: str
    file_id: str
    is_folder: bool
    size_text: str | None


def _split_label(label: str) -> tuple[str, bool] | None:
    """Return ``(name, is_folder)`` if this label names an item, else ``None``."""
    for suffix in _NAME_SUFFIXES:
        if label.endswith(suffix) and len(label) > len(suffix):
            return label[: -len(suffix)], suffix == " Shared folder"
    return None


def parse_listing(page_html: str) -> list[Entry]:
    """Extract one ``Entry`` per item from a Drive folder page.

    Drive repeats each item's ``data-id`` on several nested nodes and carries
    the name and size in ``aria-label`` attributes that follow it. So the
    document is walked in order: the first unseen id opens an item, and the
    next name-shaped label closes it.
    """
    entries: list[Entry] = []
    seen: set[str] = set()
    current_id: str | None = None
    current_name: tuple[str, bool] | None = None

    for match in _TOKEN_RE.finditer(page_html):
        raw_id, raw_label = match.group(1), match.group(2)

        if raw_id is not None:
            # Drive repeats an item's id on several nested nodes, including one
            # *after* the name label. Only a genuinely different id opens a new
            # item; anything else would discard the name we just read.
            if raw_id == _SENTINEL_ID or raw_id == current_id or raw_id in seen:
                continue
            current_id, current_name = raw_id, None
            continue

        if current_id is None or raw_label is None:
            continue

        label = html_mod.unescape(raw_label)

        if current_name is None:
            named = _split_label(label)
            if named is not None:
                current_name = named
            continue

        # Named already. Filler labels ("Shared", "Modified ...") are ignored
        # until the size line, which is what closes the item.
        size_match = _SIZE_RE.match(label)
        if size_match is None and label != "Size not available":
            continue

        entries.append(
            Entry(
                name=current_name[0],
                file_id=current_id,
                is_folder=current_name[1],
                size_text=size_match.group(1).strip() if size_match else None,
            )
        )
        seen.add(current_id)
        current_id, current_name = None, None

    return entries


class BudgetExceeded(RuntimeError):
    """Raised instead of downloading past the authorized cap."""


@dataclass
class ByteBudget:
    """A hard ceiling on total bytes fetched in one session."""

    limit: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def check(self, size: int) -> None:
        """Reject a declared size before any bytes move."""
        if self.used + size > self.limit:
            raise BudgetExceeded(
                f"{size} B would exceed the {self.limit} B cap "
                f"({self.used} B already used)"
            )

    def spend(self, size: int) -> None:
        self.check(size)
        self.used += size


def folder_url(file_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{file_id}"


def download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _open(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(request, timeout=120)


def read_text(url: str, budget: ByteBudget) -> str:
    """Fetch a listing page into memory. No file is written."""
    with _open(url) as response:
        body = response.read(budget.remaining + 1)
    budget.spend(len(body))
    return body.decode("utf-8", errors="replace")


def fetch(url: str, dest: Path, budget: ByteBudget) -> dict[str, object]:
    """Download one artifact to ``dest``, returning its provenance record.

    Reads at most ``budget.remaining + 1`` bytes so an oversized response is
    detected and refused rather than streamed to disk in full.
    """
    with _open(url) as response:
        final_url = response.geturl()
        body = response.read(budget.remaining + 1)

    budget.spend(len(body))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)

    return {
        "url": url,
        "final_url": final_url,
        "path": dest.name,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def write_manifest(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = sum(int(r["bytes"]) for r in records)
    path.write_text(
        json.dumps({"total_bytes": total, "artifacts": records}, indent=2) + "\n"
    )
