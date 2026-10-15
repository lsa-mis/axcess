"""The issue's pages table says how far a person has got checking each page.

"Checked by a person" shows "Not checked yet", "N of M checked" or "All
checked" for each page, counted over the page's occurrences of the issue,
and sorts so the pages not checked yet can be brought to the top.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.occurrence_reviews import save_review

from .test_accessibility_axe import _AXE_TAGS, _AXE_TEXT, _render_violations

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")
expect = playwright_async.expect

RULE = "checked-case"


def _seed(db_path: Path, scan_id: int) -> None:
    """Three occurrences on page 1 (two checked) and one on page 2 (none)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        pages = [
            int(r[0])
            for r in conn.execute(
                "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 2", (scan_id,)
            )
        ]
        ids: dict[str, int] = {}
        for page_id, target in (
            (pages[0], "#a"),
            (pages[0], "#b"),
            (pages[0], "#c"),
            (pages[1], "#d"),
        ):
            cur = conn.execute(
                "INSERT INTO page_a11y_findings (page_id, scan_id, pipeline, rule_id, wcag_sc, "
                "wcag_level, impact, help, target_selector, failure_summary, html_snippet, "
                "target_hash) VALUES (?, ?, 'axe', ?, '4.1.2', 'A', 'serious', 'Checked case', "
                "?, 'x', ?, ?)",
                (
                    page_id,
                    scan_id,
                    RULE,
                    target,
                    f'<b id="{target[1:]}">x</b>',
                    f"checked-{target}",
                ),
            )
            ids[target] = int(cur.lastrowid or 0)
        conn.commit()
        for target, decision in (("#a", "report"), ("#b", "repeat")):
            save_review(
                conn,
                scan_id=scan_id,
                page_id=pages[0],
                a11y_finding_ids=[ids[target]],
                page_image_ids=[],
                decision=decision,  # type: ignore[arg-type]
                notes="",
            )
        conn.commit()
    finally:
        conn.close()


async def test_pages_table_shows_and_sorts_what_was_checked(
    live_server: tuple[str, int], seeded_db: tuple[Path, Path, int], new_page: Any
) -> None:
    base, scan_id = live_server
    _seed(seeded_db[0], scan_id)
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues/axe:{RULE}/pages", wait_until="networkidle")
    table = page.get_by_role("table")
    header = table.get_by_role("columnheader", name="Checked by a person")
    await expect(header).to_be_visible()

    async def chips() -> list[str]:
        rows = table.locator("tbody tr")
        out = []
        for i in range(await rows.count()):
            out.append((await rows.nth(i).locator("td").last.inner_text()).strip())
        return out

    # Both kinds of checked count: two of the first page's three.
    assert sorted(await chips()) == ["2 of 3 checked", "Not checked yet"]

    # Sorting: the first press puts the most checked first, the second the least.
    await header.get_by_role("button").click()
    assert await chips() == ["2 of 3 checked", "Not checked yet"]
    await header.get_by_role("button").click()
    assert await chips() == ["Not checked yet", "2 of 3 checked"]

    # The table still fits a laptop screen without sideways scrolling.
    assert await page.evaluate("document.documentElement.scrollWidth") <= 1280
    await page.add_script_tag(content=_AXE_TEXT)
    violations = await page.evaluate(
        """async (tags) => (await window.axe.run(
            document.querySelector('table'), { runOnly: { type: 'tag', values: tags } },
        )).violations""",
        _AXE_TAGS,
    )
    assert not violations, _render_violations(violations)


async def test_all_checked_reads_as_finished(
    live_server: tuple[str, int], seeded_db: tuple[Path, Path, int], new_page: Any
) -> None:
    base, scan_id = live_server
    _seed(seeded_db[0], scan_id)
    conn = sqlite3.connect(seeded_db[0])
    try:
        (finding,) = conn.execute(
            "SELECT id, page_id FROM page_a11y_findings WHERE target_selector = '#c'"
        ).fetchall()
        save_review(
            conn,
            scan_id=scan_id,
            page_id=int(finding[1]),
            a11y_finding_ids=[int(finding[0])],
            page_image_ids=[],
            decision="report",
            notes="",
        )
        conn.commit()
    finally:
        conn.close()

    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues/axe:{RULE}/pages", wait_until="networkidle")
    await expect(page.get_by_role("table")).to_contain_text("All checked")
