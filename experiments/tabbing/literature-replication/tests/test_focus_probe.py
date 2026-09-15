"""Tests for the focus-order probe (manager finding: G1b control gap).

`FEASIBILITY.md` reported 11-15 distinct focus stops and cited them as evidence
that tagging is inert. Those numbers were tagged-only. The untagged arm recorded
3 / 1 / 1, not because focus order differed but because the probe read the
census attribute and fell back to `e.tagName` when it was absent -- so the
untagged runs were counting distinct *tag names*.

That left the inertness claim resting on DOM signature alone, and silent about
focus order, which is the one dimension a keyboard detector actually depends on.
The probe therefore has to identify a focused element the same way whether or
not the census ran.
"""

from __future__ import annotations

from tools import replay


def test_focus_probe_does_not_depend_on_the_census_attribute():
    """Identity must not come from the attribute whose effect is under test.

    Using it would make the tagged and untagged arms measure different things,
    which is exactly the defect this replaces.
    """
    assert replay.CENSUS_ATTR not in replay.FOCUS_PROBE_JS
    assert "data-litrep" not in replay.FOCUS_PROBE_JS


def test_focus_probe_is_label_independent():
    for forbidden in ("data-probe", "truth", "violation", "decoy"):
        assert forbidden not in replay.FOCUS_PROBE_JS


def test_focus_probe_builds_a_structural_path_not_just_a_tag_name():
    """A bare tagName collapses every link on a page into one stop."""
    source = replay.FOCUS_PROBE_JS
    assert "parentElement" in source
    assert "tagName" in source
    # An index within the parent is what separates two sibling <a> elements.
    assert "indexOf" in source or "children" in source


def test_focus_probe_reports_the_absence_of_focus_distinctly():
    """`body` and "nothing focused" are different observations."""
    assert "NONE" in replay.FOCUS_PROBE_JS


def test_focus_probe_walks_shadow_roots_like_the_census():
    """Focus can land inside a shadow root; the census already walks them."""
    assert "getRootNode" in replay.FOCUS_PROBE_JS or "shadowRoot" in replay.FOCUS_PROBE_JS
