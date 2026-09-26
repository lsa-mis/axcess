"""The Issues table's Filter menu: checkbox groups, end to end.

Every check compares the rows the table shows against what the API returns
for the same filters, so a checkbox that looks right but sends the wrong
query fails here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import playwright.async_api as pw
import pytest

from audit.db.schema import connect

from .test_accessibility_axe import _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

# (rule, sc, level, impact, help, revealed_by): one Level A group seen only
# after a click (Click-Through), one Level AA group, and one best-practice
# group with no criterion, on top of the seeded scan's two image groups.
_EXTRA = [
    ("button-name", "4.1.2", "A", "critical", "Buttons must have discernible text", "Open menu"),
    ("color-contrast", "1.4.3", "AA", "serious", "Elements must meet contrast", None),
    ("region", None, None, "moderate", "All page content should be in landmarks", None),
]


@pytest.fixture
def enriched(seeded_db: tuple[Path, Path, int]) -> None:
    db_path, _, scan_id = seeded_db
    conn = connect(db_path)
    try:
        pages = [r[0] for r in conn.execute("SELECT id FROM pages WHERE scan_id = ?", (scan_id,))]
        for n, (rule, sc, level, impact, help_, revealed) in enumerate(_EXTRA):
            for page_id in pages:
                conn.execute(
                    "INSERT INTO page_a11y_findings (page_id, scan_id, rule_id, wcag_sc, "
                    "wcag_level, impact, help, target_selector, html_snippet, target_hash, "
                    "status, revealed_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)",
                    (
                        page_id,
                        scan_id,
                        rule,
                        sc,
                        level,
                        impact,
                        help_,
                        f"#t{n}",
                        "<div></div>",
                        f"h-{rule}-{page_id}",
                        revealed,
                    ),
                )
        conn.commit()
    finally:
        conn.close()


async def _open(page: Any, base: str, scan_id: int, query: str = "") -> None:
    await page.goto(f"{base}/app/scans/{scan_id}/issues{query}", wait_until="networkidle")
    await pw.expect(
        page.get_by_role("table", name=re.compile(r"^Accessibility issues", re.I))
    ).to_be_visible()


def _filter_button(page: Any) -> Any:
    return page.get_by_role("button", name=re.compile(r"^Filter"))


async def _open_menu(page: Any) -> None:
    button = _filter_button(page)
    if await button.get_attribute("aria-expanded") != "true":
        await button.click()
    await pw.expect(button).to_have_attribute("aria-expanded", "true")


def _box(page: Any, group: str, value: str) -> Any:
    return page.get_by_role("group", name=group, exact=True).locator(f'input[data-value="{value}"]')


def _params(page: Any) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(page.url).query).items()}


async def _shown_keys(page: Any) -> set[str]:
    await page.wait_for_load_state("networkidle")
    table = page.get_by_role("table", name=re.compile(r"^Accessibility issues", re.I))
    hrefs = (
        await table.get_by_role("rowheader")
        .get_by_role("link")
        .evaluate_all("links => links.map(a => a.getAttribute('href'))")
    )
    return {re.sub(r"\?.*$", "", h).rsplit("/issues/", 1)[1] for h in hrefs}


async def _api_keys(page: Any, base: str, scan_id: int, **filters: str) -> set[str]:
    from urllib.parse import quote, unquote

    query = "&".join(f"{k}={v}" for k, v in filters.items() if v)
    body = await (await page.request.get(f"{base}/api/scans/{scan_id}/issues?{query}")).json()
    return {quote(unquote(r["issue_key"]), safe="") for r in body["rows"]}


async def _assert_matches_api(page: Any, base: str, scan_id: int) -> set[str]:
    p = _params(page)
    expected = await _api_keys(
        page,
        base,
        scan_id,
        conformance=p.get("conformance", ""),
        review_lane=p.get("type", ""),
        finding_type=p.get("finding_type", ""),
    )
    # The table follows the URL a fetch later; give it a few tries.
    for _ in range(20):
        shown = await _shown_keys(page)
        if shown == expected:
            break
        await page.wait_for_timeout(100)
    assert shown == expected, (p, shown, expected)
    return shown


async def test_menu_is_three_checkbox_groups_with_big_rows(enriched, live_server, new_page) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _open(page, base, scan_id)
    await _open_menu(page)
    for group in ("Level", "Type", "Found by"):
        fieldset = page.get_by_role("group", name=group, exact=True)
        await pw.expect(fieldset).to_be_visible()
        assert await fieldset.get_by_role("radio").count() == 0, group
        boxes = fieldset.get_by_role("checkbox")
        assert await boxes.count() >= 3, group
        for i in range(await boxes.count()):
            await pw.expect(boxes.nth(i)).not_to_be_checked()

    # The target: every option row is at least 44px tall, spans the panel,
    # and the box itself is 20px.
    rows = page.locator("fieldset label")
    panel_width = await page.locator("fieldset").first.evaluate(
        "f => f.getBoundingClientRect().width"
    )
    for i in range(await rows.count()):
        box = await rows.nth(i).bounding_box()
        assert box and box["height"] >= 44, (i, box)
        assert box["width"] >= panel_width - 2, (i, box, panel_width)
    size = await _box(page, "Level", "A").bounding_box()
    assert size and size["width"] >= 20 and size["height"] >= 20, size
    assert await _run_axe(page) == []


async def test_pressing_anywhere_on_the_row_toggles(enriched, live_server, new_page) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _open(page, base, scan_id)
    await _open_menu(page)
    row = _box(page, "Level", "A").locator("xpath=ancestor::label[1]")
    box = await row.bounding_box()
    assert box
    # Right edge (the count), left padding, and the label text: each toggles.
    for x, expected in ((box["width"] - 4, True), (3, False), (box["width"] / 2, True)):
        await page.mouse.click(box["x"] + x, box["y"] + box["height"] / 2)
        if expected:
            await pw.expect(_box(page, "Level", "A")).to_be_checked()
            await page.wait_for_url(re.compile(r"conformance=A(&|$)"))
        else:
            await pw.expect(_box(page, "Level", "A")).not_to_be_checked()
            await page.wait_for_url(lambda url: "conformance" not in url)
        # The menu stays open for the next choice.
        await pw.expect(_filter_button(page)).to_have_attribute("aria-expanded", "true")
        box = await row.bounding_box()
        assert box


async def test_several_in_a_group_and_across_groups_match_the_api(
    enriched, live_server, new_page
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _open(page, base, scan_id)
    everything = await _assert_matches_api(page, base, scan_id)
    assert len(everything) == 5, everything

    await _open_menu(page)
    # AA first, then A: the URL keeps option order, not click order.
    await _box(page, "Level", "AA").check()
    await page.wait_for_url(re.compile(r"conformance=AA(&|$)"))
    only_aa = await _assert_matches_api(page, base, scan_id)
    # Level AA: the contrast group and the image group (SC 1.4.5 is AA).
    assert "axe%3Acolor-contrast" in only_aa and "axe%3Abutton-name" not in only_aa, only_aa
    await _box(page, "Level", "A").check()
    await page.wait_for_url(re.compile(r"conformance=A%2CAA|conformance=A,AA"))
    a_or_aa = await _assert_matches_api(page, base, scan_id)
    assert only_aa < a_or_aa, (only_aa, a_or_aa)
    await pw.expect(_box(page, "Level", "AA")).to_be_checked()

    # Unchecking one keeps the other.
    await _box(page, "Level", "AA").uncheck()
    await page.wait_for_url(re.compile(r"conformance=A(&|$)"))
    await _assert_matches_api(page, base, scan_id)

    # Across groups the filters combine (AND); within a group they widen (OR).
    await _box(page, "Level", "A").uncheck()
    await _box(page, "Found by", "click_through").check()
    await page.wait_for_url(re.compile(r"finding_type=click_through"))
    ct = await _assert_matches_api(page, base, scan_id)
    assert ct == {"axe%3Abutton-name"}, ct
    await _box(page, "Found by", "alt_text").check()
    ct_or_alt = await _assert_matches_api(page, base, scan_id)
    assert ct < ct_or_alt, ct_or_alt
    await _box(page, "Type", "informational").check()
    narrowed = await _assert_matches_api(page, base, scan_id)
    assert narrowed and narrowed < ct_or_alt, narrowed

    # The badge counts groups in use; the line under the bar names them.
    await pw.expect(_filter_button(page)).to_contain_text("2")
    filtered = page.get_by_text("Filtered by", exact=False)
    await pw.expect(filtered.locator("xpath=..")).to_contain_text("Type: Informational")
    await pw.expect(filtered.locator("xpath=..")).to_contain_text("Click-Through, Alt Text")
    # Checking the lower options scrolls the page (the open panel reaches
    # past the fold), which takes the report tabs off screen. axe then
    # cannot see the active tab's sliding fill (a pointer-events-none layer
    # behind it) and reports white-on-page-background, a false positive.
    await page.evaluate("window.scrollTo(0, 0); document.querySelector('main').scrollTo(0, 0)")
    violations = await _run_axe(page)
    assert violations == [], [
        (v["id"], [(n["target"], n["html"][:160], n["failureSummary"][:300]) for n in v["nodes"]])
        for v in violations
    ]


async def test_a_reload_and_an_old_single_value_link_keep_the_checks(
    enriched, live_server, new_page
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _open(page, base, scan_id, "?conformance=A,AA&finding_type=wcag")
    await _open_menu(page)
    for group, value, on in (
        ("Level", "A", True),
        ("Level", "AA", True),
        ("Level", "BP", False),
        ("Found by", "wcag", True),
        ("Found by", "alt_text", False),
    ):
        check = pw.expect(_box(page, group, value))
        await (check.to_be_checked() if on else check.not_to_be_checked())
    await _assert_matches_api(page, base, scan_id)
    await page.reload(wait_until="networkidle")
    await _open_menu(page)
    await pw.expect(_box(page, "Level", "AA")).to_be_checked()

    # A saved link from before checkboxes: one value.
    await _open(page, base, scan_id, "?type=expert_review")
    await _open_menu(page)
    await pw.expect(_box(page, "Type", "expert_review")).to_be_checked()
    await pw.expect(_box(page, "Type", "likely_barrier")).not_to_be_checked()
    shown = await _assert_matches_api(page, base, scan_id)
    assert shown == {"image%3Aessential_missing"}, shown

    # A junk value is dropped, not treated as "match nothing".
    await _open(page, base, scan_id, "?type=nonsense")
    assert len(await _assert_matches_api(page, base, scan_id)) == 5


async def test_keyboard_only(enriched, live_server, new_page) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _open(page, base, scan_id)
    button = _filter_button(page)
    await button.focus()
    await page.keyboard.press("Enter")
    await pw.expect(button).to_have_attribute("aria-expanded", "true")
    # Tab into the panel: the first checkbox, then Space toggles it.
    await page.keyboard.press("Tab")
    first = _box(page, "Level", "A")
    await pw.expect(first).to_be_focused()
    await page.keyboard.press("Space")
    await pw.expect(first).to_be_checked()
    await page.wait_for_url(re.compile(r"conformance=A(&|$)"))
    # Focus stays on the box after the URL updates.
    await pw.expect(first).to_be_focused()
    await page.keyboard.press("Tab")
    await pw.expect(_box(page, "Level", "AA")).to_be_focused()
    await page.keyboard.press("Space")
    await page.wait_for_url(re.compile(r"conformance=A%2CAA|conformance=A,AA"))
    await _assert_matches_api(page, base, scan_id)
    # Escape closes and returns focus to the Filter button.
    await page.keyboard.press("Escape")
    await pw.expect(button).to_have_attribute("aria-expanded", "false")
    await pw.expect(button).to_be_focused()
    # Done does the same.
    await page.keyboard.press("Enter")
    await page.get_by_role("button", name="Done", exact=True).click()
    await pw.expect(button).to_be_focused()


async def test_clear_all_and_clear_filters_reset_every_group(
    enriched, live_server, new_page
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _open(page, base, scan_id, "?conformance=A,AA&type=likely_barrier&finding_type=wcag")
    await _open_menu(page)
    await page.get_by_role("button", name="Clear all", exact=True).click()
    await page.wait_for_url(lambda url: not re.search(r"conformance|type=", url))
    assert len(await _assert_matches_api(page, base, scan_id)) == 5
    for group in ("Level", "Type", "Found by"):
        boxes = page.get_by_role("group", name=group, exact=True).get_by_role("checkbox")
        for i in range(await boxes.count()):
            await pw.expect(boxes.nth(i)).not_to_be_checked()
    assert len(await _shown_keys(page)) == 5

    await _open(page, base, scan_id, "?conformance=A&finding_type=click_through")
    await page.get_by_role("button", name="Clear filters", exact=True).click()
    await page.wait_for_url(lambda url: not re.search(r"conformance|finding_type", url))
    assert len(await _assert_matches_api(page, base, scan_id)) == 5
    await pw.expect(page.get_by_text("Filtered by", exact=False)).to_have_count(0)


async def test_closing_by_clicking_outside_keeps_the_choice(
    enriched, live_server, new_page
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _open(page, base, scan_id)
    await _open_menu(page)
    await _box(page, "Type", "likely_barrier").check()
    await page.wait_for_url(re.compile(r"type=likely_barrier"))
    await page.mouse.click(5, 5)
    await pw.expect(_filter_button(page)).to_have_attribute("aria-expanded", "false")
    await _assert_matches_api(page, base, scan_id)
    await _open_menu(page)
    await pw.expect(_box(page, "Type", "likely_barrier")).to_be_checked()


async def test_rapid_toggles_settle_on_the_last_state(enriched, live_server, new_page) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await _open(page, base, scan_id)
    await _open_menu(page)
    for value in ("A", "AA", "BP", "AA"):
        await _box(page, "Level", value).click()
    await page.wait_for_url(re.compile(r"conformance=A%2CBP|conformance=A,BP"))
    await pw.expect(_box(page, "Level", "AA")).not_to_be_checked()
    await pw.expect(_box(page, "Level", "A")).to_be_checked()
    await pw.expect(_box(page, "Level", "BP")).to_be_checked()
    await _assert_matches_api(page, base, scan_id)


async def test_mobile_width_rows_still_one_target_tall(enriched, live_server, new_page) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 375, "height": 812})
    await _open(page, base, scan_id)
    await _open_menu(page)
    rows = page.locator("fieldset label")
    for i in range(await rows.count()):
        box = await rows.nth(i).bounding_box()
        assert box and box["height"] >= 44 and box["x"] >= 0 and box["x"] + box["width"] <= 375, (
            i,
            box,
        )
    await _box(page, "Found by", "alt_text").locator("xpath=ancestor::label[1]").click()
    await page.wait_for_url(re.compile(r"finding_type=alt_text"))
    await _assert_matches_api(page, base, scan_id)
