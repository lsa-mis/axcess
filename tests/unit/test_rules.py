"""Tests for remediation rule loader."""

from __future__ import annotations

import pytest

from audit.analyzer.vlm.base import VlmLabel
from audit.synthesizer.alt_compare import AltAdequacy
from audit.synthesizer.rules import RemediationRules


@pytest.fixture(scope="module")
def rules() -> RemediationRules:
    return RemediationRules.load()


def test_rules_file_loads_at_least_one_rule_per_adequacy(rules: RemediationRules) -> None:
    assert len(rules) >= 16  # 4 classifications x 4 adequacies minimum


def test_every_class_adequacy_combo_resolves_to_a_hint(rules: RemediationRules) -> None:
    for label in VlmLabel:
        for adeq in AltAdequacy:
            hint = rules.lookup(label.value, adeq)
            assert hint, f"no rule matched {label.value} + {adeq.value}"


def test_wildcard_catches_unknown_classifications(rules: RemediationRules) -> None:
    # e.g. inline SVG text produces classification=None
    for adeq in AltAdequacy:
        assert rules.lookup(None, adeq)


def test_first_match_wins_over_wildcard(rules: RemediationRules) -> None:
    # Essential/missing rule is more specific than the wildcard fallback.
    specific = rules.lookup("essential", AltAdequacy.MISSING)
    wildcard = rules.lookup("some_unknown", AltAdequacy.MISSING)
    assert specific is not None
    assert wildcard is not None
    assert specific != wildcard
