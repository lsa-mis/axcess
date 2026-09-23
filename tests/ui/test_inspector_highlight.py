"""Matching a finding's stored markup against the document being inspected.

axe reports a container element as its start tag alone, not the element with
its subtree, so equality can never match one. These tests pin the prefix rule
that handles it — and the cases it must still refuse, because a rule loose
enough to outline the wrong element is worse than one that outlines nothing.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

CAPTURE = (
    "<!doctype html><html><head><title>Fixture</title></head><body>"
    '<div id="portal-1" class="category-menu" role="listbox" tabindex="0">'
    "<span>One</span><span>Two</span>"
    "</div>"
    '<div id="other" class="sidebar">nothing to see</div>'
    "</body></html>"
)


def _seed(db_path: Path, scan_id: int, *, selector: str, snippet: str) -> int:
    """Give a page a known capture and one finding pointing into it."""
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
            "INSERT INTO page_a11y_findings (page_id, scan_id, rule_id, wcag_sc, "
            "wcag_level, impact, help, target_selector, failure_summary, "
            "html_snippet, target_hash) "
            "VALUES (?, ?, 'aria-input-field-name', '4.1.2', 'A', 'serious', "
            "'ARIA input fields must have an accessible name', ?, 'no name', ?, 'h1')",
            (page["id"], scan_id, selector, snippet),
        )
        conn.commit()
        return int(page["id"])
    finally:
        conn.close()


async def _status(new_page: Any, base: str, scan_id: int, page_id: int, selector: str) -> str:
    url = (
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect"
        f"?selector={selector.replace('#', '%23')}"
    )
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(url, wait_until="networkidle")
        # The highlight pass runs in requestIdleCallback.
        await page.wait_for_timeout(1500)
        return await page.locator("body").inner_text()
    finally:
        # One page at a time: close it now rather than at teardown.
        await page.context.close()


async def test_a_start_tag_snippet_finds_its_container(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The case that never worked: a container reported as its start tag.

    ``outerHTML`` here is the div plus two spans, which cannot equal the stored
    start tag. Before the prefix rule the inspector said the element "was not
    found in this capture" while it sat in the document being searched.
    """
    db_path, _, scan_id = seeded_db
    snippet = '<div id="portal-1" class="category-menu" role="listbox" tabindex="0">'
    page_id = _seed(db_path, scan_id, selector="#portal-1", snippet=snippet)

    text = await _status(new_page, live_server[0], scan_id, page_id, "#portal-1")

    assert "The red outline marks the flagged element" in text
    assert "not found in this capture" not in text


async def test_a_start_tag_for_a_different_element_is_refused(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Prefix matching must not turn a generic selector into a wildcard.

    ``div`` matches the container first in document order, but the snippet
    describes neither div in the capture. Outlining the wrong element would be
    worse than outlining nothing: the reviewer would record a defect against
    markup that never carried it.
    """
    db_path, _, scan_id = seeded_db
    snippet = '<div id="does-not-exist" class="ghost">'
    page_id = _seed(db_path, scan_id, selector="div", snippet=snippet)

    text = await _status(new_page, live_server[0], scan_id, page_id, "div")

    assert "not found in this capture" in text
    assert "The red outline marks the flagged element" not in text


async def test_a_snippet_with_a_subtree_still_needs_to_match_it(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The prefix rule applies only to bare start tags.

    A snippet carrying content is a complete description of the element, so it
    keeps the exact comparison. Relaxing that one too would let a snippet whose
    children disagree with the document match anyway.
    """
    db_path, _, scan_id = seeded_db
    snippet = '<div id="portal-1" class="category-menu"><span>Different</span></div>'
    page_id = _seed(db_path, scan_id, selector="#portal-1", snippet=snippet)

    text = await _status(new_page, live_server[0], scan_id, page_id, "#portal-1")

    assert "not found in this capture" in text
