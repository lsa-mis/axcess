"""Integration tests for the live-page focus probe (SC 2.4.11, SC 2.4.3).

Real Playwright against hand-built fixtures in
``tests/fixtures/site/focus/``:

  * ``clean.html``    — no sticky/fixed overlay → zero findings (FP guard).
  * ``obscured.html`` — a link under a position:fixed header → exactly one
    ``focus-not-obscured`` finding on that link, and NOT on the visible one.
  * ``sticky_bar_links.html`` — a sticky bar and no scroll padding: links
    that Shift+Tab really lands behind the bar. The expected answer comes
    from pressing the real keys in the test.
  * ``sticky_bar_links_scroll_padding.html`` — the same page, fixed.
  * ``bar_changes_on_scroll.html`` — a bar that is clear at the top of the
    page and solid once the page scrolls. The check has to let the page's
    own code run before it looks, as happens between two real key presses.
  * ``sticky_bar_tall_cards.html`` — a real page's layout that the check
    once reported in error: nothing is hidden when focus arrives.
  * ``partly_obscured.html``, ``see_through_bar.html`` — covered in part,
    hidden by its own CSS, or under a bar you can see through: none of
    these is "entirely hidden" by the bar, so none is SC 2.4.11.

SC 2.4.11 Focus Not Obscured (Minimum), Level AA, normative text: "When a
user interface component receives keyboard focus, the component is not
entirely hidden due to author-created content." The tests hold the check to
both halves: the moment focus arrives, and entirely hidden.

Skipped when Playwright / chromium aren't installed; uses ``file://`` URLs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from audit.analyzer.focus import FocusProbe
from audit.analyzer.focus.base import RULE_FOCUS_OBSCURED, RULE_POSITIVE_TABINDEX

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "focus"


def _file_url(name: str) -> str:
    return (FIXTURE_DIR / name).resolve().as_uri()


playwright = pytest.importorskip("playwright.async_api")

# One browser per module (tests/integration/conftest.py), so the tests run on
# the module's event loop. Each still gets its own context from ``page``.
pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


async def _obscured(page) -> list[Any]:  # type: ignore[no-untyped-def]
    """The SC 2.4.11 findings only."""
    return [f for f in await FocusProbe().run(page) if f.rule_id == RULE_FOCUS_OBSCURED]


async def _leave_scrolled(page, where: str) -> None:  # type: ignore[no-untyped-def]
    """Leave the page where an earlier check might have: top, middle, bottom.

    ``instant`` because some fixtures scroll smoothly, and a scroll still in
    flight is not the state under test. It then waits, as time passes
    between two checks in a scan: two frames for the page's own scroll code,
    and the end of any fade that code started.
    """
    await page.evaluate(
        """async (where) => {
          const max = document.documentElement.scrollHeight - window.innerHeight;
          const top = { top: 0, middle: Math.round(max / 2), bottom: max }[where];
          window.scrollTo({ left: 0, top: top, behavior: 'instant' });
          await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
          await Promise.all(document.getAnimations().map((a) => a.finished));
        }""",
        where,
    )


# What the real keyboard did to the focused element, read from the page.
_FOCUSED_GEOMETRY_JS = """
() => {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  const r = el.getBoundingClientRect();
  const bar = document.getElementById('bar');
  return {
    id: el.id,
    inBar: bar.contains(el),
    top: r.top,
    middle: r.top + r.height / 2,
    bottom: r.bottom,
    barBottom: bar.getBoundingClientRect().bottom,
  };
}
"""


async def _walk_with_real_keys(page, key: str, presses: int) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    """Press ``key`` and record where each focused element ended up."""
    seen: list[dict[str, Any]] = []
    for _ in range(presses):
        await page.keyboard.press(key)
        geometry = await page.evaluate(_FOCUSED_GEOMETRY_JS)
        if geometry and not geometry["inBar"]:
            seen.append(geometry)
    return seen


async def test_clean_page_has_no_findings(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("clean.html"))
    findings = await FocusProbe().run(page)
    assert findings == [], "Expected zero findings on the clean fixture, got: " + ", ".join(
        f.target_selector for f in findings
    )


async def test_detects_element_under_fixed_header(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("obscured.html"))
    findings = await FocusProbe().run(page)
    # Exactly the hidden link is flagged; the visible one is not.
    selectors = {f.target_selector for f in findings}
    assert "a#hidden-link" in selectors, f"hidden link not flagged; got {selectors}"
    assert "a#visible-link" not in selectors, "visible link wrongly flagged"
    flagged = next(f for f in findings if f.target_selector == "a#hidden-link")
    assert flagged.rule_id == RULE_FOCUS_OBSCURED
    assert flagged.criterion_sc == "2.4.11"
    assert flagged.to_repo_kwargs()["pipeline"] == "focus"
    # The stored words say what was measured: all of it hidden, by which
    # element, and how to see it again. Never the old "centre is covered".
    assert flagged.failure_summary.startswith("All of this element is hidden")
    assert "<header>" in flagged.failure_summary
    assert "centre" not in flagged.failure_summary


# --------------------------------------------------------------------
# True positive: hidden behind a sticky bar when focus really arrives.
# --------------------------------------------------------------------


async def test_reports_the_links_real_shift_tab_lands_behind_the_bar(page) -> None:  # type: ignore[no-untyped-def]
    """The check's answer equals what the real keys do, link for link.

    The expected set is not written down here. The test presses Shift+Tab
    through the page and reads which links end up wholly behind the bar,
    then asks the check, which must name the same links and no others.
    """
    url = _file_url("sticky_bar_links.html")
    await page.goto(url)
    link_count = await page.evaluate("document.querySelectorAll('a.row').length")

    backward = await _walk_with_real_keys(page, "Shift+Tab", link_count + 1)
    assert {g["id"] for g in backward} == {f"link-{i:02d}" for i in range(link_count)}
    entirely_hidden = {g["id"] for g in backward if g["bottom"] <= g["barBottom"]}
    partly_hidden_centre_covered = {
        g["id"] for g in backward if g["middle"] < g["barBottom"] < g["bottom"]
    }
    # The fixture must really contain both cases, or the test proves nothing.
    assert entirely_hidden, "fixture has no link wholly behind the bar on Shift+Tab"
    assert partly_hidden_centre_covered, "fixture has no partly hidden link"

    await page.goto(url)
    forward = await _walk_with_real_keys(page, "Tab", link_count + 1)
    assert not [g["id"] for g in forward if g["bottom"] <= g["barBottom"]], (
        "nothing stays in place at the bottom of this page, so Tab hides nothing"
    )

    await page.goto(url)
    findings = await _obscured(page)
    reported = {f.target_selector for f in findings}
    assert reported == {f"a#{link_id}" for link_id in entirely_hidden}
    # A link with its centre covered but an edge showing is not "entirely
    # hidden". It must not be filed under SC 2.4.11.
    assert not reported & {f"a#{link_id}" for link_id in partly_hidden_centre_covered}
    for finding in findings:
        assert finding.criterion_sc == "2.4.11"
        assert finding.wcag_level == "AA"
        # Only the walk that found it is named, so a reviewer can repeat it.
        assert "backward through the page, as Shift+Tab does" in finding.failure_summary
        assert "press Shift+Tab on the live page" in finding.failure_summary


# The focused element after the page has reacted to the key press: two frames
# for its scroll handler, then the end of the bar's fade. Read from the page
# with no help from the check under test.
_FOCUSED_AFTER_PAGE_REACTS_JS = """
async () => {
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const bar = document.getElementById('bar');
  await Promise.all(bar.getAnimations().map((a) => a.finished));
  const el = document.activeElement;
  if (!el || el === document.body || bar.contains(el)) return null;
  const r = el.getBoundingClientRect();
  const colour = getComputedStyle(bar).backgroundColor;
  return {
    id: el.id,
    behindBar: r.bottom <= bar.getBoundingClientRect().bottom,
    barIsSolid: colour === 'rgb(0, 63, 117)',
    barIsClear: colour === 'rgba(0, 63, 117, 0)',
  };
}
"""


@pytest.mark.parametrize("left_at", ["top", "bottom"])
async def test_bar_that_changes_on_scroll_is_judged_as_the_keyboard_user_sees_it(  # type: ignore[no-untyped-def]
    page, left_at: str
) -> None:
    """A bar that is clear at the top and solid further down the page.

    The page's script changes the bar when the page scrolls. A check that
    looks before that script has run sees the bar as it was when the check
    began: begun at the top it misses every hidden link, begun on a scrolled
    page it reports a link that sits under the clear bar. The expected
    answer comes from pressing the real keys.
    """
    url = _file_url("bar_changes_on_scroll.html")
    await page.goto(url)
    stops = await page.evaluate("document.querySelectorAll('a').length")
    assert stops > 0

    seen: list[dict[str, Any]] = []
    for key in ("Tab", "Shift+Tab"):
        await page.goto(url)
        for _ in range(stops):
            await page.keyboard.press(key)
            state = await page.evaluate(_FOCUSED_AFTER_PAGE_REACTS_JS)
            if state:
                seen.append(state)
    assert all(s["barIsSolid"] or s["barIsClear"] for s in seen), "bar read part-way through a fade"
    hidden = {s["id"] for s in seen if s["behindBar"] and s["barIsSolid"]}
    under_the_clear_bar = {s["id"] for s in seen if s["behindBar"] and s["barIsClear"]}
    # The fixture must hold both cases, or the test proves nothing.
    assert hidden, "no link lands behind the solid bar"
    assert under_the_clear_bar == {"hero-link"}

    await page.goto(url)
    await _leave_scrolled(page, left_at)
    bar_is_solid = await page.evaluate(
        "getComputedStyle(document.getElementById('bar')).backgroundColor === 'rgb(0, 63, 117)'"
    )
    assert bar_is_solid == (left_at == "bottom"), "the bar is not in the state for this place"
    reported = {f.target_selector for f in await _obscured(page)}
    assert reported == {f"a#{link_id}" for link_id in hidden}
    assert "a#hero-link" not in reported, "visible through the clear bar, but reported"


async def test_smooth_scrolling_does_not_change_the_answer(page) -> None:  # type: ignore[no-untyped-def]
    """A page that scrolls smoothly is judged after the scroll, not during it."""
    url = _file_url("sticky_bar_links.html")
    await page.goto(url)
    plain = {f.target_selector for f in await _obscured(page)}
    assert plain

    await page.goto(url)
    await page.add_style_tag(content="html { scroll-behavior: smooth; }")
    smooth = {f.target_selector for f in await _obscured(page)}
    assert smooth == plain
    # The check turned smooth scrolling off only while it looked.
    assert await page.evaluate(
        "[getComputedStyle(document.documentElement).scrollBehavior,"
        " document.documentElement.getAttribute('style')]"
    ) == ["smooth", None]


# --------------------------------------------------------------------
# False-positive guards.
# --------------------------------------------------------------------


async def test_card_left_under_the_bar_by_an_earlier_check_is_not_reported(page) -> None:  # type: ignore[no-untyped-def]
    """The reported-in-error case: a tall card on a page left scrolled down.

    The page is left at the bottom, where a card's centre is under the bar.
    A keyboard user never meets the card like that: when focus arrives the
    browser scrolls it clear, because the page sets scroll-padding-top.
    """
    await page.goto(_file_url("sticky_bar_tall_cards.html"))
    await _leave_scrolled(page, "bottom")
    centre_is_under_the_bar = await page.evaluate(
        """() => {
          const card = document.querySelectorAll('a.block')[12];
          const r = card.getBoundingClientRect();
          const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return !!hit && !!hit.closest('nav');
        }"""
    )
    assert centre_is_under_the_bar, "fixture no longer leaves a card's centre under the bar"

    findings = await _obscured(page)
    assert findings == [], "reported a card that is clear of the bar when focused: " + ", ".join(
        f.target_selector for f in findings
    )


@pytest.mark.parametrize(
    "fixture",
    [
        "sticky_bar_tall_cards.html",
        "sticky_bar_links.html",
        "sticky_bar_links_scroll_padding.html",
        "bar_changes_on_scroll.html",
        "obscured.html",
    ],
)
async def test_answer_does_not_depend_on_where_the_page_was_left(page, fixture: str) -> None:  # type: ignore[no-untyped-def]
    """Top, middle or bottom: the same page gives the same findings."""
    answers = {}
    for where in ("top", "middle", "bottom"):
        await page.goto(_file_url(fixture))
        await _leave_scrolled(page, where)
        answers[where] = sorted(f.target_selector for f in await _obscured(page))
    assert answers["top"] == answers["middle"] == answers["bottom"], answers


async def test_fixed_page_with_scroll_padding_is_clean(page) -> None:  # type: ignore[no-untyped-def]
    """scroll-padding-top is the fix; with it nothing is hidden on focus."""
    await page.goto(_file_url("sticky_bar_links_scroll_padding.html"))
    assert await _obscured(page) == []


async def test_partly_hidden_and_hidden_on_purpose_are_not_reported(page) -> None:  # type: ignore[no-untyped-def]
    """Centre covered but an edge showing, and a visually hidden link."""
    await page.goto(_file_url("partly_obscured.html"))
    centre_is_under_the_bar = await page.evaluate(
        """() => {
          const r = document.getElementById('partly-hidden').getBoundingClientRect();
          const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return !!hit && hit.tagName === 'HEADER' && r.bottom > 120;
        }"""
    )
    assert centre_is_under_the_bar, "fixture no longer covers the link's centre"
    findings = await _obscured(page)
    assert findings == [], "not entirely hidden by the bar, but reported: " + ", ".join(
        f.target_selector for f in findings
    )


async def test_see_through_bar_is_not_reported(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("see_through_bar.html"))
    assert await _obscured(page) == []


async def test_probe_leaves_scroll_and_focus_as_it_found_them(page) -> None:  # type: ignore[no-untyped-def]
    """Later checks get the page this check was given."""
    await page.goto(_file_url("sticky_bar_tall_cards.html"))
    await page.evaluate(
        """() => {
          window.scrollTo({ left: 0, top: 1000, behavior: 'instant' });
          document.getElementById('nav-work').focus({ preventScroll: true });
        }"""
    )
    await FocusProbe().run(page)
    state = await page.evaluate(
        "[window.scrollX, window.scrollY, document.activeElement.id,"
        " getComputedStyle(document.documentElement).scrollBehavior,"
        " document.documentElement.getAttribute('style')]"
    )
    assert state == [0, 1000, "nav-work", "smooth", None]


async def test_flags_positive_tabindex_only(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("tabindex.html"))
    findings = await FocusProbe().run(page)
    ti = [f for f in findings if f.rule_id == RULE_POSITIVE_TABINDEX]
    selectors = {f.target_selector for f in ti}
    # Only tabindex="3" is flagged; tabindex 0 / -1 / no-tabindex are fine.
    assert selectors == {"input#jumps-first"}, f"got {selectors}"
    f0 = ti[0]
    assert f0.criterion_sc == "2.4.3"
    assert f0.wcag_level == "A"
    assert "focus-order" in f0.help_url
    assert f0.to_repo_kwargs()["pipeline"] == "focus"
