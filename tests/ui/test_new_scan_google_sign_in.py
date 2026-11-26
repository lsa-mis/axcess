"""New scan's "Sign in to Google for Google files" (2026-11-26).

Playwright against the built SPA and the real server routes, with the
Google browser swapped for ``FakeGoogleSession``: no browser opens on
Google and nothing contacts it.

- The switch: off by default, under the document check and only while it
  is on, with its description; in a sign-in scan too (2026-11-26), with
  its own description.
- Starting with it on shows the Google card instead of a scan, with its
  buttons; "start" before Google says signed in shows the error as text;
  Cancel returns to the form with the entries kept.
- The card is axe-clean and works by keyboard alone.
- A sign-in scan with it on (2026-11-26): the sign-in card's step 1 says
  "next: sign in to Google"; step 2 is the Google window, with its own
  start; Cancel ends both and refills the form; leaving New scan and coming
  back shows the step it was on. The site's sign-in browser is
  ``FakeSignInSession``.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from ._fake_google_sign_in import FakeGoogleSession
from .test_accessibility_axe import _open_scan_groups, _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
playwright_async = pytest.importorskip("playwright.async_api")
expect = playwright_async.expect

SWITCH = "Sign in to Google for Google files"
# The switch's name starts with its label (SwitchRow's label wraps the hint).
SWITCH_NAME = re.compile(r"^Sign in to Google for Google files")
DOCUMENTS = "Check the documents the pages link to"
SITE = "https://www.example.edu/"
START = "I\u2019m signed in to Google, start scan"
CANCEL = "Cancel Google sign-in"
NOT_SIGNED_IN = (
    "Google says you are not signed in yet. Finish signing in in the Google window, then try again."
)


# Each switch's label line, not its hint.
_SWITCH_LABELS = (
    "els => els.map(el => el.closest('label').querySelector('span.font-semibold').textContent)"
)


@pytest.fixture
def fake_google(monkeypatch: pytest.MonkeyPatch) -> type[FakeGoogleSession]:
    """Swap the Google browser in apps made after this (list it before live_server)."""
    from audit.web import server

    monkeypatch.setattr(FakeGoogleSession, "instances", [])
    monkeypatch.setattr(FakeGoogleSession, "signed_in", False)
    monkeypatch.setattr(FakeGoogleSession, "fail_start", False)
    monkeypatch.setattr(FakeGoogleSession, "fail_handover", False)
    monkeypatch.setattr(server, "GoogleBrowserSession", FakeGoogleSession)
    return FakeGoogleSession


async def test_the_switch_is_off_under_the_document_check(
    fake_google: type, live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await _open_scan_groups(page)
    google = page.get_by_role("switch", name=SWITCH_NAME)
    await expect(google).not_to_be_checked()
    await expect(google).to_be_enabled()
    await expect(google).to_have_accessible_description(
        re.compile(
            "Off by default.*a browser window opens before the scan for you to sign in to Google.*"
            "reads when each Google Doc, Sheet and Slides file was created and last changed.*"
            "one each second, and changes nothing.*signs out and deletes that browser.s data"
        )
    )
    # Right after the document check, in the same list.
    names = (
        await page.get_by_role("group", name="Checks", exact=True)
        .get_by_role("switch")
        .evaluate_all(_SWITCH_LABELS)
    )
    assert names[names.index(DOCUMENTS) + 1] == SWITCH
    # Gone while the document check is off: it would do nothing.
    await page.get_by_role("switch", name=DOCUMENTS).click()
    await expect(google).to_have_count(0)


async def test_the_switch_works_in_a_sign_in_scan_with_its_own_hint(
    fake_google: type, live_server: tuple[str, int], new_page: Any
) -> None:
    """Usable on the sign-in tab since 2026-11-26: off by default, in the
    same place, saying the Google window is a second, separate one."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new?mode=login", wait_until="networkidle")
    await _open_scan_groups(page)
    google = page.get_by_role("switch", name=SWITCH_NAME)
    await expect(google).to_be_enabled()
    await expect(google).not_to_be_checked()
    await expect(google).to_have_accessible_description(
        re.compile(
            "^Off by default. When on, after you sign in to the site, a second, separate browser "
            "window opens for you to sign in to Google.*"
            "reads when each Google Doc, Sheet and Slides file was created and last changed.*"
            "Axcess uses the Google window only for these Google files. It checks the site.s "
            "pages in the site.s own browser, without your Google sign-in. When the scan ends, "
            "Axcess signs out of Google and deletes both browsers. data.$"
        )
    )
    names = (
        await page.get_by_role("group", name="Checks", exact=True)
        .get_by_role("switch")
        .evaluate_all(_SWITCH_LABELS)
    )
    assert names[names.index(DOCUMENTS) + 1] == SWITCH
    await google.check()
    await expect(google).to_be_checked()
    await page.get_by_role("switch", name=DOCUMENTS).click()
    await expect(google).to_have_count(0)


