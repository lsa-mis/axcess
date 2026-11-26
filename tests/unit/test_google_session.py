"""The Google sign-in session's safeguards (linked_files/google_session.py).

Every test drives the session with the fake Playwright in ``_fake_google``:
no browser opens and nothing contacts Google.
"""

from __future__ import annotations

import datetime as dt
import os
import stat
from pathlib import Path
from typing import Any

import pytest
from support.fake_google import FakeAPIResponse, FakePlaywright

from audit.linked_files import google_session as gs
from audit.linked_files.google_session import (
    GoogleBrowserSession,
    GoogleDates,
    download_allowed,
    google_file_key,
    parse_details,
    route_allowed,
)

DOC_ID = "1AbCdEfGhIjKlMnOpQrStUv"
OTHER_ID = "9ZyXwVuTsRqPoNmLkJiHgFe"
DOC_PAGE = f"https://docs.google.com/document/d/{DOC_ID}/edit"
EXPORT = f"https://docs.google.com/document/d/{DOC_ID}/export?format=docx"
TODAY = dt.date(2026, 11, 26)


# -- safeguard 1: the route guard -----------------------------------------------


@pytest.mark.parametrize(
    ("url", "navigation", "allowed"),
    [
        # The registered file's page, in the forms pages link with.
        (DOC_PAGE, True, True),
        (f"https://docs.google.com/document/u/0/d/{DOC_ID}/edit", True, True),
        (f"https://docs.google.com/a/example.edu/document/d/{DOC_ID}/view", True, True),
        # Another file, even on the same host.
        (f"https://docs.google.com/document/d/{OTHER_ID}/edit", True, False),
        (f"https://docs.google.com/spreadsheets/d/{OTHER_ID}/edit", True, False),
        # Gmail, a Drive folder list, Google's home page.
        ("https://mail.google.com/mail/u/0/", True, False),
        ("https://drive.google.com/drive/my-drive", True, False),
        ("https://www.google.com/", True, False),
        # Google's sign-in host: a session refresh, the sign-out.
        ("https://accounts.google.com/Logout", True, True),
        # Not https.
        (f"http://docs.google.com/document/d/{DOC_ID}/edit", True, False),
        # The editor's own parts.
        ("https://www.gstatic.com/_/docs/script.js", False, True),
        ("https://fonts.googleapis.com/css?family=Roboto", False, True),
        ("https://lh3.googleusercontent.com/a/photo", False, True),
        ("https://docs.google.com/document/d/x/bind", False, True),
        # Anything not Google's, and look-alikes.
        ("https://cdn.example.com/tracker.js", False, False),
        ("https://evilgoogle.com/x.js", False, False),
        ("https://google.com.evil.test/x.js", False, False),
        ("data:text/plain,hello", False, False),
    ],
)
def test_the_route_guard(url: str, navigation: bool, allowed: bool) -> None:
    assert route_allowed(url, navigation=navigation, allowed_ids={DOC_ID}) is allowed


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        (EXPORT, True),
        ("https://drive.usercontent.google.com/download?id=x", True),
        ("https://drive.google.com/uc?id=x", True),
        ("https://doc-0s-docstext.googleusercontent.com/export/abc", True),
        ("https://accounts.google.com/ServiceLogin", False),
        ("https://mail.google.com/", False),
        ("https://example.com/file.pdf", False),
        ("http://docs.google.com/document/d/x/export", False),
    ],
)
def test_downloads_use_googles_file_hosts_only(url: str, allowed: bool) -> None:
    assert download_allowed(url) is allowed


def test_a_published_copy_is_not_a_file_page() -> None:
    assert google_file_key("https://docs.google.com/document/d/e/2PACX-1vabc/pub") is None
    assert google_file_key(DOC_PAGE) == ("document", DOC_ID)


# -- File > Details: the text ----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Document details\nCreated on Oct 17, 2024\nModified at Jul 29, 2025 by A Person",
            GoogleDates("2024-10-17", "2025-07-29"),
        ),
        (
            "Presentation details Created on September 3, 2021 Modified on Sep 4, 2021 by me",
            GoogleDates("2021-09-03", "2021-09-04"),
        ),
        # Today's change: a time only.
        (
            "Document details\nCreated on Jan 2, 2020\nModified at 3:15 PM by A Person",
            GoogleDates("2020-01-02", "2026-11-26"),
        ),
        ("Document details\nCreated on Feb 30, 2020", GoogleDates(None, None)),
        ("Document details\nCreated on Jan 2, 1901", GoogleDates(None, None)),
        ("Document details\nCreated on Jan 2, 2099", GoogleDates(None, None)),
        ("something else entirely", GoogleDates(None, None)),
        ("", GoogleDates(None, None)),
    ],
)
def test_details_text(text: str, expected: GoogleDates) -> None:
    assert parse_details(text, TODAY) == expected


