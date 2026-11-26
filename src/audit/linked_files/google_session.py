"""Sign in to Google for the Google files a scan's pages link to (2026-11-26).

The developer's request: an opt-in New scan setting, "Sign in to Google for
Google files", off by default, first in public scans and then in sign-in
scans too. With it on, Axcess opens a visible Chromium window on Google's
sign-in page before the scan; the person signs in there, comes back, and
starts the scan. In a sign-in scan this window opens after the site
sign-in, as a second, separate browser: its own Playwright, its own
profile, never a tab of the site's browser, and never given the site's
context or pages (the developer's rule: "one flow, two separate browsers,
one after another"). During the scan's document check:

- Google Docs and Slides are downloaded as Google's export (.docx, .pptx;
  ``google.export_address``) through the signed-in browser, so files shared
  only with signed-in accounts can be checked.
- Google Drive files are downloaded through it too, but only when robots.txt
  allows it, as today (the tracker asks robots.txt about Drive's download
  address; Google's says ``Disallow: /`` there).
- Each Google Doc, Sheet and Slides file with no date yet has its page
  opened, File > Details read, and only the created and modified days kept.

Research, and why no other way works (no key, no OAuth):
docs/internal/document-check.md, "Google files: dates and sign-in".

The safeguards, all required (the developer chose "build 1-5"):

1. Allow-list. In the scan, a route guard on the browser context lets a
   page or frame load only the Google file pages this scan registered
   (``allow_file``) and ``accounts.google.com``; any other request only to
   the Google hosts the editor needs (``_SUBRESOURCE_SUFFIXES``). A
   download (``context.request``, which the route guard does not see)
   checks every address and every redirect itself (``download_allowed``).
2. Nobody uses the window after sign-in. ``enter_scan_mode`` closes the
   visible window and opens the same profile headless, with the visible
   browser's own user agent ("HeadlessChrome" put back to "Chrome"), so
   Google sees one browser. A file page that sends the browser to Google's
   sign-in page means the sign-in was lost: Google is not used again in that
   scan (``lost``), and one warning is logged.
3. Read-only. The only actions are opening a registered file page, clicking
   the "File" menu, clicking "Details" and pressing Escape. Nothing is typed.
   Downloads go through ``context.request``; the browser accepts none.
4. Sign out, then delete. ``close`` opens Google's sign-out page, closes the
   browser and removes the profile. It never raises.
5. Never kept. The profile is a mode-0700 folder of its own
   (``axcess-google-browser/axcess-google-browser-*``) and stale ones are
   swept when a session starts. Nothing here reads, logs or stores a cookie
   or token, a file's address or a person's name: logs carry counts only.

Pacing: one Google page or download at a time, at most one a second
(docs.google.com's robots.txt asks for ``Crawl-delay: 1``).

Nothing here was tried against Google by the code's author: Google's real
screens, its sign-in check and how a session survives the move to a headless
browser are assumptions the developer tests by hand.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import datetime as dt
import os
import re
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlencode, urljoin, urlsplit

from audit.linked_files.fetch import FETCH_TIMEOUT_S, MAX_FILE_BYTES, FetchedFile
from audit.linked_files.google import DOWNLOAD_URL, drive_file_id, virus_scan_form_url
from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page, Playwright, Route

log = get_logger(__name__)

#: Where the person signs in. ``continue`` lands them on their account page
#: once signed in, a page of Google's own.
SIGN_IN_URL = (
    "https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fmyaccount.google.com%2F"
)
#: Asked, without following redirects, whether the browser is signed in.
#: Signed out, Google answers 302 to ``myaccount.google.com/intro`` (seen
#: 2026-11-26), or may send it to ``accounts.google.com``: both mean signed
#: out (``_SIGNED_OUT_PATHS``). Signed in is assumed to answer 200 or a
#: redirect elsewhere on the account page (to be confirmed in a real test).
SIGNED_IN_PROBE = "https://myaccount.google.com/"
_SIGNED_OUT_PATHS = ("/intro",)
LOGOUT_URL = "https://accounts.google.com/Logout"
SIGN_IN_HOSTS = frozenset({"accounts.google.com"})

#: The profile folder: its own root and prefix. Never the protected
#: browser's (``axcess-protected-browser-*``): that session deletes every
#: sibling with its prefix when it starts.
PROFILE_ROOT_NAME = "axcess-google-browser"
PROFILE_PREFIX = "axcess-google-browser-"

#: Google pages or downloads per second, at most, one at a time.
PACE_S = 1.0
#: Google files whose dates one scan reads, at most.
MAX_DATE_FILES = 500
#: Longest one date read may take, page load to Escape.
READ_TIMEOUT_S = 75.0
#: The pause after the editor loads, and between tries of the File menu.
EDITOR_SETTLE_S = 2.0
#: Times the File menu is opened, at most, waiting for Details.
MENU_TRIES = 3
#: Longest ``close`` waits for Google's sign-out page.
SIGN_OUT_TIMEOUT_S = 8.0
#: Longest the whole of ``close`` may take, sign-out and browser included,
#: before the profile is deleted anyway: inside the app's 15 s allowance for
#: stopping a scan when it quits (``server.CRAWL_STOP_TIMEOUT_S``).
CLOSE_TIMEOUT_S = 10.0

#: Hosts a download may use, every redirect included.
_DOWNLOAD_HOSTS = frozenset({"docs.google.com", "drive.google.com", "drive.usercontent.google.com"})
_DOWNLOAD_SUFFIX = ".googleusercontent.com"
#: Hosts the editor loads its own parts from (scripts, styles, fonts, data).
_SUBRESOURCE_SUFFIXES = (
    "google.com",
    "gstatic.com",
    "googleusercontent.com",
    "googleapis.com",
    "ggpht.com",
)
_REDIRECTS = frozenset({301, 302, 303, 307, 308})

# A Doc, Sheet or Slides file page, in each form pages link with:
# ``/document/d/ID/edit``, ``/a/example.edu/document/d/ID``,
# ``/spreadsheets/u/0/d/ID``. A copy published to the web
# (``/document/d/e/…/pub``) has no File menu and is not matched: "e" is not
# a file ID.
_FILE_PAGE = re.compile(
    r"^/(?:a/[^/]+/)?(document|spreadsheets|presentation)/(?:u/\d+/)?d/([A-Za-z0-9_-]{10,})(?:/|$)"
)

FileKind = Literal["document", "spreadsheets", "presentation"]


def google_file_key(url: str) -> tuple[FileKind, str] | None:
    """``(kind, file ID)`` of a Google Doc, Sheet or Slides page address, or None."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or (parts.hostname or "").lower() != "docs.google.com":
        return None
    match = _FILE_PAGE.match(parts.path)
    if match is None:
        return None
    kind, file_id = match.groups()
    return kind, file_id  # type: ignore[return-value]


