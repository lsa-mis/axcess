"""Unit tests for :mod:`audit.web.pages_queries`, the "Pages visited" list."""

from __future__ import annotations

import gzip
import sqlite3

import pytest

from audit import evaluation
from audit.db import repo
from audit.web.pages_queries import MAX_LIMIT, list_scan_pages, load_result


def _scan(conn: sqlite3.Connection, seed: str) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES (?, 'completed', 0, 0, '{}')",
        (seed,),
    )
    return int(cur.lastrowid or 0)


def _page(
    conn: sqlite3.Connection, scan_id: int, url: str, *, status: int | None, title: str | None
) -> int:
    return repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized=url,
        status_code=status,
        title=title,
        render_mode="js",
        html_hash=None,
    )


def _finding(conn: sqlite3.Connection, scan_id: int, page_id: int, target: str) -> None:
    conn.execute(
        """
        INSERT INTO page_a11y_findings (
            page_id, scan_id, rule_id, help, target_selector, target_hash, status, pipeline
        ) VALUES (?, ?, 'color-contrast', 'Contrast (Minimum)', ?, ?, 'new', 'axe')
        """,
        (page_id, scan_id, target, f"hash-{page_id}-{target}"),
    )


def _image(conn: sqlite3.Connection, scan_id: int, page_id: int, name: str) -> None:
    image_id = repo.upsert_image(
        conn,
        content_hash=name * 64,
        src_url=f"http://example.test/{name}.png",
        mime="image/png",
        bytes_len=10,
        width=1,
        height=1,
        blob_path=None,
        has_svg_text=False,
        scan_id=scan_id,
    )
    repo.upsert_page_image(
        conn,
        page_id=page_id,
        image_id=image_id,
        alt_text=None,
        role=None,
        context_snippet=None,
        position=0,
    )


def _state(conn: sqlite3.Connection, scan_id: int, page_id: int, key: str) -> None:
    conn.execute(
        "INSERT INTO page_dom_states (page_id, scan_id, state_key, revealed_by, dom) "
        "VALUES (?, ?, ?, 'Menu', ?)",
        (page_id, scan_id, key, gzip.compress(b"<html></html>")),
    )


@pytest.fixture
def two_scans(tmp_db: sqlite3.Connection) -> tuple[int, int, dict[str, int]]:
    """Scan A with four pages of every load result, and scan B with one page."""
    scan_a = _scan(tmp_db, "http://a.test/")
    scan_b = _scan(tmp_db, "http://b.test/")
    ids = {
        "home": _page(tmp_db, scan_a, "http://a.test/", status=200, title="Home"),
        "about": _page(tmp_db, scan_a, "http://a.test/about", status=200, title=None),
        "gone": _page(tmp_db, scan_a, "http://a.test/gone", status=404, title="Not found"),
        "down": _page(tmp_db, scan_a, "http://a.test/down", status=None, title=None),
        "other": _page(tmp_db, scan_b, "http://b.test/", status=200, title="B home"),
    }
    _finding(tmp_db, scan_a, ids["home"], "main p")
    _finding(tmp_db, scan_a, ids["home"], "main h2")
    _finding(tmp_db, scan_a, ids["about"], "main p")
    _image(tmp_db, scan_a, ids["home"], "a")
    _state(tmp_db, scan_a, ids["home"], "menu|button|Menu")
    # Scan B's page carries evidence of every kind, none of which may show
    # up in scan A's list.
    for target in ("b1", "b2", "b3"):
        _finding(tmp_db, scan_b, ids["other"], target)
    _image(tmp_db, scan_b, ids["other"], "b")
    _state(tmp_db, scan_b, ids["other"], "dialog|button|Open")
    return scan_a, scan_b, ids


def test_load_result_names_each_outcome() -> None:
    assert load_result(None) == "not_loaded"
    assert load_result(404) == "error_status"
    assert load_result(500) == "error_status"
    assert load_result(200) == "loaded"
    assert load_result(301) == "loaded"


def test_lists_every_page_with_its_counts(
    tmp_db: sqlite3.Connection, two_scans: tuple[int, int, dict[str, int]]
) -> None:
    scan_a, _, ids = two_scans
    result = list_scan_pages(tmp_db, scan_a, sort="url_asc")

    assert result.scan_id == scan_a
    assert result.total == 4
    assert result.not_loaded_count == 1
    assert result.error_status_count == 1
    by_id = {row.page_id: row for row in result.pages}
    assert set(by_id) == {ids["home"], ids["about"], ids["gone"], ids["down"]}
    home = by_id[ids["home"]]
    assert (home.occurrence_count, home.image_count, home.page_state_count) == (2, 1, 1)
    assert home.title == "Home"
    assert home.load_result == "loaded"
    assert by_id[ids["about"]].occurrence_count == 1
    assert by_id[ids["gone"]].load_result == "error_status"
    assert by_id[ids["gone"]].status_code == 404
    down = by_id[ids["down"]]
    assert down.load_result == "not_loaded"
    assert down.status_code is None
    assert (down.occurrence_count, down.image_count, down.page_state_count) == (0, 0, 0)


