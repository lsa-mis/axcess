"""Needs review issues outline exactly the elements they are about, as Barriers do.

AI review findings were never outlined: the inspector compared their stored
rule (``semantic:2.4.4``) with the key's second part (``2.4.4``). An Alfa
"can't tell" issue outlined its rule's failed occurrences too. And an image
from the image text check has no selector, so nothing was outlined for it.
Each is now outlined by the element it came from, and only that element.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from audit.analyzer.semantic.extractor import extract_links
from audit.db import repo
from audit.db.schema import connect
from audit.extractor.html_images import extract_image_refs

from .test_accessibility_axe import _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

# Long enough that the AI review keeps only the first 300 characters of each
# link's code, and the two links' kept code is identical: only their place in
# the page tells them apart.
_LONG = "a" * 320
# Two paragraphs one selector matches. The zoom and layout check keeps the
# first 240 characters of an element's code and does not mark the cut.
_CLAMPED = [
    f'<p class="clamp">{word} ' + "and more text " * 30 + "</p>" for word in ("First", "Second")
]
CAPTURE = (
    "<!doctype html><html><head><title>Needs review fixture</title></head><body><main>"
    '<img src="/sale.png" alt="Sale ends Friday" width="120" height="40">'
    '<img src="/logo.png" alt="Example" width="120" height="40">'
    '<img src="/sale.png" alt="Sale ends Friday" width="120" height="40">'
    '<noscript><img src="/sale.png" alt="Sale ends Friday"></noscript>'
    f'<p><a class="more" href="/one?{_LONG}">More</a></p>'
    f'<p><a class="more" href="/two?{_LONG}">More</a></p>'
    '<nav><button type="button" id="first">One</button>'
    '<button type="button" id="second">Two</button></nav>'
    + "".join(_CLAMPED)
    + "</main></body></html>"
)


def _record(button_id: str) -> str:
    return json.dumps(
        {
            "type": "element",
            "path": f"//button[@id='{button_id}']",
            "name": "button",
            "attributes": [{"name": "id", "value": button_id}],
        }
    )


def _seed(db_path: Path, scan_id: int) -> int:
    """The capture on the scan's first page, with an image finding, an AI review
    finding on the second link, and one Alfa rule with both outcomes."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        page = conn.execute(
            "SELECT id, url_normalized FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1",
            (scan_id,),
        ).fetchone()
        page_id = int(page["id"])
        conn.execute(
            "UPDATE pages SET rendered_html = ?, final_url = NULL WHERE id = ?",
            (gzip.compress(CAPTURE.encode()), page_id),
        )
        image_ids: dict[str, int] = {}
        for ref in extract_image_refs(CAPTURE.encode(), page["url_normalized"]):
            if ref.url not in image_ids:
                image_ids[ref.url] = repo.upsert_image(
                    conn,
                    content_hash=f"needs-review-{len(image_ids)}".ljust(64, "0"),
                    src_url=ref.url,
                    mime="image/png",
                    bytes_len=10,
                    width=120,
                    height=40,
                    blob_path=None,
                    has_svg_text=False,
                    scan_id=scan_id,
                )
            repo.upsert_page_image(
                conn,
                page_id=page_id,
                image_id=image_ids[ref.url],
                alt_text=ref.alt,
                role=None,
                context_snippet=None,
                position=ref.position,
            )
        sale = next(i for url, i in image_ids.items() if url.endswith("/sale.png"))
        repo.upsert_analysis(
            conn,
            image_id=sale,
            ocr_text="Sale ends Friday",
            ocr_confidence=99,
            vlm_classification="informational",
            vlm_rationale="Text on a banner",
            has_text=True,
            model_versions={"test": "needs-review"},
        )
        repo.upsert_finding(
            conn,
            image_id=sale,
            scan_id=scan_id,
            severity="minor",
            priority_score=2,
            remediation_hint=None,
        )
        link = extract_links(CAPTURE.encode())[1]
        assert link.snippet.endswith("…")
        rows = [
            ("semantic", "semantic:2.4.4", "failed", link.selector, link.snippet),
            ("alfa", "sia-r111", "failed", _record("first"), _record("first")),
            ("alfa", "sia-r111", "cant_tell", _record("second"), _record("second")),
            ("responsive", "responsive-text-clipped", "failed", "p.clamp", _CLAMPED[1][:240]),
        ]
        for n, (pipeline, rule, outcome, selector, snippet) in enumerate(rows):
            conn.execute(
                "INSERT INTO page_a11y_findings (page_id, scan_id, pipeline, rule_id, wcag_sc, "
                "wcag_level, impact, help, target_selector, failure_summary, html_snippet, "
                "target_hash, engine_outcome) VALUES (?, ?, ?, ?, '2.4.4', 'A', 'moderate', "
                "'Needs review', ?, 'unclear', ?, ?, ?)",
                (page_id, scan_id, pipeline, rule, selector, snippet, f"needs-review-{n}", outcome),
            )
        conn.commit()
        return page_id
    finally:
        conn.close()


