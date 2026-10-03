"""Browser checks on the built public site: layout, axe, and use without scripts.

Pages are served straight from ``site/dist`` through Playwright's request
routing, so no network listener is opened. Uses Playwright's sync API with its
own browser, not the async ``browser`` fixture the app's UI tests share.

The site is held to the same gates as the review app: the same axe tags as
its main-screen sweep (A, AA, the AAA rules and best practice), the same
sentence-case rule for control labels (the app's own function, from
tests/ui/test_control_label_case.py), and the app's 44 px target size.

What each check guards:

- No page scrolls sideways at 320 px or 1280 px (SC 1.4.10 Reflow, Level AA).
- axe finds nothing at Level A, AA or the AAA rules, in light and dark. The
  AAA rules include 7:1 text contrast (SC 1.4.6), which the site promises.
- Every control label is in sentence case (docs/plain-language.md rule 11).
- Every control is at least 44 by 44 px (SC 2.5.5 Target Size (Enhanced),
  Level AAA, which the app meets with min-h-target). Links inside sentences
  are exempt, as SC 2.5.5 allows for inline targets.
- With scripts off, the phone menu still opens from the keyboard, search is
  replaced by an "All pages" link, and the theme switch is hidden. That is
  what keeps "Every page can be read and navigated without JavaScript. Search
  and the light or dark switch need it." true.
"""

from __future__ import annotations

import json
import mimetypes
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, sync_playwright

from .conftest import BASE, ROOT, ROUTES

pytestmark = pytest.mark.browser

ORIGIN = "http://site.test"
AXE = ROOT / "src" / "audit" / "web" / "static" / "axe.min.js"
# The review app's main-screen tags (tests/ui/test_accessibility_axe.py, _AXE_TAGS).
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag2aaa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]

# Names the site uses that the app's list does not need. Each is a name.
SITE_NAMES = {
    *("Linux", "AppImage", "Duo", "Apple", "Intel", "DevTools", "Deque", "Tailscale"),
    *("React", "Vue", "Angular", "Michigan", "University"),
    # Named parts the guides refer to: the app's "Issues" tab, and the hosting
    # guide's options "Path A", "Path B" and "Path C".
    *("Issues", "Path"),
}
# WCAG criterion names are W3C titles ("Focus Visible") and keep their capitals.
CRITERION_NAMES = sorted(
    (c["name"] for c in json.loads((ROOT / "site/src/data/coverage.json").read_text())["criteria"]),
    key=len,
    reverse=True,
)

# Every control on a page, with its visible text and any aria-label.
CONTROL_SELECTOR = ", ".join(
    [
        *("button", "summary", "select option", "[role=button]", ".ax-button"),
        *("header a", "nav a", "footer a", ".sidebar-content a"),
    ]
)
CONTROLS_JS = """sel => [...document.querySelectorAll(sel)]
  .filter(el => el.checkVisibility ? el.checkVisibility() : el.offsetParent)
  .flatMap(el => [el.innerText, el.getAttribute('aria-label')])
  .filter(Boolean).map(s => s.trim()).filter(Boolean)"""

# Controls smaller than 44 px. Links inside running text are inline targets.
TARGET_SELECTOR = ", ".join(
    [
        *("button", "summary", "select", ".ax-button", "header a", "nav a", "footer a"),
        *(".sidebar-content a", "starlight-toc a"),
    ]
)
SMALL_TARGETS_JS = """sel => [...document.querySelectorAll(sel)]
  .filter(el => (el.checkVisibility ? el.checkVisibility() : el.offsetParent)
    && !el.closest('p'))
  .map(el => ({el, r: el.getBoundingClientRect()}))
  .filter(({r}) => r.width > 0 && (r.height < 44 || r.width < 44))
  .map(({el, r}) => {
    const name = (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 40);
    return `${el.tagName.toLowerCase()} "${name}" ${Math.round(r.width)}x${Math.round(r.height)}`;
  })"""


@pytest.fixture(scope="module")
def site_browser(dist: Path) -> Iterator[Browser]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


