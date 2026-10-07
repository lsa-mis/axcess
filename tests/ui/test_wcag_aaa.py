"""WCAG 2.2 AAA checks on the review app, and the A and AA problems the AAA audit found.

docs/internal/wcag-aaa-audit-2026-10.md audited the app with axe, Siteimprove
Alfa and scripted checks. axe already runs on the main screens
(test_accessibility_axe.py), but it does not check most of what the audit
found: 44 px targets (SC 2.5.5), one link name with two destinations (SC
2.4.9), line length and paragraph line height (SC 1.4.8), focus under the
sticky top bar (SC 2.4.11 and 2.4.12), focus inside the saved copy (SC
2.4.7), dropdowns named only by a <label> (SC 4.1.2), and the Rule check
views' impact chips (SC 1.4.3), which no axe test reached. These tests pin
each fix on a report seeded with rule check results, so none comes back.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

from ._inspector_case import seed
from .test_accessibility_axe import _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

# The first page's saved copy: two "copy link" buttons under two headings,
# so two occurrences share their locator's last step.
CAPTURE = (
    "<!doctype html><html><head><title>AAA fixture</title></head><body>"
    "<main><h2 id='intro'>Intro <a class='copy-link-btn' href='#intro'>#</a></h2>"
    "<h2 id='usage'>Usage <a class='copy-link-btn' href='#usage'>#</a></h2>"
    "<p>Some text.</p></main></body></html>"
)
RULE = "aria-valid-attr"


@pytest.fixture
def report(seeded_db: tuple[Path, Path, int]) -> tuple[int, int]:
    """The seeded report with rule check results; returns (scan id, first page id)."""
    db_path, _, scan_id = seeded_db
    page_id = seed(
        db_path,
        scan_id,
        CAPTURE,
        RULE,
        [
            ("#intro > .copy-link-btn", '<a class="copy-link-btn" href="#intro">#</a>'),
            ("#usage > .copy-link-btn", '<a class="copy-link-btn" href="#usage">#</a>'),
        ],
    )
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Every rule check row gets an "About this rule" address, and one
        # critical rule joins the serious one, on both pages.
        conn.execute(
            "UPDATE page_a11y_findings "
            "SET help_url = 'https://dequeuniversity.com/rules/axe/' || rule_id "
            "WHERE scan_id = ?",
            (scan_id,),
        )
        pages = [
            r["id"] for r in conn.execute("SELECT id FROM pages WHERE scan_id = ?", (scan_id,))
        ]
        for page in pages:
            conn.execute(
                "INSERT INTO page_a11y_findings (page_id, scan_id, pipeline, rule_id, wcag_sc, "
                "wcag_level, impact, help, help_url, target_selector, html_snippet, target_hash) "
                "VALUES (?, ?, 'axe', 'button-name', '4.1.2', 'A', 'critical', "
                "'Buttons must have discernible text', "
                "'https://dequeuniversity.com/rules/axe/button-name', '#menu', "
                "'<button></button>', ?)",
                (page, scan_id, f"aaa-button-{page}"),
            )
        # The Rule check views show their rows only for a scan that ran axe.
        conn.execute("UPDATE scans SET axe_pages_scanned = ? WHERE id = ?", (len(pages), scan_id))
        conn.commit()
    finally:
        conn.close()
    return scan_id, page_id


def _screens(scan_id: int, page_id: int) -> list[str]:
    return [
        "/scans",
        "/scans/new",
        f"/scans/{scan_id}",
        f"/scans/{scan_id}/issues",
        f"/scans/{scan_id}/issues/axe:{RULE}/pages",
        f"/scans/{scan_id}/pages/{page_id}",
        f"/scans/{scan_id}/pages/{page_id}/inspect?issue=axe:{RULE}",
        f"/scans/{scan_id}/findings",
        f"/scans/{scan_id}/a11y",
        f"/scans/{scan_id}/a11y/by-rule",
        "/tracking",
        "/settings",
        "/about",
    ]


async def _open(new_page: Any, base: str, path: str, **options: Any) -> Any:
    page = await new_page(viewport={"width": 1280, "height": 720}, **options)
    await page.goto(f"{base}/app{path}", wait_until="networkidle")
    return page


# Interactive targets smaller than 44 by 44 px, as the audit measured them.
# Exempt, as SC 2.5.5 allows: a link inside a sentence. Measured as the real
# target: a radio hidden inside its label (the label is the target), and a
# link stretched over its card by an absolute ::after (the card is the
# target). The skip link is 1 px until it has focus.
_SMALL_TARGETS = """() => {
  const out = [];
  const shown = (e) => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'
      && !e.closest('[hidden],[aria-hidden=true]');
  };
  const controls = 'a[href], button, [role=tab], input:not([type=hidden]), select, summary';
  for (const el of document.querySelectorAll(controls)) {
    if (!shown(el) || el.classList.contains('sr-only-focusable')) continue;
    let box = el;
    const hiddenInput = el.tagName === 'INPUT' && getComputedStyle(el).opacity === '0';
    if (hiddenInput && el.closest('label')) box = el.closest('label');
    if (getComputedStyle(el, '::after').position === 'absolute') {
      let p = el.parentElement;
      while (p && getComputedStyle(p).position === 'static') p = p.parentElement;
      if (p) box = p;
    }
    const r = box.getBoundingClientRect();
    if (r.width >= 43.5 && r.height >= 43.5) continue;
    const block = el.closest('p');
    const inSentence = el.tagName === 'A' && block
      && block.innerText.trim().length > el.innerText.trim().length + 15;
    if (inSentence) continue;
    const name = (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 40);
    const size = `${Math.round(r.width)}x${Math.round(r.height)}`;
    out.push(`${el.tagName.toLowerCase()} "${name}" ${size}`);
  }
  return out;
}"""

# Link names, as screen readers hear them, that lead to more than one place.
_SHARED_NAMES = """() => {
  const names = {};
  for (const a of document.querySelectorAll('a[href]')) {
    const r = a.getBoundingClientRect();
    if (!r.width || a.closest('[hidden]')) continue;
    const name = (a.getAttribute('aria-label') || a.textContent).replace(/\\s+/g, ' ').trim();
    const url = new URL(a.href, location.href);
    (names[name] ||= new Set()).add(url.pathname + url.search);
  }
  return Object.entries(names)
    .filter(([, to]) => to.size > 1)
    .map(([n, to]) => `${n} (${to.size})`);
}"""

# Running text: lines over 80 characters, and line height under 1.5.
_TEXT_LAYOUT = """() => {
  const long = [], tight = [];
  for (const p of document.querySelectorAll('main p, main li, main dd')) {
    const r = p.getBoundingClientRect();
    if (!r.width || p.closest('table, nav, [role=img]')) continue;
    const cs = getComputedStyle(p); const size = parseFloat(cs.fontSize);
    const lh = cs.lineHeight === 'normal' ? size * 1.2 : parseFloat(cs.lineHeight);
    const text = p.innerText.replace(/\\s+/g, ' ').trim();
    const lines = Math.round(r.height / lh);
    const start = text.slice(0, 40);
    const perLine = text.length / lines;
    if (lines >= 2 && perLine > 80) long.push(`${Math.round(perLine)}: ${start}`);
    if (text.length > 40 && lh / size < 1.5) tight.push(`${(lh / size).toFixed(2)}: ${start}`);
  }
  return {long, tight};
}"""


async def test_every_control_is_at_least_44_px(
    live_server: tuple[str, int], new_page: Any, report: tuple[int, int]
) -> None:
    """SC 2.5.5 Target Size (Enhanced), Level AAA, on every main screen."""
    base, _ = live_server
    small = []
    for path in _screens(*report):
        page = await _open(new_page, base, path)
        small += [f"{path}: {t}" for t in await page.evaluate(_SMALL_TARGETS)]
        await page.context.close()
    assert not small, "\n".join(small)


async def test_each_link_name_leads_to_one_place(
    live_server: tuple[str, int], new_page: Any, report: tuple[int, int]
) -> None:
    """SC 2.4.9 Link Purpose (Link Only), Level AAA: "Open the image", "About
    this rule", "Open live page" and page titles name where they go by
    themselves, including two occurrences whose locators share a last step."""
    base, _ = live_server
    shared = []
    for path in _screens(*report):
        page = await _open(new_page, base, path)
        shared += [f"{path}: {n}" for n in await page.evaluate(_SHARED_NAMES)]
        await page.context.close()
    assert not shared, "\n".join(shared)


async def test_running_text_is_short_and_spaced(
    live_server: tuple[str, int], new_page: Any, report: tuple[int, int]
) -> None:
    """SC 1.4.8 Visual Presentation, Level AAA: lines of 80 characters or
    fewer, and line height of at least 1.5 within paragraphs."""
    base, _ = live_server
    problems = []
    for path in _screens(*report):
        page = await _open(new_page, base, path)
        found = await page.evaluate(_TEXT_LAYOUT)
        problems += [f"{path}: long {t}" for t in found["long"]]
        problems += [f"{path}: tight {t}" for t in found["tight"]]
        await page.context.close()
    assert not problems, "\n".join(problems)


# Elements held to a reading width that also draw a band or a box: the cap
# cuts the band short, as a blanket cap on every p, li and dd once did.
_CAPPED_BANDS = """() => [...document.querySelectorAll('main *')].filter((el) => {
  const cs = getComputedStyle(el);
  if (cs.maxWidth === 'none' || !el.getBoundingClientRect().width) return false;
  const filled = cs.backgroundColor !== 'rgba(0, 0, 0, 0)';
  const edged = ['Top', 'Bottom'].some((s) => parseFloat(cs[`border${s}Width`]) > 0);
  const parent = el.parentElement.getBoundingClientRect().width;
  return (filled || edged) && el.getBoundingClientRect().width < parent - 40
    && /^(P|LI|DD)$/.test(el.tagName);
}).map((el) => el.textContent.trim().slice(0, 40))"""


async def test_reading_width_never_cuts_a_band_short(
    live_server: tuple[str, int], new_page: Any, report: tuple[int, int]
) -> None:
    """The reading width (SC 1.4.8) sits on the text, not on a band or box
    around it, and the values in the Inspector's facts about the flagged
    element (such as its element locator) get the row's width."""
    base, _ = live_server
    scan_id, page_id = report
    cut = []
    for path in _screens(scan_id, page_id):
        page = await _open(new_page, base, path)
        cut += [f"{path}: {t}" for t in await page.evaluate(_CAPPED_BANDS)]
        await page.context.close()
    assert not cut, "\n".join(cut)
    page = await _open(new_page, base, f"/scans/{scan_id}/pages/{page_id}/inspect?issue=axe:{RULE}")
    await page.locator("main dl dd").first.wait_for()
    shares = await page.evaluate(
        """() => [...document.querySelectorAll('main dl dd')].map(
          (dd) => dd.getBoundingClientRect().width / dd.closest('dl').getBoundingClientRect().width
        )"""
    )
    assert shares and min(shares) > 0.6, shares
    await page.context.close()


