"""The Documents tab: ``GET /api/scans/{id}/documents`` and the screen.

The seeded report gets one file of each kind the screen must show: two
Mostly sure PDFs (one a form linked from two pages, one also revealed by a
click), a Not sure PDF shown in a frame, and four that could not be checked
for four different reasons. The API tests pin the order, the counts and scan
isolation; the browser tests drive the tab by keyboard and run axe and the
AAA checks the other screens get, on the populated table.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from audit.db import linked_files as store
from audit.db import repo

from .test_accessibility_axe import _AXE_TAGS_AA, _render_violations, _run_axe
from .test_control_text_purpose import _COLLECT, vague
from .test_wcag_aaa import _SHARED_NAMES, _SMALL_TARGETS, _TEXT_LAYOUT

pytestmark = pytest.mark.ui
# The browser tests share the module's browser, so they run on its loop.
on_module_loop = pytest.mark.asyncio(loop_scope="module")

HOME = "http://example.com/"
ABOUT = "http://example.com/about"


def _file(
    conn: sqlite3.Connection,
    scan_id: int,
    url: str,
    file_type: str,
    result: store.CheckResult | None,
    refs: list[tuple[int, str, str, str | None]],
    *,
    off_site: bool = False,
) -> int:
    file_id = store.upsert_file(
        conn,
        scan_id=scan_id,
        url=url,
        file_type=file_type,  # type: ignore[arg-type]
        found_by="extension",
        off_site=off_site,
    )
    assert file_id is not None
    if result is not None:
        store.set_result(conn, scan_id=scan_id, file_id=file_id, result=result)
    for page_id, how, text, revealed_by in refs:
        store.add_ref(
            conn,
            scan_id=scan_id,
            file_id=file_id,
            page_id=page_id,
            how=how,  # type: ignore[arg-type]
            link_text=text,
            revealed_by=revealed_by,
        )
    return file_id


def _page_id(conn: sqlite3.Connection, scan_id: int, url: str) -> int:
    row = conn.execute(
        "SELECT id FROM pages WHERE scan_id = ? AND url_normalized = ?", (scan_id, url)
    ).fetchone()
    return int(row[0])


def _seed_documents(db_path: Path, scan_id: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE scans SET config_json = json_set(config_json, '$.linked_files_enabled', "
            "json('true')) WHERE id = ?",
            (scan_id,),
        )
        home = _page_id(conn, scan_id, HOME)
        about = _page_id(conn, scan_id, ABOUT)
        _file(
            conn,
            scan_id,
            "http://example.com/files/no-title.pdf",
            "pdf",
            store.CheckResult("mostly_sure", failed_checks=["no_title"], http_status=200),
            [(home, "link", "Price list (PDF)", None)],
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/permit-form.pdf",
            "pdf",
            store.CheckResult(
                "mostly_sure",
                failed_checks=["not_tagged", "no_language"],
                is_form=True,
                http_status=200,
            ),
            [
                (home, "link", "Apply for a permit (PDF)", None),
                (about, "revealed_link", "Permit form", "More forms"),
            ],
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/map.pdf",
            "pdf",
            store.CheckResult("not_sure", http_status=200),
            [(home, "iframe", "Course map", None)],
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/report.docx",
            "docx",
            None,
            [(home, "link", "Committee report (Word)", None)],
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/budget.xls",
            "xls",
            None,
            [(about, "link", "Budget 2003 (Excel)", None)],
        )
        _file(
            conn,
            scan_id,
            "https://docs.google.com/document/d/abc/edit",
            "google_doc",
            None,
            [(about, "link", "Meeting notes", None)],
            off_site=True,
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/missing.pdf",
            "pdf",
            store.CheckResult("could_not_check", "http_error", http_status=404),
            [(home, "link", "Old newsletter (PDF)", None)],
        )


@pytest.fixture
def documents(seeded_db: tuple[Path, Path, int]) -> int:
    db_path, _, scan_id = seeded_db
    _seed_documents(db_path, scan_id)
    return scan_id


def test_files_come_in_the_recommended_order(client: TestClient, documents: int) -> None:
    body = client.get(f"/api/scans/{documents}/documents").json()
    assert body["recorded"] is True
    assert body["total"] == 7
    assert body["counts"] == {"mostly_sure": 2, "not_sure": 1, "could_not_check": 4}
    assert [(f["name"], f["status"], f["reason"]) for f in body["files"]] == [
        # Mostly sure: the form on two pages before the one on one page.
        ("permit-form.pdf", "mostly_sure", None),
        ("no-title.pdf", "mostly_sure", None),
        ("map.pdf", "not_sure", None),
        # Could not check: one page each, so by address.
        ("budget.xls", "could_not_check", "old_format"),
        ("missing.pdf", "could_not_check", "http_error"),
        ("report.docx", "could_not_check", "type_not_checked_yet"),
        # A Google address has no file name, so the link's text names it.
        ("Meeting notes", "could_not_check", "google_file"),
    ]
    form = body["files"][0]
    assert form["failed_checks"] == ["not_tagged", "no_language"]
    assert (form["is_form"], form["referring_page_count"]) == (True, 2)
    assert form["refs"] == [
        {
            "page_id": form["refs"][0]["page_id"],
            "page_url": HOME,
            "page_title": "Home",
            "how": "link",
            "link_text": "Apply for a permit (PDF)",
            "revealed_by": None,
        },
        {
            "page_id": form["refs"][1]["page_id"],
            "page_url": ABOUT,
            "page_title": "About",
            "how": "revealed_link",
            "link_text": "Permit form",
            "revealed_by": "More forms",
        },
    ]


def test_a_report_that_did_not_look_says_so(client: TestClient, seeded_db: Any) -> None:
    _, _, scan_id = seeded_db
    body = client.get(f"/api/scans/{scan_id}/documents").json()
    assert (body["recorded"], body["total"], body["files"]) == (False, 0, [])


def test_a_file_still_pending_shows_as_not_checked(
    client: TestClient, seeded_db: tuple[Path, Path, int], documents: int
) -> None:
    with sqlite3.connect(seeded_db[0]) as conn:
        _file(conn, documents, "http://example.com/files/late.pdf", "pdf", None, [])
    body = client.get(f"/api/scans/{documents}/documents?limit=200").json()
    late = next(f for f in body["files"] if f["name"] == "late.pdf")
    assert (late["status"], late["reason"], late["refs"]) == ("could_not_check", "not_checked", [])
    assert body["counts"]["could_not_check"] == 5


def test_files_are_paged(client: TestClient, documents: int) -> None:
    first = client.get(f"/api/scans/{documents}/documents?limit=3&offset=0").json()
    rest = client.get(f"/api/scans/{documents}/documents?limit=3&offset=3").json()
    names = [f["name"] for f in first["files"] + rest["files"]]
    assert len(names) == 6 and len(set(names)) == 6
    assert first["total"] == rest["total"] == 7


@pytest.mark.parametrize("query", ["limit=201", "limit=0", "offset=-1"])
def test_out_of_bounds_requests_are_refused(client: TestClient, documents: int, query: str) -> None:
    assert client.get(f"/api/scans/{documents}/documents?{query}").status_code == 422


def test_unknown_scan_is_404(client: TestClient) -> None:
    assert client.get("/api/scans/999999/documents").status_code == 404


def test_one_report_never_lists_another_reports_files(
    client: TestClient, seeded_db: tuple[Path, Path, int], documents: int
) -> None:
    with sqlite3.connect(seeded_db[0]) as conn:
        conn.row_factory = sqlite3.Row
        other = int(
            conn.execute(
                "INSERT INTO scans (seed_url, status, config_json) "
                "VALUES ('http://other.example/', 'completed', '{\"linked_files_enabled\": true}')"
            ).lastrowid
            or 0
        )
        page = repo.upsert_page(
            conn,
            scan_id=other,
            url_normalized="http://other.example/",
            status_code=200,
            title="Other",
            render_mode="js",
            html_hash=None,
        )
        _file(
            conn,
            other,
            "http://other.example/secret.pdf",
            "pdf",
            store.CheckResult("not_sure"),
            [(page, "link", "Secret", None)],
        )
    mine = client.get(f"/api/scans/{documents}/documents?limit=200").json()
    assert "secret.pdf" not in {f["name"] for f in mine["files"]}
    theirs = client.get(f"/api/scans/{other}/documents").json()
    assert [f["name"] for f in theirs["files"]] == ["secret.pdf"]
    assert theirs["files"][0]["refs"][0]["page_url"] == "http://other.example/"


# -- the screen -------------------------------------------------------------


@on_module_loop
async def test_the_tab_works_by_keyboard_and_lists_each_file(
    documents: int, live_server: tuple[str, int], new_page: Any
) -> None:
    from playwright.async_api import expect

    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    tab = page.get_by_role("navigation", name="Report views").get_by_role("link", name="Documents")
    # Reached and opened with the keyboard alone.
    for _ in range(30):
        await page.keyboard.press("Tab")
        if await tab.evaluate("el => el === document.activeElement"):
            break
    else:
        pytest.fail("Tab never reached the Documents tab")
    await page.keyboard.press("Enter")
    await page.wait_for_url(f"**/app/scans/{scan_id}/documents")
    await expect(page.get_by_role("heading", name="Documents", level=1)).to_be_visible()
    await expect(tab).to_have_attribute("aria-current", "page")
    assert await page.title() == "Documents · Axcess"

    table = page.get_by_role("table", name=f"Documents linked from report #{scan_id}", exact=False)
    rows = table.locator("tbody tr")
    await expect(rows).to_have_count(7)
    names = [
        "permit-form.pdf",
        "no-title.pdf",
        "map.pdf",
        "budget.xls",
        "missing.pdf",
        "report.docx",
        "Meeting notes",
    ]
    await expect(table.get_by_role("rowheader")).to_have_text(
        [re.compile(rf"^{re.escape(name)}\b") for name in names], use_inner_text=True
    )
    form = rows.nth(0)
    await expect(form).to_contain_text("Mostly sure")
    await expect(form).to_contain_text("Not tagged")
    await expect(form).to_contain_text("Has a form to fill in")
    await expect(form).to_contain_text("2 pages link to it.")
    await expect(form).to_contain_text("Appears only after pressing “More forms”")
    # Not sure says what a person must still check: never read as a pass.
    await expect(rows.nth(2)).to_contain_text("Not sure")
    await expect(rows.nth(2)).to_contain_text(
        "the reading order, the image descriptions (alt text) and the table headers"
    )
    await expect(rows.nth(2)).to_contain_text("Shown inside the page (in a frame)")
    # "Does not check yet" and "cannot check" read differently.
    await expect(rows.nth(3)).to_contain_text("Axcess cannot check this file type.")
    await expect(rows.nth(4)).to_contain_text("(HTTP 404)")
    await expect(rows.nth(5)).to_contain_text("Axcess does not check this file type yet.")
    await expect(rows.nth(6)).to_contain_text("Axcess cannot check files kept in Google")
    await expect(rows.nth(6)).to_contain_text("On another site")
    # The file link names the file and says it opens a new tab.
    link = table.get_by_role("link", name=re.compile(r"^permit-form\.pdf\s*, opens the file"))
    await expect(link).to_have_attribute("href", "http://example.com/files/permit-form.pdf")
    await expect(link).to_have_attribute("target", "_blank")

    # Keyboard order follows the reading order: the tab, then the first
    # file, then the first page that links to it, each with a visible focus.
    await tab.focus()
    stops = []
    for _ in range(4):
        await page.keyboard.press("Tab")
        stops.append(
            await page.evaluate(
                """() => {
                    const el = document.activeElement;
                    const s = getComputedStyle(el);
                    return {
                        text: el.innerText.replace(/\\s+/g, ' ').trim(),
                        ring: (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0)
                            || s.boxShadow !== 'none',
                    };
                }"""
            )
        )
    texts = [stop["text"] for stop in stops]
    first_file = next(i for i, t in enumerate(texts) if t.startswith("permit-form.pdf"))
    first_page = next(i for i, t in enumerate(texts) if t.startswith("Home"))
    assert first_file < first_page, texts
    assert all(stop["ring"] for stop in stops), stops


@on_module_loop
@pytest.mark.parametrize("width", [1280, 320])
@pytest.mark.parametrize("theme", ["light", "dark"])
async def test_the_populated_tab_passes_axe(
    documents: int, live_server: tuple[str, int], new_page: Any, theme: str, width: int
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": width, "height": 800})
    await page.add_init_script(
        f"localStorage.setItem('axcess.preferences', JSON.stringify({{theme: '{theme}'}}))"
    )
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    await page.get_by_role("table").wait_for()
    for tags in (_AXE_TAGS_AA, None):
        violations = await _run_axe(page, tags)
        assert not violations, f"{theme} {width}px:\n{_render_violations(violations)}"
    # Nothing but the table scrolls sideways (SC 1.4.10 Reflow).
    assert await page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )


@on_module_loop
async def test_the_populated_tab_meets_the_aaa_checks(
    documents: int, live_server: tuple[str, int], new_page: Any
) -> None:
    """44 px targets, one place per link name, short running text, and
    controls whose own words say what they do."""
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 720})
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    await page.get_by_role("table").wait_for()
    assert await page.evaluate(_SMALL_TARGETS) == []
    assert await page.evaluate(_SHARED_NAMES) == []
    layout = await page.evaluate(_TEXT_LAYOUT)
    assert layout == {"long": [], "tight": []}
    controls = await page.evaluate(_COLLECT)
    assert not [c for c in controls if vague(c["text"], in_nav=c["inNav"])], controls
