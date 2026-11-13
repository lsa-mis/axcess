"""Unit tests for the Coverage page's "What Axcess checks" data (`audit.web.coverage_checks`)."""

from __future__ import annotations

import re
from collections import Counter

import pytest

from audit import coverage_matrix
from audit.analyzer.axe import DEFAULT_AXE_BUNDLE
from audit.web import coverage_checks as checks


def test_every_criterion_has_plain_wording() -> None:
    matrix = {c.sc for c in coverage_matrix.load_matrix()}
    assert matrix == set(checks.PLAIN)
    for sc, (does, you) in checks.PLAIN.items():
        assert you, sc
        method = next(c.method for c in coverage_matrix.load_matrix() if c.sc == sc)
        # A criterion Axcess does not check says nothing about what it does,
        # unless a trial check runs there and says it does not count yet.
        if method == "manual" and sc not in _TRIAL_CHECKS:
            assert not does, sc
        elif method != "manual":
            assert does, sc
    for sc in _TRIAL_CHECKS:
        does, _ = checks.PLAIN[sc]
        assert "does not count" in does, sc


#: Criteria marked "You check" where a check runs but is not yet proved on
#: real pages: the form error check for 3.3.1.
_TRIAL_CHECKS = {"3.3.1"}


def test_wcag_21_has_50_criteria_with_4_1_1_marked_not_needed() -> None:
    result = checks.coverage_checks("2.1")
    numbers = [c.sc for c in result.criteria]
    assert len(numbers) == 50
    assert not set(numbers) & checks.WCAG22_ADDED
    parsing = next(c for c in result.criteria if c.sc == "4.1.1")
    assert parsing.method == "not_needed"
    assert parsing.checks == []
    # Numeric order: 1.4.10 after 1.4.5, 4.1.1 before 4.1.2.
    assert numbers.index("1.4.10") > numbers.index("1.4.5")
    assert numbers.index("4.1.1") + 1 == numbers.index("4.1.2")


def test_wcag_22_has_55_criteria_and_no_4_1_1() -> None:
    result = checks.coverage_checks("2.2")
    assert len(result.criteria) == 55
    assert "4.1.1" not in {c.sc for c in result.criteria}
    assert Counter(c.method for c in result.criteria)["manual"] == 27


def test_rule_catalogue_matches_the_bundled_axe_core() -> None:
    header = DEFAULT_AXE_BUNDLE.read_text(encoding="utf-8")[:400]
    match = re.search(r"axe v(\d+\.\d+\.\d+)", header)
    assert match
    assert checks.axe_catalog().version == match.group(1), (
        "Run node scripts/build_axe_rule_catalog.mjs after changing axe.min.js"
    )


def test_rule_counts_follow_the_version_and_skip_experimental_rules() -> None:
    v21 = checks.rules_by_criterion("2.1")
    v22 = checks.rules_by_criterion("2.2")
    assert "target-size" in v22["2.5.8"]
    assert "2.5.8" not in v21
    # label-content-name-mismatch is experimental, so 2.5.3 has no rules.
    assert "2.5.3" not in v21
    assert v21["1.4.3"] == ["color-contrast"]


def test_study_totals_match_the_published_figures() -> None:
    study = checks.coverage_checks().study
    assert sum(row.share for row in study) == pytest.approx(1)
    rule_check = sum(row.share * row.rule_check for row in study)
    other = sum(row.share * row.other_checks for row in study)
    # Deque's table 1 without 4.1.1: axe-core finds about 53% by volume.
    assert rule_check == pytest.approx(0.530, abs=0.001)
    assert other == pytest.approx(0.051, abs=0.001)


def test_default_version_is_what_scans_use() -> None:
    assert checks.coverage_checks().wcag_version == checks.SCAN_DEFAULT_VERSION == "2.1"


@pytest.mark.parametrize(
    ("name", "version", "url"),
    [
        (
            "Contrast (Minimum)",
            "2.1",
            "https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html",
        ),
        (
            "Name, Role, Value",
            "2.2",
            "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html",
        ),
        (
            "Error Prevention (Legal, Financial, Data)",
            "2.2",
            "https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-legal-financial-data.html",
        ),
        ("Parsing", "2.1", "https://www.w3.org/WAI/WCAG21/Understanding/parsing.html"),
    ],
)
def test_understanding_links_follow_the_w3c_page_names(name: str, version: str, url: str) -> None:
    assert checks.understanding_url(name, version) == url  # type: ignore[arg-type]


def test_apg_guidance_names_real_criteria() -> None:
    matrix = {c.sc for c in coverage_matrix.load_matrix()}
    assert set(checks.APG_GUIDANCE) <= matrix
    contrast = next(c for c in checks.coverage_checks().criteria if c.sc == "4.1.2")
    assert [g.title for g in contrast.apg] == [
        "Patterns",
        "Providing Accessible Names and Descriptions",
    ]
    assert all(g.url.startswith("https://www.w3.org/WAI/ARIA/apg/") for g in contrast.apg)
