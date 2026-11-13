"""The report's images as a ZIP: pictures in folders by group and verdict, plus a sheet.

Downloaded from the Images tab (``GET /api/scans/{id}/images/export.zip``).
It is a snapshot for a person to work from, not a source of truth: the
database and blob store stay authoritative (AGENTS.md).

Layout::

    report-82-images/
      Images with text/
        Needs alt text/00012 banner.png
        Needs better alt text/...
        Good alt text/...
      Images without alt text/
        Needs alt text/...
      Images with alt text/
        Not checked yet/...
      images.xlsx

The folders follow the tab: a group, then a verdict. An image in two groups
(an image with text is also with or without alt text) is copied into both,
so each folder is complete on its own. The file name starts with the image
number, so two images both called ``logo.png`` never overwrite each other.

The sheet lists every image once, with where its copies are in the ZIP. Each
row shows a small preview of the picture in the "Image" column, and its file
name is a link that opens the full picture from the unzipped folder (the
link is relative to images.xlsx, so it works once the ZIP is extracted, not
from inside it). "Image address" links to the picture on the live site.
Text from the crawled site goes into cells as text, never as a formula, so a
page that writes ``=HYPERLINK(...)`` into its alt text cannot run in Excel.
"""

from __future__ import annotations

import io
import re
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from audit.blob_store import BlobStore
from audit.web.image_inventory import GROUPS, ReportImage, all_report_images

GROUP_FOLDER = {
    "with_text": "Images with text",
    "missing_alt": "Images without alt text",
    "with_alt": "Images with alt text",
}
VERDICT_FOLDER = {
    "needs_alt": "Needs alt text",
    "needs_better": "Needs better alt text",
    "not_checked": "Not checked yet",
    "good": "Good alt text",
}
SOURCE_LABEL = {
    "page_code": "Page code",
    "text_match": "Compared with the text in the image",
    "local_model": "Local AI model (check before you rely on it)",
}
_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
    "image/bmp": ".bmp",
}
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")

COLUMNS = (
    ("Image number", 12),
    ("Image", 26),
    ("File name", 28),
    ("Groups", 30),
    ("Alt text verdict", 22),
    ("Why", 40),
    ("Verdict from", 30),
    ("Current alt text", 40),
    ("Text in the image", 40),
    ("Suggested alt text", 40),
    ("Suggested by", 18),
    ("Pages it appears on", 12),
    ("First page", 50),
    ("Image address", 50),
    ("Files in this ZIP", 60),
)


def _file_name(image: ReportImage) -> str:
    """``00012 banner.png``: the image number, then a safe form of its name."""
    raw = Path(image.image_url.split("?", 1)[0]).name or "image"
    stem = _UNSAFE.sub("_", Path(raw).stem).strip(" ._")[:60] or "image"
    ext = _EXTENSIONS.get((image.mime or "").lower()) or (Path(raw).suffix.lower()[:6] or "")
    return f"{image.image_id:05d} {stem}{ext}"


def _alt_cell(value: str | None) -> str:
    if value is None:
        return "(no alt text)"
    if not value.strip():
        return '(empty alt="", marked decorative)'
    return value


def _text_cell(ws: Worksheet, row: int, col: int, value: Any) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str):
        # Always text: a value starting "=" from a crawled page must not
        # become a formula.
        cell.data_type = "s"
    cell.alignment = Alignment(wrap_text=True, vertical="top")


# Preview size in pixels: big enough to recognise the picture, small enough
# that a report with hundreds of images stays a reasonable file.
PREVIEW_BOX = (180, 120)
# Previews stop after this many, so a huge report does not make an Excel
# file too large to open; the rest keep their link.
MAX_PREVIEWS = 2000
# Excel row height is in points; 1 pixel is 0.75 points.
_ROW_HEIGHT = PREVIEW_BOX[1] * 0.75 + 6


