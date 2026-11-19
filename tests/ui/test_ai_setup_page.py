"""Settings > AI features in the desktop app: axe and keyboard-only use.

No test here downloads anything: the download button is never pressed, the
setup never looks for an Ollama on port 11434, and removal works on a
temporary data folder.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import expect

from audit.ai.catalog import load_catalog
from audit.ai.state import AIConfig, AIPreferences, save_config, save_preferences
from audit.config import Settings

from .test_accessibility_axe import _render_violations, _run_axe

# The AI state the page shows (lib/terms.ts AI_STATE_LABEL): one heading for
# the on/off choice, the models and the service together (2026-11-18).
ON = "AI is on"
OFF = "AI is off"

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]


@pytest.fixture
def desktop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    data = tmp_path / "desktop-data"
    monkeypatch.setenv("AUDIT_DESKTOP", "1")
    monkeypatch.setenv("AUDIT_DATA_DIR", str(data))
    monkeypatch.setenv("AUDIT_ACCESS_TOKEN", "")
    # A 16 GB computer, like the developer's: Small and Standard can run,
    # Large (for 32 GB or more) cannot. The test server runs in this process.
    monkeypatch.setattr("audit.ai.hardware._memory_bytes", lambda: 16 * 1024**3)
    save_preferences(Settings(data_dir=data, desktop=True), AIPreferences())
    yield data


@pytest.fixture
def set_up(desktop: Path) -> Path:
    save_preferences(
        Settings(data_dir=desktop, desktop=True),
        AIPreferences(enabled=True, choice_recorded=True),
    )
    save_config(
        Settings(data_dir=desktop, desktop=True),
        AIConfig(
            source="system",
            base_url="http://127.0.0.1:9",
            tier="standard",
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
        await page.get_by_role("group", name="Choose the AI models").wait_for()
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
        await page.get_by_role("heading", name=ON).wait_for()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


@pytest.mark.parametrize("width", [320, 1280])
async def test_first_launch_skip_choice_by_keyboard(new_page: Any, server: str, width: int) -> None:
    page = await new_page(viewport={"width": width, "height": 900})
    try:
        await page.goto(f"{server}/app/", wait_until="networkidle")
        heading = page.get_by_role("heading", name="Choose whether to use AI features")
        await heading.wait_for()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        overflow = await page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0
        await _tab_to(page, "Continue without AI")
        await page.keyboard.press("Enter")
        await heading.wait_for(state="detached")
        await page.reload()
        await page.get_by_role("heading", name="Reports").first.wait_for()
        assert await heading.count() == 0
        preferences = await page.request.get(f"{server}/api/ai/preferences")
        assert await preferences.json() == {
            "enabled": False,
            "choice_recorded": True,
            "gpu_only": False,
        }
    finally:
        await page.context.close()


async def test_first_launch_setup_never_downloads_without_confirmation(
    new_page: Any, server: str
) -> None:
    page = await new_page()
    try:
        await page.goto(f"{server}/app/", wait_until="networkidle")
        await page.get_by_role("heading", name="Choose whether to use AI features").wait_for()
        # Says where the large download comes from before anything starts.
        await page.get_by_text("AI models from Hugging Face").first.wait_for()
        await _tab_to(page, "Set up AI features")
        await page.keyboard.press("Enter")
        await page.get_by_role("group", name="Choose the AI models").wait_for()
        assert (await (await page.request.get(f"{server}/api/ai/install")).json())[
            "state"
        ] == "idle"
        assert (await (await page.request.get(f"{server}/api/ai/preferences")).json())[
            "enabled"
        ] is False
        # Skipping AI is asked on the first-launch page only; the setup page
        # leaves by Back to Settings (2026-11-18, one control, one job).
        assert await page.get_by_role("button", name="Continue without AI").count() == 0
        await page.get_by_role("link", name="Back to Settings").click()
        await page.get_by_role("heading", name="Settings").first.wait_for()
    finally:
        await page.context.close()


async def test_settings_toggle_keeps_models_and_keyboard_focus(
    new_page: Any, server_set_up: str
) -> None:
    page = await new_page()
    try:
        await page.goto(f"{server_set_up}/app/settings/ai", wait_until="networkidle")
        await page.get_by_role("heading", name=ON).wait_for()
        await _tab_to(page, "Turn AI off")
        await page.keyboard.press("Enter")
        await page.get_by_role("heading", name=OFF).wait_for()
        turn_on = page.get_by_role("button", name="Turn AI on")
        assert await turn_on.evaluate("e => e === document.activeElement")
        plan = await (await page.request.get(f"{server_set_up}/api/ai/plan")).json()
        assert plan["current"]["tier"] == "standard"
        assert plan["preferences"]["enabled"] is False
        await page.reload(wait_until="networkidle")
        await page.get_by_role("heading", name=OFF).wait_for()
        await _tab_to(page, "Turn AI on")
        await page.keyboard.press("Enter")
        await page.get_by_role("heading", name=ON).wait_for()
        assert await page.get_by_role("button", name="Turn AI off").evaluate(
            "e => e === document.activeElement"
        )
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        assert (await (await page.request.get(f"{server_set_up}/api/ai/install")).json())[
            "state"
        ] == "idle"
    finally:
        await page.context.close()


async def test_busy_error_keeps_ai_on_and_preserves_focus(
    new_page: Any, server_set_up: str
) -> None:
    page = await new_page()
    try:
        await page.goto(f"{server_set_up}/app/settings/ai", wait_until="networkidle")
        await page.get_by_role("heading", name=ON).wait_for()

        async def refuse_change(route):
            message = "Finish or stop the current scan before changing AI settings."
            if route.request.method == "PUT":
                await route.fulfill(
                    status=409,
                    content_type="application/json",
                    body=json.dumps({"detail": message}),
                )
            else:
                await route.continue_()

        await page.route("**/api/ai/preferences", refuse_change)
        await _tab_to(page, "Turn AI off")
        await page.keyboard.press("Enter")
        await (
            page.get_by_role("status").filter(has_text="Finish or stop the current scan").wait_for()
        )
        assert await page.get_by_role("heading", name=ON).count() == 1
        assert await page.get_by_role("button", name="Turn AI off").evaluate(
            "e => e === document.activeElement"
        )
    finally:
        await page.context.close()


async def test_retry_scan_respects_ai_off_but_keeps_regular_checks(
    new_page: Any, server: str
) -> None:
    page = await new_page()
    try:
        scans = await (await page.request.get(f"{server}/api/scans")).json()
        scan_id = scans[0]["id"]
        snapshot = await (await page.request.get(f"{server}/api/scans/{scan_id}/settings")).json()
        snapshot["settings"].update(
            {"skip_vlm": False, "skip_semantic": False, "skip_visual": False}
        )

        async def old_settings(route):
            await route.fulfill(json=snapshot)

        await page.route(f"**/api/scans/{scan_id}/settings", old_settings)
        await page.goto(f"{server}/app/scans/new?from={scan_id}", wait_until="networkidle")
        await page.get_by_role("button", name="Local AI checks", exact=True).click()
        vision = page.get_by_role("switch", name="Compare image text with alt text (vision model)")
        wording = page.get_by_role("switch", name="AI review of wording")
        await expect(vision).not_to_be_checked()
        await expect(vision).to_be_disabled()
        await expect(wording).not_to_be_checked()
        await expect(wording).to_be_disabled()
        motion = page.get_by_role("switch", name="Check motion and animation")
        await expect(motion).to_be_checked()
        await expect(motion).to_be_enabled()
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


async def _private_standard(
    page: Any, runtime: dict[str, Any] | None = None, hardware: dict[str, Any] | None = None
) -> None:
    """The plan says the private Standard size is set up; the runtime answers
    ``runtime`` (GET) unless the test routes it itself. ``hardware`` replaces
    parts of the plan's computer (a graphics card's memory, say)."""

    async def plan(route: Any) -> None:
        response = await route.fetch()
        body = await response.json()
        body["current"].update(source="private", backend="llama_cpp", tier="standard")
        body["hardware"].update(hardware or {})
        body["program"]["gpu_build"] = True
        for tier in body["tiers"]:
            tier["installed"] = tier["id"] == "standard"
        await route.fulfill(response=response, json=body)

    await page.route("**/api/ai/plan", plan)
    if runtime is not None:

        async def answer(route: Any) -> None:
            await route.fulfill(json=runtime)

        await page.route("**/api/ai/runtime", answer)


async def _open_change(page: Any) -> None:
    """Once AI is set up, the size choice is inside "Change the AI models"."""
    await page.get_by_text("Change the AI models", exact=True).click()


async def test_choose_a_size_by_keyboard_without_downloading(new_page: Any, server: str) -> None:
    page = await new_page()
    try:
        await page.goto(f"{server}/app/settings/ai")
        group = page.get_by_role("group", name="Choose the AI models")
        await group.wait_for()
        radios = group.get_by_role("radio")
        # Small, Standard, Large, and your own model: one choice.
        assert await radios.count() == 4
        await radios.first.focus()
        await page.keyboard.press("Home")
        await page.keyboard.press("ArrowDown")
        checked = await group.locator("input:checked").get_attribute("value")
        assert checked == "standard"
        button = page.get_by_role("button", name="Download Standard and turn AI on")
        assert await button.count() == 1
        # The download size is said before the button and tied to it, so it
        # is read before anything starts (SC 3.3.2).
        note = page.locator(f"#{await button.get_attribute('aria-describedby')}")
        assert "Download size:" in await note.inner_text() and "GB" in await note.inner_text()
        assert await note.evaluate(
            "(n, b) => !!(n.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)",
            await button.element_handle(),
        )
        # Run from source, the program is not included: the page says what
        # comes from where, in plain words, and names no Ollama.
        version = load_catalog().llama_cpp.version
        await page.get_by_text(
            f"Downloads: the AI program (llama.cpp {version}, MIT licence) from GitHub and "
            "the AI models for the size you choose, from Hugging Face, "
            "a website that shares AI models. "
            "Axcess checks every file first.",
            exact=True,
        ).wait_for()
        assert "Ollama" not in await page.locator("main").inner_text()
    finally:
        await page.context.close()


async def test_remove_by_keyboard_confirms_and_announces(new_page: Any, server_set_up: str) -> None:
    page = await new_page()
    try:
        await page.goto(f"{server_set_up}/app/settings/ai")
        await page.get_by_role("heading", name=ON).wait_for()
        await _tab_to(page, "Change the AI models")
        await page.keyboard.press("Enter")
        await _tab_to(page, "Remove AI features")
        await page.keyboard.press("Enter")
        confirm = page.get_by_role("button", name="Yes, remove AI features")
        await confirm.wait_for()
        assert await confirm.evaluate("e => e === document.activeElement")
        await page.keyboard.press("Enter")
        await page.get_by_role("status").filter(has_text="AI features removed.").wait_for()
        await page.get_by_role("heading", name=ON).wait_for(state="detached")
        focused = await page.evaluate("document.activeElement?.getAttribute('type')")
        assert focused == "radio"
    finally:
        await page.context.close()


async def test_private_runtime_start_by_keyboard_preserves_focus_and_announces(
    new_page: Any, server_set_up: str
) -> None:
    page = await new_page()
    requests = []
    try:

        async def runtime(route):
            if route.request.method == "POST":
                requests.append(route.request.post_data_json)
                await route.fulfill(
                    json={
                        "state": "started",
                        "isolated": True,
                        "reason": None,
                        "download_bytes": None,
                        "tier": None,
                    }
                )
            else:
                await route.fulfill(
                    json={
                        "running": bool(requests),
                        "isolated": bool(requests),
                        "reason": None,
                        "starting": False,
                    }
                )

        await _private_standard(page)
        await page.route("**/api/ai/runtime**", runtime)
        await page.goto(f"{server_set_up}/app/settings/ai")
        await page.get_by_role("heading", name="AI has stopped").wait_for()
        await _tab_to(page, "Start AI again")
        await page.keyboard.press("Enter")
        running = page.get_by_role("heading", name=ON)
        await running.wait_for()
        assert requests == [{"confirm": True}]
        # The button is gone while AI runs (2026-11-17), and focus moved to
        # the state that says so, not back to the top of the page.
        assert await page.get_by_role("button", name="Start AI again").count() == 0
        assert await running.evaluate("e => e === document.activeElement")
        await page.get_by_text(
            "Using the Standard size. It is isolated and stays on this computer.", exact=True
        ).wait_for()
        # A later status check keeps it that way.
        await page.wait_for_timeout(5500)
        assert await page.get_by_role("button", name="Start AI again").count() == 0
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_a_graphics_cards_memory_counts_and_graphics_only_can_be_set(
    new_page: Any, server_set_up: str
) -> None:
    """Developer, 2026-11-19: a separate card's own memory counts toward the
    sizes, the page says so, and "Run AI on the graphics card only" is one
    checkbox by Turn AI on/off that saves at once."""
    page = await new_page(viewport={"width": 320, "height": 900})
    try:
        running = {"running": True, "isolated": True, "reason": None, "starting": False}
        card = {"gpu_memory_gb": 8, "ai_memory_gb": 24, "accelerator": "nvidia"}
        await _private_standard(page, running, card)
        await page.goto(f"{server_set_up}/app/settings/ai")
        await page.get_by_role("heading", name=ON).wait_for()
        box = page.get_by_role("checkbox", name="Run AI on the graphics card only")
        assert not await box.is_checked()
        description = await box.evaluate(
            "el => el.getAttribute('aria-describedby').split(' ')"
            ".map(id => document.getElementById(id).textContent).join(' ')"
        )
        assert "If they do not fit, AI does not start." in description
        assert "This graphics card has 8 GB of its own memory." in description
        assert "Changing this restarts AI if it is on." in description
        await box.focus()
        await page.keyboard.press("Space")
        await page.get_by_text(
            "Saved. If AI was running, it restarted with this setting. "
            "The AI state above says whether it is on.",
            exact=True,
        ).wait_for()
        assert await box.is_checked()
        saved = await (await page.request.get(f"{server_set_up}/api/ai/preferences")).json()
        assert saved["gpu_only"] is True

        await _open_change(page)
        await page.get_by_text("This computer has 16 GB of memory", exact=False).first.wait_for()
        assert (
            await page.get_by_text(
                "and an NVIDIA graphics card with 8 GB of its own memory. "
                "The AI uses both, so the sizes count 24 GB.",
                exact=False,
            ).count()
            == 1
        )
        group = page.get_by_role("group", name="Choose the AI models")
        await group.locator("input[value='large']").check()
        large = page.get_by_role("button", name="Download Large and switch to it")
        await large.wait_for()
        note = await page.locator(f"#{await large.get_attribute('aria-describedby')}").inner_text()
        assert note.endswith(
            "this computer has 24 GB, counting the 8 GB on its graphics card, "
            "so it may answer very slowly or stop."
        )
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_a_running_service_shows_no_start_button(new_page: Any, server_set_up: str) -> None:
    page = await new_page()
    try:
        running = {"running": True, "isolated": True, "reason": None, "starting": False}
        await _private_standard(page, running)
        await page.goto(f"{server_set_up}/app/settings/ai")
        await page.get_by_role("heading", name=ON).wait_for()
        await page.get_by_text(
            "Using the Standard size. It is isolated and stays on this computer.", exact=True
        ).wait_for()
        assert await page.get_by_role("button", name="Start AI again").count() == 0
    finally:
        await page.context.close()


async def test_a_size_that_is_set_up_offers_no_download(new_page: Any, server_set_up: str) -> None:
    """After the download, the chosen size says it is set up (2026-11-17).

    Choosing another size brings the download button back.
    """
    page = await new_page(viewport={"width": 320, "height": 900})
    try:
        running = {"running": True, "isolated": True, "reason": None, "starting": False}
        await _private_standard(page, running)
        await page.goto(f"{server_set_up}/app/settings/ai")
        await page.get_by_role("heading", name=ON).wait_for()
        await _open_change(page)
        await page.get_by_text(
            "Standard is set up on this computer. Nothing to download.", exact=True
        ).wait_for()
        download = page.get_by_role("button", name=re.compile("^Download "))
        assert await download.count() == 0
        group = page.get_by_role("group", name="Choose the AI models")
        await group.locator("input[value='small']").check()
        # AI is on, so the download switches to the new size.
        await page.get_by_role("button", name="Download Small and switch to it").wait_for()
        # Large is for 32 GB or more: on this 16 GB computer it can still be
        # downloaded, and the note before the button warns (developer,
        # 2026-11-18: refuse only Standard and Large on 8 GB or less).
        await group.locator("input[value='large']").check()
        large = page.get_by_role("button", name="Download Large and switch to it")
        await large.wait_for()
        note = await page.locator(f"#{await large.get_attribute('aria-describedby')}").inner_text()
        assert note.endswith(
            "Large is for computers with 32 GB of memory or more, and this computer has "
            "16 GB, so it may answer very slowly or stop."
        )
        assert await page.get_by_text("Choose a smaller size.").count() == 0
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_missing_private_model_shows_size_without_downloading(
    new_page: Any, server_set_up: str
) -> None:
    page = await new_page(viewport={"width": 320, "height": 900})
    downloads = []
    try:

        async def runtime(route):
            if route.request.method == "POST":
                await route.fulfill(
                    json={
                        "state": "model_missing",
                        "isolated": False,
                        "reason": None,
                        "download_bytes": 4_390_000_000,
                        "tier": "small",
                    }
                )
            else:
                await route.fulfill(
                    json={"running": False, "isolated": False, "reason": None, "starting": False}
                )

        async def install(route):
            if route.request.method == "POST":
                downloads.append(route.request.post_data_json)
            await route.continue_()

        await _private_standard(page)
        await page.route("**/api/ai/runtime**", runtime)
        await page.route("**/api/ai/install", install)
        await page.goto(f"{server_set_up}/app/settings/ai")
        await page.get_by_role("button", name="Start AI again", exact=True).click()
        await page.get_by_role("status").filter(has_text="4.4 GB").wait_for()
        assert downloads == []
        assert (
            await page.evaluate(
                "document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            <= 0
        )
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


@pytest.mark.parametrize(
    ("step", "label"),
    [
        ("program", "Downloading the AI program"),
        ("starting", "Starting the private AI service"),
    ],
)
async def test_download_progress_names_the_private_ai_service(
    new_page: Any, server: str, step: str, label: str
) -> None:
    """The progress words name Axcess's own service, not Ollama."""
    page = await new_page()
    status = {
        "state": "running",
        "tier": "small",
        "step": step,
        "step_done_bytes": 0,
        "step_total_bytes": 0,
        "done_bytes": 1_000_000_000,
        "total_bytes": 4_000_000_000,
        "error": None,
    }
    try:

        async def plan(route):
            response = await route.fetch()
            data = await response.json()
            data["install"] = status
            await route.fulfill(json=data)

        async def install(route):
            # Only the progress read is faked; nothing may start a download.
            assert route.request.method == "GET"
            await route.fulfill(json=status)

        await page.route("**/api/ai/plan", plan)
        await page.route("**/api/ai/install", install)
        await page.goto(f"{server}/app/settings/ai")
        await page.get_by_text(label, exact=True).first.wait_for()
        await page.get_by_role("status").filter(has_text=f"{label}.").wait_for()
        assert "Ollama" not in await page.locator("main").inner_text()
    finally:
        await page.context.close()


