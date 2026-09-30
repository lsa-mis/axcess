"""tests/support/golden_delta.py: draft goldens stored as diffs against finals.

The export goldens trust ``apply_delta(final, delta)`` to rebuild a draft
byte for byte, so the round trip is checked on the inputs a plain line
split gets wrong, the output is checked against ``difflib``'s own unified
diff, and a delta that no longer fits its base must raise, never apply
loosely.
"""

from __future__ import annotations

import difflib

import pytest
from support.golden_delta import DeltaError, apply_delta, make_delta, split_lines

_FORTY = "".join(f"{n}\n" for n in range(40))
_PAIRS = [
    pytest.param("a\nb\nc\n", "a\nB\nc\n", id="replace"),
    pytest.param("a\nb\n", "top\na\nb\n", id="insert-first"),
    pytest.param("a\nb\n", "a\nb\nend\n", id="insert-last"),
    pytest.param("a\nb\nc\n", "a\nc\n", id="delete-middle"),
    pytest.param("a\nb\nc\n", "a\nb\n", id="delete-last"),
    pytest.param("", "a\n", id="from-empty"),
    pytest.param("a\n", "", id="to-empty"),
    pytest.param("x\r\ny\r\n", "x,D\r\ny,D\r\n", id="crlf"),
    pytest.param('"Company\rlogo",1\r\nz\r\n', '"Company\rlogo",1,D\r\nz,D\r\n', id="bare-cr"),
    pytest.param("a\nb", "a\nb\n", id="gains-final-newline"),
    pytest.param("a\nb\n", "a\nb", id="loses-final-newline"),
    pytest.param("a\nb", "a\nc", id="no-final-newline"),
    pytest.param(
        "a\x0cb\N{LINE SEPARATOR}c\n", "a\x0cb\N{LINE SEPARATOR}C\n", id="other-line-breaks"
    ),
    pytest.param(_FORTY, _FORTY.replace("2\n", "X\n", 1).replace("38\n", "Y\n"), id="two-hunks"),
]


@pytest.mark.parametrize("context", [0, 1, 3])
@pytest.mark.parametrize(("before", "after"), _PAIRS)
def test_round_trip_is_exact(before: str, after: str, context: int) -> None:
    delta = make_delta(before, after, before_name="final", after_name="draft", context=context)
    assert delta.startswith("--- final\n+++ draft\n@@ ")
    assert apply_delta(before, delta) == after


def test_equal_texts_need_no_delta() -> None:
    assert make_delta("a\r\nb", "a\r\nb", before_name="x", after_name="y", context=1) == ""
    assert apply_delta("a\r\nb", "") == "a\r\nb"


def test_split_lines_splits_on_newline_only() -> None:
    text = 'a\r\n"b\rc"\x0cd\N{LINE SEPARATOR}e\nf'
    assert split_lines(text) == ["a\r\n", '"b\rc"\x0cd\N{LINE SEPARATOR}e\n', "f"]
    assert "".join(split_lines(text)) == text
    assert split_lines("") == []


def test_output_is_a_standard_unified_diff() -> None:
    """Readable by ``patch`` and reviewers: the same text difflib writes."""
    before = "".join(f"line {n}\n" for n in range(30))
    after = before.replace("line 3\n", "line three\n").replace("line 20\n", "") + "tail\n"
    expected = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            "final",
            "draft",
            n=2,
        )
    )
    assert make_delta(before, after, before_name="final", after_name="draft", context=2) == expected


def test_missing_final_newline_uses_the_standard_marker() -> None:
    delta = make_delta("a\nb", "a\nc", before_name="f", after_name="d", context=1)
    assert delta.endswith("-b\n\\ No newline at end of file\n+c\n\\ No newline at end of file\n")


@pytest.mark.parametrize(
    ("base", "message"),
    [
        pytest.param("a\nX\nc\n", "line 2 does not match", id="changed-removed-line"),
        pytest.param("A\nb\nc\n", "line 1 does not match", id="changed-context-line"),
        pytest.param("z\na\nb\nc\n", "does not match", id="shifted-base"),
        pytest.param("a\n", "does not match", id="truncated-base"),
    ],
)
def test_a_delta_that_no_longer_fits_raises(base: str, message: str) -> None:
    delta = make_delta("a\nb\nc\n", "a\nB\nc\n", before_name="f", after_name="d", context=1)
    with pytest.raises(DeltaError, match=message):
        apply_delta(base, delta)


@pytest.mark.parametrize(
    "delta",
    [
        pytest.param("@@ -1 +1 @@\n-a\n+b\n", id="no-file-headers"),
        pytest.param("--- f\n+++ d\n-a\n+b\n", id="no-hunk-header"),
        pytest.param("--- f\n+++ d\n@@ -1,2 +1,2 @@\n-a\n+b\n", id="ends-inside-a-hunk"),
        pytest.param("--- f\n+++ d\n@@ -1 +1 @@\n-a\n+b\n+c\n", id="more-lines-than-counted"),
        pytest.param("--- f\n+++ d\n@@ -1 +2 @@\n-a\n+b\n", id="result-lands-elsewhere"),
        pytest.param("--- f\n+++ d\n@@ -1 +1 @@\n?a\n+b\n", id="unknown-line-tag"),
        pytest.param(
            "--- f\n+++ d\n@@ -2 +2 @@\n-b\n+B\n@@ -1 +1 @@\n-a\n+A\n", id="hunks-out-of-order"
        ),
    ],
)
def test_a_malformed_delta_raises(delta: str) -> None:
    with pytest.raises(DeltaError):
        apply_delta("a\nb\n", delta)
