"""The saved copy shows each frame as the scan saw it, or says it is missing.

The saved copy runs without scripts, so a frame loaded live inside it (a
Google Sites embed, a video, a form) used to show as an empty box. The scan
now saves each frame's document, and the inspector puts it back in place,
frames inside frames too. A frame with nothing saved shows a note naming
where it came from, and nothing is fetched from the frame's site.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

from ._inspector_case import open_inspector, seed

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

CAPTURE = (
    "<!doctype html><html lang='en'><head><title>Frames fixture</title></head><body><main>"
    "<h1 id='target'>Frames</h1>"
    # Text while the scan ran, so the scan counted the frames after it from 0.
    "<noscript><iframe src='https://never.example/' title='Never a frame'></iframe></noscript>"
    "<iframe src='https://embed.example/one' title='Saved embed'></iframe>"
    "<iframe src='https://www.youtube.com/embed/x' title='Video'></iframe>"
    "</main></body></html>"
)
RULE = "aria-valid-attr"
FRAMES = [
    # (frame_id, parent_id, index, url, html)
    (
        1,
        0,
        0,
        "https://embed.example/one",
        "<p id='saved'>Saved embed content</p><iframe title='Inner'></iframe>",
    ),
    (2, 1, 0, "about:blank", "<p id='deep'>Built by code</p>"),
]


@pytest.fixture
def page_id(seeded_db: tuple[Path, Path, int]) -> int:
    db_path, _, scan_id = seeded_db
    page = seed(db_path, scan_id, CAPTURE, RULE, [("#target", '<h1 id="target">Frames</h1>')])
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executemany(
            "INSERT INTO page_frames (scan_id, page_id, frame_id, parent_id, frame_index, "
            "url, html) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (scan_id, page, fid, parent, index, url, gzip.compress(html.encode()))
                for fid, parent, index, url, html in FRAMES
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return page


async def test_saved_frames_are_shown_and_missing_ones_say_so(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    base, _ = live_server
    hosts: list[str] = []

    async def opened(page: Any) -> None:
        page.on("request", lambda request: hosts.append(request.url))

    page = await open_inspector(new_page, base, seeded_db[2], page_id, RULE)
    await opened(page)
    copy = page.frame_locator('iframe[title^="Saved copy"]')

    embed = copy.frame_locator('iframe[title="Saved embed"]')
    await playwright_async.expect(embed.locator("#saved")).to_have_text("Saved embed content")
    await playwright_async.expect(
        embed.frame_locator('iframe[title="Inner"]').locator("#deep")
    ).to_have_text("Built by code")

    video = copy.frame_locator('iframe[title="Video"]')
    await playwright_async.expect(video.locator("p")).to_have_text(
        "This part of the page comes from youtube.com. The saved copy does not include it. "
        "Use “Open live page” to see it."
    )
    await playwright_async.expect(video.locator("html")).to_have_attribute("lang", "en")

    # Nothing was loaded from the frames' own sites.
    await page.reload(wait_until="networkidle")
    await playwright_async.expect(embed.locator("#saved")).to_be_visible()
    assert not [url for url in hosts if "embed.example" in url or "youtube.com" in url], hosts
    await page.context.close()