def test_the_name_after_by_is_never_kept() -> None:
    dates = parse_details("Created on Oct 17, 2024\nModified at Jul 29, 2025 by Jane Q Doe", TODAY)
    assert "Jane" not in repr(dates)


# -- safeguard 5: the profile folder ----------------------------------------------


def test_the_profile_is_private_and_has_its_own_prefix(tmp_path: Path) -> None:
    path = gs.create_profile_dir(str(tmp_path))
    try:
        assert Path(path).parent == tmp_path / "axcess-google-browser"
        assert Path(path).name.startswith("axcess-google-browser-")
        assert not Path(path).name.startswith("axcess-protected-browser-")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o700
    finally:
        gs.remove_profile_dir(path)
    assert not Path(path).exists()


def test_stale_profiles_are_swept_but_not_a_live_one_or_anything_else(tmp_path: Path) -> None:
    root = tmp_path / "axcess-google-browser"
    root.mkdir()
    stale = root / "axcess-google-browser-crashed"
    stale.mkdir()
    (stale / "Cookies").write_text("x")
    other = root / "keep-me"
    other.mkdir()
    protected = root / "axcess-protected-browser-1"
    protected.mkdir()
    live = gs.create_profile_dir(str(tmp_path))
    try:
        assert not stale.exists()
        assert other.exists() and protected.exists()
        # A second session's start keeps the first, still live.
        second = gs.create_profile_dir(str(tmp_path))
        assert Path(live).exists()
        gs.remove_profile_dir(second)
    finally:
        gs.remove_profile_dir(live)


# -- the session, start to close --------------------------------------------------


async def _session(tmp_path: Path, **kwargs: Any) -> tuple[GoogleBrowserSession, FakePlaywright]:
    playwright = FakePlaywright()

    async def start() -> Any:
        return playwright

    clock = {"now": 0.0}
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    session = GoogleBrowserSession(
        playwright_start=start,
        profile_base=str(tmp_path),
        clock=lambda: clock["now"],
        sleep=sleep,
        **kwargs,
    )
    session.sleeps = sleeps  # type: ignore[attr-defined]
    return session, playwright


async def test_start_opens_a_visible_english_window_on_googles_sign_in(tmp_path: Path) -> None:
    session, playwright = await _session(tmp_path)
    changes: list[bool] = []
    session.on_window_change(changes.append)
    await session.start()
    profile, options = playwright.chromium.launches[0]
    assert options["headless"] is False
    assert options["locale"] == "en-US"
    assert options["extra_http_headers"] == {"Accept-Language": "en-US"}
    assert options["accept_downloads"] is False
    assert playwright.chromium.visits == [gs.SIGN_IN_URL]
    assert session.window_open and changes == [True]
    # No route guard while the person signs in: it is their window.
    assert playwright.chromium.contexts[0].routes == []
    # Closing the window is seen.
    playwright.chromium.contexts[0].close_now()
    assert changes == [True, False]
    await session.close()
    assert not Path(profile).exists()


@pytest.mark.parametrize(
    ("answer", "signed_in"),
    [
        (FakeAPIResponse(200), True),
        (FakeAPIResponse(302, {"location": "https://myaccount.google.com/?pli=1"}), True),
        (FakeAPIResponse(302, {"location": "https://accounts.google.com/ServiceLogin"}), False),
        # Google's real answer for a signed-out browser (seen 2026-11-26).
        (FakeAPIResponse(302, {"location": "https://myaccount.google.com/intro"}), False),
        (FakeAPIResponse(302, {"location": "/intro/security"}), False),
        (FakeAPIResponse(500), False),
    ],
)
async def test_the_signed_in_check(
    tmp_path: Path, answer: FakeAPIResponse, signed_in: bool
) -> None:
    session, playwright = await _session(tmp_path)
    await session.start()
    playwright.chromium.requests[gs.SIGNED_IN_PROBE] = answer
    assert await session.is_signed_in() is signed_in
    await session.close()


