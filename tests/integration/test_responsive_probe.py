"""Integration tests for the responsive/zoom/text-spacing probe.

Real Playwright against hand-built fixtures in
``tests/fixtures/site/responsive/``, in two classes:

  * Negative (must produce zero findings):
    - ``clean.html`` — the false-positive guard for all three checks.
    - ``sr_only_status.html`` — text hidden from sight on purpose (the
      ``.sr-only`` pattern and its relatives). It paints no pixel, so there
      is nothing to cut off.
    - ``always_clipped.html`` — visible text cut off at every size. Zoom
      and spacing do not cause it, so it is not their finding.
    - ``zoom_clipped_then_removed.html`` — a message that is gone before
      the comparison can be made.
  * Positive (each fires exactly its named check):
    - ``reflow_overflow.html``  → ``responsive-reflow-overflow``  (SC 1.4.10)
    - ``zoom_clipped.html``     → ``responsive-text-clipped``      (SC 1.4.4)
    - ``zoom_clipped_among_hidden.html`` → ``responsive-text-clipped``, on
      the two visible elements only, with hidden text first in the page.
    - ``spacing_clipped.html``  → ``responsive-text-spacing-clipped`` (SC 1.4.12)
    - ``skip_link_clipped.html`` → a skip link still clipped while focused

Isolation matters as much as detection: each positive fixture is built
so the OTHER two checks stay quiet on it (see the geometry notes in the
fixture files). A probe that fires three rules on one defect would
triple the triage load.

Same gating as the keyboard-probe tests: skipped when Playwright /
chromium aren't installed; ``file://`` URLs instead of a fixture server.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from audit.analyzer.responsive import ResponsiveProbe
from audit.analyzer.responsive.base import (
    RULE_REFLOW,
    RULE_SPACING_CLIPPED,
    RULE_TEXT_CLIPPED,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "responsive"


def _file_url(name: str) -> str:
    return (FIXTURE_DIR / name).resolve().as_uri()


playwright = pytest.importorskip("playwright.async_api")

# One browser per module (tests/integration/conftest.py), so the tests run on
# the module's event loop. Each still gets its own context from ``page``.
pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    # Match the crawler's standard viewport so the probe's restore step
    # and the fixtures' vw-based geometry behave exactly as production.
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


# --------------------------------------------------------------------
# Negative case — the false-positive guard.
# --------------------------------------------------------------------


async def test_clean_page_has_no_findings(page) -> None:  # type: ignore[no-untyped-def]
    """A fluid page must produce zero findings from all three checks."""
    await page.goto(_file_url("clean.html"))
    findings = await ResponsiveProbe().run(page)
    assert findings == [], "Expected zero findings on the clean fixture, got: " + ", ".join(
        f"{f.rule_id} on {f.target_selector}" for f in findings
    )


async def test_probe_restores_viewport(page) -> None:  # type: ignore[no-untyped-def]
    """The probe must leave the page at the crawl's standard viewport."""
    await page.goto(_file_url("clean.html"))
    await ResponsiveProbe().run(page)
    size = page.viewport_size
    assert size == {"width": 1440, "height": 900}, f"viewport left at {size}"


async def test_text_hidden_on_purpose_is_not_reported(page) -> None:  # type: ignore[no-untyped-def]
    """Screen-reader-only text is not "clipped": none of it is ever painted.

    The reported-in-error case was ``div.sr-only`` with ``role="status"``,
    stored as "content 262px in a 1px box". The fixture has that element,
    the ``clip-path: inset(50%)`` variant, an off-screen 1px box, a closed
    panel and text at ``opacity: 0``.
    """
    await page.goto(_file_url("sr_only_status.html"))
    # The fixture must still hold what the old check tripped on.
    box = await page.evaluate(
        """() => {
          const el = document.querySelector('div.sr-only[role=status]');
          return [el.clientWidth, el.scrollWidth > el.clientWidth + 4];
        }"""
    )
    assert box == [1, True], f"fixture no longer has the 1px box with wider text: {box}"
    findings = await ResponsiveProbe().run(page)
    assert findings == [], "hidden text reported as cut off: " + ", ".join(
        f"{f.rule_id} on {f.target_selector}" for f in findings
    )


