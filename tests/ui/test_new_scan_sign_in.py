"""New scan's sign-in card, before a sign-in scan exists.

Playwright against the built SPA and the real server routes, with the
sign-in browser swapped for ``FakeSignInSession`` (see ``_fake_sign_in``):
these tests are about what the page says and does, not about Chromium.

- New scan opened without a tab or card in its address returns to a
  waiting sign-in, and the Public website tab still works.
- Each face of the card says what it should: window open, window closed
  with Reopen, and back on the form after Cancel and after expiry, with the
  person's entries kept.
- Reports shows nothing for a sign-in that has not started a scan.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from .test_accessibility_axe import _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
playwright_async = pytest.importorskip("playwright.async_api")
expect = playwright_async.expect

SITE = "app.example.test"
SEED = f"https://{SITE}/secure/"
START = "I\u2019m signed in, start scan"
OPEN_TITLE = "Sign in using the Chromium window"
CLOSED_TITLE = "The sign-in window is closed"


async def _open_sign_in_through_the_api(page: Any, base: str) -> str:
    """Open a sign-in as the form would, and return its ID."""
    response = await page.request.post(
        f"{base}/api/local-login-scans",
        headers={"origin": base},
        data={"seed_url": SEED, "approved_auth_origins": [], "authorization_acknowledged": True},
    )
    assert response.status == 201, await response.text()
    return str((await response.json())["sign_in_id"])


async def _fill_and_submit_the_login_form(page: Any, base: str) -> None:
    await page.goto(f"{base}/app/scans/new?mode=login", wait_until="networkidle")
    await page.get_by_role("textbox", name=re.compile(r"^Website address to scan")).fill(SEED)
    await page.get_by_role("checkbox", name=re.compile(r"^The site owner allows this scan")).check()
    await page.get_by_role("button", name="Open browser to sign in").click()


async def _heading_has_focus(page: Any, name: str) -> bool:
    return bool(
        await page.evaluate(
            "(name) => document.activeElement?.tagName === 'H2'"
            " && document.activeElement.textContent.trim() === name",
            name,
        )
    )


async def test_new_scan_without_a_tab_returns_to_the_waiting_sign_in(
    fake_sign_in: type, live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    sign_in_id = await _open_sign_in_through_the_api(page, base)
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    entries_before = await page.evaluate("history.length")

    # The sidebar's New scan link: no tab and no card in the address.
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")

    await expect(page).to_have_url(re.compile(rf"mode=login.*sign_in={sign_in_id}"))
    # Replaced, not pushed: one entry for New scan, as for any visit.
    assert await page.evaluate("history.length") == entries_before + 1
    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()
    await expect(page.get_by_text("Sign-in", exact=True)).to_be_visible()
    await expect(page.get_by_text(f"You have a sign-in in progress for {SITE}.")).to_be_visible()
    await expect(page.get_by_text(re.compile(r"^Sign-in scan #"))).to_have_count(0)

    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # The Public website tab is one click away and stays there.
    await page.get_by_role("tab", name="Public website").click()
    await expect(page.get_by_role("textbox", name="Website address", exact=True)).to_be_visible()
    await expect(page).not_to_have_url(re.compile(r"sign_in="))
    await page.wait_for_timeout(1500)
    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_have_count(0)


async def test_switching_tabs_keeps_the_waiting_sign_in(
    fake_sign_in: type, live_server: tuple[str, int], new_page: Any
) -> None:
    """Public website and back shows the waiting card, not the empty form."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    sign_in_id = await _open_sign_in_through_the_api(page, base)
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()
    entries_before = await page.evaluate("history.length")

    await page.get_by_role("tab", name="Public website").click()
    await expect(page.get_by_role("textbox", name="Website address", exact=True)).to_be_visible()
    await page.get_by_role("tab", name="Site with a sign-in or two-step sign-in (2FA)").click()

    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()
    await expect(page).to_have_url(re.compile(rf"mode=login.*sign_in={sign_in_id}"))
    await expect(
        page.get_by_role("textbox", name=re.compile(r"^Website address to scan"))
    ).to_have_count(0)
    # Two tab changes, two entries: the card's return replaces, adds none.
    assert await page.evaluate("history.length") == entries_before + 2


