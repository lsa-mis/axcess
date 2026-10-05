"""Every button and link says, in its own words, what it does.

"Read more", "Download", "Cancel" or "Full details" on their own leave the
reader asking: read more about what, download which file, cancel what. The
visible words are what a sighted reader scans, what a voice-control user
says to press the control, and what a screen reader announces first, so they
have to carry the meaning themselves.

The words checked are the control's own text: what it shows, plus any
screen-reader-only text inside it (WCAG technique C7, "Using CSS to hide a
portion of the link text"), because that is real HTML text that travels with
the control. An `aria-label` is never counted: the first rule of ARIA is to
prefer native HTML and real words (https://www.w3.org/TR/using-aria/#rule1),
so ARIA cannot rescue vague words. A trailing "(opens in a new tab)" is set
aside first: it says how a link opens, not what it is.

Standards: WCAG 2.2 SC 2.4.4 Link Purpose (In Context), Level AA; SC 2.4.9
Link Purpose (Link Only), Level AAA, which the app aims for; SC 2.4.6
Headings and Labels, Level AA; and docs/plain-language.md rule 8 ("Buttons
say what they do: a verb and an object"). axe does not check any of this: it
only checks that a control has a name at all.

Icon-only controls (no visible words) are not judged here; their names are
checked by axe.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

# Visible words that say nothing about what the control does or where it goes.
# Matched against the whole visible text, lowercased, without punctuation or
# arrows, so "Read more →" and "Download ↓" match and "Download the
# Excel issue list" does not. Names of places ("Reports", "Settings",
# "About") say where a link goes, so they are not here.
GENERIC = frozenset(
    {
        "apply",
        "back",
        "cancel",
        "change",
        "clear",
        "clear all",
        "click here",
        "close",
        "collapse",
        "continue",
        "copy",
        "delete",
        "details",
        "done",
        "download",
        "edit",
        "expand",
        "export",
        "filter",
        "full details",
        "go",
        "group",
        "here",
        "hide",
        "info",
        "learn more",
        "link",
        "more",
        "more info",
        "more information",
        "next",
        "no",
        "ok",
        "open",
        "options",
        "page",
        "previous",
        "read more",
        "remove",
        "reset",
        "run",
        "save",
        "see details",
        "see more",
        "select",
        "show",
        "show less",
        "show more",
        "start",
        "stop",
        "submit",
        "toggle",
        "view",
        "view details",
        "yes",
    }
)
# A count and nothing else ("2 pages", "1 image"): which pages, and what
# happens to them?
COUNT_ONLY = re.compile(r"^\d[\d,]*( \w+)?$")

# Buttons, links and the controls that act like them. [data-button] is
# LinkButton (components/ui.tsx).
_COLLECT = r"""
() => {
  const selector = [
    'a[href]', 'button', '[role=button]', 'summary', '[role=tab]',
    '[role=menuitem]', '[role=menuitemradio]', '[role=menuitemcheckbox]',
  ].join(',');
  // Not rendered at all. Screen-reader-only text (a 1 px clipped box) is
  // still the control's own text, so it counts.
  const hidden = (el, stop) => {
    for (let node = el; node && node !== stop.parentElement; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden') return true;
    }
    return false;
  };
  const out = [];
  for (const el of document.querySelectorAll(selector)) {
    if (hidden(el, el)) continue;
    // Text from the scanned site is shown as the site wrote it.
    if (el.closest('[data-scanned-content]')) continue;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const parts = [];
    for (let text = walker.nextNode(); text; text = walker.nextNode()) {
      if (text.textContent.trim() && !hidden(text.parentElement, el)) parts.push(text.textContent);
    }
    const visible = parts.join(' ').replace(/\s+/g, ' ').trim();
    if (!visible) continue;
    out.push({
      tag: el.tagName.toLowerCase(),
      text: visible,
      inNav: Boolean(el.closest('nav')),
    });
  }
  return out;
}
"""


NEW_TAB = re.compile(r"\(?\s*opens in a new tab\s*\)?\s*$", re.IGNORECASE)


def vague(text: str, *, in_nav: bool = False) -> bool:
    """True when the control's own words do not say what it does."""
    words = re.sub(r"[^\w\s']", " ", NEW_TAB.sub("", text).lower())
    words = re.sub(r"\s+", " ", words).strip()
    if not words:
        return False
    # A page number in a pagination <nav> ("1", "2") is understood from the
    # list of numbers around it.
    if in_nav and words.isdigit():
        return False
    return words in GENERIC or bool(COUNT_ONLY.match(words))


def test_the_check_tells_vague_from_specific() -> None:
    for text in (
        "Read more",
        "Download ↓",
        "Cancel",
        "Full details →",
        "2 pages",
        "OK",
        "Download (opens in a new tab)",
    ):
        assert vague(text), text
    for text in (
        "Download the issue list (Excel)",
        "Cancel sign-in",
        "Read the reading guide",
        "Delete report",
        "Reports",
        "Show all images in one table",
    ):
        assert not vague(text), text
    assert vague("3") and not vague("3", in_nav=True)