async def test_text_cut_off_at_every_size_is_not_a_zoom_or_spacing_finding(page) -> None:  # type: ignore[no-untyped-def]
    """Both checks compare with the normal condition before they report.

    SC 1.4.4 is about content lost by resizing and SC 1.4.12 about content
    lost by the spacing. A box that cuts its text off at 1440px exactly as
    it does at 640px, with or without the spacing, is neither.
    """
    await page.goto(_file_url("always_clipped.html"))
    cut_off_at_normal_size = await page.evaluate(
        """() => ['fixed-box', 'short-box'].map((id) => {
          const el = document.getElementById(id);
          return el.scrollWidth > el.clientWidth + 4 || el.scrollHeight > el.clientHeight + 4;
        })"""
    )
    assert cut_off_at_normal_size == [True, True], "fixture boxes no longer cut off their text"
    findings = await ResponsiveProbe().run(page)
    assert findings == [], "reported text that zoom and spacing did not cut off: " + ", ".join(
        f"{f.rule_id} on {f.target_selector}" for f in findings
    )


async def test_message_removed_before_the_comparison_is_not_reported(page) -> None:  # type: ignore[no-untyped-def]
    """An element that is gone cannot be compared, and must not break the run."""
    await page.goto(_file_url("zoom_clipped_then_removed.html"))
    findings = await ResponsiveProbe().run(page)
    assert await page.evaluate("document.getElementById('passing-message')") is None, (
        "fixture did not remove its message, so the test covered nothing"
    )
    assert findings == []


# --------------------------------------------------------------------
# Positive cases — one named rule each, others quiet.
# --------------------------------------------------------------------


async def test_detects_reflow_overflow_at_320(page) -> None:  # type: ignore[no-untyped-def]
    """A fixed 900px container → responsive-reflow-overflow, only."""
    await page.goto(_file_url("reflow_overflow.html"))
    findings = await ResponsiveProbe().run(page)
    rules = {f.rule_id for f in findings}
    assert RULE_REFLOW in rules, f"reflow not detected; got {rules}"
    # The offender should be named (the fixed-width div, not just html).
    reflow = [f for f in findings if f.rule_id == RULE_REFLOW]
    assert any("fixed-width" in f.target_selector for f in reflow), (
        "Expected div#fixed-width to be named as the offender; got "
        + str([f.target_selector for f in reflow])
    )
    # Check isolation: this fixture must not fire the clipping rules.
    assert RULE_TEXT_CLIPPED not in rules
    assert RULE_SPACING_CLIPPED not in rules
    # Every reflow finding carries the right SC for the Issues view.
    assert all(f.criterion_sc == "1.4.10" for f in reflow)


async def test_detects_text_clipping_at_zoom_proxy(page) -> None:  # type: ignore[no-untyped-def]
    """A vw-sized nowrap box that clips only at 640px → text-clipped, only."""
    await page.goto(_file_url("zoom_clipped.html"))
    findings = await ResponsiveProbe().run(page)
    rules = {f.rule_id for f in findings}
    assert RULE_TEXT_CLIPPED in rules, f"zoom clipping not detected; got {rules}"
    clipped = [f for f in findings if f.rule_id == RULE_TEXT_CLIPPED]
    assert any("vw-box" in f.target_selector for f in clipped), (
        "Expected p#vw-box to be named; got " + str([f.target_selector for f in clipped])
    )
    assert RULE_REFLOW not in rules
    assert RULE_SPACING_CLIPPED not in rules
    assert all(f.criterion_sc == "1.4.4" for f in clipped)


async def test_detects_real_clipping_on_a_page_with_hidden_text(page) -> None:  # type: ignore[no-untyped-def]
    """Visible text cut off at 640px is reported; hidden text beside it is not.

    Six pieces of screen-reader-only text come first in the page and the
    check reports at most five elements, so counting hidden text would
    crowd out both real problems.
    """
    await page.goto(_file_url("zoom_clipped_among_hidden.html"))
    findings = await ResponsiveProbe().run(page)
    assert {f.rule_id for f in findings} == {RULE_TEXT_CLIPPED}, [
        f"{f.rule_id} on {f.target_selector}" for f in findings
    ]
    # #vw-box loses the end of its line; #squeezed is squeezed to nothing
    # and loses all of it. Both show their text at the normal viewport.
    assert [f.target_selector for f in findings] == ["p#vw-box", "p#squeezed"]
    for finding in findings:
        assert finding.criterion_sc == "1.4.4"
        assert "clipped horizontally" in finding.failure_summary
        # The stored words carry the comparison that makes it a zoom finding.
        assert (
            "At the normal 1440px-wide viewport this element does not cut off its text"
            in finding.failure_summary
        )


