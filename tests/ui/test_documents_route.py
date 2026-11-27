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


FIXTURE_PDFS = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "documents" / "files"


def _first_page(blob_dir: Path) -> tuple[str, str]:
    """Draw and store a real PDF's first page, as a scan does; (large, small)."""
    from audit.blob_store import BlobStore
    from audit.linked_files.thumbnail import first_page_jpegs

    pictures = first_page_jpegs((FIXTURE_PDFS / "clean.pdf").read_bytes())
    assert pictures is not None
    blobs = BlobStore(blob_dir)
    return blobs.store(pictures.large, "image/jpeg")[0], blobs.store(pictures.small, "image/jpeg")[
        0
    ]


def _seed_documents(db_path: Path, scan_id: int, blob_dir: Path | None = None) -> None:
    pictures = _first_page(blob_dir) if blob_dir else None
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
            # The one with a first-page picture, so every test of the
            # populated tab (axe, AAA, keyboard) covers a thumbnail too.
            store.CheckResult(
                "not_sure",
                http_status=200,
                thumbnail_hash=pictures[0] if pictures else None,
                thumbnail_small_hash=pictures[1] if pictures else None,
            ),
            [(home, "iframe", "Course map", None)],
        )
        # A Word file the check read (since 2026-11-17): one problem that
        # makes it Mostly sure, and three possible problems that do not
        # (a table without a header row is one since 2026-11-20).
        _file(
            conn,
            scan_id,
            "http://example.com/files/welcome-guide.docx",
            "docx",
            store.CheckResult(
                "mostly_sure",
                failed_checks=["no_alt_text", "table_no_header", "unclear_link_text", "no_title"],
                http_status=200,
                checked_as="docx",
            ),
            [(home, "link", "Welcome guide (Word)", None)],
        )
        # A Google Slides deck, checked as the PowerPoint file Google exports.
        _file(
            conn,
            scan_id,
            "https://docs.google.com/presentation/d/xyz/edit",
            "google_slides",
            store.CheckResult(
                "not_sure", failed_checks=["no_title"], http_status=200, checked_as="pptx"
            ),
            [(about, "link", "Orientation slides", None)],
            off_site=True,
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/report.xlsx",
            "xlsx",
            store.CheckResult("could_not_check", "type_not_checked_yet"),
            [(home, "link", "Committee report (Excel)", None)],
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
            "https://docs.google.com/spreadsheets/d/abc/edit",
            "google_sheet",
            store.CheckResult("could_not_check", "google_file"),
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
    db_path, blob_dir, scan_id = seeded_db
    _seed_documents(db_path, scan_id, blob_dir)
    return scan_id


def test_files_come_in_the_recommended_order(client: TestClient, documents: int) -> None:
    body = client.get(f"/api/scans/{documents}/documents").json()
    assert body["recorded"] is True
    assert body["total"] == 9
    assert body["counts"] == {"mostly_sure": 3, "not_sure": 2, "could_not_check": 4}
    assert [(f["name"], f["status"], f["reason"]) for f in body["files"]] == [
        # Mostly sure: the form on two pages before the one on one page.
        ("permit-form.pdf", "mostly_sure", None),
        ("no-title.pdf", "mostly_sure", None),
        ("welcome-guide.docx", "mostly_sure", None),
        ("map.pdf", "not_sure", None),
        # A Google address has no file name, so the link's text names it.
        ("Orientation slides", "not_sure", None),
        # Could not check: one page each, so by address.
        ("budget.xls", "could_not_check", "old_format"),
        ("missing.pdf", "could_not_check", "http_error"),
        ("report.xlsx", "could_not_check", "type_not_checked_yet"),
        ("Meeting notes", "could_not_check", "google_file"),
    ]
    form = body["files"][0]
    assert form["failed_checks"] == ["not_tagged", "no_language"]
    assert (form["is_form"], form["referring_page_count"]) == (True, 2)
    # The pages themselves are on the file's own page, not in the list.
    assert "refs" not in form
    # The server says which checks ran and splits what they found: the
    # problems (they make the file Mostly sure) and the possible problems.
    assert (form["checked_as"], form["possible_problems"]) == ("pdf", [])
    assert form["checks_run"] == [
        "not_tagged",
        "no_text",
        "blocks_assistive_tech",
        "no_title",
        "no_language",
    ]
    guide = next(f for f in body["files"] if f["name"] == "welcome-guide.docx")
    assert guide["checked_as"] == "docx"
    assert guide["failed_checks"] == ["no_alt_text"]
    assert guide["possible_problems"] == ["table_no_header", "unclear_link_text", "no_title"]
    # The checks that can make a file Mostly sure come first (2026-11-20).
    assert guide["checks_run"] == [
        "no_alt_text",
        "no_language",
        "table_no_header",
        "no_headings",
        "skipped_heading_level",
        "unclear_link_text",
        "no_title",
    ]
    deck = next(f for f in body["files"] if f["name"] == "Orientation slides")
    # A Google Slides deck: no title check, since Google's export never has
    # one and its author cannot set it (2026-11-18).
    assert (deck["checked_as"], deck["failed_checks"], deck["possible_problems"]) == (
        "pptx",
        [],
        [],
    )
    assert "slide_no_title" in deck["checks_run"]
    assert "no_title" not in deck["checks_run"]
    # A file no check read has none.
    sheet = next(f for f in body["files"] if f["name"] == "Meeting notes")
    assert (sheet["checked_as"], sheet["checks_run"]) == (None, [])


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
    assert (late["status"], late["reason"], late["referring_page_count"]) == (
        "could_not_check",
        "not_checked",
        0,
    )
    assert body["counts"]["could_not_check"] == 5


def test_files_are_paged(client: TestClient, documents: int) -> None:
    first = client.get(f"/api/scans/{documents}/documents?limit=3&offset=0").json()
    rest = client.get(f"/api/scans/{documents}/documents?limit=3&offset=3").json()
    names = [f["name"] for f in first["files"] + rest["files"]]
    assert len(names) == 6 and len(set(names)) == 6
    assert first["total"] == rest["total"] == 9


@pytest.mark.parametrize("query", ["limit=5001", "limit=0", "offset=-1"])
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
    assert theirs["files"][0]["referring_page_count"] == 1


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
    await expect(rows).to_have_count(9)

    # As on Issues: nothing under the heading, and the counts in the row of
    # summary numbers over the table, every value shown.
    await expect(
        page.locator("main header").get_by_text(re.compile(r"documents ·|expert to review"))
    ).to_have_count(0)
    numbers = page.locator("main dl").filter(
        has=page.get_by_role("term").filter(has_text=re.compile(r"^Documents$"))
    )
    # Each value says what Axcess is sure of, on a line under it.
    await expect(numbers.get_by_role("term")).to_have_text(
        [
            "Documents",
            "Mostly sure it has accessibility problems",
            "Not sure if it has accessibility problems",
            "Could not check for accessibility problems",
        ],
        use_inner_text=True,
    )
    await expect(numbers.get_by_role("definition")).to_have_text(["9", "3", "2", "4"])
    numbers_box = await numbers.bounding_box()
    table_box = await table.bounding_box()
    assert numbers_box and table_box
    assert numbers_box["y"] + numbers_box["height"] <= table_box["y"], (numbers_box, table_box)
    # Nothing to read between the numbers and the table: no caveat, key or
    # order line there, as on Issues. The order is in the caption.
    await expect(page.get_by_text(CAVEAT)).to_be_hidden()
    # Unsorted and unfiltered, no line over the table says the order, as on
    # Issues: only the caption and a status line for screen readers do.
    await expect(
        page.locator("p:not(.sr-only)", has_text=re.compile(r"recommended order", re.I))
    ).to_have_count(0)
    await expect(table).to_have_accessible_name(
        f"Documents linked from report #{scan_id}, "
        "Recommended order: Mostly sure first, then Not sure, then Could not check"
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
    await expect(page.get_by_text("3 types checked", exact=True)).to_be_visible()

    # Opened by keyboard, "What was checked" holds the caveat, what is
    # listed, the privacy fact and the limits, each said once.
    await checked.focus()
    await page.keyboard.press("Enter")
    panel = page.get_by_role("region", name=CHECKED)
    for text in (
        CAVEAT,
        "Axcess checks the PDF, Word (.docx) and PowerPoint (.pptx) files.",
        "three checks can make the file “Mostly sure”: alt text for images, slide titles and "
        "the language.",
        "Other checks list possible problems for a person to judge: table header rows, headings,",
        "To check a file, Axcess downloaded it to this computer once. It kept the results, "
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
        "welcome-guide.docx",
        "map.pdf",
        "Orientation slides",
        "budget.xls",
        "missing.pdf",
        "report.xlsx",
        "Meeting notes",
    ]
    await expect(table.get_by_role("rowheader")).to_have_text(
        [re.compile(rf"^{re.escape(name)}\b") for name in names], use_inner_text=True
    )
    form = rows.nth(0)
    await expect(form).to_contain_text("Mostly sure")
    await expect(form).to_contain_text("This site")
    # Each problem by its short name, one a line; why it matters is on the
    # document's page. The form is a fact under the type, not a problem.
    await expect(form.locator("td").nth(3).get_by_role("listitem")).to_have_text(
        ["Not tagged", "No language set"]
    )
    await expect(form.locator("td").nth(0)).to_contain_text("Has a form to fill in")
    await expect(form.locator("td").nth(3)).not_to_contain_text("form")
    # The pages are a count, as Issues' "Affected pages" is; the list is on
    # the document's own page. No page titles, addresses or link text here.
    await expect(form.locator("td").last).to_have_text("2")
    await expect(form).not_to_contain_text(HOME)
    await expect(form).not_to_contain_text("Apply for a permit")
    await expect(form).not_to_contain_text("Appears only after pressing")
    # A Word file: its problem, then its possible problems under their own
    # words, so one is never read as the other.
    guide = rows.nth(2).locator("td").nth(3)
    await expect(guide.get_by_role("list").first.get_by_role("listitem")).to_have_text(
        ["Images without alt text"]
    )
    await expect(guide.get_by_text("Possible problems:", exact=True)).to_be_visible()
    await expect(guide.get_by_role("list").nth(1).get_by_role("listitem")).to_have_text(
        ["Tables without a header row", "Links that do not say where they go", "No document title"]
    )
    # Not sure says what a person must still check: never read as a pass.
    await expect(rows.nth(3)).to_contain_text("Not sure")
    await expect(rows.nth(3)).to_contain_text(
        "the reading order, the image descriptions (alt text) and the table headers"
    )
    # A Google file says it was checked as the file Google exports.
    await expect(rows.nth(4)).to_contain_text(
        "Checked as the PowerPoint (.pptx) file that Google exports"
    )
    # "Does not check yet" and "cannot check" read differently.
    await expect(rows.nth(5)).to_contain_text("Axcess cannot check this file type.")
    await expect(rows.nth(6)).to_contain_text("(HTTP 404)")
    await expect(rows.nth(7)).to_contain_text("Axcess does not check this file type yet.")
    await expect(rows.nth(8)).to_contain_text("Axcess does not check Google Sheets.")
    await expect(rows.nth(8)).to_contain_text("docs.google.com")
    await expect(rows.nth(8)).to_contain_text("Another site")
    # The columns say what each value is; "How sure" alone did not.
    await expect(table.get_by_role("columnheader")).to_have_text(
        [
            re.compile(r"^Document"),
            re.compile(r"^Type"),
            re.compile(r"^Hosted on"),
            re.compile(r"^Accessibility problems\?"),
            re.compile(r"^What Axcess found"),
            re.compile(r"^Pages it appears on"),
        ]
    )
    # The row header is the file's name only: a screen reader reads it with
    # every cell, so no address, site or form line is in it.
    await expect(table.get_by_role("rowheader").nth(8)).to_have_text(
        re.compile(r"^Meeting notes\b"), use_inner_text=True
    )
    await expect(table.get_by_role("rowheader").get_by_text("docs.google.com")).to_have_count(0)
    await expect(table.get_by_role("rowheader").get_by_text("form to fill in")).to_have_count(0)
    await expect(table.get_by_role("rowheader").get_by_text("http://")).to_have_count(0)
    # The name opens the document's own page, as an issue type's title
    # opens its record: one link per row.
    link = table.get_by_role("link", name=re.compile(r"^permit-form\.pdf\s*, full details$"))
    await expect(link).to_have_attribute(
        "href", re.compile(rf"/app/scans/{scan_id}/documents/\d+\?origin=Documents&back=")
    )
    await expect(link).not_to_have_attribute("target", "_blank")
    await expect(form.get_by_role("link")).to_have_count(1)

    # Keyboard order follows the reading order: the tab, the Filter menu,
    # the column headers, then each file in turn, each with a visible focus.
    await tab.focus()
    stops = []
    for _ in range(12):
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
    assert texts[0] == "Filter documents", texts
    first_file = next(i for i, t in enumerate(texts) if t.startswith("permit-form.pdf"))
    # The six sort buttons, with the "?" right after its own header's
    # (Accessibility problems?), then the first file.
    assert texts[1].startswith("Document") and first_file == 8, texts
    assert texts[texts.index("Accessibility problems?") + 1] == (
        "What does \u201cAccessibility problems?\u201d mean?"
    ), texts
    assert texts[first_file + 1].startswith("no-title.pdf"), texts
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
        "them, reports from a sign-in scan made before 16 November 2026, and scans with the "
        "document check turned off."
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
    await expect(page.get_by_text("3 types checked", exact=True)).to_be_visible()
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


def test_one_document_lists_every_page_it_appears_on(client: TestClient, documents: int) -> None:
    form = _file_id(client, documents, "permit-form.pdf")
    body = client.get(f"/api/scans/{documents}/documents/{form}").json()
    assert body["file"]["name"] == "permit-form.pdf"
    assert body["file"]["referring_page_count"] == 2
    # One entry per page, in address order, each with every way it reaches
    # the file.
    assert [(p["page_url"], p["ways"]) for p in body["pages"]] == [
        (HOME, [{"how": "link", "link_text": "Apply for a permit (PDF)", "revealed_by": None}]),
        (
            ABOUT,
            [{"how": "revealed_link", "link_text": "Permit form", "revealed_by": "More forms"}],
        ),
    ]


def test_a_document_is_found_only_in_its_own_report(
    client: TestClient, seeded_db: tuple[Path, Path, int], documents: int
) -> None:
    with sqlite3.connect(seeded_db[0]) as conn:
        other = int(
            conn.execute(
                "INSERT INTO scans (seed_url, status, config_json) "
                "VALUES ('http://example.com/', 'completed', '{}')"
            ).lastrowid
            or 0
        )
    form = _file_id(client, documents, "permit-form.pdf")
    assert client.get(f"/api/scans/{other}/documents/{form}").status_code == 404
    assert client.get(f"/api/scans/{documents}/documents/999999").status_code == 404
    assert client.get(f"/api/scans/999999/documents/{form}").status_code == 404


@on_module_loop
@pytest.mark.parametrize("width", [1280, 320])
@pytest.mark.parametrize("theme", ["light", "dark"])
async def test_a_documents_page_passes_axe_and_the_aaa_checks(
    documents: int, live_server: tuple[str, int], new_page: Any, theme: str, width: int
) -> None:
    """The document's facts, its "Open the file" link and its table of pages."""
    from playwright.async_api import expect

    base, scan_id = live_server
    page = await new_page(viewport={"width": width, "height": 800})
    await page.add_init_script(
        f"localStorage.setItem('axcess.preferences', JSON.stringify({{theme: '{theme}'}}))"
    )
    response = await page.request.get(f"{base}/api/scans/{scan_id}/documents?limit=200")
    body = await response.json()
    form = next(f["file_id"] for f in body["files"] if f["name"] == "permit-form.pdf")
    await page.goto(f"{base}/app/scans/{scan_id}/documents/{form}", wait_until="networkidle")
    assert await page.title() == "Document · Axcess"
    # The file opens in a new tab, and its name and the new tab are said.
    opener = page.get_by_role("link", name=re.compile(r"^Open the file permit-form\.pdf \("))
    await expect(opener).to_have_attribute("href", "http://example.com/files/permit-form.pdf")
    await expect(opener).to_have_attribute("target", "_blank")
    facts = page.locator("main dl").first
    await expect(facts.get_by_role("term")).to_have_text(
        ["Accessibility problems?", "Type", "Hosted on", "Pages it appears on"]
    )
    await expect(page.get_by_text("it has accessibility problems", exact=True)).to_be_visible()
    await expect(page.get_by_role("heading", name="What Axcess found", level=2)).to_be_visible()
    # What Axcess found: every check, the ones with no problem too, by name,
    # result in words and why it matters; the form is a fact under Type.
    checks = page.get_by_role("table", name="Machine checks on permit-form.pdf")
    await expect(checks.get_by_role("rowheader")).to_have_text(
        [
            "Tags",
            "Text a screen reader can read",
            "Security settings",
            "Document title",
            "Language",
        ]
    )
    await expect(checks.locator("tbody tr td:nth-of-type(1)")).to_have_text(
        [
            "Problem found",
            "No problem found",
            "No problem found",
            "No problem found",
            "Problem found",
        ]
    )
    await expect(checks).not_to_contain_text("Passed")
    await expect(facts).to_contain_text("Has a form to fill in")
    table = page.get_by_role("table", name="Pages permit-form.pdf appears on")
    await expect(table.get_by_role("columnheader")).to_have_text(
        [
            re.compile(r"Row number"),
            re.compile(r"^Page title"),
            re.compile(r"^Page URL"),
            "How it appears",
        ]
    )
    rows = table.locator("tbody tr")
    await expect(rows).to_have_count(2)
    # How it appears: the link's own words, and the button that shows it.
    await expect(rows.nth(0)).to_contain_text("Link: “Apply for a permit (PDF)”")
    await expect(rows.nth(1)).to_contain_text("Appears only after pressing “More forms”")
    for tags in (_AXE_TAGS_AA, None):
        violations = await _run_axe(page, tags)
        assert not violations, f"{theme} {width}px:\n{_render_violations(violations)}"
    assert await page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    if width == 1280 and theme == "light":
        assert await page.evaluate(_SMALL_TARGETS) == []
        assert await page.evaluate(_SHARED_NAMES) == []
        controls = await page.evaluate(_COLLECT)
        assert not [c for c in controls if vague(c["text"], in_nav=c["inNav"])], controls


@on_module_loop
@pytest.mark.parametrize("width", [1280, 320])
async def test_a_word_and_a_powerpoint_page_list_their_own_checks(
    documents: int, live_server: tuple[str, int], new_page: Any, width: int
) -> None:
    """A Word file's table lists the Word checks and a deck's the PowerPoint
    ones (the row's ``checks_run``), each result in words: "Problem found"
    for a check that proves a barrier, "Possible problem" for one that does
    not, "No problem found" otherwise. A Google file says it was checked as
    the file Google exports."""
    from playwright.async_api import expect

    base, scan_id = live_server
    page = await new_page(viewport={"width": width, "height": 800})
    response = await page.request.get(f"{base}/api/scans/{scan_id}/documents?limit=200")
    body = await response.json()
    ids = {f["name"]: f["file_id"] for f in body["files"]}

    await page.goto(
        f"{base}/app/scans/{scan_id}/documents/{ids['welcome-guide.docx']}",
        wait_until="networkidle",
    )
    checks = page.get_by_role("table", name="Machine checks on welcome-guide.docx")
    await expect(checks.get_by_role("rowheader")).to_have_text(
        [
            "Alt text for images",
            "Language",
            "Table header rows",
            "Headings",
            "Heading levels",
            "Link text",
            "Document title",
        ]
    )
    # The checks that can make the file Mostly sure come first; a table
    # without a header row is a possible problem (2026-11-20).
    await expect(checks.locator("tbody tr td:nth-of-type(1)")).to_have_text(
        [
            "Problem found",
            "No problem found",
            "Possible problem",
            "No problem found",
            "No problem found",
            "Possible problem",
            "Possible problem",
        ]
    )
    await expect(checks).not_to_contain_text("Tags")
    await expect(checks).not_to_contain_text("Passed")
    for tags in (_AXE_TAGS_AA, None):
        violations = await _run_axe(page, tags)
        assert not violations, f"{width}px:\n{_render_violations(violations)}"
    assert await page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )

    await page.goto(
        f"{base}/app/scans/{scan_id}/documents/{ids['Orientation slides']}",
        wait_until="networkidle",
    )
    await expect(
        page.get_by_text("Checked as the PowerPoint (.pptx) file that Google exports.")
    ).to_be_visible()
    checks = page.get_by_role("table", name="Machine checks on Orientation slides")
    await expect(checks.get_by_role("rowheader")).to_have_text(
        [
            "Alt text for images",
            "Slide titles",
            "Language",
            "Table header rows",
            "Link text",
        ]
    )
    # A Google Slides deck has no "Document title" row (2026-11-18).
    await expect(checks.locator("tbody tr td:nth-of-type(1)")).to_have_text(
        ["No problem found"] * 5
    )
    for tags in (_AXE_TAGS_AA, None):
        violations = await _run_axe(page, tags)
        assert not violations, f"{width}px:\n{_render_violations(violations)}"


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
    """By keyboard from the Documents table to the document's page, then to
    one of its pages: the inspector outlines each link on that page to the
    file, and only those, and says what it marked in words."""
    from playwright.async_api import expect

    _save_copy(seeded_db[0], documents, HOME, _MARKED_COPY)
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
        name = page.get_by_role("table").get_by_role("link", name=re.compile(r"^permit-form\.pdf"))
        await name.focus()
        await page.keyboard.press("Enter")
        await page.wait_for_url(re.compile(r"/documents/\d+\?"))
        await expect(page.get_by_role("heading", level=1)).to_have_text("permit-form.pdf")
        # The trail leads back through Documents, as an issue type's record
        # leads back through Issues.
        trail = page.get_by_role("navigation", name="Breadcrumb")
        await expect(trail.get_by_role("link", name="Documents")).to_be_visible()
        await expect(trail).to_contain_text("permit-form.pdf")

        pages_table = page.get_by_role("table", name="Pages permit-form.pdf appears on")
        link = pages_table.get_by_role("link", name=re.compile(r"^Home\b"))
        await expect(link).to_have_accessible_name(
            re.compile(r"^Home\s*, opens the saved copy with the link to permit-form\.pdf marked$")
        )
        await link.focus()
        await page.keyboard.press("Enter")
        await page.wait_for_url(re.compile(r"/inspect\?.*file="))
        await expect(page.get_by_role("navigation", name="Breadcrumb")).to_contain_text(
            "permit-form.pdf"
        )

        group = page.get_by_role("group", name="Links to this document", exact=True)
        await expect(group.get_by_role("status")).to_have_text(
            re.compile(r"^Link to this document 1 of 2")
        )
        # The key to the marks is in the "?" beside Hide highlights.
        await page.get_by_role("button", name="What do the highlights mean?", exact=True).click()
        await expect(
            page.get_by_text(
                "Dashed red outlines mark the 2 links to “permit-form.pdf” on this page.",
                exact=False,
            )
        ).to_be_visible()
        await page.keyboard.press("Escape")
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


@on_module_loop
async def test_a_long_list_has_the_pager_under_the_table_too(
    documents: int,
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Past one page, the pager is over the table and again under its last
    row, as on every paged table; a page turn from the bottom moves focus
    to the top pager, where the new rows start."""
    from playwright.async_api import expect

    with sqlite3.connect(seeded_db[0]) as conn:
        home = _page_id(conn, documents, HOME)
        for n in range(8):
            _file(
                conn,
                documents,
                f"http://example.com/files/extra-{n:02d}.pdf",
                "pdf",
                store.CheckResult("not_sure", http_status=200),
                [(home, "link", f"Extra {n}", None)],
            )
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    top = page.get_by_role("navigation", name="Documents: page controls", exact=True)
    end = page.get_by_role(
        "navigation", name="Documents: page controls under the table", exact=True
    )
    await expect(top).to_be_visible()
    await expect(end).to_be_visible()
    table_box = await page.get_by_role("table").bounding_box()
    end_box = await end.bounding_box()
    assert table_box and end_box
    assert end_box["y"] >= table_box["y"] + table_box["height"], (table_box, end_box)
    await end.get_by_role("button", name="Next page of documents").click()
    await expect(top.get_by_role("status")).to_contain_text("Page 2 of 2")
    await expect(top).to_be_focused()


@on_module_loop
async def test_a_wide_pager_shares_the_row_with_filter_documents(
    documents: int,
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """With no search box in the bar, "Filter documents" takes only its own
    width, so a long list's pager sits beside it rather than on a line of
    its own (the developer's report, 2026-11-16: 909 documents, the pager
    under a lone button). 1400px: wide enough for the button and a 30-page
    pager side by side, too narrow for the 20rem a search box keeps, so
    the old layout fails here. At 320px it still wraps, and nothing scrolls
    sideways (SC 1.4.10 Reflow)."""
    from playwright.async_api import expect

    with sqlite3.connect(seeded_db[0]) as conn:
        home = _page_id(conn, documents, HOME)
        for n in range(300):
            _file(
                conn,
                documents,
                f"http://example.com/files/many-{n:03d}.pdf",
                "pdf",
                store.CheckResult("not_sure", http_status=200),
                [(home, "link", f"Many {n}", None)],
            )
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1400, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    filter_button = page.get_by_role("button", name="Filter documents")
    pager = page.get_by_role("navigation", name="Documents: page controls", exact=True)
    await expect(pager.get_by_role("button", name="Page 5 of documents")).to_be_visible()
    button_box = await filter_button.bounding_box()
    pager_box = await pager.bounding_box()
    assert button_box and pager_box
    assert pager_box["y"] < button_box["y"] + button_box["height"], (button_box, pager_box)
    assert pager_box["x"] > button_box["x"] + button_box["width"], (button_box, pager_box)

    await page.set_viewport_size({"width": 320, "height": 900})
    await expect(pager).to_be_visible()
    overflow = await page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, overflow


@on_module_loop
async def test_the_table_sorts_by_any_column_and_goes_back(
    documents: int, live_server: tuple[str, int], new_page: Any
) -> None:
    """As on Issues: a header sorts the whole list, the line over the table
    says the order, and "Back to recommended order" undoes it."""
    from playwright.async_api import expect

    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    table = page.get_by_role("table")
    names = table.get_by_role("rowheader")
    await table.get_by_role("button", name=re.compile(r"^Document")).click()
    await expect(page).to_have_url(re.compile(r"sort=name_asc"))
    await expect(names).to_have_text(
        [
            re.compile(rf"^{re.escape(n)}\b")
            for n in [
                "budget.xls",
                "map.pdf",
                "Meeting notes",
                "missing.pdf",
                "no-title.pdf",
                "Orientation slides",
                "permit-form.pdf",
                "report.xlsx",
                "welcome-guide.docx",
            ]
        ],
        use_inner_text=True,
    )
    await expect(
        page.locator("p:not(.sr-only)", has_text="Sorted by Document, A to Z.")
    ).to_be_visible()
    await expect(table.locator("th[aria-sort=ascending]")).to_have_count(1)
    # Pages it appears on opens with the most first: the form, on 2 pages.
    await table.get_by_role("button", name=re.compile(r"^Pages it appears on")).click()
    await expect(names.first).to_have_text(re.compile(r"^permit-form\.pdf"), use_inner_text=True)
    # Sorted by any column, the table still fits a 1280px screen: the sort
    # tag under a narrow header must not push it wider than its card.
    region = page.get_by_role("region", name="Documents table")
    for key in ("name", "type", "host", "status", "found", "pages"):
        for direction in ("asc", "desc"):
            await page.goto(
                f"{base}/app/scans/{scan_id}/documents?sort={key}_{direction}",
                wait_until="networkidle",
            )
            widths = await region.evaluate("el => [el.scrollWidth, el.clientWidth]")
            assert widths[0] <= widths[1], (key, direction, widths)
    back = page.get_by_role("button", name="Back to recommended order")
    await back.click()
    await expect(back).to_have_count(0)
    await expect(page).not_to_have_url(re.compile(r"sort="))
    await expect(names.first).to_have_text(re.compile(r"^permit-form\.pdf"), use_inner_text=True)
    await expect(names.nth(1)).to_have_text(re.compile(r"^no-title\.pdf"), use_inner_text=True)


@on_module_loop
async def test_filter_documents_narrows_the_list_and_says_how(
    documents: int, live_server: tuple[str, int], new_page: Any
) -> None:
    """Issues' Filter menu, with the columns' own names and a count per
    value; what is filtered is written out under the bar."""
    from playwright.async_api import expect

    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    toggle = page.get_by_role("button", name="Filter documents")
    await toggle.click()
    await expect(toggle).to_have_attribute("aria-expanded", "true")
    for group in ("Accessibility problems?", "Type", "Hosted on"):
        await expect(page.get_by_role("group", name=group)).to_be_visible()
    await (
        page.get_by_role("group", name="Accessibility problems?")
        .get_by_role("checkbox", name=re.compile(r"^Could not check"))
        .check()
    )
    await (
        page.get_by_role("group", name="Hosted on")
        .get_by_role("checkbox", name=re.compile(r"^This site"))
        .check()
    )
    await expect(page).to_have_url(re.compile(r"status=could_not_check"))
    await expect(page).to_have_url(re.compile(r"hosted=this"))
    table = page.get_by_role("table")
    await expect(table.get_by_role("rowheader")).to_have_count(3)
    await expect(page.get_by_text("3 of 9 shown", exact=True)).to_be_visible()
    await expect(
        page.get_by_text(re.compile(r"Filtered by.*Could not check.*This site"))
    ).to_be_visible()
    # The numbers over the table still count the whole report.
    numbers = page.locator("main dl").first
    await expect(numbers.get_by_role("definition").first).to_have_text("9")
    for tags in (_AXE_TAGS_AA, None):
        violations = await _run_axe(page, tags)
        assert not violations, _render_violations(violations)
    await page.keyboard.press("Escape")
    await page.get_by_role("button", name="Clear filters").click()
    await expect(table.get_by_role("rowheader")).to_have_count(9)
    # A filter that matches nothing says so, never an empty list.
    await page.goto(
        f"{base}/app/scans/{scan_id}/documents?status=not_sure&kind=excel",
        wait_until="networkidle",
    )
    await expect(
        page.get_by_text("No documents match these filters. Clear a filter to see more results.")
    ).to_be_visible()


@on_module_loop
async def test_a_copy_says_which_file_it_is_the_same_as(
    documents: int,
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Two addresses with the same bytes stay two rows; the later one says
    it is the same file as the first, in words in the table and with a link
    on its own page."""
    from playwright.async_api import expect

    with sqlite3.connect(seeded_db[0]) as conn:
        conn.execute(
            "UPDATE linked_files SET sha256 = 'abc' WHERE scan_id = ? AND url IN (?, ?)",
            (
                documents,
                "http://example.com/files/no-title.pdf",
                "http://example.com/files/permit-form.pdf",
            ),
        )
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    rows = page.get_by_role("table").locator("tbody tr")
    # no-title.pdf was recorded first, so permit-form.pdf is its copy.
    await expect(rows.nth(0)).to_contain_text("Same file as no-title.pdf")
    await expect(rows.nth(1)).not_to_contain_text("Same file as")
    await expect(rows.nth(0).get_by_role("link")).to_have_count(1)
    await rows.nth(0).get_by_role("link").click()
    await page.wait_for_url(re.compile(r"/documents/\d+"))
    first = page.get_by_role("link", name="no-title.pdf", exact=True)
    await expect(first).to_be_visible()
    await expect(
        page.get_by_text("The results below are that file\u2019s.", exact=False)
    ).to_be_visible()
    await first.click()
    await expect(page.get_by_role("heading", level=1)).to_have_text("no-title.pdf")
    await expect(page.get_by_text("Same file as")).to_have_count(0)


def test_a_first_page_is_served_only_through_its_own_report(
    client: TestClient, documents: int, seeded_db: tuple[Path, Path, int]
) -> None:
    """The picture is looked up by file and report, so another report's
    address, or a file with no picture, gets a 404, never the image."""
    listed = client.get(f"/api/scans/{documents}/documents").json()["files"]
    with_picture = [row for row in listed if row["has_thumbnail"]]
    assert [row["name"] for row in with_picture] == ["map.pdf"]
    file_id = with_picture[0]["file_id"]

    served = client.get(f"/api/scans/{documents}/documents/{file_id}/thumbnail")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    assert served.content[:3] == b"\xff\xd8\xff"
    small = client.get(f"/api/scans/{documents}/documents/{file_id}/thumbnail?size=small")
    assert small.status_code == 200
    assert small.content[:3] == b"\xff\xd8\xff"
    assert len(small.content) < len(served.content)
    assert (
        client.get(f"/api/scans/{documents}/documents/{file_id}/thumbnail?size=huge").status_code
        == 422
    )

    without = next(row for row in listed if not row["has_thumbnail"])
    assert (
        client.get(f"/api/scans/{documents}/documents/{without['file_id']}/thumbnail").status_code
        == 404
    )
    with sqlite3.connect(seeded_db[0]) as conn:
        other = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('http://example.com/', 'completed', '{}')"
        ).lastrowid
    assert client.get(f"/api/scans/{other}/documents/{file_id}/thumbnail").status_code == 404


@on_module_loop
async def test_the_first_page_shows_above_the_name_and_on_its_own_page(
    documents: int,
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """In the table the picture sits in the name's link and adds nothing to
    its name (alt=""); a file with no picture gets the same box with an
    icon. The document's own page shows it larger, captioned "First page"."""
    from playwright.async_api import expect

    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    link = page.get_by_role("link", name=re.compile(r"^map\.pdf\s*, full details$"))
    picture = link.locator("img")
    # Lazy-loaded: it loads only once its row is on screen.
    await link.scroll_into_view_if_needed()
    await expect(picture).to_have_attribute("alt", "")
    # The table loads the small picture, not the one for the document's page.
    await expect(picture).to_have_attribute("src", re.compile(r"/thumbnail\?size=small$"))
    await expect(picture).to_have_js_property("complete", True)
    assert await picture.evaluate("img => img.naturalWidth") > 0
    # A Word file has no picture: an icon in the same box, hidden from
    # screen readers, and still one link with the file's name.
    word = page.get_by_role("link", name=re.compile(r"^welcome-guide\.docx\s*, full details$"))
    await expect(word.locator("img")).to_have_count(0)
    await expect(word.locator("[aria-hidden=true] svg")).to_have_count(1)

    await link.click()
    figure = page.get_by_role("figure")
    await expect(figure).to_contain_text("First page")
    await expect(figure.locator("img")).to_have_attribute("alt", "")
    # Facts first, then the picture, on screen and in reading order.
    facts = await page.locator("dl").first.bounding_box()
    shown = await figure.bounding_box()
    assert facts and shown and shown["x"] >= facts["x"] + facts["width"] - 1


@on_module_loop
async def test_the_accessibility_problems_header_explains_its_values(
    documents: int,
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """A "?" on the "Accessibility problems?" header, as on Issues' How sure:
    by keyboard it opens what the column asks and what each value means,
    and Escape closes it with focus back on the "?"."""
    from playwright.async_api import expect

    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/documents", wait_until="networkidle")
    header = page.get_by_role("columnheader", name=re.compile(r"^Accessibility problems\?"))
    tip = header.get_by_role("button", name="What does “Accessibility problems?” mean?")
    await expect(tip).to_have_attribute("data-target-equivalent", "report-labels-button")
    # Wrapped onto two lines at this width, the label's words end right
    # before the "?": the sort button is shrunk to its longest line
    # (SortHeader, useFitToLines), not left as wide as its cell allows.
    sort_button = header.get_by_role("button", name=re.compile(r"^Accessibility problems\?"))
    words = await sort_button.evaluate(
        """button => {
            const rects = [];
            const walker = document.createTreeWalker(button, NodeFilter.SHOW_TEXT);
            const range = document.createRange();
            for (let node = walker.nextNode(); node; node = walker.nextNode()) {
                if (!node.textContent.trim()) continue;
                range.selectNodeContents(node);
                rects.push(...range.getClientRects());
            }
            const lines = new Set(rects.map(rect => Math.round(rect.top))).size;
            button.querySelectorAll('svg').forEach(svg => rects.push(svg.getBoundingClientRect()));
            return {end: Math.max(...rects.map(rect => rect.right)), lines};
        }"""
    )
    assert words["lines"] == 2, words  # wrapped, or this proves nothing
    tip_box = await tip.bounding_box()
    assert tip_box
    assert 0 <= tip_box["x"] - words["end"] <= 12, (words, tip_box)
    await tip.focus()
    await page.keyboard.press("Enter")
    panel = page.get_by_text("How sure Axcess is that the file has accessibility problems.")
    await expect(panel).to_be_visible()
    for meaning in (
        "A machine check found a problem",
        "The machine checks found no problem that makes the file hard to use",
        "Axcess could not check the file.",
    ):
        await expect(page.get_by_text(meaning).first).to_be_visible()
    await page.keyboard.press("Escape")
    await expect(panel).to_be_hidden()
    await expect(tip).to_be_focused()
    # Sorting by the column still works: the header's sort button is its own.
    await header.get_by_role("button", name=re.compile(r"^Accessibility problems\?")).click()
    sorted_by = page.get_by_text(re.compile(r"^Sorted by Accessibility problems\?"))
    await expect(sorted_by.first).to_be_attached()


@on_module_loop
async def test_a_google_doc_an_older_report_did_not_check_says_why(
    documents: int,
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Before 2026-11-18 every Google Doc got ``google_file``. Today only a
    copy published to the web does, so "published to the web" is said only
    of an address with no export (report #71 said it of 53 ordinary Docs)."""
    from playwright.async_api import expect

    base, scan_id = live_server
    with sqlite3.connect(seeded_db[0]) as conn:
        about = _page_id(conn, scan_id, ABOUT)
        older = _file(
            conn,
            scan_id,
            "https://docs.google.com/document/d/1ZgSJQ3EuyzIiNEN2C2xdgm_eAQ2sVBkGIBLPiWEBMkE/edit",
            "google_doc",
            store.CheckResult("could_not_check", "google_file"),
            [(about, "link", "Ordinary doc", None)],
            off_site=True,
        )
        published = _file(
            conn,
            scan_id,
            "https://docs.google.com/document/d/e/2PACX-1vQabcdefghij/pub",
            "google_doc",
            store.CheckResult("could_not_check", "google_file"),
            [(about, "link", "Published doc", None)],
            off_site=True,
        )
    page = await new_page(viewport={"width": 1280, "height": 800})
    await page.goto(f"{base}/app/scans/{scan_id}/documents/{older}", wait_until="networkidle")
    await expect(
        page.get_by_text(
            "Not checked: Axcess did not check Google Docs and Slides when this report "
            "was made. Scan again to check this file."
        )
    ).to_be_visible()
    await expect(page.get_by_text("published to the web")).to_have_count(0)
    await page.goto(f"{base}/app/scans/{scan_id}/documents/{published}", wait_until="networkidle")
    await expect(
        page.get_by_text(
            "Axcess cannot download this Google file. A copy published to the web has no file "
            "to download."
        )
    ).to_be_visible()
