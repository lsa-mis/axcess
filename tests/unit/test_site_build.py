"""The public site generator must render every page from the coverage source of truth.

These checks are deliberately structural: one ``<h1>`` per page, a language
attribute, a title, the shared assets, and coverage numbers that match
``audit.coverage_matrix`` so the site can never drift from the code.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "site" / "build.py"


@pytest.fixture(scope="module")
def pages() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("site_build", BUILD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(mod)
    return mod.render_all()


def test_every_page_renders(pages: dict[str, str]) -> None:
    expected = {
        "",
        "how-it-works",
        "coverage",
        "who-its-for",
        "privacy",
        "get-started",
        "faq",
        "about",
    }
    assert set(pages) == expected


def test_page_skeleton(pages: dict[str, str]) -> None:
    for slug, doc in pages.items():
        assert doc.startswith("<!doctype html>"), slug
        assert '<html lang="en"' in doc, slug
        assert len(re.findall(r"<h1[ >]", doc)) == 1, f"{slug}: exactly one h1"
        assert "<title>" in doc and '<main id="main"' in doc, slug
        assert 'aria-current="page"' in doc or slug in {"", "about"}, slug
        rel = "" if slug == "" else "../"
        assert f'href="{rel}assets/site.css"' in doc, slug
        assert f'src="{rel}assets/site.js"' in doc, slug


def test_coverage_numbers_come_from_the_matrix(pages: dict[str, str]) -> None:
    from audit import coverage_matrix

    summ = coverage_matrix.summary()
    crit = coverage_matrix.load_matrix()
    cov = pages["coverage"]
    assert f"{summ.covered} of {summ.total} criteria with Axcess evidence" in cov
    assert cov.count('<details class="crit"') == len(crit)
    for c in crit:
        assert f'id="sc-{c.sc.replace(".", "-")}"' in cov, c.sc
        assert f'data-method="{c.method}"' in cov
    home = pages[""]
    assert f"<b>{summ.covered}<small> of {summ.total}</small></b>" in home


def test_honesty_statement_is_present(pages: dict[str, str]) -> None:
    for slug, doc in pages.items():
        assert "does not certify WCAG conformance" in doc, slug