async def test_enter_scan_mode_closes_the_window_and_reopens_the_same_profile_headless(
    tmp_path: Path,
) -> None:
    session, playwright = await _session(tmp_path)
    playwright.chromium.user_agent = "Mozilla/5.0 (X11) HeadlessChrome/140.0 Safari/537.36"
    await session.start()
    visible = playwright.chromium.contexts[0]
    await session.enter_scan_mode()
    assert visible.closed and not session.window_open
    (first_profile, _), (second_profile, options) = playwright.chromium.launches
    assert first_profile == second_profile
    assert options["headless"] is True
    assert options["channel"] == "chromium"
    assert options["user_agent"] == "Mozilla/5.0 (X11) Chrome/140.0 Safari/537.36"
    assert options["accept_downloads"] is False
    headless = playwright.chromium.contexts[1]
    # The guard is on the Google browser's own context, every request.
    assert [pattern for pattern, _ in headless.routes] == ["**/*"]
    assert visible.routes == []
    assert session.active
    await session.close()


async def _scanning(tmp_path: Path) -> tuple[GoogleBrowserSession, FakePlaywright]:
    session, playwright = await _session(tmp_path)
    await session.start()
    await session.enter_scan_mode()
    return session, playwright


# -- safeguard 3: the dates, read only --------------------------------------------


async def test_dates_are_read_from_file_details_and_nothing_else_is_done(tmp_path: Path) -> None:
    session, playwright = await _scanning(tmp_path)
    assert session.allow_file(DOC_PAGE)
    read = await session.read_dates(DOC_PAGE)
    assert read.outcome == "dates"
    assert read.dates == GoogleDates("2024-10-17", "2025-07-29")
    page = playwright.chromium.contexts[1].pages[-1]
    assert page.actions == [
        ("click", "menuitem", "File"),
        ("click", "menuitem", "Details"),
        ("press", "Escape"),
    ]
    assert page.closed
    await session.close()


async def test_an_unregistered_file_is_never_opened(tmp_path: Path) -> None:
    session, playwright = await _scanning(tmp_path)
    read = await session.read_dates(f"https://docs.google.com/document/d/{OTHER_ID}/edit")
    assert read.outcome == "refused"
    assert playwright.chromium.visits == [gs.SIGN_IN_URL]
    await session.close()


async def test_details_turned_off_reads_nothing(tmp_path: Path) -> None:
    session, playwright = await _scanning(tmp_path)
    playwright.chromium.details_disabled = True
    session.allow_file(DOC_PAGE)
    read = await session.read_dates(DOC_PAGE)
    assert read.outcome == "none"
    page = playwright.chromium.contexts[1].pages[-1]
    assert ("click", "menuitem", "Details") not in page.actions
    await session.close()


async def test_a_file_page_sent_to_sign_in_means_the_sign_in_is_lost(tmp_path: Path) -> None:
    session, playwright = await _scanning(tmp_path)
    playwright.chromium.redirects[gs.file_page_url("document", DOC_ID)] = (
        "https://accounts.google.com/ServiceLogin?continue=x"
    )
    session.allow_file(DOC_PAGE)
    assert (await session.read_dates(DOC_PAGE)).outcome == "lost"
    assert session.lost and not session.active
    # Nothing more goes through Google.
    assert (await session.fetch_export(EXPORT)).outcome == "broken_link"
    assert ("GET", EXPORT) not in playwright.chromium.request_log
    await session.close()


# -- downloads ---------------------------------------------------------------------


async def test_an_export_is_downloaded_with_every_hop_checked(tmp_path: Path) -> None:
    session, playwright = await _scanning(tmp_path)
    final = "https://doc-0s-docstext.googleusercontent.com/export/abc"
    playwright.chromium.requests[EXPORT] = FakeAPIResponse(307, {"location": final})
    playwright.chromium.requests[final] = FakeAPIResponse(
        200, {"content-type": "application/zip"}, b"PK\x03\x04docx"
    )
    got = await session.fetch_export(EXPORT)
    assert (got.outcome, got.body) == ("ok", b"PK\x03\x04docx")
    await session.close()


