"""The pages a crawl knew about, and what it says about the ones it skipped.

Covers ``audit.db.crawl_coverage`` (migration 0032), the link sources in
``audit.crawler.links``, tracking-parameter normalization, and sitemap
reading restricted to the scanned host.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
import pytest
import respx

from audit.crawler.links import discover_links
from audit.crawler.sitemap import discover_sitemaps, read_site_sitemaps
from audit.crawler.url_policy import normalize
from audit.db import crawl_coverage

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0032_crawl_coverage"
BASE = "https://x.test/docs/"


def _scan(conn: sqlite3.Connection, seed: str = BASE) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES (?, 'running', 0, 0, '{}')",
        (seed,),
    )
    return int(cur.lastrowid or 0)


def _page(conn: sqlite3.Connection, scan_id: int, url: str) -> None:
    conn.execute(
        "INSERT INTO pages (scan_id, url_normalized, status_code, render_mode) "
        "VALUES (?, ?, 200, 'static')",
        (scan_id, url),
    )


# --- known pages and the unvisited counts --------------------------------------


def test_repeat_sightings_widen_what_is_known(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    first = crawl_coverage.note_known(
        tmp_db, scan_id=scan_id, url=BASE + "a.html", depth=1, via="sitemap"
    )
    again = crawl_coverage.note_known(
        tmp_db, scan_id=scan_id, url=BASE + "a.html", depth=4, via="link"
    )
    assert first.new and not again.new
    assert again.min_depth == 1
    row = tmp_db.execute("SELECT linked, in_sitemap FROM crawl_known_urls").fetchone()
    assert (row["linked"], row["in_sitemap"]) == (1, 1)


def test_visited_is_never_replaced(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    url = BASE + "a.html"
    crawl_coverage.set_outcome(tmp_db, scan_id=scan_id, url=url, outcome="visited")
    crawl_coverage.set_outcome(tmp_db, scan_id=scan_id, url=url, outcome="blocked")
    known = crawl_coverage.get_known(tmp_db, scan_id=scan_id, url=url)
    assert known is not None and known.outcome == "visited"


def test_finalize_counts_each_reason(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    note = crawl_coverage.note_known
    note(tmp_db, scan_id=scan_id, url=BASE, depth=0, via="link")
    crawl_coverage.set_outcome(tmp_db, scan_id=scan_id, url=BASE, outcome="visited")
    note(tmp_db, scan_id=scan_id, url=BASE + "waiting.html", depth=2, via="link")
    note(tmp_db, scan_id=scan_id, url=BASE + "deep.html", depth=11, via="link")
    crawl_coverage.set_outcome(
        tmp_db, scan_id=scan_id, url=BASE + "logout", outcome="blocked", depth=1
    )
    crawl_coverage.set_outcome(
        tmp_db, scan_id=scan_id, url=BASE + "dupe.html", outcome="duplicate", depth=1
    )
    # The slash-less spelling of a known folder is the same page, counted once.
    note(tmp_db, scan_id=scan_id, url=BASE + "guides/", depth=1, via="link")
    note(tmp_db, scan_id=scan_id, url=BASE + "guides", depth=1, via="link")

    counts = crawl_coverage.finalize(tmp_db, scan_id=scan_id, max_depth=10, page_limit_reached=True)

    assert (counts.page_limit, counts.depth_limit, counts.blocked) == (2, 1, 1)
    row = tmp_db.execute(
        "SELECT unvisited_page_limit, unvisited_depth_limit, unvisited_blocked "
        "FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    assert tuple(row) == (2, 1, 1)


def test_finalize_does_not_blame_the_page_limit_when_it_was_not_reached(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _scan(tmp_db)
    crawl_coverage.note_known(tmp_db, scan_id=scan_id, url=BASE + "left.html", depth=1, via="link")
    counts = crawl_coverage.finalize(
        tmp_db, scan_id=scan_id, max_depth=10, page_limit_reached=False
    )
    assert counts.page_limit == 0


def test_finalize_marks_pages_only_a_sitemap_led_to(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    for url, via in (
        (BASE + "only-sitemap.html", "sitemap"),
        (BASE + "both.html", "sitemap"),
        (BASE + "both.html", "link"),
        (BASE + "linked.html", "link"),
    ):
        crawl_coverage.note_known(tmp_db, scan_id=scan_id, url=url, depth=1, via=via)  # type: ignore[arg-type]
    for url in ("only-sitemap.html", "both.html", "linked.html"):
        _page(tmp_db, scan_id, BASE + url)

    crawl_coverage.finalize(tmp_db, scan_id=scan_id, max_depth=10, page_limit_reached=False)

    marked = {
        r["url_normalized"]
        for r in tmp_db.execute("SELECT url_normalized FROM pages WHERE found_only_in_sitemap = 1")
    }
    assert marked == {BASE + "only-sitemap.html"}


def test_one_scan_never_counts_another_scans_pages(tmp_db: sqlite3.Connection) -> None:
    scan_a = _scan(tmp_db)
    scan_b = _scan(tmp_db)
    crawl_coverage.note_known(tmp_db, scan_id=scan_b, url=BASE + "b.html", depth=11, via="link")
    _page(tmp_db, scan_b, BASE + "b.html")
    counts = crawl_coverage.finalize(tmp_db, scan_id=scan_a, max_depth=10, page_limit_reached=True)
    assert (counts.page_limit, counts.depth_limit, counts.blocked) == (0, 0, 0)
    assert (
        crawl_coverage.page_for_address(
            tmp_db, scan_id=scan_a, url=BASE + "b.html", raw=BASE + "b.html"
        )
        is None
    )


def test_directory_twin_only_for_folder_like_paths() -> None:
    assert crawl_coverage.directory_twin("https://x.test/docs/guides") == (
        "https://x.test/docs/guides/"
    )
    assert crawl_coverage.directory_twin("https://x.test/docs/a.html") is None
    assert crawl_coverage.directory_twin("https://x.test/docs/") is None


def test_migration_rolls_back_and_forward_cleanly(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    crawl_coverage.note_known(tmp_db, scan_id=scan_id, url=BASE, depth=0, via="link")

    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    tables = {r[0] for r in tmp_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "crawl_known_urls" not in tables
    scan_columns = {r[1] for r in tmp_db.execute("PRAGMA table_info(scans)")}
    assert "unvisited_page_limit" not in scan_columns

    tmp_db.executescript(MIGRATION.with_suffix(".sql").read_text())
    assert tmp_db.execute("SELECT COUNT(*) FROM crawl_known_urls").fetchone()[0] == 0
    page_columns = {r[1] for r in tmp_db.execute("PRAGMA table_info(pages)")}
    assert "found_only_in_sitemap" in page_columns


# --- where a page leads -------------------------------------------------------


def test_discover_links_reads_areas_buttons_and_button_only_forms() -> None:
    body = b"""
    <a href="a.html">A</a>
    <a href="javascript:void(0)">Script</a>
    <map><area href="north.html" alt="North"></map>
    <button onclick="location.href='calc.html'">Calculator</button>
    <button onclick="window.location = '/x/y.html'">Y</button>
    <span onclick="window.open('popup.html')">Popup</span>
    <form action="results.html">
      <input type="hidden" name="view" value="all"><button>Go</button>
    </form>
    <form action="search.html"><input name="q"><button>Search</button></form>
    <form action="delete.html" method="post"><button>Delete</button></form>
    <form action="pick.html"><select name="s"></select><button>Pick</button></form>
    """
    assert discover_links(BASE, body) == [
        BASE + "a.html",
        BASE + "north.html",
        BASE + "calc.html",
        "https://x.test/x/y.html",
        BASE + "popup.html",
        BASE + "results.html?view=all",
    ]


def test_discover_links_survives_unreadable_markup() -> None:
    assert discover_links(BASE, b"") == []


# --- one page, many addresses -------------------------------------------------


def test_normalize_drops_tracking_parameters_only() -> None:
    assert normalize("https://x.test/a?utm_source=mail&UTM_Medium=e&id=3&fbclid=z") == (
        "https://x.test/a?id=3"
    )
    assert normalize("https://x.test/a?page=2&ref=nav") == "https://x.test/a?page=2&ref=nav"


# --- sitemaps -----------------------------------------------------------------

_URLSET = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</urlset>"""
_INDEX = """<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</sitemapindex>"""


