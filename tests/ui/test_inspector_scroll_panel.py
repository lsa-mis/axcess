"""The numbered box stays on a flagged element inside a panel that scrolls on its own.

An app-style page (a SaaS dashboard) scrolls its sidebar, not the window. The
box was placed once, from where the element was at that moment, and followed
only a window resize, and the frame was centred by scrolling the window only.
So a flagged checkbox far down a sidebar was never scrolled into view, and the
box sat stuck at the top or bottom of the sidebar over some other control.
"""

from __future__ import annotations

import asyncio
import gzip
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

CAPTURE = (
    "<!doctype html><html style='height:100%;overflow:hidden'>"
    "<head><title>App shell fixture</title></head>"
    "<body style='height:100%;margin:0;overflow:hidden;display:flex'>"
    "<aside id='panel' style='width:320px;height:100%;overflow-y:auto'>"
    + "".join(f"<p style='height:80px;margin:0'>Setting {n}</p>" for n in range(30))
    + "<label><input id='flagged' type='checkbox' aria-controls='list-54'>"
    "Show read notifications</label>"
    + "".join(f"<p style='height:80px;margin:0'>Setting {n}</p>" for n in range(30, 60))
    + "</aside><main style='flex:1'>Main</main></body></html>"
)


def _seed(db_path: Path, scan_id: int) -> int:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        page = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()
        conn.execute(
            "UPDATE pages SET rendered_html = ? WHERE id = ?",
            (gzip.compress(CAPTURE.encode()), page["id"]),
        )
        conn.execute(
            "INSERT INTO page_a11y_findings (page_id, scan_id, pipeline, rule_id, wcag_sc, "
            "wcag_level, impact, help, target_selector, failure_summary, html_snippet, "
            "target_hash) VALUES (?, ?, 'axe', 'target-size', '2.5.8', 'AA', 'serious', "
            "'Target size', '#flagged', 'too small', ?, 'panel-0')",
            (
                page["id"],
                scan_id,
                '<input id="flagged" type="checkbox" aria-controls="list-54">',
            ),
        )
        conn.commit()
        return int(page["id"])
    finally:
        conn.close()


# The saved copy is sandboxed without scripts, so nothing can wait inside it:
# a timer or animation frame there never fires. Every check runs on the
# inspector page and reads the saved copy's document from there.
_DOC = "document.querySelector('iframe[title^=\"Saved copy\"]').contentDocument"

# Whether the box is shown and around the element, and the element is inside
# the panel's visible part.
_BOX_ON_ELEMENT = f"""() => {{
  const doc = {_DOC};
  const box = doc.getElementById('axcess-spotlight');
  if (!box || getComputedStyle(box).display === 'none') return false;
  const b = box.getBoundingClientRect();
  const e = doc.getElementById('flagged').getBoundingClientRect();
  const p = doc.getElementById('panel').getBoundingClientRect();
  return b.top <= e.top && e.bottom <= b.bottom && p.top <= e.top && e.bottom <= p.bottom;
}}"""

_PANEL = f"{_DOC}.getElementById('panel')"


async def _settled(page: Any) -> None:
    """Wait until the inspector stops centring the element (the page has settled)."""
    read = f"{_PANEL}.scrollTop"
    previous = await page.evaluate(read)
    for _ in range(40):
        await asyncio.sleep(0.8)
        current = await page.evaluate(read)
        if current == previous:
            return
        previous = current
    raise AssertionError("the panel never stopped scrolling")


async def test_the_box_follows_an_element_in_a_scrolling_panel(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed(db_path, scan_id)
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(
            f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?issue=axe:target-size",
            wait_until="networkidle",
        )
        frame_locator = page.frame_locator("iframe[title^='Saved copy']")
        await playwright_async.expect(frame_locator.locator("#axcess-spotlight")).to_have_text(
            "Flagged element"
        )

        # The panel, not the window, was scrolled so the element is in view,
        # and the box is around it.
        await page.wait_for_function(f"() => {_PANEL}.scrollTop > 1000")
        await page.wait_for_function(_BOX_ON_ELEMENT)
        await _settled(page)

        # Scrolled a little: the box moves with the element.
        before = await page.evaluate(f"{_DOC}.getElementById('axcess-spotlight').offsetTop")
        await page.evaluate(f"{_PANEL}.scrollBy(0, 120)")
        await page.wait_for_function(
            f"() => {_DOC}.getElementById('axcess-spotlight').offsetTop <= {before} - 100"
        )
        await page.wait_for_function(_BOX_ON_ELEMENT)

        # Scrolled out of the panel: the box is hidden, not left behind.
        await page.evaluate(f"{_PANEL}.scrollTop = 0")
        await page.wait_for_function(
            f"() => getComputedStyle({_DOC}.getElementById('axcess-spotlight')).display === 'none'"
        )
        # And back: shown around it again.
        await page.evaluate(
            f"{_PANEL}.scrollTop = {_DOC}.getElementById('flagged').offsetTop - 200"
        )
        await page.wait_for_function(_BOX_ON_ELEMENT)
    finally:
        await page.context.close()
