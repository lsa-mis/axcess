"""The files one report's pages link to, for the report's Documents tab.

Reads ``linked_files`` and ``linked_file_refs`` (migration 0039, written by
:mod:`audit.linked_files.tracker`). Every query is bound to one ``scan_id``:
a file, a reference or a page from another scan is never returned, whatever
the caller passes.

The order is fixed, and it is the point of the list ("which file do I fix
first"):

1. Status: Mostly sure, then Not sure, then Could not check.
2. Exposure: the number of pages that link to the file, most first; then a
   PDF with fillable form fields before one without (someone has to fill a
   form in, so they cannot just skip it).
3. Severity: a file that fails a check that stops a screen reader reading it
   at all (not tagged, no text, blocked by its security settings) before one
   that fails only the title or language checks.
4. Address, A to Z, then id, so paging never repeats or skips a row.

Exposure comes before severity because the brief that defined this list
named it first. There is no single score: each step is shown in the row, so
a reader can see why a file sits where it does.

A file still ``pending`` (a scan that stopped during the checks, or one still
running) is shown as Could not check with the reason ``not_checked``: the
report never shows a fourth status.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel

from audit.linked_files.formats import SEVERE_CHECKS, FailedCheck, FileType, Reason, RefKind

#: Largest page of rows one request may ask for.
MAX_LIMIT = 200
DEFAULT_LIMIT = 50
#: Referring pages shown per file. The row also gives the total.
MAX_REFS_SHOWN = 20

ShownStatus = Literal["mostly_sure", "not_sure", "could_not_check"]


class LinkedFileRef(BaseModel):
    """One place a page of this report reaches the file."""

    page_id: int
    page_url: str
    page_title: str | None
    how: RefKind
    #: The link's accessible name, or the frame's or embed's title.
    link_text: str
    #: The control a reader presses before the link exists, if any.
    revealed_by: str | None


class LinkedFileRow(BaseModel):
    file_id: int
    url: str
    #: A short name for the file: its file name, else the first link text.
    name: str
    file_type: FileType
    off_site: bool
    status: ShownStatus
    reason: Reason | None
    failed_checks: list[FailedCheck]
    http_status: int | None
    is_form: bool | None
    page_count: int | None
    #: Distinct pages of this report that reach the file.
    referring_page_count: int
    #: Up to ``MAX_REFS_SHOWN`` references, in page address order.
    refs: list[LinkedFileRef]


class LinkedFileCounts(BaseModel):
    """Files per status, across the whole report."""

    mostly_sure: int = 0
    not_sure: int = 0
    could_not_check: int = 0


class ScanDocumentsResponse(BaseModel):
    scan_id: int
    #: False when the scan did not look for linked files at all: a report
    #: made before this feature, a sign-in scan, or one with it turned off.
    #: An empty list then means "not looked for", never "none found".
    recorded: bool
    #: Every file the scan found, whatever the limit and offset.
    total: int
    counts: LinkedFileCounts
    limit: int
    offset: int
    files: list[LinkedFileRow]


_SEVERE_SQL = " OR ".join(
    f"f.failed_checks LIKE '%\"{check}\"%'" for check in sorted(SEVERE_CHECKS)
)

_SHOWN_STATUS_SQL = "CASE WHEN f.status = 'pending' THEN 'could_not_check' ELSE f.status END"


def scan_recorded_linked_files(config_json: str | None) -> bool:
    """Whether a scan's stored config says it looked for linked files."""
    try:
        config = json.loads(config_json or "{}")
    except (TypeError, ValueError):
        return False
    return isinstance(config, dict) and config.get("linked_files_enabled") is True


def display_name(url: str, first_link_text: str | None) -> str:
    """The file's name as the list shows it.

    The last part of its address when that looks like a file name
    ("annual-report.pdf"), since that is what a person saving the file sees.
    Otherwise (a Google address, ``download?id=7``) the first link's text,
    and the address itself as the last resort.
    """
    try:
        last = unquote(urlsplit(url).path.rsplit("/", 1)[-1]).strip()
    except ValueError:
        last = ""
    if last and "." in last.strip("."):
        return last[:200]
    if first_link_text and first_link_text.strip():
        return first_link_text.strip()[:200]
    return url


