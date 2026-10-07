"""Structural checks on the built public site (``site/dist``).

Each check guards a promise the site makes: every page is built, has one
title heading and the honesty statement, takes its coverage numbers from the
product, never links to a missing page, loads nothing from other sites, and
repeats the installer's and app's own words in its setup steps.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .conftest import BASE, PRODUCT_ROUTES, ROOT, ROUTES

# Words docs/plain-language.md's terms table says never to use, and the old
# site's check names. Only unambiguous ones: "finding" and "coverage" also
# have plain uses ("finding problems"), so a person reviews those.
RETIRED_TERMS = (
    "remediate",
    "remediation",
    "DOM state",
    "interaction state",
    "seed URL",
    "login scan",
    "protected scan",
    "MFA",
    "snippet",
    "outerHTML",
    "n/a",
    "success criterion",
    "success criteria",
    "likely barrier",
    "review lead",
    "triage",
    "Rule engine",
    "Zoom and reflow check",
    "Meaning check",
    "Visual and motion check",
)


class _Doc(HTMLParser):
    """Collects what the checks need from one page, without a parser dependency."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.resources: list[str] = []
        self.imgs: list[dict[str, str | None]] = []
        self.role_img_labels: list[str] = []
        self.h1 = 0
        self.main_text: list[str] = []
        self.own_text: list[str] = []
        self._in_main = 0
        self._skip = 0
        self._quoted = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"] or "")
        if tag == "a" and a.get("href"):
            self.links.append(a["href"] or "")
        if tag in {"script", "img", "iframe", "source"} and a.get("src"):
            self.resources.append(a["src"] or "")
        loaded_rels = {"stylesheet", "preload", "icon", "shortcut icon"}
        if tag == "link" and a.get("href") and (a.get("rel") or "") in loaded_rels:
            self.resources.append(a["href"] or "")
        if tag == "img":
            self.imgs.append(a)
        if a.get("role") == "img" and a.get("aria-label"):
            self.role_img_labels.append(a["aria-label"] or "")
        if tag == "h1":
            self.h1 += 1
        if tag == "main":
            self._in_main += 1
        if tag in {"script", "style", "template"}:
            self._skip += 1
        if a.get("data-source"):
            self._quoted += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "main":
            self._in_main -= 1
        if tag in {"script", "style", "template"}:
            self._skip -= 1
        if tag == "p" and self._quoted:
            self._quoted -= 1

    def handle_data(self, data: str) -> None:
        if self._in_main and not self._skip:
            self.main_text.append(data)
            if not self._quoted:
                self.own_text.append(data)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.main_text))

    @property
    def site_text(self) -> str:
        """Main text written for the site, without text quoted word for word
        from a product data file (marked data-source)."""
        return re.sub(r"\s+", " ", " ".join(self.own_text))


def _parse(html: str) -> _Doc:
    doc = _Doc()
    doc.feed(html)
    return doc


def _target(dist: Path, path: str) -> Path:
    rel = unquote(path[len(BASE) :])
    f = dist / rel
    return f / "index.html" if rel == "" or rel.endswith("/") or f.is_dir() else f


def test_every_page_is_built(pages: dict[str, str]) -> None:
    assert set(pages) == set(ROUTES)


def test_page_skeleton(pages: dict[str, str]) -> None:
    for route, html in pages.items():
        doc = _parse(html)
        assert html.startswith("<!DOCTYPE html>"), route
        assert '<html lang="en"' in html, route
        assert doc.h1 == 1, f"{route}: exactly one h1"
        assert "<title>" in html and "<main" in html, route
        assert "Skip to content" in html, route


def test_honesty_statement_is_on_every_page(pages: dict[str, str]) -> None:
    # In the page's text, not its markup: the first "WCAG" on a page is
    # wrapped in <abbr> with its full form (src/middleware.ts).
    for route, html in pages.items():
        assert "does not certify WCAG conformance" in _parse(html).text, route