async def test_detects_clipping_under_text_spacing_override(page) -> None:  # type: ignore[no-untyped-def]
    """A height-locked overflow-hidden box → spacing-clipped, only."""
    await page.goto(_file_url("spacing_clipped.html"))
    findings = await ResponsiveProbe().run(page)
    rules = {f.rule_id for f in findings}
    assert RULE_SPACING_CLIPPED in rules, f"spacing clip not detected; got {rules}"
    clipped = [f for f in findings if f.rule_id == RULE_SPACING_CLIPPED]
    assert any("tight-box" in f.target_selector for f in clipped), (
        "Expected p#tight-box to be named; got " + str([f.target_selector for f in clipped])
    )
    assert RULE_REFLOW not in rules
    assert RULE_TEXT_CLIPPED not in rules
    assert all(f.criterion_sc == "1.4.12" for f in clipped)
    assert all(
        "Without the override this element does not cut off its text" in f.failure_summary
        for f in clipped
    )
    # The override sheet is gone once the check is done.
    assert await page.evaluate("document.querySelectorAll('style').length") == 1


async def test_visually_hidden_text_is_not_clipping(page) -> None:  # type: ignore[no-untyped-def]
    """Screen-reader-only text (sr-only, clip-path) is clipped on purpose.

    A skip link that shows itself on focus, a hidden span inside a link, a
    hidden label and hidden text in a hidden container must all stay quiet.
    """
    await page.goto(_file_url("sr_only.html"))
    findings = await ResponsiveProbe().run(page)
    assert findings == [], "Visually hidden text was reported: " + ", ".join(
        f"{f.rule_id} on {f.target_selector}" for f in findings
    )


async def test_skip_link_clipped_while_focused_is_reported(page) -> None:  # type: ignore[no-untyped-def]
    """A skip link still cut off while it has focus is a real failure."""
    await page.goto(_file_url("skip_link_clipped.html"))
    findings = await ResponsiveProbe().run(page)
    clipped = [f for f in findings if f.rule_id == RULE_TEXT_CLIPPED]
    assert any("skip" in f.target_selector for f in clipped), (
        "Expected a#skip to be named; got " + str([f.target_selector for f in findings])
    )
    assert all("while it has keyboard focus" in f.failure_summary for f in clipped)
    # The probe hands focus back: nothing is left focused by the check.
    assert await page.evaluate("document.activeElement === document.body")


async def test_screenshots_are_taken_while_the_failure_holds(page) -> None:  # type: ignore[no-untyped-def]
    """Each picture shows the failure: at the narrow viewport, or with spacing on.

    The fetcher's general screenshot pass runs after the probe restores the
    page, when the clipped element shows whole, so the probe takes these.
    """
    taken: list[tuple[str, int, str]] = []

    async def shot(p, selector: str) -> bytes:  # type: ignore[no-untyped-def]
        size = p.viewport_size or {}
        line_height = await p.evaluate(
            "(s) => getComputedStyle(document.querySelector(s)).lineHeight", selector
        )
        taken.append((selector, int(size.get("width", 0)), line_height))
        return b"png:" + selector.encode()

    await page.goto(_file_url("zoom_clipped.html"))
    zoom = [
        f for f in await ResponsiveProbe().run(page, shot=shot) if f.rule_id == RULE_TEXT_CLIPPED
    ]
    assert zoom and all(f.screenshot == b"png:" + f.target_selector.encode() for f in zoom)
    assert {w for sel, w, _ in taken if "vw-box" in sel} == {640}

    taken.clear()
    await page.goto(_file_url("spacing_clipped.html"))
    spacing = [
        f for f in await ResponsiveProbe().run(page, shot=shot) if f.rule_id == RULE_SPACING_CLIPPED
    ]
    assert spacing and all(f.screenshot for f in spacing)
    # Taken with the spacing stylesheet applied (line-height 1.5 of 16px).
    assert all(lh == "24px" for sel, _, lh in taken if "tight-box" in sel), taken
    # The screenshot is evidence only: it is not written into the row.
    assert "screenshot" not in spacing[0].to_repo_kwargs()


# --------------------------------------------------------------------
# Persistence shape — findings flow into page_a11y_findings rows.
# --------------------------------------------------------------------


async def test_finding_repo_kwargs_shape(page) -> None:  # type: ignore[no-untyped-def]
    """to_repo_kwargs() carries the pipeline + SC the Issues view needs."""
    await page.goto(_file_url("reflow_overflow.html"))
    findings = await ResponsiveProbe().run(page)
    assert findings
    kwargs = findings[0].to_repo_kwargs()
    assert kwargs["pipeline"] == "responsive"
    assert kwargs["rule_id"].startswith("responsive-")
    assert kwargs["criterion_sc"] == kwargs["wcag_sc"] == "1.4.10"
    assert kwargs["wcag_level"] == "AA"
    assert kwargs["target_hash"]  # non-empty stable dedupe key
    assert "www.w3.org" in kwargs["help_url"]
