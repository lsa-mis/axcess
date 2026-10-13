"""Save what each frame on a page showed, beside the page's saved copy.

A saved copy (``pages.rendered_html``) is the top document only. Its
``<iframe>`` elements keep their ``src``, so the Page inspector used to load
each frame live, inside a sandbox with scripts off. Most embeds draw their
content with scripts (Google Sites' "Custom embed", video players, forms),
so they showed as empty boxes, and the copy no longer matched what the scan
checked. This module reads each frame's document in the scan's own live page,
right after the page itself is read, so the inspector can show the frame as
the scan saw it.

Each saved frame records where it sat: ``parent_id`` (0 for the page itself,
otherwise the ``frame_id`` of the frame it is inside) and ``index``, which
``<iframe>`` or ``<frame>`` it is in its parent's document, counted in
document order and skipping any inside ``<noscript>``. The inspector counts
the same way in the saved markup, so the two line up without adding an
attribute to the saved markup, which is evidence and must stay as captured.

Frames from other sites are read too: a frame on a page in the scan's scope
is part of that page (the interaction probe clicks inside them for the same
reason). Playwright reads a cross-origin frame's document through the
browser, not through the page's scripts.

Bounds (AGENTS.md rule 6): at most :data:`MAX_FRAMES` frames per page,
:data:`MAX_FRAME_BYTES` per frame (the same limit as the page itself),
:data:`MAX_TOTAL_BYTES` in all, and :data:`TIMEOUT_S` for the whole read.
A frame over a limit, detached, or unreadable is left out; the inspector
shows a note in its place. Never raises.
"""

from __future__ import annotations

import asyncio
import gzip
from dataclasses import dataclass
from typing import TYPE_CHECKING

from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Frame, Page

log = get_logger(__name__)

MAX_FRAMES = 30
MAX_FRAME_BYTES = 2_000_000
MAX_TOTAL_BYTES = 8_000_000
TIMEOUT_S = 10.0

# Where a frame element sits among its document's frames. The same rule as the
# inspector's ``frameElements``: document order, not inside <noscript>.
_INDEX_JS = """
(el) => Array.from(el.ownerDocument.querySelectorAll('iframe, frame'))
  .filter((f) => !f.closest('noscript'))
  .indexOf(el)
"""
_LENGTH_JS = "() => document.documentElement ? document.documentElement.outerHTML.length : 0"


@dataclass(frozen=True)
class SavedFrame:
    """One frame's document, and where it sat on the page."""

    #: 1-based, in the order the frames were read. Unique within one page.
    frame_id: int
    #: 0 when the frame is in the page itself, else the parent's ``frame_id``.
    parent_id: int
    #: Which frame element it is in the parent's document, from 0.
    index: int
    #: The frame's own address, used to resolve its relative links.
    url: str
    #: gzip of the UTF-8 document, ``compresslevel=1, mtime=0`` like the page.
    html: bytes


async def capture_frames(page: Page) -> tuple[SavedFrame, ...]:
    """Read every frame on ``page``; whatever cannot be read is left out."""
    saved: list[SavedFrame] = []
    try:
        async with asyncio.timeout(TIMEOUT_S):
            await _read_frames(page, saved)
    except Exception as exc:
        # A timeout or a page that navigated keeps what was read so far.
        log.debug("frames.partial", error_type=type(exc).__name__, saved=len(saved))
    return tuple(saved)


async def _read_frames(page: Page, saved: list[SavedFrame]) -> None:
    ids: dict[Frame, int] = {page.main_frame: 0}
    total = 0
    # ``page.frames`` lists a frame after the frame it is in, so a parent has
    # its id by the time its children are read. A child whose parent was left
    # out is left out too: it would have nowhere to go.
    for frame in page.frames:
        if frame is page.main_frame:
            continue
        if len(saved) >= MAX_FRAMES:
            log.info("frames.limited", reason="count", limit=MAX_FRAMES)
            return
        parent = frame.parent_frame
        if parent is None or parent not in ids or frame.is_detached():
            continue
        try:
            element = await frame.frame_element()
            index = await element.evaluate(_INDEX_JS)
            length = await frame.evaluate(_LENGTH_JS)
            if not isinstance(index, int) or index < 0:
                continue
            if not isinstance(length, int) or length <= 0 or length > MAX_FRAME_BYTES:
                continue
            body = (await frame.content()).encode("utf-8", errors="replace")
        except Exception as exc:
            log.debug("frames.unreadable", error_type=type(exc).__name__)
            continue
        if len(body) > MAX_FRAME_BYTES:
            continue
        blob = gzip.compress(body, compresslevel=1, mtime=0)
        if total + len(blob) > MAX_TOTAL_BYTES:
            log.info("frames.limited", reason="bytes", limit=MAX_TOTAL_BYTES)
            return
        total += len(blob)
        frame_id = len(saved) + 1
        ids[frame] = frame_id
        saved.append(
            SavedFrame(
                frame_id=frame_id,
                parent_id=ids[parent],
                index=index,
                url=frame.url[:2048],
                html=blob,
            )
        )
