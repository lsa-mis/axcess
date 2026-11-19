"""The Pages visited list as a CSV file, one row per page the report visited.

A download a person asks for from a report's Pages visited list
(``GET /api/scans/{id}/pages/export.csv``). It holds every page, not only the
rows on screen, in the order the list is sorted by, with the same columns and
the same words as the list:

* the column names are the list's column headers ("Issue occurrences",
  "Page states opened by clicking"), so a reader moving between the app and
  the spreadsheet sees one name for one thing (docs/plain-language.md);
* "Page load result" uses the words the list shows
  (``web/frontend/src/lib/pageLabels.ts``, ``pageLoadLabel``), mirrored in
  ``load_result_label`` below. Keep the two in step;
* a page that could not be loaded reads "Not checked" in its count columns,
  not 0, as in the list: no check ran on it, and 0 would read as a clean
  result. A spreadsheet's SUM skips the text, so totals still add up.

The server's status code has its own column too, as a plain number, so a
reader can sort or filter by it.

Text from the crawled site (a page title) cannot run as a spreadsheet
formula: a cell that starts with ``=``, ``+``, ``-``, ``@``, a tab or a
carriage return gets a leading apostrophe, which Excel, LibreOffice and
Google Sheets read as "this is text" (OWASP, "CSV Injection",
https://owasp.org/www-community/attacks/CSV_Injection).

The file starts with a UTF-8 byte order mark, so Excel opens titles in any
language, and the curly apostrophe in the server error label (U+2019),
correctly instead of guessing an older encoding.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from audit.web.pages_queries import LoadResult, ScanPageRow

COLUMNS = (
    "Page title",
    "Page address",
    "Page load result",
    "Server response code (HTTP status)",
    "Issue occurrences",
    "Images checked",
    "Page states opened by clicking",
    "Page details in Axcess",
)

NOT_CHECKED = "Not checked"

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def pages_csv_filename(scan_id: int) -> str:
    """``report-12-pages-visited.csv``, beside ``report-12-images.zip``."""
    return f"report-{scan_id}-pages-visited.csv"


def http_status_label(status: int | None) -> str:
    """The server's answer in words; ``httpStatusLabel`` in pageLabels.ts."""
    if status is None:
        return "Load result not recorded"
    if 200 <= status < 300:
        return f"Loaded successfully (HTTP {status})"
    if 300 <= status < 400:
        return f"Sent to another address (redirect, HTTP {status})"
    if status == 401:
        return "Sign-in required (HTTP 401)"
    if status == 403:
        return "Access blocked (HTTP 403)"
    if status == 404:
        return "Page not found (HTTP 404)"
    if 400 <= status < 500:
        return f"Page could not be loaded (HTTP {status})"
    if status >= 500:
        return f"The website\u2019s server had an error (HTTP {status})"
    return f"Server response code {status} (HTTP)"


def load_result_label(load_result: LoadResult, status: int | None) -> str:
    """How one page loaded; ``pageLoadLabel`` in pageLabels.ts."""
    if load_result == "not_loaded":
        return "Could not be loaded"
    return http_status_label(status)


def render_pages_csv(rows: Iterable[ScanPageRow], *, scan_id: int, app_base_url: str) -> str:
    """Return the CSV body for one report's visited pages.

    ``app_base_url`` is where this Axcess serves its app (``…/app``); each
    row links to its page's Page details there.
    """
    buf = io.StringIO(newline="")
    buf.write("\ufeff")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    base = app_base_url.rstrip("/")
    for row in rows:
        checked = row.load_result != "not_loaded"

        def count(value: int, checked: bool = checked) -> str:
            return str(value) if checked else NOT_CHECKED

        writer.writerow(
            [
                _text(row.title or ""),
                _text(row.url),
                load_result_label(row.load_result, row.status_code),
                "" if row.status_code is None else str(row.status_code),
                count(row.occurrence_count),
                count(row.image_count),
                count(row.page_state_count),
                f"{base}/scans/{scan_id}/pages/{row.page_id}",
            ]
        )
    return buf.getvalue()


def _text(value: str) -> str:
    """Crawled text, kept from being read as a formula."""
    return f"'{value}" if value.startswith(_FORMULA_STARTS) else value
