"""Browser tests for the report Images tab: axe, and keyboard-only use.

The keyboard test runs the whole flow a person without a mouse would: move
to the group row, choose a group, reach a row's "Check alt text" button,
press it, hear the progress and the answer, and land on the answer. The
local model is a stub: these tests never contact Ollama.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest

from audit.analyzer.vlm import alt_check
from audit.analyzer.vlm.alt_check import AltCheckInput, AltCheckResult

from .test_accessibility_axe import _render_violations, _run_axe
from .test_report_images import _photo

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")


class _StubChecker:
    prompt_version = "v1-test"

    def __init__(self, client: Any, *, model: str, **_: Any) -> None:
        self.model = model

    async def check(self, image_bytes: bytes, given: AltCheckInput) -> AltCheckResult:
        return AltCheckResult(
            verdict="needs_better",
            reason="Says too little about the photo.",
            suggestion="Students talking outside Haven Hall",
            model=self.model,
            prompt_version=self.prompt_version,
        )


@pytest.fixture
def images_server(
    request: pytest.FixtureRequest,
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, int]:
    """A live server whose alt text check is a stub, with one photo to check."""
    db_path, blob_dir, scan_id = seeded_db
    _photo(db_path, blob_dir, scan_id, alt="Campus")
    monkeypatch.setenv("AUDIT_ALT_CHECK_MODEL", "stub:1")
    monkeypatch.setattr(alt_check, "OllamaAltChecker", _StubChecker)
    assert os.environ["AUDIT_ALT_CHECK_MODEL"] == "stub:1"
    return request.getfixturevalue("live_server")


@pytest.mark.parametrize("group", ["with_text", "missing_alt", "with_alt"])
async def test_images_tab_has_no_axe_violations(
    images_server: tuple[str, int], new_page: Any, group: str
) -> None:
    base, scan_id = images_server
    page = await new_page()
    try:
        await page.goto(
            f"{base}/app/scans/{scan_id}/images?group={group}", wait_until="networkidle"
        )
        await page.wait_for_selector("main#main table", timeout=5000)
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def _tab_to(page: Any, name: str, limit: int = 80) -> None:
    for _ in range(limit):
        await page.keyboard.press("Tab")
        text = await page.evaluate("() => (document.activeElement?.textContent || '').trim()")
        if text.startswith(name):
            return
    raise AssertionError(f"Tab never reached {name!r}")


async def test_images_tab_works_by_keyboard_alone(
    images_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = images_server
    page = await new_page()
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/images", wait_until="networkidle")
        tabs = page.get_by_role("navigation", name="Report views")
        await playwright_async.expect(tabs.get_by_role("link", name="Images")).to_have_attribute(
            "aria-current", "page"
        )

        await _tab_to(page, "Images with alt text")
        await page.keyboard.press("Enter")
        group = page.get_by_role("button", name="Images with alt text", exact=False)
        await playwright_async.expect(group).to_have_attribute("aria-pressed", "true")
        await page.wait_for_url("**group=with_alt**")

        await _tab_to(page, "Check alt text")
        await page.keyboard.press("Enter")

        status = page.locator("#report-images-announcer")
        await playwright_async.expect(status).to_contain_text("Done: students.png")
        focused = page.locator(":focus")
        await playwright_async.expect(focused).to_contain_text(
            "Students talking outside Haven Hall"
        )
        await playwright_async.expect(focused).to_contain_text("Check it before you use it")
        row = page.get_by_role("row", name="students.png", exact=False)
        await playwright_async.expect(row).to_contain_text("Needs better alt text")
        await playwright_async.expect(row).to_contain_text("Local AI model")
        # The suggestion, its copy button and the AI note pass axe (AAA).
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        await page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
        # The name changes from "Copy alt text" to "Copied", so match both.
        copy = row.get_by_role(
            "button", name=re.compile(r"^(Copy alt text|Copied) for students\.png")
        )
        await copy.focus()
        await page.keyboard.press("Enter")
        await playwright_async.expect(copy).to_contain_text("Copied")
        pasted = await page.evaluate("() => navigator.clipboard.readText()")
        assert pasted == "Students talking outside Haven Hall"

        # Plain http on a network address has no clipboard API: the older
        # copy method still copies the text, and focus stays on the button.
        await page.reload()
        await page.evaluate(
            """() => {
              Object.defineProperty(
                navigator, "clipboard", { configurable: true, value: undefined }
              );
              document.addEventListener("copy", () => {
                window.__copied = document.activeElement && document.activeElement.value;
              });
            }"""
        )
        copy = page.get_by_role(
            "button", name=re.compile(r"^(Copy alt text|Copied) for students\.png")
        )
        await copy.focus()
        await page.keyboard.press("Enter")
        await playwright_async.expect(copy).to_contain_text("Copied")
        assert await page.evaluate("window.__copied") == "Students talking outside Haven Hall"
        assert await copy.evaluate("el => el === document.activeElement")
    finally:
        await page.context.close()


async def _photo_page(page: Any, base: str, scan_id: int) -> None:
    """Open the photo's own page from its row in the Images table."""
    await page.goto(f"{base}/app/scans/{scan_id}/images?group=with_alt", wait_until="networkidle")
    row = page.get_by_role("row").filter(has_text="students.png")
    await row.get_by_role("link", name="students.png, full details").click()
    await page.wait_for_url(re.compile(r"/images/\d+\?"))
    await playwright_async.expect(
        page.get_by_role("heading", level=1, name="students.png")
    ).to_be_visible()