async def _open(new_page: Any, base: str, scan_id: int, page_id: int, issue: str) -> Any:
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?issue={quote(issue)}",
        wait_until="networkidle",
    )
    return page


async def test_an_image_issue_outlines_its_images_and_says_what_it_leaves_out(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed(db_path, scan_id)
    page = await _open(new_page, base, scan_id, page_id, "image:informational_adequate")
    try:
        await playwright_async.expect(page.get_by_text("2 places highlighted")).to_be_visible()
        frame = page.frame_locator("iframe[title^='Saved copy']")
        marked = frame.locator(".axcess-inspect-highlight")
        await playwright_async.expect(marked).to_have_count(2)
        # The two copies of the sale banner, not the logo between them.
        assert await marked.evaluate_all("els => els.map(el => el.getAttribute('src'))") == [
            "/sale.png",
            "/sale.png",
        ]
        where = page.locator("p", has_text="Where it is in the page code:")
        await playwright_async.expect(where).to_contain_text("number 1 of the 3 img elements")
        await playwright_async.expect(where).to_contain_text("Image address: /sale.png")
        group = page.get_by_role("group", name="Flagged elements", exact=True)
        await group.get_by_role("button", name="Next flagged element").click()
        await playwright_async.expect(where).to_contain_text("number 3 of the 3 img elements")
        await playwright_async.expect(
            page.get_by_text(
                "1 more occurrence is in page code that browsers do not show when scripts run",
                exact=False,
            )
        ).to_be_visible()
        await page.get_by_role("button", name="Evidence from the scan").click()
        await playwright_async.expect(
            page.get_by_text("Alt text (what a screen reader reads): “Sale ends Friday”").first
        ).to_be_visible()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_an_ai_review_issue_outlines_the_exact_link(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed(db_path, scan_id)
    page = await _open(new_page, base, scan_id, page_id, "semantic:2.4.4")
    try:
        frame = page.frame_locator("iframe[title^='Saved copy']")
        marked = frame.locator(".axcess-inspect-highlight")
        await playwright_async.expect(marked).to_have_count(1)
        # Both links' kept code is the same; the second is the one reviewed.
        href = await marked.get_attribute("href")
        assert href is not None and href.startswith("/two?")
        await playwright_async.expect(
            page.locator("p", has_text="Where it is in the page code:")
        ).to_contain_text("number 2 of the 2 a elements")
    finally:
        await page.context.close()


async def test_each_alfa_outcome_outlines_only_its_own_occurrences(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed(db_path, scan_id)
    for issue, button in (("alfa:sia-r111:cant_tell", "second"), ("alfa:sia-r111:failed", "first")):
        page = await _open(new_page, base, scan_id, page_id, issue)
        try:
            frame = page.frame_locator("iframe[title^='Saved copy']")
            marked = frame.locator(".axcess-inspect-highlight")
            await playwright_async.expect(marked).to_have_count(1)
            assert await marked.get_attribute("id") == button
        finally:
            await page.context.close()


async def test_a_cut_snippet_names_its_element_among_the_selectors_matches(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed(db_path, scan_id)
    page = await _open(new_page, base, scan_id, page_id, "responsive:responsive-text-clipped")
    try:
        frame = page.frame_locator("iframe[title^='Saved copy']")
        marked = frame.locator(".axcess-inspect-highlight")
        await playwright_async.expect(marked).to_have_count(1)
        await playwright_async.expect(marked).to_contain_text("Second and more text")
    finally:
        await page.context.close()
