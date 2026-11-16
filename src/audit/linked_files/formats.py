"""Which URLs and server answers name a linked file, and of which type.

A link names a linked file when its path ends in one of the file extensions
below, or when it points into Google Docs, Sheets, Slides or Drive. A link
with no such extension can still lead to one: the crawler fetches every
in-scope link, and when the server answers with one of the Content-Types
below, that answer decides (``classify_content_type``).

Each type falls into one of three groups, which decide its status before any
download:

* ``pdf``: downloaded and checked (:mod:`audit.linked_files.pdf_check`).
* ``CHECKED_LATER``: modern Office and OpenDocument files and RTF. Axcess
  does not check them *yet*; nothing stops a later build from doing so.
* ``CANNOT_CHECK``: old binary Office files (.doc, .xls, .ppt) and Google
  files. Old binary files have no accessibility structure a machine check
  could read, and a Google file is not a file Axcess can download.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

FileType = Literal[
    "pdf",
    "docx",
    "doc",
    "pptx",
    "ppt",
    "xlsx",
    "xls",
    "odt",
    "odp",
    "ods",
    "rtf",
    "google_doc",
    "google_sheet",
    "google_slides",
    "google_drive",
]

#: How a scan first knew a URL was a linked file.
FoundBy = Literal["extension", "host", "content_type"]

#: How a page reaches a file: an ordinary link, a link that appeared only
#: after a click, or an element that shows the file inside the page.
RefKind = Literal["link", "revealed_link", "iframe", "object", "embed"]

#: The three statuses the report shows, plus ``pending`` while a crawl runs.
#: There is no "accessible" status: a machine check can prove a failure but
#: cannot prove that a file is accessible.
Status = Literal["pending", "mostly_sure", "not_sure", "could_not_check"]

#: Why a file could not be checked. Each has its own sentence in the
#: interface (``LINKED_FILE_REASON_TEXT`` in ``lib/terms.ts``).
Reason = Literal[
    # Groups decided by type, before any download.
    "type_not_checked_yet",
    "old_format",
    "google_file",
    # What happened when Axcess tried.
    "broken_link",
    "http_error",
    "password",
    "too_large",
    "timed_out",
    "not_a_pdf",
    "damaged",
    "robots",
    "blocked",
    "limit",
    "not_checked",
]

#: Machine checks a PDF can fail. The first three stop a screen reader user
#: reading the file at all; the last two make it harder to find and to hear
#: correctly. ``SEVERE_CHECKS`` orders the report.
FailedCheck = Literal[
    "not_tagged",
    "no_text",
    "blocks_assistive_tech",
    "no_title",
    "no_language",
]
SEVERE_CHECKS: frozenset[str] = frozenset({"not_tagged", "no_text", "blocks_assistive_tech"})

_EXTENSIONS: dict[str, FileType] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
    ".pptx": "pptx",
    ".ppt": "ppt",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".odt": "odt",
    ".odp": "odp",
    ".ods": "ods",
    ".rtf": "rtf",
}

_CONTENT_TYPES: dict[str, FileType] = {
    "application/pdf": "pdf",
    "application/x-pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.presentation": "odp",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/rtf": "rtf",
    "text/rtf": "rtf",
}

CHECKED_LATER: frozenset[str] = frozenset({"docx", "pptx", "xlsx", "odt", "odp", "ods", "rtf"})
OLD_FORMATS: frozenset[str] = frozenset({"doc", "xls", "ppt"})
GOOGLE_TYPES: frozenset[str] = frozenset(
    {"google_doc", "google_sheet", "google_slides", "google_drive"}
)

# Google Docs paths. ``/forms/`` is deliberately absent: a Google Form is a
# web page someone fills in, not a file.
_GOOGLE_DOCS_PATHS: tuple[tuple[str, FileType], ...] = (
    ("/document/", "google_doc"),
    ("/spreadsheets/", "google_sheet"),
    ("/presentation/", "google_slides"),
)


def classify_url(url: str) -> FileType | None:
    """The linked-file type a URL names by itself, or None.

    Decided from the URL alone: its path's extension, or a Google Docs or
    Drive address. Never fetches. The query string is ignored, so
    ``report.pdf?v=2`` is a PDF and ``download.php?file=report.pdf`` is not
    (the crawler's Content-Type check can still find that one if it is on
    the scanned site).
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"}:
        return None
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    if host == "docs.google.com":
        # ``in``, not ``startswith``: a Google Workspace address puts the
        # organisation first (``/a/example.edu/document/d/...``).
        for part, file_type in _GOOGLE_DOCS_PATHS:
            if part in path:
                return file_type
        return None
    if host == "drive.google.com" and (path.startswith("/file/") or path in {"/open", "/uc"}):
        return "google_drive"
    last = path.rsplit("/", 1)[-1]
    dot = last.rfind(".")
    if dot <= 0:
        return None
    return _EXTENSIONS.get(last[dot:].lower())


def found_by_for_url(url: str) -> FoundBy:
    """``host`` for a Google address, else ``extension``. Only for classified URLs."""
    host = (urlsplit(url).hostname or "").lower()
    return "host" if host in {"docs.google.com", "drive.google.com"} else "extension"


def classify_content_type(content_type: str | None) -> FileType | None:
    """The linked-file type a server's Content-Type header names, or None."""
    if not content_type:
        return None
    media = content_type.split(";", 1)[0].strip().lower()
    return _CONTENT_TYPES.get(media)


def initial_status(file_type: FileType) -> tuple[Status, Reason | None]:
    """The status a file of this type gets before anything is downloaded.

    A PDF waits to be checked. Every other type is "Could not check" at
    once, with the reason that says whether a later build may check it.
    """
    if file_type == "pdf":
        return "pending", None
    if file_type in GOOGLE_TYPES:
        return "could_not_check", "google_file"
    if file_type in OLD_FORMATS:
        return "could_not_check", "old_format"
    return "could_not_check", "type_not_checked_yet"