async def test_page_link_icon_sits_beside_its_first_line(
    live_server: tuple[str, int], new_page: Any, report: tuple[int, int]
) -> None:
    """The eye icon on a page title link lines up with the title's first
    line, on one line or wrapped, while the link stays 44 px tall."""
    base, _ = live_server
    scan_id, _page = report
    page = await _open(new_page, base, f"/scans/{scan_id}/issues/axe:{RULE}/pages")
    offsets = await page.evaluate(
        """() => [...document.querySelectorAll('main a:has(> svg.lucide-scan-eye)')].map((a) => {
          const icon = a.querySelector('svg').getBoundingClientRect();
          const range = document.createRange();
          range.selectNodeContents(a.querySelector('svg + span'));
          const line = range.getClientRects()[0];
          const middle = (r) => r.top + r.height / 2;
          return [Math.abs(middle(icon) - middle(line)), a.getBoundingClientRect().height];
        })"""
    )
    assert offsets
    for offset, height in offsets:
        assert offset <= 4, offsets
        assert height >= 43.5, offsets
    await page.context.close()


async def test_focus_is_never_under_the_top_bar(
    live_server: tuple[str, int], new_page: Any, report: tuple[int, int]
) -> None:
    """SC 2.4.11 and 2.4.12 Focus Not Obscured: tabbing through each screen
    at 1280 by 720 never leaves the focused element under the sticky bar."""
    base, _ = live_server
    covered = []
    for path in _screens(*report):
        page = await _open(new_page, base, path)
        for _ in range(60):
            await page.keyboard.press("Tab")
            hit = await page.evaluate(
                """() => {
                  const el = document.activeElement;
                  if (!el || el === document.body || el.tagName === 'IFRAME') return null;
                  const r = el.getBoundingClientRect();
                  if (r.bottom <= 0 || r.top >= innerHeight) return null;
                  const x = Math.min(innerWidth - 1, Math.max(0, r.left + r.width / 2));
                  const top = document.elementFromPoint(x, Math.max(0, r.top + 1));
                  const bar = top && top.closest('header.sticky, [data-sticky-crumb]');
                  if (!bar || bar.contains(el)) return null;
                  return (el.innerText || el.tagName).trim().slice(0, 40);
                }"""
            )
            if hit:
                covered.append(f"{path}: {hit}")
        await page.context.close()
    assert not covered, "\n".join(sorted(set(covered)))


