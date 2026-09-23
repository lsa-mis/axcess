"""The inspector must not blame drift for interaction-revealed findings.

The highlight pass searches the *load-state* capture. An element the interaction
probe only reached by operating a control was never in that capture, so failing
to find it is the expected result, not evidence the site changed. These tests
pin the two explanations apart: they are both real, and telling them apart is
the whole point.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from audit.db.schema import connect

# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

#: A selector that cannot match the stored capture, so the highlight pass
#: always misses — which is the branch under test.
MISSING_SELECTOR = "#never-present-at-load"
REVEALING_CONTROL = "Open booking dialog"


def _seed_findings(db_path: Path, scan_id: int, *revealed_by: str | None) -> int:
    """Add a11y findings whose targets are all absent from the capture.

    One per ``revealed_by``, sharing a rule so the ``?issue=`` path gathers
    them together the way a real multi-occurrence issue does.
    """
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        page = conn.execute("SELECT id FROM pages WHERE scan_id = ? LIMIT 1", (scan_id,)).fetchone()
        assert page is not None, "seeded scan has no pages"
        for index, control in enumerate(revealed_by):
            conn.execute(
                "INSERT INTO page_a11y_findings (page_id, scan_id, rule_id, wcag_sc, "
                "wcag_level, impact, help, target_selector, failure_summary, "
                "html_snippet, target_hash, revealed_by) "
                "VALUES (?, ?, 'aria-dialog-name', '4.1.2', 'A', 'serious', "
                "'ARIA dialog nodes should have an accessible name', ?, 'no name', "
                "?, ?, ?)",
                (
                    page["id"],
                    scan_id,
                    MISSING_SELECTOR,
                    f'<div role="dialog" data-n="{index}"></div>',
                    f"hash-{index}",
                    control,
                ),
            )
        conn.commit()
        return int(page["id"])
    finally:
        conn.close()


async def _inspector_text(new_page: Any, base: str, scan_id: int, page_id: int) -> str:
    """Open the inspector on the unmatchable findings and return its text."""
    url = f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?issue=axe:aria-dialog-name"
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(url, wait_until="networkidle")
        # The highlight pass runs in requestIdleCallback, so the status
        # line settles a beat after the document is ready.
        await page.wait_for_timeout(1500)
        return await page.locator("body").inner_text()
    finally:
        # One page at a time: close it now rather than at teardown.
        await page.context.close()


async def test_revealed_finding_names_its_control_instead_of_blaming_drift(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    db_path, _, scan_id = seeded_db
    page_id = _seed_findings(db_path, scan_id, REVEALING_CONTROL)

    text = await _inspector_text(new_page, live_server[0], scan_id, page_id)

    assert REVEALING_CONTROL in text
    assert "the page as it loaded" in text
    # Stops at "flagged": the probe records that a violation was first reported
    # after the control was operated, not that the element was absent before.
    assert "first flagged after activating" in text
    # The load capture is not stale, and saying so blames the site for a fact
    # about how the scan works.
    assert "changed since the scan" not in text


async def test_load_state_finding_still_reports_a_possible_change(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    db_path, _, scan_id = seeded_db
    page_id = _seed_findings(db_path, scan_id, None)

    text = await _inspector_text(new_page, live_server[0], scan_id, page_id)

    # Nothing revealed this one, so it genuinely should have been in the
    # capture and drift is the honest explanation.
    assert "changed since the scan" in text
    assert "the page as it loaded" not in text


async def test_a_mixed_issue_keeps_both_explanations_open(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """One issue can span load-state and interaction-revealed occurrences.

    Neither explanation covers the whole set then: the load-state occurrence
    genuinely should have been matched, and the revealed one was never going to
    be. Committing to either would misreport half the findings.
    """
    db_path, _, scan_id = seeded_db
    page_id = _seed_findings(db_path, scan_id, REVEALING_CONTROL, None)

    text = await _inspector_text(new_page, live_server[0], scan_id, page_id)

    assert "a control was operated" in text
    assert "changed since the scan" in text
    # With drift still in play this is not the settled case, so it must not
    # claim a specific control accounts for the miss.
    assert "first flagged after activating" not in text


def _seed_two_state_issue(db_path: Path, scan_id: int) -> tuple[int, str]:
    """One rule failing both at load and behind a control, on one page."""
    state_key = "https://x.test/|#menu|Filter"
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        page = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()
        conn.execute(
            "INSERT INTO page_dom_states (page_id, scan_id, state_key, revealed_by, "
            "path_labels, encoding, dom) VALUES (?, ?, ?, 'Filter', '[\"Filter\"]', "
            "'gzip', ?)",
            (page["id"], scan_id, state_key, gzip.compress(b"<!doctype html><html></html>")),
        )
        for target, revealed_by, key in (
            ("#at-load", None, None),
            ("#after-click", "Filter", state_key),
        ):
            conn.execute(
                "INSERT INTO page_a11y_findings (page_id, scan_id, rule_id, wcag_sc, "
                "wcag_level, impact, help, target_selector, failure_summary, "
                "html_snippet, target_hash, revealed_by, revealed_state_key) "
                "VALUES (?, ?, 'aria-required-parent', '1.3.1', 'A', 'serious', "
                "'Certain ARIA roles must be contained by particular parents', ?, "
                "'bad parent', ?, ?, ?, ?)",
                (
                    page["id"],
                    scan_id,
                    target,
                    '<a role="menuitem">' + target + "</a>",
                    "hash" + target,
                    revealed_by,
                    key,
                ),
            )
        conn.commit()
        return int(page["id"]), state_key
    finally:
        conn.close()


async def _evidence_text(new_page: Any, base: str, scan_id: int, page_id: int, state: str) -> str:
    url = (
        base + "/app/scans/" + str(scan_id) + "/pages/" + str(page_id) + "/inspect"
        "?issue=axe:aria-required-parent&state=" + state
    )
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        return await page.locator("body").inner_text()
    finally:
        # One page at a time: close it now rather than at teardown.
        await page.context.close()


async def test_each_state_shows_only_the_occurrences_it_contains(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """One issue can fail both at load and behind a control.

    The evidence list used to show every occurrence whichever state was
    selected, so "At page load" listed markup that only exists after a click,
    and a revealed state listed occurrences belonging to a different control.
    That is the same mistake as the message this view was built to remove,
    made by the panel underneath it.
    """
    db_path, _, scan_id = seeded_db
    page_id, state_key = _seed_two_state_issue(db_path, scan_id)
    base = live_server[0]

    at_load = await _evidence_text(new_page, base, scan_id, page_id, "")
    assert "#at-load" in at_load
    assert "#after-click" not in at_load
    assert "in another state" in at_load

    revealed = await _evidence_text(new_page, base, scan_id, page_id, quote(state_key, safe=""))
    assert "#after-click" in revealed
    # The load-state occurrence is still there: the click added markup, it did
    # not remove the page underneath.
    assert "#at-load" in revealed