def list_scan_documents(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> ScanDocumentsResponse:
    """One bounded page of the files ``scan_id``'s pages link to, in report order.

    ``limit`` is clamped to 1..``MAX_LIMIT`` and ``offset`` to 0 or more, so
    a caller outside FastAPI's validation cannot load a whole scan at once.
    The caller checks that the scan exists.
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    scan = conn.execute("SELECT config_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
    recorded = scan is not None and scan_recorded_linked_files(scan[0])

    counts = LinkedFileCounts()
    for row in conn.execute(
        f"SELECT {_SHOWN_STATUS_SQL} AS shown, COUNT(*) FROM linked_files f "  # noqa: S608 - fixed SQL
        "WHERE f.scan_id = ? GROUP BY shown",
        (scan_id,),
    ):
        setattr(counts, str(row[0]), int(row[1]))
    total = counts.mostly_sure + counts.not_sure + counts.could_not_check

    rows = conn.execute(
        f"""
        SELECT f.id, f.url, f.file_type, f.off_site, {_SHOWN_STATUS_SQL} AS shown,
               CASE WHEN f.status = 'pending' THEN 'not_checked' ELSE f.reason END AS reason,
               f.failed_checks, f.http_status, f.is_form, f.page_count,
               (SELECT COUNT(DISTINCT r.page_id) FROM linked_file_refs r
                 WHERE r.file_id = f.id AND r.scan_id = f.scan_id) AS referring
          FROM linked_files f
         WHERE f.scan_id = ?
         ORDER BY CASE {_SHOWN_STATUS_SQL}
                    WHEN 'mostly_sure' THEN 0 WHEN 'not_sure' THEN 1 ELSE 2 END,
                  referring DESC,
                  COALESCE(f.is_form, 0) DESC,
                  CASE WHEN {_SEVERE_SQL} THEN 1 ELSE 0 END DESC,
                  f.url COLLATE NOCASE ASC,
                  f.id ASC
         LIMIT ? OFFSET ?
        """,  # noqa: S608 - only fixed strings are interpolated
        (scan_id, limit, offset),
    ).fetchall()

    refs = _refs(conn, scan_id, [int(row[0]) for row in rows])
    files = []
    for row in rows:
        file_refs = refs.get(int(row[0]), [])
        files.append(
            LinkedFileRow(
                file_id=int(row[0]),
                url=str(row[1]),
                name=display_name(str(row[1]), file_refs[0].link_text if file_refs else None),
                file_type=row[2],
                off_site=bool(row[3]),
                status=row[4],
                reason=row[5],
                failed_checks=json.loads(row[6] or "[]"),
                http_status=row[7],
                is_form=None if row[8] is None else bool(row[8]),
                page_count=row[9],
                referring_page_count=int(row[10]),
                refs=file_refs,
            )
        )
    return ScanDocumentsResponse(
        scan_id=scan_id,
        recorded=recorded,
        total=total,
        counts=counts,
        limit=limit,
        offset=offset,
        files=files,
    )


def _refs(
    conn: sqlite3.Connection, scan_id: int, file_ids: list[int]
) -> dict[int, list[LinkedFileRef]]:
    """At most ``MAX_REFS_SHOWN`` references per file, in page address order."""
    if not file_ids:
        return {}
    marks = ",".join("?" for _ in file_ids)
    rows = conn.execute(
        f"""
        SELECT file_id, page_id, url, title, how, link_text, revealed_by FROM (
            SELECT r.file_id, r.page_id, p.url_normalized AS url, p.title, r.how,
                   r.link_text, r.revealed_by,
                   ROW_NUMBER() OVER (
                       PARTITION BY r.file_id
                       ORDER BY p.url_normalized COLLATE NOCASE, r.how, r.link_text, r.id
                   ) AS n
              FROM linked_file_refs r
              JOIN pages p ON p.id = r.page_id AND p.scan_id = r.scan_id
             WHERE r.scan_id = ? AND r.file_id IN ({marks})
        ) WHERE n <= ?
        ORDER BY file_id, n
        """,  # noqa: S608 - only placeholders are interpolated
        (scan_id, *file_ids, MAX_REFS_SHOWN),
    ).fetchall()
    out: dict[int, list[LinkedFileRef]] = {}
    for row in rows:
        out.setdefault(int(row[0]), []).append(
            LinkedFileRef(
                page_id=int(row[1]),
                page_url=str(row[2]),
                page_title=row[3],
                how=row[4],
                link_text=str(row[5] or ""),
                revealed_by=row[6],
            )
        )
    return out


#: Elements of one page marked for one file. A page that links to one file
#: more often than this is marked only this many times.
MAX_PLACES = 50


class ElementPlaceModel(BaseModel):
    """The ``index``th of ``total`` elements a plain tag selector matches.

    The inspector's ``ElementPlace``: it outlines that element only when its
    own count of ``selector`` is ``total``.
    """

    selector: str
    index: int
    total: int


class DocumentOnPage(BaseModel):
    """Where one file of a report is reached on one page of that report."""

    file_id: int
    page_id: int
    name: str
    #: How the page reaches the file, as the Documents table lists it.
    refs: list[LinkedFileRef]
    #: False when the scan kept no copy of the page, so nothing can be marked.
    saved_copy: bool
    #: Each link, frame, object or embed in the saved copy that reaches the
    #: file, in page order: the elements the scan counted for it.
    places: list[ElementPlaceModel]


_PLACE_TAGS: tuple[tuple[str, str], ...] = (
    ("a", "href"),
    ("iframe", "src"),
    ("object", "data"),
    ("embed", "src"),
)


def document_on_page(
    conn: sqlite3.Connection, scan_id: int, file_id: int, page_id: int
) -> DocumentOnPage | None:
    """The elements of ``page_id``'s saved copy that reach ``file_id``.

    None unless the file and the page both belong to ``scan_id`` and the
    page reaches the file: one report's file is never looked up through
    another report, and a page that does not link to a file is never
    searched for it.

    The saved copy is read with the scan's own rules
    (:func:`audit.linked_files.discovery.resolve` and the tags
    :func:`~audit.linked_files.discovery.find_links` reads), so an element
    is marked exactly when the scan counted it. A link that appeared only
    after a click is not in the copy and gets no place; the refs say so.
    """
    from selectolax.parser import HTMLParser

    from audit.evaluation import saved_copy
    from audit.extractor.places import Places, hidden_from_inspector
    from audit.linked_files.discovery import resolve

    file_row = conn.execute(
        "SELECT url FROM linked_files WHERE id = ? AND scan_id = ?", (file_id, scan_id)
    ).fetchone()
    if file_row is None:
        return None
    page_row = conn.execute(
        "SELECT url_normalized, title FROM pages WHERE id = ? AND scan_id = ?",
        (page_id, scan_id),
    ).fetchone()
    if page_row is None:
        return None
    file_url = str(file_row[0])
    ref_rows = conn.execute(
        """
        SELECT how, link_text, revealed_by FROM linked_file_refs
         WHERE file_id = ? AND page_id = ? AND scan_id = ?
         ORDER BY how, link_text, id
         LIMIT ?
        """,
        (file_id, page_id, scan_id, MAX_REFS_SHOWN),
    ).fetchall()
    if not ref_rows:
        return None
    refs = [
        LinkedFileRef(
            page_id=page_id,
            page_url=str(page_row[0]),
            page_title=page_row[1],
            how=row[0],
            link_text=str(row[1] or ""),
            revealed_by=row[2],
        )
        for row in ref_rows
    ]
    name = display_name(file_url, refs[0].link_text)

    saved = saved_copy(conn, page_id)
    if saved is None:
        return DocumentOnPage(
            file_id=file_id, page_id=page_id, name=name, refs=refs, saved_copy=False, places=[]
        )
    body, base_url = saved
    places: list[ElementPlaceModel] = []
    try:
        tree = HTMLParser(body)
    except Exception:
        tree = None
    if tree is not None:
        counter = Places(tree)
        for tag, attribute in _PLACE_TAGS:
            for node in tree.css(tag):
                raw = node.attributes.get(attribute)
                if not raw or hidden_from_inspector(node):
                    continue
                if tag == "a" and raw.strip().startswith("#"):
                    continue
                if resolve(base_url, raw) != file_url:
                    continue
                place = counter.of(node, tag)
                if place is not None:
                    places.append(
                        ElementPlaceModel(
                            selector=place.selector, index=place.index, total=place.total
                        )
                    )
                if len(places) >= MAX_PLACES:
                    break
            if len(places) >= MAX_PLACES:
                break
    return DocumentOnPage(
        file_id=file_id, page_id=page_id, name=name, refs=refs, saved_copy=True, places=places
    )