async def test_the_images_table_counts_pages_and_links_each_image(
    images_server: tuple[str, int], new_page: Any
) -> None:
    """Each image's thumbnail and name are one link to its page, and the
    table counts its pages; it no longer names one of them (2026-11-16)."""
    base, scan_id = images_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(
            f"{base}/app/scans/{scan_id}/images?group=with_alt", wait_until="networkidle"
        )
        table = page.get_by_role("table")
        await playwright_async.expect(
            table.get_by_role("columnheader", name="Pages it appears on")
        ).to_be_visible()
        await playwright_async.expect(
            table.get_by_role("columnheader", name="Where it appears")
        ).to_have_count(0)
        row = table.get_by_role("row").filter(has_text="students.png")
        # One link per image: the thumbnail and the name together.
        await playwright_async.expect(row.get_by_role("link")).to_have_count(1)
        await playwright_async.expect(row.get_by_role("cell").nth(3)).to_have_text("1")
        await _photo_page(page, base, scan_id)
        await playwright_async.expect(page.get_by_text("Text in the image")).to_be_visible()
        await playwright_async.expect(page.get_by_text("Current alt text")).to_be_visible()
        await playwright_async.expect(page.get_by_text("Alt text verdict")).to_be_visible()
        await playwright_async.expect(page.get_by_text("Suggested alt text")).to_be_visible()
        await playwright_async.expect(
            page.get_by_role("heading", level=2, name=re.compile(r"^Pages it appears on\s*1 page$"))
        ).to_be_visible()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_image_viewer_opens_and_closes(images_server: tuple[str, int], new_page: Any) -> None:
    """ "View larger image" on the image's page opens it large; Escape or the
    close button shuts it, and focus returns to the button."""
    base, scan_id = images_server
    page = await new_page()
    try:
        await _photo_page(page, base, scan_id)
        await page.get_by_role("button", name=re.compile(r"^View larger image")).focus()
        opener = await page.evaluate("() => document.activeElement.textContent.trim()")
        await page.keyboard.press("Enter")
        viewer = page.get_by_role("dialog")
        await playwright_async.expect(viewer).to_be_visible()
        await playwright_async.expect(viewer.get_by_role("heading", level=2)).to_be_visible()
        await playwright_async.expect(viewer).to_contain_text("Current alt text")
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)

        await page.keyboard.press("Escape")
        await playwright_async.expect(viewer).to_be_hidden()
        assert await page.evaluate("() => document.activeElement.textContent.trim()") == opener

        await page.keyboard.press("Enter")
        await playwright_async.expect(viewer).to_be_visible()
        await viewer.get_by_role("button", name="Close image viewer").click()
        await playwright_async.expect(viewer).to_be_hidden()
    finally:
        await page.context.close()


_IMAGES_HELP = "What does the Images tab show?"
# The numbers' labels for more than one image; one image takes the verdict's
# own label ("Needs alt text").
_VERDICT_NUMBER_LABELS = {
    "needs_alt": ("Needs alt text", "Need alt text"),
    "needs_better": ("Needs better alt text", "Need better alt text"),
    "not_checked": ("Needs a person to check", "Need a person to check"),
    "good": ("Good alt text", "Good alt text"),
}


