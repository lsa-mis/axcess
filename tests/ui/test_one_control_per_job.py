"""One control per job: no two controls in a row, card or dialog do the same thing.

Two controls that do one job make the reader choose between them and wonder
how they differ; screen reader and keyboard users meet both, one after the
other. The Reports table had one until 2026-10-30: a site row's occurrence
count, "224 occurrences", was a link to the same report as "Open latest scan"
in the same row.

What counts as the same job, inside one scope:

- two links that end up at the same place, after the app's own redirects
  (`/scans/12` opens `/scans/12/issues` for a completed scan) and without
  the "came from here" pair (`origin`, `back`) that only feeds the
  breadcrumb; or
- two controls with the same words: the same job, or two jobs a reader
  cannot tell apart (SC 2.4.4 Link Purpose (In Context), Level AA).

A scope is the nearest table row (`<tr>`, or `role="row"`), card
(`data-card`, components/ui.tsx) or dialog. Whole screens are not checked:
a screen repeats some links on purpose (the breadcrumb and the sidebar both
reach Reports; "Scan again" is on Reports and on Issues, with the same name,
for SC 3.2.4 Consistent Identification, Level AA). Within a row or a card, a
repeat is almost always a mistake.

Standards: W3C COGA, "Making Content Usable"
(https://www.w3.org/TR/coga-usable/), one way to do one thing (paraphrased);
the repo's rule "no duplicate controls for one function" (AGENTS.md, "Review
every frontend change for accessibility").

What this cannot see: two controls with different words and different
addresses that still do one job for the reader. That is for review.

A real exception goes in KEEP, with its reason.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import pytest

from audit.db.schema import connect

from .conftest import _seed
from .test_control_text_purpose import OPEN, STATIC_PATHS, _report_urls

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

# (screen path pattern, scope text pattern, control text) -> why both stay.
KEEP: dict[tuple[str, str, str], str] = {}

# Buttons, links and the controls that act like them, as the control-text
# sweep collects them, each with its scope.
_COLLECT = r"""
() => {
  const selector = [
    'a[href]', 'button', '[role=button]', 'summary', '[role=tab]',
    '[role=menuitem]', '[role=menuitemradio]', '[role=menuitemcheckbox]',
  ].join(',');
  const hidden = (el, stop) => {
    for (let node = el; node && node !== stop.parentElement; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden') return true;
    }
    return false;
  };
  const scopes = new Map();
  const out = [];
  for (const el of document.querySelectorAll(selector)) {
    if (hidden(el, el)) continue;
    if (el.closest('[data-scanned-content]')) continue;
    const scope = el.closest('tr, [role=row], [data-card], dialog, [role=dialog]');
    if (!scope) continue;
    if (!scopes.has(scope)) {
      const named = scope.querySelector('th[scope=row], [role=rowheader], h2, h3, th');
      const label = (named ?? scope).textContent.replace(/\s+/g, ' ').trim().slice(0, 60);
      scopes.set(scope, `${scopes.size}: <${scope.tagName.toLowerCase()}> ${label}`);
    }
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const parts = [];
    for (let text = walker.nextNode(); text; text = walker.nextNode()) {
      if (text.textContent.trim() && !hidden(text.parentElement, el)) parts.push(text.textContent);
    }
    // An image link's words are its picture's alt text.
    for (const img of el.querySelectorAll('img[alt]')) parts.push(img.alt);
    out.push({
      scope: scopes.get(scope),
      tag: el.tagName.toLowerCase(),
      text: parts.join(' ').replace(/\s+/g, ' ').trim(),
      href: el.tagName === 'A' ? el.href : null,
      sameOrigin: el.tagName === 'A' ? el.origin === location.origin : null,
    });
  }
  return out;
}
"""

_SCAN = re.compile(r"^/scans/(\d+)$")
_LEGACY_REPORT = re.compile(r"^/scans/(\d+)/(?:review|manual-checks|handoff)$")
_LEGACY_DIFF = re.compile(r"^/scans/(\d+)/diff$")
# Only feed the breadcrumb (withReturnTrail, components/ui.tsx).
_TRAIL = frozenset({"origin", "back"})


def destination(href: str, *, same_origin: bool, completed: set[int]) -> str:
    """Where a link ends up: its in-app path after the app's redirects (App.tsx,
    routes/ScanDetail.tsx), and its query without the return trail."""
    if not same_origin:
        return href
    parts = urlsplit(href)
    path = parts.path.removeprefix("/app").rstrip("/") or "/"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _TRAIL]
    if path == "/":
        path = "/scans"
    elif path == "/scans/protected/new":
        path = "/scans/new"
        query = [(k, v) for k, v in query if k != "mode"] + [("mode", "login")]
    elif match := _LEGACY_REPORT.match(path):
        path, query = f"/scans/{match[1]}/issues", []
    elif match := _LEGACY_DIFF.match(path):
        path = f"/scans/{match[1]}/compare/changes"
        query = [(k, v) for k, v in query if k == "compare_to"]
    elif (match := _SCAN.match(path)) and int(match[1]) in completed:
        path, query = f"/scans/{match[1]}/issues", []
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    return path + (f"?{urlencode(sorted(query))}" if query else "") + fragment


def duplicates(controls: list[dict[str, Any]], completed: set[int]) -> list[str]:
    """Pairs of controls in one scope that do the same job."""
    found: list[str] = []
    by_scope: dict[str, list[dict[str, Any]]] = {}
    for control in controls:
        by_scope.setdefault(control["scope"], []).append(control)
    for scope, members in by_scope.items():
        seen_place: dict[str, str] = {}
        seen_words: dict[str, str] = {}
        for c in members:
            label = f"<{c['tag']}> {c['text']!r}"
            if c["href"]:
                place = destination(c["href"], same_origin=c["sameOrigin"], completed=completed)
                if place in seen_place:
                    found.append(f"[{scope}] {seen_place[place]} and {label} both go to {place}")
                else:
                    seen_place[place] = label
            words = c["text"].lower()
            if words:
                if words in seen_words:
                    found.append(f"[{scope}] {seen_words[words]} and {label} have the same words")
                else:
                    seen_words[words] = label
    return found


def kept(path: str, finding: str) -> bool:
    return any(
        re.search(screen, path) and re.search(scope, finding) and words in finding
        for (screen, scope, words) in KEEP
    )


def test_the_check_tells_one_job_from_two() -> None:
    base = "http://host/app"
    completed = {12}

    def control(text: str, href: str | None = None, scope: str = "row") -> dict[str, Any]:
        tag = "a" if href else "button"
        return {"scope": scope, "tag": tag, "text": text, "href": href, "sameOrigin": True}

    # The case that started this: a count linking where "Open latest scan" goes.
    assert duplicates(
        [
            control("224 occurrences", f"{base}/scans/12/issues"),
            control("Open latest scan", f"{base}/scans/12"),
        ],
        completed,
    )
    # A scan that has not completed does not redirect to its issues.
    assert not duplicates(
        [
            control("Open Report #13", f"{base}/scans/13"),
            control("Issues", f"{base}/scans/13/issues"),
        ],
        completed,
    )
    # The return trail does not make a different place.
    assert duplicates(
        [
            control("Image #3", f"{base}/findings/3?origin=Issues&back=%2Fscans%2F12%2Fissues"),
            control("Open image 3", f"{base}/findings/3"),
        ],
        completed,
    )
    # A filter does.
    assert not duplicates(
        [
            control("All", f"{base}/scans/12/issues"),
            control("New", f"{base}/scans/12/issues?change=new"),
        ],
        completed,
    )
    # Two buttons with the same words, in one row; but not across rows.
    assert duplicates([control("Delete report 12"), control("Delete report 12")], completed)
    assert not duplicates(
        [control("Scan again", scope="a"), control("Scan again", scope="b")], completed
    )
    # Old addresses land where the app sends them.
    assert destination(f"{base}/scans/12/diff?compare_to=9", same_origin=True, completed=set()) == (
        "/scans/12/compare/changes?compare_to=9"
    )
    assert destination(f"{base}/scans/5/review", same_origin=True, completed=set()) == (
        "/scans/5/issues"
    )


@pytest.fixture
def two_reports(seeded_db: tuple[Path, Path, int]) -> tuple[int, int]:
    """A second completed report of the seeded site, so pairs and lists show."""
    db_path, blob_dir, first = seeded_db
    conn = connect(db_path)
    try:
        second = _seed(conn, blob_dir)
        conn.commit()
    finally:
        conn.close()
    return first, second


async def _completed(base: str, new_page: Any) -> tuple[set[int], list[str]]:
    """The completed reports' ids, and each site's address."""
    page = await new_page()
    try:
        sites = await (await page.request.get(f"{base}/api/sites")).json()
    finally:
        await page.context.close()
    rows = sites["sites"] if isinstance(sites, dict) else sites
    ids = {scan["id"] for site in rows for scan in site["scans"] if scan["status"] == "completed"}
    return ids, [site["site_url"] for site in rows]


async def _check(new_page: Any, url: str, completed: set[int]) -> list[str]:
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_selector("main#main *", timeout=5000)
        found = duplicates(await page.evaluate(_COLLECT), completed)
        # Menus and panels show their own controls only once open.
        for name in (*OPEN, *(f"Compare with another report, for Report #{i}" for i in completed)):
            button = page.get_by_role("button", name=name, exact=True)
            if await button.count():
                await button.first.click()
                await page.wait_for_timeout(300)
                found += duplicates(await page.evaluate(_COLLECT), completed)
                await page.keyboard.press("Escape")
        return sorted(set(found))
    finally:
        await page.context.close()


async def test_no_two_controls_do_one_job(
    live_server: tuple[str, int], two_reports: tuple[int, int], new_page: Any
) -> None:
    base, scan_id = live_server
    first, second = two_reports
    completed, sites = await _completed(base, new_page)
    paths = [p.format(scan_id=scan_id) for p in STATIC_PATHS]
    paths += await _report_urls(base, scan_id, new_page)
    # Reports with every site open, so the scan rows are checked too, and
    # Compare reports with a pair.
    paths += [
        "/app/scans?" + urlencode([("open", url) for url in sites]),
        f"/app/scans/{second}/compare?compare_to={first}",
        f"/app/scans/{second}/compare/changes?compare_to={first}",
    ]
    failures: list[str] = []
    # A report URL found by following links can repeat a fixed one.
    for path in dict.fromkeys(paths):
        url = base + (path if path.startswith("/app") else "/app" + path)
        failures += [
            f"{path}: {f}" for f in await _check(new_page, url, completed) if not kept(path, f)
        ]
    assert not failures, "Two controls doing one job:\n" + "\n".join(failures)


async def test_the_reports_row_count_is_not_a_second_way_in(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """Putting the old count link back into a site row fails the check."""
    base, _ = live_server
    completed, _ = await _completed(base, new_page)
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}/app/scans", wait_until="networkidle")
        row = page.get_by_role("table").locator(":scope > tbody > tr").first
        open_link = row.get_by_role("link", name=re.compile(r"^Open latest scan"))
        href = await open_link.get_attribute("href")
        assert href
        assert not duplicates(await page.evaluate(_COLLECT), completed)
        await (
            row.locator("td")
            .nth(2)
            .evaluate(
                "(cell, href) => { const a = document.createElement('a');"
                " a.href = href + '/issues'; a.textContent = '224 occurrences';"
                " cell.replaceChildren(a); }",
                href,
            )
        )
        found = duplicates(await page.evaluate(_COLLECT), completed)
        assert any("224 occurrences" in f and "Open latest scan" in f for f in found), found
    finally:
        await page.context.close()
