"""What the form error check lets out of the page while it presses submit.

The safety review (docs/internal/form-error-check.md): the network guard
let same-origin GET requests through, and could not see sockets at all. A
form's submit handler here tries every way out it can: a same-origin GET, a
beacon, a message on a WebSocket opened before the press, and a new
WebSocket. None may reach the server, and a form that tried to send is "not
checked", never judged.
"""

from __future__ import annotations

import asyncio
import http.server
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
import websockets

from audit.analyzer.forms import ErrorIdentificationProbe

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Guard</title></head>
<body><main>
<form id="contact" novalidate>
  <label for="name">Name</label><input id="name" style="border:1px solid #767676">
  <button type="submit">Send message</button>
</form>
</main>
<script>
  window.ws = new WebSocket('ws://127.0.0.1:{ws_port}/open');
  document.getElementById('contact').addEventListener('submit', e => {
    e.preventDefault();
    fetch('/hit-get?name=');
    navigator.sendBeacon('/hit-beacon', 'name=');
    try { window.ws.send('submitted'); } catch (_) {}
    try { new WebSocket('ws://127.0.0.1:{ws_port}/new'); } catch (_) {}
    document.getElementById('name').style.border = '2px solid #c62828';
  });
</script></body></html>"""


@contextmanager
def _http(page: str, hits: list[str]) -> Iterator[str]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _answer(self) -> None:
            hits.append(f"{self.command} {self.path}")
            body = page.encode() if self.path == "/" else b""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = do_HEAD = do_OPTIONS = _answer  # noqa: N815

    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}/"
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


async def test_nothing_leaves_the_page_while_a_form_is_pressed(browser: Any) -> None:
    messages: list[str] = []
    connections: list[str] = []

    async def on_socket(socket: Any) -> None:
        connections.append(socket.request.path)
        async for message in socket:
            messages.append(str(message))

    async with websockets.serve(on_socket, "127.0.0.1", 0) as server:
        ws_port = next(iter(server.sockets)).getsockname()[1]
        hits: list[str] = []
        with _http(_PAGE.replace("{ws_port}", str(ws_port)), hits) as url:
            context = await browser.new_context(service_workers="block")
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="load")
                await page.wait_for_function("window.ws.readyState === 1")
                results = await ErrorIdentificationProbe().run(page)
                await asyncio.sleep(0.5)
            finally:
                await context.close()

    # Only the page itself was fetched; nothing the submit handler tried.
    assert [hit for hit in hits if "hit-" in hit] == [], hits
    # The socket opened at load stayed open, carried nothing, and no new one
    # was opened during the press.
    assert connections == ["/open"], connections
    assert messages == [], messages
    # The form tried to send itself, so it is not judged.
    assert [r.outcome for r in results] == ["not_checked"], results