@pytest.mark.parametrize(
    ("location", "outcome", "status"),
    [
        ("https://accounts.google.com/ServiceLogin?x", "http_error", 401),
        ("https://evil.example.com/steal", "blocked", None),
    ],
)
async def test_a_redirect_off_googles_file_hosts(
    tmp_path: Path, location: str, outcome: str, status: int | None
) -> None:
    session, playwright = await _scanning(tmp_path)
    playwright.chromium.requests[EXPORT] = FakeAPIResponse(302, {"location": location})
    got = await session.fetch_export(EXPORT)
    assert (got.outcome, got.http_status) == (outcome, status)
    assert ("GET", location) not in playwright.chromium.request_log
    await session.close()


async def test_a_drive_file_over_the_limit_is_not_downloaded(tmp_path: Path) -> None:
    session, playwright = await _scanning(tmp_path)
    address = f"{gs.DOWNLOAD_URL}?id={DOC_ID}&export=download"
    playwright.chromium.requests[address] = FakeAPIResponse(
        200, {"content-length": str(gs.MAX_FILE_BYTES + 1)}
    )
    got = await session.fetch_drive(f"https://drive.google.com/file/d/{DOC_ID}/view")
    assert got.outcome == "too_large"
    assert ("GET", address) not in playwright.chromium.request_log
    await session.close()


async def test_the_virus_scan_page_is_passed_once(tmp_path: Path) -> None:
    session, playwright = await _scanning(tmp_path)
    address = f"{gs.DOWNLOAD_URL}?id={DOC_ID}&export=download"
    page = (
        b'<!DOCTYPE html><html><form id="download-form" '
        b'action="https://drive.usercontent.google.com/download">'
        b'<input type="hidden" name="id" value="X"><input type="hidden" name="confirm" value="t">'
        b"</form></html>"
    )
    anyway = "https://drive.usercontent.google.com/download?id=X&confirm=t"
    playwright.chromium.requests[address] = FakeAPIResponse(200, {}, page)
    playwright.chromium.requests[anyway] = FakeAPIResponse(200, {}, b"%PDF-1.7 file")
    got = await session.fetch_drive(f"https://drive.google.com/file/d/{DOC_ID}/view")
    assert (got.outcome, got.body) == ("ok", b"%PDF-1.7 file")
    await session.close()


async def test_one_google_request_a_second_at_most(tmp_path: Path) -> None:
    session, playwright = await _scanning(tmp_path)
    playwright.chromium.requests[EXPORT] = FakeAPIResponse(200, {}, b"PK")
    for _ in range(3):
        await session.fetch_export(EXPORT)
    sleeps = session.sleeps  # type: ignore[attr-defined]
    assert len(sleeps) == 2 and all(abs(s - gs.PACE_S) < 1e-9 for s in sleeps)
    await session.close()


# -- safeguard 4: sign out, then delete -------------------------------------------


async def test_close_signs_out_then_deletes(tmp_path: Path) -> None:
    session, playwright = await _scanning(tmp_path)
    profile = session.profile_dir
    assert profile is not None and Path(profile).exists()
    await session.close()
    assert playwright.chromium.visits[-1] == gs.LOGOUT_URL
    assert playwright.chromium.contexts[-1].closed
    assert playwright.stopped
    assert not Path(profile).exists()
    # Twice is once.
    await session.close()
    assert playwright.chromium.visits.count(gs.LOGOUT_URL) == 1


async def test_close_deletes_even_when_every_step_fails(tmp_path: Path) -> None:
    session, playwright = await _scanning(tmp_path)
    profile = session.profile_dir
    assert profile is not None
    playwright.chromium.fail_goto = True
    playwright.chromium.fail_context_close = True
    await session.close()  # never raises
    assert not Path(profile).exists()


async def test_close_after_the_person_closed_the_window_still_signs_out(tmp_path: Path) -> None:
    session, playwright = await _session(tmp_path)
    await session.start()
    profile = session.profile_dir
    playwright.chromium.contexts[0].close_now()
    await session.close()
    # The profile was opened once more, headless, only to sign out.
    assert playwright.chromium.launches[-1][0] == profile
    assert playwright.chromium.launches[-1][1]["headless"] is True
    assert playwright.chromium.visits[-1] == gs.LOGOUT_URL
    assert profile is not None and not Path(profile).exists()


async def test_a_failed_start_deletes_the_profile(tmp_path: Path) -> None:
    session, playwright = await _session(tmp_path)
    playwright.chromium.fail_launch_after = 0
    with pytest.raises(gs.GoogleSessionError):
        await session.start()
    root = tmp_path / "axcess-google-browser"
    assert [p for p in root.iterdir() if p.name.startswith("axcess-google-browser-")] == []