def _context(browser: Browser, dist: Path, **options: object) -> BrowserContext:
    ctx = browser.new_context(**options)  # type: ignore[arg-type]

    def serve(route: Route) -> None:
        url = route.request.url
        if not url.startswith(ORIGIN + BASE):
            # Nothing from other sites, including the GitHub release lookup.
            route.abort()
            return
        rel = url[len(ORIGIN + BASE) :].split("#")[0].split("?")[0]
        f = dist / rel
        if rel == "" or rel.endswith("/") or f.is_dir():
            f = f / "index.html"
        if not f.is_file():
            route.fulfill(status=404, body="Not found")
            return
        route.fulfill(
            status=200,
            body=f.read_bytes(),
            content_type=mimetypes.guess_type(f.name)[0] or "text/html",
        )

    ctx.route("**/*", serve)
    return ctx


def _open(ctx: BrowserContext, route: str) -> Page:
    page = ctx.new_page()
    page.goto(f"{ORIGIN}{BASE}{route}")
    return page


@pytest.mark.parametrize("width", [320, 1280])
def test_no_page_scrolls_sideways(site_browser: Browser, dist: Path, width: int) -> None:
    ctx = _context(site_browser, dist, viewport={"width": width, "height": 800})
    wide = []
    for route in ROUTES:
        page = _open(ctx, route)
        scroll = page.evaluate("document.documentElement.scrollWidth")
        if scroll > width:
            wide.append(f"{route}: {scroll}px")
        page.close()
    ctx.close()
    assert not wide, "\n".join(wide)


@pytest.mark.parametrize("width", [320, 1280])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_axe_finds_nothing(site_browser: Browser, dist: Path, scheme: str, width: int) -> None:
    ctx = _context(
        site_browser, dist, viewport={"width": width, "height": 800}, color_scheme=scheme
    )
    problems = []
    for route in ROUTES:
        page = _open(ctx, route)
        page.add_script_tag(path=str(AXE))
        result = page.evaluate(
            "tags => axe.run(document, {runOnly: {type: 'tag', values: tags}})",
            AXE_TAGS,
        )
        for v in result["violations"]:
            targets = ", ".join(str(n["target"]) for n in v["nodes"][:3])
            problems.append(f"{route} [{scheme}, {width}px] {v['id']}: {v['help']} ({targets})")
        page.close()
    ctx.close()
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("width", [320, 1280])
def test_controls_are_at_least_44_px(site_browser: Browser, dist: Path, width: int) -> None:
    ctx = _context(site_browser, dist, viewport={"width": width, "height": 800})
    small = []
    for route in ROUTES:
        page = _open(ctx, route)
        small += [
            f"{route or 'home'}: {s}" for s in page.evaluate(SMALL_TARGETS_JS, TARGET_SELECTOR)
        ]
        page.close()
    ctx.close()
    assert not small, "\n".join(small)


def test_control_labels_are_sentence_case(site_browser: Browser, dist: Path) -> None:
    from ui.test_control_label_case import title_case_words

    ctx = _context(site_browser, dist, viewport={"width": 1280, "height": 800})
    wrong = []
    for route in ROUTES:
        page = _open(ctx, route)
        for label in set(page.evaluate(CONTROLS_JS, CONTROL_SELECTOR)):
            text = label
            for name in CRITERION_NAMES:
                text = text.replace(name, name.lower())
            words = [w for w in title_case_words(text) if w not in SITE_NAMES]
            if words:
                wrong.append(f"{route or 'home'}: {label!r} ({', '.join(words)})")
        page.close()
    ctx.close()
    assert not wrong, "\n".join(sorted(wrong))


def test_without_scripts_the_phone_menu_and_all_pages_link_work(
    site_browser: Browser, dist: Path
) -> None:
    ctx = _context(
        site_browser, dist, viewport={"width": 320, "height": 640}, java_script_enabled=False
    )
    page = _open(ctx, "docs/reading-your-report/")

    assert page.locator("a.all-pages").is_visible()
    assert not page.locator("site-search > button").first.is_visible()
    assert not page.locator("starlight-theme-select").first.is_visible()

    menu = page.locator("button.sl-menu-button")
    menu.focus()
    page.keyboard.press("Enter")
    link = page.locator("#starlight__sidebar a", has_text="Hosting Axcess")
    assert link.is_visible()
    link.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(f"{ORIGIN}{BASE}docs/hosting/")
    ctx.close()


def test_without_scripts_the_system_colour_scheme_applies(
    site_browser: Browser, dist: Path
) -> None:
    for scheme, background in (("light", "rgb(255, 255, 255)"), ("dark", "rgb(17, 26, 38)")):
        ctx = _context(site_browser, dist, java_script_enabled=False, color_scheme=scheme)
        page = _open(ctx, "docs/")
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == background, (
            scheme
        )
        ctx.close()