def test_scan_a_never_lists_or_counts_scan_b(
    tmp_db: sqlite3.Connection, two_scans: tuple[int, int, dict[str, int]]
) -> None:
    scan_a, scan_b, ids = two_scans
    result_a = list_scan_pages(tmp_db, scan_a, limit=MAX_LIMIT)
    assert ids["other"] not in {row.page_id for row in result_a.pages}
    assert all(row.url.startswith("http://a.test/") for row in result_a.pages)
    # Scan B's three occurrences, image and page state count nowhere in A.
    assert sum(row.occurrence_count for row in result_a.pages) == 3
    assert sum(row.image_count for row in result_a.pages) == 1
    assert sum(row.page_state_count for row in result_a.pages) == 1

    result_b = list_scan_pages(tmp_db, scan_b)
    assert [row.page_id for row in result_b.pages] == [ids["other"]]
    assert result_b.total == 1
    assert (result_b.not_loaded_count, result_b.error_status_count) == (0, 0)
    assert result_b.pages[0].occurrence_count == 3


def test_a_child_row_filed_under_another_scan_is_not_counted(
    tmp_db: sqlite3.Connection, two_scans: tuple[int, int, dict[str, int]]
) -> None:
    """A finding is counted only when both its page and its scan match."""
    scan_a, scan_b, ids = two_scans
    _finding(tmp_db, scan_b, ids["home"], "stray")
    home = next(row for row in list_scan_pages(tmp_db, scan_a).pages if row.page_id == ids["home"])
    assert home.occurrence_count == 2


def test_counts_match_the_page_details_each_row_links_to(
    tmp_db: sqlite3.Connection, two_scans: tuple[int, int, dict[str, int]]
) -> None:
    scan_a, _, _ = two_scans
    for row in list_scan_pages(tmp_db, scan_a).pages:
        evidence = evaluation.get_page_evidence(tmp_db, scan_id=scan_a, page_id=row.page_id)
        assert evidence is not None
        assert row.occurrence_count == len(evidence["a11y_findings"])
        assert row.image_count == len(evidence["image_occurrences"])
        assert row.status_code == evidence["page"]["status_code"]


def test_unknown_or_empty_scan_lists_nothing(tmp_db: sqlite3.Connection) -> None:
    empty = _scan(tmp_db, "http://empty.test/")
    result = list_scan_pages(tmp_db, empty)
    assert (result.total, result.not_loaded_count, result.error_status_count) == (0, 0, 0)
    assert result.pages == []
    assert list_scan_pages(tmp_db, 999_999).pages == []


def test_problems_first_is_the_default_order(
    tmp_db: sqlite3.Connection, two_scans: tuple[int, int, dict[str, int]]
) -> None:
    scan_a, _, ids = two_scans
    order = [row.page_id for row in list_scan_pages(tmp_db, scan_a).pages]
    # Not loaded, then an error status, then the loaded pages by URL.
    assert order == [ids["down"], ids["gone"], ids["home"], ids["about"]]


@pytest.mark.parametrize(
    ("sort", "first"),
    [
        ("occurrences_desc", "home"),
        ("images_desc", "home"),
        ("states_desc", "home"),
        ("url_asc", "home"),
        ("url_desc", "gone"),
        ("load_asc", "home"),
    ],
)
def test_each_sort_orders_the_rows(
    tmp_db: sqlite3.Connection,
    two_scans: tuple[int, int, dict[str, int]],
    sort: str,
    first: str,
) -> None:
    scan_a, _, ids = two_scans
    result = list_scan_pages(tmp_db, scan_a, sort=sort)  # type: ignore[arg-type]
    assert result.pages[0].page_id == ids[first]
    assert result.sort == sort


def test_unknown_sort_is_refused(
    tmp_db: sqlite3.Connection, two_scans: tuple[int, int, dict[str, int]]
) -> None:
    scan_a, _, _ = two_scans
    with pytest.raises(ValueError, match="Unknown sort"):
        list_scan_pages(tmp_db, scan_a, sort="p.id; DROP TABLE pages")  # type: ignore[arg-type]


def test_limit_and_offset_page_through_without_repeats(
    tmp_db: sqlite3.Connection, two_scans: tuple[int, int, dict[str, int]]
) -> None:
    scan_a, _, _ = two_scans
    seen: list[int] = []
    for offset in range(0, 4, 3):
        page = list_scan_pages(tmp_db, scan_a, limit=3, offset=offset)
        assert page.total == 4
        seen += [row.page_id for row in page.pages]
    assert len(seen) == 4 == len(set(seen))


def test_limit_is_bounded(
    tmp_db: sqlite3.Connection, two_scans: tuple[int, int, dict[str, int]]
) -> None:
    scan_a, _, _ = two_scans
    assert list_scan_pages(tmp_db, scan_a, limit=10_000).limit == MAX_LIMIT
    assert list_scan_pages(tmp_db, scan_a, limit=0).limit == 1
    assert list_scan_pages(tmp_db, scan_a, offset=-5).offset == 0