def _urls(*locs: str) -> str:
    return _URLSET.format("".join(f"<url><loc>{loc}</loc></url>" for loc in locs))


def test_discover_sitemaps_adds_the_scanned_folder() -> None:
    assert discover_sitemaps(BASE, [], path_prefix="/docs/") == [
        "https://x.test/sitemap.xml",
        "https://x.test/sitemap_index.xml",
        "https://x.test/docs/sitemap.xml",
    ]


@pytest.mark.asyncio
@respx.mock
async def test_read_site_sitemaps_reads_robots_lines_and_stays_on_the_host() -> None:
    respx.get("https://x.test/declared.xml").mock(
        return_value=httpx.Response(
            200,
            content=_INDEX.format(
                "<sitemap><loc>https://x.test/child.xml</loc></sitemap>"
                "<sitemap><loc>https://other.test/child.xml</loc></sitemap>"
            ),
        )
    )
    respx.get("https://x.test/child.xml").mock(
        return_value=httpx.Response(200, content=_urls("https://x.test/docs/c.html"))
    )
    respx.get("https://x.test/sitemap.xml").mock(
        return_value=httpx.Response(
            200, content=_urls("https://x.test/docs/s.html", "https://x.test/docs/c.html")
        )
    )
    respx.get("https://x.test/sitemap_index.xml").mock(return_value=httpx.Response(404))
    other = respx.get("https://other.test/child.xml").mock(
        return_value=httpx.Response(200, content=_urls("https://other.test/z"))
    )
    elsewhere = respx.get("https://elsewhere.test/robots-said.xml").mock(
        return_value=httpx.Response(200, content=_urls("https://x.test/docs/e.html"))
    )

    async with httpx.AsyncClient() as client:
        urls = await read_site_sitemaps(
            client,
            "https://x.test/",
            ["https://x.test/declared.xml", "https://elsewhere.test/robots-said.xml"],
        )

    assert urls == ["https://x.test/docs/c.html", "https://x.test/docs/s.html"]
    assert not other.called
    assert not elsewhere.called


@pytest.mark.asyncio
@respx.mock
async def test_read_site_sitemaps_stops_at_the_cap() -> None:
    respx.get("https://x.test/sitemap.xml").mock(
        return_value=httpx.Response(200, content=_urls(*(f"https://x.test/{i}" for i in range(9))))
    )
    respx.get("https://x.test/sitemap_index.xml").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        urls = await read_site_sitemaps(client, "https://x.test/", [], max_urls=3)
    assert len(urls) == 3
