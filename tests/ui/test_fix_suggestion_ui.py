"""AI fix suggestion panel in the browser: keyboard only, and axe-clean.

Drives the real SPA against a live server whose model is a fake, so it runs
without Ollama. Pins what the panel promises: the button works from the
keyboard, focus lands on the new content, the status is announced, the
views switch by keyboard, and the panel has no axe violations.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from audit.ai.state import AIPreferences, save_preferences
from audit.config import Settings
from audit.db.schema import connect
from audit.suggest.provider import SuggestionError
from audit.web import server as web_server
from audit.web.server import create_app

from .test_accessibility_axe import _render_violations, _run_axe
from .test_fix_suggestions import GOOD_ANSWER, FakeProvider, FakeVerifier, _add_finding

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

pytest.importorskip("playwright.async_api")


@pytest.fixture
def suggest_server(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Iterator[tuple[str, int, int, int]]:
    """Live server with suggestions on: ``(base, scan_id, page_id, finding_id)``."""
    if not (web_server._FRONTEND_DIST / "index.html").exists():
        pytest.skip("SPA bundle not built (run `npm run build`)")
    monkeypatch.setenv("AUDIT_SUGGESTIONS_ENABLED", "true")
    db_path, blob_dir, scan_id = seeded_db
    if getattr(request, "param", False) in (True, "offline"):
        monkeypatch.setenv("AUDIT_DESKTOP", "1")
        monkeypatch.setenv("AUDIT_DATA_DIR", str(db_path.parent))
        monkeypatch.setattr("audit.ai.manager.system_ollama", lambda: None)
        save_preferences(
            Settings(data_dir=db_path.parent, desktop=True),
            AIPreferences(enabled=True, choice_recorded=True),
        )
    finding_id = _add_finding(db_path, scan_id)
    conn = connect(db_path)
    try:
        page_id = conn.execute(
            "SELECT page_id FROM page_a11y_findings WHERE id = ?", (finding_id,)
        ).fetchone()[0]
        if getattr(request, "param", None) == "v1":
            result = {
                **GOOD_ANSWER,
                "before_html": '<input id="q" value="">',
                "confidence": "likely",
                "check_rule_id": "aria-input-field-name",
            }
            conn.execute(
                "INSERT INTO fix_suggestions (scan_id, page_id, occurrence_kind, occurrence_id, "
                "status, audience_default, text_model, prompt_version, result_json, check_outcome) "
                "VALUES (?, ?, 'a11y', ?, 'ready', 'developer', 'old-model', 'v1', ?, 'passed')",
                (scan_id, page_id, finding_id, json.dumps(result)),
            )
        if getattr(request, "param", None) == "guidance":
            conn.execute(
                "UPDATE page_a11y_findings SET help_url = ? WHERE id = ?",
                ("https://example.com/rules/search-label", finding_id),
            )
    finally:
        conn.close()

    class MixedVerifier(FakeVerifier):
        async def check(self, rule_id: str | None, html: str | None, css: str | None) -> Any:
            self.calls.append((rule_id, html))
            outcomes = (
                ("not_checked", "passed")
                if request.param == "unchecked"
                else ("passed", "still_fails")
            )
            return outcomes[len(self.calls) - 1]

    class SlowProvider(FakeProvider):
        async def generate(self, prompt: str, *, model: str, image: bytes | None) -> str:
            await asyncio.sleep(5)
            return await super().generate(prompt, model=model, image=image)

    class OfflineOnceProvider(FakeProvider):
        """Fails like a stopped Ollama the first time, then answers."""

        failed = False

        async def generate(self, prompt: str, *, model: str, image: bytes | None) -> str:
            if not self.failed:
                self.failed = True
                raise SuggestionError("model_unavailable", "connection refused")
            return await super().generate(prompt, model=model, image=image)

    param = getattr(request, "param", None)
    provider = (
        SlowProvider()
        if param == "slow"
        else OfflineOnceProvider()
        if param == "offline"
        else FakeProvider()
    )
    verifier = (
        MixedVerifier()
        if getattr(request, "param", None) in {"mixed", "unchecked"}
        else FakeVerifier("passed")
    )
    app = create_app(
        db_path=db_path,
        blob_dir=blob_dir,
        suggestion_provider=provider,
        suggestion_verifier=verifier,
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


@pytest.mark.parametrize("suggest_server", [True], indirect=True)
async def test_saved_suggestion_stays_readable_with_ai_off(
    suggest_server: tuple[str, int, int, int], new_page: Any
) -> None:
    base, scan_id, page_id, finding_id = suggest_server
    page = await new_page()
    try:
        response = await page.request.post(
            f"{base}/api/scans/{scan_id}/suggestions",
            data={"occurrence_kind": "a11y", "occurrence_id": finding_id},
        )
        assert response.status == 202
        sid = (await response.json())["id"]
        for _ in range(100):
            answer = await (
                await page.request.get(f"{base}/api/scans/{scan_id}/suggestions/{sid}")
            ).json()
            if answer["status"] == "ready":
                break
            await asyncio.sleep(0.02)
        assert answer["status"] == "ready"
        for _ in range(100):
            off = await page.request.put(f"{base}/api/ai/preferences", data={"enabled": False})
            if off.status == 200:
                break
            await asyncio.sleep(0.02)
        assert off.status == 200
        await page.goto(f"{base}/app/scans/{scan_id}/pages/{page_id}", wait_until="networkidle")
        card = page.locator(f"#finding-{finding_id}")
        await card.get_by_text('<input id="q" aria-label="Search">').wait_for()
        assert await card.get_by_role("button", name="Suggest again").count() == 0
        await page.get_by_text("AI features are off.", exact=False).first.wait_for()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


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
    # One precise sentence and two options; old summary stays hidden.
    await card.get_by_text('<input id="q" aria-label="Search">').wait_for()
    assert await card.get_by_text("Add a label so screen readers announce the field.").count() == 0
    assert await card.get_by_text("Give the search box a name.").count() == 0
    assert await card.get_by_text("After", exact=True).count() == 2
    await card.get_by_text("Before", exact=True).wait_for()
    await card.get_by_text("Add a label linked to the search field by its existing id.").wait_for()
    await card.get_by_text("Option 1: Smallest change", exact=True).wait_for()
    await card.get_by_text("Option 2: Matches nearby code", exact=True).wait_for()
    assert (
        await card.get_by_text("The rule check passed on the suggested code", exact=False).count()
        == 2
    )
    assert (
        await card.get_by_role("link", name="Read guidance for this rule", exact=False).count() == 0
    )
    # "Ready" is announced, not shown.
    assert (await status.bounding_box() or {"width": 0})["width"] <= 1
    await card.get_by_text(
        "The rule check passed on the suggested code", exact=False
    ).first.wait_for()
    # Model, time and the export note are kept, one press away.
    about = card.locator("details", has_text="About this suggestion")
    assert await about.get_attribute("open") is None
    await about.locator("summary").focus()
    await page.keyboard.press("Enter")
    await card.get_by_text("Not included in exports.").wait_for()
    await card.get_by_text(
        "It does not show that the page meets WCAG", exact=False
    ).first.wait_for()

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

    # Check the developer code, not just the editor steps, at both widths.
    await developer.focus()
    await page.keyboard.press("Enter")
    for width in (320, 1280):
        await page.set_viewport_size({"width": width, "height": 800})
        overflow = await card.evaluate("el => el.scrollWidth - el.clientWidth")
        assert overflow <= 1
    await page.context.close()


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


async def test_page_inspector_suggests_a_fix_for_the_element_you_are_on(
    suggest_server: tuple[str, int, int, int], new_page: Any
) -> None:
    base, scan_id, page_id, _ = suggest_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?issue=axe:aria-input-field-name",
        wait_until="networkidle",
    )
    # Not inside the facts box: that waits for the saved copy to load, and
    # the suggestion must not wait for, or vanish with, the frame.
    box = page.locator("#inspect-panel-page")
    button = box.get_by_role("button", name="Suggest a fix (AI)")
    await button.wait_for()
    await button.focus()
    await page.keyboard.press("Enter")

    heading = box.get_by_role("heading", name="AI suggestion", level=2)
    await heading.wait_for()
    assert await heading.evaluate("el => el === document.activeElement")
    await box.get_by_text('<input id="q" aria-label="Search">').wait_for(timeout=15000)

    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


@pytest.mark.parametrize("suggest_server", ["guidance"], indirect=True)
async def test_guidance_is_the_saved_rule_link(
    suggest_server: tuple[str, int, int, int], new_page: Any
) -> None:
    base, scan_id, page_id, finding_id = suggest_server
    page = await new_page()
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/pages/{page_id}", wait_until="networkidle")
        card = page.locator(f"#finding-{finding_id}")
        await card.get_by_role("button", name="Suggest a fix (AI)").click()
        link = card.get_by_role("link", name="Read guidance for this rule (opens in a new tab)")
        await link.wait_for(timeout=15000)
        assert await link.get_attribute("href") == "https://example.com/rules/search-label"
        assert await link.get_attribute("rel") == "noopener noreferrer"
        await link.focus()
        assert await link.evaluate("el => el === document.activeElement")
        for width in (320, 1280):
            await page.set_viewport_size({"width": width, "height": 800})
            assert await card.evaluate("el => el.scrollWidth - el.clientWidth") <= 1
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


@pytest.mark.parametrize("suggest_server", ["slow"], indirect=True)
async def test_writing_status_is_short_polite_and_keeps_focus(
    suggest_server: tuple[str, int, int, int], new_page: Any
) -> None:
    base, scan_id, page_id, finding_id = suggest_server
    page = await new_page()
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/pages/{page_id}", wait_until="networkidle")
        card = page.locator(f"#finding-{finding_id}")
        await card.get_by_role("button", name="Suggest a fix (AI)").focus()
        await page.keyboard.press("Enter")
        status = card.get_by_role("status").first
        await page.wait_for_function(
            "el => el.textContent.includes('Writing the fix. You can keep browsing other issues.')",
            arg=await status.element_handle(),
            timeout=10000,
        )
        assert await status.get_attribute("aria-live") == "polite"
        assert await card.get_by_role("heading", name="AI suggestion").evaluate(
            "el => el === document.activeElement"
        )
        await card.get_by_role("button", name="Stop", exact=True).focus()
        await page.keyboard.press("Enter")
        await card.get_by_role("button", name="Suggest a fix (AI)").wait_for()
    finally:
        await page.context.close()


@pytest.mark.parametrize("suggest_server", ["v1"], indirect=True)
async def test_v1_single_code_suggestion_still_renders(
    suggest_server: tuple[str, int, int, int], new_page: Any
) -> None:
    base, scan_id, page_id, finding_id = suggest_server
    page = await new_page()
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/pages/{page_id}", wait_until="networkidle")
        card = page.locator(f"#finding-{finding_id}")
        await card.get_by_text('<input id="q" aria-label="Search">').wait_for(timeout=15000)
        assert await card.get_by_text("Before", exact=True).count() == 1
        assert await card.get_by_text("After", exact=True).count() == 1
        assert await card.get_by_text("Option 1: Smallest change", exact=True).count() == 0
        assert (
            await card.get_by_text("Add a label so screen readers announce the field.").count() == 0
        )
        await card.get_by_role("button", name="For content editors").focus()
        await page.keyboard.press("Enter")
        await card.get_by_text("Ask a developer to add a label to the search box.").wait_for()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


@pytest.mark.parametrize("suggest_server", ["mixed", "unchecked"], indirect=True)
async def test_each_option_shows_only_its_own_rule_result(
    suggest_server: tuple[str, int, int, int], new_page: Any, request: pytest.FixtureRequest
) -> None:
    base, scan_id, page_id, finding_id = suggest_server
    page = await new_page()
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/pages/{page_id}", wait_until="networkidle")
        card = page.locator(f"#finding-{finding_id}")
        await card.get_by_role("button", name="Suggest a fix (AI)").click()
        await card.get_by_text("Option 1: Smallest change", exact=True).wait_for(timeout=15000)
        options = card.locator("ol > li")
        first = await options.nth(0).inner_text()
        second = await options.nth(1).inner_text()
        if request.node.callspec.params["suggest_server"] == "mixed":
            assert "The rule check passed" in first and "The rule check still fails" not in first
            assert "The rule check still fails" in second and "The rule check passed" not in second
        else:
            assert "Axcess could not check this suggestion" in first
            assert "Check this option on the real page." in first
            assert "The rule check passed" in second
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


@pytest.mark.parametrize("suggest_server", ["offline"], indirect=True)
async def test_start_ai_service_then_writes_the_suggestion(
    suggest_server: tuple[str, int, int, int], new_page: Any
) -> None:
    base, scan_id, page_id, finding_id = suggest_server
    page = await new_page()
    started: list[Any] = []

    async def fake_start(route: Any) -> None:
        started.append(route.request.post_data_json)
        await route.fulfill(
            json={
                "state": "started",
                "isolated": True,
                "reason": None,
                "download_bytes": None,
                "tier": "small",
            }
        )

    await page.route("**/api/ai/runtime/start", fake_start)
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/pages/{page_id}", wait_until="networkidle")
        card = page.locator(f"#finding-{finding_id}")
        await card.get_by_role("button", name="Suggest a fix (AI)").click()
        start = card.get_by_role("button", name="Start AI service")
        await start.wait_for(timeout=10000)
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        await start.focus()
        await page.keyboard.press("Enter")
        await card.get_by_text("Option 1").first.wait_for(timeout=10000)
        assert started == [{"confirm": True}]
    finally:
        await page.context.close()


@pytest.mark.parametrize("suggest_server", ["slow"], indirect=True)
@pytest.mark.parametrize("stay", [True, False], ids=["stays", "browses_on"])
async def test_ready_answer_takes_focus_only_if_person_waited(
    suggest_server: tuple[str, int, int, int], new_page: Any, stay: bool
) -> None:
    base, scan_id, page_id, finding_id = suggest_server
    page = await new_page()
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/pages/{page_id}", wait_until="networkidle")
        card = page.locator(f"#finding-{finding_id}")
        await card.get_by_role("button", name="Suggest a fix (AI)").focus()
        await page.keyboard.press("Enter")
        heading = card.get_by_role("heading", name="AI suggestion")
        await heading.wait_for()
        elsewhere = page.get_by_role("link").first
        if not stay:
            await elsewhere.focus()
        lead = card.get_by_text("Add a label linked to the search field by its existing id.")
        await lead.wait_for(timeout=15000)
        # The fix sentence leads in larger, bold text than the code labels.
        size = await lead.evaluate("el => parseFloat(getComputedStyle(el).fontSize)")
        label = await card.get_by_text("Before", exact=True).evaluate(
            "el => parseFloat(getComputedStyle(el).fontSize)"
        )
        assert size > label
        assert int(await lead.evaluate("el => getComputedStyle(el).fontWeight")) >= 600
        await page.wait_for_timeout(300)
        target = lead if stay else elsewhere
        assert await target.evaluate("el => el === document.activeElement")
    finally:
        await page.context.close()
