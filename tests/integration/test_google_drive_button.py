"""The Drive download button fallback, pressed in real Chromium.

Moved from tests/unit/test_google_drive_download.py (2026-11-20): it needs a
browser, and CI installs Chromium for this folder, not for the unit job.
"""

from __future__ import annotations

import http.server
import threading
from collections.abc import Iterator

import pytest

from audit.linked_files.google import download_with_button

FILE_ID = "1-5fbJabcdefghijklmnop"
PDF = b"%PDF-1.7\n" + b"x" * 200


@pytest.fixture
def drive_like_site() -> Iterator[str]:
    """A page with a "Download" button that downloads a PDF, on this computer."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.startswith("/file/d/"):
                body = (
                    b"<!doctype html><html><body><h1>report.pdf</h1>"
                    b"<button type='button' aria-label='Download'"
                    b" onclick=\"location.href='/download'\">"
                    b"<svg aria-hidden='true' width='16' height='16'></svg></button>"
                    b"</body></html>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
            else:
                body = PDF
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", 'attachment; filename="report.pdf"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


async def test_the_button_fallback_presses_download_and_keeps_the_file(
    drive_like_site: str,
) -> None:
    """The button is an icon named only by its accessible name, as Drive's
    is: found by role and name, then pressed."""
    pytest.importorskip("playwright.async_api")
    got = await download_with_button(f"{drive_like_site}/file/d/{FILE_ID}/view", user_agent="test")
    assert (got.outcome, got.body) == ("ok", PDF)
