"""The pages one report visited, for the "Pages visited" list.

The report summary has always said how many pages a scan visited, but not
which ones, so a reader could not tell a clean result from missing coverage:
"0 issue occurrences" reads the same whether every page loaded and passed or
half of them never loaded at all. This module lists the scan's ``pages`` rows,
one per page the crawler recorded, with how each one loaded and what the
checks stored against it.

Every count here is the same count the page's own evidence route
(``GET /api/scans/{id}/pages/{page_id}``, ``evaluation.get_page_evidence``)
shows for that page, so a number in the list matches the page it links to:

* ``occurrence_count``: every ``page_a11y_findings`` row of the page. The
  Issues table counts an element that repeats across pages (a shared menu)
  once, on the first page it was found (``issues._first_instances``), so the
  sum of this column can be higher than the report's "Issue occurrences".
* ``image_count``: every ``page_images`` row of the page, the images the page
  evidence lists as "images checked".
* ``page_state_count``: every ``page_dom_states`` row of the page, the page
  states the interaction probe opened by clicking.

How a page loaded comes from ``pages.status_code``. The crawler writes NULL
only when the fetch itself failed (``orchestrator._record_page`` with no
result); any answer from the server is stored with its status code.

Scope: every query is bound to one ``scan_id``. A page id from another scan
is never returned, whatever the caller passes. The caller checks that the
scan exists; this module returns an empty list for a scan with no pages.
"""

from __future__ import annotations

import sqlite3
from typing import Literal

from pydantic import BaseModel

#: Largest page of rows one request may ask for.
MAX_LIMIT = 200
DEFAULT_LIMIT = 50

LoadResult = Literal["loaded", "error_status", "not_loaded"]

PageSort = Literal[
    "load_desc",
    "load_asc",
    "url_asc",
    "url_desc",
    "occurrences_desc",
    "occurrences_asc",
    "images_desc",
    "images_asc",
    "states_desc",
    "states_asc",
]
DEFAULT_SORT: PageSort = "load_desc"

# How badly a page failed to load, for "problems first": a page the scan
# could not fetch at all, then a page that answered with an error status,
# then a page that loaded.
_LOAD_RANK = "CASE WHEN p.status_code IS NULL THEN 2 WHEN p.status_code >= 400 THEN 1 ELSE 0 END"

# Sort key -> ORDER BY expression. Only these fixed strings ever reach the
# SQL; the request's value selects one, it is never interpolated.
_ORDER_BY: dict[str, str] = {
    "load_desc": f"{_LOAD_RANK} DESC",
    "load_asc": f"{_LOAD_RANK} ASC",
    "url_asc": "p.url_normalized COLLATE NOCASE ASC",
    "url_desc": "p.url_normalized COLLATE NOCASE DESC",
    "occurrences_desc": "occurrence_count DESC",
    "occurrences_asc": "occurrence_count ASC",
    "images_desc": "image_count DESC",
    "images_asc": "image_count ASC",
    "states_desc": "page_state_count DESC",
    "states_asc": "page_state_count ASC",
}


class ScanPageRow(BaseModel):
    """One page the scan visited."""

    page_id: int
    url: str
    title: str | None
    #: The HTTP status the server answered with; None when the fetch failed.
    status_code: int | None
    #: ``not_loaded`` when the fetch failed, ``error_status`` when the server
    #: answered 400 or above, else ``loaded``.
    load_result: LoadResult
    occurrence_count: int
    image_count: int
    page_state_count: int


class ScanPagesResponse(BaseModel):
    """One page of a report's visited pages, with the report-wide totals."""

    scan_id: int
    #: Every page the scan recorded, whatever the limit and offset.
    total: int
    #: Pages whose fetch failed, across the whole report.
    not_loaded_count: int
    #: Pages that answered with an error status (400 or above), across the report.
    error_status_count: int
    limit: int
    offset: int
    sort: PageSort
    pages: list[ScanPageRow]


def load_result(status_code: int | None) -> LoadResult:
    """How a page loaded, from its stored HTTP status."""
    if status_code is None:
        return "not_loaded"
    if status_code >= 400:
        return "error_status"
    return "loaded"


def list_scan_pages(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    sort: PageSort = DEFAULT_SORT,
) -> ScanPagesResponse:
    """Return one bounded page of the pages ``scan_id`` visited.

    ``limit`` is clamped to 1..``MAX_LIMIT`` and ``offset`` to 0 or more, so
    a caller outside FastAPI's validation cannot load a whole large scan in
    one call. Ties in any sort fall back to the URL and then the page id, so
    paging through a sort never repeats or skips a row.
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    order_by = _ORDER_BY.get(sort)
    if order_by is None:
        raise ValueError(f"Unknown sort: {sort!r}")

    totals = conn.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(status_code IS NULL), 0) AS not_loaded,
               COALESCE(SUM(status_code >= 400), 0) AS error_status
          FROM pages
         WHERE scan_id = ?
        """,
        (scan_id,),
    ).fetchone()

    # Each count is a correlated subquery on an indexed page_id column
    # (idx_a11y_page, idx_page_images_page, the page_dom_states primary
    # key), and each repeats the scan_id bound: a child row is only counted
    # when it belongs to this scan as well as to this page.
    rows = conn.execute(
        f"""
        SELECT p.id AS page_id,
               p.url_normalized AS url,
               p.title AS title,
               p.status_code AS status_code,
               (SELECT COUNT(*) FROM page_a11y_findings a
                 WHERE a.page_id = p.id AND a.scan_id = p.scan_id) AS occurrence_count,
               (SELECT COUNT(*) FROM page_images pi
                 WHERE pi.page_id = p.id) AS image_count,
               (SELECT COUNT(*) FROM page_dom_states d
                 WHERE d.page_id = p.id AND d.scan_id = p.scan_id) AS page_state_count
          FROM pages p
         WHERE p.scan_id = ?
         ORDER BY {order_by}, p.url_normalized COLLATE NOCASE ASC, p.id ASC
         LIMIT ? OFFSET ?
        """,  # noqa: S608 - order_by is one of the fixed _ORDER_BY strings
        (scan_id, limit, offset),
    ).fetchall()

    return ScanPagesResponse(
        scan_id=scan_id,
        total=int(totals["total"]),
        not_loaded_count=int(totals["not_loaded"]),
        error_status_count=int(totals["error_status"]),
        limit=limit,
        offset=offset,
        sort=sort,
        pages=[
            ScanPageRow(
                page_id=int(row["page_id"]),
                url=str(row["url"]),
                title=row["title"],
                status_code=row["status_code"],
                load_result=load_result(row["status_code"]),
                occurrence_count=int(row["occurrence_count"]),
                image_count=int(row["image_count"]),
                page_state_count=int(row["page_state_count"]),
            )
            for row in rows
        ],
    )
