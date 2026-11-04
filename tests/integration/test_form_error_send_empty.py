"""The form error check's opt-in "send empty forms", against a real server.

W3C's BAD "before" survey is checked only on its server: pressing Submit
posts the form, and the page that comes back marks the missing answers with
red labels and no words. Without sending, the check can only say "not
checked". With the scan's permission it may send a form whose every visible
field is empty, and judge the page the site sends back. Everything else is
still refused: a form with any value in it, a form that goes to another
site, and every request the reply page makes on its own except reads.
"""

from __future__ import annotations

import asyncio
import http.server
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, ClassVar

import pytest

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.forms import ErrorIdentificationProbe
from audit.analyzer.interaction import InteractionProbe

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

_STYLE = "<style>label.bad { color: #c00000; } label { display: block; }</style>"


def _form(bad: bool, *, value: str = "", action: str = "/survey", radios: bool = False) -> str:
    cls = ' class="bad"' if bad else ""
    # As on the BAD survey: answer buttons with no label of their own.
    answers = (
        "".join(f'<input type="radio" name="res" value="{n}">{n}' for n in (1, 2, 3))
        if radios
        else ""
    )
    return f"""<form action="{action}" method="post"><h2>Survey</h2>{answers}
  <label for="name"{cls}>Name</label><input id="name" name="name" value="{value}">
  <label for="email"{cls}>Email</label><input id="email" name="email">
  <input type="hidden" name="token" value="abc">
  <input type="submit" value="submit"></form>"""


def _page(body: str, script: str = "") -> bytes:
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Survey</title>'
        f"{_STYLE}</head><body><main>{body}</main>{script}</body></html>"
    ).encode()


class _Site(http.server.BaseHTTPRequestHandler):
    posts: ClassVar[list[str]] = []
    other_posts: ClassVar[list[str]] = []

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        pages = {
            "/": _form(False),
            "/filled": _form(False, value="Ada"),
            "/elsewhere": _form(False, action="http://other.invalid/survey"),
            "/radios": _form(False, action="/survey-radios", radios=True),
        }
        self._send(_page(pages.get(self.path, "")))

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode()
        if self.path in {"/survey", "/survey-radios"}:
            type(self).posts.append(body)
            # As the BAD survey does: the form again, labels red, no words.
            # Its own script tries to post somewhere; that must be refused.
            beacon = "<script>fetch('/beacon', {method: 'POST', body: 'x'});</script>"
            radios = self.path == "/survey-radios"
            reply = _form(True, action=self.path, radios=radios)
            self._send(_page(reply, beacon))
        else:
            type(self).other_posts.append(self.path)
            self._send(b"")


@contextmanager
def _serve() -> Iterator[str]:
    _Site.posts, _Site.other_posts = [], []
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Site) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}"
        finally:
            httpd.shutdown()


async def _check(browser: Any, url: str, *, send: bool) -> list[Any]:
    context = await browser.new_context(service_workers="block")
    page = await context.new_page()
    try:
        await page.goto(url)
        return await ErrorIdentificationProbe(send_empty=send).run(page)
    finally:
        await context.close()


async def test_a_form_checked_on_the_server_is_judged_when_sending_is_allowed(browser) -> None:  # type: ignore[no-untyped-def]
    with _serve() as base:
        results = await _check(browser, f"{base}/", send=True)
        await asyncio.sleep(0.3)
        posts, others = list(_Site.posts), list(_Site.other_posts)
    assert [r.outcome for r in results] == ["fail"], results
    assert results[0].sent is True
    assert len(posts) == 1 and "name=&email=" in posts[0] and "token=abc" in posts[0]
    # The reply page's own POST never reached the server.
    assert others == []


async def test_without_permission_nothing_is_sent(browser) -> None:  # type: ignore[no-untyped-def]
    with _serve() as base:
        results = await _check(browser, f"{base}/", send=False)
        posts = list(_Site.posts)
    assert [r.outcome for r in results] == ["not_checked"]
    assert results[0].sent is False and posts == []


@pytest.mark.parametrize("path", ["/filled", "/elsewhere"])
async def test_a_form_with_a_value_or_another_site_is_never_sent(browser, path: str) -> None:  # type: ignore[no-untyped-def]
    with _serve() as base:
        results = await _check(browser, f"{base}{path}", send=True)
        posts = list(_Site.posts)
    assert posts == [], posts
    assert all(not r.sent for r in results)


async def test_buttons_ticked_by_click_through_are_cleared_before_sending(browser) -> None:  # type: ignore[no-untyped-def]
    """Report #39, on W3C's BAD survey: Click-Through runs first on the same
    page and ticks every radio button it finds, without leaving the page, so
    nothing put the page back. The form check then found a form with answers
    in it, rightly refused to send it, and could not judge it. It must start
    from the page as it loaded."""
    with _serve() as base:
        context = await browser.new_context(service_workers="block")
        page = await context.new_page()
        try:
            await page.goto(f"{base}/radios")
            await InteractionProbe(axe=AxeAnalyzer.from_bundled()).run(page)
            assert await page.evaluate(
                "() => [...document.querySelectorAll('input[type=radio]')].some(r => r.checked)"
            ), "Click-Through no longer ticks the buttons; this test proves nothing"
            results = await ErrorIdentificationProbe(send_empty=True).run(page)
        finally:
            await context.close()
        posts = list(_Site.posts)
    assert [r.outcome for r in results] == ["fail"], results
    assert len(posts) == 1 and "res=" not in posts[0], posts