async def test_a_sign_in_address_without_https_is_completed(
    fake_sign_in: type, live_server: tuple[str, int], new_page: Any
) -> None:
    """Typed without its scheme, the address is sent as https:// (lib/webAddress.ts)."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new?mode=login", wait_until="networkidle")
    field = page.get_by_role("textbox", name=re.compile(r"^Website address to scan"))
    await field.fill(f"{SITE}/secure/")
    await page.keyboard.press("Tab")
    await expect(field).to_have_value(SEED)
    await page.get_by_role("checkbox", name=re.compile(r"^The site owner allows this scan")).check()
    async with page.expect_request("**/api/local-login-scans") as sent:
        await page.get_by_role("button", name="Open browser to sign in").click()
    assert (await sent.value).post_data_json["seed_url"] == SEED


async def test_switching_tabs_keeps_a_sign_in_started_after_the_first_visit(
    fake_sign_in: type, live_server: tuple[str, int], new_page: Any
) -> None:
    """The first trip back must show the card, not an answer from before the sign-in.

    New scan's first visit learns "no sign-in yet"; that answer stayed in the
    page and was used on the next return to the sign-in tab, so the empty form
    showed and only the second return found the card.
    """
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await expect(page.get_by_role("textbox", name="Website address", exact=True)).to_be_visible()

    sign_in_tab = page.get_by_role("tab", name="Site with a sign-in or two-step sign-in (2FA)")
    await sign_in_tab.click()
    await page.get_by_role("textbox", name=re.compile(r"^Website address to scan")).fill(SEED)
    await page.get_by_role("checkbox", name=re.compile(r"^The site owner allows this scan")).check()
    await page.get_by_role("button", name="Open browser to sign in").click()
    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()

    await page.get_by_role("tab", name="Public website").click()
    await expect(page.get_by_role("textbox", name="Website address", exact=True)).to_be_visible()
    await sign_in_tab.click()

    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()
    await expect(
        page.get_by_role("textbox", name=re.compile(r"^Website address to scan"))
    ).to_have_count(0)


async def test_new_scan_shows_the_form_when_no_sign_in_waits(
    fake_sign_in: type, live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")

    await expect(page.get_by_role("textbox", name="Website address", exact=True)).to_be_visible()
    await expect(page).not_to_have_url(re.compile(r"sign_in="))


async def test_the_card_while_the_window_is_open_then_closed_then_reopened(
    fake_sign_in: type, live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _fill_and_submit_the_login_form(page, base)

    # Window open.
    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()
    assert await _heading_has_focus(page, OPEN_TITLE)
    await expect(page.get_by_text("Sign-in", exact=True)).to_be_visible()
    await expect(page.get_by_role("button", name=START)).to_be_visible()
    await expect(page.get_by_role("button", name="Cancel sign-in")).to_be_visible()
    await expect(page.get_by_role("button", name="Reopen sign-in window")).to_have_count(0)
    await expect(
        page.get_by_text(
            "If you close the sign-in window before you start, Axcess keeps your sign-in "
            "for 30 minutes, in memory only."
        )
    ).to_be_visible()

    # The person closes the sign-in window.
    fake_sign_in.instances[0].close_window()
    await expect(page.get_by_role("heading", name=CLOSED_TITLE)).to_be_visible()
    assert await _heading_has_focus(page, CLOSED_TITLE)
    await expect(
        page.get_by_role("status").filter(has_text="Axcess has kept your sign-in")
    ).to_have_text("Axcess has kept your sign-in, so you can start the scan or reopen the window.")
    await expect(
        page.get_by_text(
            "Some sites tie a sign-in to the exact browser window, or end it quickly. If yours "
            "does, the site may ask you to sign in again after you reopen the window."
        )
    ).to_be_visible()
    await expect(
        page.get_by_text(
            "Axcess keeps your sign-in in memory only. If you do not start the scan or reopen "
            "the window within 30 minutes, Axcess forgets it."
        )
    ).to_be_visible()
    await expect(page.get_by_role("button", name=START)).to_be_visible()
    reopen = page.get_by_role("button", name="Reopen sign-in window")
    await expect(reopen).to_be_visible()
    await expect(page.get_by_role("button", name="Cancel sign-in")).to_be_visible()
    for name in (START, "Reopen sign-in window", "Cancel sign-in"):
        box = await page.get_by_role("button", name=name).bounding_box()
        assert box is not None and box["height"] >= 44, (name, box)

    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # By keyboard: Reopen opens a new window and the card returns to "open".
    await reopen.focus()
    await page.keyboard.press("Enter")
    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()
    assert await _heading_has_focus(page, OPEN_TITLE)
    assert fake_sign_in.instances[0].reopened == 1


async def test_cancel_returns_to_the_form_with_the_entries_kept(
    fake_sign_in: type, live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _fill_and_submit_the_login_form(page, base)
    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()

    await page.get_by_role("button", name="Cancel sign-in").click()

    notice = page.get_by_role("status").filter(has_text="You cancelled the sign-in.")
    await expect(notice).to_have_text(
        "You cancelled the sign-in. Axcess closed the sign-in window and forgot your sign-in. "
        "Your settings are still filled in."
    )
    assert await notice.evaluate("el => el === document.activeElement")
    await expect(page).to_have_url(re.compile(r"mode=login"))
    await expect(page).not_to_have_url(re.compile(r"sign_in="))
    await expect(
        page.get_by_role("textbox", name=re.compile(r"^Website address to scan"))
    ).to_have_value(SEED)
    await expect(
        page.get_by_role("checkbox", name=re.compile(r"^The site owner allows"))
    ).to_be_checked()
    session = fake_sign_in.instances[0]
    assert session.closed and session.kept is None


async def test_an_expired_sign_in_returns_to_the_form_and_says_why(
    fake_sign_in: type,
    monkeypatch: pytest.MonkeyPatch,
    seeded_db: tuple[Path, Path, int],
    new_page: Any,
    request: pytest.FixtureRequest,
) -> None:
    from audit.web import local_sign_in

    # The product limit is 30 minutes; the test cannot wait that long, so the
    # clock's limit is cut to 2 seconds. The words still say 30 minutes,
    # which is what the product does.
    monkeypatch.setattr(local_sign_in, "SIGN_IN_KEEP_SECONDS", 2)
    base, _ = request.getfixturevalue("live_server")
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _fill_and_submit_the_login_form(page, base)
    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()

    fake_sign_in.instances[0].close_window()
    await expect(page.get_by_role("heading", name=CLOSED_TITLE)).to_be_visible()

    notice = page.get_by_role("status").filter(has_text="Your sign-in was kept")
    await expect(notice).to_have_text(
        "Your sign-in was kept for 30 minutes without use, so Axcess forgot it. "
        "Select “Open browser to sign in” to sign in again.",
        timeout=15_000,
    )
    assert await notice.evaluate("el => el === document.activeElement")
    await expect(
        page.get_by_role("textbox", name=re.compile(r"^Website address to scan"))
    ).to_have_value(SEED)
    await expect(page.get_by_role("button", name="Open browser to sign in")).to_be_visible()
    session = fake_sign_in.instances[0]
    assert session.closed and session.kept is None


async def test_an_expired_sign_in_refills_the_form_after_new_scan_was_reopened(
    fake_sign_in: type,
    monkeypatch: pytest.MonkeyPatch,
    seeded_db: tuple[Path, Path, int],
    new_page: Any,
    request: pytest.FixtureRequest,
) -> None:
    """The card was reached from the New scan link, so the form started empty."""
    from audit.web import local_sign_in

    monkeypatch.setattr(local_sign_in, "SIGN_IN_KEEP_SECONDS", 2)
    base, _ = request.getfixturevalue("live_server")
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _open_sign_in_through_the_api(page, base)
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()

    fake_sign_in.instances[0].close_window()

    await expect(page.get_by_role("status").filter(has_text="Your sign-in was kept")).to_be_visible(
        timeout=15_000
    )
    await expect(
        page.get_by_role("textbox", name=re.compile(r"^Website address to scan"))
    ).to_have_value(SEED)


async def test_reports_shows_nothing_for_a_waiting_sign_in(
    fake_sign_in: type, live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    before = await (await page.request.get(f"{base}/api/scans")).json()
    await _open_sign_in_through_the_api(page, base)

    await page.goto(f"{base}/app/scans", wait_until="networkidle")

    after = await (await page.request.get(f"{base}/api/scans")).json()
    assert after == before
    await expect(page.get_by_text(SITE)).to_have_count(0)
    await expect(page.get_by_text(re.compile(r"Scanning"))).to_have_count(0)


async def test_start_turns_the_sign_in_into_a_numbered_sign_in_scan(
    fake_sign_in: type,
    monkeypatch: pytest.MonkeyPatch,
    seeded_db: tuple[Path, Path, int],
    new_page: Any,
    request: pytest.FixtureRequest,
) -> None:
    import asyncio

    from audit.web import server

    async def _scan_that_keeps_preparing(*_args: object) -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(server, "_run_local_login_background", _scan_that_keeps_preparing)
    base, _ = request.getfixturevalue("live_server")
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _fill_and_submit_the_login_form(page, base)
    await expect(page.get_by_role("heading", name=OPEN_TITLE)).to_be_visible()

    await page.get_by_role("button", name=START).click()

    await expect(page).to_have_url(re.compile(r"mode=login&scan=\d+"))
    scan_id = int(re.search(r"scan=(\d+)", page.url).group(1))  # type: ignore[union-attr]
    await expect(page.get_by_text(f"Sign-in scan #{scan_id}", exact=True)).to_be_visible()
    title = "Preparing the signed-in session"
    await expect(page.get_by_role("heading", name=title)).to_be_visible()
    assert await _heading_has_focus(page, title)
    scans = await (await page.request.get(f"{base}/api/scans")).json()
    assert scan_id in {scan["id"] for scan in scans}