def file_page_url(kind: str, file_id: str) -> str:
    """The editor page Axcess opens to read a file's dates."""
    return f"https://docs.google.com/{kind}/d/{file_id}/edit"


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _is_https(url: str) -> bool:
    try:
        return urlsplit(url).scheme == "https"
    except ValueError:
        return False


def route_allowed(
    url: str,
    *,
    navigation: bool,
    allowed_ids: frozenset[str] | set[str],
    main_frame: bool = True,
) -> bool:
    """Safeguard 1: may the scan's Google browser load ``url``?

    The page itself (a main-frame ``navigation``) may go only to a
    registered file page or to Google's sign-in host (a session refresh, the
    sign-out). What that page loads inside itself, its frames included, may
    come only from Google's own hosts, or be built in memory (``blob:``,
    ``data:``). The editor needs both: seen 2026-11-26 on scan 84, where
    blocking its frames on docs.google.com, clients6.google.com and
    contacts.google.com, and its ``blob:`` parts, left File > Details
    unreadable on every file.
    """
    scheme = urlsplit(url).scheme if url else ""
    if scheme in ("blob", "data"):
        return not (navigation and main_frame)
    if not _is_https(url):
        return False
    host = _host(url)
    if navigation and main_frame:
        if host in SIGN_IN_HOSTS:
            return True
        key = google_file_key(url)
        return key is not None and key[1] in allowed_ids
    return any(host == suffix or host.endswith("." + suffix) for suffix in _SUBRESOURCE_SUFFIXES)