def test_questions_open_from_the_keyboard_without_scripts(
    site_browser: Browser, dist: Path
) -> None:
    ctx = _context(site_browser, dist, java_script_enabled=False)
    page = _open(ctx, "")
    summary = page.locator("details summary").first
    summary.focus()
    page.keyboard.press("Enter")
    assert page.locator("details").first.evaluate("d => d.open")
    ctx.close()


def test_first_tab_reaches_the_skip_link(site_browser: Browser, dist: Path) -> None:
    ctx = _context(site_browser, dist)
    page = _open(ctx, "")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Skip to content"
    ctx.close()


# Get started: download links and install drawings. Ported from the old
# tests/ui/test_site_downloads.py and test_site_install_drawings.py.

DOWNLOAD = "https://github.com/lsa-mis/axcess/releases/download/desktop-v0.64"
LATEST = "https://github.com/lsa-mis/axcess/releases/latest"
BUILDS = (
    "Mac-Apple-Silicon.dmg",
    "Windows-Installer.exe",
    "Windows-Portable.zip",
    "Linux.AppImage",
)


def _get_started(browser: Browser, dist: Path, release: dict[str, object] | None) -> Page:
    ctx = _context(browser, dist)

    def api(route: Route) -> None:
        if release is None:
            route.fulfill(status=503, body="unavailable")
        else:
            route.fulfill(content_type="application/json", body=json.dumps(release))

    # Registered after the catch-all, so it answers first.
    ctx.route("https://api.github.com/**", api)
    page = _open(ctx, "get-started/")
    page.wait_for_load_state("networkidle")
    return page


def test_download_links_point_at_the_newest_release_files(
    site_browser: Browser, dist: Path
) -> None:
    names = [f"Axcess-0.64-{kind}" for kind in BUILDS]
    release = {
        "tag_name": "desktop-v0.64",
        "assets": [{"name": n, "browser_download_url": f"{DOWNLOAD}/{n}"} for n in names]
        + [{"name": "latest.yml", "browser_download_url": f"{DOWNLOAD}/latest.yml"}],
    }
    page = _get_started(site_browser, dist, release)
    for kind in BUILDS:
        for link in page.locator(f'a[data-release-file="{kind}"]').all():
            assert link.get_attribute("href") == f"{DOWNLOAD}/Axcess-0.64-{kind}", kind
    shown = page.locator("code[data-release-name]").all_inner_texts()
    assert shown and all(s.startswith("Axcess-0.64-") for s in shown)
    page.context.close()


def test_without_the_api_download_links_open_the_release_page(
    site_browser: Browser, dist: Path
) -> None:
    page = _get_started(site_browser, dist, None)
    for kind in BUILDS:
        for link in page.locator(f'a[data-release-file="{kind}"]').all():
            assert link.get_attribute("href") == LATEST, kind
    shown = page.locator("code[data-release-name]").first.inner_text()
    assert shown == "Axcess-(version)-Mac-Apple-Silicon.dmg"
    page.context.close()


def test_each_install_drawing_is_one_named_picture(site_browser: Browser, dist: Path) -> None:
    page = _get_started(site_browser, dist, None)
    assert page.get_by_role("img", name="Drawing of", exact=False).count() == 7
    assert page.get_by_role("img", name="Two drawings of", exact=False).count() == 1
    # The drawn buttons are part of the picture, not controls.
    for name in ("Open Anyway", "Run anyway", "Done", "Next >", "Install", "Finish"):
        assert page.get_by_role("button", name=name, exact=True).count() == 0, name
    inside = page.evaluate(
        """() => [...document.querySelectorAll('[role=img][aria-label^="Drawing"],'
                 + '[role=img][aria-label^="Two drawings"]')]
             .reduce((n, d) => n + d.querySelectorAll('a, button, input, [tabindex]').length, 0)"""
    )
    assert inside == 0
    page.context.close()


def test_install_drawings_fit_at_320_px(site_browser: Browser, dist: Path) -> None:
    ctx = _context(site_browser, dist, viewport={"width": 320, "height": 900})
    page = _open(ctx, "get-started/")
    overflow = page.evaluate(
        """() => [...document.querySelectorAll('[role=img][aria-label*="rawing"]')]
             .filter(d => d.scrollWidth > d.clientWidth + 1).length"""
    )
    assert overflow == 0
    ctx.close()