async def _start_with_google(page: Any, base: str) -> None:
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await page.get_by_role("textbox", name="Website address", exact=True).fill(SITE)
    await _open_scan_groups(page)
    await page.get_by_role("switch", name=SWITCH_NAME).check()
    await page.get_by_role("button", name="Start scan").click()


async def test_starting_shows_the_google_card_and_cancel_keeps_the_entries(
    fake_google: type[FakeGoogleSession], live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _start_with_google(page, base)

    heading = page.get_by_role("heading", name="Sign in to Google", exact=True)
    await expect(heading).to_be_visible()
    await expect(heading).to_be_focused()
    await expect(page).to_have_url(re.compile(r"google_sign_in="))
    await expect(
        page.get_by_text(
            "A browser window opened. Sign in to Google there, with the account that can "
            "open the site\u2019s Google files. Then come back and start the scan."
        )
    ).to_be_visible()
    start = page.get_by_role("button", name=START)
    await expect(start).to_be_visible()

    await start.click()
    alert = page.get_by_role("alert")
    await expect(alert).to_have_text(NOT_SIGNED_IN)
    assert fake_google.instances[0].signed_in_checks == 1

    await page.get_by_role("button", name=CANCEL).click()
    notice = page.get_by_role("status").filter(has_text="You cancelled the Google sign-in.")
    await expect(notice).to_be_visible()
    await expect(notice).to_be_focused()
    await expect(page).not_to_have_url(re.compile(r"google_sign_in="))
    await expect(page.get_by_role("textbox", name="Website address", exact=True)).to_have_value(
        SITE
    )
    await _open_scan_groups(page)
    await expect(page.get_by_role("switch", name=SWITCH_NAME)).to_be_checked()
    assert fake_google.instances[0].closed == 1


async def test_a_waiting_google_sign_in_comes_back_after_leaving_new_scan(
    fake_google: type[FakeGoogleSession], live_server: tuple[str, int], new_page: Any
) -> None:
    """The same as a site sign-in (2026-11-26, "copy the same UX and logic"):
    leaving New scan, or the public tab, and coming back shows the waiting
    Google sign-in's card, not an empty form; cancelling it refills the form
    from the settings the server kept."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _start_with_google(page, base)
    heading = page.get_by_role("heading", name="Sign in to Google", exact=True)
    await expect(heading).to_be_visible()
    first = re.search(r"google_sign_in=([^&]+)", page.url)
    assert first is not None

    # Away to Reports, then New scan from a fresh address: the card is back.
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await expect(heading).to_be_visible()
    await expect(page).to_have_url(re.compile(rf"google_sign_in={re.escape(first.group(1))}"))
    await expect(page.get_by_role("button", name=START)).to_be_visible()

    # The sign-in tab, then the public tab again: the card again.
    await page.get_by_role("tab", name=re.compile(r"^Site with a sign-in")).click()
    await expect(heading).to_have_count(0)
    await page.get_by_role("tab", name="Public website", exact=True).click()
    await expect(heading).to_be_visible()

    # Cancelled from a page opened afresh: the form is refilled.
    await page.get_by_role("button", name=CANCEL).click()
    await expect(page.get_by_role("textbox", name="Website address", exact=True)).to_have_value(
        SITE
    )
    assert len(fake_google.instances) == 1


async def test_the_google_card_is_axe_clean_and_works_by_keyboard(
    fake_google: type[FakeGoogleSession],
    live_server: tuple[str, int],
    new_page: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from audit.web import server

    started: list[Any] = []

    async def _no_crawl(_db: Any, config: Any, *, google_files: Any = None) -> None:
        started.append(google_files)

    monkeypatch.setattr(server, "_run_background_crawl", _no_crawl)
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _start_with_google(page, base)
    await expect(page.get_by_role("heading", name="Sign in to Google", exact=True)).to_be_focused()

    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # Keyboard only: Tab from the heading reaches Start, Enter presses it.
    fake_google.signed_in = True
    start = page.get_by_role("button", name=START)
    for _ in range(10):
        await page.keyboard.press("Tab")
        if await start.evaluate("el => el === document.activeElement"):
            break
    await expect(start).to_be_focused()
    await page.keyboard.press("Enter")
    await expect(page).to_have_url(re.compile(r"/app/scans/\d+$"))
    assert started and started[0] is fake_google.instances[0]
    assert fake_google.instances[0].scanning


async def test_a_closed_google_window_offers_cancel_only(
    fake_google: type[FakeGoogleSession], live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _start_with_google(page, base)
    await expect(page.get_by_role("heading", name="Sign in to Google", exact=True)).to_be_visible()
    fake_google.instances[0].close_window()
    closed = page.get_by_role("heading", name="The Google window is closed", exact=True)
    await expect(closed).to_be_visible()
    await expect(closed).to_be_focused()
    await expect(page.get_by_role("button", name=START)).to_have_count(0)
    await expect(page.get_by_role("button", name=CANCEL)).to_be_visible()
    await expect(
        page.get_by_text(re.compile("Axcess signs out of Google and deletes that browser"))
    ).to_be_visible()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


# -- a sign-in scan with the Google sign-in (2026-11-26) ---------------------

SIGN_IN_SEED = "https://app.example.test/secure/"
NEXT = "I\u2019m signed in to the site, next: sign in to Google"
SITE_START = "I\u2019m signed in, start scan"
STEP_1 = "Step 1 of 2: sign in to the site"
STEP_2 = "Step 2 of 2: sign in to Google"
SITE_OPEN = "Sign in using the Chromium window"
GOOGLE_OPEN = "Now sign in to Google"


async def _start_sign_in_with_google(page: Any, base: str) -> None:
    await page.goto(f"{base}/app/scans/new?mode=login", wait_until="networkidle")
    await page.get_by_role("textbox", name=re.compile(r"^Website address to scan")).fill(
        SIGN_IN_SEED
    )
    await page.get_by_role("checkbox", name=re.compile(r"^The site owner allows this scan")).check()
    await _open_scan_groups(page)
    await page.get_by_role("switch", name=SWITCH_NAME).check()
    await page.get_by_role("button", name="Open browser to sign in").click()


async def _focused_heading(page: Any) -> str:
    return str(
        await page.evaluate(
            "() => document.activeElement?.tagName === 'H2'"
            " ? document.activeElement.textContent.trim() : ''"
        )
    )


async def test_a_sign_in_scan_goes_site_then_google_and_cancel_ends_both(
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _start_sign_in_with_google(page, base)

    # Step 1: the site's window, as before, but "next", not "start".
    site_heading = page.get_by_role("heading", name=SITE_OPEN, exact=True)
    await expect(site_heading).to_be_visible()
    await expect(page.get_by_text(STEP_1, exact=True)).to_be_visible()
    await expect(page.get_by_role("button", name=SITE_START)).to_have_count(0)
    next_button = page.get_by_role("button", name=NEXT)
    await expect(next_button).to_be_visible()
    await expect(page.get_by_role("button", name="Cancel sign-in")).to_be_visible()
    await expect(page.get_by_role("heading", name="What happens next")).to_be_visible()
    assert fake_google.instances == []

    # Step 2: a second, separate Google window.
    await next_button.click()
    google_heading = page.get_by_role("heading", name=GOOGLE_OPEN, exact=True)
    await expect(google_heading).to_be_visible()
    await expect(google_heading).to_be_focused()
    await expect(page.get_by_text(STEP_2, exact=True)).to_be_visible()
    await expect(
        page.get_by_role("status").filter(has_text="A browser window opened. Sign in to Google")
    ).to_have_text(
        "A browser window opened. Sign in to Google there, with the account that can "
        "open the site\u2019s Google files. Then come back and start the scan."
    )
    assert len(fake_google.instances) == 1
    assert fake_google.instances[0] is not fake_sign_in.instances[0]
    assert fake_sign_in.instances[0].window_open, "the site's window stays as it was"
    start = page.get_by_role("button", name=START)
    for name in (START, "Cancel sign-in"):
        box = await page.get_by_role("button", name=name).bounding_box()
        assert box is not None and box["height"] >= 44, (name, box)

    # Google says not signed in yet: the same words as the public card.
    await start.click()
    await expect(page.get_by_role("alert")).to_have_text(NOT_SIGNED_IN)
    assert fake_google.instances[0].signed_in_checks == 1

    # Cancel sign-in ends both and refills the form.
    await page.get_by_role("button", name="Cancel sign-in").click()
    notice = page.get_by_role("status").filter(has_text="You cancelled the sign-in.")
    await expect(notice).to_have_text(
        "You cancelled the sign-in. Axcess closed the sign-in window and forgot your sign-in. "
        "Your settings are still filled in. Axcess also signed out of Google and deleted the "
        "Google browser\u2019s data."
    )
    await expect(notice).to_be_focused()
    await expect(page).not_to_have_url(re.compile(r"sign_in="))
    await expect(
        page.get_by_role("textbox", name=re.compile(r"^Website address to scan"))
    ).to_have_value(SIGN_IN_SEED)
    await _open_scan_groups(page)
    await expect(page.get_by_role("switch", name=SWITCH_NAME)).to_be_checked()
    assert fake_sign_in.instances[0].closed
    assert fake_google.instances[0].closed == 1


async def test_a_sign_in_scan_returns_to_the_step_it_was_on(
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _start_sign_in_with_google(page, base)
    await expect(page.get_by_role("heading", name=SITE_OPEN, exact=True)).to_be_visible()

    # Left on step 1: back on step 1.
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await expect(page.get_by_role("heading", name=SITE_OPEN, exact=True)).to_be_visible()
    await expect(page.get_by_role("button", name=NEXT)).to_be_visible()

    # Left on step 2: back on step 2, with the same Google window.
    await page.get_by_role("button", name=NEXT).click()
    await expect(page.get_by_role("heading", name=GOOGLE_OPEN, exact=True)).to_be_visible()
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await expect(page.get_by_role("heading", name=GOOGLE_OPEN, exact=True)).to_be_visible()
    await expect(page.get_by_text(STEP_2, exact=True)).to_be_visible()
    await expect(page.get_by_role("button", name=START)).to_be_visible()
    assert len(fake_google.instances) == 1

    # A closed Google window: said in words, Cancel only.
    fake_google.instances[0].close_window()
    closed = page.get_by_role("heading", name="The Google window is closed", exact=True)
    await expect(closed).to_be_visible()
    await expect(closed).to_be_focused()
    await expect(page.get_by_role("button", name=START)).to_have_count(0)
    await expect(page.get_by_role("button", name="Cancel sign-in")).to_be_visible()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


async def test_a_sign_in_scan_with_google_is_axe_clean_and_works_by_keyboard(
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
    monkeypatch: pytest.MonkeyPatch,
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    import asyncio

    from audit.web import server

    runs: list[Any] = []

    async def _scan_that_keeps_preparing(_db: Any, _blobs: Any, _config: Any, run: Any) -> None:
        runs.append(run)
        await asyncio.sleep(3600)

    monkeypatch.setattr(server, "_run_local_login_background", _scan_that_keeps_preparing)
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _start_sign_in_with_google(page, base)
    await expect(page.get_by_role("heading", name=SITE_OPEN, exact=True)).to_be_visible()
    assert await _focused_heading(page) == SITE_OPEN
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # Keyboard only: Tab from the heading to "next", Enter.
    next_button = page.get_by_role("button", name=NEXT)
    for _ in range(10):
        await page.keyboard.press("Tab")
        if await next_button.evaluate("el => el === document.activeElement"):
            break
    await expect(next_button).to_be_focused()
    await page.keyboard.press("Enter")
    await expect(page.get_by_role("heading", name=GOOGLE_OPEN, exact=True)).to_be_focused()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    fake_google.signed_in = True
    start = page.get_by_role("button", name=START)
    for _ in range(12):
        await page.keyboard.press("Tab")
        if await start.evaluate("el => el === document.activeElement"):
            break
    await expect(start).to_be_focused()
    await page.keyboard.press("Enter")
    await expect(page).to_have_url(re.compile(r"mode=login&scan=\d+"))
    assert runs and runs[0].google is fake_google.instances[0]
    assert runs[0].session is fake_sign_in.instances[0]
    assert fake_google.instances[0].scanning