async def _vague_controls(page: Any) -> list[str]:
    controls = await page.evaluate(_COLLECT)
    return sorted(
        {f"<{c['tag']}> {c['text']!r}" for c in controls if vague(c["text"], in_nav=c["inNav"])}
    )


async def _check(new_page: Any, url: str, *, open_buttons: tuple[str, ...] = ()) -> list[str]:
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_selector("main#main *", timeout=5000)
        failures = await _vague_controls(page)
        # Menus and panels show their own controls only once open.
        for name in open_buttons:
            button = page.get_by_role("button", name=name, exact=True)
            if await button.count():
                await button.first.click()
                await page.wait_for_timeout(300)
                failures += await _vague_controls(page)
                await page.keyboard.press("Escape")
        return sorted(set(failures))
    finally:
        await page.context.close()


async def _report_urls(base: str, scan_id: int, new_page: Any) -> list[str]:
    """Report screens, with real IDs from the seeded report."""
    page = await new_page()
    try:
        issues = await (await page.request.get(f"{base}/api/scans/{scan_id}/issues")).json()
        key = quote(issues["rows"][0]["issue_key"], safe="")
        await page.goto(f"{base}/app/scans/{scan_id}/issues/{key}", wait_until="networkidle")
        inspect = await page.eval_on_selector(
            "main a[href*='/inspect']", "a => a.getAttribute('href')"
        )
        await page.goto(f"{base}/app/scans/{scan_id}/findings", wait_until="networkidle")
        finding = await page.eval_on_selector(
            "main a[href*='/findings/']", "a => a.getAttribute('href')"
        )
    finally:
        await page.context.close()
    return [
        f"/app/scans/{scan_id}/issues/{key}",
        f"/app/scans/{scan_id}/issues/{key}/pages",
        str(inspect),
        str(finding),
    ]


STATIC_PATHS = (
    "/app/scans",
    "/app/scans/new",
    "/app/scans/new?mode=login",
    "/app/scans/{scan_id}/issues",
    "/app/scans/{scan_id}/compare",
    "/app/scans/{scan_id}/a11y/by-rule",
    "/app/scans/{scan_id}/findings",
    "/app/scans/{scan_id}/findings/grouped",
    "/app/tracking",
    "/app/about",
    "/app/settings",
    "/app/no-such-page",
)
# Opened on each screen that has them, so their insides are checked too.
OPEN = ("Export report", "Filter", "Filter issues", "Filter images", "Filter criteria")


async def test_every_control_says_what_it_does(live_server: tuple[str, int], new_page: Any) -> None:
    base, scan_id = live_server
    paths = [p.format(scan_id=scan_id) for p in STATIC_PATHS]
    paths += await _report_urls(base, scan_id, new_page)
    failures: list[str] = []
    for path in paths:
        url = base + (path if path.startswith("/app") else "/app" + path)
        failures += [f"{path}: {f}" for f in await _check(new_page, url, open_buttons=OPEN)]
    assert not failures, "Visible text that does not say what the control does:\n" + "\n".join(
        failures
    )


async def test_the_waiting_sign_in_card_says_what_its_buttons_do(
    fake_sign_in: type, live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page()
    response = await page.request.post(
        f"{base}/api/local-login-scans",
        headers={"origin": base},
        data={
            "seed_url": "https://app.example.test/secure/",
            "approved_auth_origins": [],
            "authorization_acknowledged": True,
        },
    )
    assert response.status == 201, await response.text()
    await page.context.close()
    failures = await _check(new_page, f"{base}/app/scans/new")
    assert not failures, "\n".join(failures)


async def test_an_aria_label_does_not_rescue_vague_visible_text(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """The collector reads what a person sees, not what ARIA adds."""
    base, _ = live_server
    page = await new_page()
    try:
        await page.goto(f"{base}/app/about", wait_until="networkidle")
        await page.wait_for_selector("main#main *", timeout=5000)
        await page.evaluate(
            """() => {
                const main = document.querySelector('main#main');
                const vague = document.createElement('button');
                vague.textContent = 'Read more';
                vague.setAttribute('aria-label', 'Read more about scan limits');
                const hiddenWords = document.createElement('a');
                hiddenWords.href = '#';
                hiddenWords.innerHTML = 'Download<span class="sr-only"> the issue list</span>';
                main.append(vague, hiddenWords);
            }"""
        )
        flagged = await _vague_controls(page)
        assert "<button> 'Read more'" in flagged
        # Screen-reader-only words are the link's own text, so they count.
        assert not [f for f in flagged if "Download" in f]
    finally:
        await page.context.close()
