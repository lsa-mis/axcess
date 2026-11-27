"""Shared parts of the inspector edge-case tests (``test_inspector_<case>.py``).

Each test seeds its own saved copy into ``pages.rendered_html`` with one
Rule check (axe) occurrence per flagged element, opens the inspector on that
rule, and reads the saved copy from the inspector page. The saved copy is
sandboxed without scripts, so nothing can wait inside it: a timer there never
fires, and ``frame.wait_for_function`` never re-polls. Every wait runs on the
inspector page and reads the saved copy's document from there (``DOC``).
"""

from __future__ import annotations

import asyncio
import gzip
import sqlite3
from pathlib import Path
from typing import Any

from audit.db.schema import connect

DOC = "document.querySelector('iframe[title^=\"Saved copy\"]').contentDocument"

# The numbered box's rectangle in the saved copy's view, or null when it is
# not drawn (absent or hidden).
BOX_RECT = f"""() => {{
  const box = {DOC}.getElementById('axcess-spotlight');
  if (!box || getComputedStyle(box).display === 'none') return null;
  const r = box.getBoundingClientRect();
  return {{left: r.left, top: r.top, right: r.right, bottom: r.bottom}};
}}"""


def seed(
    db_path: Path, scan_id: int, capture: str, rule: str, findings: list[tuple[str, str]]
) -> int:
    """Give the scan's first page ``capture`` and one axe occurrence per (selector, snippet)."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        page = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()
        conn.execute(
            "UPDATE pages SET rendered_html = ? WHERE id = ?",
            (gzip.compress(capture.encode()), page["id"]),
        )
        for n, (selector, snippet) in enumerate(findings):
            conn.execute(
                "INSERT INTO page_a11y_findings (page_id, scan_id, pipeline, rule_id, wcag_sc, "
                "wcag_level, impact, help, target_selector, failure_summary, html_snippet, "
                "target_hash) VALUES (?, ?, 'axe', ?, '4.1.2', 'A', 'serious', 'Edge case', "
                "?, 'edge', ?, ?)",
                (page["id"], scan_id, rule, selector, snippet, f"edge-{rule}-{n}"),
            )
        conn.commit()
        return int(page["id"])
    finally:
        conn.close()


async def open_inspector(
    new_page: Any, base: str, scan_id: int, page_id: int, rule: str, **options: Any
) -> Any:
    page = await new_page(viewport={"width": 1280, "height": 900}, **options)
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?issue=axe:{rule}",
        wait_until="networkidle",
    )
    return page


def box_note(page: Any) -> Any:
    """The line under the saved copy that says where the box is when it is
    not simply around the element ("Where the box is: ...").

    It followed the key to the marks until 2026-11-27, when the key moved
    into the "?" beside Hide highlights (see ``highlight_key``).
    """
    return page.locator("#inspect-box-note")


async def open_manual_review(page: Any) -> None:
    """Open the inspector's "Manual review" section, which starts closed
    (2026-11-27), so the review of the element you are on can be used."""
    button = page.get_by_role("button", name="Manual review", exact=True)
    await button.click()
    await page.get_by_role("group", name="The flagged element you are on").wait_for()


async def highlight_key(page: Any) -> Any:
    """Open the "?" beside Hide highlights and return its panel: the key to
    the marks ("A blue box with a yellow ring marks the flagged element.")."""
    await page.get_by_role("button", name="What do the highlights mean?", exact=True).click()
    return page.locator("[popover]:popover-open")


def element_status(page: Any) -> Any:
    """The toolbar status that names the flagged element you are on."""
    return page.get_by_role("group", name="Flagged elements", exact=True).get_by_role("status")


def rect_of(selector: str) -> str:
    """A script for one saved-copy element's rectangle in the frame's view."""
    return f"""{DOC}.querySelector({selector!r}).getBoundingClientRect()"""


async def settled(page: Any) -> None:
    """Wait until the inspector stops scrolling the saved copy and moving the box."""
    view = f"{DOC}.defaultView"
    read = f"() => [{view}.scrollY, {view}.scrollX, JSON.stringify(({BOX_RECT})())]"
    previous = await page.evaluate(read)
    for _ in range(40):
        await asyncio.sleep(0.7)
        current = await page.evaluate(read)
        if current == previous:
            return
        previous = current
    raise AssertionError("the saved copy never stopped moving")