def _preview(data: bytes) -> bytes | None:
    """A small PNG of the picture, or None when it cannot be drawn (SVG, broken)."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as picture:
            picture.seek(0)  # first frame of an animation
            small = picture.convert("RGBA")
            small.thumbnail(PREVIEW_BOX)
            out = io.BytesIO()
            small.save(out, format="PNG", optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


def _web_link(url: str) -> str | None:
    """Only http and https addresses become links; anything else stays text."""
    return url if url.startswith(("http://", "https://")) else None


def _workbook(
    scan_id: int,
    seed_url: str,
    rows: list[ReportImage],
    files: dict[int, list[str]],
    previews: dict[int, bytes],
) -> bytes:
    wb = Workbook()
    # A new workbook starts with one sheet; it becomes "About".
    about = wb.active if wb.active is not None else wb.create_sheet()
    about.title = "About"
    lines = [
        f"Images in report #{scan_id}",
        f"Site: {seed_url}",
        "",
        "Every image the scan found, with a verdict on its alt text: the text a "
        "screen reader reads for an image.",
        "Needs alt text: there is none, or it is empty on an image that has text in it.",
        "Needs better alt text: there is some, but it falls short.",
        "Not checked yet: there is no text in the image to compare, and no one asked "
        "the local AI model.",
        "",
        "Each verdict is a lead for a person to confirm. Suggested alt text from the "
        "local AI model must be checked before use. This list does not prove that the "
        "site meets accessibility standards (WCAG).",
        "",
        "The pictures are in folders by group, then by verdict. An image in two groups "
        "is in both folders.",
        "On the Images sheet, each row shows a small preview. Unzip the folder first, then "
        "select a file name to open the full picture. Image address opens the picture "
        "on the live site.",
    ]
    for index, line in enumerate(lines, start=1):
        _text_cell(about, index, 1, line)
    about.column_dimensions["A"].width = 100
    about["A1"].font = Font(bold=True, size=14)

    ws = wb.create_sheet("Images")
    for col, (name, width) in enumerate(COLUMNS, start=1):
        _text_cell(ws, 1, col, name)
        ws.cell(row=1, column=col).font = Font(bold=True)
        ws.column_dimensions[get_column_letter(col)].width = width
    for r, image in enumerate(rows, start=2):
        values: list[Any] = [
            image.image_id,
            "" if image.image_id in previews else "No preview",
            _file_name(image),
            ", ".join(GROUP_FOLDER[g] for g in image.groups),
            VERDICT_FOLDER[image.verdict],
            image.verdict_reason,
            SOURCE_LABEL[image.verdict_source] if image.verdict_source else "Not checked",
            _alt_cell(image.alt_text),
            image.image_text or "",
            image.suggestion or "",
            image.suggestion_model or "",
            image.page_count,
            image.sample_page_url or "",
            image.image_url,
            "\n".join(files.get(image.image_id, [])) or "No saved picture (drawn in the page code)",
        ]
        for col, value in enumerate(values, start=1):
            _text_cell(ws, r, col, value)
        _link_row(ws, r, image, files.get(image.image_id, []), previews.get(image.image_id))
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(1, len(rows) + 1)}"
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


_COL = {name: index for index, (name, _width) in enumerate(COLUMNS, start=1)}


def _link_row(
    ws: Worksheet, row: int, image: ReportImage, copies: list[str], preview: bytes | None
) -> None:
    """The preview picture, and the two links, for one row of the sheet."""
    if preview is not None:
        picture = XLImage(io.BytesIO(preview))
        ws.add_image(picture, f"{get_column_letter(_COL['Image'])}{row}")
        ws.row_dimensions[row].height = _ROW_HEIGHT
    link_font = Font(color="0B5394", underline="single")
    if copies:
        # Relative to images.xlsx, which sits at the top of the unzipped folder.
        name_cell = ws.cell(row=row, column=_COL["File name"])
        name_cell.hyperlink = copies[0]
        name_cell.font = link_font
    web = _web_link(image.image_url)
    if web:
        address = ws.cell(row=row, column=_COL["Image address"])
        address.hyperlink = web
        address.font = link_font


def write_images_zip(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    seed_url: str,
    blob_store: BlobStore,
    out: Any,
) -> None:
    """Write the ZIP to ``out``, a binary file object."""
    rows = all_report_images(conn, scan_id)
    blob_paths = {
        int(r["id"]): r["blob_path"]
        for r in conn.execute(
            """
            SELECT DISTINCT i.id, i.blob_path
              FROM images i
              JOIN page_images pi ON pi.image_id = i.id
              JOIN pages p ON p.id = pi.page_id
             WHERE p.scan_id = ?
            """,
            (scan_id,),
        )
    }
    root = f"report-{scan_id}-images"
    root_dir = blob_store.root.resolve()
    files: dict[int, list[str]] = {}
    previews: dict[int, bytes] = {}
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for image in rows:
            rel = blob_paths.get(image.image_id)
            if not rel:
                continue
            path = blob_store.path_for(rel).resolve()
            try:
                path.relative_to(root_dir)
                data = path.read_bytes()
            except (ValueError, OSError):
                continue
            if len(previews) < MAX_PREVIEWS:
                small = _preview(data)
                if small is not None:
                    previews[image.image_id] = small
            name = _file_name(image)
            for group in GROUPS:
                if group not in image.groups:
                    continue
                arc = f"{GROUP_FOLDER[group]}/{VERDICT_FOLDER[image.verdict]}/{name}"
                # Pictures are already compressed; storing them is faster.
                zf.writestr(f"{root}/{arc}", data, compress_type=zipfile.ZIP_STORED)
                files.setdefault(image.image_id, []).append(arc)
        zf.writestr(f"{root}/images.xlsx", _workbook(scan_id, seed_url, rows, files, previews))


def images_zip_filename(scan_id: int) -> str:
    return f"report-{scan_id}-images.zip"
