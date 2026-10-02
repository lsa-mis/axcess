"""AI fix suggestion panel in the browser: keyboard only, and axe-clean.

Drives the real SPA against a live server whose model is a fake, so it runs
without Ollama. Pins what the panel promises: the button works from the
keyboard, focus lands on the new content, the status is announced, the
views switch by keyboard, and the panel has no axe violations.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from audit.db.schema import connect
from audit.web import server as web_server
from audit.web.server import create_app

from .test_accessibility_axe import _render_violations, _run_axe
from .test_fix_suggestions import FakeProvider, FakeVerifier, _add_finding

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

pytest.importorskip("playwright.async_api")


@pytest.fixture
def suggest_server(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[str, int, int, int]]:
    """Live server with suggestions on: ``(base, scan_id, page_id, finding_id)``."""
    if not (web_server._FRONTEND_DIST / "index.html").exists():
        pytest.skip("SPA bundle not built (run `npm run build`)")
    monkeypatch.setenv("AUDIT_SUGGESTIONS_ENABLED", "true")
    db_path, blob_dir, scan_id = seeded_db
    finding_id = _add_finding(db_path, scan_id)
    conn = connect(db_path)
    try:
        page_id = conn.execute(
            "SELECT page_id FROM page_a11y_findings WHERE id = ?", (finding_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    app = create_app(
        db_path=db_path,
        blob_dir=blob_dir,
        suggestion_provider=FakeProvider(),
        suggestion_verifier=FakeVerifier("passed"),
    )
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started and server.servers:
            break
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield (f"http://127.0.0.1:{port}", scan_id, page_id, finding_id)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


async def test_suggestion_works_by_keyboard_and_passes_axe(
    suggest_server: tuple[str, int, int, int], new_page: Any
) -> None:
    base, scan_id, page_id, finding_id = suggest_server
    page = await new_page()
    await page.goto(f"{base}/app/scans/{scan_id}/pages/{page_id}", wait_until="networkidle")
    card = page.locator(f"#finding-{finding_id}")
    button = card.get_by_role("button", name="Suggest a fix (AI)")
    await button.focus()
    await page.keyboard.press("Enter")

    heading = card.get_by_role("heading", name="AI suggestion")
    await heading.wait_for()
    assert await heading.evaluate("el => el === document.activeElement")
    await card.get_by_text("It can be wrong. Check it before you use it.").wait_for()

    status = card.get_by_role("status").first
    await page.wait_for_function(
        "(el) => el.textContent.startsWith('Ready')",
        arg=await status.element_handle(),
        timeout=15000,
    )
    await card.get_by_text("Add a label so screen readers announce the field.").wait_for()
    await card.get_by_text("The rule check passed on the suggested code").wait_for()
    await card.get_by_text("It does not show that the page meets WCAG").wait_for()

    editor = card.get_by_role("button", name="For content editors")
    developer = card.get_by_role("button", name="For developers")
    assert await developer.get_attribute("aria-pressed") == "true"
    await editor.focus()
    await page.keyboard.press("Enter")
    assert await editor.get_attribute("aria-pressed") == "true"
    await card.get_by_text("Ask a developer to add a label to the search box.").wait_for()
    await card.get_by_role("button", name="Copy Label text").wait_for()

    helpful = card.get_by_role("button", name="Helpful", exact=True)
    await helpful.focus()
    await page.keyboard.press("Space")
    await page.wait_for_function(
        "(el) => el.getAttribute('aria-pressed') === 'true'",
        arg=await helpful.element_handle(),
    )

    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # Reflow: nothing in the panel scrolls sideways at 320 px (SC 1.4.10).
    await page.set_viewport_size({"width": 320, "height": 800})
    overflow = await card.evaluate("el => el.scrollWidth - el.clientWidth")
    assert overflow <= 1


async def test_no_button_when_suggestions_are_off(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int]
) -> None:
    base, scan_id = live_server
    db_path, _, _ = seeded_db
    finding_id = _add_finding(db_path, scan_id)
    conn = connect(db_path)
    try:
        page_id = conn.execute(
            "SELECT page_id FROM page_a11y_findings WHERE id = ?", (finding_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    page = await new_page()
    await page.goto(f"{base}/app/scans/{scan_id}/pages/{page_id}", wait_until="networkidle")
    await page.locator(f"#finding-{finding_id}").wait_for()
    assert await page.get_by_role("button", name="Suggest a fix (AI)").count() == 0
