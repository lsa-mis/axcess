"""Shared fixtures for the built public site (``site/dist``).

These tests check the HTML Astro produced, so they need ``make site`` first.
Locally they skip with a hint when the site is not built; CI sets
``AXCESS_SITE_REQUIRED=1`` so a missing build fails instead of passing
silently.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIST = Path(os.environ.get("AXCESS_SITE_DIST", ROOT / "site" / "dist"))
BASE = "/axcess/"

# Every page the site must publish, by route under the base.
PRODUCT_ROUTES = (
    "",
    "get-started/",
    "how-it-works/",
    "coverage/",
    "who-its-for/",
    "privacy/",
    "faq/",
    "about/",
    "all-pages/",
    "volume/",
)
GUIDE_ROUTES = (
    "docs/",
    "docs/desktop-app/",
    "docs/reading-your-report/",
    "docs/troubleshooting/",
    "docs/hosting/",
    "docs/spa-search-scans/",
    "docs/glossary/",
    "docs/coverage-tracker/",
)
ROUTES = PRODUCT_ROUTES + GUIDE_ROUTES


@pytest.fixture(scope="session")
def dist() -> Path:
    if not (DIST / "index.html").is_file():
        if os.environ.get("AXCESS_SITE_REQUIRED"):
            pytest.fail(f"The site is not built at {DIST}. Run `make site`.")
        pytest.skip("The public site is not built. Run `make site` to test it.")
    return DIST


@pytest.fixture(scope="session")
def pages(dist: Path) -> dict[str, str]:
    """Every built page by route. A missing page fails test_every_page_is_built
    (and any test that reads it) rather than every test at once."""
    found = {}
    for route in ROUTES:
        f = dist / route / "index.html"
        if f.is_file():
            found[route] = f.read_text(encoding="utf-8")
    return found
