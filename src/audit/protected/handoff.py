"""In-memory transfer of the selected login tab's sessionStorage."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page, Route

SessionStorage = dict[str, dict[str, str]]
_MAX_STORAGE_BYTES = 16 * 1024 * 1024
_MAX_FRAMES = 32


async def capture_session_storage(page: Page) -> SessionStorage:
    """Include embedded origins in the selected tab, without merging other tabs."""
    frames = page.frames
    if len(frames) > _MAX_FRAMES:
        raise ValueError("Too many frames to transfer the signed-in session.")
    result: SessionStorage = {}
    for frame in frames:
        snapshot = await frame.evaluate(
            """() => {
                if (!/^https?:$/.test(location.protocol) || self.origin === 'null')
                    return null;
                const entries = Object.fromEntries(Object.entries(sessionStorage));
                if (JSON.stringify(entries).length > 8 * 1024 * 1024)
                    throw new Error('Session storage exceeds the handoff limit');
                return {origin: location.origin, entries};
            }"""
        )
        if snapshot and snapshot["entries"]:
            result[snapshot["origin"]] = snapshot["entries"]
    if len(json.dumps(result).encode()) > _MAX_STORAGE_BYTES:
        raise ValueError("Session storage exceeds the handoff limit.")
    return result


async def restore_session_storage(page: Page, state: SessionStorage) -> None:
    """Seed storage once through empty, locally fulfilled documents.

    An init script replayed on every navigation would resurrect stale tokens
    after an application deletes or rotates them. Bootstrap each origin before
    crawling instead; the reusable scan tab then owns its evolving storage.
    No target requests or application scripts run during this bootstrap.
    """
    if not state:
        return

    async def empty_document(route: Route) -> None:
        await route.fulfill(status=200, content_type="text/html", body="<!doctype html>")

    await page.route("**/*", empty_document)
    try:
        for origin, entries in state.items():
            await page.goto(origin + "/", wait_until="domcontentloaded", timeout=10_000)
            await page.evaluate(
                "entries => { for (const [key, value] of Object.entries(entries)) "
                "sessionStorage.setItem(key, value); }",
                entries,
            )
        await page.goto("about:blank", timeout=10_000)
    finally:
        await page.unroute("**/*", empty_document)