async def test_images_tab_numbers_and_help(images_server: tuple[str, int], new_page: Any) -> None:
    """The Images tab's numbers in the Issues tab's style, and its explanation
    behind a "?" after the heading (2026-11-16)."""
    base, scan_id = images_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/images", wait_until="networkidle")
        body = await (
            await page.request.get(f"{base}/api/scans/{scan_id}/images?group=with_text")
        ).json()
        groups = (body["counts"]["missing_alt"], body["counts"]["with_alt"])
        total = sum(g["total"] for g in groups)
        assert total > 0, body["counts"]

        # One number per verdict that has any, after the images found, in the
        # verdict filter's order; every number is the whole report's.
        expected = [("Image found" if total == 1 else "Images found", total)]
        for key in ("needs_alt", "needs_better", "not_checked", "good"):
            n = sum(g[key] for g in groups)
            if n:
                expected.append((_VERDICT_NUMBER_LABELS[key][0 if n == 1 else 1], n))
        numbers = page.locator("main dl").first
        await playwright_async.expect(numbers.get_by_role("term")).to_have_text(
            [label for label, _ in expected]
        )
        await playwright_async.expect(numbers.get_by_role("definition")).to_have_text(
            [f"{n:,}" for _, n in expected]
        )
        # The explanation is no longer on screen until asked for.
        await playwright_async.expect(page.get_by_text("Each verdict is a lead")).to_be_hidden()

        tip = page.get_by_role("button", name=_IMAGES_HELP, exact=True)
        box = await tip.bounding_box()
        assert box and box["height"] >= 44 and box["width"] >= 44, box
        # After the heading, not inside it.
        await playwright_async.expect(
            page.get_by_role("heading", level=1, name="Images", exact=True)
        ).to_be_visible()
        await tip.focus()
        await page.keyboard.press("Enter")
        await playwright_async.expect(tip).to_have_attribute("aria-expanded", "true")
        panel = page.locator("[popover]:popover-open")
        await playwright_async.expect(panel).to_contain_text("One image can be in two groups")
        await playwright_async.expect(panel).to_contain_text(
            "No verdict proves that the site meets accessibility standards."
        )
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        await page.keyboard.press("Escape")
        await playwright_async.expect(panel).to_have_count(0)
        await playwright_async.expect(tip).to_be_focused()
    finally:
        await page.context.close()


async def test_an_image_opens_in_the_inspector_outlined(
    images_server: tuple[str, int],
    seeded_db: tuple[Path, Path, int],
    new_page: Any,
) -> None:
    """A page in the image's "Pages it appears on" opens the inspector with
    that image outlined (``?image=`` its content hash; 2026-11-16), and the
    Images tab's trail ends at the report, like Issues (ReportCrumb.tsx)."""
    import gzip
    import sqlite3

    base, scan_id = images_server
    db_path = seeded_db[0]
    conn = sqlite3.connect(db_path)
    try:
        page_id = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()[0]
        content_hash = conn.execute(
            "SELECT content_hash FROM images WHERE src_url_canonical LIKE '%students.png'"
        ).fetchone()[0]
        capture = (
            "<!doctype html><html><head><title>Campus</title></head><body>"
            "<p>Our students</p>"
            '<img src="http://example.com/students.png" alt="Campus" width="40" height="40">'
            "</body></html>"
        )
        conn.execute(
            "UPDATE pages SET rendered_html = ? WHERE id = ?",
            (gzip.compress(capture.encode()), page_id),
        )
        conn.commit()
    finally:
        conn.close()

    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(
            f"{base}/app/scans/{scan_id}/images?group=with_alt", wait_until="networkidle"
        )
        trail = page.get_by_role("navigation", name="Breadcrumb")
        await playwright_async.expect(trail.locator("[aria-current=page]")).not_to_have_text(
            "Images"
        )
        await _photo_page(page, base, scan_id)
        # The image's page sits under Images in the trail.
        await playwright_async.expect(trail.get_by_role("link", name="Images")).to_be_visible()
        link = page.get_by_role(
            "link", name=re.compile("opens the saved copy with students.png marked")
        )
        href = await link.get_attribute("href")
        assert href and f"image={content_hash}" in href, href
        await link.click()
        await page.wait_for_url(f"**/pages/{page_id}/inspect?**")
        frame = page.frame_locator("iframe[title^='Saved copy']")
        await playwright_async.expect(frame.locator(".axcess-inspect-highlight")).to_have_count(1)
        # From the inspector, the trail leads back to the Images tab.
        await playwright_async.expect(trail.get_by_role("link", name="Images")).to_be_visible()
    finally:
        await page.context.close()