def test_coverage_numbers_come_from_the_matrix(pages: dict[str, str]) -> None:
    from audit import coverage_matrix

    summ = coverage_matrix.summary()
    crit = coverage_matrix.load_matrix()
    home = _parse(pages[""]).text
    assert f"{summ.covered} of {summ.total}" in home
    assert f"{summ.manual_only} of {summ.total}" in home
    cov = pages["coverage/"]
    for c in crit:
        assert f'id="sc-{c.sc.replace(".", "-")}"' in cov, c.sc


def test_volume_is_unlisted(pages: dict[str, str]) -> None:
    assert '<meta name="robots" content="noindex"' in pages["volume/"]
    for route, html in pages.items():
        if route != "volume/":
            assert f'href="{BASE}volume/"' not in html, route


def test_internal_links_images_and_anchors_resolve(dist: Path, pages: dict[str, str]) -> None:
    ids: dict[Path, set[str]] = {}
    broken = []
    for route, html in pages.items():
        doc = _parse(html)
        for href in doc.links + doc.resources:
            parts = urlsplit(href)
            if parts.scheme or parts.netloc or not parts.path.startswith(BASE):
                continue
            target = _target(dist, parts.path)
            if not target.is_file():
                broken.append(f"{route} -> {href}")
                continue
            if parts.fragment and target.suffix == ".html":
                if target not in ids:
                    ids[target] = _parse(target.read_text(encoding="utf-8")).ids
                if unquote(parts.fragment) not in ids[target]:
                    broken.append(f"{route} -> {href} (no such anchor)")
    assert not broken, "\n".join(broken)


def test_nothing_loads_from_other_sites(pages: dict[str, str]) -> None:
    """Fonts, scripts, styles and images are all served from the site itself.

    The download links' optional GitHub lookup is a fetch() in a script, not
    a page resource, and is described on the Privacy page.
    """
    for route, html in pages.items():
        for src in _parse(html).resources:
            assert not urlsplit(src).netloc, f"{route} loads {src}"
        assert "fonts.googleapis.com" not in html, route


def test_no_version_numbers_or_dashes_in_page_text(pages: dict[str, str]) -> None:
    for route, html in pages.items():
        text = _parse(html).text
        assert not re.search(r"Axcess-\d+\.\d+", text), route
        assert chr(0x2014) not in text and chr(0x2013) not in text, f"{route}: no em or en dashes"


def test_product_pages_use_the_plain_language_terms(pages: dict[str, str]) -> None:
    """Product pages follow the terms table. Guides in docs/ follow it too,
    but they are reviewed with the docs, so they are not checked here.

    Criterion text shown word for word from src/audit/rules/wcag_coverage.yaml
    (marked data-source on the coverage page) is skipped: the app's reports
    use the same text, so its wording is fixed there, with their tests."""
    wrong = []
    for route in PRODUCT_ROUTES:
        text = _parse(pages[route]).site_text
        for term in RETIRED_TERMS:
            if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, flags=re.IGNORECASE):
                wrong.append(f"{route or 'home'}: {term!r}")
    assert not wrong, "\n".join(wrong)


def test_download_links_cover_every_build(pages: dict[str, str]) -> None:
    page = pages["get-started/"]
    assert 'id="download"' in page
    builds = (
        "Mac-Apple-Silicon.dmg",
        "Windows-Installer.exe",
        "Windows-Portable.zip",
        "Linux.AppImage",
    )
    for kind in builds:
        assert f'data-release-file="{kind}"' in page, kind