async def test_your_own_model_is_one_of_the_choices_and_errors_say_what_to_do(
    new_page: Any, server: str
) -> None:
    """WCAG 2.2 SC 3.3.1 and 3.3.3: the error is text under its field, the
    field is marked and focused, and the text says what to enter."""
    page = await new_page(viewport={"width": 320, "height": 900})
    try:
        await page.goto(f"{server}/app/settings/ai")
        group = page.get_by_role("group", name="Choose the AI models")
        await group.get_by_role("radio", name="Your own model").check()
        await page.get_by_role("button", name="Copy and use this model").click()
        model = page.get_by_label("Model file (GGUF)", exact=True)
        await page.get_by_text("Error: Choose a model file.", exact=False).wait_for()
        assert await model.get_attribute("aria-invalid") == "true"
        assert await model.evaluate("e => e === document.activeElement")
        described = await model.get_attribute("aria-describedby")
        error = page.locator(f"#{described.split()[-1]}")
        assert "ends in .gguf" in await error.inner_text()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        assert (
            await page.evaluate(
                "document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            <= 0
        )
    finally:
        await page.context.close()


async def test_an_answer_setting_out_of_range_is_named_under_its_field(
    new_page: Any, server: str, tmp_path: Path
) -> None:
    page = await new_page()
    try:
        await page.goto(f"{server}/app/settings/ai")
        await page.get_by_role("radio", name="Your own model").check()
        gguf = tmp_path / "tiny.gguf"
        gguf.write_bytes(b"GGUF" + bytes(40))
        await page.get_by_label("Model file (GGUF)", exact=True).set_input_files(str(gguf))
        await page.get_by_text("Answer settings (sampling), optional").click()
        temp = page.get_by_label("Randomness (temperature), 0 to 2")
        await temp.fill("5")
        await page.get_by_role("button", name="Copy and use this model").click()
        await page.get_by_text("Error: Enter a number from 0 to 2", exact=False).wait_for()
        assert await temp.get_attribute("aria-invalid") == "true"
        assert await temp.evaluate("e => e === document.activeElement")
        # Fixing the value clears the error.
        await temp.fill("0.6")
        assert await temp.get_attribute("aria-invalid") is None
    finally:
        await page.context.close()


async def test_your_own_model_in_use_is_the_chosen_option(
    new_page: Any, server_set_up: str
) -> None:
    """After using your own model, the choice shows it, not a size
    (developer, 2026-11-17: "the size of AI models should switch to custom")."""
    page = await new_page()
    try:
        sha = "a" * 64

        async def plan(route):
            response = await route.fetch()
            body = await response.json()
            body["current"].update(
                source="private",
                backend="llama_cpp",
                tier="custom",
                vision_model="",
                custom_model={
                    "tag": "my-qwen3.8-4b-aaaaaaaa",
                    "size": 10,
                    "gguf": {"sha256": sha},
                    "mmproj": None,
                },
            )
            body["my_models"] = [
                {
                    "sha256": sha,
                    "file": "Qwen3.8-4B-Q4_K_M.gguf",
                    "size": 10,
                    "kind": "model",
                    "name": "Qwen3.8 4B",
                    "for_model": None,
                }
            ]
            await route.fulfill(response=response, json=body)

        async def runtime(route):
            await route.fulfill(
                json={"running": True, "isolated": True, "reason": None, "starting": False}
            )

        await page.route("**/api/ai/plan", plan)
        await page.route("**/api/ai/runtime", runtime)
        await page.goto(f"{server_set_up}/app/settings/ai")
        await page.get_by_text(
            "Using your own model (Qwen3.8 4B, text only). It is isolated and stays on this "
            "computer.",
            exact=True,
        ).wait_for()
        await _open_change(page)
        own = page.get_by_role("radio", name="Your own model (in use now)")
        assert await own.is_checked()
        assert await page.get_by_text("In use now", exact=True).count() == 1
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_a_refusal_for_low_memory_appears_right_under_its_button(
    new_page: Any, server_set_up: str
) -> None:
    """Developer, 2026-11-17: the error ... should appear right above or under
    the button, not at the top of the page (SC 3.3.1, SC 4.1.3). Since
    2026-11-18 the only memory refusal is a size on a computer with less
    memory than it is for; low free memory warns instead."""
    page = await new_page()
    refusal = (
        "The Standard size is for computers with 16 GB of memory or more, and this computer "
        "has 8 GB. Choose a smaller size."
    )
    try:

        async def preferences(route):
            if route.request.method == "PUT":
                await route.fulfill(status=503, json={"detail": refusal})
            else:
                await route.continue_()

        await page.route("**/api/ai/preferences", preferences)
        await page.goto(f"{server_set_up}/app/settings/ai", wait_until="networkidle")
        button = page.get_by_role("button", name=re.compile("^Turn AI (on|off)$"))
        await button.click()
        await page.get_by_text(refusal, exact=True).wait_for()
        # The very next element after the button is the message.
        follows = await button.evaluate(
            "b => b.nextElementSibling && b.nextElementSibling.textContent"
        )
        assert follows == refusal
    finally:
        await page.context.close()
