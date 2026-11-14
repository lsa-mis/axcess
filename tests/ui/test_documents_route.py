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
# The two closed notes under the table, with Issues' titles.
CHECKED = "What was checked"
LABELS = 'What "Mostly sure", "Not sure" and the other labels mean'
CAVEAT = (
    "Results for an expert to review. They do not prove that the files meet "
    "accessibility standards."
)


async def _open_notes(page: Any) -> None:
    from playwright.async_api import expect

    for name in (CHECKED, LABELS):
        button = page.get_by_role("button", name=name, exact=True)
        await button.click()
        await expect(button).to_have_attribute("aria-expanded", "true")


async def _title_fits_beside_its_fact(page: Any) -> None:
    """The closed "What was checked" row's fact leaves its title room: at
    most two lines, not one word a line."""
    title = page.get_by_role("button", name=CHECKED, exact=True).locator("span")
    lines = await title.evaluate(
        "(el) => Math.round(el.getBoundingClientRect().height"
        " / parseFloat(getComputedStyle(el).lineHeight))"
    )
    assert lines <= 2, lines


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


# -- where a file is linked on a page (the inspector's marks) ---------------

_HOME_COPY = b"""<!doctype html><html><body>
<a href="/files/permit-form.pdf">Apply for a permit (PDF)</a>
<a href="#top">Top</a>
<a href="http://example.com/files/no-title.pdf">Price list (PDF)</a>
<noscript><a href="/files/permit-form.pdf">Not shown</a></noscript>
<a href="files/permit-form.pdf">Apply again</a>
<iframe src="/files/map.pdf" title="Course map"></iframe>
</body></html>"""


def _save_copy(db_path: Path, scan_id: int, url: str, html: bytes | None) -> int:
    import gzip

    with sqlite3.connect(db_path) as conn:
        page_id = _page_id(conn, scan_id, url)
        conn.execute(
            "UPDATE pages SET rendered_html = ?, final_url = ? WHERE id = ?",
            (gzip.compress(html) if html is not None else None, url, page_id),
        )
    return page_id


def _file_id(client: TestClient, scan_id: int, name: str) -> int:
    body = client.get(f"/api/scans/{scan_id}/documents?limit=200").json()
    return int(next(f["file_id"] for f in body["files"] if f["name"] == name))


def test_each_link_to_the_file_is_placed_as_the_browser_counts_it(
    client: TestClient, seeded_db: tuple[Path, Path, int], documents: int
) -> None:
    home = _save_copy(seeded_db[0], documents, HOME, _HOME_COPY)
    form = _file_id(client, documents, "permit-form.pdf")
    body = client.get(f"/api/scans/{documents}/documents/{form}/pages/{home}").json()
    assert body["saved_copy"] is True
    assert body["name"] == "permit-form.pdf"
    # Both links that resolve to the file, relative or not; never the copy
    # in <noscript>, which the inspector does not count either, and never
    # the fragment link.
    assert body["places"] == [
        {"selector": "a", "index": 0, "total": 4},
        {"selector": "a", "index": 3, "total": 4},
    ]
    assert [ref["how"] for ref in body["refs"]] == ["link"]
    frame = _file_id(client, documents, "map.pdf")
    body = client.get(f"/api/scans/{documents}/documents/{frame}/pages/{home}").json()
    assert body["places"] == [{"selector": "iframe", "index": 0, "total": 1}]


def test_a_link_shown_only_after_a_click_has_no_place_and_says_why(
    client: TestClient, seeded_db: tuple[Path, Path, int], documents: int
) -> None:
    about = _save_copy(
        seeded_db[0], documents, ABOUT, b"<html><body><a href='/'>Home</a></body></html>"
    )
    form = _file_id(client, documents, "permit-form.pdf")
    body = client.get(f"/api/scans/{documents}/documents/{form}/pages/{about}").json()
    assert (body["saved_copy"], body["places"]) == (True, [])
    assert [(r["how"], r["revealed_by"]) for r in body["refs"]] == [("revealed_link", "More forms")]


def test_a_page_with_no_saved_copy_says_so(
    client: TestClient, seeded_db: tuple[Path, Path, int], documents: int
) -> None:
    home = _save_copy(seeded_db[0], documents, HOME, None)
    form = _file_id(client, documents, "permit-form.pdf")
    body = client.get(f"/api/scans/{documents}/documents/{form}/pages/{home}").json()
    assert (body["saved_copy"], body["places"]) == (False, [])