def test_setup_drawings_use_the_installer_words(pages: dict[str, str]) -> None:
    """The Windows Setup drawings repeat the wizard's words; keep them in step.

    The words come from desktop/installer/installer.nsh. If the installer's
    wording changes, the drawings on Get started must change with it.
    """
    nsh = (ROOT / "desktop" / "installer" / "installer.nsh").read_text(encoding="utf-8")
    words = {
        m.group(1): m.group(2).replace("&", "")
        for m in re.finditer(r'LangString (\w+) \$\{LANG_ENGLISH\} "([^"]*)"', nsh)
    }
    page = _parse(pages["get-started/"]).text
    for key in (
        "chooseInstallationOptions",
        "whoShouldThisApplicationBeInstalledFor",
        "selectUserMode",
        "onlyForMe",
        "forAll",
        "freshInstallForCurrent",
        "MUI_TEXT_DIRECTORY_TITLE",
        "MUI_TEXT_DIRECTORY_SUBTITLE",
        "axcessFolderIntro",
        "axcessFolderLabel",
        "MUI_TEXT_FINISH_INFO_TITLE",
        "MUI_TEXT_FINISH_RUN",
    ):
        assert words[key] in page, key
    finish_last_line = words["MUI_TEXT_FINISH_INFO_TEXT"].split("$\\r$\\n")[-1]
    assert finish_last_line in page


def test_get_started_keeps_the_first_launch_steps_link(pages: dict[str, str]) -> None:
    """Shipped desktop apps link to get-started/#first-launch; it must lead to the steps.

    The update message in desktop/src/main.cjs, the README and the release
    notes send Mac users there for the first-launch steps, and an app that
    is already installed can't be changed.
    """
    page = pages["get-started/"]
    assert 'id="first-launch"' in page
    for anchor in ("install", "mac", "windows", "linux", "from-source"):
        assert f'id="{anchor}"' in page, anchor
    assert "Open Anyway" in _parse(page).text


def test_install_drawings_are_named_pictures(pages: dict[str, str]) -> None:
    doc = _parse(pages["get-started/"])
    named = ("Drawing of", "Two drawings of")
    drawings = [label for label in doc.role_img_labels if label.startswith(named)]
    assert len(drawings) == 8
    assert "The drawings are simplified, so your screen may look a little different." in doc.text


def test_step_screenshots_have_alt_text_and_size(pages: dict[str, str]) -> None:
    # Six on Get started (four first-scan steps, two of the report), three
    # with the sign-in steps.
    shots = []
    for route, count in (("get-started/", 6), ("sign-in-scan/", 3)):
        imgs = _parse(pages[route]).imgs
        found = [img for img in imgs if "/screens/" in (img.get("src") or "")]
        assert len(found) == count, route
        shots += found
    for img in shots:
        name = Path(urlsplit(img["src"] or "").path).name
        assert (ROOT / "site" / "public" / "screens" / name).is_file(), name
        assert int(img.get("width") or 0) > 0 and int(img.get("height") or 0) > 0, name
        assert len(img.get("alt") or "") > 40, name


def test_first_scan_steps_use_the_app_words(pages: dict[str, str]) -> None:
    """The first-scan and sign-in steps name what New scan shows (newScan/copy.ts)."""
    page = _parse(pages["get-started/"]).text + _parse(pages["sign-in-scan/"]).text
    for words in (
        "Website address",
        "Scan the whole website",
        "Pages to scan",
        "Limits and rule check tool",
        "Maximum pages",
        "Speed and browser window",
        "What this scan will do",
        "Site with a sign-in or two-step sign-in (2FA)",
        "Website address to scan after you sign in",
        "Open browser to sign in",
    ):
        assert words in page, words
    retired = (
        "Create New Scan",
        "Advanced settings",
        "Max pages",
        "Site URL",
        "Crawl the entire host",
    )
    for old in retired:
        assert old not in page, old


def test_guides_come_from_docs(pages: dict[str, str]) -> None:
    """Each guide's title is the first heading of its docs/ file, and repo links point at GitHub."""
    for route in ("docs/hosting/", "docs/glossary/", "docs/reading-your-report/"):
        name = route.split("/")[1]
        first = (ROOT / "docs" / f"{name}.md").read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("# ")
        assert "<h1" in pages[route] and first[2:].strip() in pages[route], route
    yaml_on_github = (
        "https://github.com/lsa-mis/axcess/blob/main/src/audit/rules/wcag_coverage.yaml"
    )
    assert yaml_on_github in pages["docs/coverage-tracker/"]
