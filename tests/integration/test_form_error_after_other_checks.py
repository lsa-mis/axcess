"""The form error check judges the page as it loaded, after the other checks.

In a scan it runs last, on the page the other checks already used. The
keyboard and focus checks move focus through every field, and a page that
checks a field when it loses focus marks it in error then, before any press.
The form check then saw the same marks before and after its press, "no sign
of an error". Section 508's test page TF10/10.D-2-fail-2 (a field that only
turns red) came out that way in reports #48 and #49, though the check alone
fails it. This is a cut-down copy of that page.
"""

from __future__ import annotations

from typing import Any

import pytest

from audit.analyzer.forms import ErrorIdentificationProbe
from audit.analyzer.keyboard import KeyboardProbe

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

_URL = "http://blur.test/"
_PAGE = """<!doctype html><html lang="en"><head><title>Number</title><style>
input.error { background-color: #fdd; border-color: red; }</style><script>
function validate(el) {
  if (!/^[0-9]+$/.test(el.value)) el.classList.add('error');
  else el.classList.remove('error');
}
window.onload = () => {
  const box = document.getElementById('number');
  box.addEventListener('blur', () => validate(box));
  box.addEventListener('keydown', () => box.classList.remove('error'));
  document.getElementById('submit-btn').addEventListener('click', () => validate(box));
};
</script></head><body><main>
<label for="number">Enter A Number:</label><input type="text" id="number">
<button type="button" id="submit-btn">Submit</button>
</main></body></html>"""


async def test_a_field_marked_on_blur_by_the_keyboard_check_still_fails(browser: Any) -> None:
    context = await browser.new_context(service_workers="block")
    await context.route(_URL, lambda r: r.fulfill(body=_PAGE, content_type="text/html"))
    page = await context.new_page()
    try:
        await page.goto(_URL)
        await KeyboardProbe().run(page)
        assert await page.evaluate(
            "() => document.getElementById('number').classList.contains('error')"
        ), "the keyboard check no longer leaves the field marked; this test proves nothing"
        results = await ErrorIdentificationProbe().run(page)
    finally:
        await context.close()
    assert [r.outcome for r in results] == ["fail"], results


# A form a script builds after the page's load event, as web components and
# many single-page apps do: Shoelace's form controls appear 0.27 s after
# "load". The check reloads before its first press, and used to plan again at
# once, find no form, and say nothing about the page.
_LATE = """<!doctype html><html lang="en"><head><title>Late</title></head><body><main></main>
<script>setTimeout(() => {
  document.querySelector('main').innerHTML = '<form id="f" novalidate><label for="n">Name</label>' +
    '<input id="n"><button type="submit">Send</button></form>';
  document.getElementById('f').addEventListener('submit', e => { e.preventDefault();
    document.getElementById('n').style.border = '2px solid #c62828'; });
}, 300);</script></body></html>"""


async def test_a_form_built_after_load_is_still_judged_after_the_reload(browser: Any) -> None:
    context = await browser.new_context(service_workers="block")
    await context.route(_URL, lambda r: r.fulfill(body=_LATE, content_type="text/html"))
    page = await context.new_page()
    try:
        await page.goto(_URL)
        await page.wait_for_selector("#f")
        results = await ErrorIdentificationProbe().run(page)
    finally:
        await context.close()
    assert [r.outcome for r in results] == ["fail"], results
