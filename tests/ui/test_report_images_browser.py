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
              Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
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


async def test_image_viewer_opens_and_closes(images_server: tuple[str, int], new_page: Any) -> None:
    """The thumbnail opens the image large; Escape or the close button shuts
    it, and focus returns to the thumbnail."""
    base, scan_id = images_server
    page = await new_page()
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/images", wait_until="networkidle")
        await _tab_to(page, "View larger image")
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
