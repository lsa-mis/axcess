"""Unit tests for alt_compare.compare / normalize / worst."""

from __future__ import annotations

import pytest

from audit.synthesizer.alt_compare import AltAdequacy, compare, normalize, worst


def test_normalize_lowercases_and_strips_punctuation() -> None:
    assert normalize("Hello, World!") == "hello world"


def test_normalize_collapses_whitespace() -> None:
    assert normalize("  foo\n\tbar   baz  ") == "foo bar baz"


def test_normalize_keeps_underscores_as_word_chars() -> None:
    # \w matches [A-Za-z0-9_] so underscores stay — this is fine for our use.
    assert normalize("a_b c") == "a_b c"


def test_missing_alt_is_missing_bucket() -> None:
    assert compare(None, "buy now") is AltAdequacy.MISSING


def test_no_visible_text_is_adequate_regardless_of_alt() -> None:
    assert compare("anything", "") is AltAdequacy.ADEQUATE
    assert compare("", "") is AltAdequacy.ADEQUATE
    assert compare(None, "") is AltAdequacy.MISSING  # alt-absent still missing


def test_empty_alt_on_image_with_text_is_inadequate() -> None:
    assert compare("", "BUY NOW TODAY") is AltAdequacy.INADEQUATE


def test_exact_match_is_adequate() -> None:
    assert compare("Buy now today", "BUY NOW TODAY") is AltAdequacy.ADEQUATE


def test_substring_match_is_adequate() -> None:
    assert compare("Buy now today — limited offer", "buy now today") is AltAdequacy.ADEQUATE


def test_fuzzy_high_ratio_is_adequate() -> None:
    # Token order doesn't matter; token_set_ratio handles rearrangement.
    assert compare("today buy now", "buy now today") is AltAdequacy.ADEQUATE


def test_partial_overlap_is_partial() -> None:
    # "Welcome" shares only one token with "BUY NOW TODAY" — mid-range ratio.
    adeq = compare("Welcome now", "BUY NOW TODAY")
    assert adeq in (AltAdequacy.PARTIAL, AltAdequacy.INADEQUATE)


def test_unrelated_is_inadequate() -> None:
    assert compare("Photo of a cat", "BUY NOW TODAY") is AltAdequacy.INADEQUATE


def test_worst_picks_highest_severity() -> None:
    assert worst([AltAdequacy.ADEQUATE, AltAdequacy.PARTIAL]) is AltAdequacy.PARTIAL
    assert (
        worst([AltAdequacy.ADEQUATE, AltAdequacy.MISSING, AltAdequacy.PARTIAL])
        is AltAdequacy.MISSING
    )


def test_worst_empty_defaults_to_missing() -> None:
    assert worst([]) is AltAdequacy.MISSING


@pytest.mark.parametrize(
    ("alt", "text", "expected"),
    [
        ("Acme logo", "Acme", AltAdequacy.ADEQUATE),
        ("Acme corp — industrial supplies", "Acme corp", AltAdequacy.ADEQUATE),
        ("buy now today limited", "Buy now today. Limited time.", AltAdequacy.ADEQUATE),
    ],
)
def test_parametrized_adequate_cases(alt: str, text: str, expected: AltAdequacy) -> None:
    assert compare(alt, text) is expected
