"""What the report's Export panel knows before anything is downloaded.

The panel offers four files, and choosing one used to be a guess. Nothing
said how large a file would be: a 1,718-page scan's raw findings run to
about 24 MB while its workbook stays under 1 MB. Nothing said that every
file would arrive labeled DRAFT because expert review was unfinished, either:
the panel acknowledged the draft on the reader's behalf and never told them.

This module answers both from the same bytes the download route serves. The
caller passes the route's own renderer, so each format is rendered and
labeled exactly as ``GET /api/scans/{id}/export/{fmt}`` would, and its
encoded length is reported. Nothing is estimated from row counts. A size can
drift only if the report changes between this request and the download (a
status edit, say), which is why the panel shows it as approximate.

Taking the renderer as an argument also keeps this module free of FastAPI
and of the database, so it can be tested with a stub.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal

from pydantic import BaseModel

from audit.web.export_readiness import PublicExportReadiness, public_export_filename

PanelFormat = Literal["xlsx", "audit", "csv", "json"]

#: The files the Export panel offers, in the panel's order. The route also
#: serves ``markdown`` and ``jira``; the panel does not list them, so they
#: are not rendered here.
PANEL_FORMATS: tuple[PanelFormat, ...] = ("xlsx", "audit", "csv", "json")


class ExportFormatOption(BaseModel):
    """One file the panel offers, as the download would deliver it."""

    format: PanelFormat
    #: The name the download route's ``Content-Disposition`` gives the file,
    #: ``_DRAFT`` marker included.
    filename: str
    #: The file's size in bytes: the rendered, draft-labeled export, encoded
    #: the way the route sends it.
    size_bytes: int


class ExportOptions(BaseModel):
    """The Export panel's facts for one report."""

    scan_id: int
    #: True when every file is downloaded as a labeled draft, because expert
    #: review of this report is not complete.
    draft: bool
    evaluation_status: str
    formats: list[ExportFormatOption]


def encoded_size(rendered: str | bytes) -> int:
    """Return the byte length the route sends; text is served as UTF-8."""

    return len(rendered) if isinstance(rendered, bytes) else len(rendered.encode("utf-8"))


def build_export_options(
    scan_id: int,
    readiness: PublicExportReadiness,
    *,
    extensions: Mapping[str, str],
    render: Callable[[PanelFormat], str | bytes],
) -> ExportOptions:
    """Describe each panel format by rendering it the way the route would.

    ``readiness`` must be the draft-acknowledged disposition the panel's
    downloads request, and ``render`` must return the labeled export for
    that disposition, so the filename and the size describe the same file.
    """

    return ExportOptions(
        scan_id=scan_id,
        draft=readiness.is_draft,
        evaluation_status=readiness.evaluation_status,
        formats=[
            ExportFormatOption(
                format=export_format,
                filename=public_export_filename(scan_id, extensions[export_format], readiness),
                size_bytes=encoded_size(render(export_format)),
            )
            for export_format in PANEL_FORMATS
        ],
    )
