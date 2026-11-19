"""Unit tests for :mod:`audit.exports.pages_csv`, the Pages visited CSV."""

from __future__ import annotations

import csv
import io

import pytest

from audit.exports.pages_csv import (
    COLUMNS,
    http_status_label,
    load_result_label,
    pages_csv_filename,
    render_pages_csv,
)
from audit.web.pages_queries import ScanPageRow


def _row(page_id: int, url: str, status: int | None, title: str | None = None) -> ScanPageRow:
    load = "not_loaded" if status is None else "error_status" if status >= 400 else "loaded"
    return ScanPageRow(
        page_id=page_id,
        url=url,
        title=title,
        status_code=status,
        load_result=load,
        occurrence_count=3,
        image_count=2,
        page_state_count=1,
    )


def _parse(text: str) -> list[list[str]]:
    assert text.startswith("\ufeff")
    return list(csv.reader(io.StringIO(text.removeprefix("\ufeff"))))


def test_rows_keep_the_order_given_and_the_lists_words() -> None:
    rows = [
        _row(7, "http://a.test/down", None),
        _row(8, "http://a.test/gone", 404, "Not found"),
        _row(9, "http://a.test/", 200, "Home"),
    ]
    out = _parse(render_pages_csv(rows, scan_id=5, app_base_url="http://h:8765/app/"))
    assert out[0] == list(COLUMNS)
    assert [r[1] for r in out[1:]] == ["http://a.test/down", "http://a.test/gone", "http://a.test/"]
    assert out[1][2:7] == ["Could not be loaded", "", "Not checked", "Not checked", "Not checked"]
    assert out[2][2:7] == ["Page not found (HTTP 404)", "404", "3", "2", "1"]
    assert out[3][0] == "Home"
    assert out[3][7] == "http://h:8765/app/scans/5/pages/9"


@pytest.mark.parametrize("start", ["=", "+", "-", "@", "\t", "\r"])
def test_a_title_cannot_run_as_a_formula(start: str) -> None:
    title = f"{start}1+1"
    out = _parse(
        render_pages_csv([_row(1, "http://a.test/", 200, title)], scan_id=1, app_base_url="")
    )
    assert out[1][0] == f"'{title}"


def test_an_ordinary_title_is_left_as_it_is() -> None:
    title = "Caf\u00e9 \u2013 menu"
    out = _parse(
        render_pages_csv([_row(1, "http://a.test/", 200, title)], scan_id=1, app_base_url="")
    )
    assert out[1][0] == title


def test_labels_match_the_apps_words() -> None:
    # The same words as web/frontend/src/lib/pageLabels.ts.
    assert http_status_label(200) == "Loaded successfully (HTTP 200)"
    assert http_status_label(301) == "Sent to another address (redirect, HTTP 301)"
    assert http_status_label(401) == "Sign-in required (HTTP 401)"
    assert http_status_label(403) == "Access blocked (HTTP 403)"
    assert http_status_label(410) == "Page could not be loaded (HTTP 410)"
    assert http_status_label(503) == "The website\u2019s server had an error (HTTP 503)"
    assert load_result_label("not_loaded", None) == "Could not be loaded"


def test_filename_sits_beside_the_images_zip() -> None:
    assert pages_csv_filename(12) == "report-12-pages-visited.csv"
