"""Download a file kept in Google Drive, and a Google Doc or Slides deck.

Google Docs and Slides (``export_address``, since 2026-11-17): a Doc is
downloaded as the Word file (.docx) and a Slides deck as the PowerPoint file
(.pptx) that the editor's File > Download menu gives, from
``docs.google.com/document/d/ID/export?format=docx`` and
``docs.google.com/presentation/d/ID/export/pptx``. Google's robots.txt
allows ``/document`` and ``/presentation`` on that host, and the tracker
asks it about the export address as about any download. A Doc shared only
with signed-in accounts answers 401, reported as needing a sign-in, as a
private Drive file is. A Google file has no original file: what is checked
is Google's export of it, and the report says so.

Drive files (``drive.google.com/file/d/ID/...``):

Research and the real links it was tested on:
docs/internal/google-files-research.md. In short:

- Drive's own download button requests
  ``https://drive.usercontent.google.com/download?id=ID&export=download``.
  This asks for that address directly (``fetch_drive_file``). It is the
  button's own target, three times faster than opening the file in a
  browser, and it works in a Fast scan, which has no browser.
- If Google ever stops answering that address with the file, the browser
  fallback (``download_with_button``) opens the file's page in Chromium,
  presses the button whose accessible name starts with "Download" (found by
  role and name, never by Google's generated CSS classes) and keeps what it
  downloads.
- A file shared only with signed-in accounts redirects to Google's sign-in
  page (``accounts.google.com``). That is reported as HTTP 401, a sign-in
  needed, never as a broken link. A deleted file answers 404 or 410.
- A file too large for Google's virus scan gets a page saying "Google Drive
  can't scan this file for viruses", whose form (``#download-form``)
  downloads it anyway. That form is submitted once.

Google's robots.txt for ``drive.usercontent.google.com`` says ``Disallow: /``
to every crawler, and every way of downloading a Drive file, the button
included, comes from that host. So the tracker asks robots.txt about that
address: a scan that follows robots.txt lists Drive files as not checked,
and one set to ignore robots.txt downloads them (the developer's decision,
2026-11-16). Every request goes through the crawl's rate limit.

Never raises for a network fault; says what happened, as ``fetch_file``.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import httpx

from audit.linked_files.fetch import FETCH_TIMEOUT_S, MAX_FILE_BYTES, FetchedFile
from audit.logging import get_logger

log = get_logger(__name__)

DOWNLOAD_URL = "https://drive.usercontent.google.com/download"
_SIGN_IN_HOSTS = frozenset({"accounts.google.com"})
_FILE_ID = re.compile(r"^[A-Za-z0-9_-]{10,}$")

#: The browser fallback: given a Drive file's view address, press its
#: download button and say what came back. None leaves the fallback out
#: (a test, or a scan that cannot open a browser).
ButtonDownload = Callable[[str], Awaitable[FetchedFile]]


def drive_file_id(url: str) -> str | None:
    """The file ID in a Drive file address, or None.

    ``/file/d/ID/view`` (with or without ``/view``), ``/open?id=ID`` and
    ``/uc?id=ID`` are the forms pages link with.
    """
    parts = urlsplit(url)
    if (parts.hostname or "").lower() != "drive.google.com":
        return None
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) >= 3 and segments[0] == "file" and segments[1] == "d":
        candidate = segments[2]
    else:
        candidate = (parse_qs(parts.query).get("id") or [""])[0]
    return candidate if _FILE_ID.match(candidate) else None


_EXPORT_PATH = re.compile(r"/(document|presentation)/(?:u/\d+/)?d/([A-Za-z0-9_-]{10,})(?:/|$)")


def export_address(url: str) -> str | None:
    """Where Google exports the Doc or Slides deck ``url`` names, or None.

    A Doc as Word (.docx), a deck as PowerPoint (.pptx). The ID is read from
    the editor's address in any of the forms pages link with
    (``/document/d/ID/edit``, ``/a/example.edu/document/d/ID``,
    ``/document/u/0/d/ID``). None for any other address, including a copy
    published to the web (``/document/d/e/…/pub``), which has no export.
    """
    parts = urlsplit(url)
    if (parts.hostname or "").lower() != "docs.google.com":
        return None
    match = _EXPORT_PATH.search(parts.path)
    if match is None:
        return None
    kind, file_id = match.groups()
    if kind == "document":
        return f"https://docs.google.com/document/d/{file_id}/export?format=docx"
    return f"https://docs.google.com/presentation/d/{file_id}/export/pptx"


async def fetch_export(
    client: httpx.AsyncClient,
    address: str,
    *,
    max_bytes: int = MAX_FILE_BYTES,
    timeout_s: float = FETCH_TIMEOUT_S,
) -> FetchedFile:
    """Download a Google export (``export_address``); a sign-in page reads as 401."""
    try:
        async with asyncio.timeout(timeout_s):
            fetched, _final = await _get(client, address, max_bytes=max_bytes)
    except TimeoutError:
        return FetchedFile("timed_out")
    except (httpx.HTTPError, ValueError):
        return FetchedFile("broken_link")
    return fetched


def view_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def _looks_like_html(body: bytes) -> bool:
    head = body[:512].lstrip().lower()
    return head.startswith((b"<!doctype html", b"<html"))


class _DownloadForm(HTMLParser):
    """The action and hidden fields of the virus-scan page's ``#download-form``."""

    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self._inside = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "form" and values.get("id") == "download-form":
            self.action = values.get("action") or None
            self._inside = True
        elif self._inside and tag == "input" and values.get("type") == "hidden":
            name = values.get("name")
            if name:
                self.fields[name] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._inside = False


