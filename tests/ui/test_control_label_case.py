"""Buttons and controls are labelled in sentence case.

docs/plain-language.md rule 11: sentence case for everything. Title Case
("Start New Scan", "Delete Report") is the easy slip, and axe does not
check it, so this test reads every control on the main screens of the
review app and fails on a word capitalized where a sentence would not
capitalize it. Controls are buttons, link buttons, tabs, menu items,
options, checkboxes, radios, switches, disclosures and form labels; both
the visible text and any ``aria-label`` are checked, since a screen reader
reads the second.

Only the words the app writes are checked. Text that comes from a scanned
site (page titles, site names, element code) is left alone: it is shown
as the site wrote it.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

pytest.importorskip("playwright.async_api")

# Words that keep their capital inside a sentence: names. Abbreviations
# in capitals (PDF, WCAG) are allowed separately. docs/plain-language.md lists
# the names the interface uses. A new entry needs to be a name; a Title
# Case label does not belong here.
_NAMES = {
    "Axcess",
    "WCAG",
    "Alfa",
    "Excel",
    "Markdown",
    "Ollama",
    "Chromium",
    "Playwright",
    "Tesseract",
    "Windows",
    "Mac",
    "GitHub",
    "Google",
    "Siteimprove",
    "XPath",
    "Level",
    "Enter",
    "Escape",
    "Tab",
    "Shift",
}

# Named terms the interface capitalizes wherever they appear, as whole
# phrases, so "Delete Page" still fails while "the Page inspector" passes.
# Each is one name from docs/plain-language.md's terms table or lib/.
_PHRASES = (
    "Needs review",  # issue type, lib/terms.ts
    "Barrier",  # issue type, lib/terms.ts
    "Informational",  # issue type, lib/terms.ts
    "Best practice",  # level, docs/plain-language.md
    "Rule check",  # check name: Rule check (axe), Rule check (Alfa)
    "Page inspector",  # the tool's name
    "Click-Through",  # the feature's one name, lib/labels.ts CLICK_THROUGH
)

_WORD = re.compile("[A-Za-z][A-Za-z'\u2019-]*")


def title_case_words(text: str) -> list[str]:
    """Words written with a capital where sentence case has none.

    The first word of each line or sentence may be capitalized, and so may
    names, named terms (``_PHRASES``), abbreviations (``PDF``, ``WCAG``),
    and words with a digit, dot, plus or slash in them (``example.com``,
    ``2FA``, ``Cmd+K``). ``"Start New Scan"`` returns ``["New", "Scan"]``.
    """
    for phrase in _PHRASES:
        text = text.replace(phrase, phrase.lower())
    wrong: list[str] = []
    for line in text.splitlines():
        tokens = line.split()
        for index, token in enumerate(tokens):
            bare = token.strip("()[]{}<>.,:;?!\"'\u201c\u201d\u2018\u2019\u2026")
            if not bare or not bare[0].isupper() or not bare[1:2].islower():
                continue
            previous = tokens[index - 1] if index else ""
            ends_sentence = previous.endswith(
                (".", "?", "!", ":", "|", "\u00b7", "\u2014", "\u2013")
            )
            starts = index == 0 or ends_sentence or previous in {"#", "/"}
            if starts or bare in _NAMES:
                continue
            if any(ch.isdigit() or ch in "./@_+" for ch in bare) or bare.isupper():
                continue
            match = _WORD.match(bare)
            if match and match.group(0) in _NAMES:
                continue
            wrong.append(bare)
    return wrong


def test_the_check_catches_title_case() -> None:
    assert title_case_words("Start New Scan") == ["New", "Scan"]
    assert title_case_words("Delete Report #40") == ["Report"]
    assert title_case_words("Start a scan") == []
    assert title_case_words("Rule check (Alfa)") == []
    assert title_case_words("Export to Excel. Open the PDF") == []
    assert title_case_words("Open example.com") == []
    assert title_case_words("Open the Page inspector") == []
    assert title_case_words("Delete Page") == ["Page"]
    assert title_case_words("Search everything (Cmd+K)") == []


# Every control the app writes. [data-button] is LinkButton (components/ui.tsx).
_COLLECT = r"""
() => {
  const selector = [
    'button', '[role=button]', 'a[data-button]', '[role=tab]',
    '[role=menuitem]', '[role=menuitemradio]', '[role=menuitemcheckbox]',
    '[role=option]', 'option', '[role=switch]', '[role=radio]',
    '[role=checkbox]', 'summary', 'label',
  ].join(',');
  // Text from the scanned site is shown as the site wrote it.
  const scanned = '[data-scanned-content], code, pre, kbd, samp';
  const out = [];
  for (const el of document.querySelectorAll(selector)) {
    const label = el.getAttribute('aria-label');
    if (label) out.push({ tag: el.tagName.toLowerCase(), kind: 'aria-label', text: label });
    // innerText of the rendered element keeps the line breaks between a
    // label and its hint; a detached copy would run them together.
    let text = el.innerText ?? '';
    for (const skip of el.querySelectorAll(scanned + ', [aria-hidden=true]')) {
      const part = skip.innerText ?? '';
      if (part) text = text.split(part).join('\n');
    }
    text = text.trim();
    if (text) out.push({ tag: el.tagName.toLowerCase(), kind: 'text', text });
  }
  return out;
}
"""


async def _controls(page: Any) -> list[dict[str, str]]:
    return list(await page.evaluate(_COLLECT))


_SCAN_GROUPS = (
    "Pages to scan",
    "Checks",
    "AI checks on this computer",
    "Limits and rule check tool",
    "Speed and browser window",
)


async def _labels_on(new_page: Any, url: str, *, open_groups: bool = False) -> list[str]:
    page = await new_page()
    try:
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_selector("main#main *", timeout=5000)
        if open_groups:
            for name in _SCAN_GROUPS:
                button = page.get_by_role("button", name=name, exact=True)
                if await button.get_attribute("aria-expanded") != "true":
                    await button.click()
        controls = await _controls(page)
        assert controls, f"{url}: no controls found; is the selector still right?"
        failures = []
        for control in controls:
            words = title_case_words(control["text"])
            if words:
                where = f"<{control['tag']}> {control['kind']} {control['text']!r}"
                failures.append(f"{where}: {', '.join(words)}")
        return failures
    finally:
        await page.context.close()


@pytest.mark.parametrize(
    "path",
    [
        "/app/scans",
        "/app/scans/new",
        "/app/scans/{scan_id}",
        "/app/scans/{scan_id}/issues",
        "/app/scans/{scan_id}/compare",
        "/app/tracking",
        "/app/about",
        "/app/settings",
        "/app/no-such-page",
    ],
)
async def test_controls_are_in_sentence_case(
    live_server: tuple[str, int], new_page: Any, path: str
) -> None:
    base, scan_id = live_server
    failures = await _labels_on(
        new_page, base + path.format(scan_id=scan_id), open_groups=path == "/app/scans/new"
    )
    assert not failures, f"{path}: Title Case in control labels:\n" + "\n".join(failures)


async def test_a_title_case_button_on_a_page_fails(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """The collector reads what a real screen shows, hidden text included."""
    base, _ = live_server
    page = await new_page()
    try:
        await page.goto(f"{base}/app/about", wait_until="networkidle")
        await page.wait_for_selector("main#main *", timeout=5000)
        await page.evaluate(
            """() => {
                const button = document.createElement('button');
                button.textContent = 'Start New Scan';
                button.setAttribute('aria-label', 'Delete This Report');
                document.querySelector('main#main').append(button);
            }"""
        )
        flagged = {c["text"]: title_case_words(c["text"]) for c in await _controls(page)}
        assert flagged["Start New Scan"] == ["New", "Scan"]
        assert flagged["Delete This Report"] == ["This", "Report"]
    finally:
        await page.context.close()
