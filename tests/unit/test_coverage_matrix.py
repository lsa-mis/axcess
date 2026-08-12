"""Tests for the WCAG 2.2 A/AA coverage matrix.

These guard the honesty contract: the matrix must enumerate exactly the
A/AA criteria, never claim a pipeline it doesn't have, and always tell a
human what's left to test.
"""

from __future__ import annotations

import pytest

from audit.coverage_matrix import (
    LEVELS,
    METHODS,
    Criterion,
    by_sc,
    load_matrix,
    summary,
)

# WCAG 2.2 Level A + AA has 55 success criteria (31 A + 24 AA); 4.1.1 Parsing
# was removed in 2.2 and AAA is out of scope for this matrix.
EXPECTED_TOTAL = 55
EXPECTED_A = 31
EXPECTED_AA = 24

# The criteria each shipped pipeline actually emits findings for — these MUST
# be marked non-manual and name the right pipeline, or the report would lie.
SHIPPED_PIPELINE_SCS = {
    "2.1.2": "keyboard",
    "1.4.4": "responsive",
    "1.4.10": "responsive",
    "1.4.12": "responsive",
    "1.4.5": "image",
    "2.4.4": "semantic",
}


def test_matrix_loads_and_has_exact_aaa_set() -> None:
    crit = load_matrix()
    assert len(crit) == EXPECTED_TOTAL
    assert sum(1 for c in crit if c.level == "A") == EXPECTED_A
    assert sum(1 for c in crit if c.level == "AA") == EXPECTED_AA
    # 4.1.1 was removed in WCAG 2.2 — it must not be present.
    assert by_sc("4.1.1") is None


def test_no_duplicate_criteria() -> None:
    scs = [c.sc for c in load_matrix()]
    assert len(scs) == len(set(scs))


def test_every_criterion_is_well_formed() -> None:
    for c in load_matrix():
        assert isinstance(c, Criterion)
        assert c.method in METHODS
        assert c.level in LEVELS
        # The transparency promise: every SC tells a human what to check.
        assert c.manual_check.strip(), f"{c.sc} missing manual_check"
        # Honesty guards.
        if c.method == "manual":
            assert c.pipelines == (), f"{c.sc} manual but has pipelines"
            assert not c.is_covered
        else:
            assert c.pipelines, f"{c.sc} {c.method} but no pipeline"
            assert c.is_covered


def test_shipped_pipeline_criteria_are_covered() -> None:
    for sc, pipeline in SHIPPED_PIPELINE_SCS.items():
        c = by_sc(sc)
        assert c is not None, f"{sc} missing from matrix"
        assert c.method != "manual", f"{sc} should be covered by {pipeline}"
        assert pipeline in c.pipelines, f"{sc} should name pipeline {pipeline}"


def test_summary_math_is_consistent() -> None:
    s = summary()
    assert s.total == EXPECTED_TOTAL
    assert sum(s.by_method.values()) == s.total
    assert s.covered + s.manual_only == s.total
    # Per-level method counts sum to the per-level totals.
    for level in LEVELS:
        level_total = sum(1 for c in load_matrix() if c.level == level)
        assert sum(s.by_level[level].values()) == level_total


def test_automated_criteria_have_high_or_real_confidence() -> None:
    # An 'automated' claim with 'n/a' confidence would be incoherent.
    for c in load_matrix():
        if c.method == "automated":
            assert c.confidence in ("high", "medium"), f"{c.sc} automated but {c.confidence}"
            assert c.automated_check.strip(), f"{c.sc} automated but no automated_check"


def test_accessible_authentication_stays_a_manual_review() -> None:
    """A post-MFA browser session must never be treated as an SC 3.3.8 verdict."""
    criterion = by_sc("3.3.8")
    assert criterion is not None
    assert criterion.level == "AA"
    assert criterion.method == "manual"
    assert criterion.pipelines == ()
    assert "MFA" in criterion.manual_check
    assert "does not automatically" in criterion.manual_check


@pytest.mark.parametrize("sc", ["2.1.2", "1.4.10", "1.4.5", "2.4.4", "2.4.6", "1.1.1"])
def test_known_criteria_present_by_name(sc: str) -> None:
    c = by_sc(sc)
    assert c is not None and c.name