async def test_focus_inside_the_saved_copy_shows_a_ring(
    live_server: tuple[str, int], new_page: Any, report: tuple[int, int]
) -> None:
    """SC 2.4.7 Focus Visible, Level AA: tabbing into the Inspector's saved
    copy draws the app's ring on its frame, and tabbing out removes it."""
    base, _ = live_server
    scan_id, page_id = report
    page = await _open(new_page, base, f"/scans/{scan_id}/pages/{page_id}/inspect?issue=axe:{RULE}")
    frame = page.locator('iframe[title^="Saved copy"]')
    for _ in range(80):
        await page.keyboard.press("Tab")
        if await page.evaluate("document.activeElement.tagName") == "IFRAME":
            break
    else:
        pytest.fail("Tabbing never reached the saved copy")
    width = await frame.evaluate(
        "(f) => { const cs = getComputedStyle(f);"
        " return cs.outlineStyle === 'none' ? 0 : parseFloat(cs.outlineWidth); }"
    )
    assert width >= 2, width
    await page.keyboard.press("Shift+Tab")
    assert await frame.evaluate("(f) => getComputedStyle(f).outlineStyle") == "none"
    await page.context.close()


async def test_every_dropdown_is_named(
    live_server: tuple[str, int], new_page: Any, report: tuple[int, int]
) -> None:
    """SC 4.1.2 Name, Role, Value, Level A: every dropdown (a button with
    role="combobox") is named by aria-labelledby, not by a <label> alone,
    which Siteimprove Alfa did not count as its name."""
    base, _ = live_server
    scan_id, page_id = report
    for path in (
        f"/scans/{scan_id}/pages/{page_id}/inspect?issue=axe:{RULE}",
        "/scans/new",
        "/tracking",
    ):
        page = await _open(new_page, base, path)
        boxes = page.get_by_role("combobox")
        for i in range(await boxes.count()):
            box = boxes.nth(i)
            if not await box.is_visible():
                continue
            label = await box.evaluate(
                "(b) => (document.getElementById(b.getAttribute('aria-labelledby') || '')"
                "?.textContent || '').trim()"
            )
            assert label, f"{path}: dropdown {i} has no aria-labelledby name"
            await playwright_async.expect(box).to_have_accessible_name(re.compile(re.escape(label)))
        await page.context.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