def virus_scan_form_url(body: bytes, base: str) -> str | None:
    """Where "Download anyway" on Google's virus-scan page leads, or None."""
    if b"download-form" not in body:
        return None
    parser = _DownloadForm()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
    except Exception:  # an HTML parser can choke on unusual pages
        return None
    if not parser.action:
        return None
    action = urljoin(base, parser.action)
    return f"{action}{'&' if '?' in action else '?'}{urlencode(parser.fields)}"


async def _get(client: httpx.AsyncClient, url: str, *, max_bytes: int) -> tuple[FetchedFile, str]:
    """One streamed GET, size-capped: what came back, and the final address."""
    async with client.stream("GET", url, follow_redirects=True) as response:
        final = str(response.url)
        status = response.status_code
        content_type = response.headers.get("content-type")
        if (response.url.host or "").lower() in _SIGN_IN_HOSTS:
            # Google's sign-in page: only signed-in people with access may
            # open the file. HTTP 401's meaning, whatever status it sent.
            return FetchedFile("http_error", 401, content_type), final
        if status >= 400:
            return FetchedFile("http_error", status, content_type), final
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            return FetchedFile("too_large", status, content_type), final
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > max_bytes:
                return FetchedFile("too_large", status, content_type), final
            chunks.append(chunk)
        return FetchedFile("ok", status, content_type, b"".join(chunks)), final


async def fetch_drive_file(
    client: httpx.AsyncClient,
    url: str,
    *,
    button: ButtonDownload | None = None,
    max_bytes: int = MAX_FILE_BYTES,
    timeout_s: float = FETCH_TIMEOUT_S,
) -> FetchedFile:
    """Download the Drive file ``url`` names (see the module docstring)."""
    file_id = drive_file_id(url)
    if file_id is None:
        return FetchedFile("broken_link")
    address = f"{DOWNLOAD_URL}?{urlencode({'id': file_id, 'export': 'download'})}"
    try:
        async with asyncio.timeout(timeout_s):
            fetched, final = await _get(client, address, max_bytes=max_bytes)
            if fetched.outcome == "ok" and _looks_like_html(fetched.body):
                anyway = virus_scan_form_url(fetched.body, final)
                if anyway is not None:
                    fetched, final = await _get(client, anyway, max_bytes=max_bytes)
    except TimeoutError:
        return FetchedFile("timed_out")
    except (httpx.HTTPError, ValueError):
        return FetchedFile("broken_link")
    if fetched.outcome != "ok" or not _looks_like_html(fetched.body):
        return fetched
    # A page where the file should be: Google changed how its download
    # address answers. The button still downloads what a person would get.
    log.info("linked_files.drive_address_gave_a_page", has_button_fallback=button is not None)
    if button is None:
        return FetchedFile("broken_link", fetched.http_status, fetched.content_type)
    return await button(view_url(file_id))


async def download_with_button(
    url: str,
    *,
    user_agent: str,
    max_bytes: int = MAX_FILE_BYTES,
    timeout_s: float = FETCH_TIMEOUT_S,
) -> FetchedFile:
    """Open a Drive file's page in Chromium and press its "Download" button.

    The fallback for ``fetch_drive_file``: rare, so it starts its own
    browser rather than holding one open for the whole scan. The button is
    found by its role and accessible name (English, as Axcess's browser
    is), so a redesign that keeps the button keeps this working; if the
    page has no such button (a sign-in page, downloads turned off), nothing
    is downloaded.
    """
    from playwright.async_api import async_playwright

    try:
        async with asyncio.timeout(timeout_s), async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                context = await browser.new_context(
                    accept_downloads=True, locale="en-US", user_agent=user_agent
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                if (urlsplit(page.url).hostname or "").lower() in _SIGN_IN_HOSTS:
                    return FetchedFile("http_error", 401)
                download_button = page.get_by_role("button", name=re.compile(r"^Download\b", re.I))
                try:
                    await download_button.first.wait_for(state="visible", timeout=15_000)
                except Exception:
                    return FetchedFile("broken_link")
                async with page.expect_download() as info:
                    await download_button.first.click()
                download = await info.value
                path = await download.path()
                data = path.read_bytes()
                if len(data) > max_bytes:
                    return FetchedFile("too_large", 200)
                return FetchedFile("ok", 200, None, data)
            finally:
                await browser.close()
    except TimeoutError:
        return FetchedFile("timed_out")
    except Exception as exc:  # Playwright raises its own errors
        log.info("linked_files.drive_button_failed", error_type=type(exc).__name__)
        return FetchedFile("broken_link")
