"""The form error check finishes on a page that redraws all the time.

On mantine.dev the check's change watcher read every change as it happened.
The page's live demos change constantly, so the watcher kept the page's main
thread busy for over 20 seconds, and the check ran out of time after one
form of many. Here three forms sit beside a block that changes style on
every frame; all three must be checked, within the check's time limit.
"""

from __future__ import annotations

import time

import pytest

from audit.analyzer.forms import ErrorIdentificationProbe

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

_FORM = """
<form id="f{n}" novalidate><h2>Form {n}</h2>
  <label for="a{n}">Name {n}</label><input id="a{n}">
  <button type="submit">Send {n}</button></form>
"""

_PAGE = (
    """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Busy</title></head>
<body><main>"""
    + "".join(_FORM.format(n=n) for n in range(3))
    + """
<div id="busy"></div>
<script>
  const busy = document.getElementById('busy');
  for (let i = 0; i < 1000; i++) {
    const d = document.createElement('div'); d.textContent = 'Tile ' + i; busy.appendChild(d);
  }
  const tick = t => {
    for (const d of busy.children) d.style.opacity = String(0.5 + 0.5 * Math.sin(t / 200));
    busy.firstChild.textContent = 'Frame ' + Math.round(t);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  document.querySelectorAll('form').forEach(f => f.addEventListener('submit', e => {
    e.preventDefault();
    const i = f.querySelector('input');
    i.setAttribute('aria-invalid', 'true');
    i.setAttribute('aria-describedby', f.id + '-e');
    i.insertAdjacentHTML('afterend', '<p id="' + f.id + '-e">Enter your name.</p>');
  }));
</script></main></body></html>"""
)


async def test_busy_page_is_checked_in_time(browser) -> None:  # type: ignore[no-untyped-def]
    context = await browser.new_context(service_workers="block")
    page = await context.new_page()
    await page.route("http://busy.test/", lambda r: r.fulfill(body=_PAGE, content_type="text/html"))
    try:
        await page.goto("http://busy.test/")
        probe = ErrorIdentificationProbe()
        started = time.perf_counter()
        results = await probe.run(page)
        elapsed = time.perf_counter() - started
    finally:
        await context.close()
    assert [r.outcome for r in results] == ["pass", "pass", "pass"], results
    assert elapsed < probe.timeout_s