def download_allowed(url: str) -> bool:
    """Safeguard 1: may a download use ``url`` (each redirect is asked too)?"""
    if not _is_https(url):
        return False
    host = _host(url)
    return host in _DOWNLOAD_HOSTS or host.endswith(_DOWNLOAD_SUFFIX)


# -- File > Details ----------------------------------------------------------

_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for name in names
}
_DAY = r"(?P<month>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})"
_TIME = r"(?P<time>\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)?)"
# Docs write "Created on Oct 17, 2024"; Slides and Sheets put "Created" and
# "Sep 30, 2019" in two cells of a small table (seen 2026-11-26), so "on" or
# "at" is optional.
_CREATED = re.compile(rf"Created(?:\s+(?:on|at))?\s+(?:{_DAY}|{_TIME})")
_MODIFIED = re.compile(rf"Modified(?:\s+(?:on|at))?\s+(?:{_DAY}|{_TIME})")
_EARLIEST_YEAR = 1980


@dataclass(frozen=True)
class GoogleDates:
    """Two days, ``YYYY-MM-DD``, or None when Google's screen did not say."""

    created: str | None = None
    modified: str | None = None

    @property
    def found(self) -> bool:
        return self.created is not None or self.modified is not None


def _day(match: re.Match[str] | None, today: dt.date) -> str | None:
    if match is None:
        return None
    if match.group("time"):
        # A time alone ("Modified at 3:15 PM") is today, in the browser's
        # own calendar, as Google writes it.
        return today.isoformat()
    month = _MONTHS.get(match.group("month").lower())
    if month is None:
        return None
    try:
        day = dt.date(int(match.group("year")), month, int(match.group("day")))
    except ValueError:
        return None
    if day.year < _EARLIEST_YEAR or day > today + dt.timedelta(days=1):
        return None
    return day.isoformat()


def parse_details(text: str, today: dt.date) -> GoogleDates:
    """The created and modified days in Google's details popup text.

    ``Created on Oct 17, 2024`` and ``Modified at Jul 29, 2025 by <name>``:
    the days only. The name after "by" is never read into anything.
    """
    return GoogleDates(
        created=_day(_CREATED.search(text), today),
        modified=_day(_MODIFIED.search(text), today),
    )


# Finds the popup: the element around a text "Document details" (or
# "Spreadsheet", "Presentation") whose text says "Created on". Walks text
# nodes, not every element, so a large editor page is not laid out
# thousands of times. Returns at most 2,000 characters.
_DETAILS_TEXT_JS = r"""
() => {
  const heading = /^(Document|Spreadsheet|Presentation|File) details$/;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!heading.test((node.textContent || "").trim())) continue;
    for (let el = node.parentElement; el && el !== document.body; el = el.parentElement) {
      const text = el.innerText || "";
      if (/Created\s/.test(text)) return text.slice(0, 2000);
    }
  }
  return null;
}
"""
#: The File menu's Details item: "Details b" to programs, the letter being
#: its keyboard shortcut in the menu.
_DETAILS_ITEM = re.compile(r"^Details\b")
_TODAY_JS = (
    "() => { const d = new Date(); return [d.getFullYear(), d.getMonth() + 1, d.getDate()]; }"
)


