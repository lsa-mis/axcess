"""A stand-in for Playwright, for the Google sign-in session's tests.

``GoogleBrowserSession`` opens a real Chromium on Google. These fakes record
what the session asks of the browser (launches, routes, page loads, clicks,
requests) and answer from tables the test fills in, so no test opens a
browser or contacts Google.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeAPIResponse:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes = b""
    disposed: bool = False

    async def body(self) -> bytes:
        return self.content

    async def dispose(self) -> None:
        self.disposed = True


class FakeRequest:
    """``context.request``: answers by address; records (method, url)."""

    def __init__(self, routes: dict[str, FakeAPIResponse], log: list[tuple[str, str]]) -> None:
        self.routes = routes
        self.log = log

    def _answer(self, url: str) -> FakeAPIResponse:
        found = self.routes.get(url)
        if found is None:
            return FakeAPIResponse(404)
        return FakeAPIResponse(found.status, dict(found.headers), found.content)

    async def get(self, url: str, **_: Any) -> FakeAPIResponse:
        self.log.append(("GET", url))
        return self._answer(url)

    async def head(self, url: str, **_: Any) -> FakeAPIResponse:
        self.log.append(("HEAD", url))
        answer = self._answer(url)
        return FakeAPIResponse(answer.status, answer.headers)


class FakeLocator:
    def __init__(self, page: FakePage, role: str, name: str) -> None:
        self.page = page
        self.role = role
        self.name = name

    async def click(self, **_: Any) -> None:
        self.page.actions.append(("click", self.role, self.name))
        if self.name == "Details":
            self.page.details_open = True

    async def wait_for(self, **_: Any) -> None:
        return None

    async def get_attribute(self, name: str) -> str | None:
        if name == "aria-disabled" and self.name == "Details" and self.page.details_disabled:
            return "true"
        return None


class FakeKeyboard:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    async def press(self, key: str) -> None:
        self.page.actions.append(("press", key))

    async def type(self, text: str, **_: Any) -> None:  # never called; recorded if it were
        self.page.actions.append(("type", text))


class FakeHandle:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def json_value(self) -> Any:
        return self.value


class FakePage:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.url = "about:blank"
        self.closed = False
        self.actions: list[tuple[str, ...]] = []
        self.details_open = False
        self.details_disabled = browser.details_disabled
        self.keyboard = FakeKeyboard(self)

    async def goto(self, url: str, **_: Any) -> None:
        self.browser.visits.append(url)
        if self.browser.fail_goto:
            raise RuntimeError("navigation failed")
        self.url = self.browser.redirects.get(url, url)

    async def evaluate(self, script: str, *_: Any) -> Any:
        if "navigator.userAgent" in script:
            return self.browser.user_agent
        if "getFullYear" in script:
            return list(self.browser.today)
        raise AssertionError(f"unexpected script: {script[:40]}")

    def get_by_role(
        self, role: str, *, name: str | re.Pattern[str], exact: bool = False
    ) -> FakeLocator:
        """Google's own accessible names (seen 2026-11-26): "File" for the
        menu, "Details b" for the item, its menu letter included. A name
        must match them as Playwright would: exactly, or by pattern."""
        real = {"File": "File", "Details": "Details b"}
        for short, accessible in real.items():
            matched = (
                name.search(accessible)
                if isinstance(name, re.Pattern)
                else (name == accessible if exact else name.lower() in accessible.lower())
            )
            if matched:
                return FakeLocator(self, role, short)
        raise AssertionError(f"no {role} named {name!r} on Google's page")

    async def wait_for_function(self, _script: str, **_: Any) -> FakeHandle:
        assert self.details_open, "the details are read only after Details is clicked"
        return FakeHandle(self.browser.details_text)

    def is_closed(self) -> bool:
        return self.closed

    async def close(self, **_: Any) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, browser: FakeBrowser, options: dict[str, Any]) -> None:
        self.browser = browser
        self.options = options
        self.pages: list[FakePage] = [FakePage(browser)]
        self.closed = False
        self.routes: list[tuple[str, Callable[..., Any]]] = []
        self._listeners: dict[str, list[Callable[[Any], None]]] = {}
        self.request = FakeRequest(browser.requests, browser.request_log)

    def on(self, event: str, callback: Callable[[Any], None]) -> None:
        self._listeners.setdefault(event, []).append(callback)

    async def new_page(self) -> FakePage:
        page = FakePage(self.browser)
        self.pages.append(page)
        return page

    async def route(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.routes.append((pattern, handler))

    async def close(self) -> None:
        if self.browser.fail_context_close:
            raise RuntimeError("close failed")
        self.close_now()

    def close_now(self) -> None:
        """The window closing, as a person closing it looks from outside."""
        if self.closed:
            return
        self.closed = True
        for callback in self._listeners.get("close", []):
            callback(self)


class FakeBrowser:
    """``playwright.chromium``, with every table a test can fill in."""

    def __init__(self) -> None:
        self.launches: list[tuple[str, dict[str, Any]]] = []
        self.contexts: list[FakeContext] = []
        self.visits: list[str] = []
        self.redirects: dict[str, str] = {}
        self.requests: dict[str, FakeAPIResponse] = {}
        self.request_log: list[tuple[str, str]] = []
        self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) Chrome/140.0.0.0 Safari/537.36"
        self.today = (2026, 11, 26)
        self.details_text: str | None = (
            "Document details\nCreated on Oct 17, 2024\nModified at Jul 29, 2025 by A Person"
        )
        self.details_disabled = False
        self.fail_goto = False
        self.fail_context_close = False
        self.fail_launch_after = -1

    async def launch_persistent_context(self, profile: str, **options: Any) -> FakeContext:
        if self.fail_launch_after == len(self.launches):
            self.launches.append((profile, options))
            raise RuntimeError("launch failed")
        self.launches.append((profile, options))
        context = FakeContext(self, options)
        self.contexts.append(context)
        return context


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeBrowser()
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True