async def test_impact_chips_are_readable_and_in_plain_words(
    live_server: tuple[str, int], new_page: Any, report: tuple[int, int], scheme: str
) -> None:
    """SC 1.4.3 Contrast (Minimum), Level AA: the impact chips were white on
    their pale colours (1.16:1). Now dark on pale, in the glossary's words
    (Critical, Serious), not axe's raw values."""
    base, _ = live_server
    scan_id, _page = report
    for path in (f"/scans/{scan_id}/a11y", f"/scans/{scan_id}/a11y/by-rule"):
        page = await _open(new_page, base, path, color_scheme=scheme)
        await playwright_async.expect(page.get_by_text("Serious", exact=True).first).to_be_visible()
        await playwright_async.expect(
            page.get_by_text("Critical", exact=True).first
        ).to_be_visible()
        assert await page.get_by_text("serious", exact=True).count() == 0
        violations = [v for v in await _run_axe(page) if v["id"].startswith("color-contrast")]
        assert not violations, (path, violations)
        await page.context.close()


async def test_not_found_has_a_level_one_heading(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """Every page has one level 1 heading, Not found included."""
    base, _ = live_server
    page = await _open(new_page, base, "/no-such-page")
    await playwright_async.expect(
        page.get_by_role("heading", level=1, name="Page not found")
    ).to_be_visible()
    await page.context.close()


async def test_header_separators_are_drawn_not_typed(
    live_server: tuple[str, int], new_page: Any, report: tuple[int, int]
) -> None:
    """The report header's separator is a drawn line, not a light "|"
    character that contrast checks read as text (Alfa found it at 1.68:1)."""
    base, _ = live_server
    scan_id, page_id = report
    page = await _open(new_page, base, f"/scans/{scan_id}/pages/{page_id}")
    typed = await page.evaluate(
        "() => [...document.querySelectorAll('main header span')]"
        ".filter(s => /^[|·]$/.test(s.textContent.trim())).length"
    )
    assert typed == 0
    await page.context.close()