@dataclass(frozen=True)
class DatesRead:
    """What opening one file page gave.

    ``dates``: Google's screen was read (``dates.found`` says whether it
    held a date). ``none``: no Details to read (not allowed, the page did
    not load, Details turned off). ``lost``: the page went to Google's
    sign-in, so the sign-in is gone. ``refused``: not a registered file.
    """

    outcome: Literal["dates", "none", "lost", "refused"]
    dates: GoogleDates = GoogleDates()


# -- the profile folder --------------------------------------------------------

#: Profile folders of sessions alive in this process: the stale sweep keeps
#: them (a sign-in can wait while a scan with another session runs).
_live_profiles: set[str] = set()


def profile_root(base: str | None = None) -> str:
    return os.path.join(base or tempfile.gettempdir(), PROFILE_ROOT_NAME)


def sweep_stale_profiles(root: str) -> int:
    """Remove profile folders a crash left behind. Returns how many.

    Only folders with this session's own prefix, never a symlink, never one
    a live session in this process uses.
    """
    removed = 0
    with contextlib.suppress(OSError):
        for entry in os.scandir(root):
            if (
                entry.name.startswith(PROFILE_PREFIX)
                and entry.is_dir(follow_symlinks=False)
                and entry.path not in _live_profiles
            ):
                with contextlib.suppress(OSError):
                    shutil.rmtree(entry.path)
                    removed += 1
    return removed


