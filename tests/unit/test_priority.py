"""Golden tests for the priority-score formula + severity mapping.

Covers the full (VlmLabel x AltAdequacy) cross-product so any change to
weights or thresholds is caught immediately.
"""

from __future__ import annotations

import math

import pytest

from audit.analyzer.vlm.base import VlmLabel
from audit.synthesizer.alt_compare import AltAdequacy
from audit.synthesizer.priority import (
    ADEQUACY_WEIGHTS,
    CLASSIFICATION_WEIGHTS,
    Severity,
    compute_priority_score,
    severity_for,
)


def test_severity_boundaries() -> None:
    assert severity_for(8.0) is Severity.CRITICAL
    assert severity_for(7.99) is Severity.MAJOR
    assert severity_for(5.0) is Severity.MAJOR
    assert severity_for(4.99) is Severity.MINOR
    assert severity_for(2.0) is Severity.MINOR
    assert severity_for(1.99) is Severity.INFO
    assert severity_for(0.0) is Severity.INFO


@pytest.mark.parametrize(
    ("classification", "adequacy", "occurrences", "above_fold", "expected_score"),
    [
        # Cross product with occurrences=0 and not above fold — pure weight sums.
        (VlmLabel.ESSENTIAL, AltAdequacy.MISSING, 0, False, 4 + 3),
        (VlmLabel.ESSENTIAL, AltAdequacy.INADEQUATE, 0, False, 4 + 2),
        (VlmLabel.ESSENTIAL, AltAdequacy.PARTIAL, 0, False, 4 + 1),
        (VlmLabel.ESSENTIAL, AltAdequacy.ADEQUATE, 0, False, 4 + 0),
        (VlmLabel.INFORMATIONAL, AltAdequacy.MISSING, 0, False, 3 + 3),
        (VlmLabel.LOGO, AltAdequacy.MISSING, 0, False, 1 + 3),
        (VlmLabel.DECORATIVE, AltAdequacy.INADEQUATE, 0, False, 1 + 2),
        (VlmLabel.NO_MEANINGFUL_TEXT, AltAdequacy.ADEQUATE, 0, False, 0 + 0),
        (None, AltAdequacy.MISSING, 0, False, 0 + 3),
    ],
)
def test_priority_formula_weights_cross_product(
    classification: VlmLabel | None,
    adequacy: AltAdequacy,
    occurrences: int,
    above_fold: bool,
    expected_score: int,
) -> None:
    score = compute_priority_score(
        classification=classification,
        adequacy=adequacy,
        occurrence_count=occurrences,
        above_fold=above_fold,
    )
    assert score == pytest.approx(float(expected_score))


def test_occurrence_count_adds_log1p() -> None:
    base = compute_priority_score(
        classification=VlmLabel.ESSENTIAL,
        adequacy=AltAdequacy.ADEQUATE,
        occurrence_count=0,
        above_fold=False,
    )
    scored = compute_priority_score(
        classification=VlmLabel.ESSENTIAL,
        adequacy=AltAdequacy.ADEQUATE,
        occurrence_count=10,
        above_fold=False,
    )
    assert scored == pytest.approx(base + math.log1p(10), abs=0.01)


def test_above_fold_adds_one() -> None:
    below = compute_priority_score(
        classification=VlmLabel.ESSENTIAL,
        adequacy=AltAdequacy.ADEQUATE,
        occurrence_count=0,
        above_fold=False,
    )
    above = compute_priority_score(
        classification=VlmLabel.ESSENTIAL,
        adequacy=AltAdequacy.ADEQUATE,
        occurrence_count=0,
        above_fold=True,
    )
    assert above - below == pytest.approx(1.0)


def test_essential_missing_above_fold_on_many_pages_is_critical() -> None:
    # 4 (essential) + 3 (missing) + log1p(50)=~3.93 + 1 (above fold) = ~11.9 → critical
    score = compute_priority_score(
        classification=VlmLabel.ESSENTIAL,
        adequacy=AltAdequacy.MISSING,
        occurrence_count=50,
        above_fold=True,
    )
    assert severity_for(score) is Severity.CRITICAL


def test_decorative_adequate_single_page_is_info() -> None:
    score = compute_priority_score(
        classification=VlmLabel.DECORATIVE,
        adequacy=AltAdequacy.ADEQUATE,
        occurrence_count=1,
        above_fold=False,
    )
    assert severity_for(score) is Severity.INFO


def test_weight_tables_cover_every_enum_value() -> None:
    # Keys drift over time — this locks the tables against accidental removals.
    for label in VlmLabel:
        assert label in CLASSIFICATION_WEIGHTS
    for bucket in AltAdequacy:
        assert bucket in ADEQUACY_WEIGHTS
