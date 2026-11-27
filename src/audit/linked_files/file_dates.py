"""When a linked file says it was created and last changed.

Read from the file's own properties while its check has it open, for the
Documents tab's "Creation date" (migration 0050). Asked for to tell current
documents from old ones that may be archived (the developer's request,
2026-11-25). Research, on the real files already labelled for the document
check (docs/internal/document-check.md, "Creation and modified dates"):

- Word (.docx) and PowerPoint (.pptx): ``dcterms:created`` and
  ``dcterms:modified`` in the core properties (``docProps/core.xml``).
  321 of 325 Word files and 35 of 45 PowerPoint files had a creation date.
- PDF: ``/CreationDate`` and ``/ModDate`` in the document information, or
  ``xmp:CreateDate`` and ``xmp:ModifyDate`` in its XMP metadata when those
  are missing. 54 of 54 real PDFs had one or the other.
- Google Docs and Slides exports carry neither: 0 of 42. Google keeps the
  dates in Drive, where only a signed-in API call reads them.

A creation date is when the file was first made, by whoever made it, as
the program that made it recorded it. It is not when the file was posted:
on finance.umich.edu, whose upload folders are named by month, 16 of 33
files were created more than a year before they were uploaded (a form
copied from an older one keeps the older date). It can also be wrong when
the computer's clock was. So a date is never treated as proof of when a
document was published or whether it is archived.

A date before 1980 or more than a day in the future is dropped as not a
real date (a reset clock, or a placeholder such as 1601-01-01).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

#: Dates outside these years are a broken clock or a placeholder.
_EARLIEST_YEAR = 1980
_CORE_PROPERTIES = "application/vnd.openxmlformats-package.core-properties+xml"


@dataclass(frozen=True)
class FileDates:
    """ISO 8601 strings, or None when the file does not say."""

    created: str | None = None
    modified: str | None = None


def _iso(value: Any, *, now: dt.datetime | None = None) -> str | None:
    """``value`` as ISO 8601, or None when it is not a believable date."""
    if not isinstance(value, dt.datetime):
        return None
    current = now or dt.datetime.now(dt.UTC)
    compare = value if value.tzinfo else value.replace(tzinfo=dt.UTC)
    if value.year < _EARLIEST_YEAR or compare > current + dt.timedelta(days=1):
        return None
    return value.isoformat(timespec="seconds")


def office_dates(package: Any, *, now: dt.datetime | None = None) -> FileDates:
    """A Word or PowerPoint package's creation and modified dates.

    Read from the core properties part the file has, never from the one
    python-docx and python-pptx make up for a file without it (Google's
    exports), which would say the file was made just now.
    """
    for part in package.iter_parts():
        if part.content_type == _CORE_PROPERTIES:
            # python-docx's part holds a CoreProperties; python-pptx's part is one.
            properties = getattr(part, "core_properties", part)
            return FileDates(
                created=_iso(_utc(getattr(properties, "created", None)), now=now),
                modified=_iso(_utc(getattr(properties, "modified", None)), now=now),
            )
    return FileDates()


def _utc(value: Any) -> Any:
    """An Office date as UTC. The file stores it in UTC (W3CDTF); python-docx
    says so, python-pptx gives the same time with no zone. Marked here, so a
    Word and a PowerPoint date of the same moment read and sort alike."""
    if isinstance(value, dt.datetime) and value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value


def pdf_dates(reader: Any, *, now: dt.datetime | None = None) -> FileDates:
    """A PDF's creation and modified dates: document information, then XMP."""
    created = modified = None
    try:
        info = reader.metadata
    except Exception:  # untrusted file: a broken /Info is no date
        info = None
    if info is not None:
        created = _read(lambda: info.creation_date, now)
        modified = _read(lambda: info.modification_date, now)
    if created is None or modified is None:
        try:
            xmp = reader.xmp_metadata
        except Exception:
            xmp = None
        if xmp is not None:
            created = created or _read(lambda: xmp.xmp_create_date, now)
            modified = modified or _read(lambda: xmp.xmp_modify_date, now)
    return FileDates(created=created, modified=modified)


def _read(get: Any, now: dt.datetime | None) -> str | None:
    try:
        return _iso(get(), now=now)
    except Exception:  # an unparseable date string is no date
        return None