def test_a_file_is_looked_up_only_on_its_own_reports_pages(
    client: TestClient, seeded_db: tuple[Path, Path, int], documents: int
) -> None:
    home = _save_copy(seeded_db[0], documents, HOME, _HOME_COPY)
    with sqlite3.connect(seeded_db[0]) as conn:
        conn.row_factory = sqlite3.Row
        other = int(
            conn.execute(
                "INSERT INTO scans (seed_url, status, config_json) "
                "VALUES ('http://example.com/', 'completed', '{\"linked_files_enabled\": true}')"
            ).lastrowid
            or 0
        )
        their_page = repo.upsert_page(
            conn,
            scan_id=other,
            url_normalized=HOME,
            status_code=200,
            title="Home",
            render_mode="js",
            html_hash=None,
        )
        their_file = _file(
            conn,
            other,
            "http://example.com/files/permit-form.pdf",
            "pdf",
            store.CheckResult("not_sure"),
            [(their_page, "link", "Apply", None)],
        )
    form = _file_id(client, documents, "permit-form.pdf")
    budget = _file_id(client, documents, "budget.xls")
    # Another report's file through this report, this report's file on
    # another report's page, and a page that does not link to the file.
    assert (
        client.get(f"/api/scans/{documents}/documents/{their_file}/pages/{home}").status_code == 404
    )
    assert (
        client.get(f"/api/scans/{documents}/documents/{form}/pages/{their_page}").status_code == 404
    )
    assert client.get(f"/api/scans/{other}/documents/{form}/pages/{their_page}").status_code == 404
    assert client.get(f"/api/scans/{documents}/documents/{budget}/pages/{home}").status_code == 404
    assert client.get(f"/api/scans/999999/documents/{form}/pages/{home}").status_code == 404


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

    # As on Issues: nothing under the heading, and the counts in the row of
    # summary numbers over the table, every value shown.
    await expect(
        page.locator("main header").get_by_text(re.compile(r"documents ·|expert to review"))
    ).to_have_count(0)
    numbers = page.locator("main dl").filter(
        has=page.get_by_role("term").filter(has_text=re.compile(r"^Documents$"))
    )
    await expect(numbers.get_by_role("term")).to_have_text(
        ["Documents", "Mostly sure", "Not sure", "Could not check"]
    )
    await expect(numbers.get_by_role("definition")).to_have_text(["7", "2", "1", "4"])
    numbers_box = await numbers.bounding_box()
    table_box = await table.bounding_box()
    assert numbers_box and table_box
    assert numbers_box["y"] + numbers_box["height"] <= table_box["y"], (numbers_box, table_box)
    # Nothing to read between the numbers and the table: no caveat, key or
    # order line there, as on Issues. The order is in the caption.
    await expect(page.get_by_text(CAVEAT)).to_be_hidden()
    await expect(page.get_by_text(re.compile(r"recommended order", re.I))).to_have_count(0)
    await expect(table).to_have_accessible_name(
        f"Documents linked from report #{scan_id}, "
        "Mostly sure first, then Not sure, then Could not check"
    )

    # Under the table, Issues' two closed notes, in Issues' order; the
    # closed "What was checked" row shows its one fact.
    checked = page.get_by_role("button", name=CHECKED, exact=True)
    labels = page.get_by_role("button", name=LABELS, exact=True)
    for button in (checked, labels):
        await expect(button).to_have_attribute("aria-expanded", "false")
    checked_box = await checked.bounding_box()
    labels_box = await labels.bounding_box()
    assert checked_box and labels_box
    assert table_box["y"] + table_box["height"] <= checked_box["y"] < labels_box["y"]
    await expect(page.get_by_text("Only PDFs checked", exact=True)).to_be_visible()

    # Opened by keyboard, "What was checked" holds the caveat, what is
    # listed, the privacy fact and the limits, each said once.
    await checked.focus()
    await page.keyboard.press("Enter")
    panel = page.get_by_role("region", name=CHECKED)
    for text in (
        CAVEAT,
        "Axcess checks only the PDF files.",
        "To check a PDF, Axcess downloaded it to this computer once. It kept the results, "
        "not the file.",
        "The list can miss files.",
        "Some reports do not look for documents",
    ):
        await expect(panel.get_by_text(text, exact=False)).to_be_visible()
        await expect(page.get_by_text(text, exact=False)).to_have_count(1)
    # The labels note: what is counted, the How sure values as the table's
    # tags, and the order as its own section, as Issues explains Priority.
    await labels.focus()
    await page.keyboard.press("Enter")
    glossary = page.get_by_role("region", name=LABELS)
    await expect(glossary.get_by_role("heading", level=3)).to_have_text(
        [
            "The numbers: what is counted",
            "Accessibility problems? How sure Axcess is that a file has them",
            "The order: which files to look at first",
        ]
    )
    await expect(glossary.get_by_role("term")).to_have_text(
        [
            "Document",
            "Mostly sure",
            "Not sure",
            "Could not check",
            "1. Accessibility problems?",
            "2. Pages it appears on",
            "3. A form to fill in",
            "4. How serious the problem is",
        ]
    )
    await expect(glossary).to_contain_text(
        "Mostly sure first, then Not sure, then Could not check."
    )
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
    await expect(form).to_contain_text("This site")
    await expect(form).to_contain_text("Not tagged")
    await expect(form).to_contain_text("Has a form to fill in")
    # The pages by title only: no address, no link text, no count line.
    await expect(form).not_to_contain_text("link to it.")
    await expect(form).not_to_contain_text("Link text")
    await expect(form).not_to_contain_text(HOME)
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
    await expect(rows.nth(6)).to_contain_text("docs.google.com")
    await expect(rows.nth(6)).to_contain_text("Another site")
    # The columns say what each value is; "How sure" alone did not.
    await expect(table.get_by_role("columnheader")).to_have_text(
        [
            "Document",
            "Type",
            "Site",
            "Accessibility problems?",
            "What Axcess found",
            "Pages it appears on",
        ]
    )
    # The row header is the file's name only: a screen reader reads it with
    # every cell, so no address, site or form line is in it.
    await expect(table.get_by_role("rowheader").nth(6)).to_have_text(
        re.compile(r"^Meeting notes\b"), use_inner_text=True
    )
    await expect(table.get_by_role("rowheader").get_by_text("docs.google.com")).to_have_count(0)
    await expect(table.get_by_role("rowheader").get_by_text("form to fill in")).to_have_count(0)
    await expect(table.get_by_role("rowheader").get_by_text("http://")).to_have_count(0)
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
    await _title_fits_beside_its_fact(page)
    # The notes open, so axe and the reflow check reach their text too.
    await _open_notes(page)
    for tags in (_AXE_TAGS_AA, None):
        violations = await _run_axe(page, tags)
        assert not violations, f"{theme} {width}px:\n{_render_violations(violations)}"
    # Nothing but the table scrolls sideways (SC 1.4.10 Reflow).
    assert await page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )


@on_module_loop
@pytest.mark.parametrize("width", [1280, 320])
async def test_a_report_that_did_not_look_says_so_once(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any, width: int
) -> None:
    """The empty table says it and points to the note, which says why; the
    sentence is never shown twice, and there are no numbers to show."""
    from playwright.async_api import expect

    base, scan_id = live_server
    page = await new_page(viewport={"width": width, "height": 800})
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    message = page.get_by_text(
        "This report did not look for documents. See why in “What was checked”, below this table."
    )
    await expect(message).to_be_visible()
    await expect(page.get_by_text("Not looked for", exact=True)).to_be_visible()
    await _title_fits_beside_its_fact(page)
    await expect(
        page.get_by_role("term").filter(has_text=re.compile(r"^Documents?$"))
    ).to_have_count(0)
    await _open_notes(page)
    await expect(page.get_by_text("This report did not look for documents")).to_have_count(1)
    await expect(page.get_by_role("region", name=CHECKED)).to_contain_text(
        "Some reports do not look for documents: reports made before Axcess could find "
        "documents, and scans that sign in to a site."
    )
    for tags in (_AXE_TAGS_AA, None):
        violations = await _run_axe(page, tags)
        assert not violations, f"{width}px:\n{_render_violations(violations)}"
    assert await page.evaluate(_TEXT_LAYOUT) == {"long": [], "tight": []}
    assert await page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )


@on_module_loop
async def test_a_report_that_found_none_says_what_that_does_not_mean(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    """As Issues' empty table does: no rows is not a clean result."""
    from playwright.async_api import expect

    db_path, _, scan_id = seeded_db
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE scans SET config_json = json_set(config_json, '$.linked_files_enabled', "
            "json('true')) WHERE id = ?",
            (scan_id,),
        )
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 800})
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    await expect(
        page.get_by_text(
            "The scan found no links to documents on the pages it visited. That does not mean "
            "the site has none, because the list can miss files. See “What was checked”, below "
            "this table."
        )
    ).to_be_visible()
    numbers = page.locator("main dl").filter(
        has=page.get_by_role("term").filter(has_text=re.compile(r"^Documents$"))
    )
    await expect(numbers.get_by_role("definition")).to_have_text(["0", "0", "0", "0"])
    await expect(page.get_by_text("Only PDFs checked", exact=True)).to_be_visible()
    assert await page.evaluate(_TEXT_LAYOUT) == {"long": [], "tight": []}


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
    await _open_notes(page)
    assert await page.evaluate(_SMALL_TARGETS) == []
    assert await page.evaluate(_SHARED_NAMES) == []
    layout = await page.evaluate(_TEXT_LAYOUT)
    assert layout == {"long": [], "tight": []}
    controls = await page.evaluate(_COLLECT)
    assert not [c for c in controls if vague(c["text"], in_nav=c["inNav"])], controls


_MARKED_COPY = b"""<!doctype html><html><head><title>Home</title></head><body>
<a id="first" href="/files/permit-form.pdf">Apply for a permit (PDF)</a>
<p>Text between the links.</p>
<a id="price" href="/files/no-title.pdf">Price list (PDF)</a>
<a id="second" href="files/permit-form.pdf">Apply again</a>
</body></html>"""


@on_module_loop
async def test_the_inspector_marks_the_links_to_the_document(
    documents: int,
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Opened from a Documents row, the inspector outlines each link on the
    page to that file, and only those, and says what it marked in words."""
    from playwright.async_api import expect

    _save_copy(seeded_db[0], documents, HOME, _MARKED_COPY)
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
        row = page.get_by_role("table").locator("tbody tr").first
        link = row.get_by_role("link", name=re.compile(r"^Home\b.*page inspector"))
        await expect(link).to_have_accessible_name(
            re.compile(
                r"^Home\s*, opens in the page inspector, marks the link to permit-form\.pdf$"
            )
        )
        await link.focus()
        await page.keyboard.press("Enter")
        await page.wait_for_url(re.compile(r"/inspect\?.*file="))

        group = page.get_by_role("group", name="Links to this document", exact=True)
        await expect(group.get_by_role("status")).to_have_text(
            re.compile(r"^Link to this document 1 of 2")
        )
        await expect(
            page.get_by_text(
                "Dashed red outlines mark the 2 links to “permit-form.pdf” on this page.",
                exact=False,
            )
        ).to_be_visible()
        # No issue wording: a link to a document flags nothing.
        await expect(page.get_by_text("issue type has no element")).to_have_count(0)
        await expect(page.get_by_text("flagged element", exact=False)).to_have_count(0)

        frame = page.frame_locator("iframe[title^='Saved copy']")
        await expect(frame.locator("#first")).to_have_css("outline-color", "rgb(0, 39, 76)")
        await expect(frame.locator("#second")).to_have_css("outline-color", "rgb(190, 0, 30)")
        await expect(frame.locator("#price")).not_to_have_css("outline-style", "dashed")

        violations = await _run_axe(page, _AXE_TAGS_AA)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


@on_module_loop
async def test_the_inspector_says_why_a_revealed_link_is_not_marked(
    documents: int,
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    from playwright.async_api import expect

    about = _save_copy(
        seeded_db[0], documents, ABOUT, b"<html><body><a href='/'>Home</a></body></html>"
    )
    base, scan_id = live_server
    response = await (await new_page()).request.get(
        f"{base}/api/scans/{scan_id}/documents?limit=200"
    )
    body = await response.json()
    form = next(f["file_id"] for f in body["files"] if f["name"] == "permit-form.pdf")
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(
            f"{base}/app/scans/{scan_id}/pages/{about}/inspect?file={form}",
            wait_until="networkidle",
        )
        await expect(
            page.get_by_text(
                "The link to “permit-form.pdf” appears only after pressing “More forms”. "
                "This copy shows the page at page load, so the link is not in it."
            )
        ).to_be_visible()
        await expect(page.get_by_text("issue type has no element")).to_have_count(0)
    finally:
        await page.context.close()