def create_profile_dir(base: str | None = None) -> str:
    """Safeguard 5: a new mode-0700 profile folder, after sweeping stale ones."""
    root = profile_root(base)
    os.makedirs(root, mode=0o700, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(root, 0o700)
    sweep_stale_profiles(root)
    path = tempfile.mkdtemp(prefix=PROFILE_PREFIX, dir=root)
    os.chmod(path, 0o700)
    _live_profiles.add(path)
    return path


def remove_profile_dir(path: str) -> None:
    _live_profiles.discard(path)
    with contextlib.suppress(Exception):
        shutil.rmtree(path)


class GoogleSessionError(RuntimeError):
    """The Google browser could not do what was asked (message has no address)."""


async def _start_playwright() -> Playwright:
    from playwright.async_api import async_playwright

    return await async_playwright().start()


class GoogleBrowserSession:
    """One Google sign-in: a visible window, then a headless scan browser.

    Lifecycle: ``start`` (visible window on Google's sign-in page),
    ``is_signed_in``, ``enter_scan_mode`` (window closed, same profile
    headless, route guard on), then ``fetch_export``, ``fetch_drive`` and
    ``read_dates`` during the scan, and ``close`` at the end, always.
    """

    site = "accounts.google.com"

    def __init__(
        self,
        *,
        playwright_start: Callable[[], Awaitable[Playwright]] | None = None,
        profile_base: str | None = None,
        pace_s: float = PACE_S,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        nav_timeout_ms: int = 30_000,
    ) -> None:
        self._playwright_start = playwright_start or _start_playwright
        self._profile_base = profile_base
        self._pace_s = pace_s
        #: Date reads that stopped, by the step they stopped at.
        self.read_failures: collections.Counter[str] = collections.Counter()
        self._step = ""
        self._clock = clock
        self._sleep = sleep
        self._nav_timeout_ms = nav_timeout_ms
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._profile_dir: str | None = None
        self._window_open = False
        self._listeners: list[Callable[[bool], None]] = []
        self._scanning = False
        self._closed = False
        #: Set once the sign-in turned out lost; Google is not used again.
        self.lost = False
        self._allowed_ids: set[str] = set()
        self._lock = asyncio.Lock()
        self._next_at = 0.0
        self._ignore_close = False

    # -- state ---------------------------------------------------------------

    @property
    def window_open(self) -> bool:
        return self._window_open

    @property
    def active(self) -> bool:
        """Whether the scan may use Google through this session now."""
        return self._scanning and not self.lost and not self._closed

    @property
    def profile_dir(self) -> str | None:
        return self._profile_dir

    def on_window_change(self, callback: Callable[[bool], None]) -> None:
        self._listeners.append(callback)

    def _set_window_open(self, value: bool) -> None:
        if self._window_open == value:
            return
        self._window_open = value
        for callback in list(self._listeners):
            with contextlib.suppress(Exception):
                callback(value)

    def _context_closed(self, context: BrowserContext) -> None:
        # The person closed the window (a persistent context's window ends
        # its browser). Not when Axcess closes it itself.
        if context is self._context and not self._ignore_close:
            self._context = None
            self._set_window_open(False)

    def _context_options(self) -> dict[str, Any]:
        # English, so the menu and popup words match (spec: force en-US).
        return {
            "locale": "en-US",
            "extra_http_headers": {"Accept-Language": "en-US"},
            "accept_downloads": False,
            "service_workers": "block",
        }

    # -- sign-in -------------------------------------------------------------

    async def start(self) -> None:
        """Open the visible window on Google's sign-in page."""
        if self._closed or self._playwright is not None:
            raise GoogleSessionError("The Google sign-in has already started.")
        try:
            self._playwright = await self._playwright_start()
            self._profile_dir = create_profile_dir(self._profile_base)
            context = await self._playwright.chromium.launch_persistent_context(
                self._profile_dir, headless=False, **self._context_options()
            )
            self._context = context
            context.on("close", lambda _ctx: self._context_closed(context))
            page = context.pages[0] if context.pages else await context.new_page()
            for extra in list(context.pages):
                if extra is not page:
                    with contextlib.suppress(Exception):
                        await extra.close()
            self._set_window_open(True)
            await page.goto(
                SIGN_IN_URL, wait_until="domcontentloaded", timeout=self._nav_timeout_ms
            )
        except Exception as exc:
            await self.close()
            raise GoogleSessionError("Could not open the Google sign-in window.") from exc

    async def is_signed_in(self) -> bool:
        """Whether Google treats this browser as signed in.

        One request to Google's account page, redirects not followed; a
        redirect to the sign-in host means signed out. The answer's body is
        never read.
        """
        context = self._context
        if context is None or self._closed:
            return False
        try:
            response = await context.request.get(
                SIGNED_IN_PROBE,
                max_redirects=0,
                fail_on_status_code=False,
                timeout=self._nav_timeout_ms,
            )
        except Exception:
            return False
        status = response.status
        location = response.headers.get("location", "")
        with contextlib.suppress(Exception):
            await response.dispose()
        if status in _REDIRECTS:
            target = urljoin(SIGNED_IN_PROBE, location)
            if _host(target) in SIGN_IN_HOSTS:
                return False
            path = urlsplit(target).path or "/"
            return not any(path.startswith(prefix) for prefix in _SIGNED_OUT_PATHS)
        return status < 300

    async def enter_scan_mode(self) -> None:
        """Safeguard 2: close the visible window, reopen the profile headless."""
        context = self._context
        playwright = self._playwright
        if context is None or playwright is None or self._profile_dir is None or self._closed:
            raise GoogleSessionError("The Google window is not open.")
        pages = [page for page in context.pages if not page.is_closed()]
        if not pages:
            raise GoogleSessionError("The Google window is not open.")
        user_agent = str(await pages[0].evaluate("() => navigator.userAgent"))
        user_agent = user_agent.replace("HeadlessChrome", "Chrome")
        self._ignore_close = True
        try:
            with contextlib.suppress(Exception):
                await context.close()
            self._context = None
            self._set_window_open(False)
            headless = await playwright.chromium.launch_persistent_context(
                self._profile_dir,
                headless=True,
                # The full Chromium in its new headless mode, so the browser
                # Google sees is the one the person signed in with.
                channel="chromium",
                user_agent=user_agent,
                **self._context_options(),
            )
            await headless.route("**/*", self._guard)
            for extra in list(headless.pages):
                with contextlib.suppress(Exception):
                    await extra.close(run_before_unload=False)
            self._context = headless
        finally:
            self._ignore_close = False
        self._scanning = True

    # -- safeguard 1: the route guard -----------------------------------------

    def allow_file(self, url: str) -> bool:
        """Register a file page this scan found, so the guard lets it load."""
        key = google_file_key(url)
        if key is None:
            return False
        self._allowed_ids.add(key[1])
        return True

    async def _guard(self, route: Route) -> None:
        request = route.request
        try:
            navigation = request.is_navigation_request() or request.resource_type == "document"
            main_frame = True
            if navigation:
                with contextlib.suppress(Exception):
                    main_frame = request.frame.parent_frame is None
            allowed = route_allowed(
                request.url,
                navigation=navigation,
                allowed_ids=self._allowed_ids,
                main_frame=main_frame,
            )
        except Exception:
            allowed = False
        with contextlib.suppress(Exception):
            if allowed:
                await route.continue_()
            else:
                await route.abort("blockedbyclient")

    # -- pacing ----------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def _paced(self) -> Any:
        async with self._lock:
            wait = self._next_at - self._clock()
            if wait > 0:
                await self._sleep(wait)
            try:
                yield
            finally:
                self._next_at = self._clock() + self._pace_s

    # -- downloads -------------------------------------------------------------

    async def fetch_export(self, address: str) -> FetchedFile:
        """A Doc or Slides export through the signed-in session."""
        return await self._download(address, head_first=False, drive=False)

    async def fetch_drive(self, url: str) -> FetchedFile:
        """A Drive file through the signed-in session, as ``google.fetch_drive_file``."""
        file_id = drive_file_id(url)
        if file_id is None:
            return FetchedFile("broken_link")
        address = f"{DOWNLOAD_URL}?{urlencode({'id': file_id, 'export': 'download'})}"
        return await self._download(address, head_first=True, drive=True)

    async def _download(self, address: str, *, head_first: bool, drive: bool) -> FetchedFile:
        context = self._context
        if context is None or not self.active:
            return FetchedFile("broken_link")
        async with self._paced():
            try:
                async with asyncio.timeout(FETCH_TIMEOUT_S):
                    fetched, final = await self._get(context, address, head_first=head_first)
                    if drive and fetched.outcome == "ok" and _looks_like_html(fetched.body):
                        anyway = virus_scan_form_url(fetched.body, final)
                        if anyway is not None:
                            fetched, final = await self._get(context, anyway, head_first=True)
            except TimeoutError:
                return FetchedFile("timed_out")
            except Exception:  # Playwright raises its own errors for network faults
                return FetchedFile("broken_link")
        if drive and fetched.outcome == "ok" and _looks_like_html(fetched.body):
            # A page where the file should be (no access, or Google changed).
            return FetchedFile("broken_link", fetched.http_status, fetched.content_type)
        return fetched

    async def _get(
        self, context: BrowserContext, url: str, *, head_first: bool
    ) -> tuple[FetchedFile, str]:
        """One download, every hop checked; a sign-in page reads as HTTP 401.

        Signed in, Google's first download passes once through
        ``accounts.google.com`` to hand the sign-in to docs.google.com (seen
        2026-11-26: export → accounts.google.com/ServiceLogin →
        docs.google.com/accounts/SetOSID → export → the file). That hop is
        followed, as a redirect, and never sent a body. Only a sign-in host
        answering with a page of its own means the file needs a sign-in. Until
        2026-11-26 any sign-in hop read as 401, so the hand-over never
        happened and every Doc in scan 84 was "needs a sign-in".
        """
        current = url
        timeout_ms = FETCH_TIMEOUT_S * 1000
        for _ in range(12):
            if _host(current) in SIGN_IN_HOSTS:
                if not _is_https(current):
                    return FetchedFile("blocked"), current
                hand_over = await context.request.get(
                    current, max_redirects=0, fail_on_status_code=False, timeout=timeout_ms
                )
                where = hand_over.headers.get("location")
                handed = hand_over.status in _REDIRECTS and bool(where)
                with contextlib.suppress(Exception):
                    await hand_over.dispose()
                if not handed or where is None:
                    return FetchedFile("http_error", 401), current
                current = urljoin(current, where)
                continue
            if not download_allowed(current):
                return FetchedFile("blocked"), current
            if head_first:
                head = await context.request.head(
                    current, max_redirects=0, fail_on_status_code=False, timeout=timeout_ms
                )
                head_location = head.headers.get("location")
                head_status = head.status
                declared = head.headers.get("content-length", "")
                head_type = head.headers.get("content-type")
                with contextlib.suppress(Exception):
                    await head.dispose()
                if head_status in _REDIRECTS and head_location:
                    current = urljoin(current, head_location)
                    continue
                if head_status < 400 and declared.isdigit() and int(declared) > MAX_FILE_BYTES:
                    return FetchedFile("too_large", head_status, head_type), current
            response = await context.request.get(
                current, max_redirects=0, fail_on_status_code=False, timeout=timeout_ms
            )
            status = response.status
            content_type = response.headers.get("content-type")
            location = response.headers.get("location")
            if status in _REDIRECTS and location:
                with contextlib.suppress(Exception):
                    await response.dispose()
                current = urljoin(current, location)
                continue
            if status >= 400:
                with contextlib.suppress(Exception):
                    await response.dispose()
                return FetchedFile("http_error", status, content_type), current
            body = await response.body()
            with contextlib.suppress(Exception):
                await response.dispose()
            if len(body) > MAX_FILE_BYTES:
                return FetchedFile("too_large", status, content_type), current
            return FetchedFile("ok", status, content_type, body), current
        return FetchedFile("broken_link"), current

    # -- safeguard 3: the dates, read only --------------------------------------

    async def read_dates(self, url: str) -> DatesRead:
        """Open a registered file page and read File > Details. Read-only."""
        key = google_file_key(url)
        if key is None or key[1] not in self._allowed_ids:
            return DatesRead("refused")
        context = self._context
        if context is None or not self.active:
            return DatesRead("none")
        async with self._paced():
            page: Page | None = None
            self._step = "open the page"
            try:
                async with asyncio.timeout(READ_TIMEOUT_S):
                    page = await context.new_page()
                    await page.goto(
                        file_page_url(*key),
                        wait_until="domcontentloaded",
                        timeout=self._nav_timeout_ms,
                    )
                    if _host(page.url) in SIGN_IN_HOSTS:
                        self._mark_lost()
                        return DatesRead("lost")
                    return await self._read_details(page)
            except Exception:  # A timeout, or Playwright's own errors.
                # Which step stopped, counted for the scan log (step names
                # only, never an address): the scan-84 log could say only
                # that no file gave a date, not why.
                self.read_failures[self._step] += 1
                return DatesRead("none")
            finally:
                if page is not None:
                    with contextlib.suppress(Exception):
                        await page.close(run_before_unload=False)

    async def _read_details(self, page: Page) -> DatesRead:
        """File, then Details, then the box's text; nothing else is pressed.

        Paced like a person (seen 2026-11-26): pressing File as soon as the
        page's HTML arrived, before the editor had started, read the dates
        of 1 file in 5; the others stopped at "find Details", at "read the
        details box", or found Details greyed out while the file was still
        loading. So it waits for the page to load and settle, and opens the
        menu again (up to ``MENU_TRIES`` times) when Details is not there yet
        or still greyed out.
        """
        self._step = "wait for the editor"
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("load", timeout=20_000)
        await self._sleep(EDITOR_SETTLE_S)
        year, month, day = await page.evaluate(_TODAY_JS)
        today = dt.date(int(year), int(month), int(day))
        file_menu = page.get_by_role("menuitem", name="File", exact=True)
        # Google names the item with its menu letter, "Details b" (seen
        # 2026-11-26; an exact "Details" matched nothing, so scan 84 read no
        # dates), so the name is matched by its first word.
        details = page.get_by_role("menuitem", name=_DETAILS_ITEM)
        for attempt in range(1, MENU_TRIES + 1):
            self._step = "press File"
            await file_menu.click(timeout=15_000)
            self._step = "find Details"
            try:
                await details.wait_for(state="visible", timeout=8_000)
            except Exception:
                if attempt == MENU_TRIES:
                    raise
                await page.keyboard.press("Escape")
                await self._sleep(EDITOR_SETTLE_S)
                continue
            if (await details.get_attribute("aria-disabled")) != "true":
                break
            # Greyed out: still loading, or not allowed (signed out).
            await page.keyboard.press("Escape")
            if attempt == MENU_TRIES:
                self.read_failures["Details greyed out"] += 1
                return DatesRead("none")
            await self._sleep(EDITOR_SETTLE_S)
        self._step = "press Details"
        await details.click()
        self._step = "read the details box"
        handle = await page.wait_for_function(_DETAILS_TEXT_JS, timeout=15_000)
        text = await handle.json_value()
        await page.keyboard.press("Escape")
        if not isinstance(text, str):
            return DatesRead("dates")
        return DatesRead("dates", parse_details(text, today))

    def _mark_lost(self) -> None:
        if not self.lost:
            self.lost = True
            log.warning(
                "linked_files.google_sign_in_lost",
                message=(
                    "Google asked to sign in again, so the rest of this scan checks "
                    "Google files without the Google sign-in."
                ),
            )

    # -- safeguard 4: sign out, then delete ---------------------------------------

    async def close(self) -> None:
        """Sign out at Google, close the browser, delete the profile. Never raises."""
        if self._closed:
            return
        self._closed = True
        if self.read_failures:
            log.warning(
                "linked_files.google_dates_stopped",
                steps=dict(self.read_failures),
                message="Reading File, Details stopped at these steps (counts).",
            )
        self._scanning = False
        self._set_window_open(False)
        context = self._context
        playwright = self._playwright
        profile = self._profile_dir
        self._ignore_close = True
        try:
            async with asyncio.timeout(CLOSE_TIMEOUT_S):
                await self._close_browser(context, playwright, profile)
        except TimeoutError:
            log.warning("linked_files.google_close_slow", seconds=CLOSE_TIMEOUT_S)
        finally:
            # Always, even when a step above was cancelled or slow: the profile goes.
            self._context = None
            self._playwright = None
            self._profile_dir = None
            self._allowed_ids.clear()
            if profile is not None:
                remove_profile_dir(profile)

    async def _close_browser(
        self, context: BrowserContext | None, playwright: Playwright | None, profile: str | None
    ) -> None:
        if context is None and playwright is not None and profile is not None:
            # The window was closed by the person: open the profile once
            # more, headless, only to sign out.
            with contextlib.suppress(Exception):
                context = await asyncio.wait_for(
                    playwright.chromium.launch_persistent_context(
                        profile, headless=True, **self._context_options()
                    ),
                    timeout=SIGN_OUT_TIMEOUT_S,
                )
        if context is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._sign_out(context), timeout=SIGN_OUT_TIMEOUT_S)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(context.close(), timeout=SIGN_OUT_TIMEOUT_S)
        if playwright is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(playwright.stop(), timeout=SIGN_OUT_TIMEOUT_S)

    async def _sign_out(self, context: BrowserContext) -> None:
        page = await context.new_page()
        try:
            await page.goto(LOGOUT_URL, wait_until="load", timeout=SIGN_OUT_TIMEOUT_S * 1000)
        finally:
            with contextlib.suppress(Exception):
                await page.close(run_before_unload=False)


def _looks_like_html(body: bytes) -> bool:
    head = body[:512].lstrip().lower()
    return head.startswith((b"<!doctype html", b"<html"))
