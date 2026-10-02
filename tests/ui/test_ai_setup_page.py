"""Settings > AI features in the desktop app: axe and keyboard-only use.

No test here downloads anything: the download button is never pressed, the
check for an Ollama on port 11434 is stubbed, and removal works on a
temporary data folder.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from audit.ai.state import AIConfig, save_config
from audit.config import Settings

from .test_accessibility_axe import _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]


@pytest.fixture
def desktop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    data = tmp_path / "desktop-data"
    monkeypatch.setenv("AUDIT_DESKTOP", "1")
    monkeypatch.setenv("AUDIT_DATA_DIR", str(data))
    monkeypatch.setenv("AUDIT_ACCESS_TOKEN", "")
    monkeypatch.setattr("audit.ai.manager.system_ollama", lambda: None)
    yield data


@pytest.fixture
def set_up(desktop: Path) -> Path:
    save_config(
        Settings(data_dir=desktop, desktop=True),
        AIConfig(
            source="system",
            base_url="http://127.0.0.1:9",
            tier="small",
            text_model="qwen3:4b-instruct-2507-q4_K_M",
            vision_model="qwen3-vl:2b-instruct",
        ),
    )
    return desktop


@pytest.fixture
def server(desktop: Path, live_server: tuple[str, int]) -> str:
    return live_server[0]


@pytest.fixture
def server_set_up(set_up: Path, live_server: tuple[str, int]) -> str:
    return live_server[0]


@pytest.mark.parametrize("width", [1280, 320])
@pytest.mark.parametrize("scheme", ["light", "dark"])
async def test_ai_setup_page_has_no_axe_violations(
    new_page: Any, server: str, scheme: str, width: int
) -> None:
    page = await new_page(color_scheme=scheme, viewport={"width": width, "height": 900})
    try:
        await page.goto(f"{server}/app/settings/ai")
        await page.get_by_role("group", name="Choose the size of the AI models").wait_for()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        # Nothing sideways at 320 px (SC 1.4.10 Reflow).
        overflow = await page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0
    finally:
        await page.context.close()


async def test_set_up_page_and_reports_prompt_pass_axe(new_page: Any, server_set_up: str) -> None:
    page = await new_page()
    try:
        await page.goto(f"{server_set_up}/app/settings/ai")
        await page.get_by_role("heading", name="AI features are on").wait_for()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_reports_prompt_shows_until_dismissed(new_page: Any, server: str) -> None:
    page = await new_page()
    try:
        await page.goto(f"{server}/app/", wait_until="networkidle")
        heading = page.get_by_role("heading", name="Optional: set up AI features")
        await heading.wait_for()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        await page.get_by_role("button", name="Not now").click()
        await heading.wait_for(state="detached")
        await page.reload()
        await page.get_by_role("heading", name="Reports").first.wait_for()
        assert await heading.count() == 0
    finally:
        await page.context.close()


async def _tab_to(page: Any, name: str, limit: int = 60) -> None:
    for _ in range(limit):
        await page.keyboard.press("Tab")
        label = await page.evaluate(
            "(() => { const e = document.activeElement;"
            " return e ? (e.innerText || e.value || '') : '' })()"
        )
        if name in label:
            return
    raise AssertionError(f"Could not reach {name!r} with Tab")


async def test_choose_a_size_by_keyboard_without_downloading(new_page: Any, server: str) -> None:
    page = await new_page()
    try:
        await page.goto(f"{server}/app/settings/ai")
        group = page.get_by_role("group", name="Choose the size of the AI models")
        await group.wait_for()
        radios = group.get_by_role("radio")
        assert await radios.count() == 3
        await radios.first.focus()
        await page.keyboard.press("Home")
        await page.keyboard.press("ArrowDown")
        checked = await group.locator("input:checked").get_attribute("value")
        assert checked in {"standard", "small"}
        button = page.get_by_role("button", name="Download and set up")
        assert await button.count() == 1
        # The button says how big the download is before anything starts.
        assert "GB" in (await button.inner_text())
    finally:
        await page.context.close()


async def test_remove_by_keyboard_confirms_and_announces(new_page: Any, server_set_up: str) -> None:
    page = await new_page()
    try:
        await page.goto(f"{server_set_up}/app/settings/ai")
        await page.get_by_role("heading", name="AI features are on").wait_for()
        await _tab_to(page, "Remove AI features")
        await page.keyboard.press("Enter")
        confirm = page.get_by_role("button", name="Yes, remove AI features")
        await confirm.wait_for()
        assert await confirm.evaluate("e => e === document.activeElement")
        await page.keyboard.press("Enter")
        await page.get_by_role("status").filter(has_text="AI features removed.").wait_for()
        await page.get_by_role("heading", name="AI features are on").wait_for(state="detached")
        focused = await page.evaluate("document.activeElement?.getAttribute('type')")
        assert focused == "radio"
    finally:
        await page.context.close()
